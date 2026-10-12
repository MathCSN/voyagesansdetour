"""Bounded draft intake. No RSS edits, approvals or social provider calls."""
import datetime as dt
import hashlib
import json
from pathlib import Path
from pin_draft import render,HERE

STOP=dt.datetime(2027,9,14,21,59,59,tzinfo=dt.timezone.utc)

def intake(articles,reserved,output,now,renderer=render):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=STOP:return {'status':'period_ended','created':0}
    slugs=[a['slug'] for a in articles]
    if len(slugs)!=len(set(slugs)):raise ValueError('duplicate_article')
    output=Path(output)
    if output.is_symlink():raise ValueError('output_symlink')
    known=set(reserved)
    if output.exists():
        for folder in output.iterdir():
            if folder.is_symlink() or not folder.is_dir():raise ValueError('invalid_draft_directory')
            manifest=json.loads((folder/'draft.json').read_text())
            if manifest['status']!='draft_requires_review' or manifest['publicationApproved'] is not False:raise ValueError('unexpected_draft_state')
            slug=manifest['id'].removeprefix('pin-')
            if folder.name!='pin-'+slug or manifest['targetUrl']!='https://voyagesansdetour.fr/portugal/'+slug+'/':raise ValueError('draft_identity')
            if (folder/'pin.jpg').is_symlink() or hashlib.sha256((folder/'pin.jpg').read_bytes()).hexdigest()!=manifest['imageSha256']:raise ValueError('draft_image_changed')
            known.add(slug)
    for article in sorted(articles,key=lambda a:(a.get('publishedOn',''),a['slug']),reverse=True):
        if article['slug'] in known:continue
        # The public catalogue is the input; a queue/candidate is never selected.
        target=renderer(article,output)
        return {'status':'draft_created_not_published','created':1,'id':target.name,'publicationAttempted':False}
    return {'status':'no_new_article','created':0,'publicationAttempted':False}

if __name__=='__main__':
    articles=json.loads((HERE.parents[1]/'site-src/articles.json').read_text())
    config=json.loads((HERE/'pin-reservations.json').read_text())
    if config.get('schemaVersion')!=1:raise ValueError('reservation_schema')
    print(json.dumps(intake(articles,config['reservedSlugs'],HERE/'pin-drafts',dt.datetime.now(dt.timezone.utc))))
