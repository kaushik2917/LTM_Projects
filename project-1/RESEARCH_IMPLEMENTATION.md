# Incremental research-validity implementation

## Inspection and plan

Existing architecture: Next.js 16 frontend, FastAPI backend, SQLite event and
workflow storage, local CSV/STIX files, scikit-learn/joblib models. Preserve it.

Present: four custom CSVs (7,700 / 5,000 / 8,000 / 1,890 rows), ATT&CK 19.2,
five trained forest baselines, holdout report, scenario audit, six fixture events.
Absent: raw OpTC telemetry, trained TC-FAPN, observed future-technique labels,
live acquisition, measured conformal coverage. An empty `.part` is not telemetry.

Hardcoded: dashboard future techniques/probabilities, uncertainty, utility,
retention, graph summary and response rankings. Computed: baseline predictions,
weighted ELC/ERS, response objective, dataset and snapshot hashes. Existing
training splits group incident IDs but do not assess scenario generalization.
Existing audit records are not hash chained. The old optimizer YAML belongs to
the preliminary package and differs from the formula in the running backend.

Implementation order:
1. Add canonical metadata/configuration and dataset validation.
2. Preserve historical scores; train reproducible baselines and inspect AFIP and
   poisoning with detailed metrics, duplicate checks and scenario holdouts.
3. Derive evidence-quality features and explicit mapping states. Predict next
   stages from the actual synthetic stage labels; do not invent technique labels.
4. Add temporal analysis, persisted predictions, custody chaining and preservation
   verification; extend existing APIs/reports.
5. Execute deterministic fixture corruption scenarios, label unmeasurable metrics
   explicitly, and retain results/provenance.
6. Bind existing UI cards to these outputs; add details and temporal controls.
7. Test temporal causality, probability normalization, hashes, leakage checks,
   benchmarks, API workflows and browser interactions; run the complete app.

## Implemented result

The existing routes and dark dashboard theme remain. Dashboard prediction,
uncertainty, evidence utility, graph and response cards now consume analysis
outputs; unavailable measurements are explicit. Predictions expose actual input
evidence IDs, observed features, model version and dataset hash. Graph cutoff
controls recompute state and prediction from the selected evidence prefix.
Evidence inspection exposes mapping status, quality factors and calculation
methods. Research screens show dataset provenance, model metrics, confusion
matrices, leakage checks, scenario diagnostics and executable benchmark results.

Key implementation files:
- `backend/config/research.json`: canonical dataset names and objective weights.
- `backend/app/training.py`: reproducible six-model training and diagnostics.
- `backend/app/services/metadata_service.py` and `validation_service.py`: hashes,
  model/data provenance, split checks and validation artifacts.
- `backend/app/services/analysis_service.py`: prefix-only stage inference,
  explicit mapping states and explainable evidence quality.
- `backend/app/services/workflow_service.py`: temporal graph, persisted
  predictions, preservation verification, linked custody and report export.
- `backend/app/services/benchmark_service.py`: deterministic fixture replay.
- `backend/app/services/research_service.py`: exposed objective contributions.
- `backend/app/api/research.py` and `workflow.py`: additional analysis,
  evaluation, import, benchmark, verification and export endpoints.
- `frontend/src/components/research-analysis.tsx`, `evaluation-panel.tsx`,
  `incident-console.tsx`, and `frontend/src/app/page.tsx`: integrated UI.
- `backend/tests/test_validity.py` and
  `frontend/tests/research-validity.spec.ts`: scientific-validity regression tests.

## Data and measured model results

Datasets 10/11/12 contain 7,700/5,000/8,000 rows. Dataset 13 contains 1,890
evaluation-only descriptors; none are training features. The local ATT&CK 19.2
catalog has 697 active techniques. Raw OpTC event count remains zero.

Original five baselines retain grouped 80/20 splits (seed 42). The new stage
classifier uses grouped 60/20/20 splits and only previous stage, current stage
and current technique as inputs. Artifact hashes, timestamps, features, targets,
parameters, distributions, per-class metrics and group-overlap checks are stored
under `data/models/`. Historical scores are retained separately.

| Model | Held-out result |
|---|---|
| CDFU | MAE 0.02255; RMSE 0.02837; R² 0.91085 |
| ACES | MAE 0.01281; RMSE 0.01840; R² 0.96499 |
| AFIP | Accuracy 0.613; macro F1 0.08806 |
| Trust | MAE 0.00488; RMSE 0.00660; R² 0.99479 |
| Poisoning | Accuracy and macro F1 1.0 on original synthetic holdout |
| Next stage | Accuracy and macro F1 1.0 on synthetic labels |

AFIP predicts `none` for 987 of 1,000 held-out rows: its headline accuracy
conceals poor minority-class performance. Poisoning's perfect original score
is consistent with generated proxy labels and explicit corruption flags, not
proof of real tampering detection. Reduced-feature, attack-scenario holdouts
produce macro F1 approximately 0.469–0.982. The new progression labels follow
a deterministic current-stage transition rule in this dataset; its perfect
score measures recovery of that synthetic rule, not real attack forecasting.
No train/test incident overlap or complete-record duplication was found.
Generated-template leakage remains a limitation. T1070.001 values absent from
the active local catalog are flagged instead of silently relabeled.

## Evidence, objective and benchmark interpretation

Evidence trust and forensic utility in the incident UI are disclosed heuristics
computed from available observations. Missing independent sensor observations
remain null. Poisoning risk is an anomaly fraction; calibrated poisoning
probability remains null where required sensor features do not exist.
Next-technique prediction is unavailable because no observed target labels exist.

The running balanced objective is 0.40 residual risk + 0.30 normalized ELC +
0.15 business impact + 0.10 cost + 0.05 opportunity loss. Each contribution is
returned. ELC is utility-weighted predicted evidence loss; uncertainty is model
context, not an undisclosed extra objective term. ACES survival is predicted,
not observed post-response survival.

The benchmark selects the first descriptor for each of 14 named scenarios.
Twelve deterministic corruption scenarios execute on the six-event fixture;
concept drift and unseen techniques remain unmeasured. Results measure actual
fixture retention, anomaly counts, utility retention, entropy and distribution
changes. Expected CSV scores are not reused as measurements. Accuracy, true
trust/utility error, post-response survival and conformal coverage remain null.
Each run has an immutable JSON artifact and dataset/model/fixture provenance.

New custody entries use canonical SHA-256 hashes linked to the preceding
record. Existing legacy entries are explicitly unsealed. Snapshot bytes are
verified before simulated response; exports and verification are audited.
There is no external trusted anchor: tail truncation or full database replacement
cannot be ruled out by the local chain alone. All responses remain simulations.

## Verification and operation

Verified: 14 backend tests, five Edge/Playwright browser tests, ESLint and the
Next.js production build. Browser checks cover all seven routes, prediction
explanations, temporal exclusion of future evidence, quality inspection,
benchmark execution, preservation, response assessment and report download.

From `backend/`:
```powershell
..\fapt_guard\.venv\Scripts\python.exe -m app.datasets train
..\fapt_guard\.venv\Scripts\python.exe -m app.datasets evaluate
..\fapt_guard\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\fapt_guard\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From `frontend/`, in a separate terminal:
```powershell
node node_modules/next/dist/bin/next build
node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3000
```
With both servers running, browser tests use
`node node_modules/@playwright/test/cli.js test` from `frontend/`.

Remaining research dependencies: raw OpTC telemetry and ground-truth alignment,
real temporal next-technique labels, trained TC-FAPN architecture, calibrated
uncertainty, validated tampering detectors, causal response effects and live
post-response outcomes. This implementation does not claim those are complete.
