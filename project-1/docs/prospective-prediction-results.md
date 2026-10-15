# PROSPECTIVE-V1: final frozen synthetic evaluation

## Status

90% Top-1 target: **NOT ACHIEVED**. FAPT-Guard: **38.00% (114/300)**. Conformal target 90%: **NOT ACHIEVED**, actual **82.00% (246/300)**, average set **5.913333 classes**.

This is a new prospective synthetic experiment. It does not replace or retrospectively repair the historical 32.6667%/43.3333% experiments. See [historical validity audit](temporal-research-validity.md). No real-world accuracy or prevention success is claimed.

## A. Historical discrepancy

32.6667% was a chronological midpoint ensemble evaluation; 43.3333% was a random-group transition-frequency evaluation using many more training prefixes. Same source data, different model/split/cutoffs. Only 16 test scenarios overlap; 113 chronological test scenarios were historical training scenarios. INC-00001's63.7263% is a calibrated class probability from a raw one-match transition estimate, not accuracy. All historical values remain unchanged and separately labelled.

## B. Frozen model and dataset

Selected: **FAPT-Guard temporal ensemble**, weights `{"Markov": 0.5, "Random Forest": 0.25, "Gradient Boosting": 0.25, "Sequence model": 0.0}`. Temperature **1.25**. This result was selected using validation only, including alternatives with single-model selection and smoothed orders1/2/3/5 with strengths1/5/20. The smoothed candidates were not selected. Candidate scores and exact hyperparameters are retained in `frozen.json`.

Model SHA-256: `9f64fc0513453676e1c1223bdd43a1bf177d5ce148ea630dfbb3e3b22a16899d`.
Frozen at: `2026-10-08T01:24:22.252165+00:00`.
Frozen manifest SHA-256: `687d58a65ea8fe0e1f3e8ca0cb71a17e6fe062e12c8f5296032702cac94977c5`.
Feature version: `future_prediction_v3`.

Development source: existing synthetic v2.0.0 SHA-256 `8433855364724c70b147ee480e0e2eb739aa7ae26d3e590657754bb22aab7a6e`. Partitions:700 training, 100 validation, 25 probability calibration, 25 conformal calibration, each one midpoint sample per sequence. Historical latest 150 test scenarios excluded from these roles. Development cohorts were exposed in historical experiments; no retroactive independence claim.

Prospective test: **300 new sequences, 2724 events, 300 samples, 19 supported classes**. Dataset version `prospective-v1`, SHA-256 `dfbd801b75707c9f35ab5ed15262a70199f39a7221071600c9d2da4335f89527`. Seed was drawn once after freeze and persisted in `evaluation_started.json`; no seed search. Generator parameters/source were frozen before test generation. All six models receive identical test samples. Existing source files and historical test sets remain unchanged.

## C. Validation results (not test accuracy)

| Model | Validation Top-1 | Validation Top-3 | Validation macro F1 |
| --- | --- | --- | --- |
| Most frequent | 0.130000 | 0.350000 | 0.012110 |
| Markov | 0.410000 | 0.670000 | 0.218774 |
| Random Forest | 0.380000 | 0.640000 | 0.196334 |
| Gradient Boosting | 0.340000 | 0.570000 | 0.223234 |
| Sequence model | 0.300000 | 0.540000 | 0.165778 |
| FAPT-Guard | 0.460000 | 0.670000 | 0.293937 |

Selection maximized validation Top-1, then macro F1. Extra whitelist features cover suffixes through5, trigrams, tactic history, event density and temporal decay. Existing RF/boosting class-weight and hyperparameter grids were fitted on training only. No result below fed back into selection.

## D/E. Frozen test and baseline comparison

Fractions use0?1. Precision/recall/F1 are macro unless specified; all classification scores include all 300 eligible samples before abstention. Coverage is the accepted prediction fraction; conformal coverage is true-label inclusion in the set.

| Model | top_1_accuracy | top_3_accuracy | macro_precision | macro_recall | macro_f1 | weighted_f1 | multiclass_brier_score | expected_calibration_error | coverage | abstention_rate | conformal_coverage | average_prediction_set_size |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Most frequent | 0.123333 | 0.333333 | 0.006491 | 0.052632 | 0.011557 | 0.027082 | 0.924274 | 0.004545 | 0.000000 | 1.000000 | 0.950000 | 16.000000 |
| Markov | 0.376667 | 0.693333 | 0.280566 | 0.269585 | 0.259630 | 0.339602 | 0.741581 | 0.087382 | 0.096667 | 0.903333 | 0.816667 | 4.890000 |
| Random Forest | 0.356667 | 0.606667 | 0.290970 | 0.248826 | 0.252522 | 0.328846 | 0.820618 | 0.156039 | 0.003333 | 0.996667 | 0.860000 | 8.660000 |
| Gradient Boosting | 0.293333 | 0.593333 | 0.230888 | 0.218151 | 0.219611 | 0.301788 | 0.852222 | 0.109287 | 0.000000 | 1.000000 | 0.973333 | 15.166667 |
| Sequence model | 0.313333 | 0.533333 | 0.213941 | 0.216811 | 0.210574 | 0.304107 | 1.012951 | 0.256813 | 0.413333 | 0.586667 | 0.883333 | 14.333333 |
| FAPT-Guard | 0.380000 | 0.663333 | 0.279220 | 0.278284 | 0.268972 | 0.362741 | 0.756001 | 0.082479 | 0.050000 | 0.950000 | 0.820000 | 5.913333 |

FAPT-Guard exceeded Markov by **one correct prediction**, 0.3333 percentage points. It lost to Markov on Top-3 and Brier. Paired discordant results: FAPT-only correct=18, Markov-only correct=17; exact two-sided binomial/McNemar p=1.000000. This does not establish a statistically reliable advantage or general superiority. This post-evaluation comparison is descriptive, not a selection criterion.

FAPT Top-1 Wilson95% interval: **32.6919%?43.6116%**. Every model's interval is retained in the report. One sample per sequence reduces within-sequence correlation, but generator dependence and deduplication limit interpretation.

[Per-class precision/recall/F1 and support for all models](prospective-per-class.csv); [all confusion matrices and intervals](prospective-confusion-matrices.json). Machine-readable report: `data/model_evaluations/prospective_temporal_v1/report.json`.

## F. Calibration

| Model | Temperature | Raw Brier | Calibrated Brier | Raw ECE | Calibrated ECE | LAC threshold |
| --- | --- | --- | --- | --- | --- | --- |
| Most frequent | 1.5 | 0.923777 | 0.924274 | 0.039524 | 0.004545 | 0.972066062 |
| Markov | 1.5 | 0.720915 | 0.741581 | 0.085025 | 0.087382 | 0.942978962 |
| Random Forest | 1.25 | 0.797554 | 0.820618 | 0.103492 | 0.156039 | 0.960682317 |
| Gradient Boosting | 3.0 | 0.922388 | 0.852222 | 0.275066 | 0.109287 | 0.975076288 |
| Sequence model | 4.0 | 1.008319 | 1.012951 | 0.310300 | 0.256813 | 0.999559687 |
| FAPT-Guard | 1.25 | 0.744244 | 0.756001 | 0.068418 | 0.082479 | 0.958729507 |

All temperatures were selected by log loss using only 25 probability-calibration sequences, after model selection. Test ECE and Brier were calculated after freeze, including before/after values. These diagnostics may worsen for a model; calibration was not selected by test improvement. Small calibration sample size and distribution differences constrain reliability.

## G. Conformal coverage, set size and abstention

Fixed LAC nonconformity1-p(true); quantile rank ceil((25+1)*.9)=24, fitted on the **other 25** calibration sequences. No test-derived threshold, top-k cap, method search or set-size optimization was performed.

FAPT actual conformal coverage **82%**, average set **5.913333**, minimum **2**, maximum **14**. The historical random experiment's11.4067 mean set and89.3333% coverage used different samples/model/calibration counts; these values are not a controlled before/after comparison. New sets are smaller but do **not** achieve90% coverage. Do not claim efficiency improved while maintaining target coverage. More independent calibration data and a separately preregistered future experiment are required; these test results must not be used to retune this experiment.

Abstention coverage **5% (15/300)**, abstention **95%**. Covered accuracy **86.6667% (13/15)**. This is not overall accuracy. Probability>=.5 and entropy<=.6 thresholds are unchanged. Operational telemetry still abstains without validated observed-data labels/models.

## H. Leakage and test-contamination checks

- Development roles use disjoint scenario/incident IDs and chronological ranges; no old test rows fit/select/calibrate.
- New test draw created after model and generator freeze, then evaluated once. Existing test sets not resampled or substituted.
- Exact full paths cannot repeat across historical/prospective data or within prospective test; IDs are new; timestamps strictly later than historical events.
- Prefix features whitelist only data available at cutoff; targets strictly later. IDs/absolute clocks/future fields are excluded.
- Temperature and conformal subgroups are separate. All model temperatures use the same probability subgroup; all sets use the same conformal subgroup.
- Exclusive evaluation marker rejects another scoring invocation. Frozen model, generator, development rows, implementation and final artifacts have hashes. Local locks are not tamper-proof external custody.
- Source generator uses documented synthetic transition assumptions, not independently observed labels. Temporal ordering, rejection sampling, historical exposure of development groups and small calibration cohorts limit coverage guarantees and external validity.
- INC-00001 remains separate, PENDING_GROUND_TRUTH, and absent from all benchmark test samples.

## I. Files changed for this validity task

Added:
- `backend/app/prospective_prediction.py`
- `backend/tests/test_prospective_prediction.py`
- `frontend/src/components/prospective-evaluation.tsx`
- `frontend/tests/prospective-validity.spec.ts`
- `docs/temporal-experiment-audit.json`
- `docs/temporal-research-validity.md`
- `docs/prospective-prediction-results.md` (this report)
- `docs/prospective-per-class.csv`
- `docs/prospective-confusion-matrices.json`
- `data/model_evaluations/prospective_temporal_v1/` artifacts (joblib ignored)

Updated:
- `backend/app/api/research.py`: GET `/api/research/prospective-prediction`
- `backend/app/services/research_service.py`: explicit advisory weight sum/unnormalized interpretation; unchanged ranking/formula
- `frontend/src/app/research/page.tsx`
- `frontend/src/components/temporal-demonstration.tsx`
- `frontend/src/components/prediction-benchmark.tsx`
- `frontend/src/components/future-evaluation.tsx`
- `frontend/src/components/research-analysis.tsx`
- `frontend/src/components/incident-console.tsx`
- `docs/prediction-benchmark.md` and `docs/prediction-accuracy-evaluation.md`: links identifying historical versus prospective results

Other pre-existing changes are preserved. No cosmetic redesign, real host response, commit or push.

## J. Reproduction commands and one-shot safeguard

From `backend`, the commands used were:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_prospective_prediction.py -q
..\.venv\Scripts\python.exe -m app.prospective_prediction prepare
..\.venv\Scripts\python.exe -m app.prospective_prediction evaluate
..\.venv\Scripts\python.exe -m app.prospective_prediction status
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m compileall -q app tests scripts
..\.venv\Scripts\python.exe scripts/verify_prediction_demo.py
```

`prepare` refuses an existing frozen experiment; `evaluate` refuses an existing evaluation marker. **Do not delete either to rerun or search for better scores.** Use `status` to verify hashes/read the saved report. To reproduce the exact generated data without another model evaluation, load `generator.json` and call `generate_test(spec, recorded_seed)` from `evaluation_started.json`; compare canonical content with `test_dataset.json`. Independent new research requires its own preregistered protocol, not rewriting these results.

Frontend checks from `frontend`:

```powershell
npm run lint
npm run build
npx playwright test
```

Start API with `..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001`; frontend with `npm run start -- --port 3000`. Open `/research`. If Windows sandbox blocks worker pipes or child processes, run the same command with the appropriate permission rather than changing model outputs.

## Validation

Backend: 82 tests and 28 subtests passed (295.05 seconds), with one existing Starlette/httpx warning. Lint, build and compilation passed. Safe replay `4b6e8dd1` verified both evidence hashes/seals and the 38-record audit chain; DRY_RUN retained and both operational predictions ABSTAINED. Final browser suite: **21 passed (2.5 minutes)**, including historical provenance, prospective metrics and pending incident truth. An earlier graph test timed out at five seconds during training; the complete suite passed after fitting finished without weakening that assertion. The rendered prospective panel was visually inspected. The recorded seed regenerated identical test data; all hashes, freeze/generation order, new IDs, chronological boundaries and shared sample counts verified. A second evaluation invocation was rejected before generation/inference. The prospective API returned HTTP 200 and exactly matched the stored report. Final backend logs showed no application errors or HTTP 500s. `git diff --check` passed and `git status` was inspected. Existing screenshots and the unrelated benchmark report changed by tests were restored byte-for-byte from saved pre-test copies. No commit, push, dataset deletion or host action was performed.
