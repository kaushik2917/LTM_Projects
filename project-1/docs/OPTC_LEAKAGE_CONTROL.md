# OpTC Leakage Control

Status: planning and standalone preparation checks only. No application pipeline was changed and no model was trained.

## Controls required before training

| Risk | Required control | Evidence / rejection rule |
|---|---|---|
| Future events in prefix | Strict timestamp filter | Every prefix record must fall in [cutoff−window, cutoff]. Future targets must fall in (cutoff, cutoff+horizon]. |
| Delayed observations | Separate availability clock | Online claims require observed-at ≤ cutoff; absent clocks restrict the estimand to declared offline event-time replay. |
| Labels in features | Feature allowlist and separate storage | Reject labels, targets, task IDs, campaign IDs, archive names and annotation text in feature inputs. |
| Post-hoc process context | Rebuild graph from prefix only | No future children, termination times or all-run correlations in a prefix graph. |
| Scenario/campaign reuse | Connected group split | Collection/campaign/linked episode component cannot appear in multiple partitions. |
| Duplicate events/sequences | Source, UUID and canonical-content comparisons | Cross-partition duplicates or conflicting UUID payloads require quarantine/review. Different formatting is not a new example. |
| Future clock features | Event-time derivation only | Absolute future times, next-event gaps and time-to-target are forbidden features. |
| Ground truth available during prediction | Separate labels and prediction execution | Freeze predictions before evaluator can access future annotations. Ground-truth knowledge time is not event observation time. |
| Supplementary labels as features and targets | Analysis-only supplementary provenance | Archive selection, malicious membership and propagation annotations cannot become prefix evidence or definitive targets. |
| Test-driven preprocessing | Fit only on training groups | Vocabulary, imputers, scalers, feature selection and class-prior estimation must be frozen before test. |
| Calibration leakage | Disjoint model-selection/calibration/test groups | Probability and conformal calibration cannot consume test labels. |
| Outcome-selected cutoffs | Fixed grid independent of later labels | Do not select only cutoffs preceding known malicious behavior. Include reviewed complete NO_EVENT windows. |
| Missing follow-up treated as benign | Explicit censoring | Unobserved or unreconciled future windows remain UNKNOWN; report exclusions. |
| Host/PID shortcuts | Identity used for linkage, not default features | Reused PIDs, task/campaign identifiers and absolute host identities must not encode the split or target. |

## Implemented preparation checker

`data/external/optc/processed/check_preparation.py` is isolated from application imports and databases. It verifies source hashes, required raw-file presence and declared readiness prerequisites, then writes an inspection result. It performs no download, import, feature extraction or training. Missing raw files, unresolved annotations, clock alignment, groups or protocol approval yield BLOCKED rather than invented pass results.

Run from the workspace root:

```powershell
.\.venv\Scripts\python.exe -B data/external/optc/processed/check_preparation.py
```

The checker covers preparation gates only. It is not an implemented event-level leakage validator and cannot certify a future feature pipeline. Before a later integration, implement and test event-boundary, forbidden-feature, cross-partition identity and canonical-sequence checks against real derived samples. No samples exist yet, so these controls are NOT RUN, not PASS.

## Planned adversarial checks for the later pipeline

1. Add a known post-cutoff event to a prefix and ensure rejection.
2. Insert a target/annotation field into feature input and ensure rejection.
3. Put a campaign, duplicated UUID or canonical sequence in two partitions and ensure rejection.
4. Give a prefix an observed-at timestamp after cutoff; reject online use.
5. Alter source bytes or use conflicting payloads for the same UUID; quarantine.
6. Supply an incomplete future window; require censored/unknown status.
7. Attempt to use test labels for model selection or calibration; reject partition access.

These are planned tests, not fabricated OpTC records or completed validation. Report the actual checks and limitations with any later experiment.
