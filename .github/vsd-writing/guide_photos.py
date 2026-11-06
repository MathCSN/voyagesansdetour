"""Free photos for a new guide: Wikimedia Commons files only, licence checked, credit recorded.

Commons search finds them first; Openverse (api.openverse.org, no key) is the fallback search
when Commons search is rate limited or finds nothing. Either way the file is then verified on
Commons itself (licence, author, camera EXIF, categories and every AI mark), because the site
credits each photo to its Commons page.
The topic names each wanted subject (search words, required words, French alt text).
Nothing is published here: files land in the run folder, then admission installs them
with the guide that uses them. Standard library only, like the rest of the writing chain.
"""
import email.utils
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
OPENVERSE='https://api.openverse.org/v1/images/'
USER_AGENT='VoyageSansDetour-photos/1 (https://voyagesansdetour.fr; contact@voyagesansdetour.fr)'
IMAGE_HOSTS={'upload.wikimedia.org','thumb.wikimedia.org'}
# Same rule as the site catalogue test: CC BY, CC BY-SA or CC0 only (no NC, ND or unknown terms).
LICENCE=re.compile(r'CC BY(?:-SA)? [0-9.]+|CC0')
CC0_URL='https://creativecommons.org/publicdomain/zero/1.0/'
WIDE,SMALL=1600,800
MIN_RATIO,MAX_RATIO=1.25,2.6
MAX_IMAGE_BYTES=4*1024*1024
MIN_PHOTOS=3
# Never an AI-generated image (Mathis, 24/10/2026): any AI mark in a category, the description,
# the credit or the author refuses the file, and a photo must carry its camera's EXIF data.
AI_MARK=re.compile(r'\bai[- ]generated|generated (?:by|with|using) (?:an? )?(?:ai|artificial)|artificial intelligence|'
                   r'midjourney|dall[·\-. ]?e|stable[- ]diffusion|text[- ]to[- ]image|generative ai|\bai[- ]art\b|'
                   r'deepdream|firefly|imagen\b|flux\.1|ai image',re.I)
# Commons thumbnails are barely compressed; the site's photos are progressive JPEG at this quality (measured on the existing set).
JPEG_QUALITY=72
# Wikimedia and Openverse ask clients to slow down with HTTP 429 (or 503), often for a few
# minutes. Each request waits as told by Retry-After, else these pauses, within one budget
# for the whole run (the job has 25 minutes and the writing still has to happen).
RETRY_PAUSES=(10,30,90)
MAX_RETRY_AFTER=300
WAIT_BUDGET=600
SLOW_DOWN={429,503}
# Original Commons files, as Openverse lists them: /wikipedia/commons/a/ab/Name.jpg
COMMONS_FILE=re.compile(r'/wikipedia/commons/[0-9a-f]/[0-9a-f]{2}/([^/]+\.jpe?g)\Z',re.I)
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


def retry_delay(error,attempt,now=None):
    """Seconds asked by Retry-After (seconds or HTTP date), else the next planned pause."""
    value=(error.headers.get('Retry-After') if error.headers else None) or ''
    value=value.strip()
    if value.isdigit():return min(int(value),MAX_RETRY_AFTER)
    try:
        moment=email.utils.parsedate_to_datetime(value)
    except (TypeError,ValueError,IndexError):
        moment=None
    if moment is not None and moment.tzinfo is not None:
        now=now or time.time()
        return min(max(0,round(moment.timestamp()-now)),MAX_RETRY_AFTER)
    return RETRY_PAUSES[attempt]


class Patient:
    """Opener that waits and retries on HTTP 429/503 while the run's waiting budget lasts."""
    def __init__(self,opener,budget=WAIT_BUDGET,sleep=None):
        self.opener=opener;self.remaining=budget;self.waited=[]
        self.sleep=sleep or (lambda seconds:time.sleep(seconds))
    def open(self,request,timeout):
        for attempt in range(len(RETRY_PAUSES)+1):
            try:
                return self.opener.open(request,timeout=timeout)
            except urllib.error.HTTPError as error:
                if error.code not in SLOW_DOWN or attempt==len(RETRY_PAUSES):raise
                pause=retry_delay(error,attempt)
                if pause>self.remaining:raise
                self.remaining-=pause;self.waited.append(pause)
                self.sleep(pause)


def read_json(url,opener):
    request=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
    with opener.open(request,timeout=30) as response:
        require(response.status==200,'guide_photo_api_status')
        return json.loads(response.read(2_000_001))


def get_json(params,opener):
    return read_json(API+'?'+urllib.parse.urlencode(dict(params,format='json',formatversion='2')),opener)


FILE_PROPS={'prop':'imageinfo|categories','cllimit':'max','iiprop':'url|size|mime|extmetadata|commonmetadata','iiurlwidth':str(WIDE),
            'iiextmetadatafilter':'LicenseShortName|LicenseUrl|Artist|Attribution|ImageDescription|Credit|Categories'}


def search(spec,opener,quality=True):
    words=spec['query']+' filetype:bitmap filemime:image/jpeg filew:>'+str(WIDE-1)+(' incategory:Quality_images' if quality else '')
    data=get_json(dict(FILE_PROPS,action='query',generator='search',gsrnamespace='6',gsrsearch=words,gsrlimit='20'),opener)
    return sorted(data.get('query',{}).get('pages',[]),key=lambda page:page.get('index',99))


def openverse_titles(spec,opener):
    """Commons file titles Openverse finds for the subject, best first, free licences only."""
    query=urllib.parse.urlencode({'q':spec['query'],'source':'wikimedia','license':'by,by-sa,cc0','extension':'jpg','mature':'false','page_size':'20'})
    data=read_json(OPENVERSE+'?'+query,opener)
    titles=[]
    for row in data.get('results',[]) if isinstance(data,dict) else []:
        if not isinstance(row,dict) or not isinstance(row.get('url'),str):continue
        url=urllib.parse.urlsplit(row['url'])
        found=COMMONS_FILE.search(url.path) if url.scheme=='https' and url.hostname=='upload.wikimedia.org' else None
        title='File:'+urllib.parse.unquote(found.group(1)).replace('_',' ') if found else None
        if title and title not in titles:titles.append(title)
    return titles


def openverse_search(spec,opener):
    """The same Commons pages as search() would give, found by Openverse instead of Commons search."""
    titles=openverse_titles(spec,opener)
    if not titles:return []
    data=get_json(dict(FILE_PROPS,action='query',titles='|'.join(titles)),opener)
    rank={title:index for index,title in enumerate(titles)}
    # Commons may answer under a normalised title (first letter, Unicode form).
    for pair in data.get('query',{}).get('normalized',[]):
        if pair.get('from') in rank:rank[pair.get('to')]=rank[pair['from']]
    pages=[p for p in data.get('query',{}).get('pages',[]) if p.get('title') in rank]
    return sorted(pages,key=lambda page:rank[page['title']])


def camera(info):
    """Camera make or model from the file's EXIF data, empty when the file has none."""
    exif={m.get('name'):m.get('value') for m in info.get('commonmetadata',[]) if isinstance(m,dict)}
    return ' '.join(str(exif[k]) for k in ('Make','Model') if isinstance(exif.get(k),(str,int)) and str(exif[k]).strip())


def real_photo(page):
    """True only for a camera photograph with no sign of AI generation anywhere on the file page."""
    info=(page.get('imageinfo') or [{}])[0];meta=info.get('extmetadata',{})
    text=' '.join([page.get('title','')]+[c.get('title','') for c in page.get('categories',[]) if isinstance(c,dict)]+
                  [plain(meta.get(k,{}).get('value'),2000) for k in ('Categories','ImageDescription','Credit','Artist','Attribution')])
    return not AI_MARK.search(text) and bool(camera(info))


def candidate(page,spec,used):
    """Credit fields of a Commons file the site may reuse, or None. Never guesses a licence or an author."""
    info=(page.get('imageinfo') or [{}])[0];meta=info.get('extmetadata',{})
    if not real_photo(page):return None
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
        require(target.scheme=='https' and target.hostname in IMAGE_HOSTS|{'commons.wikimedia.org','api.openverse.org'},'guide_photo_redirect_host')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download(url,opener):
    parsed=urllib.parse.urlsplit(url)
    require(parsed.scheme=='https' and parsed.hostname in IMAGE_HOSTS,'guide_photo_host')
    with opener.open(urllib.request.Request(url,headers={'User-Agent':USER_AGENT}),timeout=60) as response:
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


def searches(spec,opener):
    """Where to look, in order: Commons quality images, all of Commons, then Openverse."""
    yield 'commons',lambda:search(spec,opener,True)
    yield 'commons',lambda:search(spec,opener,False)
    yield 'openverse',lambda:openverse_search(spec,opener)


def fetch_photo(spec,out,used,opener,compress=recompress,trace=None):
    trace=trace if trace is not None else []
    for origin,find in searches(spec,opener):
        try:
            pages=find()
        except (urllib.error.URLError,OSError,ValueError) as error:
            # A search still rate limited after its retries, or down, hands over to the next one.
            trace.append({'search':origin,'error':getattr(error,'code',None) or type(error).__name__});continue
        trace.append({'search':origin,'pages':len(pages)})
        for page in pages:
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
            trace.append({'search':origin,'chosen':found['source_page']})
            return record,{'sha256':hashlib.sha256(wide).hexdigest(),'sha256Small':hashlib.sha256(small).hexdigest()}
    return None,None


def prepare(topic,catalogue,out,opener=None,compress=recompress):
    """Photo ids for cover and sections, plus the new credit records to install with the guide."""
    opener=Patient(opener or urllib.request.build_opener(WikimediaRedirect()))
    known={p['id'] for p in catalogue}
    used={p['source_page'] for p in catalogue}
    specs=[validate_spec(s) for s in topic.get('photos',[])]
    require(len({s['id'] for s in specs})==len(specs),'guide_photo_duplicate_id')
    ids=[];records=[];hashes={};searched={}
    for spec in specs:
        if spec['id'] in known:
            ids.append(spec['id']);continue
        require('query' in spec,'guide_photo_unknown_id')
        record,digest=fetch_photo(spec,out,used,opener,compress,searched.setdefault(spec['id'],[]))
        if record is None:continue
        used.add(record['source_page']);records.append(record);hashes[spec['id']]=digest;ids.append(spec['id'])
    # Written before the verdict: a held guide says which subject found nothing, and why.
    (out/'guide-photo-search.json').write_text(json.dumps({'searches':searched,'waitedSeconds':opener.waited},ensure_ascii=False,indent=2)+'\n')
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
