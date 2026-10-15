# Future Attack Prediction: research validation pass

**Subsequent update:** the [uncertainty and evaluation layer](prediction-uncertainty-evaluation.md) now computes full-distribution entropy and attaches held-out calibration diagnostics. It preserves the normalized model described here; its current measurement states supersede the missing-uncertainty statements below.

October 3, 2026. This report supersedes the original synthetic integration results. The existing transition-frequency pipeline, FastAPI routes, SQLite audit storage and UI layout were retained. No production build or real cyber-defense action was performed.

## 1. ATT&CK normalization findings

All **20 original dataset technique IDs** were inspected against the project's pinned Enterprise ATT&CK **19.2** STIX bundle, including inactive objects and `revoked-by` relationships.

- 18 original IDs were active; 2 were revoked.
- No original IDs were marked deprecated; no IDs were absent or syntactically invalid.
- `T1077` and `T1021.002` were overlapping classes connected by an explicit replacement relationship. They now form one active output class.
- Six supplied technique names differed from canonical names, mostly because they included parent-technique prefixes. Derived names now use the pinned catalog.
- The source dataset does **not** specify an ATT&CK release or per-technique object versions. Those source versions remain **NOT AVAILABLE**. Their exact historical version mismatch cannot be inferred; incompatibility of the two revoked IDs with the active catalog is established.
- Canonical object versions, original names, status flags, replacement IDs and relationship IDs are recorded for every source technique in the model report's `dataset.normalization.techniques`.
- Distinct active techniques are not merged merely because their behaviors may overlap.

Pinned catalog SHA-256:

`dc1639caa5501d720e280cf1cbd8fbe009884a0c9b3e6e9ed9d0c25166c3d8f4`

| Original ID | Pinned status | Derived training/output ID | Evidence |
|---|---|---|---|
| T1077 | Revoked | **T1021.002** | `relationship--bcdb80d6-8ae4-4283-8abd-e933b498be13` |
| T1021.002 | Active | T1021.002 | Canonical SMB/Windows Admin Shares object |
| T1562.001 | Revoked | **T1685** | `relationship--30d508e7-2562-40aa-8ca2-9534dc411e22` |

The remaining active IDs are retained: T1003.001, T1016.001, T1027, T1041, T1053.005, T1057, T1059.001, T1059.003, T1071.001, T1083, T1087.001, T1105, T1204.002, T1486, T1547.001, T1555.003 and T1566.001.

Tactic normalization also corrects `T1027`: Defense Evasion → **Stealth** (163 events), and `T1562.001` → `T1685`: Defense Evasion → **Defense Impairment** (55 events). Multiple-tactic techniques retain the supplied tactic when it is valid in the catalog. Ambiguous corrections are rejected. Original technique/tactic fields are preserved in the derived records.

## 2. Final dataset and preprocessing

**FAPT-Guard Synthetic Temporal ATT&CK Sequence Dataset v1.0.1** remains the source dataset. Its six original archive files and verified hashes are unchanged. No new source dataset version is invented.

Preprocessing version: `attack-stix-replacements-v1`.

- 600 scenarios, 4,175 events, 3,575 supervised samples
- Supplied scenario split: 480 train / 60 validation / 60 test
- Sample split: 2,855 train / 360 validation / 360 test
- No scenario or incident crosses splits; no random repartitioning
- 19 normalized event classes, 18 normalized target classes, 16 trained target classes
- Every target starts with the supplied `target_next_technique_id` and is transformed by the documented catalog mapping. No target is inferred from the model.

The training command regenerates `data/models/synthetic_temporal_normalized.json`, containing normalized events, supervised rows, original labels, input/target event IDs, source manifest hash and normalization audit. The same transformed labels are used for fitting, evaluation and output names. The provided whole-dataset transition statistics remain excluded from fitting.

Normalized data SHA-256:

`b94d0d9373e65b9c9adbe141eea12dbaa4411c1724c5f7f4b95fac4c3a1c9122`

Source manifest SHA-256:

`9ebef685b77a26e91777259e2b6e302420b7314bb8a9c16ad98c1e2970e90352`

## 3. Final model and provenance

Model: **transition_frequency**.

Algorithm: maximum-likelihood next-technique counts conditioned on mapped suffixes of length 3, then 2, then 1; backoff to the training prior when no suffix matches. Training rows alone provide counts and matching sample IDs. No smoothing, manual probability adjustment or calibrated-probability claim is made.

The existing Random Forest comparison was also retrained. The selection rule remains highest validation Macro-F1, ties favoring transition frequency. Validation Macro-F1 was **0.165005** for transition frequency and **0.126050** for Random Forest. Test outcomes did not select the model.

Training timestamp: `2026-10-03T07:43:37.333323+00:00`.

Model version / artifact SHA-256:

`65e8aaf54884efe0ca75de124d734890a600831d16435ddc062fd3fa2dc67139`

The model record stores model name/version, algorithm, dataset/name/version, training/validation/test scenario counts, timestamp, random seed, feature definition and target definition. Seed 42 applies to the Random Forest comparison; transition counts are deterministic without randomness. It also stores source/derived hashes, catalog hash, normalization version, validation selection rule and test prediction hash. Loading rejects stale normalization, a changed catalog, changed data/model bytes or inactive model classes.

Only technique suffix features influence the selected transition model. Additional event/time/source features are available to the Random Forest comparison and are identified separately in `feature_definition`.

## 4. Actual held-out synthetic test results

The saved model was rerun on all **360 test prefixes from 60 held-out scenarios**. Tests compare its probabilities with the exported test rows and independently reconstruct metrics and the confusion matrix. Training results are not presented as test performance.

| Test metric | Value |
|---|---:|
| Accuracy | **0.350000** (126/360) |
| Macro precision | 0.106181 |
| Macro recall | 0.183007 |
| Macro F1 | **0.116613** |
| Weighted F1 | **0.286661** |
| Top-3 accuracy | 0.516667 |
| Top-5 accuracy | 0.691667 |
| Multiclass Brier diagnostic | 0.806334 |
| ECE diagnostic, ten bins | 0.297975 |

Macro metrics use the union of trained and actual test classes (17 labels), including zero-support classes, with zero division set to zero. The normalized class universe changed; this accounts for the Macro-F1 change while test accuracy and weighted F1 remained unchanged. Top-k rankings can include zero-probability classes; these are ranking metrics, not calibrated coverage.

### Confusion matrix and per-class metrics

- [Confusion matrix CSV](synthetic-temporal-confusion-matrix.csv): true technique rows, support column, predicted technique columns; total support 360
- `data/models/synthetic_temporal.json` → `evaluation.test.model.confusion_matrix`, `class_order`, `per_class`
- `data/models/synthetic_temporal_test_predictions.csv`: all test predictions, probability vectors, true labels, cutoffs and supporting IDs
- Research → **Future Attack Prediction — Synthetic Benchmark** → **TEST evaluation**

The matrix and per-class precision/recall/F1/support come from actual predictions, including misses on unseen target classes.

## 5. INC-00001 demonstration and traceability

**Synthetic-trained research model applied to simulated incident. NOT REAL-WORLD VALIDATION.**

Current ATT&CK assessment: **T1003.001 — LSASS Memory; Status: CANDIDATE**. No mapping rule or confidence was strengthened. Dashboard headings, prediction card and explanation show the status explicitly.

Cutoff: `2026-09-25T10:05:02`. The incident retains its timezone-unspecified fixture clock. All six supporting events are at or before this cutoff:

`EV-00001`, `EV-00002`, `EV-00003`, `EV-00004`, `EV-00005`, `EV-00006`.

Observed mapped technique prefix: **T1059.001 → T1003.001**. Four input events have no technique mapping and remain explicitly unmapped. No extra technique labels are invented.

The longer mapped suffix is unseen in training, so the model backs off to **T1003.001**. There are **153 matching training samples**:

| Next technique | Training count | Model output probability |
|---|---:|---:|
| **T1021.002 — SMB/Windows Admin Shares** | **142** | **142/153 = 0.9281045751633987** |
| **T1041 — Exfiltration Over C2 Channel** | **11** | **11/153 = 0.0718954248366013** |

All other trained classes have probability zero; the complete vector sums to one. These values were computed by the retrained model. They were not changed in frontend code or combined at display time.

Stored prediction ID: `deceefd1-3ecc-4ce4-ba0e-04369f7ee9c2`.

Stored timestamp: `2026-10-03T07:44:45.463544+00:00`.

The prediction links to the model hash, source and derived data hashes, cutoff, exact observed records and supporting IDs. Its transition evidence includes the actual training sample IDs used for the counts. Tests look up those IDs in the normalized samples and verify every one belongs to the training split and reproduces the probability calculation. Mutating events after cutoff or injecting target fields does not change the prefix prediction.

The explanation dialog shows predicted technique, model output probability, current assessment/status, cutoff, model/version, training dataset/version, evidence IDs, observed technique prefix and actual transition evidence. It states: **“Feature-level explanation unavailable for this baseline model.”** No feature importance is invented.

Research separates **TRAINING DATA**, **VALIDATION DATA**, **HELD-OUT TEST DATA** and **INC-00001 DEMONSTRATION**. The demonstration has no measured future ground truth and is not counted in test metrics.

## 6. Calibration and remaining limitations

- Probability calibration: **NOT MEASURED**. No calibration fitting or calibrated-probability claim. Brier/ECE are separately labelled held-out diagnostics.
- Incident uncertainty: **NOT MEASURED**.
- Coverage: **NOT MEASURED**.
- Real-world validation: **NO**. This is controlled synthetic evaluation with low held-out performance.
- Validation has unseen normalized target `T1685`; test has unseen target `T1547.001`. They remain in evaluation and count as misses.
- This is a revised evaluation on the existing test partition, not a new independently collected test dataset. Normalization follows the catalog, not test-score optimization.
- Supplied splits hold out templates, but some short feature patterns repeat. They do not establish real-world generalization.
- The source ATT&CK release and source object versions are unavailable; the pinned catalog and derived object versions are recorded.
- A candidate evidence mapping can affect the model output. The probabilities do not confirm the current technique or guarantee the next event.
- File hashes and local audit chaining provide integrity checks, not external provenance authentication.
- No real cyber-defense action is executed. Prevention probabilities remain advisory; preservation and response execution remain safe simulations.

## 7. Validation and files changed

32 backend tests and all 12 browser scenarios passed. After final tactic metadata corrections, the eight synthetic pipeline tests and three prediction browser tests passed again. TypeScript and ESLint passed. Browser checks capture page/console errors; successful final prediction and Research checks reported none. Existing navigation, mobile preservation, simulation, hash verification, audit and failure-feedback tests passed.

Changed implementation:

- `backend/app/attack_normalization.py`: full pinned-catalog audit, explicit replacement chains, canonical names/tactics, original labels and derived counts
- `backend/app/synthetic_temporal.py`: normalized training data, retraining/evaluation, full provenance, active-ID checks and transition support explanations
- `backend/app/services/future_prediction_service.py`: separately labelled Research incident demonstration using the existing workflow
- `backend/tests/test_synthetic_temporal.py`: normalization, provenance, cutoff, transition-count reconstruction and actual held-out-model reevaluation
- `frontend/src/components/research-analysis.tsx`: probability wording, candidate status and explanation fields
- `frontend/src/components/future-evaluation.tsx`: synthetic benchmark and train/validation/test/demo distinctions
- `frontend/src/app/page.tsx`, `frontend/src/components/incident-console.tsx`: consistent current assessment/status
- `frontend/tests/future-prediction.spec.ts`: normalized output, status, explanation and Research checks
- Generated model/report/normalized dataset/test predictions in `data/models/`, local SQLite audit records and this report/matrix

Reproduction, from `backend/`:

```powershell
..\.venv\Scripts\python.exe -m app.datasets train-temporal
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

From `frontend/` in separate terminals:

```powershell
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
npx.cmd tsc --noEmit
npm.cmd run lint
npx.cmd playwright test
```

The application remains running at http://127.0.0.1:3000 and the API at http://127.0.0.1:8001.
