# Final defense review — 2026-10-08

## Scope and repository state

PASS: Reviewed the existing `feature/live-telemetry-lab` branch. The initial working tree contained only the user's two-line LSASS rule addition in `backend/app/services/attack_service.py`. It was preserved without alteration. No commit, push, reset, clean, dataset deletion, real attack, or real containment was performed.

Added:

- `backend/tests/test_attack_rules.py`: two tests with seven subtests covering the exact MiniDump example, case handling, image/command alternatives, missing indicators, pinned metadata, and uncalibrated CANDIDATE status.
- `backend/scripts/verify_defense_demo.py`: executable API verification using synthetic REPLAY telemetry, fresh synthetic host names, duplicate/quarantine checks, independent SHA-256 recomputation, linked object retrieval, metrics, health, and OpenAPI checks. Each run appends two events, two evidence records, two assessments, one incident, and one quarantine record. It never invokes response execution.
- This report: commands, measured results, and limitations.

Browser tests also wrote ignored test artifacts and appended normal fixture workflow records. Generated tracked screenshots and the benchmark report were copied into `frontend/test-results/final-review-approved-20261008/generated/`, then restored to their initially clean contents.

## Architecture inspected

| Stage | Existing implementation |
|---|---|
| Startup/routes | `backend/app/main.py`, `backend/app/api/defense.py` |
| Ingest, deduplication, orchestration | `backend/app/defense/pipeline.py` |
| Canonical schema/adapters/quarantine validation | `backend/app/defense/events.py`; `extra="forbid"`, unknown input fields rejected |
| ATT&CK candidates | `backend/app/services/attack_service.py`; local Enterprise ATT&CK 19.2 STIX catalog |
| Prediction | `defense/inference.py`, `services/future_prediction_service.py`; qualified observed-data model gate |
| Risk/policy | `defense/risk.py`, `defense/policy.py`, `backend/config/defense.json` |
| Evidence/storage/audit | `defense/evidence.py`, `defense/store.py`; append-only `data/defense.sqlite3` |
| Incidents | `defense/incidents.py`; correlate at MEDIUM or above |
| Responses/verification | `defense/responses.py`, `executor.py`, `verification.py`; DRY_RUN only |
| Frontend | Existing Next.js 16 / React app, npm lockfile, seven pages, Playwright tests |

Python is the root `.venv` (Python 3.14). Core and research requirements are in `backend/requirements*.txt`. Existing tests cover import, synthetic/temporal prediction, research validity, workflow, and defense safety. The supplied data and models remain unchanged; no training or downloads were needed.

## Validation results

| Check | Result |
|---|---|
| Backend suite | PASS: 66 passed, 1 warning, 22 subtests passed; includes original response approval, allowlist, rollback and DRY_RUN tests |
| Python compile | PASS: rule, new tests, and replay script |
| Frontend lint | PASS: `npm.cmd run lint` |
| Frontend production build | PASS: TypeScript and all seven pages built |
| Browser tests | PASS: 14 passed in 1.8 minutes, including desktop/mobile preservation, actual API rejection feedback, simulated 500/refresh failures, and all navigation links |
| Backend | PASS: reused existing project Uvicorn process on `127.0.0.1:8001`; verified its command line; no duplicate server started |
| Frontend | PASS: started production server on `127.0.0.1:3000` |
| Health/status/docs | PASS: `status=ok`, `last_error=null`, pipeline `failed=0`; API `online`; docs HTTP 200 |
| OpenAPI | PASS: 28 defense paths; ingestion modes/formats and forbidden additional request fields retained |
| Git whitespace | PASS: `git diff --check`; only an LF/CRLF advisory |

WARNING: Initial sandbox test run reported 46 failed, 20 passed, 13 errors, and 23 warnings due Windows temporary-directory/SQLite access restrictions. Approved execution outside the sandbox passed. The frontend build and Playwright worker initially returned `spawn EPERM`; their approved retries passed. No dependency or safety setting was changed to make checks pass.

WARNING: Starlette TestClient reports deprecated `httpx` usage and recommends `httpx2`. Playwright emitted a harmless conflicting color-environment warning.

## Final synthetic REPLAY run

Full API responses are retained locally in `data/final-defense-review-run.json` (ignored generated artifact). Run ID: `2d2e9379`. Fresh synthetic host names prevent prior host windows or inference throttling from contaminating the demonstration. Commands were submitted as JSON telemetry text only.

| Object | LSASS scenario | Shadow-copy scenario |
|---|---|---|
| Event | `EVT-8BBBECA7153EC8A9ED20CDE6` | `EVT-FF099E3D5C9CF04CD4A3B1F0` |
| Evidence | `EVD-7B13FADE37924789` | `EVD-B4605412F8954245` |
| Prediction | `PRED-85E972C0EA9D4A6B` | `PRED-0E8AB36287DC4635` |
| Risk | `RISK-43676F4590E641B9` | `RISK-2B55E2A52F87413E` |
| Decision | `POL-FC622C0D35D44B4E` | `POL-C51129DF7F464A6A` |
| Technique candidate | T1003.001 / LSASS Memory | T1490 / Inhibit System Recovery |
| Risk score/level | 0.225 / LOW | 0.25 / MEDIUM |
| Policy | MONITOR | ALERT, PRESERVE_EVIDENCE |
| Incident | NOT APPLICABLE: below threshold | `INC-D-F319772C099F40F0` |

PASS: Both accepted events were retrieved with their evidence, prediction, risk, and decision records. Evidence has provenance, parser/schema versions, host, user, action, raw hash, seal, and supporting relations. Both raw hashes and evidence seals were independently recomputed with Python SHA-256, and the API returned `record_seal_valid=true`, `raw_event_hash_valid=true`, `verified=true`.

PASS: Predictions ABSTAINED because validated observed sequential ATT&CK-labelled training/evaluation data is unavailable. Predicted technique, probability, uncertainty, model identity and training dataset version remain null. Risk uses the unchanged analyst assumptions, not measured attack likelihood.

PASS: Local T1003.001 mapping resolves to LSASS Memory in ATT&CK 19.2, with seven mitigations and configured local controls. D3FEND remains NOT_LOADED.

PASS: The MEDIUM incident links event, evidence, prediction, risk, and decision. Its title identifies MEDIUM risk and the synthetic host; `opened_at_level` and peak/latest risk expose severity. The affected user is available in expanded event/evidence records. WARNING: the existing incident schema has no explicit workflow `status` field or top-level user field; neither was invented.

PASS: Resubmitting each exact event returned duplicate and left all per-mode metrics unchanged. Unsupported canonical field was quarantined as `QRN-3CE6B60843174490` with a meaningful validation reason and was retrievable.

PASS: Final REPLAY metrics: 10 events, 10 evidence records, 10 predictions, all 10 abstained, two incidents, zero response records. The final run added exactly two of each event/evidence/prediction and one incident. A prior successful verification run remains preserved in the database.

PASS: Audit verification returned 23 records, `verified=true`, `failures=[]`; each demo ingestion and assessment has its own retrieved audit entry, plus the quarantine audit entry.

NOT APPLICABLE: No containment response was generated by these LOW/MEDIUM scenarios. Approval, DRY_RUN execution, verification UNKNOWN, and rollback were exercised by the existing automated tests using explicitly mocked model outputs in temporary test stores. Those mocks are not real prediction results. Production response authentication remains fail-closed because no response token is configured. No real host action was executed.

## Existing frontend workflow

PASS: `.env.local` points to `http://127.0.0.1:8001`; browser tests confirmed requests reach the backend and the fixture simulation gives visible preservation/simulation feedback. Successful browser scenarios had empty captured error lists. The desktop snapshot `25f64002-b05e-4edf-a8e4-6d81aeddea59` and simulation `546350ad-1e63-4687-9366-bb47dd57022b` were verified against the report and audit chain. SHA-256: `2ec70127537232e242d13e777a615c55378a0fcf90cd6611f6b20ab70edc7d52`. `host_action_executed=false`.

WARNING: Source fallbacks still use port 8000 when `NEXT_PUBLIC_API_URL` is absent; keep the existing environment override when building/starting on 8001. No UI redesign was needed.

NOT APPLICABLE: A dedicated real-time defense dashboard is not implemented. The existing frontend displays the fixture/research workflow; the real-time REPLAY objects are available through the API/Swagger. Its synthetic-trained fixture predictions are separate from the defense engine's ABSTAINED results.

## Limits

- NOT MEASURED: Real attack prediction accuracy, calibration, prevention success, evidence survival after actual containment, and live endpoint effectiveness. Defense metrics correctly return null with explanations.
- WARNING: Local evidence integrity does not authenticate the original sensor. The audit chain has no external anchor, so tail truncation/full replacement cannot be authenticated.
- WARNING: Synchronous demo ingestion leaves the async worker idle (`worker_alive=false`); health remains ok. Quarantine intentionally increases the failed-ingestion ratio, while pipeline failure count remains zero.
- WARNING: The existing backend process's console stream was not attached in this review. API health/audit and browser error capture were checked; a complete backend console-log review is not claimed.

## Commands used / repeat demonstration

From the repository root:

```powershell
git status --short
git branch --show-current
git diff --check
git diff
.\.venv\Scripts\python.exe -m py_compile backend/app/services/attack_service.py backend/tests/test_attack_rules.py backend/scripts/verify_defense_demo.py
```

From `backend`:

```powershell
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe scripts/verify_defense_demo.py
```

The full final replay output was saved using:

```powershell
..\.venv\Scripts\python.exe scripts/verify_defense_demo.py | Out-File -LiteralPath '../data/final-defense-review-run.json' -Encoding utf8
```

The direct rule check used this inert Python input via a PowerShell here-string piped to the same interpreter:

```python
from app.services.attack_service import map_event
print(map_event({'properties': {'command_line': r'rundll32.exe C:\Windows\System32\comsvcs.dll,MiniDump', 'image_path': r'C:\Windows\System32\rundll32.exe'}}))
```

From `frontend`:

```powershell
npm.cmd run lint
npm.cmd run build
npm.cmd run start -- --hostname 127.0.0.1 --port 3000
npx.cmd playwright test --output=test-results/final-review-approved-20261008
```

Existing backend command verified via process inspection (already running):

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

The replay script performs HTTP checks for health, status, docs, OpenAPI, mappings, metrics, audit, quarantine, ingestion, duplicate ingestion and every linked object. Servers are left running. No real containment endpoint is invoked by the demo script.
