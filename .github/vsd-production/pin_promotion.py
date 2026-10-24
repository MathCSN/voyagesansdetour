"""Admit one exact-title typographic Pin to the connected preparation RSS feed."""
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import shutil
import urllib.request
from PIL import Image
from pin_intake import STOP,digest,renderer_sha256
from pin_draft import FREE_LICENSES,HERE,ORIGIN,article_path

FILES=('pin.jpg','credits.txt','dmsans-OFL.txt','playfairdisplay-OFL.txt')
# Each country with a Pinterest board fed by RSS; a country without a board waits for one.
COUNTRY_FEEDS={'portugal':'preparer-portugal.xml','espagne':'preparer-espagne.xml','italie':'preparer-italie.xml'}
COUNTRY_NAMES={'portugal':'au Portugal','espagne':'en Espagne','italie':'en Italie'}
CADENCE=dt.timedelta(days=7)

def require(value,code):
    if not value:raise ValueError(code)

def on_hold(last,country,now):
    # One Pin per board per week; a single date (older callers) applies to every board.
    previous=last.get(country) if isinstance(last,dict) else last
    return bool(previous) and now<previous+CADENCE

def select(articles,drafts,known,last,now,skip=frozenset()):
    require(now.tzinfo is not None,'timezone_required')
    if now>=STOP:return None,'period_ended'
    by_slug={a['slug']:a for a in articles}
    require(len(by_slug)==len(articles),'duplicate_article')
    waiting=False
    for folder in sorted(Path(drafts).glob('pin-*')):
        require(folder.is_dir() and not folder.is_symlink(),'invalid_draft_folder')
        require(not (folder/'draft.json').is_symlink(),'manifest_symlink')
        item=json.loads((folder/'draft.json').read_text());identity=item['id']
        if identity in known or identity in skip:continue
        slug=identity.removeprefix('pin-');article=by_slug.get(slug)
        if not article or article.get('country','portugal') not in COUNTRY_FEEDS:continue
        if on_hold(last,article.get('country','portugal'),now):waiting=True;continue
        require(folder.name==identity and identity=='pin-'+article['slug'],'draft_identity')
        # A guide refreshed or a template changed after the draft is redrawn by pin_intake; never promote the old one.
        if item['articleSha256']!=digest(article) or item.get('rendererSha256')!=renderer_sha256() or item['targetUrl']!=ORIGIN+article_path(article):continue
        require(item['title']==article['title'] and 1<=len(item['title'])<=100,'title_changed_or_too_long')
        require(item['status']=='draft_requires_review' and item['publicationApproved'] is False,'draft_state')
        require(item.get('templateVersion') in (1,2),'unqualified_renderer')
        # Version 2 carries the guide's cover photo, accepted only with a free licence recorded in the draft.
        photo_ok=item.get('templateVersion')==2 and item.get('externalPhotographs') is True and (item.get('photo') or {}).get('license') in FREE_LICENSES
        require(item.get('originalComposition') is True and (item.get('externalPhotographs') is False or photo_ok),'unqualified_assets')
        for name in FILES:require((folder/name).is_file() and not (folder/name).is_symlink(),'missing_or_symlink_file')
        require(hashlib.sha256((folder/'pin.jpg').read_bytes()).hexdigest()==item['imageSha256'],'image_changed')
        with Image.open(folder/'pin.jpg') as image:require(image.format=='JPEG' and image.size==(1000,1500),'image_format');image.verify()
        for name in FILES[2:]:require((folder/name).read_bytes()==(HERE/'assets'/name).read_bytes(),'license_changed')
        return (folder,item,article),'eligible'
    return None,'cadence_hold' if waiting else 'no_eligible_new_draft'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('public_target_redirect')

def verify_target(url,title):
    with urllib.request.build_opener(NoRedirect()).open(url,timeout=20) as response:
        require(response.status==200,'public_target_unavailable');raw=response.read(2_000_001)
    require(len(raw)<=2_000_000,'public_target_too_large')
    text=html.unescape(raw.decode('utf-8'))
    require(title in text,'public_title_not_found')
    return hashlib.sha256(raw).hexdigest()

def run(root=HERE.parents[1],now=None,fetcher=verify_target):
    root=Path(root);now=now or dt.datetime.now(dt.timezone.utc);production=root/'.github/vsd-production';site=root/'site-src'
    ledger_path=production/'pin-admissions.json';ledger=json.loads(ledger_path.read_text())
    config=json.loads((site/'pinterest-additions.json').read_text());media=json.loads((site/'public-media.json').read_text())
    known={i['id'] for f in config['feeds'] for i in f['items']}
    known.update(i['id'] for i in json.loads((site/'pinterest-rss.json').read_text())['items'])
    articles=json.loads((site/'articles.json').read_text());held=[]
    country_of={'pin-'+a['slug']:a.get('country','portugal') for a in articles};last={}
    for entry in ledger['items']:
        country=country_of.get(entry['id'],'portugal');admitted=dt.datetime.fromisoformat(entry['admittedAt'].replace('Z','+00:00'))
        if country not in last or admitted>last[country]:last[country]=admitted
    while True:
        selected,status=select(articles,production/'pin-drafts',known,last,now,frozenset(h['id'] for h in held))
        if not selected:return {'status':status,'changed':False,'publicationConfirmed':False,'held':held}
        folder,item,article=selected;identity=item['id']
        # An unreachable guide page holds this Pin only; the next draft can still go out.
        try:public_hash=fetcher(item['targetUrl'],item['title']);break
        except (OSError,ValueError):held.append({'id':identity,'reason':'public_target_unavailable'})
    require(not any(x['contentId']==identity for x in media['items']),'media_already_exists')
    feed=[f for f in config['feeds'] if f['file']==COUNTRY_FEEDS[article.get('country','portugal')]];require(len(feed)==1,'connected_feed_missing')
    route=article_path(article)
    require(not any(p['linkPath']==route for f in config['feeds'] for p in f['items']),'route_already_admitted')
    require(not any(p['link_path']==route for p in json.loads((site/'pinterest-rss.json').read_text())['items']),'route_already_in_legacy_feed')
    destination=site/'social-media/production'/identity;require(not destination.exists(),'destination_exists')
    files=[{'name':name,'bytes':(folder/name).stat().st_size,'sha256':hashlib.sha256((folder/name).read_bytes()).hexdigest()} for name in FILES]
    photo=item.get('photo') if item.get('externalPhotographs') else None
    origin_note='Photo : '+photo['author']+' — '+photo['license']+'.' if photo else 'Composition typographique originale Voyage Sans Détour, assistée par IA.'
    description='📌 Retrouvez le guide et ses sources pour préparer votre voyage '+COUNTRY_NAMES[article.get('country','portugal')]+'. '+origin_note+' Crédits : '+ORIGIN+'/social-media/production/'+identity+'/credits.txt'
    require(len(description)<=500,'caption_too_long')
    feed[0]['items'].append({'id':identity,'title':item['title'],'description':description,'linkPath':route,'mediaId':identity,'width':1000,'height':1500})
    media['items'].append({'contentId':identity,'kind':'pin','approved':True,'files':files})
    ledger['items'].append({'id':identity,'admittedAt':now.isoformat(),'articleSha256':item['articleSha256'],'imageSha256':item['imageSha256'],'publicHtmlSha256':public_hash,'method':'exact_published_title_typographic_template_v1','publicationConfirmed':False})
    destination.mkdir(parents=True)
    for name in FILES:shutil.copyfile(folder/name,destination/name)
    for path,value in [(site/'pinterest-additions.json',config),(site/'public-media.json',media),(ledger_path,ledger)]:path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return {'status':'admitted_to_feed_not_published','changed':True,'id':identity,'publicationConfirmed':False,'held':held}

if __name__=='__main__':print(json.dumps(run()))
