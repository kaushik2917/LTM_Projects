"""Fail-closed preparation gate; no application imports, downloads or database writes."""
import datetime
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[2]

def check():
    dataset = json.loads((ROOT/'manifests/optc_manifest.json').read_text(encoding='utf8'))
    errors=[]
    for source in dataset['files']:
        p=(WORKSPACE/source['path']).resolve()
        if not p.is_relative_to(ROOT):
            errors.append({'path':source['path'],'reason':'Source outside acquisition directory'});continue
        if not p.is_file():
            errors.append({'path':source['path'],'reason':'Missing source'});continue
        with p.open('rb') as f: actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=source['sha256'] or p.stat().st_size!=source['size_bytes']:
            errors.append({'path':source['path'],'reason':'Source checksum/size mismatch'})
    plan=json.loads((ROOT/'manifests/acquisition_plan.json').read_text())
    missing=[i['file_name'] for i in plan['files'] if not (ROOT/'official/raw'/i['file_name']).is_file()]
    # Presence is necessary, never sufficient. No current approved coverage/label/split artifacts exist.
    prerequisite_paths={
        'official_raw_validation':'manifests/official_raw_validation.json',
        'independent_reviewed_targets':'manifests/approved_technique_targets.json',
        'reviewed_clock_alignment':'manifests/approved_clock_alignment.json',
        'independent_split_review':'manifests/approved_scenario_split.json',
        'final_protocol_review':'manifests/approved_prediction_protocol.json',
        'event_level_leakage_checks':'manifests/event_leakage_validation.json',
    }
    gates={k:('NOT_AVAILABLE' if not (ROOT/p).is_file() else 'REQUIRES_CONTENT_REVIEW') for k,p in prerequisite_paths.items()}
    # This preparation-only checker cannot approve training, even if future files appear.
    return {'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status':'BLOCKED','training_authorized':False,'source_integrity':'FAIL' if errors else 'PASS',
        'source_files_checked':len(dataset['files']),'source_errors':errors,'missing_official_raw_files':missing,
        'prerequisite_gates':gates,'event_level_leakage_validation':'NOT_RUN: no approved real experiment samples exist.',
        'scope':'Preparation audit only; future artifacts require content validation and separate authorization. No training or import performed.'}

if __name__=='__main__':
    result=check()
    path=ROOT/'manifests/preparation_check.json'
    if path.exists():
        path=ROOT/'manifests'/('preparation_check_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
    sys.exit(2 if result['status']=='BLOCKED' else 0)
