> Historical CHRONOLOGICAL-V2 experiment. For the separately frozen prospective evaluation, see [PROSPECTIVE-V1 results](prospective-prediction-results.md); for the 32.67% / 43.33% discrepancy, see [validity audit](temporal-research-validity.md). Historical values below remain unchanged.

# Prediction benchmark

## Measured result

The 90% target was **NOT ACHIEVED**. FAPT-Guard scored **32.6667%** (49/150) on the fixed synthetic temporal test scenarios. The strongest baseline, Markov, scored **38.6667%** (58/150). There is no superiority claim.

These are offline synthetic generator annotations, not independently validated attack labels. The same test scenarios had already been evaluated before the expanded search was requested. They were not replaced or resampled. This is an exploratory evaluation, not an untouched confirmatory result.

All table values are fractions. Precision and recall are macro-averaged across the supported/observed class union. Accuracy, Top-3 and F1 cover every test sample before abstention. Covered accuracy uses only the predictions passing the fixed thresholds; null means no predictions passed.

| Model | Top-1 | Top-3 | Precision (macro) | Recall (macro) | Macro F1 | Coverage | Abstention | Covered accuracy | Brier | ECE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Most frequent | 0.166667 | 0.360000 | 0.008772 | 0.052632 | 0.015038 | 0.000000 | 1.000000 | NOT MEASURED | 0.929815 | 0.003810 |
| Markov | 0.386667 | 0.633333 | 0.252913 | 0.214416 | 0.198682 | 0.293333 | 0.706667 | 0.750000 | 0.725762 | 0.065833 |
| Random Forest | 0.326667 | 0.606667 | 0.243512 | 0.197473 | 0.187474 | 0.053333 | 0.946667 | 0.875000 | 0.799090 | 0.092889 |
| Gradient Boosting | 0.260000 | 0.546667 | 0.183375 | 0.167543 | 0.169664 | 0.380000 | 0.620000 | 0.526316 | 0.849016 | 0.220252 |
| Sequence model | 0.280000 | 0.500000 | 0.283727 | 0.190318 | 0.195602 | 0.573333 | 0.426667 | 0.430233 | 0.990657 | 0.332601 |
| FAPT-Guard | 0.326667 | 0.600000 | 0.224206 | 0.190995 | 0.180459 | 0.193333 | 0.806667 | 0.793103 | 0.747177 | 0.127372 |

Sequence model means the existing non-neural variable-order suffix estimator (length 3, backoff to 2, 1, training prior). GRU/LSTM: **NOT MEASURED**, because torch and TensorFlow are not installed. No heavy dependency was added.

Temperature selection on the separate calibration partition chose 1.0: the transform did not improve or change the proposed probabilities. Calibration is measured, not assumed. Baselines use their raw probabilities. See [full evaluation](prediction-accuracy-evaluation.md) and [machine-readable report](../data/model_evaluations/chronological_prediction_v2/report.json).
