"""Render source-bound storyboards into unpublished voice/video candidates."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
import tempfile

import pilot
import compose
sys.path.insert(0, str(pilot.HERE.parent))
from reel_intake import PublicArticle, fetch_public, normalized, digest, ORIGIN


def prepare(folder, now, fetcher=fetch_public):
    folder=Path(folder)
    if folder.is_symlink():raise ValueError('storyboard_symlink')
    for name in ('storyboard.json','receipt.json'):
        if (folder/name).is_symlink():raise ValueError('storyboard_symlink')
    raw=(folder/'storyboard.json').read_bytes()
    receipt=json.loads((folder/'receipt.json').read_text());draft=json.loads(raw)
    if pilot.sha(raw)!=receipt['storyboardSha256']:raise ValueError('storyboard_changed')
    if draft['publicationApproved'] is not False or draft['status']!='storyboard_requires_media_review':raise ValueError('unexpected_state')
    if draft['id']!=folder.name:raise ValueError('identity_changed')
    source=draft['source'];slug=source['slug']
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug):raise ValueError('invalid_slug')
    checked=dt.date.fromisoformat(source['sourcesCheckedOn'])
    expiry=min(dt.datetime.combine(checked+dt.timedelta(days=30),dt.time(),dt.timezone.utc),pilot.STOP)
    if dt.datetime.fromisoformat(source['validUntil'])!=expiry or checked>now.date() or now>=expiry:raise ValueError('source_review_expired')
    articles=json.loads((pilot.HERE.parents[2]/'site-src/articles.json').read_text())
    matches=[a for a in articles if a['slug']==slug]
    if len(matches)!=1 or digest(matches[0])!=source['articleSha256']:raise ValueError('article_changed')
    article=matches[0];narration=draft['narration']
    if narration['hook']!=article['title'] or narration['closing']!='Retrouvez le guide et ses sources sur Voyage Sans Détour.':raise ValueError('narration_changed')
    if len(narration['excerpts'])!=2:raise ValueError('excerpt_count')
    for excerpt in narration['excerpts']:
        sections=[s for s in article['sections'] if s['id']==excerpt['sectionId']]
        if len(sections)!=1 or sections[0]['paragraphs'][excerpt['paragraphIndex']]!=excerpt['text']:raise ValueError('excerpt_changed')
    url=ORIGIN+'/portugal/'+slug+'/'
    if draft['targetUrl']!=url:raise ValueError('target_changed')
    public=fetcher(url);page=PublicArticle();page.feed(public.decode('utf-8'))
    if page.canonicals!=[url] or not all(normalized(e['text']) in page.paragraphs for e in narration['excerpts']):raise ValueError('public_excerpt_changed')
    # Short exact contiguous chunks avoid unreadably dense captions. Their
    # measured audio boundaries are also the video caption boundaries.
    chunks=[];headings=[];badges=[]
    parts=[narration['hook']]+[e['text'] for e in narration['excerpts']]+[narration['closing']]
    labels=[('Préparez', 'votre départ.'),('Dans le sac,','de la place.'),('Avant de poser','vos bagages.'),('Le guide', 'et ses sources.')]
    badge_labels=['LE GUIDE BAGAGES','VOYAGER LÉGER','CONSIGNES EN GARE','POUR ALLER PLUS LOIN']
    for index,part in enumerate(parts):
        for sentence in re.split(r'(?<=[.!?])\s+',part):
            words=re.findall(r'\S+(?:[ \u00a0\u202f]+[?!:;](?=\s|$))?',sentence)
            # Balance chunks so a final fragment such as “24 heures” is not
            # isolated on its own card. Keep every word in its original order.
            while words:
                total=len(' '.join(words));count=(total+69)//70
                target=total/count
                chunk=[]
                while words:
                    candidate=' '.join(chunk+[words[0]])
                    if chunk and (len(candidate)>70 or abs(len(' '.join(chunk))-target)<abs(len(candidate)-target)):
                        break
                    chunk.append(words.pop(0))
                chunks.append(' '.join(chunk));headings.append(labels[index]);badges.append(badge_labels[index])
    if normalized(' '.join(chunks))!=normalized(' '.join(parts)):raise ValueError('text_changed_during_chunking')
    return draft,chunks,headings,badges,pilot.sha(raw),pilot.sha(public)


def run(folder, output, now):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=pilot.STOP:return {'status':'period_ended','generated':0}
    output=Path(output)
    if output.exists() or output.is_symlink():raise ValueError('existing_output_preserved')
    draft,sentences,headings,badges,story_hash,public_hash=prepare(folder,now)
    # This first layout is qualified for the bagage storyboard only. Other
    # topics need their own truthful scene headings, not these bagage labels.
    if draft['id']!='reel-article-portugal-sans-voiture-bagages':raise ValueError('layout_topic_not_qualified')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.storyboard-media-',dir=output.parent) as tmp:
        result=Path(tmp)/'result';result.mkdir()
        pilot.run(result/'audio',now,sentences)
        compose.compose(result/'audio',result/'videos',now,sentences,headings,badges)
        finished=dt.datetime.now(dt.timezone.utc)
        if finished>=dt.datetime.fromisoformat(draft['source']['validUntil']) or finished>=pilot.STOP:raise ValueError('expired_during_render')
        proof={'schemaVersion':1,'status':'storyboard_media_requires_review','id':draft['id'],'storyboardSha256':story_hash,
               'publicHtmlSha256':public_hash,'startedAt':now.isoformat(),'finishedAt':finished.isoformat(),
               'validUntil':draft['source']['validUntil'],'targetUrl':draft['targetUrl'],
               'paidInferenceCalls':0,'publicationAttempted':False,'listeningReviewComplete':False,
               'files':[{'file':str(p.relative_to(result)),'sha256':pilot.sha(p.read_bytes())} for p in sorted(result.rglob('*')) if p.is_file()]}
        (result/'receipt.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
        (result/'storyboard.json').write_bytes((Path(folder)/'storyboard.json').read_bytes())
        result.rename(output)
    return proof

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--storyboard',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=run(args.storyboard,args.output,dt.datetime.now(dt.timezone.utc))
    print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False))
