"""Admit one exact-title typographic Pin to the connected preparation RSS feed."""
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import shutil
import urllib.request
from PIL import Image
from pin_intake import STOP
from pin_draft import HERE

FILES=('pin.jpg','credits.txt','dmsans-OFL.txt','playfairdisplay-OFL.txt')
ORIGIN='https://voyagesansdetour.fr'

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def require(value,code):
    if not value:raise ValueError(code)

def select(articles,drafts,known,last,now):
    require(now.tzinfo is not None,'timezone_required')
    if now>=STOP:return None,'period_ended'
    if last and now<last+dt.timedelta(days=7):return None,'cadence_hold'
    by_slug={a['slug']:a for a in articles}
    require(len(by_slug)==len(articles),'duplicate_article')
    for folder in sorted(Path(drafts).glob('pin-*')):
        require(folder.is_dir() and not folder.is_symlink(),'invalid_draft_folder')
        require(not (folder/'draft.json').is_symlink(),'manifest_symlink')
        item=json.loads((folder/'draft.json').read_text());identity=item['id']
        if identity in known:continue
        slug=identity.removeprefix('pin-');article=by_slug.get(slug)
        # Only this board has a connected RSS route for new typographic Pins.
        if not article or article.get('destination')!='Portugal':continue
        require(folder.name==identity and identity=='pin-'+article['slug'],'draft_identity')
        require(item['articleSha256']==digest(article),'article_changed')
        require(item['title']==article['title'] and 1<=len(item['title'])<=100,'title_changed_or_too_long')
        require(item['targetUrl']==ORIGIN+'/portugal/'+slug+'/','target_changed')
        require(item['status']=='draft_requires_review' and item['publicationApproved'] is False,'draft_state')
        require(item.get('templateVersion')==1 and item.get('rendererSha256')==hashlib.sha256((HERE/'pin_draft.py').read_bytes()).hexdigest(),'unqualified_renderer')
        require(item.get('originalComposition') is True and item.get('externalPhotographs') is False,'unqualified_assets')
        for name in FILES:require((folder/name).is_file() and not (folder/name).is_symlink(),'missing_or_symlink_file')
        require(hashlib.sha256((folder/'pin.jpg').read_bytes()).hexdigest()==item['imageSha256'],'image_changed')
        with Image.open(folder/'pin.jpg') as image:require(image.format=='JPEG' and image.size==(1000,1500),'image_format');image.verify()
        for name in FILES[2:]:require((folder/name).read_bytes()==(HERE/'assets'/name).read_bytes(),'license_changed')
        return (folder,item,article),'eligible'
    return None,'no_eligible_new_draft'

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
    last=max((dt.datetime.fromisoformat(x['admittedAt'].replace('Z','+00:00')) for x in ledger['items']),default=None)
    selected,status=select(json.loads((site/'articles.json').read_text()),production/'pin-drafts',known,last,now)
    if not selected:return {'status':status,'changed':False,'publicationConfirmed':False}
    folder,item,article=selected;identity=item['id']
    require(not any(x['contentId']==identity for x in media['items']),'media_already_exists')
    feed=[f for f in config['feeds'] if f['file']=='preparer-portugal.xml'];require(len(feed)==1,'connected_feed_missing')
    route='/portugal/'+article['slug']+'/'
    require(not any(p['linkPath']==route for f in config['feeds'] for p in f['items']),'route_already_admitted')
    require(not any(p['link_path']==route for p in json.loads((site/'pinterest-rss.json').read_text())['items']),'route_already_in_legacy_feed')
    public_hash=fetcher(item['targetUrl'],item['title'])
    destination=site/'social-media/production'/identity;require(not destination.exists(),'destination_exists')
    files=[{'name':name,'bytes':(folder/name).stat().st_size,'sha256':hashlib.sha256((folder/name).read_bytes()).hexdigest()} for name in FILES]
    description='📌 Retrouvez le guide et ses sources pour préparer votre voyage au Portugal. Composition typographique originale Voyage Sans Détour, assistée par IA. Crédits : '+ORIGIN+'/social-media/production/'+identity+'/credits.txt'
    require(len(description)<=500,'caption_too_long')
    feed[0]['items'].append({'id':identity,'title':item['title'],'description':description,'linkPath':route,'mediaId':identity,'width':1000,'height':1500})
    media['items'].append({'contentId':identity,'kind':'pin','approved':True,'files':files})
    ledger['items'].append({'id':identity,'admittedAt':now.isoformat(),'articleSha256':item['articleSha256'],'imageSha256':item['imageSha256'],'publicHtmlSha256':public_hash,'method':'exact_published_title_typographic_template_v1','publicationConfirmed':False})
    destination.mkdir(parents=True)
    for name in FILES:shutil.copyfile(folder/name,destination/name)
    for path,value in [(site/'pinterest-additions.json',config),(site/'public-media.json',media),(ledger_path,ledger)]:path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return {'status':'admitted_to_feed_not_published','changed':True,'id':identity,'publicationConfirmed':False}

if __name__=='__main__':print(json.dumps(run()))
