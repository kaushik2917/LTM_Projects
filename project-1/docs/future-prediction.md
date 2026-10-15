# Future attack prediction: implementation and research report

**Historical report, October 2, 2026.** The subsequently supplied synthetic temporal dataset now enables a separately labelled research model for simulated incidents. See the [October 3 integration report](synthetic-temporal-integration.md). Observed-data validation remains unavailable; the unavailable synthetic demonstration state described below has been superseded.

Project: **FAPT-Guard — An Intelligent Framework for Prediction and Avoidance of Cyberattack with Digital Evidence Analysis**.

## Outcome

Genuine future ATT&CK technique prediction is **NOT AVAILABLE with the supplied data**. This includes `INC-00001`. No observed-data model, probability, accuracy, uncertainty or coverage has been invented.

The project now has a temporal dataset contract, sample builder, grouped training/evaluation pipeline, qualification gates, timestamp-based inference API, persisted prediction attempts, separate synthetic demonstration, research evaluation panel and forensic report section. Tests exercise the train/inference machinery using explicitly synthetic temporary fixtures. Those tests do not constitute observed-data validation.

Next.js/React, FastAPI, scikit-learn, joblib, SQLite JSON audit storage, existing navigation/routes, dark styles and safe simulation remain in place. No replacement architecture or production rebuild was introduced. The original incident, host, user and six evidence observations remain intact.

## 1. Original prediction investigation

The existing path is `workflow_service.analysis` → `analysis_service.prediction` → `research_service.model('progression')` → `progression.joblib`.

It selects the last two mapped observations, supplies `observed_prev_stage`, `observed_current_stage`, and `current_technique_id`, and calls RandomForest `predict_proba`. Normalized predictive entropy is computed from the full class distribution. These values were model outputs, not hardcoded dashboard constants.

The target is dataset 11's **synthetic `predicted_next_stage`**. It is not a later observed event or an ATT&CK technique. The dashboard previously showed these outputs within its future-prediction card and even added a synthetic stage to the chronology. The chronology now contains only observed evidence; synthetic results are in a separate, explicitly labelled expandable section.

Searches covered the active frontend/backend, data and metadata, and the preliminary `fapt_guard` package for prediction/uncertainty paths, the requested technique IDs and numeric constants. `53.8`, `26.3`, `11.3`, and `50.1` do not occur as active source-code prediction constants. Numeric matches in tables or stored results are data, not replacement forecasts. The old `fapt_guard` package has expert configuration and schema defaults, but it is not imported by the running API. The prevention uncertainty slider is still an explicitly labelled analyst assumption.

## 2. Available datasets

Complete schemas, hashes, identifier counts, duplicate checks and readiness findings are saved in `data/models/prediction_readiness.json` and shown on Research.

| Dataset | Rows | Identifiers | Temporal/future-label finding |
|---|---:|---|---|
| 10: FAPT-Guard Cyber-Forensic Response | 7,700 | 700 incidents, 80 hosts, 13 current techniques | Each incident has one timestamp/current technique repeated across 11 response alternatives. These are not 11 future events. |
| 11: FAPT Anti-Forensic | 5,000 | 5,000 sequence row IDs, 13 current techniques | All labels declare `synthetic_rule_based`. No timestamps, event IDs, hosts/users or actual future-event sequence. |
| 12: FAPT Evidence Trust & Poisoning | 8,000 | 8,000 evidence IDs, 700 incidents, 10 scenarios/sensors, 13 techniques | Quality/corruption rows lack event timestamps, process/network chronology and observed future outcomes. Row order cannot supply time. |
| 13: FAPT-Bench 2.0 | 1,890 | 1,890 benchmark IDs, 14 scenario families, 5 source descriptors | Synthetic expected scores and benchmark conditions, not measured future events. “OpTC-compatible” is not imported OpTC. |
| ATT&CK | Pinned 19.2 STIX | Active technique vocabulary | Supplies names and tactics, not observed attack sequences or prediction targets. |
| OpTC | 0 imported events at inspection | No source trace/ground-truth sequences supplied | Remains NOT IMPORTED. The existing importer and graph are preserved. |

Datasets 10/11/12 have no supplied version number: **NOT AVAILABLE**, not an invented version. Dataset 13 declares version 2.0. Dataset 10 has timezone-unspecified timestamps; 11/12/13 lack event timestamps. Dataset 12's `timestamp_shift_seconds` is a corruption descriptor, not an event time. Source/generation provenance for 10/12 remains undocumented beyond user-supplied research tables.

SHA-256 hashes:

| Dataset | SHA-256 |
|---|---|
| 10 | `60c1bc983c16ff35c644b525b14298c40b129a6aa92c542a8d1cb0495eeb6462` |
| 11 | `f9851b4cc3e98ffdd46da6a4e88cadea9437a2c316561df88ce4e5ab0edb241c` |
| 12 | `0ed157d55a32bccfbf72ce287f00dfdb0b7c703a71fd4045e3dcf123954b3e32` |
| 13 | `64664b417d796723c123b57156bb67095264143bb21034a49f79eb7ea2a32773` |

## 3. Temporal pipeline and target

Given all evidence **observed and available at T**, predict the next independently labelled observed event with **event timestamp strictly greater than T**. Technique and stage are separate tasks. Unlabelled future events are skipped, so the precise horizon is *next independently labelled observed event*, not necessarily the next raw telemetry event. There is no claimed fixed minute/hour horizon.

`temporal_prediction.prefix` sorts by timestamp and uses both `timestamp <= T` and `observed_at <= T`. An annotation enters features only when `label_known_at <= T`. Retrospective annotations may provide training targets, but cannot leak into earlier inputs. Simultaneous conflicting future labels are rejected rather than arbitrarily ordered. All boundary-time evidence is included together by the legacy count slider.

Real sequence timestamps must include a timezone. The unchanged six-event fixture has timezone-unspecified timestamps: cutoffs use that same fixture clock, with no invented UTC conversion. Mixed clocks are rejected. `2026-09-25T10:04:00` selects EV-00001 through EV-00004 and excludes EV-00005/06. The graph slider now sends this timestamp to the API.

Feature version: `future_prediction_v1`.

Whitelist: event count, distinct host/entity counts, elapsed time, time since last observed event, source/action/entity-type counts, and current/previous/aggregate known technique and stage annotations. Supporting evidence IDs are the exact prefix records used to build those features. IDs themselves, future outcomes, response outcomes, final incident labels and target columns are not features. Sensor trust, graph integrity and other unavailable measurements are not synthesized into this baseline.

### Sequence bundle contract

Supply a reviewed JSON bundle with `metadata` and `events`. No such observed bundle is included in this repository.

Required metadata: `dataset_name`, `version`, `source`, `ground_truth_reference`, `domain`, and `data_kind` (`observed` or `synthetic`). Unknown source provenance must be resolved before treating the data as observed validation.

Required event fields: `evidence_id`, `incident_id`, `scenario_id`, `collection_id`, `timestamp`, `observed_at`, `source`, `host`, `subject`, `object`, `action`, and Boolean `simulated` consistent with data kind. Labelled records add `technique_id` and/or `attack_stage`, `label_known_at`, `label_basis: independent_ground_truth`, and a nonempty `label_reference`. Technique IDs must exist in the pinned active ATT&CK catalog. Stage labels must be valid tactics. Behavior-rule hypotheses are not accepted as independent ground truth.

Provenance declarations are supplied by the dataset owner. Schema checks cannot authenticate those declarations; source and annotation review is still required.

### Training and qualification

- RandomForestClassifier + DictVectorizer; seed 42; 80 trees; max depth 12; minimum leaf samples 2; one worker. Other scikit-learn defaults apply. Exact feature columns, library version and hyperparameters are stored.
- Connect shared incident, scenario and collection identities into indivisible groups. Split approximately 60/20/20 using GroupShuffleSplit with fixed seeds 42 and 43. Actual sample counts depend on group sizes.
- Require at least five independent groups, two classes with at least two examples in each partition, and all evaluation labels in the trained label space. This is a technical minimum, not evidence that statistical support is sufficient for deployment.
- Reject duplicate event IDs/content, cross-partition duplicate feature/target samples, inconsistent incident grouping, invalid timestamps/labels, ambiguous future targets and explicit target/future fields.
- Report pairwise incident/scenario/collection overlap and sensor-source overlap. Shared sensor types do not imply independent source-domain validation; collection identities are held out.
- Fit the vectorizer and classifier only on training. Validation and holdout remain separate. Compare with a training-only most-frequent-label baseline on the same partitions.
- Calculate precision, recall, macro/weighted F1, per-class support, confusion matrix, Top-1/3/5 when class counts permit, MRR, multiclass Brier score, ECE and reliability bins. No calibration transformation is fitted. Conformal coverage remains null.
- Save validation/holdout error examples with incident, cutoff, prefix, target event/time, predicted label, probability and entropy. Empty categories are explained rather than invented.
- Save dataset/catalog hashes, dataset version, feature version, partition membership, fit/evaluation timestamps, hyperparameters, global impurity feature importance and artifact SHA-256 model version.
- Qualification verifies artifact/metadata agreement, hashes, feature/task versions, observed-data provenance, held-out evaluation and passed checks. Synthetic artifacts cannot activate genuine prediction. Synthetic training is allowed only with `--allow-synthetic` and an output directory separate from operational models.
- Inference also rejects synthetic incidents, mismatched source domains, and incidents/scenarios/collections used in model fitting. A model cannot forecast a training incident using its already learned future labels and call it unseen.

## 4. API, persistence and UI

Existing endpoint extended:

```http
POST /api/workflow/INC-00001/prediction
Content-Type: application/json

{"cutoff_timestamp":"2026-09-25T10:04:00","task":"technique"}
```

`task` may separately be `stage`. The selected incident is in the URL. For the supplied fixture this returns a real persisted unavailable result, with an empty probability list, null uncertainty, the exact reason and four supporting evidence IDs. HTTP 422 rejects malformed cutoffs; 404 rejects unknown incidents. No equivalent endpoint was duplicated.

Analysis/graph accept `cutoff_timestamp`; legacy `upto` remains for compatibility and cannot be combined with a timestamp. Analysis returns `future_prediction` and `synthetic_prediction`. The old `prediction` key is retained as an explicitly tagged synthetic compatibility alias.

Prediction attempts, including unavailable results, are recorded under `future_prediction` in the existing SQLite audit chain. Identical input/model/cutoff results reuse their stored ID. Output metadata, feature values, evidence IDs and cutoff remain inspectable. Existing `prediction` audit records are legacy synthetic-stage results and are not retroactively altered. Reports expose current future readiness plus stored prediction runs.

For reviewed nonfixture sequences, place the validated input bundle at `data/temporal_events.json`; the same prediction endpoint resolves its incident IDs. A trained matching-domain model and independent inference group are still required. This does not import fake OpTC data or convert the fixture into a real incident.

The Command Center and graph distinguish OBSERVED, PREDICTED, SYNTHETIC and NOT AVAILABLE. The synthetic section is collapsed by default. Clicking an available model result opens the existing detail panel containing the actual result and provenance. Research separates observed-data readiness from synthetic validation/holdout scores. No CSS, navigation or route redesign was needed.

## 5. Actual synthetic evaluation

The existing progression artifact was reevaluated using its reproducible stored split; it was not relabelled as a future-technique model or unnecessarily retrained.

| Property | Actual value |
|---|---|
| Model | RandomForestClassifier synthetic next-stage baseline |
| Training data | `11_fapt_anti_forensic.csv` |
| Dataset version | NOT AVAILABLE |
| Target | `predicted_next_stage`, synthetic rule label |
| Features | `observed_prev_stage`, `observed_current_stage`, `current_technique_id` |
| Feature version | Existing `research-v2` |
| TRAINING / VALIDATION / HOLDOUT | 3,000 / 1,000 / 1,000 synthetic rows |
| Split | Sequence row IDs; fixed GroupShuffleSplit seeds 42/43; not actual chronological campaigns |
| Model version | `801abb77371bb1d937b5e63972180f7abeac228b27616c60d8d0626300d6ff39` |
| Seed / principal parameters | 42; 80 trees; depth 12; minimum leaf samples 4; two workers |
| Fit timestamp | `2026-09-29T06:46:58.050830+00:00` (artifact metadata) |
| Holdout Top-1 / Top-3 / Top-5 | 1.0 / 1.0 / 1.0 |
| Holdout precision / recall / Macro-F1 / Weighted-F1 | 1.0 / 1.0 / 1.0 / 1.0 |
| Holdout MRR | 1.0 |
| Majority holdout accuracy | 0.172 |
| Holdout multiclass Brier / ECE | 0.0 / 0.0, synthetic labels only |
| Probability calibration | Diagnostics calculated; no calibrator fitted; fixture/real-world calibration NOT MEASURED |
| Uncertainty | Normalized predictive entropy over actual model probabilities |
| Conformal coverage | NOT MEASURED |

**These perfect scores do not validate forecasting.** There are 13 repeated feature/target patterns across training/validation, training/holdout and validation/holdout. Sequence-ID overlap is zero, but each ID identifies a row rather than an independent attack. Scenario overlap cannot be checked because scenario identities are missing. Temporal leakage cannot be assessed because timestamps are missing. Label-source overlap is `synthetic_rule_based`; target generation is deterministic from stage. Feature/target column-name overlap is empty, but this does not remove generator leakage. The UI and stored audit disclose these findings.

The genuine future-technique model, version, fit sizes, holdout metrics and calibration remain **NOT AVAILABLE / NOT MEASURED**. They are not assigned the synthetic scores above.

## 6. Prevention, AFIP, poisoning and FAPT-Bench

The existing prevention objective remains `0.40*risk + 0.30*normalized_loss + 0.15*business + 0.10*cost + 0.05*opportunity`. Uncertainty is a model input, not an additional objective term. The UI says “Calculated under simulation assumptions.” Future prediction status/probabilities are retained as advisory assessment context; the existing response model is not falsely claimed to have learned new future-probability features. With current data it explicitly uses current-state context. Preservation priority records the actual supplied volatility ordering; future-technique-to-artifact relevance stays unavailable because no validated relevance model exists.

AFIP retained holdout accuracy 0.613, Macro-F1 0.0880615, with 987/1,000 predictions `none`. It is weak on minority classes. Poisoning retains original accuracy/Macro-F1 1.0, but inputs expose corruption proxies; reduced-feature scenario holdouts have Macro-F1 approximately 0.4691–0.9824. Neither is raw telemetry or real-world validation.

FAPT-Bench still executes 12 supported corruption families from 14 descriptors on six fixture events; drift/unseen-technique cases remain unmeasured. It measures fixture retention/quality and synthetic-stage distribution change, not genuine future-technique accuracy degradation. Dataset 13 stays outside model training. `future_prediction_robustness` and coverage remain null.

Preserve & simulate still creates a full application snapshot, hashes and verifies saved content, stores the simulated response and audit records, and refreshes the UI. No host/network/process/account/service/shutdown action is executed. Predicted loss is never relabelled observed survival.

## 7. Commands

From `backend`:

```powershell
..\.venv\Scripts\python.exe -m app.prediction_audit
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Future training, **only after reviewed labelled data is supplied**:

```powershell
..\.venv\Scripts\python.exe -m app.temporal_prediction ..\data\temporal_events.json --task technique
..\.venv\Scripts\python.exe -m app.temporal_prediction ..\data\temporal_events.json --task stage
```

The new training paths were exercised with synthetic temporary test bundles, not a nonexistent observed dataset. Original baselines can still be reproduced using `python -m app.datasets train`; that command was not needed for this update.

From `frontend`:

```powershell
node node_modules/typescript/bin/tsc --noEmit
npm.cmd run lint
node node_modules/@playwright/test/cli.js test --reporter=list
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Browser tests intentionally create safe simulated audit/benchmark records. Deliberately injected HTTP errors test feedback and are not claimed spontaneous service failures.

### Completed verification

- Full backend suite: 24 tests passed. The eight temporal tests were rerun successfully after the final training-group inference guard.
- All 12 browser scenarios passed after correcting two tests for first-load timing and the collapsed synthetic section. The five prediction/research scenarios were rerun successfully; the seven navigation/workflow/simulation scenarios passed in the full run.
- TypeScript `--noEmit`, full ESLint and Git whitespace checks passed. No production build was run.
- Successful browser flows recorded no page/console errors. Backend logs showed no unexpected server errors; deliberate invalid requests were rejected as expected.
- Final running-state check: `/`, `/incidents`, `/evidence`, `/graph`, `/prevention`, `/research`, `/reports` all returned HTTP 200.
- Final persisted prediction attempt: `c652109f-8997-4213-850a-b3079f5fc0f3`, cutoff `2026-09-25T10:04:00`, input evidence exactly EV-00001 through EV-00004. Status `not_available`, probabilities empty, uncertainty null. The report contains the record and its audit chain verifies.
- OpTC status remains `not_imported`, event count 0. The application is running at `http://127.0.0.1:3000`, API at `http://127.0.0.1:8001`.

## 8. Files in this update

- Added: `backend/app/temporal_prediction.py`, `backend/app/prediction_audit.py`, `backend/app/services/future_prediction_service.py`, `backend/tests/test_temporal_prediction.py`.
- Extended: `backend/app/api/workflow.py`, `backend/app/api/research.py`, `backend/app/services/workflow_service.py`, `backend/app/services/analysis_service.py`, `backend/app/services/benchmark_service.py`.
- Added: `frontend/src/components/future-evaluation.tsx`, `frontend/tests/future-prediction.spec.ts`.
- Extended: `frontend/src/components/research-analysis.tsx`, `frontend/src/components/incident-console.tsx`, `frontend/src/app/page.tsx`, `frontend/src/app/research/page.tsx`, `frontend/tests/research-validity.spec.ts`.
- Generated/documented: `data/models/prediction_readiness.json`, this report, `docs/future-prediction-plan.md`, README link. Existing benchmark artifacts update when tests execute.
- Earlier preservation fixes and local setup/model metadata edits were retained.

## 9. Remaining data limits

To enable genuine prediction, supply multiple independent observed attack sequences with timestamps, arrival times, label availability times, event/incident/scenario/collection IDs, documented source/version, and independently referenced ATT&CK labels. Sufficient class support must remain after leakage-safe splitting. Deployment to a different domain needs separate evaluation.

No genuine future-technique metrics, future-stage metrics from observed sequences, real-world calibration, conformal coverage, future robustness degradation, live acquisition outcomes or future-technique preservation relevance can be supplied from the current tables. The infrastructure exposes these limits instead of manufacturing results.
