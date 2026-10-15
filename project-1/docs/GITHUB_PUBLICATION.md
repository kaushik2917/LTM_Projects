# GitHub publication scope

This repository publishes the current application source, synthetic research datasets,
existing evaluation metadata, tests, documentation and OpTC preparation artifacts.
Publication does not change application behavior, retrain models or establish real-world validation.

## Files intentionally retained only on the development computer

- Official OpTC raw telemetry: excluded whether present now or acquired later.
- `data/external/optc/processed/tasks.json`: 136,569,900 bytes, above GitHub's normal 100 MiB file limit.
- `data/external/optc/supplementary/optc-labels/`: the independent third-party Git checkout, including approximately 220 MB of label/task archives and supporting files. It is not embedded as an accidental Git submodule.
- `data/external/optc/downloads/`: saved network HTML/responses, cookies, corporate filtering diagnostics and isolated PDF tooling. Only the acquisition Python helper is published.
- Local `.env` files, workflow SQLite databases, logs, dependency/build directories and trained `.joblib` binaries, according to the existing ignore policy. Model metadata and recorded research results remain included.
- The downloaded ATT&CK STIX bundle remains excluded under the existing policy; its source/version and checksum information remain available.

No excluded local file is deleted. The whole `data/` directory is not ignored.
The example environment file contains only a localhost API URL and remains tracked.

## Reproducing the acquisition context

Official PDF and documentation copies are included with their existing provenance.
Supplementary material comes from https://github.com/AT03380/optc-labels at commit
`64c9f9b2e1a15bf3c2789d89d93dc0724cb0d4fa`. Obtain that independent repository
through normal authorized GitHub access if needed; its README documents licensing.
The acquired labels are third-party research, not official DARPA ground truth.

OpTC manifests and SHA-256 records describe the original local acquisition, including
files intentionally not uploaded. A listed file/hash does not mean the file is bundled
in this Git repository. Inspection scripts require those local source files; a fresh
clone alone cannot pass the full acquisition preparation check. Acquisition logs and
historical hash records remain research provenance, not a guarantee of remote completeness.

See `OPTC_REAL_DATA_READINESS.md`, `OPTC_IMPORT_PLAN.md`,
`OPTC_FUTURE_PREDICTION_PROTOCOL.md`, `OPTC_LEAKAGE_CONTROL.md` and
`OPTC_SUPPLEMENTARY_RECONCILIATION.md` for current scientific limitations.
The current corporate content-filtering block and prior Google quota restriction
must be respected; do not use mirrors or bypass controls.

Git attributes preserve bytes for included datasets and OpTC artifacts so line-ending
conversion does not invalidate their recorded source hashes. No dataset is regenerated
as part of publication. Existing model binaries and local database state are not included;
consult the project setup/reproduction documentation before running a fresh clone.
