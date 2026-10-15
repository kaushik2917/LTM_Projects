"""Create acquisition manifests and documentation from inspected local sources."""
import datetime
import hashlib
import json
import pathlib
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[2]
REPO = ROOT / 'supplementary/optc-labels'
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()
COMMIT = '64c9f9b2e1a15bf3c2789d89d93dc0724cb0d4fa'
def read(path): return json.loads((ROOT / path).read_text(encoding='utf8'))
def relative(path): return path.relative_to(WORKSPACE).as_posix()
def digest(path):
    with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def save(path, value):
    with (ROOT / path).open('x', encoding='utf8') as f: json.dump(value, f, indent=2, ensure_ascii=False)
def field(value, provenance, evidence=None):
    return {'value':value, 'provenance':provenance, 'evidence':evidence}

official = read('downloads/official_acquisition_retry.json')
labels = read('processed/supplementary_labels_inspection.json')
tasks = read('processed/supplementary_tasks_inspection.json')
timeline = read('processed/official_timeline.json')
plan = read('manifests/acquisition_plan.json')
text = (ROOT/'official/ground_truth/ground_truth_text.txt').read_text(encoding='utf8')
source_files=[]
for item in official:
    p=WORKSPACE/item['path']
    assert digest(p)==item['sha256']
    source_files.append(dict(item, source_type='official', contains_events=False))
for p in sorted(REPO.rglob('*')):
    if not p.is_file() or '.git' in p.relative_to(REPO).parts: continue
    rp=p.relative_to(REPO).as_posix()
    source_files.append({'path':relative(p),'url':f'https://github.com/AT03380/optc-labels/blob/{COMMIT}/{rp}',
        'source_type':'supplementary_research','source_repository':'AT03380/optc-labels','git_commit':COMMIT,
        'size_bytes':p.stat().st_size,'sha256':digest(p),
        'downloaded_at':datetime.datetime.fromtimestamp(p.stat().st_mtime,datetime.timezone.utc).isoformat(),
        'timestamp_basis':'Local clone checkout file modification time; exact per-file network time not measured',
        'contains_events':rp.startswith('labels/') or rp=='tasks/tasks.zip'})

errors = [
 {'scope':'Sandbox official HTTPS attempts','error':"URLError(ConnectionRefusedError(10061, 'No connection could be made because the target machine actively refused it', None, 10061, None))",'resolution':'Normal HTTPS succeeded after tool sandbox approval; no network policy bypass.'},
 {'scope':'Sandbox git clone','error':"fatal: unable to access 'https://github.com/AT03380/optc-labels.git/': Failed to connect to github.com port 443 via 127.0.0.1 after 2041 ms: Could not connect to server",'resolution':'Normal git clone succeeded after tool sandbox approval.'},
 {'scope':'Web PDF reader','error':'(400) Unsupported content-type: application/octet-stream','resolution':'Downloaded original PDF through HTTPS; extracted locally with pypdf.'},
 {'scope':'First official shard','error':"RuntimeError('Download returned HTML instead of gzip')",'diagnosis':'Google Drive - Quota exceeded; HTTP 200 text/html, not telemetry. Saved download diagnostic confirms quota.'},
 {'scope':'Second official shard','error':"RuntimeError('GOOGLE_DRIVE_QUOTA_EXCEEDED: Too many users have viewed or downloaded this file recently.')",'diagnosis':'Google Drive - Quota exceeded; failure HTML retained.'},
]
save('manifests/network_access.json',{'checked_at':NOW,'github_accessible':True,'google_drive_listing_accessible':True,
    'corporate_network_block_evidence':False,'status':'GOOGLE_DRIVE_QUOTA_EXCEEDED',
    'errors':errors,'restrictions_bypassed':False,'unauthorized_mirrors_used':False})

missing=[]
for item in plan['files']:
    record=read('downloads/'+item['drive_id']+'_download.json')
    missing.append(dict(item, status='NOT_ACQUIRED',reason='GOOGLE_DRIVE_QUOTA_EXCEEDED',size_bytes=None,
        contains_events=None,event_count=None,time_start=None,time_end=None,hosts=[],sha256=None,
        required_for_experiment=True,reason_required=plan['reason']))
save('manifests/missing_required_files.json',{'files':missing,'selection_scope':'First single-host Day 1 pilot, pending actual shard coverage verification',
    'conditional_requirements':['Earlier benign or adjacent evaluation shards if the two selected files lack sufficient pre-attack/post-cutoff coverage; exact filenames NOT AVAILABLE until content inspection.',
        'Additional host groups for Day 1 pivots and independent campaigns for holdout design are deferred; they are not required for the first single-host inspection.'],
    'not_required_for_initial_pilot':['ecar-bro enrichment','bro network files','short incomplete-data subset']})

catalog=[]
for rec in labels:
    path=REPO/'labels'/rec['file_name']
    src=next(s for s in source_files if s['path']==relative(path))
    catalog.append(dict(rec,relative_path=relative(path),source=src['url'],downloaded_at=src['downloaded_at'],
        download_timestamp_basis=src['timestamp_basis'],contains_events=True,
        hosts=sorted(rec['hosts']),host_event_counts=rec['hosts'],required_for_experiment=rec['file_name'] in ['malicious.zip','ground.zip'],
        reason_required='Supplementary event-ID research annotations and cross-checks. Not a replacement for complete official telemetry.'))
save('manifests/raw_file_catalog.json',{'official_raw_files':[], 'official_raw_downloaded_count':0,
    'official_raw_downloaded_bytes':0,'official_raw_event_count':None,
    'official_raw_event_count_reason':'NOT AVAILABLE: both selected official files returned quota pages.',
    'supplementary_event_archives':catalog,'missing_required_files':missing,
    'gzip_validation':'NOT AVAILABLE: no official gzip downloaded.',
    'supplementary_validation':'All five ZIP members fully read to EOF; CRC and JSONL parsing verified. Original archive bytes unchanged.'})

scenarios=[]
matches=list(re.finditer(r'Day ([123]) - "([^"]+)"',text))
for i,match in enumerate(matches):
    segment=text[match.start():matches[i+1].start() if i+1<len(matches) else len(text)]
    timestamps=re.findall(r'\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}',segment)
    hosts=sorted(set(re.findall(r'\b(?:sysclient\s*\d{4}|DC1(?:\.systemia\.com)?)\b',segment,re.I)))
    scenarios.append({'name':field(match[2],'OFFICIAL_SOURCE','PDF campaign heading'),
        'day':field(int(match[1]),'OFFICIAL_SOURCE','PDF campaign heading'),
        'timestamps_as_printed':field(timestamps,'OFFICIAL_SOURCE','PDF log entries; extracted order preserved'),
        'timezone':field(None,'UNKNOWN','PDF does not explicitly specify timezone. Supplementary telemetry contains -04:00; do not silently assign this to PDF times.'),
        'hosts_as_printed':field(hosts,'DERIVED','Case-insensitive regex extraction from this campaign section; spelling/case preserved, not canonical identities'),
        'phases_and_actions':field('See official_timeline.json and extracted PDF text; retain attempted/failed/successful distinctions.','OFFICIAL_SOURCE','Official campaign summary and dated log'),
        'ecar_event_ids':field(None,'UNKNOWN','No eCAR UUIDs explicitly present in official PDF.'),
        'attack_technique_ids':field(None,'UNKNOWN','No explicit ATT&CK technique IDs present in official PDF.')})
ground={
 'official_pdf':field('data/external/optc/official/ground_truth/OpTCRedTeamGroundTruth.pdf','OFFICIAL_SOURCE',official[0]['url']),
 'sha256':field(official[0]['sha256'],'DERIVED','SHA-256 of downloaded PDF bytes'),
 'size_bytes':field(official[0]['size_bytes'],'DERIVED','Local file size'),
 'downloaded_at':field(official[0]['downloaded_at'],'DERIVED','HTTPS acquisition log'),
 'pdf_validation':field({'header':'%PDF-','eof_marker':True,'pages':7,'parser':'pypdf 6.19.0'},'DERIVED','Successfully parsed all seven pages; not HTML'),
 'extracted_text_path':field('data/external/optc/official/ground_truth/ground_truth_text.txt','DERIVED','pypdf 6.19.0 page.extract_text; page markers added; original PDF unchanged'),
 'extraction_limitations':field('Some punctuation decodes as replacement characters; use original PDF when exact typography matters. No OCR or inferred words added.','DERIVED','Inspection of extracted text'),
 'attack_scenarios':field(scenarios,'OFFICIAL_SOURCE','PDF; individual fields identify derived/unknown values'),
 'timeline_path':field('data/external/optc/processed/official_timeline.json','DERIVED','102 extracted timestamped narrative entries with PDF page references'),
 'official_event_identifiers':field(None,'UNKNOWN','Official PDF lists agent IDs and PIDs, not eCAR event UUIDs.'),
 'explicit_attack_mapping':field(None,'UNKNOWN','Independent reviewed ATT&CK mapping not yet available; no mapping inferred as official.'),
 'processes_accounts_files_network':field('Official PDF and page-referenced timeline retain process names, PIDs, accounts, files, IPs, domains and action outcomes verbatim; they are narrative indicators, not verified telemetry joins.','OFFICIAL_SOURCE','ground_truth_text.txt and official_timeline.json'),
 'supplementary_event_mapping':field({'repository':'AT03380/optc-labels','commit':COMMIT,'tasks_path':'data/external/optc/processed/tasks.json',
    'annotated_narrative_path':'data/external/optc/supplementary/optc-labels/supplementary/ground-truth.md',
    'task_count':tasks['task_count'],'unique_nonempty_event_ids':tasks['unique_nonempty_event_ids'],
    'example_event_id':'43fb9623-3cd1-45ec-ab22-dbe46e75240e','example_host':'SysClient0201.systemia.com',
    'example_timestamp':'2019-09-23T11:23:55.857-04:00','example_labels':['malicious','ground','red','day1','process'],
    'warnings':'The third-party ground label is not an official DARPA label. Invalid correlations and incomplete/missing observations must be reviewed.'},'SUPPLEMENTARY_SOURCE','tasks/tasks.zip and supplementary/ground-truth.md'),
 'raw_alignment_verified':field(False,'DERIVED','Official raw shards unavailable; no independent official-raw join performed.'),
}
save('manifests/ground_truth_manifest.json',ground)

malicious=next(x for x in labels if x['file_name']=='malicious.zip')
manifest={'dataset_name':'DARPA Operationally Transparent Cyber (OpTC)',
 'dataset_type':'real_collected_cybersecurity_telemetry','official_source':'https://github.com/FiveDirections/OpTC-data',
 'ground_truth_source':'OpTCRedTeamGroundTruth.pdf','supplementary_label_source':'AT03380/optc-labels',
 'supplementary_label_status':'third_party_research','supplementary_git_commit':COMMIT,
 'download_timestamp':NOW,'download_timestamp_meaning':'Acquisition report completion; individual file timestamps in files',
 'files':source_files,'source_file_count':len(source_files),'total_size_bytes':sum(x['size_bytes'] for x in source_files),
 'total_size_scope':'Official PDF/documentation plus supplementary repository working-tree files, excluding .git, tools, manifests and derived outputs.',
 'total_events':None,'hosts':[],'time_range':{'start':None,'end':None},
 'event_coverage_scope':'Complete official raw telemetry; NOT AVAILABLE. Supplementary event subsets reported separately below.',
 'official_raw_files_acquired':0,'official_raw_bytes_acquired':0,
 'supplementary_event_subset':{'archive':'malicious.zip','event_count':malicious['event_count'],
    'unique_event_ids':malicious['unique_event_ids'],'hosts':sorted(malicious['hosts']),
    'time_range':{'start':malicious['time_start'],'end':malicious['time_end']},
    'warning':'Research-selected events, not complete chronological or benign coverage. Do not add counts across overlapping label archives.'},
 'sha256':[{'path':f['path'],'sha256':f['sha256']} for f in source_files],
 'license_or_release_information':{'official':'Public domain, Distribution A; as-is without accuracy warranty (official README).',
    'supplementary_code':'AGPL-3.0','supplementary_material':'CC BY-SA 4.0',
    'supplementary_labels_and_tasks':'Public domain per repository README; third-party research, not official DARPA ground truth.'},
 'processing_status':'PARTIAL_ACQUISITION_OFFICIAL_RAW_QUOTA_BLOCKED',
 'ground_truth_status':'OFFICIAL_PDF_ACQUIRED_AND_EXTRACTED; SUPPLEMENTARY_LABELS_INSPECTED; INDEPENDENT_TECHNIQUE_TARGETS_NOT_READY',
 'notes':['No application, frontend, model, database or schema changes. No training or host response actions.',
    'OpTC is collected telemetry from a controlled red-team exercise, not operational production traffic.',
    'Existing importer not executed; API only accepts files directly in data/optc.',
    'pypdf 6.19.0 installed with approval only under data/external/optc/downloads/pdf_tools; no dependency manifests changed.',
    'Both planned raw downloads returned Google quota pages, not a demonstrated corporate firewall block.',
    'No real-data performance, uncertainty, calibration or holdout results have been calculated.']}
save('manifests/optc_manifest.json',manifest)

readiness=[
 ('A','Chronological observed prefixes','PARTIAL','Timestamped supplementary records can be ordered, but label-selected records omit benign context; complete official prefixes cannot yet be built.'),
 ('B','Events after a prediction cutoff','PARTIAL','Supplementary events span several days and include later records; completeness and official-raw coverage are unverified.'),
 ('C','Independent actual future attack behavior','PARTIAL','Official narrative and third-party annotations exist independently of the predictor; raw alignment and action outcomes require review.'),
 ('D','ATT&CK mapping independent of predictor output','PARTIAL','Narrative behavior supports later analyst mapping, but no explicit technique IDs were found in the PDF or tasks and no reviewed mapping is ready.'),
 ('E','Train/validation/test scenario separation','NO','A complete pilot is unavailable; three related campaign days do not establish sufficient independent scenarios. Host/day groups are not independent incidents.'),
 ('F','Top-1/3/5, MRR, Macro-F1, Brier, ECE','NO','No aligned independent technique targets, declared label space, real-data predictions or held-out split.'),
 ('G','Measure uncertainty','NO','No real-data predictive distribution or independent uncertainty validation has been produced.'),
 ('H','Measure calibration','NO','No untouched calibration/test partitions and aligned probability predictions exist for real telemetry.'),
 ('I','Real-data holdout evaluation','NO','Acquisition is partial and no leakage-controlled real holdout has been established.'),
]
save('manifests/evaluation_readiness.json',{'evaluated_at':NOW,'answers':[dict(zip(['id','question','status','evidence'],r)) for r in readiness],
 'metrics':None,'metric_status':'NOT MEASURED','real_validation_completed':False})

label_rows='\n'.join(f"| {x['file_name']} | {x['event_count']:,} | {len(x['hosts'])} | {x['size_bytes']:,} |" for x in labels)
readiness_rows='\n'.join(f'| {i}. {q} | {s} | {e} |' for i,q,s,e in readiness)
missing_rows='\n'.join(f"- `{x['file_name']}` — Drive ID `{x['drive_id']}`, listed {x['listed_size']}; `GOOGLE_DRIVE_QUOTA_EXCEEDED`." for x in missing)
source_rows='\n'.join(f"| `{pathlib.Path(x['path']).name}` | {x['size_bytes']:,} | `{x['sha256']}` |" for x in official)
report=f'''# OpTC Real-Data Readiness

Acquisition inspected {NOW}. **PARTIAL: official documentation and research labels acquired; official raw telemetry unavailable because of Google Drive quota. Real future-technique evaluation is not ready.**

Only `data/external/optc/` and this report were created. Application code, frontend, models, database and schema were not changed. No training, import, simulation or host response action was run.

## Official source

[FiveDirections/OpTC-data](https://github.com/FiveDirections/OpTC-data) releases collected endpoint telemetry from a controlled red-team exercise. This is not a claim of production deployment validation. The release is public domain, Distribution A, and carries no accuracy warranty. Local copies of README, ecar.md and errata.md are under `data/external/optc/official/documentation/`.

Initial inspection found no OpTC telemetry, PDF, supplementary labels, dedicated manifest or `data/optc.sqlite3`. A historical checksum entry existed for an absent PDF; the new PDF matches it. See `manifests/project_inspection.json` for importer review and inspected paths.

## Ground truth

Official PDF: `data/external/optc/official/ground_truth/OpTCRedTeamGroundTruth.pdf`.
SHA-256: `{official[0]['sha256']}`. Size: {official[0]['size_bytes']:,} bytes.

PDF signature, EOF marker and seven-page parsing succeeded. Text is in `official/ground_truth/ground_truth_text.txt`; 102 timestamped log entries with page references are in `processed/official_timeline.json`. These are derived extractions of the official narrative. Some punctuation has replacement characters; consult the PDF for exact typography. No event text was invented.

No PDF extractor was installed. With permission, pypdf 6.19.0 was installed only in `downloads/pdf_tools/`; application dependencies were not changed. Raw source copies were never overwritten.

## Supplementary labels

[AT03380/optc-labels](https://github.com/AT03380/optc-labels), commit `{COMMIT}`, was cloned through normal HTTPS. It is **third-party research, not official DARPA ground truth**. All 24 tracked working-tree files were acquired, including README, LICENSE, five label archives, tasks/tasks.zip, supplementary documentation and source code. No downloaded labeler code was executed. Git transport succeeded; no repository ZIP endpoint was used.

The README and how-to document say `malicious.zip` is the broad event selection and the other label archives are overlapping subsets. Do not sum their counts as independent observations. The archive membership relationship has not been exhaustively compared across all files.

`tasks/tasks.zip` contains `tasks.json` (136,569,900 uncompressed bytes); an exact extracted copy is in `processed/tasks.json`. It has 931 task records, 851 distinct nonempty event UUIDs, 58 repeated nonempty UUID occurrences, and 22 records without event IDs or hostnames. Counts concern tasks, not independent events. Its 17 `invalid` tasks must be excluded from matching.

Labels distinguish outcome (malicious/benign), source (ground/correlated/anomaly/invalid), actor (red/admin), timeline (prior/day1/day2/day3), and granularity (process/event). Join event-level annotations by event UUID; process-level annotations require the documented object/process relationship. A `ground` label remains a third-party annotation. The repository's benign-by-complement convention is not independent proof that unannotated activity is benign.

Useful integration resources: official PDF, supplementary/ground-truth.md, tasks/tasks.zip, labels/malicious.zip, labels/ground.zip, supplementary/how-to.md, labels.md and errata.md. Retained source code and image are not required for this experiment. README assigns AGPL-3.0 to original code, CC BY-SA 4.0 to supplementary materials, and public domain to labels/tasks and reproduced OpTC records.

## Raw files acquired

**Official raw telemetry: 0 files, 0 bytes. Event count: NOT AVAILABLE.** No HTML response was accepted as gzip.

The supplementary repository does contain selected raw eCAR event records; they are catalogued separately as `supplementary_research`, not as direct official raw downloads:

| Archive | JSONL records | Hosts | Compressed bytes |
|---|---:|---:|---:|
{label_rows}

All five archives were read completely to EOF, validating ZIP CRC and every JSONL record. No malformed records, duplicate event IDs within an archive, missing event IDs, missing hostnames, invalid timestamps or missing required importer fields were found. This establishes structural readability only, not correctness of annotations. Detailed host counts and event types are in `processed/supplementary_labels_inspection.json`.

## Raw files unavailable

The first pilot selects Day 1, SysClient0201, retaining the full host-group shards. Both are in official `ecar/evaluation/23Sep19-red/AIA-201-225/`:

{missing_rows}

Both were attempted through normal public Drive confirmation forms and returned quota errors. File names contain post-processing dates and cannot establish event time coverage. No gzip validity, official event count, official duplicate count or actual official time range is available.

## File hashes

`data/external/optc/manifests/sha256_manifest.json` records SHA-256 and byte length of acquired sources and derived inspection files. It excludes mutable `.git` internals and isolated PDF tool binaries. Source hashes were recalculated and checked after inspection. No upstream authenticated hash/signature is claimed; the historical PDF checksum is a local consistency check.

| Official file | Bytes | SHA-256 |
|---|---:|---|
{source_rows}

Dataset source-file total: {len(source_files)} files, {manifest['total_size_bytes']:,} bytes, excluding .git, tools and derived copies. Per-file source URLs, timestamps and provenance are in `optc_manifest.json`.

## Dataset time range

Complete official raw time range: **NOT AVAILABLE**. Official narrative covers September 23–25, 2019; its printed clock times have no explicit timezone. Day 2 includes overnight events on September 25.

The inspected supplementary malicious event subset spans `{malicious['time_start']}` through `{malicious['time_end']}` (UTC conversion of actual event timestamps). This range belongs to the selected subset, not the full dataset. Telemetry includes explicit -04:00 offsets; matching the PDF clock to that offset remains a documented alignment hypothesis until reviewed.

## Host coverage

Official raw hosts: **NOT AVAILABLE**. The broad supplementary malicious subset has {len(malicious['hosts'])} observed hostnames; `SysClient0201.systemia.com` contributes {malicious['hosts']['SysClient0201.systemia.com']:,} records. Full host lists are in the manifests. PDF host references describe campaign scope and do not prove that every host was recorded.

The supplementary annotated narrative states that DC1 logs are absent and identifies narrative actions whose corresponding raw event was not found. This is a third-party finding, not newly verified against the complete official release.

## Event counts

Complete official events: **NOT AVAILABLE**. Downloaded official bytes: 0. Supplementary `malicious.zip`: {malicious['event_count']:,} records / {malicious['unique_event_ids']:,} unique event IDs. Other archive counts overlap. No global independent event total is fabricated.

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

Disk free before source acquisition was 391,444,471,808 bytes; before planned raw downloads it was {plan['free_disk_bytes']:,} bytes. Drive displayed 104.6 MB and 2.07 GB; exact byte lengths are **NOT AVAILABLE**. The download plan caps them at 110,000,000 and 2,300,000,000 bytes. A conservative, unmeasured 50× expansion allowance is 120,500,000,000 bytes; inspection would stream without writing decompressed files. Current free disk: {shutil.disk_usage(ROOT).free:,} bytes. No >20 GB file was attempted.

## What remains to be acquired

The two named official eCAR shards above are the required pilot downloads. Wait for Google quota to reset or obtain owner-approved access through the official source; do not work around the quota. The required filenames and IDs are in `missing_required_files.json`. If their content lacks lead-in/future coverage, inspect the adjacent official benign/evaluation listings before choosing further files. Exact additional filenames and extracted sizes are **NOT AVAILABLE**, not invented.

Bro/ecar-bro and other campaign host groups are deferred, not silently assumed acquired. The pilot alone will not establish a sufficient independent train/calibration/test population.

## Whether real future-technique evaluation is currently possible

**NO. Preparation is partial, not completed real-world validation.**

| Check | Status | Evidence |
|---|---|---|
{readiness_rows}

Next step: retry the two official downloads after the quota restriction clears, then validate coverage and independently reconcile the first campaign's labels and clocks. Application integration and training require a separate task after these prerequisites are satisfied.
'''
with (WORKSPACE/'docs/OPTC_REAL_DATA_READINESS.md').open('x',encoding='utf8') as f:f.write(report)
print(json.dumps({'source_files':len(source_files),'source_bytes':manifest['total_size_bytes'],'report':'docs/OPTC_REAL_DATA_READINESS.md','official_raw_files':0,'readiness':'PARTIAL; real evaluation NO'},indent=2))
