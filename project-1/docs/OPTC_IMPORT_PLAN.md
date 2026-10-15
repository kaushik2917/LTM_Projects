# OpTC Import Plan

Status: **PLANNING ONLY — no import has run.** Official raw telemetry is unavailable. This plan does not authorize application integration or training.

## 1. Expected raw file locations

Keep immutable originals under `data/external/optc/official/raw/`:

- `AIA-201-225.ecar-2019-12-08T11-05-10.046.json.gz`
- `AIA-201-225.ecar-last.json.gz`

The saved official listing places both in `ecar/evaluation/23Sep19-red/AIA-201-225/`. These are candidate shards for the SysClient0201 Day 1 pilot, not a verified complete experiment. The official README describes folder structure but does not list shard filenames. Actual time coverage must be inspected after acquisition. The latest listing request was blocked by corporate content filtering; previous downloads hit Google quota. No alternative official raw-telemetry download source identified in the acquired README, ecar.md or errata.md.

## 2. Expected file formats

Expect gzip containing one eCAR JSON object per line. Confirm gzip signature, full decompression CRC/EOF and JSONL before trusting the extension. Reject HTML, incomplete transfers, arrays and archives of an unexpected structure. Supplementary ZIP files contain selected JSONL records; `tasks.json` is a JSON array with annotations and process context, not raw importer input.

## 3. Required parsers

Python standard-library gzip and JSON parsers suffice for streaming inspection. Use strict UTF-8 and preserve bytes before decoding. Do not execute command lines or binaries described by events. Bound memory, record length and decompressed-byte budgets; hitting a budget means incomplete inspection, never a complete dataset. Any future parser implementation must be tested before integration.

## 4. Timestamp normalization

Keep original timestamp and normalized UTC timestamp separately. eCAR documentation describes `timestamp_ms`; examples and supplementary records also use `timestamp`. Numeric timestamps are epoch milliseconds; timezone-aware strings convert to UTC. Reject ambiguous, non-finite, boolean or out-of-range values. If both timestamp fields are present, compare them and quarantine conflicts rather than silently preferring one.

## 5. Event ID preservation

Preserve `id` as the source UUID, plus source-file hash, line number and exact line hash. Never substitute a generated UUID for a missing source ID. Missing IDs may be retained in quarantine with source references; they are unsuitable for a verified UUID linkage until reviewed.

## 6. Host identity preservation

Retain `hostname` exactly. Store any approved alias/case/FQDN normalization separately with a mapping record. Do not assume similarly named hosts are identical across collections. Scope joins by collection and host as well as UUID when appropriate.

## 7. Process identity preservation

Retain `actorID`, `objectID`, PID, PPID, TID, principal, object/action and available image paths. PIDs are reused; process UUID and host/collection context take precedence. Do not merge zero UUIDs or missing processes into one entity. Build process relationships only from evidence available at cutoff; future termination times and reconstructed future children are forbidden prefix features.

## 8. Source preservation

Original downloads are immutable. Derived tables belong under `processed/` with source references and versioned transformations. Keep official narrative, supplementary research annotations and derived reviewer decisions separate. Never relabel supplementary-only records as direct official downloads.

## 9. Raw-byte hash preservation

Compute SHA-256 for compressed source bytes and exact decompressed line bytes, including line endings. Store both scopes explicitly. Canonical parsed-content hashes may supplement these for duplicate detection but must not replace byte hashes. SHA integrity is not proof of semantic accuracy or authenticated publisher identity.

## 10. Deduplication policy

Keep all original source copies and an occurrence table. Collapse exact duplicate events only in a derived view. Compare collection/host/event UUID and canonical content; the same UUID with differing content is a conflict requiring review. Track overlap across archives and shards. Do not count overlapping research label archives as independent events or put duplicate sequences into different partitions.

## 11. Malformed-event handling

Quarantine invalid JSON, missing required fields, invalid clocks, conflicting UUID content and oversized records with file/line/hash/reason. Report denominators and rejected counts. No fabricated field values or silent repair. Sampling/limits must be explicit; partial ingestion is not complete chronological coverage.

## 12. Time-zone handling

Supplementary records contain explicit offsets. The official PDF does not declare a timezone. Retain printed PDF times as naive narrative values until reviewers establish an evidence-backed alignment. Record any assumed offset and uncertainty; never assign UTC or -04:00 silently. Event time is not ingestion/availability time. Without availability timestamps, label the future experiment an offline event-time replay and do not claim online causal availability.

## 13. Ground-truth linkage

Start with the official narrative and independently inspect full raw telemetry. Supplementary tasks provide candidate event/process links and label provenance. Respect process/event granularity; exclude invalid correlations and adjudicate conflicting labels. Match attempts and failures distinctly from successful behavior. Store reviewer, source references, clock alignment, ATT&CK version, technique decision and unresolved uncertainty. Predictor output and existing behavior rules are not ground truth.

## 14. Scenario grouping

Use campaign, collection, host relationships and attack episode evidence. A host/day window is not automatically an incident or independent scenario. Keep linked campaign days and pivots in one grouping component when they share attack state. Do not create extra independent scenarios merely to obtain a split.

## 15. Train/validation/test separation

Before training, freeze scenario/collection components and split them without overlap. If there are too few independent groups, stop. Keep calibration and optional conformal calibration separate from model selection and final test. Host-disjoint performance is a separate estimand; do not claim it when hosts overlap. The current single-host pilot cannot satisfy these requirements.

## 16. Future-event construction

Use strict `event_time > cutoff` through the fixed horizon. Preserve censored/missing windows separately; absence of a mapped event is not proof of no attack. Targets are independently reviewed technique onsets, not archive membership or the model's own mappings. Repeated event records do not create new technique onsets.

## 17. Prediction cutoff construction

Use the fixed observation/horizon/grid rules in `OPTC_FUTURE_PREDICTION_PROTOCOL.md`. Require complete source coverage and adequate lead-in before accepting a cutoff. The illustrative Day 1 narrative cutoff is not an approved timezone-aware evaluation timestamp.

## 18. Leakage prevention

Use a feature allowlist, isolate annotations, validate clock boundaries and disjoint groups, and fingerprint events/sequences. Fit preprocessing only on training data. See `OPTC_LEAKAGE_CONTROL.md` and the standalone preparation checker. These checks are prerequisites, not a trained evaluation pipeline.

## 19. Independent evaluation procedure

Freeze the task definition, approved targets, split manifest, model selection rules and metric definitions before inspecting holdout results. Record source hashes, transformations and protocol version. Report missing coverage and exclusions. A final holdout is only meaningful after independent raw-ground-truth reconciliation and sufficient scenarios exist.

## Existing FAPT-Guard importer: exact current behavior

Read-only review of `backend/app/services/optc_service.py` and the research import route:

| Aspect | Current implementation |
|---|---|
| Input | Plain JSONL; gzip selected by `.gz` suffix. No ZIP or JSON-array support. |
| Required fields | Nonempty string hostname, actorID, objectID, object, action; numeric-millisecond or timezone-aware timestamp/timestamp_ms. Event `id` is stored but not required. |
| Normalization | UTC ISO timestamp; original hostname; actor as subject, objectID as object; lowercased object/action evidence type; properties retained. Subject type is always process. |
| Grouping | `OPTC:{hostname}:{UTC-date}`; explicitly host/day, not a confirmed attack incident. |
| Database | Default `data/optc.sqlite3`; events and imports tables plus timeline index. Main workflow import route also records an audit event. Neither was invoked. |
| Identity/hash | Evidence ID `OPTC-` plus SHA-256 of exact input line; full source-file SHA-256 also recorded. Raw line stored as BLOB; UUID stored separately. |
| Deduplication | `digest` primary key / INSERT OR IGNORE. Same UUID with changed JSON formatting/content is not deduplicated or flagged. |
| Errors | Counts rejected rows; retains first 20 errors. Default cap 100,000 records; API permits at most 1,000,000 and marks truncated imports. A truncated gzip read does not verify its entire CRC/coverage. |
| API location | Only files directly inside `data/optc/`; new acquisition paths are not accepted. A later integration decision is required; no files moved. |
| ATT&CK | `map_event` emits candidate rules for PowerShell T1059.001, event-log clearing T1070.001 and shadow-copy deletion T1490 against the pinned catalog. Confidence is null; these are hypotheses, not independent labels. |
| Limits | No scenario labels, target reconciliation, clock uncertainty, observed-at clock, semantic UUID conflict checking, archive provenance separation or leakage-safe split construction. Numeric boolean/non-finite validation and properties typing are weaker than this proposed import contract. |

Do not run the current importer on the supplementary ZIP/task array or connect it to the incident workflow during preparation.
