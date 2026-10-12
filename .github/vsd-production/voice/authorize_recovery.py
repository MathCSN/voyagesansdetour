"""Authorize one corrected rendering retry only after remote failure reconciliation."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import adopt_run
import select_render as selection

def authorize(root,identity,now,reader=adopt_run.api):
    if now>=selection.STOP:return {'status':'period_ended'}
    if not re.fullmatch(r'reel-article-[a-z0-9-]+',identity):raise ValueError('identity')
    root=Path(root);record=selection.read(root/'voice-attempts'/(identity+'.json'))
    if record['id']!=identity or record.get('previousAttempts') or record['status']!='reserved_before_render':raise ValueError('retry_limit')
    run_id=record['runId']
    remote=json.loads(reader(f'actions/runs/{run_id}'))
    if remote['status']!='completed' or remote['conclusion']!='failure':raise ValueError('failure_not_confirmed')
    # Reuse origin checks; overriding only the already-checked conclusion.
    adopt_run.qualify_run({**remote,'conclusion':'success'},run_id)
    artifacts=json.loads(reader(f'actions/runs/{run_id}/artifacts?per_page=100'))
    if artifacts['total_count']!=len(artifacts['artifacts']):raise ValueError('partial_artifacts')
    if any(a['name']=='vsd-storyboard-media' for a in artifacts['artifacts']):raise ValueError('media_requires_reconciliation')
    draft=root/'reel-drafts'/identity/'storyboard.json';selection.read(draft)
    if selection.sha(draft.read_bytes())!=record['storyboardSha256']:raise ValueError('source_changed')
    if now>=dt.datetime.fromisoformat(record['validUntil'].replace('Z','+00:00')):raise ValueError('expired')
    grant={'status':'one_recovery_authorized','id':identity,'previousRunId':run_id,'storyboardSha256':record['storyboardSha256'],'rendererSha256':selection.renderer_hash(root),'checkedAt':now.isoformat(),'priorRunConclusion':'failure','mediaArtifactAbsent':True,'reason':'Subtitle layout corrected and regression-tested; preserve original attempt, source identity and expiry.'}
    output=root/'voice-recoveries'
    if output.is_symlink():raise ValueError('symlink')
    output.mkdir(exist_ok=True)
    with (output/(identity+'.json')).open('x') as f:json.dump(grant,f,indent=2);f.write('\n')
    return grant

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--id',required=True);a=p.parse_args()
    print(json.dumps(authorize(Path(__file__).resolve().parent.parent,a.id,dt.datetime.now(dt.timezone.utc))))
