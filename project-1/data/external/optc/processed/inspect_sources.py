"""Read-only source inspection; outputs derived JSON alongside this script."""
import collections
import datetime
import hashlib
import json
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = ROOT / 'supplementary/optc-labels'
def save(name, value):
    with (ROOT / 'processed' / name).open('x', encoding='utf8') as f:
        json.dump(value, f, indent=2)

tasks = json.loads((ROOT / 'processed/tasks.json').read_bytes())
ids = collections.Counter(t.get('event_id') for t in tasks if t.get('event_id'))
task_report = {
    'provenance': 'SUPPLEMENTARY_SOURCE', 'source_type': 'supplementary_research',
    'source_repository': 'AT03380/optc-labels', 'task_count': len(tasks),
    'label_counts': dict(collections.Counter(l for t in tasks for l in (t.get('labels') or []))),
    'unique_nonempty_event_ids': len(ids), 'duplicate_nonempty_event_id_occurrences': sum(n-1 for n in ids.values()),
    'missing_event_id': sum(not t.get('event_id') for t in tasks),
    'hosts': sorted({t['hostname'] for t in tasks if t.get('hostname')}),
    'missing_hostname': sum(not t.get('hostname') for t in tasks),
    'matching_rule': 'Tasks identify event_id and process object_id; event vs process granularity must be honored. Exclude invalid correlations. See supplementary/how-to.md and errata.md.',
    'explicit_attack_technique_ids': sorted(set(re.findall(r'\bT\d{4}(?:\.\d{3})?\b', json.dumps(tasks)))),
}
save('supplementary_tasks_inspection.json', task_report)
print('TASKS', json.dumps({k:v for k,v in task_report.items() if k != 'hosts'}), flush=True)

reports = []
for path in sorted((REPO / 'labels').glob('*.zip')):
    rec = {'file_name': path.name, 'source_type': 'supplementary_research', 'format': 'ZIP containing JSONL',
           'size_bytes': path.stat().st_size, 'sha256': hashlib.file_digest(path.open('rb'), 'sha256').hexdigest(),
           'event_count': 0, 'malformed_records': 0, 'missing_event_id': 0, 'missing_hostname': 0,
           'invalid_timestamp': 0, 'missing_importer_fields': 0, 'duplicate_event_ids': 0}
    seen = set(); hosts = collections.Counter(); objects = collections.Counter(); low = None; high = None
    with zipfile.ZipFile(path) as archive:
        rec['members'] = [{'name': x.filename, 'uncompressed_bytes': x.file_size} for x in archive.infolist()]
        for member in archive.infolist():
            if member.is_dir(): continue
            with archive.open(member) as lines:
                for line in lines:
                    try:
                        event = json.loads(line)
                        if not isinstance(event, dict): raise ValueError('not object')
                    except (ValueError, UnicodeError):
                        rec['malformed_records'] += 1; continue
                    rec['event_count'] += 1
                    eid = event.get('id')
                    if not eid: rec['missing_event_id'] += 1
                    elif eid in seen: rec['duplicate_event_ids'] += 1
                    else: seen.add(eid)
                    host = event.get('hostname')
                    if host: hosts[host] += 1
                    else: rec['missing_hostname'] += 1
                    objects[str(event.get('object'))] += 1
                    if any(not isinstance(event.get(k), str) or not event[k] for k in ['hostname','actorID','objectID','object','action']): rec['missing_importer_fields'] += 1
                    try:
                        stamp = event.get('timestamp', event.get('timestamp_ms'))
                        dt = datetime.datetime.fromtimestamp(stamp/1000, datetime.timezone.utc) if isinstance(stamp, (int,float)) else datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))
                        if dt.tzinfo is None: raise ValueError('timezone missing')
                        dt = dt.astimezone(datetime.timezone.utc)
                        low = dt if low is None or dt < low else low
                        high = dt if high is None or dt > high else high
                    except (ValueError, TypeError, AttributeError, OverflowError): rec['invalid_timestamp'] += 1
        rec['zip_crc_verified'] = True
    rec.update(time_start=low.isoformat() if low else None, time_end=high.isoformat() if high else None,
               hosts=dict(sorted(hosts.items())), event_types=dict(objects), unique_event_ids=len(seen),
               interpretation='Selected research-labeled records, not complete chronological telemetry. Archives overlap; do not sum as independent observations.')
    reports.append(rec)
    print('LABELS', path.name, rec['event_count'], rec['time_start'], rec['time_end'], flush=True)
save('supplementary_labels_inspection.json', reports)

text = (ROOT / 'official/ground_truth/ground_truth_text.txt').read_text(encoding='utf8')
pages = re.split(r'=== PAGE (\d+) ===\n', text)
entries=[]
for index in range(1,len(pages),2):
    page = int(pages[index]); body = pages[index+1]
    for match in re.finditer(r'(\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) -- (.*?)(?=\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} -- |\Z)', body, re.S):
        description = ' '.join(match.group(2).split())
        # Do not include the next campaign summary in the final log entry on a page.
        description = re.split(r' Day [23] -', description)[0]
        entries.append({'timestamp_as_printed':match.group(1), 'timezone':'NOT SPECIFIED', 'description':description,
                        'pdf_page':page, 'provenance':'OFFICIAL_SOURCE', 'extraction':'DERIVED; pypdf 6.19.0'})
save('official_timeline.json', entries)
print('OFFICIAL TIMELINE', len(entries), flush=True)
