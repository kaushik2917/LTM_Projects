# FAPT-Guard real-time defense pipeline

Status: backend implemented and tested in REPLAY and LAB-safe operation. **LIVE endpoint operation has not been validated** (no Sysmon/Wazuh lab endpoint yet). **No qualified real-data prediction model exists**, so every live/replay prediction currently ABSTAINS. **Response execution is DRY_RUN only**; no host action has ever been executed. No UI was changed.

## Flow

```
telemetry (Sysmon / Windows Security / Wazuh / OpTC eCAR / canonical)
  -> normalize (backend/app/defense/events.py)          malformed -> quarantine (raw bytes kept)
  -> store event + immutable evidence (store.py, evidence.py)   dedup per (mode, raw hash)
  -> inference (inference.py -> services/future_prediction_service.predict)   gate refuses -> ABSTAIN
  -> risk (risk.py)            separate engine, documented formula
  -> policy (policy.py)        thresholds, allowlist, approval, protected targets
  -> response request (responses.py)   cooldown/duplicate suppression, PENDING_APPROVAL
  -> analyst approve -> execute (executor.py, DRY_RUN) -> verify (verification.py)
  -> incident correlation (incidents.py) + hash-chained audit_log
```

The model predicts; the evidence engine preserves; the risk engine assesses; the policy engine decides; the executor runs only allowlisted actions; verification checks the effect.

## Modes

Every row stores `mode`: `LIVE` (real endpoint telemetry), `LAB` (controlled testing), `REPLAY` (historical files). Queries and `/api/defense/metrics?mode=` never pool modes; the same raw event in two modes produces two distinct event IDs.

Estimands (config `inference.estimand`): LIVE/LAB use processing time as the cutoff and only see events whose `collection_time <= cutoff`. REPLAY is offline event-time replay: cutoff = triggering event time, availability assumed equal to event time.

## Storage

`data/defense.sqlite3` (git-ignored, separate from `workflow.sqlite3`). Path override: `FAPT_DEFENSE_DB`. Tables are insert-only (SQLite triggers abort UPDATE/DELETE); response state changes are appended `response_transitions`. Every pipeline decision is written to a global SHA-256 hash chain (`/api/defense/audit/verify`). Limitation: no external anchor, so tail truncation or full replacement of the file is not detectable locally.

## Canonical event and evidence

Schema `canonical-event-v1` contains the fields of the project specification; unavailable values stay `null`. `technique_id/name/confidence` are populated only from a validated label source and are `null` for all ingested telemetry today. Behavior-rule hits (`services/attack_service.map_event`) are stored separately in `candidate_techniques` with `assertion: OBSERVED_CANDIDATE`, `mapping_status: CANDIDATE`. Distinctions kept: OBSERVED_CANDIDATE, PREDICTED (model output), VALIDATED (none exist), THIRD_PARTY (OpTC labels are never ingested as techniques).

Timestamps must carry a timezone, except Sysmon `UtcTime`, which the Sysmon schema documents as UTC (`timestamp_basis` records this). Events more than `future_skew_seconds` ahead of collection, or arriving out of order, are kept and flagged.

Raw bytes: `/events/ndjson` stores and hashes the exact received line (`raw_hash_basis: exact_received_bytes`); the JSON endpoint hashes canonical JSON of the received object. Evidence records are sealed with SHA-256 over the whole record and link to the raw event hash; `GET /api/defense/evidence/{id}` re-verifies both. Evidence describes an observation; it does not by itself establish an attack.

## Prediction and abstention

`inference.py` wraps the existing `predict()` and its `qualified_model` gate (observed data, hashes, leakage checks, validation and holdout required). Synthetic models are never applied to LIVE/LAB/REPLAY telemetry. With the gate closed the result is `ABSTAINED` with the gate reason and decision `MONITOR_ONLY`. When a qualified model exists, predictions below `abstain_below_probability` (0.5) or above `abstain_above_uncertainty` (0.6, normalized entropy) also abstain. Calibration is reported as `NOT MEASURED`. Inference is throttled per host (`min_interval_seconds`).

## Risk (config `risk`, version `defense-config-v1`)

```
risk = max(predictive, observed)
predictive = probability * (1 - uncertainty) * evidence_strength * impact(predicted technique) * asset_criticality
observed   = candidate_discount(0.5) * evidence_strength * max impact(OBSERVED_CANDIDATE techniques) * asset_criticality
levels: LOW < 0.25 <= MEDIUM < 0.5 <= HIGH < 0.75 <= CRITICAL
```

`impact` is the maximum configured tactic impact; `evidence_strength` is the mean telemetry-quality score (penalties for skew, ordering, missing process/user), not a probability of maliciousness; `asset_criticality` defaults to 0.5 (`default_assumption`) unless configured per host. All weights are analyst assumptions and every record stores them.

## Policy and response

| Level | Actions |
|---|---|
| LOW | MONITOR |
| MEDIUM | ALERT, PRESERVE_EVIDENCE |
| HIGH | ALERT, PRESERVE_EVIDENCE, containment candidates requiring approval |
| CRITICAL | PRESERVE_EVIDENCE, containment candidates (approval required; `auto_execute_critical` is false, and irreversible actions are never automatic) |

Containment is proposed only for a `PREDICTED` result with probability >= 0.75 and evidence strength >= 0.8. Abstained predictions at HIGH/CRITICAL become `ANALYST_REVIEW`. Candidate actions come only from ATT&CK 19.2 `mitigates` relationships mapped to local controls (`defensive_mapping.mitigation_controls`, e.g. M1031/M1037 -> BLOCK_DESTINATION_IP). D3FEND is `NOT_LOADED`.

Allowlist: `BLOCK_DESTINATION_IP` (reversible), `TERMINATE_PROCESS` (irreversible), `DISABLE_LOCAL_ACCOUNT` (reversible). Parameters come from the triggering telemetry fields and are validated (IP syntax, protected networks, protected processes/accounts). Commands are fixed argv templates; no text from predictions is ever placed in a command. The executor imports no subprocess module: `DRY_RUN` records the command and rollback only. Duplicate requests with the same action/target inside `cooldown_seconds` are suppressed and recorded.

## Verification

After execution, events from the same host/mode inside `verification.window_minutes` are checked for the contained target (destination IP, PID+image, or account), and risk is reassessed (stored as new prediction/risk rows linked to the incident). Outcome rule:

- not actually executed (dry run) -> `UNKNOWN` (no effect can be attributed)
- no subsequent telemetry -> `UNKNOWN`
- target activity continues -> `FAILED`
- target absent and risk fell by >= 50% -> `SUCCESS`, otherwise `PARTIAL_SUCCESS`

`escalate` is set when reassessed risk is HIGH or CRITICAL.

## API (`/api/defense`)

Read endpoints (open, like the rest of the app): `health`, `system/status`, `events`, `events/{id}`, `quarantine`, `evidence`, `evidence/{id}`, `predictions`, `predictions/{id}`, `risk`, `risk/{id}`, `decisions/{id}`, `incidents`, `incidents/{id}?expand=true`, `responses`, `responses/{id}`, `responses/{id}/verification`, `models`, `policies`, `mappings/{technique_id}`, `audit`, `audit/verify`, `metrics?mode=`.

Ingestion: `POST events` (`{mode, source_format, events, synchronous}`) and `POST events/ndjson?mode=&source_format=`. Requires `Authorization: Bearer $FAPT_INGEST_TOKEN` only when that variable is set. Token-bucket rate limit (429) and bounded queue backpressure (429).

Response actions: `POST responses/{id}/approve` (`{comment}`), `/execute`, `/rollback`, `/verify`. Require `Authorization: Bearer $FAPT_RESPONSE_TOKEN` and `X-Analyst-Id`; if the variable is unset they return 503 (fail closed). The analyst ID is recorded verbatim in transitions and the audit chain.

Replay CLI (from `backend/`): `python -m app.defense.pipeline <file.jsonl> --format sysmon --mode REPLAY`.

## Lab deployment (not yet validated)

1. Separate Windows lab VM (not a corporate endpoint) with Sysmon and a Wazuh agent.
2. Forward Wazuh Windows eventchannel alerts as JSON lines to `POST /api/defense/events/ndjson?mode=LAB&source_format=wazuh` with the ingest token.
3. Keep `response.execution_mode = DRY_RUN`. A real execution backend is intentionally absent and must be added, reviewed and authorized separately for the lab VM only.

## Tests

`backend/tests/test_defense.py` (20 tests): valid/malformed/duplicate events, timestamp handling, Security/Wazuh adapters, exact-byte hashing, evidence sealing and immutability, abstention without a model, prefix-only inference, abstention thresholds, throttling, risk formula and evidence weighting, policy allow/deny/approval, executor allowlist, response lifecycle with duplicate suppression and rollback, verification outcomes and escalation, token/analyst enforcement, end-to-end incident chain and audit verification, async worker resilience, backpressure and rate limiting. Model outputs in the predictive-path tests are mocks and are labelled as such; they do not represent a real model.

## Not measured

Prediction accuracy (Top-k, Macro-F1, MRR, Brier, ECE), lead time, prevention/containment success, false-prevention rate and attack-progression reduction are **NOT MEASURED**: there is no qualified real-data model, no independently validated future-technique labels for this telemetry, and no executed responses. `/api/defense/metrics` reports these as `null` with reasons.
