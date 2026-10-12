"""Preserve completed cloud voice renders; never approve or publish them."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

STOP=dt.datetime(2027,9,14,21,59,59,tzinfo=dt.timezone.utc)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def inventory(root):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():raise ValueError('unsafe_root')
    rows=[];total=0
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('symlink')
        if path.is_dir():continue
        if not path.is_file():raise ValueError('not_regular_file')
        size=path.stat().st_size;total+=size
        if size>50_000_000 or total>100_000_000:raise ValueError('media_size_bound')
        rows.append({'file':str(path.relative_to(root)),'bytes':size,'sha256':sha(path.read_bytes())})
    if not 1<=len(rows)<=200:raise ValueError('inventory_bound')
    return rows


def validate(source,cloud,now):
    rows=inventory(source);files={r['file']:r for r in rows}
    receipt=json.loads((source/'receipt.json').read_text())
    if receipt['status']!='storyboard_media_requires_review' or receipt['publicationAttempted'] is not False or receipt['paidInferenceCalls']!=0:raise ValueError('render_state')
    identity=receipt['id']
    if not re.fullmatch(r'reel-article-[a-z0-9-]+',identity):raise ValueError('render_identity')
    if not dt.datetime.fromisoformat(receipt['startedAt'])<=dt.datetime.fromisoformat(receipt['finishedAt'])<=now<dt.datetime.fromisoformat(receipt['validUntil']):raise ValueError('expired_or_future_render')
    listed=receipt['files']
    if len({r['file'] for r in listed})!=len(listed) or set(files)!={r['file'] for r in listed}|{'receipt.json','storyboard.json'}:raise ValueError('unexpected_files')
    if any(files[r['file']]['sha256']!=r['sha256'] for r in listed):raise ValueError('file_changed')
    draft=json.loads((source/'storyboard.json').read_text())
    if files['storyboard.json']['sha256']!=receipt['storyboardSha256'] or draft['id']!=identity or draft['publicationApproved'] is not False or draft['source']['validUntil']!=receipt['validUntil']:raise ValueError('storyboard_changed')
    if cloud.get('repository')!='MathCSN/voyagesansdetour' or cloud.get('artifactName')!='vsd-storyboard-media':raise ValueError('cloud_origin')
    run=cloud['run']
    if run['status']!='completed' or run['conclusion']!='success' or run['headBranch']!='main' or not re.fullmatch(r'[a-f0-9]{40}',run['headSha']):raise ValueError('cloud_run_not_successful')
    if run['url']!=f"https://github.com/MathCSN/voyagesansdetour/actions/runs/{run['databaseId']}":raise ValueError('cloud_run_url')
    if cloud['receiptSha256']!=files['receipt.json']['sha256']:raise ValueError('cloud_receipt_changed')
    return identity,receipt,rows


def adopt(source,output,cloud,now):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=STOP:return {'status':'period_ended','changed':False}
    source=Path(source);output=Path(output)
    identity,receipt,rows=validate(source,cloud,now)
    if output.name!=identity:raise ValueError('output_identity')
    if output.is_symlink():raise ValueError('output_symlink')
    if output.exists():
        if (output/'stock.json').is_symlink():raise ValueError('stock_symlink')
        stored=json.loads((output/'stock.json').read_text())
        if stored['files']!=rows or inventory(output/'media')!=rows or stored['cloud']!=cloud:raise ValueError('existing_stock_conflict')
        return {'status':'already_preserved_not_approved','changed':False,'id':identity}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.voice-stock-',dir=output.parent) as temp:
        staged=Path(temp)/'stock';staged.mkdir()
        shutil.copytree(source,staged/'media')
        if inventory(staged/'media')!=rows:raise ValueError('copy_changed')
        record={'schemaVersion':1,'id':identity,'status':'rendered_requires_review','preservedAt':now.isoformat(),
                'validUntil':receipt['validUntil'],'publicationApproved':False,'publicationAttempted':False,
                'cloud':cloud,'files':rows,'remaining':['listening_review','voice_selection','format_and_rights_review','public_media_promotion','publication_admission']}
        (staged/'stock.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        staged.rename(output)
    return {'status':'preserved_not_approved','changed':True,'id':identity,'fileCount':len(rows)}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cloud-proof',type=Path,required=True)
    args=parser.parse_args();now=dt.datetime.now(dt.timezone.utc)
    if now>=STOP:print(json.dumps({'status':'period_ended','changed':False}))
    else:print(json.dumps(adopt(args.source,args.output,json.loads(args.cloud_proof.read_text()),now)))
