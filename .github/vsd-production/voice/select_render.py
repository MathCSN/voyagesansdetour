"""Choose one never-attempted storyboard; no render, provider call or approval."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

STOP=dt.datetime(2027,9,14,21,59,59,tzinfo=dt.timezone.utc)

def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):
    if path.is_symlink():raise ValueError('symlink')
    return json.loads(path.read_text())
def children(path,limit):
    if path.is_symlink():raise ValueError('symlink')
    values=sorted(path.iterdir()) if path.exists() else []
    if len(values)>limit:raise ValueError('inventory_bound')
    return values

def select(root,now):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=STOP:return {'status':'period_ended','selected':None}
    root=Path(root)
    if root.is_symlink():raise ValueError('symlink')
    known={}
    families=[root/'voice-stock']+children(root/'voice-revisions',16)
    for family in families:
        for folder in children(family,64):
            if folder.is_symlink() or not folder.is_dir():raise ValueError('stock_path')
            record=read(folder/'stock.json');identity=record['id']
            if identity!=folder.name:raise ValueError('stock_identity')
            receipt=read(folder/'media/receipt.json')
            if receipt['id']!=identity:raise ValueError('stock_identity')
            known.setdefault(identity,set()).add(receipt['storyboardSha256'])
    attempts={}
    for path in children(root/'voice-attempts',64):
        if path.suffix!='.json':raise ValueError('attempt_path')
        attempt=read(path)
        if path.stem!=attempt['id'] or attempt['status']!='reserved_before_render':raise ValueError('attempt_identity')
        attempts[path.stem]=attempt['storyboardSha256']
    held=[]
    for folder in children(root/'reel-drafts',64):
        if folder.is_symlink() or not folder.is_dir() or not re.fullmatch(r'reel-article-[a-z0-9-]+',folder.name):raise ValueError('draft_path')
        draft=read(folder/'storyboard.json');receipt=read(folder/'receipt.json')
        digest=sha((folder/'storyboard.json').read_bytes())
        if draft['id']!=folder.name or digest!=receipt['storyboardSha256'] or draft['publicationApproved'] is not False:raise ValueError('draft_changed')
        identity=draft['id']
        if identity in known:
            if known[identity]!={digest}:raise ValueError('existing_stock_source_conflict')
            held.append({'id':identity,'reason':'already_rendered'});continue
        if identity in attempts:
            if attempts[identity]!=digest:raise ValueError('existing_attempt_source_conflict')
            held.append({'id':identity,'reason':'attempt_requires_reconciliation'});continue
        expiry=dt.datetime.fromisoformat(draft['source']['validUntil'].replace('Z','+00:00'))
        if expiry.tzinfo is None:raise ValueError('timezone_required')
        if now>=expiry:held.append({'id':identity,'reason':'expired'});continue
        return {'status':'selected','selected':identity,'storyboardSha256':digest,'validUntil':draft['source']['validUntil'],'held':held}
    return {'status':'no_new_storyboard','selected':None,'held':held}

def reserve(root,plan,run,now):
    current=select(root,now)
    if current!=plan or not plan['selected']:raise ValueError('selection_changed')
    if not re.fullmatch(r'[1-9][0-9]{0,19}',run):raise ValueError('run_identity')
    directory=Path(root)/'voice-attempts'
    if directory.is_symlink():raise ValueError('symlink')
    directory.mkdir(exist_ok=True)
    record={'id':plan['selected'],'status':'reserved_before_render','storyboardSha256':plan['storyboardSha256'],'validUntil':plan['validUntil'],'reservedAt':now.isoformat(),'runId':run,'publicationApproved':False}
    with (directory/(record['id']+'.json')).open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    return record

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent);p.add_argument('--plan',type=Path,required=True);p.add_argument('--reserve-run');p.add_argument('--github-output',type=Path)
    a=p.parse_args();now=dt.datetime.now(dt.timezone.utc)
    if a.reserve_run:result=reserve(a.root,read(a.plan),a.reserve_run,now)
    else:
        result=select(a.root,now)
        with a.plan.open('x') as f:json.dump(result,f,indent=2)
        if a.github_output:
            with a.github_output.open('a') as f:f.write('selected='+str(bool(result['selected'])).lower()+'\n')
    print(json.dumps(result))
