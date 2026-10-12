"""Apply one explicitly reviewed, additive article update without replacing history."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import urllib.parse

import editorial_queue as q
from autonomous_editorial import source_fingerprint, HARD_STOP

ROOT=Path(__file__).resolve().parent

def source_digest(url,text):
    # CP exposes the backend node in visible footer text. Only this exact
    # terminal infrastructure marker is excluded; travel conditions are kept.
    if urllib.parse.urlsplit(url).hostname=='www.cp.pt':
        text=re.sub(r'\s+Node: vmusitecpprd\d+:8085: Hidden\s*$', '', text)
    return hashlib.sha256(text.encode()).hexdigest()

def approval_hash(patch):
    return q.digest({k:v for k,v in patch.items() if k!='approvalSha256'})

def apply_update(articles, ledger, patch, now, fetcher=source_fingerprint):
    import editorial_model_review as model_review
    model_method=isinstance(patch,dict) and patch.get('reviewMethod')==model_review.METHOD
    q.require(isinstance(patch,dict) and set(patch)-({'reviewEvidence'} if model_method else set())=={'schemaVersion','id','slug','baseArticleSha256','sectionId','afterParagraphSha256','paragraph','sources','reviewedAt','validUntil','reviewMethod','approvalSha256'},'Invalid update patch')
    q.require(patch['schemaVersion']==(2 if model_method else 1) and q.SLUG.fullmatch(patch['id']) and q.SLUG.fullmatch(patch['slug']),'Invalid update identity')
    q.require(patch['approvalSha256']==approval_hash(patch),'Update changed after review')
    q.require(isinstance(ledger,dict) and set(ledger)=={'schemaVersion','updates'} and ledger['schemaVersion']==1 and isinstance(ledger['updates'],list),'Invalid update ledger')
    ids=[e['id'] for e in ledger['updates']]
    q.require(len(ids)==len(set(ids)),'Duplicate update history')
    prior=next((e for e in ledger['updates'] if e['id']==patch['id']),None)
    if prior:
        q.require(prior['approvalSha256']==patch['approvalSha256'],'Update identity conflict')
        return articles,ledger,False
    q.require(q.instant(patch['reviewedAt'])<=now<q.instant(patch['validUntil'])<=HARD_STOP,'Update review expired or future')
    q.require(q.instant(patch['validUntil'])-q.instant(patch['reviewedAt'])<=dt.timedelta(days=3),'Update review window too long')
    q.require(model_method or patch['reviewMethod']=='agent-source-review-v1','Unqualified update review method')
    reviewed_facts=model_review.validate(patch) if model_method else []
    matches=[a for a in articles if a['slug']==patch['slug']]
    q.require(len(matches)==1 and q.digest(matches[0])==patch['baseArticleSha256'],'Base article changed')
    article=matches[0]
    q.require(isinstance(patch['paragraph'],str) and 60<=len(patch['paragraph'])<=1800,'Invalid update paragraph')
    q.require(not any(patch['paragraph'] in s.get('paragraphs',[]) for s in article['sections']),'Update text already exists without receipt')
    source_urls={s['url'] for s in article['sources']}
    q.require(isinstance(patch['sources'],list) and patch['sources'],'Update source missing')
    seen=set();source_texts={}
    for source in patch['sources']:
        q.require(set(source)=={'url','sha256','normalization'} and source['normalization']=='visible-text-cp-node-v1' and source['url'] in source_urls and source['url'] not in seen and q.HASH.fullmatch(source['sha256']),'Invalid update source')
        seen.add(source['url'])
        observed=fetcher(source['url'])
        source_texts[source['url']]=observed['text'][:7000]
        q.require(source_digest(source['url'],observed['text'])==source['sha256'],'Update source changed since review')
    if model_method:
        model_review.check_quotes(reviewed_facts,source_texts,article)
    result=copy.deepcopy(articles);updated=next(a for a in result if a['slug']==patch['slug'])
    sections=[s for s in updated['sections'] if s['id']==patch['sectionId']]
    q.require(len(sections)==1,'Update target section missing')
    section=sections[0]
    anchors=[i for i,p in enumerate(section['paragraphs']) if q.digest(p)==patch['afterParagraphSha256']]
    q.require(len(anchors)==1,'Update anchor changed')
    section['paragraphs'].insert(anchors[0]+1,patch['paragraph'])
    updated['updatedOn']=q.today(now)
    history=copy.deepcopy(ledger)
    history['updates'].append({'id':patch['id'],'slug':patch['slug'],'approvalSha256':patch['approvalSha256'],
        'beforeSha256':q.digest(article),'afterSha256':q.digest(updated),'appliedAt':q.iso(now),'receipt':None})
    return result,history,True

def apply_file(patch_path,root=ROOT,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    articles,queue=q.load(root,now)
    q.require(not any(p['receipt'] is None for p in queue['promotions']),'Unconfirmed article promotion blocks update')
    ledger_path=root/'editorial-updates.json'
    ledger=q.read_json(ledger_path) if ledger_path.exists() else {'schemaVersion':1,'updates':[]}
    q.require(not any(e['receipt'] is None for e in ledger['updates']), 'Unconfirmed update blocks a new application')
    patch=q.read_json(patch_path)
    articles,ledger,changed=apply_update(articles,ledger,patch,now)
    if changed:
        q.validate(articles,queue,now)
        q.write_json(root/'articles.json',articles)
        q.write_json(ledger_path,ledger)
    return changed

def record_receipt(articles,ledger,patch,body,now):
    """Confirm this addition's visible paragraph, not an unrelated full-build hash."""
    import html
    q.require(patch['approvalSha256']==approval_hash(patch),'Update changed after review')
    matches=[e for e in ledger['updates'] if e['id']==patch['id']]
    q.require(len(matches)==1 and matches[0]['approvalSha256']==patch['approvalSha256'],'Applied update missing')
    entry=matches[0]
    article=next(a for a in articles if a['slug']==patch['slug'])
    q.require(q.digest(article)==entry['afterSha256'],'Article changed before update confirmation')
    q.require(q.instant(entry['appliedAt'])<=now<q.instant(patch['validUntil']),'Update confirmation outside review window')
    expected='<p>'+html.escape(patch['paragraph'])+'</p>'
    q.require(body.decode('utf-8').count(expected)==1,'Published update paragraph missing or duplicated')
    result=copy.deepcopy(ledger)
    target=next(e for e in result['updates'] if e['id']==patch['id'])
    if target['receipt'] is None:
        target['receipt']={'verifiedAt':q.iso(now),'url':q.ORIGIN+'/portugal/'+patch['slug']+'/',
            'htmlSha256':hashlib.sha256(body).hexdigest(),'paragraphSha256':q.digest(patch['paragraph']),
            'verification':'exact-paragraph-presence-v1'}
    return result

def confirm_file(patch_path,root=ROOT,fetcher=q.fetch_public,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    patch=q.read_json(patch_path)
    q.require(q.SLUG.fullmatch(patch['slug']),'Invalid update slug')
    articles,_=q.load(root,now)
    ledger=q.read_json(root/'editorial-updates.json')
    body=fetcher(q.ORIGIN+'/portugal/'+patch['slug']+'/')
    result=record_receipt(articles,ledger,patch,body,now)
    q.write_json(root/'editorial-updates.json',result)
    return next(e['receipt'] for e in result['updates'] if e['id']==patch['id'])


def pending_patches(articles, ledger, read_patch, now, margin=0):
    """Validate durable unconfirmed additions before any cloud deployment."""
    q.require(ledger.get('schemaVersion') == 1 and isinstance(ledger.get('updates'), list), 'Invalid update ledger')
    ids=[e['id'] for e in ledger['updates']]
    q.require(len(ids)==len(set(ids)), 'Duplicate update history')
    result=[]
    for entry in ledger['updates']:
        if entry['receipt'] is not None:
            continue
        q.require(isinstance(entry['id'],str) and q.SLUG.fullmatch(entry['id']), 'Invalid pending update identity')
        patch=read_patch(entry['id'])
        q.require(patch['id']==entry['id'] and patch['slug']==entry['slug'], 'Pending update identity conflict')
        q.require(patch['approvalSha256']==approval_hash(patch)==entry['approvalSha256'], 'Pending update approval conflict')
        q.require(q.instant(patch['reviewedAt'])<=q.instant(entry['appliedAt'])<=now and now+dt.timedelta(seconds=margin)<q.instant(patch['validUntil'])<=HARD_STOP, 'Pending update expired or future')
        matches=[a for a in articles if a['slug']==entry['slug']]
        q.require(len(matches)==1 and q.digest(matches[0])==entry['afterSha256'], 'Pending update article changed')
        result.append(patch)
    return result


def check_pending_file(root=ROOT, now=None, margin=900, revalidate=False):
    now=now or dt.datetime.now(dt.timezone.utc)
    articles,_=q.load(root,now)
    ledger_path=root/'editorial-updates.json'
    ledger=q.read_json(ledger_path) if ledger_path.exists() else {'schemaVersion':1,'updates':[]}
    patches=pending_patches(articles,ledger,lambda identity:q.read_json(root/'editorial-update-patches'/(identity+'.json')),now,margin)
    if revalidate:
        for patch in patches:
            for source in patch['sources']:
                observed=source_fingerprint(source['url'])
                q.require(source_digest(source['url'],observed['text'])==source['sha256'], 'Pending update source changed')
    return patches


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['check','confirm'])
    args=parser.parse_args()
    patches=check_pending_file(margin=900 if args.action=='check' else 0,revalidate=args.action=='check')
    if args.action=='confirm':
        for patch in patches:
            confirm_file(ROOT/'editorial-update-patches'/(patch['id']+'.json'))
    print(json.dumps({'action':args.action,'pendingUpdateCount':len(patches)}))
