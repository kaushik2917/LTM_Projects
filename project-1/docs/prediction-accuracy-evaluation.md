> Historical CHRONOLOGICAL-V2 experiment. For the separately frozen prospective evaluation, see [PROSPECTIVE-V1 results](prospective-prediction-results.md); for the 32.67% / 43.33% discrepancy, see [validity audit](temporal-research-validity.md). Historical values below remain unchanged.

# Future ATT&CK prediction: accuracy evaluation

## Objective and research status

Target Top-1 accuracy: 90%. **NOT ACHIEVED**. The validation-selected FAPT-Guard Temporal Prediction Model scored 32.6667% (49/150). No operational accuracy or superiority is established.

Task: given valid labelled observations available at cutoff, predict the first annotated ATT&CK event strictly later than cutoff, including repeats. This is next-event technique prediction, not current-event classification or a fixed-minute attack forecast. All probabilities come from fitted models.

The initial four-model benchmark was already evaluated before the expanded 90% request. Its artifacts are retained under `data/model_evaluations/chronological_prediction/initial-evaluation-v1/`. Test scenario identifiers and membership remained exactly fixed; model choices in the expanded run use only training/validation inputs. Prior knowledge of the initial test scores prevents claiming an untouched confirmatory experiment. Independent newly collected labelled sequences are required for that claim. The worse expanded result is reported rather than selecting a run by test accuracy.

## Repository and dataset assessment

- FastAPI serves the defense API and separate research endpoints. `app/defense` implements ingestion, evidence, inference, risk, policy, incidents, responses and audit verification. The existing `future_prediction_service` qualifies operational models using observed-data provenance and hashes.
- CSV 10 has ATT&CK IDs, incident IDs, host and timestamps, but rows are response alternatives, not chronological sensor observations.
- CSV 11 has synthetic sequence/stage targets without event timestamps. CSV 12 has unordered evidence quality records. CSV 13 contains benchmark descriptions and expected metrics. None supports observed next-event training.
- Synthetic temporal v1.0.1 has 600 scenarios / 4,175 events and supplied template-derived labels. Existing research behavior is preserved.
- Existing v2 data has temporal sequence IDs, incident/evidence IDs, host/user fields, timestamps and explicit generator annotations. This benchmark consumes that file unchanged; it never calls its generator. No new easy benchmark was generated to reach 90%.
- OpTC has documentation and ground-truth timelines, but no acquired raw event telemetry. Observed model training is blocked on timestamped telemetry, independently reconciled technique labels, label availability times, collection/host/incident grouping and independent evaluation data.

Source: `data/custom/synthetic_temporal_v2/scenarios.json`.
Version: **2.0.0**. SHA-256: `8433855364724c70b147ee480e0e2eb739aa7ae26d3e590657754bb22aab7a6e`.
Generator: existing `source-transition-walk-v1`, seed 20261003, derived from synthetic v1 transitions; paths include repeat/restart assumptions. These walks are not validated adversary attack families. Source event text is templated. Host/user identifiers repeat across scenarios and are excluded from features.

Size: **1000 scenarios/sequences, 9066 events, 1000 samples, 19 classes**. Rejected rows: **0**. Labels marked `CONFIRMED` by the generator remain `synthetic_annotation`; they are not sensor-confirmed or independently validated ground truth. Synthetic calendar dates extend into 2028 and represent generated ordering, not real observations.

## Temporal protocol and leakage controls

Whole scenarios are sorted by timezone-aware start time. Split: **700 train / 150 validation / 150 test**. One label-independent midpoint prefix per scenario; target is the immediate strictly later annotated event. The full sequence length determines where an offline cutoff is sampled, but is not a feature. No target/future values enter features.

Validation is divided chronologically into **100 model-selection / 50 probability-calibration** scenarios. No threshold tuning occurs. Full sequence ranges cannot overlap across split boundaries. Exact complete technique paths, evidence IDs, incident IDs and scenario IDs cannot duplicate across partitions. Repeated shorter prefixes are allowed: ambiguity is part of the task. Invalid timestamps, missing annotations/features and ambiguous equal timestamps reject a sequence and are recorded.

A strict whitelist uses only visible labels whose `label_known_at <= cutoff`. Existing `next_technique_id`, `next_event_timestamp`, split, outcome and template fields are ignored. No absolute date, sequence ID, host ID or user ID is a model feature. Group membership and sample hashes are written to the manifest. The initial test group membership is checked before training. All model, ensemble and calibration choices are written to `frozen_config.json` before test scoring; a changed configuration cannot silently overwrite that frozen protocol.

Train dates: 2026-01-01T00:00:38+00:00 through 2027-12-01T00:07:45+00:00.
Validation dates: 2027-12-02T00:00:51+00:00 through 2028-04-29T00:12:12+00:00.
Test dates: 2028-04-30T00:01:17+00:00 through 2028-09-26T00:08:06+00:00.

## Features (future_prediction_v2)

1. Prefix event and mapped-label counts.
2. Last one, two and three technique suffixes.
3. Prefix technique counts and adjacent transition counts.
4. Elapsed prefix seconds and last event interval; no absolute clock value.
5. Counts by evidence source and action category.
6. Technique counts in the latest three observations.
7. Adjacent repeated-technique count.
8. Last technique's tactics from the pinned ATT&CK 19.2 catalog.

Process ancestry, causal evidence-quality measurements and independent host context are **NOT AVAILABLE** in this dataset. They are not invented from identifiers or text templates. Source/action fields are synthetic evidence-derived categories, not measured sensor reliability.

## Models, imbalance and optimization

Most Frequent predicts the training majority; its full probability vector is the training class distribution. Markov uses first-order transition counts with one unit of training-prior smoothing. Random Forest and HistGradientBoosting use sklearn DictVectorizer fit on training only. The non-neural sequence model reuses variable-order transition suffix counts (3 -> 2 -> 1 -> training prior).

Predeclared RF grid: depths 6/12, class_weight None/balanced, 80 trees, minimum leaf 2, seed 20261003, one job. Boosting grid: leaves 7/15, class_weight None/balanced, 80 iterations, learning rate .1, L2 1, no internal early stopping, same seed. There is no oversampling of any partition. Balanced weights are computed from training only. Validation Top-1 selects models, macro F1 breaks ties, grid order breaks remaining ties. Both selected models use class_weight=None.

The proposed ensemble searches quarter-step weights over Markov, RF, boosting and sequence models, requiring at least two nonzero components. Weights selected on the 100 selection sequences: `{"Markov": 0.5, "Random Forest": 0.25, "Gradient Boosting": 0.25, "Sequence model": 0.0}`. No component is selected based on test accuracy. Calibration temperature grid: .5/.75/1/1.25/1.5/2, selected by log loss on the separate 50 calibration sequences. Selected temperature: **1.0**.

Model SHA-256: `32a942498ddbad5363d830488b13b54ada9d072e0e4f487f6d09caf9e265f18c`. Version: `chronological-synthetic-v2`.
Software: `{"python": "3.14.4", "sklearn": "1.9.1", "numpy": "2.5.3", "joblib": "1.6.0"}`.
All search trials, selected hyperparameters, artifact hashes, class distributions and model metadata are in the [report](../data/model_evaluations/chronological_prediction_v2/report.json) and [frozen configuration](../data/model_evaluations/chronological_prediction_v2/frozen_config.json).

## Original and partition class distributions

Counts below are the selected next-event labels, not oversampled training counts. The event count is reported separately above.

| Technique | All samples | Training | Validation | Test |
| --- | --- | --- | --- | --- |
| T1003.001 | 55 | 40 | 11 | 4 |
| T1016.001 | 47 | 38 | 4 | 5 |
| T1021.002 | 148 | 106 | 22 | 20 |
| T1027 | 32 | 22 | 5 | 5 |
| T1041 | 82 | 63 | 10 | 9 |
| T1053.005 | 21 | 12 | 2 | 7 |
| T1057 | 28 | 18 | 6 | 4 |
| T1059.001 | 36 | 20 | 9 | 7 |
| T1059.003 | 29 | 24 | 0 | 5 |
| T1071.001 | 161 | 114 | 22 | 25 |
| T1083 | 45 | 33 | 7 | 5 |
| T1087.001 | 43 | 24 | 6 | 13 |
| T1105 | 72 | 49 | 13 | 10 |
| T1204.002 | 26 | 16 | 3 | 7 |
| T1486 | 80 | 63 | 10 | 7 |
| T1547.001 | 15 | 9 | 4 | 2 |
| T1555.003 | 40 | 25 | 7 | 8 |
| T1566.001 | 19 | 11 | 4 | 4 |
| T1685 | 21 | 13 | 5 | 3 |

## Results and baseline comparison

| Model | Top-1 | Top-3 | Precision (macro) | Recall (macro) | Macro F1 | Coverage | Abstention | Covered accuracy | Brier | ECE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Most frequent | 0.166667 | 0.360000 | 0.008772 | 0.052632 | 0.015038 | 0.000000 | 1.000000 | NOT MEASURED | 0.929815 | 0.003810 |
| Markov | 0.386667 | 0.633333 | 0.252913 | 0.214416 | 0.198682 | 0.293333 | 0.706667 | 0.750000 | 0.725762 | 0.065833 |
| Random Forest | 0.326667 | 0.606667 | 0.243512 | 0.197473 | 0.187474 | 0.053333 | 0.946667 | 0.875000 | 0.799090 | 0.092889 |
| Gradient Boosting | 0.260000 | 0.546667 | 0.183375 | 0.167543 | 0.169664 | 0.380000 | 0.620000 | 0.526316 | 0.849016 | 0.220252 |
| Sequence model | 0.280000 | 0.500000 | 0.283727 | 0.190318 | 0.195602 | 0.573333 | 0.426667 | 0.430233 | 0.990657 | 0.332601 |
| FAPT-Guard | 0.326667 | 0.600000 | 0.224206 | 0.190995 | 0.180459 | 0.193333 | 0.806667 | 0.793103 | 0.747177 | 0.127372 |

FAPT-Guard did not outperform Markov and tied RF on Top-1. Its 95% Wilson interval for Top-1 is **25.68%?40.52%**. This interval treats one sample per sequence as a unit; shared synthetic generator dependence and prior test exposure limit its interpretation. It is not an interval for operational attack accuracy.

## Abstention and calibration

Unchanged configured gate: probability >= .5 and normalized Shannon entropy <= .6. Invalid/missing sequences, unavailable artifacts, insufficient history and unsupported prefix techniques abstain. Abstained technique/probability are null and a reason is returned. Top-k remains model output, not an accepted response.

All 150 test samples are scored before abstention; **29/150** pass the gate and **23/29** covered predictions are correct (**79.3103%**). Reporting only covered accuracy would hide errors and is not done. Coverage is **19.3333%**, abstention **80.6667%**. Operational risk/policy thresholds were not changed.

Temperature selection chose 1.0, leaving probabilities unchanged. Proposed multiclass Brier: **0.747177**; ten-bin ECE: **0.127372**. These measurements do not establish good calibration on observed telemetry. Reliability bins, raw before-calibration metrics and confusion matrices for every model are in the report.

## Per-technique results and confusion matrix

| Technique | Precision | Recall | F1 | Test support |
| --- | --- | --- | --- | --- |
| T1003.001 | 0.000000 | 0.000000 | 0.000000 | 4.0 |
| T1016.001 | 0.333333 | 0.200000 | 0.250000 | 5.0 |
| T1021.002 | 0.866667 | 0.650000 | 0.742857 | 20.0 |
| T1027 | 0.000000 | 0.000000 | 0.000000 | 5.0 |
| T1041 | 0.000000 | 0.000000 | 0.000000 | 9.0 |
| T1053.005 | 0.000000 | 0.000000 | 0.000000 | 7.0 |
| T1057 | 0.000000 | 0.000000 | 0.000000 | 4.0 |
| T1059.001 | 0.400000 | 0.285714 | 0.333333 | 7.0 |
| T1059.003 | 0.000000 | 0.000000 | 0.000000 | 5.0 |
| T1071.001 | 0.274194 | 0.680000 | 0.390805 | 25.0 |
| T1083 | 0.285714 | 0.400000 | 0.333333 | 5.0 |
| T1087.001 | 0.500000 | 0.384615 | 0.434783 | 13.0 |
| T1105 | 0.500000 | 0.600000 | 0.545455 | 10.0 |
| T1204.002 | 1.000000 | 0.142857 | 0.250000 | 7.0 |
| T1486 | 0.100000 | 0.285714 | 0.148148 | 7.0 |
| T1547.001 | 0.000000 | 0.000000 | 0.000000 | 2.0 |
| T1555.003 | 0.000000 | 0.000000 | 0.000000 | 8.0 |
| T1566.001 | 0.000000 | 0.000000 | 0.000000 | 4.0 |
| T1685 | 0.000000 | 0.000000 | 0.000000 | 3.0 |

The [complete confusion matrix](prediction-confusion-matrix.csv) uses actual labels as rows and predicted labels as columns. It includes all 150 test cases before abstention.

## Robustness and limitations

- Temporal split and unseen complete sequence paths are checked automatically. This does not test new attack families, unseen hosts or an independent telemetry domain.
- Leave-one-attack-family-out evaluation: **NOT AVAILABLE**. V2 has no independently defined family annotations. IDs and transition walks cannot be relabelled as independent attack families.
- Predeclared context-removal sensitivity: the frozen model receives features without source/action counts or intervals, with no retraining/tuning. Top-1 is **36.0000%**. This is a sensitivity check, not a new holdout, an optimized model or proof of a causal feature effect.
- Random restarts, repeated techniques and branching transitions limit how predictable the generator is from a short prefix. No theoretical accuracy ceiling has been measured.
- Only 700 training samples, 19 imbalanced classes and 50 calibration samples are available in this protocol. Minority-class scores and calibration are unstable. More observed sequences and meaningful context are needed; raising scores by changing data/thresholds is not justified.
- GRU/LSTM: NOT MEASURED; dependencies absent. The non-neural sequence model is measured above.
- The 90% objective is not met, even on this synthetic dataset. No new test set was manufactured or substituted to improve the result.

## API, frontend and defense integration

`GET /api/research/prediction-benchmark` returns verified dataset/model hashes, manifest, search protocol, per-class/confusion results and comparison. `GET /api/research/prediction-benchmark/examples/{scenario_id}` runs actual research inference for a frozen test prefix, separately returning its hindsight synthetic annotation. Neither endpoint activates a model or executes a response.

The existing defense prediction endpoint already carries probability, entropy, model/dataset provenance, cutoff, supporting IDs and calibration status. Its observed-data gate remains in force: **this synthetic model cannot qualify as a validated operational predictor**. Safe replay therefore continues to return ABSTAINED for operational inference. The research panel shows actual offline metrics; the defense panel shows current candidate, prediction state, model provenance/top-k, evidence and audit status. A generated annotation is never displayed as validated ground truth.

Risk is the existing configured prioritisation estimate, not measured attack likelihood. Evidence SHA-256 preservation, integrity verification, policy levels and audit chain are unchanged. Responses stay DRY_RUN; no host containment is enabled.

## Reproduction

From the project directory (PowerShell):

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.prediction_benchmark
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m compileall -q app tests scripts
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In another terminal:

```powershell
cd backend
..\.venv\Scripts\python.exe scripts/verify_prediction_demo.py
```

The safe demo appends two inert JSON replay events and one quarantined invalid event, independently recomputes raw-event and evidence-seal hashes, checks candidate mapping, abstention, unchanged risk/decisions, incident chain and audit, then verifies the fixed research example. No telemetry string is executed as a command. Repeating it creates a new isolated synthetic host/run ID.

Frontend:

```powershell
cd frontend
npm run lint
npm run build
npm run start -- --port 3000
# Separate terminal in frontend:
npx playwright test
```

Open http://localhost:3000/research. API base remains http://127.0.0.1:8001. Hash-bearing artifacts are under `data/model_evaluations/chronological_prediction_v2/`; joblib binaries stay ignored by git and can be regenerated. No commit or push is performed.

## Validation status

Verified on 2026-10-08:

- Backend: `python -m pytest tests -q` ? **76 passed, 28 subtests passed**, 249.62 seconds. One existing Starlette/httpx deprecation warning.
- Python compilation: passed for app, tests and scripts.
- Frontend lint: passed. Production build: passed; all existing routes retained.
- Playwright: **20 passed**, 2.8 minutes, including existing preservation/simulation workflows, current defense data, offline benchmark values, fixed research example and failure feedback. The performance panel screenshot was inspected.
- Reproduction: an independent retraining in `.publish/prediction-validation/reproduction/` exactly matched the model hash, sample hash, frozen configuration, test prediction hash and all reported metrics.
- API: all eleven requested defense GET endpoints returned HTTP 200; benchmark and fixed example also returned HTTP 200. Both localhost and 127.0.0.1 frontend research URLs returned HTTP 200.
- Safe demo run `f108829f`: LSASS event `EVT-5E6121C2CDA6DE6AF746BDED`, evidence `EVD-9DF4F91B6F804218`; shadow-copy event `EVT-E03B30A7D7E28E9EF924B20E`, evidence `EVD-FC145B923B5341BD`. Both raw-event hashes and evidence record seals were independently recomputed and verified.
- Defense predictions correctly ABSTAINED. LSASS risk remained 0.225 / LOW / MONITOR; shadow-copy risk remained 0.25 / MEDIUM / ALERT + PRESERVE_EVIDENCE, with an incident and complete chain created. No response or containment was executed.
- Audit verification: **33 records, verified=true, failures=[]**. This is the existing local chain; no external anchor authenticates tail truncation or full replacement.
- Fixed research example `SYN2-00851`: real model top probability 0.4345160713; normalized entropy 0.6657281177; ABSTAINED with null accepted technique/probability. The API preserves model top-k for inspection. Hindsight annotation is separately identified as synthetic.
- Initial sandbox runs blocked temporary-file access, Node child workers and existing sklearn worker pipes. Those commands were rerun outside the sandbox. The backend's worker-pipe restriction caused initial browser HTTP 500s; no model or defense logic workaround was applied. Final browser suite passed; final backend log inspection showed no application errors or HTTP 500s. One earlier connection-reset callback occurred during interrupted browser navigation.
- Existing tracked screenshots and `data/benchmark_report.json` overwritten by tests were restored to their pre-task contents (saved screenshot bytes and the originally clean tracked benchmark report); newly generated outputs remain under ignored `.publish/prediction-validation/generated/`.
- `git diff --check` and `git status` were run. No commit, push, reset, clean, dataset deletion, or real containment.

### Files for this upgrade

Added: `backend/app/prediction_benchmark.py`, `backend/tests/test_prediction_benchmark.py`, `backend/scripts/verify_prediction_demo.py`, `frontend/src/components/prediction-benchmark.tsx`, `frontend/tests/prediction-benchmark.spec.ts`, this report, `docs/prediction-benchmark.md`, `docs/prediction-confusion-matrix.csv`, and generated benchmark artifacts under `data/model_evaluations/chronological_prediction_v2/`. Initial evaluation artifacts are preserved under `data/model_evaluations/chronological_prediction/`.

Updated: `backend/app/api/research.py`, `frontend/src/app/research/page.tsx`, and the existing in-progress `frontend/src/components/defense-dashboard.tsx` to expose prediction provenance/top-k. Other pre-existing uncommitted changes were preserved.

