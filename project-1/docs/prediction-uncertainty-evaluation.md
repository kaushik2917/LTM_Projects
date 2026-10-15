# Future Attack Prediction: uncertainty and held-out evaluation

October 3, 2026. The existing transition-frequency model and its probabilities are unchanged. This adds an evaluation layer, distribution-based entropy, evidence checks and feedback within the existing Future Attack Prediction UI. No production rebuild or UI redesign was performed.

## Model and formulas

Model: **transition_frequency**. Model SHA-256 before and after this change:

`65e8aaf54884efe0ca75de124d734890a600831d16435ddc062fd3fa2dc67139`

The model uses normalized ATT&CK technique suffixes of length 3, then 2, then 1, with backoff to the training prior. For the selected suffix:

`P(next technique = c | suffix) = training_count(suffix, c) / total_training_count(suffix)`

No model retraining, probability adjustment or calibration fitting was performed. The output is the complete distribution over **16 trained active technique classes**, including zero-probability entries.

Uncertainty is normalized predictive entropy:

`H(p) = -sum(p_i * ln(p_i))`, with `0 * ln(0) = 0`

`H_normalized(p) = H(p) / ln(K)`, where `K = 16`

The calculation uses the full distribution before sorting/truncating for display. It validates finite, nonnegative probabilities and a sum of one. A one-class distribution has entropy zero. The value is not `1 - max(p)` and is not a calibrated error probability. Zero-probability classes count in K. Unseen classes outside the trained output space are not represented by this entropy; a low value does not establish correctness or reliability outside the training distribution.

## Dataset and split validation

Dataset: **FAPT-Guard Synthetic Temporal ATT&CK Sequence Dataset v1.0.1**.

- Synthetic: YES; real-world validation: NO
- 600 scenarios / complete event sequences
- 4,175 chronological events
- 3,575 next-technique prefix samples
- 48 distinct complete normalized technique sequences

| Supplied split | Scenarios / sequences | Prefix samples | Distinct complete technique sequences |
|---|---:|---:|---:|
| Train | 480 | 2,855 | 38 |
| Validation | 60 | 360 | 4 |
| Test | 60 | 360 | 6 |

No split was changed. Scenario IDs, incident IDs and complete normalized technique sequences have zero overlap across all three partition pairs. The new evaluator rejects overlap, even when duplicate sequences use different IDs, hosts or absolute timestamps. Complete technique sequences are fingerprinted in timestamp order. Shared shorter prefixes are not treated as complete duplicate scenarios; correlations and within-partition repeats remain disclosed.

Every supplied target is validated against the next chronological event, then transformed by the existing ATT&CK normalization. Evaluation features contain only the prefix available at cutoff; target event IDs cannot occur in supporting evidence. The original source bytes and trained model are unchanged.

Source manifest SHA-256:

`9ebef685b77a26e91777259e2b6e302420b7314bb8a9c16ad98c1e2970e90352`

Normalized dataset SHA-256:

`b94d0d9373e65b9c9adbe141eea12dbaa4411c1724c5f7f4b95fac4c3a1c9122`

## Stored evaluation run

Evaluation ID: **2aa947f2-e916-4672-a404-f801879e1562**.

Record: `data/model_evaluations/2aa947f2-e916-4672-a404-f801879e1562.json`.

Record SHA-256: `55155a7c891baf185c065b22ec6d0f536440eff3b35bce413ffd861386d8b62c`.

The record includes its timestamp, dataset version/hash, normalized data hash, model version, split scenario IDs and sequence fingerprints, inherited random seed 42, metrics, full test probability distributions, test targets, evidence IDs, entropy, calibration diagnostics and conformal eligibility findings. Evaluation itself is deterministic and uses no random operation.

`data/models/synthetic_temporal_evaluation.json` points to this run and verifies its content hash. A missing, modified or stale evaluation is exposed as unavailable, with the command needed to regenerate it. A new model or dataset does not silently inherit old metrics. The original training artifact's metadata remains historical; the separate evaluation run supplies the current measurements.

## Actual held-out metrics

The frozen model was executed on all **360 test samples from 60 scenarios**. No fitting or model selection uses these outputs.

| Metric | Measured value |
|---|---:|
| Top-1 accuracy | **0.350000** |
| Top-3 accuracy | **0.516667** |
| Macro precision | 0.106181 |
| Macro recall | 0.183007 |
| Macro F1 | **0.116613** |
| Weighted F1 | **0.286661** |
| Mean reciprocal rank | **0.459727** |
| Mean normalized entropy | **0.37675984** |
| Median normalized entropy | **0.36372148** |

Per-class precision, recall, F1, support and the confusion matrix are stored in the evaluation run's `metrics` and displayed through the existing Research evaluation table. Matrix support totals 360. The [matrix export](synthetic-temporal-confusion-matrix.csv) from the normalization pass remains valid because model predictions and labels did not change.

Macro metrics include the union of trained and actual test labels, including zero-support classes. Unseen true classes are included as misses. Top-k ties resolve by technique ID; zero-probability classes can appear in a top-k ranking. These are synthetic ranking metrics, not coverage claims.

## Probability calibration diagnostics

Calibration reliability is evaluated across the **held-out synthetic test outcomes**, never from INC-00001 alone:

- Method: top-label Expected Calibration Error (10 equal-width confidence bins) and multiclass Brier score
- Dataset: Synthetic Temporal Dataset v1.0.1, **test** partition
- Samples: **360**, from **60 scenarios**
- **ECE: 0.29797514030852135**
- **Brier score: 0.8063337416776256**

ECE is the count-weighted difference between mean confidence and accuracy within each bin. Brier is the mean squared probability error summed over the union of trained and actual outcome classes. An unseen true class has probability zero and contributes its missing mass term of 1. The run stores the reliability-bin counts, accuracy and confidence.

These are measured calibration diagnostics. **No probability recalibration has been fitted.** They do not turn the unchanged model output into calibrated probabilities or estimate correctness for a single incident. Correlated prefixes and repeated synthetic sequences limit inference about a broader population.

## Conformal coverage: NOT MEASURED

No conformal prediction-set experiment was executed, and no coverage or average set size is fabricated.

The eligibility audit records these specific constraints:

1. The supplied validation labels were already used to select the model. They cannot serve as an untouched calibration partition for that selection procedure.
2. Keeping complete duplicate sequences together leaves only **six distinct test sequence groups**. Reserving a test group leaves at most five calibration groups. At a configured 90% target, a finite split-conformal order statistic needs at least nine calibration groups. A trivial full-label set is not reported as evidence of useful coverage.
3. Validation contains `T1685` and test contains `T1547.001`, outside the frozen model's output classes. Restricting sets to model classes would exclude these outcomes regardless of threshold.
4. Template-specific partitions and correlated samples do not establish exchangeability between calibration and test outcomes.

The proposed method is split conformal with score `1 - p(true label)`, maximum score per independent sequence group, and quantile rank `ceil((n + 1) * target_coverage)`. This differs from the implemented entropy measure. The split-conformal quantile and exchangeability requirements follow [Angelopoulos and Bates, *A Gentle Introduction to Conformal Prediction*](https://arxiv.org/html/2107.07511v6).

Stored coverage fields:

- Target coverage: **0.90**, explicitly a design target, not a measurement
- Measured coverage: **null / NOT MEASURED**
- Average prediction set size: **null / NOT MEASURED**
- Coverage sample count: **0** (no coverage experiment executed)
- `experiment_executed`: **false**

What is missing is a separate labelled calibration/test collection with enough independent sequence groups, unused in model selection, an explicit label universe covering outcomes, and a defensible sampling relationship. More repeated prefix rows from the same six sequences do not supply that independence. Synthetic data may support a future controlled experiment; real-world coverage would still require separate validation.

## INC-00001 result and provenance

Cutoff: **2026-09-25T10:05:02**. Current assessment: **T1003.001 — LSASS Memory, CANDIDATE**.

| Model output | Probability |
|---|---:|
| T1021.002 — SMB/Windows Admin Shares | **0.9281045751633987** |
| T1041 — Exfiltration Over C2 Channel | **0.0718954248366013** |
| Other 14 trained classes | 0 |

The matched training suffix is T1003.001: 142 of 153 samples lead to T1021.002, and 11 lead to T1041. The full vector sums to one.

**Normalized entropy: 0.09323938097598138 (9.323938%)**, displayed as **9.3%**. K remains 16, not the two nonzero classes or the three UI rows.

Prediction ID: `faff59f1-ea26-463b-89cb-b08dcd72b908`.

Supporting evidence: **EV-00001 through EV-00006**. IDs are checked against the incident inventory, must be unique and must belong to INC-00001. The shared temporal selector enforces event and observation availability at or before cutoff. The record stores the complete distribution, uncertainty value/method/formula/class count, current/top technique, probabilities, model and dataset versions, evidence IDs, observed prefix and evaluation ID. Repeated identical inference reuses the recorded prediction; audit integrity is retained.

**Observed future outcome: NOT AVAILABLE. Prediction correctness: NOT MEASURED.** No observed event after EV-00006 is supplied for this cutoff. Neither prediction probabilities nor synthetic benchmark labels create ground truth for this incident.

## Remaining limitations and missing values

- Conformal coverage and set size remain NOT MEASURED for the reasons above.
- INC-00001 future ground truth is unavailable, so its correctness is not measured.
- Probability recalibration is not fitted. ECE/Brier are measured aggregate diagnostics.
- Entropy excludes unseen model classes and cannot establish epistemic uncertainty, causal confidence or out-of-distribution reliability.
- All benchmark data is synthetic; test scenarios have limited template diversity and repeated prefixes.
- Test performance is low and is reported without substituting training performance.
- Source ATT&CK release metadata remains unavailable; existing pinned-catalog normalization and hashes are unchanged.
- **No real host response action was executed.** Simulation, preservation and audit behavior remain intact.

## Exact files changed for this layer

Implementation and tests:

- `backend/app/prediction_evaluation.py` — new frozen-model evaluator, entropy summaries, sequence checks, calibration diagnostics, conformal eligibility and evaluation storage
- `backend/app/datasets.py` — `evaluate-temporal` command
- `backend/app/synthetic_temporal.py` — complete-distribution entropy, evidence membership checks, evaluation linkage and unknown-ground-truth fields
- `backend/tests/test_prediction_evaluation.py` — independent formulas, overlap rejection, model immutability, evaluation integrity and prediction provenance checks
- `backend/tests/test_synthetic_temporal.py` — updated uncertainty expectation
- `frontend/src/components/research-analysis.tsx` — entropy/calibration feedback, coverage explanation and ground-truth distinction
- `frontend/src/components/future-evaluation.tsx` — evaluation ID, hashes, metrics, entropy statistics and calibration/conformal findings
- `frontend/tests/future-prediction.spec.ts` — UI and independently calculated entropy checks

Generated records and documentation:

- `data/model_evaluations/2aa947f2-e916-4672-a404-f801879e1562.json`
- `data/models/synthetic_temporal_evaluation.json`
- `data/workflow.sqlite3` — new local prediction/audit records
- `docs/prediction-uncertainty-evaluation.md`, `docs/synthetic-temporal-validation.md`, `README.md`, `DATASETS.md`

The existing model artifact and normalized training dataset were not modified. Browser fixture-benchmark tests can refresh the existing `data/benchmark_report.json` runtime report.

## Commands

Validation completed: **37 backend tests and 12 browser scenarios passed**. TypeScript, ESLint and Git whitespace checks passed. Final browser checks recorded no page/console errors; backend logs contained no error/traceback entries. Dashboard, Research and API status returned HTTP 200. The SQLite audit chain verified with zero legacy unsealed entries. Tests cover entropy formulas and invalid distributions, calibration against hand calculations, all held-out outputs, full-sequence overlap rejection, model immutability, evaluation tampering/staleness, prediction reproducibility, evidence membership/cutoff, unknown ground truth and safe simulation.

From `backend/`:

```powershell
..\.venv\Scripts\python.exe -m app.datasets evaluate-temporal
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

From `frontend/`:

```powershell
npx.cmd tsc --noEmit
npm.cmd run lint
npx.cmd playwright test
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Run `evaluate-temporal` again after any future model/data change; otherwise the stale-evaluation guard keeps those measurements unavailable.
