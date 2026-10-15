# Temporal pipeline implementation plan

Repository audit: FastAPI routes call workflow/research services; Next.js client components render their JSON. SQLite's canonical SHA-256 audit payloads already store predictions, snapshots, simulations and reports. No new database tables are needed. TransitionFrequency and sequence_features produce temporal probabilities; temporal_prediction.entropy/evaluate implement entropy, ECE, Brier and classification metrics. prediction_evaluation currently cannot fit conformal coverage because validation selected the model. research_service.responses owns the weighted prevention objective. research-analysis, future-evaluation and incident-console display these outputs.

1. Preserve v1.0.1 and add deterministic v2 synthetic scenarios derived from normalized source transitions. Validate complete sequences, scenario partitions and prefix/target separation.
2. Reuse TransitionFrequency and evaluation utilities. Fit counts on training only; fit temperature on one calibration subgroup and conformal scores on a separate subgroup. Evaluate one prespecified cutoff per test scenario.
3. Integrate versioned artifacts and current-incident pending status. Add audited demonstration prediction followed by explicit ground-truth reveal using stored prediction probabilities.
4. Extend the existing prevention objective with a configurable expected future risk term using the existing response model, with unsupported contexts explicitly unavailable.
5. Extend existing UI/report contracts, add leakage and mathematical tests, run all checks and build, then inspect the running application and browser/backend errors.

All response actions remain records only. Synthetic calibration and test coverage do not establish real-world performance or causal prevention effectiveness.
