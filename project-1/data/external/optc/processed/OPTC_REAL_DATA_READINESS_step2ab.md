# OpTC Real-Data Readiness

Acquisition inspected 2026-10-03T17:08:33.984767+00:00. **PARTIAL: official documentation and research labels acquired; official raw telemetry unavailable because of Google Drive quota. Real future-technique evaluation is not ready.**

Only `data/external/optc/` and this report were created. Application code, frontend, models, database and schema were not changed. No training, import, simulation or host response action was run.

## Official source

[FiveDirections/OpTC-data](https://github.com/FiveDirections/OpTC-data) releases collected endpoint telemetry from a controlled red-team exercise. This is not a claim of production deployment validation. The release is public domain, Distribution A, and carries no accuracy warranty. Local copies of README, ecar.md and errata.md are under `data/external/optc/official/documentation/`.

Initial inspection found no OpTC telemetry, PDF, supplementary labels, dedicated manifest or `data/optc.sqlite3`. A historical checksum entry existed for an absent PDF; the new PDF matches it. See `manifests/project_inspection.json` for importer review and inspected paths.

## Ground truth

Official PDF: `data/external/optc/official/ground_truth/OpTCRedTeamGroundTruth.pdf`.
SHA-256: `5986d23b81169221a491f7a8302fce140b12638ef4cf9b3a894ed3cb2fad9567`. Size: 453,244 bytes.

PDF signature, EOF marker and seven-page parsing succeeded. Text is in `official/ground_truth/ground_truth_text.txt`; 102 timestamped log entries with page references are in `processed/official_timeline.json`. These are derived extractions of the official narrative. Some punctuation has replacement characters; consult the PDF for exact typography. No event text was invented.

No PDF extractor was installed. With permission, pypdf 6.19.0 was installed only in `downloads/pdf_tools/`; application dependencies were not changed. Raw source copies were never overwritten.

## Supplementary labels

[AT03380/optc-labels](https://github.com/AT03380/optc-labels), commit `64c9f9b2e1a15bf3c2789d89d93dc0724cb0d4fa`, was cloned through normal HTTPS. It is **third-party research, not official DARPA ground truth**. All 24 tracked working-tree files were acquired, including README, LICENSE, five label archives, tasks/tasks.zip, supplementary documentation and source code. No downloaded labeler code was executed. Git transport succeeded; no repository ZIP endpoint was used.

The README and how-to document say `malicious.zip` is the broad event selection and the other label archives are overlapping subsets. Do not sum their counts as independent observations. The archive membership relationship has not been exhaustively compared across all files.

`tasks/tasks.zip` contains `tasks.json` (136,569,900 uncompressed bytes); an exact extracted copy is in `processed/tasks.json`. It has 931 task records, 851 distinct nonempty event UUIDs, 58 repeated nonempty UUID occurrences, and 22 records without event IDs or hostnames. Counts concern tasks, not independent events. Its 17 `invalid` tasks must be excluded from matching.

Labels distinguish outcome (malicious/benign), source (ground/correlated/anomaly/invalid), actor (red/admin), timeline (prior/day1/day2/day3), and granularity (process/event). Join event-level annotations by event UUID; process-level annotations require the documented object/process relationship. A `ground` label remains a third-party annotation. The repository's benign-by-complement convention is not independent proof that unannotated activity is benign.

Useful integration resources: official PDF, supplementary/ground-truth.md, tasks/tasks.zip, labels/malicious.zip, labels/ground.zip, supplementary/how-to.md, labels.md and errata.md. Retained source code and image are not required for this experiment. README assigns AGPL-3.0 to original code, CC BY-SA 4.0 to supplementary materials, and public domain to labels/tasks and reproduced OpTC records.

## Raw files acquired

**Official raw telemetry: 0 files, 0 bytes. Event count: NOT AVAILABLE.** No HTML response was accepted as gzip.

The supplementary repository does contain selected raw eCAR event records; they are catalogued separately as `supplementary_research`, not as direct official raw downloads:

| Archive | JSONL records | Hosts | Compressed bytes |
|---|---:|---:|---:|
| admin.zip | 1,480 | 4 | 137,492 |
| anomaly.zip | 281,327 | 30 | 50,929,269 |
| ground.zip | 276,895 | 29 | 50,427,842 |
| malicious.zip | 313,018 | 31 | 52,964,839 |
| red.zip | 311,877 | 29 | 52,855,002 |

All five archives were read completely to EOF, validating ZIP CRC and every JSONL record. No malformed records, duplicate event IDs within an archive, missing event IDs, missing hostnames, invalid timestamps or missing required importer fields were found. This establishes structural readability only, not correctness of annotations. Detailed host counts and event types are in `processed/supplementary_labels_inspection.json`.

## Raw files unavailable

The first pilot selects Day 1, SysClient0201, retaining the full host-group shards. Both are in official `ecar/evaluation/23Sep19-red/AIA-201-225/`:

- `AIA-201-225.ecar-2019-12-08T11-05-10.046.json.gz` — Drive ID `1pJLxJsDV8sngiedbfVajMetczIgM3PQd`, listed 104.6 MB; `GOOGLE_DRIVE_QUOTA_EXCEEDED`.
- `AIA-201-225.ecar-last.json.gz` — Drive ID `1HFSyvmgH0jvdnnnTdKfWRjZYOrLWoIkv`, listed 2.07 GB; `GOOGLE_DRIVE_QUOTA_EXCEEDED`.

Both were attempted through normal public Drive confirmation forms and returned quota errors. File names contain post-processing dates and cannot establish event time coverage. No gzip validity, official event count, official duplicate count or actual official time range is available.

## File hashes

`data/external/optc/manifests/sha256_manifest.json` records SHA-256 and byte length of acquired sources and derived inspection files. It excludes mutable `.git` internals and isolated PDF tool binaries. Source hashes were recalculated and checked after inspection. No upstream authenticated hash/signature is claimed; the historical PDF checksum is a local consistency check.

| Official file | Bytes | SHA-256 |
|---|---:|---|
| `OpTCRedTeamGroundTruth.pdf` | 453,244 | `5986d23b81169221a491f7a8302fce140b12638ef4cf9b3a894ed3cb2fad9567` |
| `README.md` | 4,681 | `bbbeca5d5a861ffc765a6d42ddd19cb84acb93861226b4b93887bb950e121074` |
| `ecar.md` | 2,336 | `1df4539c49963cc49b783580033fe1ec68bbae68434abf29da83c47b5d26d16b` |
| `errata.md` | 722 | `4044970eae0db4f67055fa2c0e5bb99824628c13d991fcef01dcc5ec06e8d062` |

Dataset source-file total: 28 files, 220,492,676 bytes, excluding .git, tools and derived copies. Per-file source URLs, timestamps and provenance are in `optc_manifest.json`.

## Dataset time range

Complete official raw time range: **NOT AVAILABLE**. Official narrative covers September 23–25, 2019; its printed clock times have no explicit timezone. Day 2 includes overnight events on September 25.

The inspected supplementary malicious event subset spans `2019-09-20T15:53:18.559000+00:00` through `2019-09-25T18:35:04.555000+00:00` (UTC conversion of actual event timestamps). This range belongs to the selected subset, not the full dataset. Telemetry includes explicit -04:00 offsets; matching the PDF clock to that offset remains a documented alignment hypothesis until reviewed.

## Host coverage

Official raw hosts: **NOT AVAILABLE**. The broad supplementary malicious subset has 31 observed hostnames; `SysClient0201.systemia.com` contributes 39,333 records. Full host lists are in the manifests. PDF host references describe campaign scope and do not prove that every host was recorded.

The supplementary annotated narrative states that DC1 logs are absent and identifies narrative actions whose corresponding raw event was not found. This is a third-party finding, not newly verified against the complete official release.

## Event counts

Complete official events: **NOT AVAILABLE**. Downloaded official bytes: 0. Supplementary `malicious.zip`: 313,018 records / 313,018 unique event IDs. Other archive counts overlap. No global independent event total is fabricated.

## Attack scenarios

- Day 1, “Plain PowerShell Empire”: September 23. Initial access on Sysclient0201; credential collection, registry persistence and discovery; WMI pivots through Sysclient0402, Sysclient0660 and DC1; later workstation spread. Official log spans 11:23:29–15:30:00, timezone unspecified.
- Day 2, “Custom Powershell Empire”: September 24, with overnight activity into September 25. Phishing documents, modified C2, domain enumeration, attempted and successful privilege changes, WMI persistence, RDP tunneling and file exfiltration.
- Day 3, “Malicious Upgrade”: September 25. Malicious update on Sysclient0051 and Sysclient0351, Meterpreter, discovery, process migration, credential collection, autorun persistence and timestamp modification. Official log spans 10:29:42–14:24:03, timezone unspecified.

Exact printed timestamps, host spellings and narrative actions are retained in the extracted text/timeline. Failed attempts must not be relabeled as successful outcomes. The PDF contains PIDs and agent IDs but no eCAR event UUIDs or explicit ATT&CK technique IDs.

## Ground-truth availability

**PARTIAL.** Official narrative and independent third-party event annotations are available. No official machine-readable future-technique target table exists in the acquired material. `ground_truth_manifest.json` distinguishes OFFICIAL_SOURCE, SUPPLEMENTARY_SOURCE, DERIVED and UNKNOWN. Review task/event joins, label granularity, missing events and time alignment before assigning technique targets. Do not use FAPT-Guard's own mapping rules or predictions as evaluation truth.

## Future-event availability

**PARTIAL.** Supplementary labeled events include timestamps after candidate cutoffs, but selecting records by their eventual malicious label can leak future knowledge and omits benign context. Complete prefix and future windows require the official shards. Their actual time coverage cannot yet be confirmed.

## Potential prediction cutoffs

Planning candidate only: Day 1 after the initial elevated agent check-in at printed 11:26:38 and before the 11:33:14 credential-collection action; for example printed 11:30:00. Preserve at least a lead-in before 11:23:29 and later activity through the chosen forecast horizon. A provisional inspection window is printed 10:30–15:30 on September 23; neither availability nor timezone alignment is verified. Do not promote this into a timezone-aware evaluation cutoff until raw coverage and clock alignment are reviewed.

Use endpoint eCAR for the first host-only pilot. Preserve PROCESS, FILE, REGISTRY, FLOW, MODULE, THREAD and SHELL context as available rather than selecting only a malicious event. ecar-bro/Bro are optional for a later experiment needing endpoint/network correlation. The short subset is unsuitable as the primary source because documentation identifies missing data there.

## Required preprocessing

1. Acquire the two official shards without modifying their bytes; verify SHA-256, full gzip CRC/EOF, JSONL, timestamps, UUIDs, hosts and duplicate IDs.
2. Check actual coverage around SysClient0201 and the candidate cutoff; acquire adjacent/benign shards only if needed. Folder/file naming is not proof of coverage.
3. Retain exact source line references and hash provenance, normalize timezone-aware timestamps and document clock alignment. Preserve unknown actor/object identifiers and distinguish missing information from observed absence.
4. Join third-party task annotations by event UUID/process object with granularity honored; exclude invalid correlations and retain attempted/failed actions. No direct task-array import.
5. Create independently reviewed ATT&CK mappings with evidence, version and uncertainty. Keep target labels and label-known times separate from observed input features.
6. Define forecast horizon and censoring rules; split independent campaigns/collections without shared-host or scenario leakage. The existing host/day grouping is not sufficient by itself.
7. A later authorized integration must resolve path/schema compatibility. The API currently accepts gzip/plain JSONL only directly in `data/optc/`; these new source paths are deliberately not imported. CLI supports explicit paths. Existing importer defaults to a 100,000-record cap and deduplicates source-line bytes rather than event UUIDs.

No preprocessing that changes source records, database import, model training or application integration was performed. The only extraction beyond PDF text is an exact tasks.json copy and inspection metadata.

## Data-quality issues

The label archives pass structural checks, but analyst labels can be incomplete or noisy. Tasks contain repeated/missing identifiers. Process-level label propagation can overlabel unrelated activity, especially long-running services. Supplementary errata also describes invalid parent-child correlations and inconsistent conhost.exe labeling. No acquired source provides an independently reviewed ATT&CK target list. All prediction metrics, uncertainty and calibration values are **NOT MEASURED**.

## OpTC errata

Official errata identifies duplicate process objects, missing executable hashes for module loads, zero acuity_level on FLOW OPEN records, and inconsistent device/drive path representations. Keep these as known limitations; structural JSON validity does not resolve them. Local errata.md is preserved verbatim.

## Corporate/network download limitations

GitHub and public Drive listings were accessible. Initial sandbox HTTPS returned `ConnectionRefusedError(10061)`; git reported inability to connect via `127.0.0.1`. Normal requests succeeded after tool sandbox permission. There is **no observed evidence of a corporate firewall block**, so no corporate-block status is asserted.

Both official raw downloads returned HTTP 200 HTML titled **Google Drive - Quota exceeded**, with the message “Too many users have viewed or downloaded this file recently.” The first downloader reported `RuntimeError('Download returned HTML instead of gzip')`; a diagnostic confirmed the quota page. The second reported `GOOGLE_DRIVE_QUOTA_EXCEEDED`. This is a service quota restriction. No mirror, authentication bypass or quota workaround was used. Saved HTML and `manifests/network_access.json` preserve the exact failures. Browser-tool PDF reading separately failed with `(400) Unsupported content-type: application/octet-stream`; local extraction succeeded.

Disk free before source acquisition was 391,444,471,808 bytes; before planned raw downloads it was 390,932,541,440 bytes. Drive displayed 104.6 MB and 2.07 GB; exact byte lengths are **NOT AVAILABLE**. The download plan caps them at 110,000,000 and 2,300,000,000 bytes. A conservative, unmeasured 50× expansion allowance is 120,500,000,000 bytes; inspection would stream without writing decompressed files. Current free disk: 390,925,840,384 bytes. No >20 GB file was attempted.

## What remains to be acquired

The two named official eCAR shards above are the required pilot downloads. Wait for Google quota to reset or obtain owner-approved access through the official source; do not work around the quota. The required filenames and IDs are in `missing_required_files.json`. If their content lacks lead-in/future coverage, inspect the adjacent official benign/evaluation listings before choosing further files. Exact additional filenames and extracted sizes are **NOT AVAILABLE**, not invented.

Bro/ecar-bro and other campaign host groups are deferred, not silently assumed acquired. The pilot alone will not establish a sufficient independent train/calibration/test population.

## Whether real future-technique evaluation is currently possible

**NO. Preparation is partial, not completed real-world validation.**

| Check | Status | Evidence |
|---|---|---|
| A. Chronological observed prefixes | PARTIAL | Timestamped supplementary records can be ordered, but label-selected records omit benign context; complete official prefixes cannot yet be built. |
| B. Events after a prediction cutoff | PARTIAL | Supplementary events span several days and include later records; completeness and official-raw coverage are unverified. |
| C. Independent actual future attack behavior | PARTIAL | Official narrative and third-party annotations exist independently of the predictor; raw alignment and action outcomes require review. |
| D. ATT&CK mapping independent of predictor output | PARTIAL | Narrative behavior supports later analyst mapping, but no explicit technique IDs were found in the PDF or tasks and no reviewed mapping is ready. |
| E. Train/validation/test scenario separation | NO | A complete pilot is unavailable; three related campaign days do not establish sufficient independent scenarios. Host/day groups are not independent incidents. |
| F. Top-1/3/5, MRR, Macro-F1, Brier, ECE | NO | No aligned independent technique targets, declared label space, real-data predictions or held-out split. |
| G. Measure uncertainty | NO | No real-data predictive distribution or independent uncertainty validation has been produced. |
| H. Measure calibration | NO | No untouched calibration/test partitions and aligned probability predictions exist for real telemetry. |
| I. Real-data holdout evaluation | NO | Acquisition is partial and no leakage-controlled real holdout has been established. |

Next step: retry the two official downloads after the quota restriction clears, then validate coverage and independently reconcile the first campaign's labels and clocks. Application integration and training require a separate task after these prerequisites are satisfied.
