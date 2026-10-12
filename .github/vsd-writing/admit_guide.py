"""Admit one freshly qualified guide through the existing verified release queue."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
from guide_admission import qualify
from admit_update import cadence_open
from source_draft import HARD_STOP, source_fingerprint
import editorial_queue as q

ROOT=Path(__file__).resolve().parents[2]/'site-src'


def run(out,root=ROOT,now=None,fetcher=source_fingerprint):
    now=now or dt.datetime.now(q.UTC).replace(microsecond=0)
    if now>=HARD_STOP:return {'status':'period_ended','changed':False}
    paths=[out/name for name in ('guide-proposal.json','guide-revised-proposal.json') if (out/name).exists()]
    if not paths:return {'status':'no_proposal','changed':False}
    q.require(len(paths)==1,'Ambiguous guide proposal')
    proposal=q.read_json(paths[0])
    if proposal.get('status') not in {'guide_ready_for_pilot_review','revised_guide_ready_for_pilot_review'}:
        return {'status':'review_held','changed':False}
    articles,queue=q.load(root,now)
    slug=proposal['article']['slug']
    identity='generated-'+slug
    prior=[d for d in queue['drafts'] if d['id']==identity]
    if prior:
        q.require(len(prior)==1 and q.digest(prior[0]['article'])==q.digest(proposal['article']),'Admitted guide changed')
        return {'status':'already_admitted','changed':False,'id':identity}
    if any(a['slug']==slug for a in articles):return {'status':'already_published','changed':False,'id':identity}
    ledger=q.read_json(root/'editorial-updates.json')
    if not cadence_open(articles,queue,ledger,now):return {'status':'cadence_or_pending_hold','changed':False}
    known=articles+[d['article'] for d in queue['drafts']]
    known += [q.read_json(p)['article'] for p in (root/'editorial-candidates').glob('*.json')]
    evidence=qualify(proposal,known,now,fetcher)
    draft={'id':identity,'article':proposal['article'],'releaseAt':q.iso(now),
           'validUntil':q.iso(min(now+dt.timedelta(hours=48),HARD_STOP)),
           'approval':{'approvedAt':q.iso(now),'sha256':''}}
    draft['approval']['sha256']=q.approval_hash(draft)
    updated=copy.deepcopy(queue);updated['drafts'].append(draft)
    q.validate(articles,updated,now)
    proof=root/'editorial-guide-evidence'/(identity+'.json')
    q.require(not proof.parent.is_symlink() and not proof.exists(),'Guide evidence already exists')
    proof.parent.mkdir(exist_ok=True)
    # Evidence first, queue last. Interrupted writes leave an explicit hold,
    # never a queued article without its bound proposal and review.
    with proof.open('x') as handle:
        json.dump({'schemaVersion':1,'proposal':proposal,'verification':evidence,
                   'draftSha256':q.digest(draft)},handle,ensure_ascii=False,indent=2)
        handle.write('\n')
    q.write_json(root/'editorial-queue.json',updated)
    return {'status':'admitted_not_published','changed':True,'id':identity}


if __name__=='__main__':
    out=Path(os.environ['REPORT_DIR'])
    try:result=run(out)
    except Exception as error:result={'status':'held_no_retry','changed':False,'errorType':type(error).__name__}
    (out/'guide-calendar-report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as handle:handle.write('changed='+str(result['changed']).lower()+'\n')
    raise SystemExit(1 if result['status']=='held_no_retry' else 0)
