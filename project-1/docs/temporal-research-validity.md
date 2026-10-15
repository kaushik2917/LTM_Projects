# Temporal prediction research-validity audit

## Why 32.67%, 43.33% and 63.73% differ

These values are not measurements of the same fitted model on the same samples.

| Display | Meaning | Protocol |
| --- | --- | --- |
| 32.6667% | 49/150 correct next-event predictions | CHRONOLOGICAL-V2: midpoint per scenario, chronological groups, RF/boosting/Markov ensemble |
| 43.3333% | 65/150 correct next-event predictions | V2-RANDOM-TRANSITION: random scenario groups, all training prefixes, one stored random cutoff per test scenario |
| 63.7263% for T1021.002 | One incident class probability, not accuracy | INC-00001, historical transition-frequency model with temperature 4.0 |

Both v2 experiments use the same source file hash, but different groups, training samples, cutoffs, features and models. Only 16 test scenarios overlap. **113 of the chronological experiment's 150 test scenarios were training scenarios in the older random experiment.** The chronological learner did not directly fit on its own test rows, but cross-experiment exposure rules out presenting it as untouched confirmatory research. The old random-group split is sequence-disjoint but not chronologically separated.

INC-00001 is absent from all benchmark partitions. Its raw distribution places probability 1 on T1021.002 based on **one matching training transition**. Flooring the other 18 class probabilities to 1e-6 and applying temperature 4.0 produces 0.6372633449. This is sparse synthetic model output, not evidence of 63.7% incident accuracy. Future ground truth/correctness remains PENDING_GROUND_TRUTH; the demonstration must never be added as a test observation.

## Every metric-producing path

- `backend/app/training.py::classification_metrics`: shared accuracy, macro/weighted/per-class F1 and confusion matrix calculation. Other classifiers in this file target next stage or anti-forensic labels, not next ATT&CK events.
- `backend/app/temporal_prediction.py::evaluate/train`: shared Top-k, MRR, Brier, ECE plus observed-data training; operational model qualification remains separate.
- `backend/app/synthetic_temporal.py::train`: historical v1.0.1 candidate selection and evaluation; 600 scenarios, 3,575 samples; supplied template partitions.
- `backend/app/prediction_evaluation.py`: re-evaluates the frozen v1 artifact; it does not create a new independent dataset. Its conformal-readiness output is NOT MEASURED.
- `backend/app/temporal_experiment.py::train_experiment`: historical v2 generation and random-group transition model with independent probability/conformal calibration subgroups. Its `infer` supplies INC-00001 probabilities. `demonstrate/reveal` exposes test cases interactively; these are historical demonstration cases now.
- `backend/app/prediction_benchmark.py`: historical chronological ensemble benchmark and sensitivity results. Its metrics are exploratory because its test set was exposed before the expanded search.
- `backend/app/prospective_prediction.py`: new staged protocol; model selection finishes before a new synthetic test draw exists. A persistent exclusive evaluation lock prevents a second scoring run.
- `backend/app/services/benchmark_service.py` and `research_service.py`: other robustness/expected-score summaries explicitly leave future-technique accuracy null when labels are unavailable.
- `backend/app/api/defense.py`: operational prediction accuracy is null, with an explanation. No synthetic benchmark result is substituted into defense metrics.
- Frontend consumers are `future-evaluation.tsx`, `temporal-demonstration.tsx`, `prediction-benchmark.tsx`, `research-analysis.tsx`, and the new `prospective-evaluation.tsx`. Historical experiment IDs/model hashes/splits now accompany their metrics. The standalone `fapt_guard` package has no additional fitted temporal metric implementation.

## Exact historical experiment inventory

The following fields are transcribed from stored artifacts and inference output, not guessed. Full machine-readable records are in `docs/temporal-experiment-audit.json`.

### CHRONOLOGICAL-V2

- **dataset_version**: 2.0.0
- **dataset_hash**: 8433855364724c70b147ee480e0e2eb739aa7ae26d3e590657754bb22aab7a6e
- **sequences**: 1000
- **samples**: 1000
- **classes**: 19
- **split**: {"train": 700, "validation": 100, "calibration_probability": 50, "calibration_conformal": 0, "test": 150}
- **model**: FAPT-Guard ensemble 0.5 Markov + 0.25 RF + 0.25 Gradient Boosting
- **model_version**: chronological-synthetic-v2
- **model_hash**: 32a942498ddbad5363d830488b13b54ada9d072e0e4f487f6d09caf9e265f18c
- **features**: future_prediction_v2: suffixes 1/2/3, counts/transitions, elapsed/last interval, source/action counts, recent3/repeats/last tactics; no identity or absolute dates
- **preprocessing**: Timestamp sorting, strict prefix whitelist and label availability; midpoint per scenario; exact path/identity rejection
- **calibration**: Temperature on 50 calibration sequences, selected T=1
- **conformal**: NOT MEASURED in this experiment
- **test_usage**: 150 chronologically latest sequences; previously evaluated under v1 then expanded model search; all baseline rows identical
- **test_influenced_tuning**: Code selects on validation only. Prior test exposure means adaptive human influence cannot be excluded; exploratory, not confirmatory. Historical random experiment used some of these groups for training.
- **top1**: 0.32666666666666666

### V2-RANDOM-TRANSITION

- **dataset_version**: 2.0.0
- **dataset_hash**: 8433855364724c70b147ee480e0e2eb739aa7ae26d3e590657754bb22aab7a6e
- **sequences**: 1000
- **samples**: 5955
- **classes**: 19
- **split**: {"train_sequences": 700, "train_samples": 5655, "validation": 0, "calibration_probability": 75, "calibration_conformal": 75, "test": 150}
- **model**: transition_frequency
- **model_version**: b0a9b61c02871a72f3db945c14dac7bece5bc8b3dcf9dd23ba0a8183c30ecc93
- **model_hash**: b0a9b61c02871a72f3db945c14dac7bece5bc8b3dcf9dd23ba0a8183c30ecc93
- **features**: Existing sequence_features whitelist; selected model uses only last 3/2/1 mapped techniques, then global training prior. Unsmoothed raw counts; calibration floor applied separately.
- **preprocessing**: Source labels normalized via pinned ATT&CK; original shuffled whole-scenario split; all adjacent training prefixes, random stored cutoff for held-out groups
- **calibration**: 75 probability-calibration rows; temperature 4.0, log probability floor 1e-6
- **conformal**: 75 separate rows; LAC score 1-p(true), q=0.9885469306569868, target90%; test coverage89.3333%, average set11.4067
- **test_usage**: 150 random-group test samples; calendar periods overlap partitions. Interactive demonstrations subsequently expose test labels.
- **test_influenced_tuning**: Training code fixes transition model and fits temperature on calibration only. No evidence of test-based parameter optimization; prior development history cannot be reconstructed solely from artifacts. Random group split is not chronological.
- **top1**: 0.43333333333333335

### INC-00001-DEMO

- **dataset_version**: 2.0.0 trained model; separate incident fixture
- **sequences**: 1
- **samples**: 0
- **classes**: 19
- **split**: No benchmark partition; same model/provenance as V2-RANDOM-TRANSITION
- **model**: transition_frequency
- **model_version**: b0a9b61c02871a72f3db945c14dac7bece5bc8b3dcf9dd23ba0a8183c30ecc93
- **model_hash**: b0a9b61c02871a72f3db945c14dac7bece5bc8b3dcf9dd23ba0a8183c30ecc93
- **features**: {"event_count": 6, "mapped_count": 2, "technique_suffix_1": "T1003.001", "technique_suffix_2": "T1059.001|T1003.001", "technique_suffix_3": "T1059.001|T1003.001", "technique_count:T1059.001": 1, "technique_count:T1003.001": 1, "transition:T1059.001>T1003.001": 1, "elapsed_seconds": 182.0, "last_interval_seconds": 42.0, "source_count:authentication": 1, "source_count:process": 2, "source_count:sysmon": 2, "source_count:network": 1}
- **preprocessing**: Incident evidence prefix and candidate mapping; not independent target labels
- **calibration**: Same T=4 transform as V2-RANDOM-TRANSITION
- **conformal**: Same historical population calibration; no empirical incident coverage
- **test_usage**: Never count INC-00001 as test sample; PENDING_GROUND_TRUTH
- **test_influenced_tuning**: No fit or tuning performed by incident inference
- **probability**: 0.6372633449255795
- **technique**: T1021.002
- **raw_support**: {"basis": "training suffix transition counts", "suffix_feature_length": 3, "matched_technique_suffix": ["T1059.001", "T1003.001"], "target_counts": {"T1021.002": 1}, "total_training_samples": 1, "training_sample_ids": ["SYN2-00469-EV-002"], "formula": "Model output probability = target count / total matching training samples"}

### V1-TEMPLATE

- **dataset_version**: 1.0.1
- **dataset_hash**: 9ebef685b77a26e91777259e2b6e302420b7314bb8a9c16ad98c1e2970e90352
- **sequences**: 600
- **samples**: 3575
- **classes**: {"event_classes": 19, "target_classes": 18, "trained_target_classes": 16}
- **split**: {"train_sequences": 480, "validation_sequences": 60, "test_sequences": 60, "sample_counts": {"train": 2855, "test": 360, "validation": 360}, "calibration": 0}
- **model**: transition_frequency
- **model_version**: 65e8aaf54884efe0ca75de124d734890a600831d16435ddc062fd3fa2dc67139
- **model_hash**: 65e8aaf54884efe0ca75de124d734890a600831d16435ddc062fd3fa2dc67139
- **features**: {"available_features": "Last 1/2/3 mapped techniques, technique and transition counts, event/mapped counts, elapsed time, last interval, source counts", "selected_model_features": ["technique_suffix_3", "technique_suffix_2", "technique_suffix_1"], "excluded": "Targets, future events, incident/scenario/template IDs, sample IDs and split"}
- **preprocessing**: Pinned STIX replacement normalization; preserve original CSV; supplied template split
- **calibration**: Uncalibrated; diagnostics only
- **conformal**: NOT MEASURED; insufficient independent sequence groups
- **test_usage**: 360 adjacent prefixes from 60 test scenarios; repeated templates/full paths limit independence
- **test_influenced_tuning**: Highest validation macro-F1; ties favor transition frequency. Test never used for fitting or selection.
- **top1**: 0.35

## Why the historical ensemble lost

The existing generator is primarily a first-order transition walk, so a first-order baseline matches that data-generating assumption. The chronological experiment fitted only 700 midpoint samples, versus 5,655 prefixes for the historical random-group model. Mixing in RF/boosting can dilute a good transition estimate. Its old search also required at least two nonzero ensemble weights, forbidding selection of the strongest single baseline as the proposed method. Validation-selected weights need not generalize: historical validation selection did not establish test superiority. The test scores are diagnostic observations only, not selection criteria for this revision.

The new prospective selector permits a single baseline, a validation-selected ensemble, or smoothed variable-order history. Hierarchical Dirichlet smoothing backs sparse long suffixes toward shorter history instead of trusting a single matching transition. Added whitelist features include suffixes through length five, trigrams, tactic history, prefix event density and 300-second decayed technique counts. Existing class-weight grids remain training-only. Selection uses validation Top-1 then macro F1, not historical test scores. No neural-model superiority is assumed.

## Why the historical conformal sets are broad

The older model uses unsmoothed suffix counts, often assigning zero probability to the true future class. The calibration-selected temperature 4.0 flattens its probabilities. Its 90% LAC quantile is 0.9885469306569868, so every class with probability at least 0.0114530693430132 is included. Many classes meet that low inclusion threshold. Mean set size is 11.4067/19; empirical test coverage is 89.3333%, not a guaranteed achieved 90%.

The new protocol improves the underlying probability estimator and keeps the conformal rule fixed. Temperature fitting and LAC quantiles use separate 25-sequence subgroups. There is no test-based set shrinking or choice of conformal method. Small calibration cohorts, temporal shifts and unique-path rejection limit finite-sample coverage claims; nominal coverage is a design target, not a result to force. The finite-sample order statistic is ceil((n+1)*0.90); with n=25 this is rank 24. A broad resulting set must be reported honestly.

## Prospective protocol and limitations

Existing earliest 700 scenarios train models; next 100 select models/features/hyperparameters; next 25 fit temperature; next 25 calibrate conformal sets. Historical latest 150 test scenarios are excluded from fitting/selection/calibration. All existing development cohorts have some historical exposure; this is disclosed. Independence is established prospectively for the new test draw, not retroactively claimed for the development data.

The frozen generator uses the same documented source transition distribution as historical v2: 10% repeats, 10% uniform restarts, lengths 6?12, gaps 20?120 seconds. It is a synthetic transition process, not a validated simulation of independent attack families. The original v1 labels define the generator; they are explicitly research annotations. Generator source hashes and parameters are frozen alongside model hashes before a seed is drawn. No test is regenerated because a score is low. The prospective draw has 300 sequences, new incident/evidence IDs, generated dates after all historical sequences, and no exact full-path duplicate of any historical sequence or another prospective sample. Partial prefixes may repeat legitimately.

All six models use identical prospective test rows. Probability calibration is fitted separately for each model on the same probability-calibration subgroup. Conformal LAC thresholds are fitted per model on the same distinct conformal subgroup. Stored results include all requested classification metrics, Wilson Top-1 intervals, calibration, abstention coverage and conformal coverage/set size. Confidence intervals do not establish real-world performance or correct for synthetic-generator dependence.

An exclusive freeze and evaluation marker blocks refitting/re-evaluation in the same experiment directory. Stored predictions and a persisted random seed permit artifact verification without selecting another seed. Local hashes/locks are reproducibility controls, not external cryptographic custody; an operator with write access could replace them. Future independent observed sequences are still needed for operational validation.

## Prevention laboratory formula

The implemented score is an **unnormalized additive advisory cost**:

`J(action) = base_weighted_cost(action) + 0.2 * expected_future_risk(action)`.

The five base weights total 1.0. With future information, total weight is 1.2. The code adds the future term separately and preserves both base and future contributions. This is mathematically consistent as a penalty objective: only relative action ranking is used, not a probability interpretation or fixed [0,1] threshold. Dividing all action scores by 1.2 leaves rankings unchanged but changes recorded numerical contributions and comparability with prior reports. Accordingly the coefficients/rankings are preserved, while API/UI now explicitly report `objective_normalized=false`, total weight 1.2, and the [0,1.2] range when component costs are unit-range. Without a future distribution the base remains normalized. This does not change the defense risk formula or policy thresholds.

DRY_RUN/advisory responses remain unexecuted. No preservation estimate is claimed as observed prevention success.


## Completed prospective result

The single prospective draw yielded 38.0% FAPT-Guard Top-1 versus 37.6667% Markov. FAPT conformal coverage was 82.0%, mean set size 5.913333. Neither the accuracy target nor conformal coverage target was met. These outcomes did not trigger refitting, threshold changes or another test draw. See [complete final results and reproduction](prospective-prediction-results.md).
