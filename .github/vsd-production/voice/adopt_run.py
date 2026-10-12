"""Adopt a successful trusted rendering artifact; never execute artifact code."""
import argparse
import datetime as dt
import io
import json
from pathlib import Path,PurePosixPath
import re
import stat
import subprocess
import tempfile
import zipfile
import stock
import select_render

REPO='MathCSN/voyagesansdetour'
WORKFLOW='.github/workflows/vsd-voice-production.yml'

def api(path,limit=2_000_000):
    with tempfile.TemporaryFile() as error:
        proc=subprocess.Popen(['gh','api',f'repos/{REPO}/{path}'],stdout=subprocess.PIPE,stderr=error)
        try:
            raw=proc.stdout.read(limit+1)
            if len(raw)>limit:raise ValueError('response_bound')
            if proc.wait(timeout=60):raise ValueError('github_read_failed')
            return raw
        finally:
            if proc.poll() is None:proc.kill();proc.wait()

def qualify_run(run,run_id):
    if (str(run.get('id'))!=run_id or run.get('repository',{}).get('full_name')!=REPO
        or run.get('repository',{}).get('private') is not False
        or run.get('head_repository',{}).get('full_name')!=REPO
        or run.get('head_branch')!='main' or run.get('path')!=WORKFLOW
        or run.get('event') not in ('schedule','workflow_dispatch') or run.get('run_attempt')!=1
        or run.get('status')!='completed' or run.get('conclusion')!='success'
        or not re.fullmatch(r'[a-f0-9]{40}',run.get('head_sha',''))
        or run.get('html_url')!=f'https://github.com/{REPO}/actions/runs/{run_id}'):
        raise ValueError('untrusted_or_unsuccessful_run')

def unpack(raw,destination):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos=archive.infolist();total=0;names=set()
        if not 1<=len(infos)<=240:raise ValueError('archive_count')
        for item in infos:
            path=PurePosixPath(item.filename);mode=item.external_attr>>16
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                or item.filename in names or stat.S_ISLNK(mode)
                or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)))):raise ValueError('archive_path')
            names.add(item.filename);total+=item.file_size
            if item.file_size>50_000_000 or total>100_000_000:raise ValueError('archive_size')
        archive.extractall(destination)

def run(root,run_id,now,reader=api):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=stock.STOP:return {'status':'period_ended','changed':False}
    if not re.fullmatch(r'[1-9][0-9]{0,19}',run_id):raise ValueError('run_identity')
    root=Path(root)
    if root.is_symlink() or (root/'voice-stock').is_symlink() or (root/'reel-drafts').is_symlink():raise ValueError('symlink')
    remote=json.loads(reader(f'actions/runs/{run_id}'));qualify_run(remote,run_id)
    matches=[]
    for p in select_render.children(root/'voice-attempts',64):
        record=select_render.read(p)
        if str(record.get('runId'))==run_id:
            if p.stem!=record['id'] or record['status']!='reserved_before_render' or record['publicationApproved'] is not False:raise ValueError('attempt_changed')
            matches.append(record)
    if not matches:return {'status':'no_reserved_render','changed':False,'runId':run_id}
    if len(matches)!=1:raise ValueError('ambiguous_attempt')
    attempt=matches[0];identity=attempt['id']
    if not re.fullmatch(r'reel-article-[a-z0-9-]+',identity):raise ValueError('identity')
    if now>=dt.datetime.fromisoformat(attempt['validUntil'].replace('Z','+00:00')):return {'status':'expired_not_adopted','changed':False,'id':identity}
    draft=root/'reel-drafts'/identity/'storyboard.json'
    select_render.read(draft)
    if stock.sha(draft.read_bytes())!=attempt['storyboardSha256']:raise ValueError('source_changed')
    data=json.loads(reader(f'actions/runs/{run_id}/artifacts?per_page=100'))
    if data['total_count']!=len(data['artifacts']):raise ValueError('partial_artifacts')
    assets=[a for a in data['artifacts'] if a['name']=='vsd-storyboard-media']
    if len(assets)!=1 or assets[0]['expired'] or not 0<assets[0]['size_in_bytes']<=100_000_000:raise ValueError('artifact_unavailable')
    artifact_id=assets[0]['id']
    if type(artifact_id) is not int or artifact_id<=0:raise ValueError('artifact_identity')
    with tempfile.TemporaryDirectory(prefix='vsd-voice-adopt-') as tmp:
        media=Path(tmp)/'media';media.mkdir()
        unpack(reader(f'actions/artifacts/{artifact_id}/zip',100_000_000),media)
        receipt=select_render.read(media/'receipt.json')
        if receipt['id']!=identity or receipt['storyboardSha256']!=attempt['storyboardSha256'] or receipt['validUntil']!=attempt['validUntil']:raise ValueError('artifact_attempt_mismatch')
        cloud={'repository':REPO,'artifactName':'vsd-storyboard-media','run':{'databaseId':remote['id'],'status':remote['status'],'conclusion':remote['conclusion'],'headBranch':remote['head_branch'],'headSha':remote['head_sha'],'url':remote['html_url']},'receiptSha256':stock.sha((media/'receipt.json').read_bytes())}
        return stock.adopt(media,root/'voice-stock'/identity,cloud,now)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();result=run(Path(__file__).resolve().parent.parent,a.run_id,dt.datetime.now(dt.timezone.utc))
    with a.report.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))
