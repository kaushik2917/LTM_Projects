# FAPT-Guard Properly Structured Synthetic Temporal Dataset

## Purpose
A deterministic, research-safe synthetic dataset for the FAPT-Guard Future Attack Prediction module.

It is designed for the supervised task:

> Given the ordered ATT&CK technique prefix observed up to a temporal cutoff, predict the next ATT&CK technique.

This dataset is **synthetic** and must not be described as real-world validation.

## Generation
- Random seed: 42
- Scenarios: 600
- Event records: 4175
- Next-technique supervised samples: 3575
- Train scenarios: 480
- Validation scenarios: 60
- Test scenarios: 60
- ATT&CK technique classes used: 20
- Scenario-disjoint splits: YES

## Files
- `temporal_evidence_events.csv` — event-level temporal evidence.
- `next_technique_samples.csv` — supervised next-technique prediction examples.
- `scenario_summary.csv` — one row per synthetic incident/scenario.
- `transition_statistics.csv` — observed synthetic technique-to-technique transition counts.
- `dataset_manifest.json` — provenance, schema, generation configuration and SHA-256 hashes.

## Recommended modeling protocol
1. Group records by `scenario_id`.
2. Sort each scenario by `timestamp`.
3. Use `next_technique_samples.csv` as the supervised target table.
4. Keep train/validation/test split at the **scenario level**.
5. Never randomly split individual prefix rows across train and test.
6. Fit preprocessing only on the training scenarios.
7. Tune on validation scenarios.
8. Report final metrics only on the held-out test scenarios.
9. For each prediction, retain the temporal cutoff and supporting event IDs from the corresponding prefix.
10. Do not claim real-world performance from this dataset.

## Suggested baseline
Start with a deterministic transition-frequency or multinomial classifier baseline. Then compare against a stronger sequence model if justified by the project.

Report:
- Accuracy
- Macro Precision
- Macro Recall
- Macro F1
- Weighted F1
- Per-class Precision/Recall/F1
- Support
- Confusion matrix
- Top-k accuracy if implemented
- Calibration metrics only when actually measured

## Important limitation
The event labels and sequences are synthetic and were generated from controlled templates. They are useful for testing the end-to-end prediction pipeline, not for proving operational effectiveness against real adversaries.
