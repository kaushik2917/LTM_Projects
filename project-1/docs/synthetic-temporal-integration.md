# Synthetic temporal prediction integration

**Historical initial integration report.** The subsequent [research validation pass](synthetic-temporal-validation.md) normalizes revoked ATT&CK labels and supersedes the model hash, predictions and metrics below.

Implemented October 3, 2026 in the existing FastAPI, Next.js and SQLite workflow. No application rebuild or UI redesign was performed. The existing prediction endpoint, dashboard, graph cutoff, explanation dialog, Research page and audit chain are used.

**SYNTHETIC DATASET — NOT REAL-WORLD VALIDATION.**

## Dataset and verification

Imported `FAPT-Guard-Synthetic-Temporal-Dataset-v1.0.zip`. The filename says v1.0; its verified manifest identifies **v1.0.1**, which is the version used throughout the application.

- ID: `FAPT-GUARD-SYN-TEMPORAL-001`
- Name: FAPT-Guard Synthetic Temporal ATT&CK Sequence Dataset
- Synthetic: true; real-world validation: false; generation seed: 42
- 600 scenarios, 4,175 events, 3,575 supervised next-technique samples
- 20 event technique labels, 19 target labels across the entire dataset
- All five file hashes supplied by the manifest were independently verified. Manifest and archive hashes were also calculated. Hash agreement checks bytes; it does not authenticate the dataset author's identity.

| Material | SHA-256 |
|---|---|
| Supplied ZIP | `1317c8c2ba411b9978d41f390141ba629b0b96febc372c9e7adfeedfad57681b` |
| Manifest | `9ebef685b77a26e91777259e2b6e302420b7314bb8a9c16ad98c1e2970e90352` |
| Temporal events CSV | `711cb602c6f6d08a848568d32205d60c603b832ad742a22beaf9b8c7b6747cc9` |
| Supervised samples CSV | `9b41fd67bde391502d9e530f37a645aac9dd997595f6f743c3611d2cd09e837c` |
| Scenario summary CSV | `b43128f545cac5cb20311d5586b14ba2ed4b2031f2398172d29391f1c1c2c9e7` |
| Transition statistics CSV | `ccf4fea3248a254adcf6056883071802559924cc9859d3db2c8bad2b8f439e47` |
| Supplied README | `b15f49f06eb5d4f809556e7b8d9600c23bd923ebbbbf4f4c30c5ab438730feaf` |

Files are preserved in `data/custom/synthetic_temporal/`. Import metadata is stored beside them and registered in the existing `data/manifest.json`. The supplied transition statistics cover the whole dataset and are **not used for fitting**.

## Supplied splits and temporal checks

| Split | Scenarios | Prefix samples | Templates |
|---|---:|---:|---|
| Train | 480 | 2,855 | 01, 02, 03, 04, 06, 07, 08, 09 |
| Validation | 60 | 360 | 10 |
| Test | 60 | 360 | 05 |

No repartitioning was performed. Scenario intersections for train/validation, train/test and validation/test are empty. Incidents cannot cross splits either.

Every scenario is sorted by parsed, timezone-aware timestamp. Every supervised row is checked against the source events: cutoff, prefix length, current technique, ordered techniques/tactics, evidence IDs, incident, split and the next chronological target event/technique/name/tactic must agree. Missing prefix rows, duplicate IDs, ambiguous simultaneous events, future evidence in prefixes and incorrect targets are rejected. The supervised target is exactly `target_next_technique_id` from `next_technique_samples.csv`.

The supplied split holds out entire templates. Validation contains `T1562.001`, and test contains `T1547.001`, neither of which occurs among training targets. The 17-class model cannot predict these unseen classes. These examples remain in evaluation and count as misses. Brier scoring includes the missing class probability contribution.

There are also repeated feature patterns across splits: 32 train/validation, 33 train/test and 27 validation/test. Thus disjoint scenarios and templates do not imply every short observed prefix is unique.

## Training and selection

Two reproducible models were fitted using training rows only:

1. **Transition frequency:** maximum-likelihood next-technique counts conditioned on mapped technique suffixes of length 3, 2, then 1. An unseen suffix backs off to a shorter suffix, then the training prior. No smoothing or fabricated probabilities.
2. **Random Forest:** existing sklearn approach, DictVectorizer fitted on training features only; 80 trees, max depth 12, minimum leaf size 2, random seed 42, one worker.

Shared features: last one/two/three mapped techniques, technique counts, transition counts, event and mapped-event counts, elapsed time, last event interval and source counts. IDs, scenario/template/split, targets, future events and response outcomes are excluded. All actual input evidence IDs and their mapped/unmapped status are retained separately for traceability. Techniques are prediction targets; tactics are not substituted for techniques.

Selection rule: highest **validation Macro-F1**, with ties favoring transition frequency. The selected model is **transition_frequency**. Test results are reported after selection; they do not select or fit the model.

Model version (artifact SHA-256):

`7e18bc1acce051cfb4ea56de9687d7cc0a69e550e1c6555bd816d32bad89bbc5`

Training artifact: `data/models/synthetic_temporal.joblib`. Configuration, library version, timestamp, feature version, hashes, splits and candidate results: `data/models/synthetic_temporal.json`. Retraining preserves deterministic predictions for the same inputs/configuration; the artifact hash may change because its provenance includes the training timestamp.

## Actual synthetic benchmark results

| Metric | Train | Validation | Test |
|---|---:|---:|---:|
| Accuracy | 0.759370 | 0.480556 | **0.350000** |
| Macro precision | 0.628177 | 0.144726 | 0.100282 |
| Macro recall | 0.670784 | 0.211111 | 0.172840 |
| Macro F1 | 0.621815 | 0.151581 | **0.110134** |
| Weighted F1 | 0.704059 | 0.431237 | **0.286661** |
| Top-3 accuracy | 0.994396 | 0.647222 | 0.361111 |
| Top-5 accuracy | 1.000000 | 0.669444 | 0.536111 |
| Multiclass Brier score | 0.300794 | 0.581859 | 0.979024 |
| ECE, 10 confidence bins | 0.000000 | 0.215089 | 0.373440 |

Macro metrics use the union of trained classes and actual partition classes, including zero-support classes. Zero-division precision/recall is zero. Test Macro-F1 averages 18 classes. Ranking ties are resolved by technique ID for reproducibility. Top-k may include zero-probability classes when fewer than k classes have positive probability; it is a ranking diagnostic, not a coverage guarantee.

The stronger Random Forest candidate had validation accuracy 0.344444 and Macro-F1 0.119048; test accuracy 0.466667 and Macro-F1 0.174436. It was not selected because its validation Macro-F1 was lower. Both candidates and the majority-label baseline are shown in Research.

**Confusion matrix locations:**

- Research → Future ATT&CK Technique Prediction → TEST evaluation
- `data/models/synthetic_temporal.json` → `evaluation.test.model.confusion_matrix`, with `class_order` and per-class precision/recall/F1/support
- `data/models/synthetic_temporal_test_predictions.csv`: all 360 test outputs, probabilities, actual targets, scenario IDs, cutoffs and supporting evidence IDs. Tests independently reconstruct the matrix and metrics from this file.

These are controlled synthetic benchmark measurements, not production accuracy or validation against real attacks.

## Application prediction and audit

Endpoint: `POST /api/workflow/INC-00001/prediction`

```json
{"cutoff_timestamp":"2026-09-25T10:05:02","task":"technique"}
```

The dashboard and graph also use the existing analysis endpoint to obtain and persist predictions. There is no disconnected demonstration model or hardcoded UI probability.

For the existing simulated incident, current mapping is `T1003.001 — LSASS Memory`, with mapping status **CANDIDATE**. Only two of the six evidence records have technique mappings (`EV-00004`: `T1059.001`; `EV-00006`: `T1003.001`). The other evidence records remain visible as unmapped inputs; their techniques are not invented.

| Rank | Actual model output | Probability |
|---|---|---:|
| 1 | T1077 — Windows Admin Shares | 0.6143790849673203 |
| 2 | T1021.002 — SMB/Windows Admin Shares | 0.3137254901960784 |
| 3 | T1041 — Exfiltration Over C2 Channel | 0.0718954248366013 |

`T1077` and `T1562.001` from the supplied dataset are absent from the active pinned ATT&CK 19.2 catalog. Original targets/names are retained. The top prediction is visibly marked **NOT IN ACTIVE CATALOG — original dataset label**. No automatic relabelling to a newer technique was performed.

Supporting evidence: `EV-00001`, `EV-00002`, `EV-00003`, `EV-00004`, `EV-00005`, `EV-00006`.

Verified stored prediction ID: `c6de6f19-45fb-41ed-8368-bd2e3375c372`, timestamp `2026-10-03T07:13:13.056060+00:00`, cutoff `2026-09-25T10:05:02`. Audit chain verification returned true, with zero legacy unsealed entries.

The incident is an application inference case, not a synthetic training incident. UI label: **“Synthetic-trained research model applied to simulated incident.”** The horizon is the next chronological labelled event after cutoff, not a specified number of seconds into the future. Fixture timestamps have no supplied timezone; the existing clock policy is preserved rather than assuming UTC.

SQLite `future_prediction` audit records contain prediction ID, incident, timestamp, cutoff, current/top technique, name, probability, full ranking, model name/version, training dataset/version/hash, input IDs, observed prefix, horizon, synthetic flag and uncertainty status. Identical inputs/model/cutoff reuse the existing record. The SHA-256 audit chain remains verified.

“Future prediction inputs and provenance” and the prediction explanation dialog expose the exact input records, model and dataset details. For the transition model, model-level feature importance is **unavailable**; no feature importance is invented.

## Missing measurements and remaining limitations

- Incident uncertainty: **NOT MEASURED**; no validated uncertainty procedure implemented for this synthetic inference case.
- Fitted probability calibration: **NOT MEASURED**; held-out Brier/ECE are actual diagnostics, not fitted calibration or incident error probabilities.
- Coverage: **NOT MEASURED**; no conformal prediction sets evaluated.
- Real-world validation: **NO**. The existing observed-data model qualification gate remains separate and unavailable.
- Application incident mappings and input distribution differ from fully labelled synthetic training prefixes. Prediction correctness for INC-00001 cannot be measured without a later ground-truth event.
- The synthetic corpus has legacy labels, limited template diversity and unseen validation/test classes. Low held-out results are reported without hiding them.
- File hashes and the local audit chain are integrity checks, not external signatures or guarantees of original sensor authenticity.
- Synthetic future probabilities are advisory context only. Existing response estimates are not recalculated using unsupported causal assumptions.
- **No real host action was executed.** Preservation still serializes local application evidence; response actions remain stored simulations.

## Verification

- 30 backend tests passed, including file hashes, scenario separation, target/prefix validation, timestamp sorting, no target/future inference leakage, stored prediction provenance, reconstructed held-out metrics, audit integrity and all simulation action names.
- All 12 browser scenarios passed across the full run and targeted rerun: prediction probabilities, explanation dialog, cutoff, Research/confusion matrix, seven routes, mobile workflow, preservation SHA-256, safe simulation and error feedback.
- The initial browser run caught a missing `modules` registry field that crashed Research. The importer and registry were corrected; the affected tests passed on rerun.
- Final prediction/Research checks recorded no page or console errors. Backend logs showed successful requests and no unexpected application traceback during the final workflow checks.
- TypeScript and ESLint passed. No production build was run.

## Files changed for this integration

Backend:

- `backend/app/synthetic_temporal.py` — importer, validation, shared features, transition/RF fitting, evaluation, artifact qualification and synthetic inference
- `backend/app/datasets.py` — existing CLI import/train commands
- `backend/app/temporal_prediction.py` — correct Brier contribution for unseen held-out classes
- `backend/app/services/future_prediction_service.py` — simulation-only synthetic inference and Research metadata
- `backend/app/services/metadata_service.py` — dataset registry integration
- `backend/app/services/workflow_service.py` — prediction IDs/timestamps embedded in stored audit results
- `backend/tests/test_synthetic_temporal.py`, `test_temporal_prediction.py`, `test_validity.py` — new checks and updated expectations

Frontend:

- `frontend/src/components/future-evaluation.tsx` — synthetic dataset/model results, matrix/support, limitations and provenance
- `frontend/src/components/research-analysis.tsx` — synthetic model label, provenance, missing uncertainty and legacy-label warning
- `frontend/src/app/page.tsx` — NOT MEASURED uncertainty display
- `frontend/tests/future-prediction.spec.ts`, `research-validity.spec.ts` — end-to-end prediction and Research checks

Data and documentation:

- `data/custom/synthetic_temporal/` — six original files and import metadata
- `data/manifest.json` — fifth dataset entry
- `data/models/synthetic_temporal.joblib`, `synthetic_temporal.json`, `synthetic_temporal_test_predictions.csv`
- `data/workflow.sqlite3` — local prediction and simulation audit records; existing ignored runtime storage
- `DATASETS.md`, `README.md`, `docs/future-prediction.md`, this report

Existing edits from earlier work were preserved. Browser benchmark tests also refresh the existing `data/benchmark_report.json` runtime report.

## Reproduction commands (PowerShell)

From the project root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app.datasets import-temporal 'C:\Users\T9975\Downloads\FAPT-Guard-Synthetic-Temporal-Dataset-v1.0.zip'
..\.venv\Scripts\python.exe -m app.datasets train-temporal
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In a second terminal, from the project root:

```powershell
Set-Location frontend
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Frontend checks in another terminal, from `frontend/`:

```powershell
npx.cmd tsc --noEmit
npm.cmd run lint
npx.cmd playwright test
npx.cmd playwright test tests/future-prediction.spec.ts tests/research-validity.spec.ts
```

The Windows environment requires process access outside the agent sandbox for browser workers, temporary SQLite tests and existing sklearn worker processes. Dependencies were already installed.

App: http://127.0.0.1:3000 · Research: http://127.0.0.1:3000/research · API: http://127.0.0.1:8001/docs
