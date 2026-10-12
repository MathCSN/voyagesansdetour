"""Verify the evidence for a new guide before calendar admission.

This gate does not approve, enqueue, render, or publish content.
"""
import datetime as dt
import re
from guide_review import public_blocks, validate_checks
from source_draft import require, HARD_STOP, source_fingerprint
from update_draft import digest
import editorial_queue as q


def qualify(proposal, known, now, fetcher=source_fingerprint):
    require(now.tzinfo is not None and now < HARD_STOP, 'guide_admission_period')
    require(proposal.get('status') in {'guide_ready_for_pilot_review','revised_guide_ready_for_pilot_review'}
            and proposal.get('publicationApproved') is False, 'guide_admission_held')
    article=proposal['article'];facts=proposal['facts'];review=proposal['blockReview']
    require(article['slug'] not in {a['slug'] for a in known}, 'guide_admission_duplicate')
    q.validate_article(article,{a['slug'] for a in known})
    checked=dt.date.fromisoformat(article['sourcesCheckedOn'])
    require(dt.timedelta(0)<=now.astimezone(q.PARIS).date()-checked<=dt.timedelta(days=1), 'guide_admission_stale')
    blocks=public_blocks(article,proposal['citations'],facts)
    require(review['articleSha256']==digest(article) and review['blocksSha256']==digest(blocks), 'guide_admission_changed_text')
    require(review.get('factsSha256')==digest(facts), 'guide_admission_changed_evidence')
    decision=validate_checks({'checks':review['checks']},blocks)
    require(decision['supported'] and review.get('supported') is True and not review.get('issues')
            and not review.get('policyIssues'), 'guide_admission_failed_review')
    require(not any(re.search(r'\buniques?\b',b['text'],re.I) for b in blocks), 'guide_admission_policy')
    ids={f['id'] for f in facts}
    require(len(ids)==len(facts) and all(b['evidence'] and set(b['evidence'])<=ids for b in blocks), 'guide_admission_evidence_coverage')
    manifest=proposal['sourceManifest'];urls={s['url'] for s in article['sources']}
    require(len(manifest)==len(urls) and {s['url'] for s in manifest}==urls, 'guide_admission_sources')
    observed={}
    for source in manifest:
        require(isinstance(source['sha256'],str) and q.HASH.fullmatch(source['sha256']), 'guide_admission_source_hash')
        document=fetcher(source['url'])
        require(document['sha256']==source['sha256'], 'guide_admission_source_changed')
        observed[source['url']]=document['text']
    for fact in facts:
        context=fact['sourceContext'];url=context['url']
        require(url in observed and fact['quote'] and fact['quote'] in observed[url]
                and context['excerpt'] and context['excerpt'] in observed[url], 'guide_admission_quote_changed')
    return {'status':'evidence_revalidated_not_admitted','articleSha256':digest(article),
            'proposalSha256':digest(proposal),'verifiedAt':q.iso(now),
            'sources':manifest,'publicationApproved':False,'publicationAttempted':False}


def persist_qualification(proposal, known, now, output, fetcher=source_fingerprint):
    if proposal.get('status') not in {'guide_ready_for_pilot_review','revised_guide_ready_for_pilot_review'}:
        return 'review_held'
    evidence=qualify(proposal,known,now,fetcher)
    target=output/'guide-admission-evidence.json'
    require(not target.exists(), 'guide_admission_evidence_exists')
    import json
    with target.open('x') as handle:
        handle.write(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    return evidence['status']
