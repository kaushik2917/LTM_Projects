# FAPT-Guard temporal pipeline v2

## Implemented behavior

The existing FastAPI/Next.js application now connects prefix evidence, next-technique prediction, calibration, conformal sets, explicit synthetic ground-truth reveal, expected future risk and audited reporting. INC-00001 and EV-00001 through EV-00006 remain unchanged. Its ground truth is **PENDING** and correctness is **PENDING_GROUND_TRUTH**. Its LSASS assessment remains CANDIDATE.

All prevention actions remain simulated records. Snapshot preservation still serializes actual application evidence, calculates SHA-256 over canonical JSON, reads it back and verifies it before recording the simulation. There is no host action dispatcher.

## Dataset and reproducibility

Run from `backend`:

```powershell
..\.venv\Scripts\python.exe -m app.datasets experiment-temporal
```

This generates, validates, trains and evaluates dataset **2.0.0**, generator **source-transition-walk-v1**, seed **20261003**. Original v1.0.1 CSVs, normalized model and historical evaluation remain available. The new JSON bundle is `data/custom/synthetic_temporal_v2/scenarios.json`.

Each scenario stores unique scenario/incident IDs, host/user, ordered evidence IDs/timestamps, source/subject/action/object, technique/tactic, explicit synthetic annotation status, sequence position, next-technique label and next-event time. Mapping confidence is null: generator annotations are not measured sensor confidence. Known synthetic labels are CONFIRMED annotations; existing behavior-based CANDIDATE and UNMAPPED events are preserved.

The generator uses normalized transitions and event templates from the supplied dataset, with 10% repeated-current transitions and 10% uniform restarts among existing active labels. Terminal source states restart. Lengths are 6–12 events. Duplicate complete technique paths are rejected. Hosts, users and clocks are simulated. These sequences are not observations, and random restarts do not establish realistic attack causality. Source corpus knowledge defines the generator; this is evaluation on newly generated scenarios from that generator, not generalization to a new attack domain.

Scenarios are shuffled once into disjoint groups:

| Group | Scenarios | Model outcomes used |
|---|---:|---:|
| Training | 700 | 5,655 prefix/next-event pairs |
| Probability calibration | 75 | 75 predetermined cutoffs |
| Conformal calibration | 75 | 75 predetermined cutoffs |
| Test | 150 | 150 predetermined cutoffs |

One cutoff is sampled per nontraining scenario without consulting its target. Related prefixes are not treated as independent test outcomes. Validator rejects duplicate scenario/incident/evidence IDs, duplicate complete paths, incorrect next labels/times, unordered timestamps and invalid prefix/target separation. Shared shorter transitions are expected; template/domain generalization is not claimed.

## Prediction and uncertainty

The original `TransitionFrequency` estimator is reused. It matches the longest available suffix feature (up to three mapped techniques), backs off to two/one, then uses the training class prior. Raw probabilities are unsmoothed matching counts divided by total support. Inputs use the existing `sequence_features` whitelist; identifiers, split, target fields and later events are excluded. Ground truth is the first labelled event strictly after the cutoff.

The API retains the old prediction fields and adds raw/calibrated distributions, probability kind, scenario ID, structured ground truth/evaluation, prediction set, calibration, dataset metrics and split provenance. All 19 trained classes are represented. Entropy is `-sum(p*log2(p))/log2(K)`, computed from the full calibrated vector including zero classes; it is distributional dispersion, **not error probability**.

## Probability calibration

Temperature scaling transforms `log(max(raw_probability, 1e-6)) / T`, followed by softmax. The probability floor is explicit and does not alter stored raw model output. A fixed grid from 0.25 to 4.0 in 0.05 steps minimizes negative log likelihood on the probability-calibration subgroup only. This run selected **T=4.0**, the upper grid boundary; the finite search range is a limitation, not evidence of optimal calibration.

The separate conformal-calibration subgroup supplies independent reliability diagnostics and conformal scores after temperature is frozen. Raw and calibrated ECE/Brier/reliability bins are persisted for both calibration groups and test. Fit-group diagnostics are clearly distinct from independent diagnostics.

Multiclass Brier is the mean over outcomes of the **sum over classes** of `(p_k - one_hot_target_k)^2`; it is not divided by class count. ECE uses ten equal-width top-confidence bins, weighted by outcome count; the first includes zero, subsequent bins exclude the lower and include the upper boundary. Calibration does not establish accuracy.

## Conformal prediction

Scores are `1 - calibrated_probability(true_class)`. With n=75 independent scenario outcomes and target 0.90, the threshold is the **69th sorted score**, using `ceil((n+1)*0.90)`. If the requested rank exceeds n, the full bounded-score threshold 1 is used. Sets contain every class whose score is at most the threshold.

This follows [split-conformal classification](https://arxiv.org/html/2107.07511v6). Temperature fitting, conformal threshold fitting and testing use disjoint scenarios. Test labels do not choose the temperature or threshold. Coverage is a procedure-level aggregate, not an incident's probability of correctness. Synthetic path construction and source assumptions limit claims outside this experiment; no real-world coverage guarantee is made.

## Actual evaluation run

Evaluation ID: `1a36ebba-5774-49d4-8f46-36630d9b6b33`.

Model SHA-256/version: `b0a9b61c02871a72f3db945c14dac7bece5bc8b3dcf9dd23ba0a8183c30ecc93`.

Dataset SHA-256: `8433855364724c70b147ee480e0e2eb739aa7ae26d3e590657754bb22aab7a6e`.

| Metric | Calculated result |
|---|---:|
| Test top-1 | 43.3333% |
| Test top-3 | 64.6667% |
| Test macro precision | 0.303823 |
| Test macro recall | 0.315231 |
| Test macro F1 | 0.296586 |
| Independent calibration ECE | 0.138538 |
| Independent calibration Brier | 0.828493 |
| Test ECE | 0.157564 |
| Test Brier | 0.799862 |
| Conformal target | 90% |
| Empirical test coverage | 89.3333% (134/150) |
| Average prediction set size | 11.4067 of 19 classes |
| Minimum / maximum set size | 3 / 19 |

The wide sets and modest accuracy are limitations. No values were substituted to meet the target. Full confusion matrix, per-class metrics, raw/calibrated reliability bins, calibration scores and every evaluated vector are in the versioned evaluation JSON. The pointer `data/models/temporal_experiment.json` seals its SHA-256; inference verifies dataset/model/catalog hashes. Regeneration preserves dataset/model calculations; evaluation UUID and timestamp identify each run.

INC-00001 now produces T1021.002 with raw probability 1.0 from one matching suffix sample and calibrated probability 0.637263; normalized entropy is 0.578521. These values changed because training data changed. Sparse support and the explicit probability floor must be considered when interpreting this result. No future event was added to that incident.

## Demonstration, graph and report

On **Dataset research → Synthetic Evaluation / Demonstration**, select a held-out scenario and cutoff, then choose **Predict observed prefix**. The response and temporal relationship graph include only observed evidence. **Reveal hidden ground truth** evaluates the already stored probabilities, exposes the first later labelled event and records CORRECT/INCORRECT, actual-class probability and rank. Model prediction and revealed annotation remain separate sections. Interactive cutoffs do not replace the fixed-cutoff test metrics.

**Export demonstration report** exports the prediction, any already revealed evaluation, observed evidence, payload SHA-256 and relevant audit records. Exporting does not reveal hidden labels. Existing forensic exports include the current incident's prediction, split/calibration/conformal provenance, pending ground truth, assessments, simulated responses, preserved snapshots and chain verification.

APIs:

- `GET /api/research/temporal-scenarios`
- `POST /api/research/temporal-scenarios/{scenario_id}/predict` with `cutoff_timestamp`
- `POST /api/research/temporal-scenarios/{scenario_id}/reveal` with `prediction_id`
- `POST /api/research/temporal-scenarios/{scenario_id}/report` with `prediction_id`
- Existing `/api/workflow/{incident_id}/prediction`, `/assessment`, `/simulate` and `/report/export` remain compatible.

SQLite schema is unchanged. The existing JSON audit table stores `future_prediction`, `prediction_evaluation` and `report_generation` records. Calibration/conformal evaluations use immutable versioned JSON artifacts, avoiding duplicate tables. The local SHA-256 chain detects edits but has no external signature/anchor.

## Prediction-aware prevention

`ExpectedFutureRisk(action) = sum(probability(t) * ResidualRisk(action,t))`.

For techniques represented in response dataset 10, the existing ACES model supplies action-conditioned synthetic residual-risk estimates with the corresponding stage. Other analyst context stays fixed. For unsupported techniques, the explicit assumption is unchanged current-state residual risk. Every class's source/contribution and unsupported probability mass are exposed. No invented measured causal risk table is introduced.

`new_objective = existing_weighted_objective + future_prediction_weight * expected_future_risk`.

`backend/config/research.json` sets the additional weight to **0.2**. Existing risk, normalized evidence loss, business, cost and opportunity terms retain their definitions and weights. The added term is not renormalized. Missing future predictions retain the base objective and an unavailable reason. Old saved assessments retain their original scores; rerun to use the new term. The existing `prediction_uncertainty` input is labelled **Analyst uncertainty assumption** and remains separate from predictive entropy.

## Files and checks

Added: `backend/app/temporal_experiment.py`, `backend/tests/test_temporal_experiment.py`, `frontend/src/components/temporal-demonstration.tsx`, `frontend/tests/temporal-demonstration.spec.ts`, v2 dataset, experiment pointer/evaluation artifacts, this document and `temporal-upgrade-plan.md`.

Updated: backend dataset CLI, research API, synthetic/future prediction services, metadata, research response scoring, workflow integration and research config; frontend prediction feedback, research evaluation and incident console; legacy-model tests explicitly selecting the preserved artifact; browser expectations; README, DATASETS and artifact ignore rules. Existing unrelated work was retained.

Validation: backend unit/integration suite, dataset regeneration/hash equality, independent metric reconstruction, leakage/partition rejection, correct/incorrect/pending cases, reveal/export boundary, expected-risk distribution dependence, all-action simulation checks, TypeScript, ESLint, production build and headless Edge workflows. Browser tests cover all seven navigation routes, graph cutoff, evidence intelligence, prediction modal, demonstration/reveal, prevention, snapshot SHA-256, error feedback, report download and mobile navigation. Browser error events are captured; expected injected failure tests intentionally exercise API rejection.

Final results: **44 backend tests passed; 14 browser tests passed against the production build; TypeScript, ESLint, `next build` and whitespace checks passed.** The frontend runs at `http://127.0.0.1:3000`; API at `http://127.0.0.1:8001`. No unexpected browser errors occurred in monitored flows, and the checked API log contained no traceback or HTTP 500.

An inspected NETWORK_ISOLATE simulation was `25073fde-86e6-4c32-a8e5-1ccb574fa15f`, with snapshot `5453085d-1342-4160-9dbb-7976f80bc594`, six evidence records, SHA-256 `2ec70127537232e242d13e777a615c55378a0fcf90cd6611f6b20ab70edc7d52`, verification VERIFIED and a verified audit chain. `host_action_executed` was false. Actual post-response evidence survival remains unavailable because no real response occurred.
