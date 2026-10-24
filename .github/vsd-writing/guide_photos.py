"""Free photos for a new guide: Wikimedia Commons only, licence checked, credit recorded.

The topic names each wanted subject (search words, required words, French alt text).
Nothing is published here: files land in the run folder, then admission installs them
with the guide that uses them. Standard library only, like the rest of the writing chain.
"""
import hashlib
import html
import io
import json
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from source_draft import require

API='https://commons.wikimedia.org/w/api.php'
USER_AGENT='VoyageSansDetour-photos/1 (https://voyagesansdetour.fr; contact@voyagesansdetour.fr)'
IMAGE_HOSTS={'upload.wikimedia.org','thumb.wikimedia.org'}
# Same rule as the site catalogue test: CC BY, CC BY-SA or CC0 only (no NC, ND or unknown terms).
LICENCE=re.compile(r'CC BY(?:-SA)? [0-9.]+|CC0')
CC0_URL='https://creativecommons.org/publicdomain/zero/1.0/'
WIDE,SMALL=1600,800
MIN_RATIO,MAX_RATIO=1.25,2.6
MAX_IMAGE_BYTES=4*1024*1024
MIN_PHOTOS=3
# Commons thumbnails are barely compressed; the site's photos are progressive JPEG at this quality (measured on the existing set).
JPEG_QUALITY=72
# Wikimedia asks clients to slow down with HTTP 429: one pause, one retry, then the guide waits.
RETRY_PAUSE=10
ID=re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')


def fold(text):
    text=unicodedata.normalize('NFKD',text.lower())
    return ''.join(c for c in text if not unicodedata.combining(c))


def plain(value,limit):
    text=html.unescape(re.sub(r'<[^>]+>',' ',value or ''))
    return re.sub(r'\s+',' ',text).strip()[:limit]


def validate_spec(spec):
    require(isinstance(spec,dict) and isinstance(spec.get('id'),str) and ID.fullmatch(spec['id']),'guide_photo_spec')
    if set(spec)=={'id'}:return spec
    require(set(spec)=={'id','query','must','alt'},'guide_photo_spec')
    require(isinstance(spec['query'],str) and 3<=len(spec['query'])<=120,'guide_photo_query')
    require(isinstance(spec['must'],list) and 1<=len(spec['must'])<=4 and all(isinstance(w,str) and w for w in spec['must']),'guide_photo_must')
    require(isinstance(spec['alt'],str) and 20<=len(spec['alt'])<=200,'guide_photo_alt')
    return spec


def get_json(params,opener,pause=RETRY_PAUSE):
    url=API+'?'+urllib.parse.urlencode(dict(params,format='json',formatversion='2'))
    request=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
    try:
        response=opener.open(request,timeout=30)
    except urllib.error.HTTPError as error:
        if error.code!=429 or not pause:raise
        time.sleep(pause)
        return get_json(params,opener,pause=0)
    with response:
        require(response.status==200,'guide_photo_api_status')
        return json.loads(response.read(2_000_001))


def search(spec,opener,quality=True):
    words=spec['query']+' filetype:bitmap filemime:image/jpeg filew:>'+str(WIDE-1)+(' incategory:Quality_images' if quality else '')
    data=get_json({'action':'query','generator':'search','gsrnamespace':'6','gsrsearch':words,'gsrlimit':'20',
                   'prop':'imageinfo','iiprop':'url|size|mime|extmetadata','iiurlwidth':str(WIDE),
                   'iiextmetadatafilter':'LicenseShortName|LicenseUrl|Artist|Attribution|ImageDescription'},opener)
    return sorted(data.get('query',{}).get('pages',[]),key=lambda page:page.get('index',99))


def candidate(page,spec,used):
    """Credit fields of a Commons file the site may reuse, or None. Never guesses a licence or an author."""
    info=(page.get('imageinfo') or [{}])[0];meta=info.get('extmetadata',{})
    licence=plain(meta.get('LicenseShortName',{}).get('value'),40)
    # "Artist" sometimes names the monument's architect; "Attribution" is the uploader's requested credit.
    author=plain(meta.get('Attribution',{}).get('value'),120) or plain(meta.get('Artist',{}).get('value'),120)
    source=info.get('descriptionurl','')
    if not (LICENCE.fullmatch(licence) and author and source.startswith('https://commons.wikimedia.org/wiki/File:')):return None
    if source in used or info.get('mime')!='image/jpeg':return None
    width,height=info.get('width',0),info.get('height',0)
    if width<WIDE or not height or not MIN_RATIO<=width/height<=MAX_RATIO:return None
    label=fold(page.get('title','')+' '+plain(meta.get('ImageDescription',{}).get('value'),400))
    if not all(fold(word) in label for word in spec['must']):return None
    url=CC0_URL if licence=='CC0' else meta.get('LicenseUrl',{}).get('value','')
    url='https:'+url if url.startswith('//') else url
    if not url.startswith('https://creativecommons.org/'):return None
    return {'source_page':source,'author':author,'license':licence,'license_url':url}


class WikimediaRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects only to the Commons API and the Wikimedia image hosts."""
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        target=urllib.parse.urlsplit(newurl)
        require(target.scheme=='https' and target.hostname in IMAGE_HOSTS|{'commons.wikimedia.org'},'guide_photo_redirect_host')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download(url,opener,pause=RETRY_PAUSE):
    parsed=urllib.parse.urlsplit(url)
    require(parsed.scheme=='https' and parsed.hostname in IMAGE_HOSTS,'guide_photo_host')
    try:
        response=opener.open(urllib.request.Request(url,headers={'User-Agent':USER_AGENT}),timeout=60)
    except urllib.error.HTTPError as error:
        if error.code!=429 or not pause:raise
        time.sleep(pause)
        return download(url,opener,pause=0)
    with response:
        require(response.status==200,'guide_photo_download_status')
        data=response.read(MAX_IMAGE_BYTES+1)
    require(len(data)<=MAX_IMAGE_BYTES and data[:3]==b'\xff\xd8\xff','guide_photo_not_jpeg')
    return data


def recompress(data):
    """Same pixels, smaller file: progressive JPEG without metadata (Pillow, installed by the workflow)."""
    from PIL import Image
    image=Image.open(io.BytesIO(data));image.load()
    out=io.BytesIO()
    image.convert('RGB').save(out,'JPEG',quality=JPEG_QUALITY,optimize=True,progressive=True)
    return out.getvalue()


def small_url(title,opener):
    pages=get_json({'action':'query','titles':title,'prop':'imageinfo','iiprop':'url','iiurlwidth':str(SMALL)},opener)['query']['pages']
    require(len(pages)==1 and pages[0].get('imageinfo'),'guide_photo_thumbnail')
    return pages[0]['imageinfo'][0]['thumburl']


def fetch_photo(spec,out,used,opener,compress=recompress):
    for quality in (True,False):
        for page in search(spec,opener,quality):
            found=candidate(page,spec,used)
            if not found:continue
            info=page['imageinfo'][0]
            try:
                wide=compress(download(info['thumburl'],opener))
                small=compress(download(small_url(page['title'],opener),opener))
            except (ValueError,OSError):
                # One broken thumbnail never costs the guide: try the next candidate.
                continue
            folder=out/'photos';folder.mkdir(exist_ok=True)
            (folder/(spec['id']+'.jpg')).write_bytes(wide);(folder/(spec['id']+'-800.jpg')).write_bytes(small)
            record={'id':spec['id'],'file':'photos/'+spec['id']+'.jpg','width':info['thumbwidth'],'height':info['thumbheight'],
                    'source_page':found['source_page'],'author':found['author'],'license':found['license'],
                    'license_url':found['license_url'],'alt_fr':spec['alt'],
                    'credit_fr':found['author']+' / Wikimedia Commons — '+found['license']+'.'}
            return record,{'sha256':hashlib.sha256(wide).hexdigest(),'sha256Small':hashlib.sha256(small).hexdigest()}
    return None,None


def prepare(topic,catalogue,out,opener=None,compress=recompress):
    """Photo ids for cover and sections, plus the new credit records to install with the guide."""
    opener=opener or urllib.request.build_opener(WikimediaRedirect())
    known={p['id'] for p in catalogue}
    used={p['source_page'] for p in catalogue}
    specs=[validate_spec(s) for s in topic.get('photos',[])]
    require(len({s['id'] for s in specs})==len(specs),'guide_photo_duplicate_id')
    ids=[];records=[];hashes={}
    for spec in specs:
        if spec['id'] in known:
            ids.append(spec['id']);continue
        require('query' in spec,'guide_photo_unknown_id')
        record,digest=fetch_photo(spec,out,used,opener,compress)
        if record is None:continue
        used.add(record['source_page']);records.append(record);hashes[spec['id']]=digest;ids.append(spec['id'])
    require(len(ids)>=MIN_PHOTOS,'guide_photos_insufficient')
    return {'ids':ids,'records':records,'hashes':hashes}


def attach(article,photo_ids):
    """Cover first, then one photo per section in order; a photo is never shown twice."""
    remaining=list(photo_ids[1:]);sections=[]
    for section in article['sections']:
        sections.append(dict(section,image=remaining.pop(0)) if remaining else dict(section))
    return dict(article,cover=photo_ids[0],sections=sections)


def install(selection,run_dir,site_root,needed=()):
    """Copy the verified files and append their credits; an existing id is never overwritten."""
    if not selection['records'] and not needed:return []
    sources_path=site_root/'image-sources.json'
    catalogue=json.loads(sources_path.read_text())
    ids={p['id'] for p in catalogue['photos']}
    require(set(needed)<=ids|{r['id'] for r in selection['records']},'guide_photo_unknown_id')
    target=site_root/'dist'/'assets'/'photos'
    require(target.is_dir() and not target.is_symlink(),'guide_photo_target')
    for record in selection['records']:
        require(isinstance(record.get('id'),str) and ID.fullmatch(record['id']) and record['id'] not in ids,'guide_photo_exists')
        for suffix,key in (('.jpg','sha256'),('-800.jpg','sha256Small')):
            source=run_dir/'photos'/(record['id']+suffix)
            require(source.is_file() and not source.is_symlink(),'guide_photo_file_missing')
            require(hashlib.sha256(source.read_bytes()).hexdigest()==selection['hashes'][record['id']][key],'guide_photo_file_changed')
            require(not (target/(record['id']+suffix)).exists(),'guide_photo_exists')
            shutil.copyfile(source,target/(record['id']+suffix))
        ids.add(record['id'])
    updated=dict(catalogue,photos=catalogue['photos']+selection['records'])
    temporary=sources_path.with_name(sources_path.name+'.tmp')
    temporary.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(sources_path)
    return [r['id'] for r in selection['records']]
