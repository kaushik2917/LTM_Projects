# OpTC Future Prediction Protocol

Version: Step 2C proposal. **NOT READY FOR TRAINING OR EVALUATION.** This document defines intended rules; no experiment or metric has been run.

## Research question and scope

Can a model predict the next independently established ATT&CK technique onset within a fixed horizon using only earlier endpoint telemetry? OpTC is a controlled exercise. Even a future successful holdout would not establish production or real-world deployment validity.

Historical telemetry → fixed cutoff → earlier-only features → prediction → later events → independent ground-truth reconciliation → evaluation.

## Observation window, horizon and cutoff rule

- Proposed observation window: the preceding 30 minutes, inclusive at the start and cutoff.
- Proposed horizon: strictly after cutoff through 30 minutes later, inclusive at the end.
- Proposed cutoff grid: every 5 minutes within verified complete coverage. Anchor the grid to UTC after clock reconciliation, not to future attack events.
- Require a complete observation window and follow-up horizon. Censor insufficient coverage; do not treat it as a negative.
- Freeze these values before model fitting. Changes create a new protocol version and invalidate comparisons unless rerun consistently.

The earlier Day 1 printed 11:30 cutoff is an exploratory linkage example between narrative foothold and credential-collection actions. It is not an outcome-independent evaluation grid and has no approved timezone alignment. Host SysClient0201 and the selected shards are a pipeline pilot, not a representative holdout.

## Target definition

Primary target: the first independently reviewed technique onset within the horizon. Define an onset by reviewed action episode, not every repeated log line. Technique IDs and version must be approved independently of predictor output. Record attempt/success/failure separately; an attempted technique can be a behavior onset if the chosen annotation policy explicitly includes attempts.

If multiple techniques begin at indistinguishable times, retain the target set and mark the primary single-label sample ambiguous. Exclude it under a rule frozen before training; report its count separately rather than imposing a guessed ordering. If follow-up is complete and reviewed but no onset exists, use an explicitly defined NO_EVENT class. Missing annotations or missing telemetry mean UNKNOWN/CENSORED, not NO_EVENT. Freeze taxonomy and treatment of unseen techniques using training/protocol information, not test results.

## Ground-truth sources and review

Official PDF supplies narrative evidence. Complete official eCAR supplies independently observed later behavior. AT03380 tasks/labels provide supplementary candidate links. Require documented analyst adjudication, event references, clock alignment and ATT&CK catalog version. No explicit technique IDs were found in the acquired tasks/PDF. Existing FAPT-Guard mapping rules must not supply evaluation truth. Reviewers should be blinded to model predictions.

## Scenario and host splits

Build connected groups from campaign/collection links, shared attack state, pivots and duplicate episodes. No component may cross train/validation/test/calibration boundaries. Related campaign days may need to stay together. Random event/prefix splits are prohibited.

Propose 60/20/20 train/validation/test allocation at group level only if sufficient independent groups exist. Reserve additional disjoint groups for probability calibration and, if justified, conformal calibration; do not slice prefixes from the same campaign to populate these sets. Specify actual groups before training and report deviations from proportions. Scarcity is a reason to stop, not to weaken independence. Current data does not demonstrate enough independent groups.

For an additional unseen-host claim, require host separation on top of campaign separation. Otherwise state that host generalization was not tested. Global host and process identities are join keys, not model shortcut features.

## Feature extraction

Use a reviewed allowlist: pre-cutoff counts/rates of object-action types, time gaps, and process/flow relationships established using earlier observations only. Keep raw UUIDs, source archive names, campaign/task labels, future timestamps, targets and post-hoc process trees out of model features. Freeze handling of paths, commands and categorical values on training data only. No test vocabulary, scaler fitting or feature selection.

Event-time replay is the default proposed estimand because ingestion/observed-at times are not established. If actual availability timestamps become available, require both event time and availability time ≤ cutoff. Never fabricate availability by copying event time while claiming online performance.

## Model training and validation

Do not train until official telemetry, reviewed targets and split approvals are complete. Proposed baselines are a training-only class prior and first-order technique-transition baseline; any transition features must themselves be based on approved pre-cutoff observations. A simple multiclass model may follow after feature review. Select model/hyperparameters on validation groups only. Freeze seeds, code/data hashes and all preprocessing. Synthetic v2 metrics are irrelevant to this OpTC experiment.

## Holdout testing and metrics

Freeze the model, probability calibration and exclusions before opening holdout labels for evaluation. Evaluate each accepted cutoff once. Because adjacent cutoffs overlap, report campaign-level support and uncertainty intervals grouped by independent campaign; do not treat every prefix as an independent draw.

Planned metrics: Top-1, Top-3, Top-5, MRR, macro-F1, multiclass Brier and ECE. Ranking uses a frozen deterministic tie rule; k is capped at the declared class count. MRR uses reciprocal rank of the unique accepted target. Macro-F1 uses the declared target classes with explicit zero-support handling. Brier is the mean sum of squared class-probability errors. ECE uses 10 prespecified equal-width confidence bins, with counts reported. If targets remain ambiguous, use the prespecified exclusion policy and report excluded samples. Metrics are NOT MEASURED today.

## Calibration

Fit any probability calibrator only on an independent reserved calibration partition after model selection. Evaluate calibrated and uncalibrated outputs on untouched test groups using the same samples. Report calibration-group scarcity and confidence-bin counts. No current real calibration partition or fitted real calibrator exists.

## Uncertainty

Predictive entropy and maximum class probability may later describe a distribution; they do not by themselves establish calibrated uncertainty or correctness. Evaluate uncertainty against held-out errors with prespecified measures. Do not invent epistemic estimates or transfer uncertainty metrics from synthetic data.

## Conformal evaluation, only if supported

Require a separate untouched calibration set and a defensible exchangeability/grouping argument. Overlapping cutoffs and related campaigns violate naive independent-example assumptions. A proposed 90% target coverage must not be presented as guaranteed when assumptions fail. If feasible later, report observed test coverage, set size and group/class support at fixed alpha=0.10; otherwise mark conformal evaluation NOT SUPPORTED. No conformal fitting or guarantee is made here.

## Release gate

Finalize reviewer-approved protocol, raw coverage, independent targets, enough disjoint groups, hash manifests and leakage checks before a separate authorized training task. Current real prediction, calibration, conformal and holdout statuses are all NOT_READY.
