"""One immutable, unpublished storyboard derived from a current public guide.

Exact excerpts only; no inference, source-date renewal, media render or send.
"""
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
import urllib.request

from paths import article_path

HERE=Path(__file__).resolve().parent
STOP=dt.datetime(2027,9,14,21,59,59,tzinfo=dt.timezone.utc)
ORIGIN='https://voyagesansdetour.fr'


def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(raw).hexdigest()


def normalized(value):
    return ' '.join(value.split())


class PublicArticle(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonicals=[];self.paragraphs=[];self.current=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='link' and attrs.get('rel')=='canonical':self.canonicals.append(attrs.get('href'))
        if tag=='p':self.current=[]
    def handle_endtag(self,tag):
        if tag=='p' and self.current is not None:
            self.paragraphs.append(normalized(''.join(self.current)));self.current=None
    def handle_data(self,value):
        if self.current is not None:self.current.append(value)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def fetch_public(url):
    request=urllib.request.Request(url,headers={'User-Agent':'VoyageSansDetour-PublicExcerptCheck/1.0'})
    with urllib.request.build_opener(NoRedirect()).open(request,timeout=20) as response:
        if response.status!=200 or response.headers.get_content_type()!='text/html':raise ValueError('public_html_unavailable')
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('public_html_too_large')
    return raw


def excerpts(article):
    selected=[]
    for section in article['sections']:
        for index,text in enumerate(section.get('paragraphs',[])):
            if not isinstance(text,str) or not 70<=len(text)<=280:continue
            # A cross-link or a meta-comment is not useful spoken travel content.
            if re.search(r'\bguide\b|https?://|\barticle\b',text,re.I):continue
            if len(text.split())>48:continue
            selected.append({'sectionId':section['id'],'paragraphIndex':index,'text':text})
            break
        if len(selected)==2:break
    return selected


def run(root=HERE,output=None,now=None,fetcher=fetch_public):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=STOP:return {'status':'period_ended','created':0}
    root=Path(root);output=Path(output or root/'reel-drafts')
    if output.is_symlink():raise ValueError('output_symlink')
    config=json.loads((root/'reel-reservations.json').read_text())
    if config.get('schemaVersion')!=1:raise ValueError('reservation_schema')
    reserved=set(config['reservedSlugs'])
    existing_drafts=set()
    if output.exists():
        for folder in output.iterdir():
            if folder.is_symlink() or not folder.is_dir():raise ValueError('invalid_draft_folder')
            storyboard=folder/'storyboard.json';receipt=folder/'receipt.json'
            if storyboard.is_symlink() or receipt.is_symlink():raise ValueError('draft_symlink')
            meta=json.loads(receipt.read_text())
            if hashlib.sha256(storyboard.read_bytes()).hexdigest()!=meta['storyboardSha256']:raise ValueError('storyboard_changed')
            draft=json.loads(storyboard.read_text())
            if draft['id']!=folder.name or draft['publicationApproved'] is not False:raise ValueError('draft_identity_or_state')
            existing_drafts.add(draft['source']['slug'])
    articles=json.loads((root.parents[1]/'site-src/articles.json').read_text())
    if len({a['slug'] for a in articles})!=len(articles):raise ValueError('duplicate_article')
    held=[];skipped=[]
    for article in sorted(articles,key=lambda a:(a.get('publishedOn',''),a['slug']),reverse=True):
        slug=article['slug']
        if slug in reserved or slug in existing_drafts:
            skipped.append({'slug':slug,'reason':'existing_storyboard' if slug in existing_drafts else 'reserved_existing_video'})
            continue
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug):raise ValueError('article_identity')
        if not article.get('sourcesCheckedOn'):
            held.append({'slug':slug,'reason':'source_review_date_missing'});continue
        checked=dt.date.fromisoformat(article['sourcesCheckedOn'])
        expiry=min(dt.datetime.combine(checked+dt.timedelta(days=30),dt.time(),dt.timezone.utc),STOP)
        if checked>now.date() or now>=expiry:
            held.append({'slug':slug,'reason':'source_review_expired_or_future'});continue
        selected=excerpts(article)
        if len(selected)!=2:
            held.append({'slug':slug,'reason':'insufficient_short_exact_excerpts'});continue
        url=ORIGIN+article_path(article)
        # A guide not yet deployed (or moved) is held; it never stops the other guides.
        try:
            raw=fetcher(url)
        except (OSError,ValueError):
            held.append({'slug':slug,'reason':'public_page_unavailable'});continue
        if not isinstance(raw,bytes) or len(raw)>2_000_000:
            held.append({'slug':slug,'reason':'public_html_invalid'});continue
        page=PublicArticle();page.feed(raw.decode('utf-8','replace'))
        if page.canonicals!=[url]:
            held.append({'slug':slug,'reason':'public_canonical_mismatch'});continue
        if not all(normalized(item['text']) in page.paragraphs for item in selected):
            held.append({'slug':slug,'reason':'excerpt_not_public'});continue
        identity='reel-article-'+slug
        draft={'schemaVersion':1,'id':identity,'status':'storyboard_requires_media_review','publicationApproved':False,
               'createdAt':now.isoformat(),'title':article['title'],'targetUrl':url,
               'source':{'slug':slug,'articleSha256':digest(article),'publicHtmlSha256':hashlib.sha256(raw).hexdigest(),
                         'publicCheckedAt':now.isoformat(),'sourcesCheckedOn':str(checked),'validUntil':expiry.isoformat(),
                         'officialSources':article['sources'],'proofScope':'Exact excerpts in a public guide; no new official-source audit'},
               'narration':{'hook':article['title'],'excerpts':selected,
                            'closing':'Retrouvez le guide et ses sources sur Voyage Sans Détour.'},
               'paidInferenceCalls':0,'limitations':['Narration timing, rendered layout, voice choice and publication payload remain unqualified.',
                                                    'A storyboard is not a rendered, imported, scheduled or published Reel.']}
        output.mkdir(parents=True,exist_ok=True)
        if (output/identity).exists():raise ValueError('existing_identity_preserved')
        with tempfile.TemporaryDirectory(prefix='.storyboard-',dir=output.parent) as temporary:
            staged=Path(temporary)/'draft';staged.mkdir()
            content=(json.dumps(draft,ensure_ascii=False,indent=2)+'\n').encode()
            (staged/'storyboard.json').write_bytes(content)
            (staged/'receipt.json').write_text(json.dumps({'schemaVersion':1,'storyboardSha256':hashlib.sha256(content).hexdigest(),
                                                         'status':'draft_not_rendered','publicationAttempted':False},indent=2)+'\n')
            staged.rename(output/identity)
        return {'status':'storyboard_created_not_rendered','created':1,'id':identity,'publicationAttempted':False,'held':held,'skipped':skipped}
    return {'status':'no_eligible_new_article','created':0,'publicationAttempted':False,'held':held,'skipped':skipped}


if __name__=='__main__':
    try:result=run()
    except Exception as error:result={'status':'held_no_retry','created':0,'errorType':type(error).__name__,'publicationAttempted':False}
    print(json.dumps(result,ensure_ascii=False))
    if result['status']=='held_no_retry':raise SystemExit(1)
