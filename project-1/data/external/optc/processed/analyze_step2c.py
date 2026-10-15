"""Inspect acquired copies only. Never import application code or execute telemetry."""
import collections
import csv
import datetime as dt
import hashlib
import itertools
import json
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = ROOT / 'supplementary/optc-labels'
tasks = json.loads((ROOT/'processed/tasks.json').read_bytes())
official = json.loads((ROOT/'processed/official_timeline.json').read_text())
pdf_text = (ROOT/'official/ground_truth/ground_truth_text.txt').read_text(encoding='utf8')
def save(name, data):
    with (ROOT/'manifests'/name).open('x',encoding='utf8') as f: json.dump(data,f,indent=2,ensure_ascii=False)
def stamp(s):
    d = dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('Timezone missing')
    return d.astimezone(dt.timezone.utc)
def norm(s): return ' '.join(s.lower().split())
def host(s): return s.lower().split('.')[0].replace(' ','')

task_ids = {t['event_id'] for t in tasks if t.get('event_id')}
sets={}; primary={}; selected={}; summaries=[]; byte_conflicts=collections.Counter()
for name in ['malicious','admin','anomaly','ground','red']:
    ids=set(); count=0; fields=collections.Counter(); missing=collections.Counter(); label_keys=collections.Counter()
    timestamps=[]; hosts=collections.Counter(); previous_by_host={}; out_of_order=0
    before=after=0; low=None; high=None
    with zipfile.ZipFile(REPO/'labels'/f'{name}.zip') as z:
        with z.open(f'{name}.json') as f:
            for line in f:
                e=json.loads(line); count+=1; eid=e['id']; ids.add(eid)
                h=hashlib.sha256(line).hexdigest()
                if name=='malicious': primary[eid]=h
                elif eid in primary and primary[eid]!=h: byte_conflicts[name]+=1
                fields.update(e.keys())
                label_keys.update(k for k in e if any(s in k.lower() for s in ['label','technique','scenario','task']))
                for k in ['id','hostname','timestamp','actorID','objectID','pid','ppid','principal','properties']:
                    if k not in e or e[k] is None or e[k]=='': missing[k]+=1
                time=stamp(e['timestamp']); hostname=e['hostname']; hosts[hostname]+=1
                low=time if low is None or time<low else low; high=time if high is None or time>high else high
                if hostname in previous_by_host and time<previous_by_host[hostname]:out_of_order+=1
                previous_by_host[hostname]=time
                if eid in task_ids and name=='malicious':selected[eid]={k:e.get(k) for k in ['id','hostname','timestamp','actorID','objectID','pid','object','action']}
                if name=='malicious' and host(hostname)=='sysclient0201':
                    cutoff=dt.datetime(2019,9,23,15,30,tzinfo=dt.timezone.utc)
                    if time<=cutoff: before+=1
                    else: after+=1
    sets[name]=ids
    summaries.append({'archive':name+'.zip','records':count,'unique_event_ids':len(ids),'duplicate_ids_within_archive':count-len(ids),
        'hosts':dict(sorted(hosts.items())),'time_min_utc':low.isoformat(),'time_max_utc':high.isoformat(),
        'top_level_fields':dict(fields),'missing_or_empty_fields':dict(missing),'embedded_label_technique_scenario_task_keys':dict(label_keys),
        'per_host_backwards_timestamp_steps_in_file_order':out_of_order,'zip_crc_verified':True,
        'cutoff_probe':{'host':'SysClient0201.systemia.com','cutoff_utc':'2019-09-23T15:30:00+00:00','before_or_equal':before,'strictly_after':after,
            'scope':'Whole malicious archive only; not a forecast-horizon count and not proof of complete prefixes. PDF timezone alignment remains unverified.'} if name=='malicious' else None})
    print(name,count,'extra IDs outside malicious',len(ids-sets['malicious']),flush=True)

overlaps=[{'left':a,'right':b,'shared_ids':len(sets[a]&sets[b]),'left_only':len(sets[a]-sets[b]),'right_only':len(sets[b]-sets[a])}
          for a,b in itertools.combinations(sets,2)]
by_event=collections.defaultdict(list)
for t in tasks:
    if t.get('event_id'):by_event[t['event_id']].append(t)
conflicting=[]
for eid,items in by_event.items():
    outcomes={l for t in items for l in (t.get('labels') or []) if l in ['malicious','benign']}
    if len(outcomes)>1: conflicting.append({'event_id':eid,'task_ids':[t['task_id'] for t in items],'labels':[t.get('labels') for t in items]})
conflict_ids={x['event_id'] for x in conflicting}
missing_task={k:sum(k not in t or t[k] is None or t[k]=='' or t[k]==[] for t in tasks) for k in sorted(set().union(*(t.keys() for t in tasks)))}
task_uuid_counts=collections.Counter(t.get('task_id') for t in tasks if t.get('task_id'))
invalid=[{'task_id':t.get('task_id'),'event_id':t.get('event_id'),'labels':t.get('labels'),
          'event_in_malicious_archive':t.get('event_id') in sets['malicious'],'annotation':t.get('annotations')} for t in tasks if 'invalid' in (t.get('labels') or [])]
scenario_hosts={l:sorted({t['hostname'] for t in tasks if l in (t.get('labels') or []) and t.get('hostname')}) for l in ['prior','day1','day2','day3']}
scenario_overlaps=[{'left':a,'right':b,'shared_hosts':sorted(set(scenario_hosts[a])&set(scenario_hosts[b]))} for a,b in itertools.combinations(scenario_hosts,2)]

rows=[]
for index,t in enumerate(tasks):
    log=t.get('log') or ''; match=re.search(r'\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}',log)
    candidates=[x for x in official if match and x['timestamp_as_printed']==match[0]]
    exact_narrative=bool(log and norm(log) in norm(pdf_text))
    eid=t.get('event_id'); labels=t.get('labels') or []; event=selected.get(eid)
    reasons=[]; disagreements=[]
    if candidates: support='Matching printed timestamp in official narrative; action wording must be reviewed, timezone not resolved.'
    elif exact_narrative:support='Task log text occurs in official extracted PDF (whitespace/case normalized).'
    else:support='No exact printed timestamp or normalized whole-log text match found; absence is not evidence of benign behavior.'
    if eid in conflict_ids:disagreements.append('Same event UUID has both benign and malicious outcomes in different supplementary tasks.')
    if 'benign' in labels and eid in sets['malicious']:disagreements.append('Task labels event benign but the event UUID occurs in malicious.zip; task/process granularity needs adjudication.')
    if 'invalid' in labels and eid in sets['malicious']:disagreements.append('Task marked invalid still has its event UUID in malicious.zip.')
    if event and t.get('hostname') and host(t['hostname'])!=host(event['hostname']):disagreements.append('Task hostname differs from matching archive event.')
    if event and t.get('timestamp'):
        try:
            if stamp(t['timestamp'])!=stamp(event['timestamp']):disagreements.append('Task timestamp differs from matching archive event timestamp.')
        except ValueError:reasons.append('Task timestamp could not be compared.')
    if not eid: reasons.append('Missing event UUID.')
    if not event:reasons.append('Event UUID not found in malicious.zip; other task context may exist.')
    reasons.extend(['No official eCAR UUID in PDF.','No explicit independent ATT&CK target.','Complete official telemetry unavailable.','PDF timezone not specified.'])
    status='DISAGREEMENT' if disagreements else 'PARTIAL' if candidates or exact_narrative else 'NOT_FOUND' if log else 'UNKNOWN'
    delta=None
    if match and t.get('timestamp'):
        try:delta=(dt.datetime.fromisoformat(t['timestamp']).replace(tzinfo=None)-dt.datetime.strptime(match[0],'%m/%d/%y %H:%M:%S')).total_seconds()
        except ValueError:pass
    rows.append({'scenario':','.join(l for l in labels if l in ['prior','day1','day2','day3']) or 'UNKNOWN',
        'host':t.get('hostname') or 'UNKNOWN','timestamp':t.get('timestamp') or 'UNKNOWN','task_id':t.get('task_id'),
        'event_id':eid,'official_ground_truth_support':support,'official_pdf_pages':sorted({x['pdf_page'] for x in candidates}),
        'official_printed_timestamp':match[0] if match else None,'task_log':log,
        'supplementary_label_support':labels,'event_found_in_archives':[a for a,ids in sets.items() if eid in ids],
        'agreement':status,'disagreement':disagreements,'missing_information':reasons,
        'wall_clock_delta_seconds_unverified_timezone':delta,
        'provenance':{'official':'OpTCRedTeamGroundTruth.pdf, extracted page-referenced timeline',
            'supplementary':f'AT03380/optc-labels tasks.json array index {index}',
            'comparison':'DERIVED deterministic comparison; not a declaration of ground-truth equivalence'}})
save('ground_truth_reconciliation.json',{'status_definitions':{'AGREEMENT':'Reserved for a fully reviewed supported claim; none automatically assigned.',
    'PARTIAL':'Narrative text/timestamp match; UUID, timezone, semantics or full telemetry verification remains incomplete.',
    'DISAGREEMENT':'Observed supplementary inconsistency; not necessarily a contradiction of the official PDF.',
    'NOT_FOUND':'Task narrative has no deterministic PDF match; does not imply false or benign.',
    'UNKNOWN':'No task narrative sufficient for deterministic reconciliation.'},
    'status_counts':dict(collections.Counter(r['agreement'] for r in rows)),
    'scope':'One row per supplementary task, including unresolved/invalid entries; no guessed matches or ATT&CK labels.', 'rows':rows})
with (ROOT/'processed/ground_truth_reconciliation.csv').open('x',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
    for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})

answers=[
 ('A','Benign context','NO','Archives select research-labeled malicious activity. Some task outcomes contradict archive membership; neither these nor admin-labeled events establish a representative benign stream.'),
 ('B','Complete chronological prefixes','NO','Selected event subsets omit all unselected activity. Time ordering cannot recover missing events.'),
 ('C','Future events after cutoffs','PARTIAL','Actual records exist on both sides of the explicit UTC probe cutoff; complete future horizons and PDF clock alignment remain unverified.'),
 ('D','Independent future-technique labels','NO','Outcome/source/actor/timeline/granularity labels exist, but no explicit independent ATT&CK targets were found.'),
 ('E','Scenario-disjoint evaluation','NO','Only related campaign-day annotations and selected events are available. Independent scenario/collection partitions and complete observations are missing.'),
 ('F','Original event identifiers','YES','All archive records contain event UUIDs and preserve eCAR fields. Identity against unavailable official shard bytes has not been independently verified.'),
 ('G','Alignment to official ground truth','PARTIAL','Task narrative timestamps/text can be reconciled in part. Official PDF lacks event UUIDs and timezone; inconsistencies remain unresolved.'),
 ('H','Exploratory preprocessing','YES','Suitable for parser, schema, identifier, timestamp and provenance inspection with the selection bias clearly retained.'),
 ('I','Final real-data validation','NO','Missing full raw telemetry, benign context, reviewed technique targets, independent splits and finalized evaluation protocol.')]
save('supplementary_label_analysis.json',{'analyzed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
    'source_type':'supplementary_research','source_repository':'AT03380/optc-labels',
    'git_commit':'64c9f9b2e1a15bf3c2789d89d93dc0724cb0d4fa',
    'documentation_directory':'NOT PRESENT; README and supplementary/ contain the documentation.',
    'archives':summaries,'archive_overlaps_by_event_id':overlaps,'unique_event_union':len(set().union(*sets.values())),
    'same_uuid_different_line_bytes_vs_malicious':dict(byte_conflicts),
    'task_count':len(tasks),'task_field_missing_empty_null_counts':missing_task,
    'unique_task_ids':len(task_uuid_counts),'duplicate_task_id_occurrences':sum(v-1 for v in task_uuid_counts.values()),
    'unique_nonempty_event_ids':len(task_ids),'task_event_ids_found_in_malicious':len(task_ids&sets['malicious']),
    'task_label_counts':dict(collections.Counter(l for t in tasks for l in (t.get('labels') or []))),
    'unique_nonempty_process_object_ids':len({t['object_id'] for t in tasks if t.get('object_id')}),
    'unique_nonempty_actor_ids':len({t['actor_id'] for t in tasks if t.get('actor_id')}),
    'annotations_present':sum(bool(t.get('annotations')) for t in tasks),
    'process_tree_present':sum(bool(t.get('proces_table')) for t in tasks),
    'embedded_raw_context_present':sum(bool(t.get('raw')) for t in tasks),
    'invalid_tasks':invalid,'conflicting_task_outcomes_for_same_uuid':conflicting,
    'scenario_hosts':scenario_hosts,'scenario_host_overlap':scenario_overlaps,
    'reconciliation_status_counts':dict(collections.Counter(r['agreement'] for r in rows)),
    'archive_suitability':[dict(zip(['id','question','status','evidence'],a)) for a in answers],
    'matcher_static_review':['Process filters aggregate labels by object_id without host qualification.',
        'Event filters are populated from process-object filters rather than directly copying event-only task labels.',
        'No explicit invalid-label exclusion was found in makeFilters; malicious inclusion uses aggregated labels.',
        'Matching uses regex against actorID or event id; no hostname check. No source code was executed.',
        'These are static implementation observations, not proof that this exact revision generated each archive.'],
    'prohibited_uses':['Do not treat these labels as official DARPA ground truth.','Do not treat archive selection or task annotations as cutoff features.','Do not report prediction performance from this analysis.']})
print('OVERLAPS',json.dumps(overlaps),flush=True)
print('RECONCILIATION',dict(collections.Counter(r['agreement'] for r in rows)),flush=True)
