"""Stage one selected voice; verify public bytes before recording completion."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import urllib.request
import urllib.error
import stock
import promote_selected
from select_catalogue import write_once

ORIGIN='https://voyagesansdetour.fr'

def read_public(url,limit):
    try:
        with urllib.request.urlopen(url,timeout=20) as response:
            if response.status!=200 or response.url!=url:raise ValueError('unexpected_public_response')
            return response.read(limit+1)
    except urllib.error.HTTPError as error:
        if error.code==404:return None
        raise


def run(root,site,now,fetcher=read_public,stage=promote_selected.stage):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=stock.STOP:return {'status':'period_ended','changed':False,'needsDeployment':False}
    root,site=Path(root),Path(site)
    for path in (root,site,root/'voice-stock',root/'voice-revisions'):
        if path.is_symlink():raise ValueError('symlink')
    families=sorted((root/'voice-revisions').iterdir()) if (root/'voice-revisions').exists() else []
    if len(families)>16:raise ValueError('revision_bound')
    for path in families:
        if path.is_symlink() or not path.is_dir() or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',path.name):raise ValueError('revision_path')
    count=0
    for family in [root/'voice-stock']+families:
        if not family.exists():continue
        for candidate in sorted(family.iterdir()):
            count+=1
            if count>64:raise ValueError('stock_bound')
            if candidate.is_symlink() or not candidate.is_dir() or not re.fullmatch(r'reel-article-[a-z0-9-]+',candidate.name):raise ValueError('candidate_path')
            selection=candidate/'selection.json';proof_path=candidate/'public-media-proof.json'
            if selection.is_symlink() or proof_path.is_symlink():raise ValueError('symlink')
            if not selection.exists():continue
            selected=json.loads(selection.read_text());selection_hash=stock.sha(selection.read_bytes())
            if proof_path.exists():
                proof=json.loads(proof_path.read_text())
                if proof['selectionSha256']!=selection_hash or proof['contentId']!=candidate.name:raise ValueError('public_proof_conflict')
                continue
            if now>=dt.datetime.fromisoformat(selected['validUntil']):continue
            result=stage(candidate,site,now)
            manifest=json.loads((site/'public-media.json').read_text())
            item=next(x for x in manifest['items'] if x['contentId']==result['mediaId'])
            verified=[];missing=[]
            for asset in item['files']:
                url=ORIGIN+'/social-media/production/'+result['mediaId']+'/'+asset['name']
                raw=fetcher(url,asset['bytes'])
                if raw is None:missing.append(url);continue
                if len(raw)!=asset['bytes'] or stock.sha(raw)!=asset['sha256']:raise ValueError('public_bytes_conflict')
                verified.append({'url':url,'sha256':asset['sha256'],'bytes':len(raw)})
            if missing:return {'status':'staged_awaiting_deployment','changed':result['changed'],'needsDeployment':True,'id':candidate.name,'missingCount':len(missing),'publicationAttempted':False}
            proof={'schemaVersion':1,'status':'public_bytes_verified','contentId':candidate.name,'selectionSha256':selection_hash,'checkedAt':now.isoformat(),'validUntil':selected['validUntil'],'files':verified,'socialPublicationAttempted':False}
            write_once(proof_path,(json.dumps(proof,ensure_ascii=False,indent=2)+'\n').encode())
            return {'status':'public_bytes_confirmed','changed':True,'needsDeployment':False,'id':candidate.name,'publicationAttempted':False}
    return {'status':'no_pending_selected_media','changed':False,'needsDeployment':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--site',type=Path,required=True);parser.add_argument('--github-output',type=Path);args=parser.parse_args()
    result=run(args.root,args.site,dt.datetime.now(dt.timezone.utc))
    if args.github_output:
        with args.github_output.open('a') as f:f.write('needs_deployment='+str(result['needsDeployment']).lower()+'\n')
    print(json.dumps(result))
