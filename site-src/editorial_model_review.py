"""Validate the evidence connecting a model-reviewed addition to its patch.

This is a bounded automatic review method, not a claim of human review or
infallible factual verification. Fresh source bytes are checked by the caller.
"""
import datetime as dt
import editorial_queue as q

METHOD='source-grounded-model-review-v1'


def validate(patch):
    evidence=patch['reviewEvidence']
    q.require(set(evidence)=={'proposal','entailment','novelty','observedAt'}, 'Model evidence schema')
    proposal=evidence['proposal']
    q.require(proposal['schemaVersion']==2 and proposal['status']=='update_ready_for_pilot_review' and proposal['publicationApproved'] is False, 'Model proposal not eligible')
    q.require(proposal['guideSlug']==patch['slug'] and proposal['baseArticleSha256']==patch['baseArticleSha256'], 'Model proposal base conflict')
    observed=q.instant(evidence['observedAt']);reviewed=q.instant(patch['reviewedAt'])
    q.require(observed<=reviewed<=observed+dt.timedelta(hours=2), 'Model evidence stale or future')
    facts=proposal['facts'];ids=[f['id'] for f in facts]
    q.require(1<=len(ids)<=5 and len(ids)==len(set(ids)) and q.digest(facts)==proposal['factsSha256'], 'Model facts conflict')
    review=proposal['review']
    q.require(review['supported'] is True and review['issues']==[] and sorted(review['checkedClaimIds'])==sorted(ids), 'Model prose review rejected')
    matching=[s for s in proposal['additions'] if s['paragraph']==patch['paragraph'] and s['targetSectionId']==patch['sectionId']]
    q.require(len(matching)==1 and matching[0]['claims'] and set(matching[0]['claims'])<=set(ids), 'Model paragraph not reviewed')
    for rows,flag in ((evidence['entailment']['checks'],'entailed'),(evidence['novelty']['decisions'],'supported')):
        row_ids=[r['id'] for r in rows]
        q.require(len(row_ids)==len(set(row_ids)), 'Model duplicate review identity')
        indexed={r['id']:r for r in rows}
        for identity in ids:
            q.require(identity in indexed and indexed[identity][flag] is True, 'Model fact not approved')
            row=indexed[identity]
            if flag=='entailed':
                q.require(row['unsupportedDetails']==[], 'Model unsupported details')
            else:
                q.require(row['newInformation'] is True and row['useful'] is True, 'Model fact not novel or useful')
    selected=[f for f in facts if f['id'] in matching[0]['claims']]
    q.require({f['sourceContext']['url'] for f in selected}=={s['url'] for s in patch['sources']}, 'Model source coverage')
    return selected


def check_quotes(facts,source_texts,article):
    labels={s['url']:s.get('label','') for s in article['sources']}
    for fact in facts:
        context=fact['sourceContext'];text=source_texts[context['url']]
        quote=fact['quote']
        q.require(isinstance(quote,str) and 15<=len(quote)<=350 and quote in text, 'Model quote absent from fresh source')
        position=text.find(quote)
        expected=text[max(0,position-400):position+len(quote)+400]
        q.require(context['label']==labels[context['url']] and context['excerpt']==expected, 'Model source context changed')
