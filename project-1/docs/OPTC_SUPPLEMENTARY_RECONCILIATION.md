# OpTC Supplementary Analysis and Ground-Truth Reconciliation

Status: **READY_FOR_ANALYSIS**, not a validated target dataset. Source: AT03380/optc-labels at commit `64c9f9b2e1a15bf3c2789d89d93dc0724cb0d4fa`. This is third-party research. Neither its `ground` label nor `ground.zip` is official DARPA ground truth.

## What was inspected

README, LICENSE, labels/, tasks/tasks.zip and extracted tasks.json, all supplementary Markdown documents, labeler/matcher/matcher.go (static inspection only), the official PDF/extracted text/timeline, official documentation, importer and mapping source, acquisition helpers and existing manifests. A documentation/ directory does not exist in the cloned repository; documentation is in README and supplementary/.

Five label archives were streamed completely; JSON, ZIP CRC, IDs, timestamps, fields and overlap were checked without extracting executable content or running labeler code. All 60 existing artifact checksums matched before this task.

## Actual archive content

`malicious.zip` has 313,018 JSONL records, 313,018 distinct event UUIDs, 31 hostnames and no duplicate UUIDs within the archive. Its top-level fields are action, actorID, hostname, id, object, objectID, pid, ppid, principal, properties, tid and timestamp. No embedded label, technique, task or scenario keys were found at the top level. Labels are assigned by archive membership and task annotations, not an independent future-technique column. 5,847 records have an empty/missing principal value. Required importer fields are present; this does not prove semantic quality.

The stream is not chronological: 90,772 records move backwards in time relative to the previous record for that host. Sort derived views by normalized timestamp with a deterministic UUID/source tie-breaker; do not reorder originals. UTC range is 2019-09-20T15:53:18.559+00:00 through 2019-09-25T18:35:04.555+00:00.

For the explicit exploratory cutoff 2019-09-23T15:30:00+00:00, SysClient0201 has 1,801 selected records at/before cutoff and 37,532 strictly after it across the entire archive. These are actual selected-record counts, not a complete prefix or a 30-minute horizon count. The PDF's timezone remains unresolved.

## Archive overlap

| Archive pair | Shared UUIDs | Left only | Right only |
|---|---:|---:|---:|
| malicious / admin | 1,480 | 311,538 | 0 |
| malicious / anomaly | 281,327 | 31,691 | 0 |
| malicious / ground | 276,895 | 36,123 | 0 |
| malicious / red | 311,877 | 1,141 | 0 |
| admin / anomaly | 1,143 | 337 | 280,184 |
| admin / ground | 0 | 1,480 | 276,895 |
| admin / red | 339 | 1,141 | 311,538 |
| anomaly / ground | 272,864 | 8,463 | 4,031 |
| anomaly / red | 280,522 | 805 | 31,355 |
| ground / red | 276,895 | 0 | 34,982 |

All four other archives are subsets of malicious.zip. Their union is 313,018 UUIDs. Shared UUIDs have identical raw-line bytes relative to malicious.zip. The 339 admin/red shared UUIDs mean those supplied archive attributions are not disjoint; do not silently resolve attribution.

## Tasks and correlations

931 task records have 931 unique task IDs. There are 851 distinct nonempty event UUIDs; repeated UUID occurrences are not duplicate tasks. 22 tasks lack event ID, hostname, timestamp and labels. 791 have no log narrative. There are 799 distinct nonempty process object IDs and 190 actor IDs. All tasks have process-tree structures; 813 have annotations and 251 have embedded raw context. 795 distinct task event UUIDs occur in malicious.zip.

The label classes cover outcome, source, actor, timeline and granularity. Correlated labels and process trees are post-hoc research annotations; they must not become prefix features. Process identity is not PID alone. Distinguish task object_id semantics from raw objectID: for an event-level flow annotation, task object_id may designate the acting process rather than the flow object.

There are 17 invalid tasks. Thirteen have matching UUIDs in malicious.zip while carrying benign/invalid labels. No same-UUID benign/malicious contradiction between task rows was found, but task/archive membership conflicts remain. Example: task `a5f55e05-fe4f-4724-be65-0c48d39123a5`, event `67b1106b-9833-4b13-9e70-7ff8f6ab81c5`. No disagreement was resolved by guessing.

Static matcher review found that process-object filters aggregate labels without hostname qualification; event filters inherit process-object labels instead of directly copying event-only labels; no explicit invalid-label exclusion was found. It matches actorID/event UUID by regex without a host check. These implementation observations do not prove that the current code revision generated the stored archives. No code was run or changed.

## Ground-truth reconciliation

Full table: `data/external/optc/processed/ground_truth_reconciliation.csv`. Structured equivalent and definitions: `manifests/ground_truth_reconciliation.json`. Each row includes scenario, host, timestamp, task/event IDs, official support, supplementary support, status, disagreement, missing information and provenance.

Comparison is deterministic: match printed narrative timestamp or normalized whole-log text to the extracted official PDF; inspect event UUID membership and task/archive metadata. No fuzzy match is promoted to truth. Results: 139 PARTIAL, 13 DISAGREEMENT, 1 NOT_FOUND, 778 UNKNOWN. No automatic full AGREEMENT is assigned.

PARTIAL supports narrative linkage, not equivalence. DISAGREEMENT identifies observed supplementary inconsistencies, not a proven contradiction with the official account. NOT_FOUND is failure of exact matching, not evidence that an action did not happen. UNKNOWN reflects insufficient narrative information. Official PDF pages contain no eCAR UUIDs or explicit ATT&CK IDs and do not specify timezone. Wall-clock differences in the table deliberately do not assume timezone equivalence. Human action/outcome adjudication and official-raw joins remain missing.

## Can malicious.zip be used?

| Question | Status | Evidence |
|---|---|---|
| A. Benign context | NO | Archives select research-labeled malicious activity. Some task outcomes contradict archive membership; neither these nor admin-labeled events establish a representative benign stream. |
| B. Complete chronological prefixes | NO | Selected event subsets omit all unselected activity. Time ordering cannot recover missing events. |
| C. Future events after cutoffs | PARTIAL | Actual records exist on both sides of the explicit UTC probe cutoff; complete future horizons and PDF clock alignment remain unverified. |
| D. Independent future-technique labels | NO | Outcome/source/actor/timeline/granularity labels exist, but no explicit independent ATT&CK targets were found. |
| E. Scenario-disjoint evaluation | NO | Only related campaign-day annotations and selected events are available. Independent scenario/collection partitions and complete observations are missing. |
| F. Original event identifiers | YES | All archive records contain event UUIDs and preserve eCAR fields. Identity against unavailable official shard bytes has not been independently verified. |
| G. Alignment to official ground truth | PARTIAL | Task narrative timestamps/text can be reconciled in part. Official PDF lacks event UUIDs and timezone; inconsistencies remain unresolved. |
| H. Exploratory preprocessing | YES | Suitable for parser, schema, identifier, timestamp and provenance inspection with the selection bias clearly retained. |
| I. Final real-data validation | NO | Missing full raw telemetry, benign context, reviewed technique targets, independent splits and finalized evaluation protocol. |

The NO answer for benign context means no representative or complete benign background stream exists in this selected archive. It does not claim every included event is truly malicious; the observed conflicts show why that would be unjustified.

## Required official telemetry and availability

The previously saved official Drive listing identifies the 104.6 MB dated shard and 2.07 GB last shard in ecar/evaluation/23Sep19-red/AIA-201-225. The official README supports the endpoint/evaluation layout, but does not specify shard coverage. These remain the appropriate candidates for initial SysClient0201 inspection, not proven sufficient data for scenario-disjoint validation.

Current listing verification returned a corporate content-filtering block. Prior raw requests returned Google quota pages. No raw retries were made and current quota state is UNKNOWN. No alternative official raw-telemetry download source identified in the acquired official documentation. Obtain authorized access first, then wait for quota availability and validate the source bytes.

## Scientific limits

Selection by malicious outcome leaks future knowledge if used to construct model inputs. Archive labels cannot serve simultaneously as features and targets. Related campaigns, shared hosts/processes and duplicated prefixes threaten split independence. Missing official telemetry, unclear PDF clock alignment, invalid correlations, absent technique adjudication and incomplete benign coverage block final validation. All prediction/calibration/conformal metrics remain NOT MEASURED.
