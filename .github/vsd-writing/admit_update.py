"""Admit at most one freshly grounded addition into the existing release path."""
import datetime as dt
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'site-src'))
import editorial_queue as q
import editorial_update as u
import editorial_model_review as review
from autonomous_editorial import HARD_STOP, source_fingerprint


# A guide may be written up to this long before its release slot (its review stays valid 48 h).
GUIDE_LOOKAHEAD=dt.timedelta(hours=30)


def latest_release(articles,queue,ledger):
    past=[dt.datetime.combine(dt.date.fromisoformat(a.get('publishedOn','2026-09-14')),dt.time(),q.PARIS).astimezone(q.UTC) for a in articles]
    past += [q.instant(x['promotedAt']) for x in queue['promotions']]
    past += [q.instant(x['appliedAt']) for x in ledger['updates']]
    return max(past) if past else None


def cadence_open(articles,queue,ledger,now):
    if now>=HARD_STOP or any(x['receipt'] is None for x in queue['promotions']+ledger['updates']):
        return False
    latest=latest_release(articles,queue,ledger)
    if latest and now.astimezone(q.PARIS).date()<q.release_day(latest):return False
    # Already reserved guides keep their calendar priority.
    if any(q.instant(x['releaseAt'])<=now+q.RELEASE_INTERVAL for x in queue['drafts']):return False
    return True


def guide_release_at(articles,queue,ledger,now):
    """Next release instant for one new guide, or None when the calendar is full.

    One reserved guide at a time; it may be written the day before its slot so that a
    held attempt still leaves a full day to retry without missing the slot."""
    if now>=HARD_STOP or queue['drafts'] or any(x['receipt'] is None for x in queue['promotions']+ledger['updates']):
        return None
    latest=latest_release(articles,queue,ledger)
    slot=dt.datetime.combine(q.release_day(latest),dt.time(),q.PARIS).astimezone(q.UTC) if latest else now
    release=max(now,slot)
    return release if release<=now+GUIDE_LOOKAHEAD and release<HARD_STOP else None


def prepare(proposal,entailment,novelty,observed_at,article,now,fetcher=source_fingerprint):
    q.require(proposal['baseArticleSha256']==q.digest(article),'Admission base changed')
    section=proposal['additions'][0]
    targets=[s for s in article['sections'] if s['id']==section['targetSectionId']]
    q.require(len(targets)==1 and targets[0]['paragraphs'],'Admission target absent')
    claims=set(section['claims'])
    selected=[f for f in proposal['facts'] if f['id'] in claims]
    urls=sorted({f['sourceContext']['url'] for f in selected})
    q.require(urls and set(urls)<={s['url'] for s in article['sources']},'Admission source outside article')
    sources=[]
    for url in urls:
        observed=fetcher(url)
        manifests=[s for s in proposal['sourceManifest'] if s['url']==url]
        q.require(len(manifests)==1,'Admission source manifest missing')
        manifest=manifests[0]
        q.require(u.source_digest(url,observed['text'])==manifest.get('normalizedSha256') if 'normalizedSha256' in manifest else observed['sha256']==manifest['sha256'],'Admission source changed')
        sources.append({'url':url,'sha256':u.source_digest(url,observed['text']),'normalization':'visible-text-cp-node-v1'})
    evidence={'proposal':proposal,'entailment':entailment,'novelty':novelty,'observedAt':observed_at}
    patch={'schemaVersion':2,'id':'auto-'+q.digest({'base':proposal['baseArticleSha256'],'paragraph':section['paragraph']})[:24],
           'slug':article['slug'],'baseArticleSha256':q.digest(article),'sectionId':section['targetSectionId'],
           'afterParagraphSha256':q.digest(targets[0]['paragraphs'][-1]),'paragraph':section['paragraph'],
           'sources':sources,'reviewedAt':q.iso(now),'validUntil':q.iso(min(now+dt.timedelta(hours=48),HARD_STOP)),
           'reviewMethod':review.METHOD,'reviewEvidence':evidence}
    patch['approvalSha256']=u.approval_hash(patch)
    review.validate(patch)
    return patch


def run(out,root=u.ROOT,now=None,fetcher=source_fingerprint):
    now=now or dt.datetime.now(q.UTC)
    articles,queue=q.load(root,now)
    ledger=q.read_json(root/'editorial-updates.json')
    if not cadence_open(articles,queue,ledger,now):return {'status':'cadence_or_pending_hold','changed':False}
    proposal_path=out/'update-proposal.json'
    if not proposal_path.exists():return {'status':'no_proposal','changed':False}
    proposal=q.read_json(proposal_path)
    if proposal.get('status')!='update_ready_for_pilot_review':return {'status':'review_held','changed':False}
    report=q.read_json(out/'discovery-report.json')
    q.require(report['status']==proposal['status'] and report['guideSlug']==proposal['guideSlug'] and report['publicationAttempted'] is False,'Admission report conflict')
    article=next(a for a in articles if a['slug']==proposal['guideSlug'])
    patch=prepare(proposal,q.read_json(out/'quote-entailment.json'),q.read_json(out/'fact-review.json'),report['observedAt'],article,now,fetcher)
    updated,history,changed=u.apply_update(articles,ledger,patch,now,fetcher)
    if changed:
        q.validate(updated,queue,now)
        target=root/'editorial-update-patches'/(patch['id']+'.json')
        q.require(not target.exists(),'Admission identity already persisted')
        q.write_json(target,patch)
        q.write_json(root/'articles.json',updated)
        q.write_json(root/'editorial-updates.json',history)
    return {'status':'admitted' if changed else 'already_present','changed':changed,'patchId':patch['id']}


if __name__=='__main__':
    out=Path(os.environ['REPORT_DIR'])
    try:result=run(out)
    except Exception as error:
        result={'status':'held_no_retry','changed':False,'errorType':type(error).__name__}
    (out/'admission-report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as output:output.write('changed='+str(result['changed']).lower()+'\n')
    raise SystemExit(1 if result['status']=='held_no_retry' else 0)
