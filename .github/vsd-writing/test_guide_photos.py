import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import guide_photos as p

SPEC={'id':'kyoto-fushimi-inari','query':'Fushimi Inari torii','must':['fushimi','inari'],'alt':'Les torii vermillon du sanctuaire Fushimi Inari, à Kyoto.'}
JPEG=b'\xff\xd8\xff\xe0'+b'0'*64


def page(title='File:Torii path at Fushimi Inari Taisha, Kyoto.jpg',licence='CC BY-SA 4.0',width=6000,height=4000,author='<a href="//commons.wikimedia.org/wiki/User:Ex">Ex Ample</a>',attribution='',mime='image/jpeg'):
    return {'title':title,'index':1,'imageinfo':[{'width':width,'height':height,'mime':mime,'thumbwidth':1600,'thumbheight':1067,
            'thumburl':'https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/x.jpg/1600px-x.jpg',
            'descriptionurl':'https://commons.wikimedia.org/wiki/'+title.replace(' ','_'),
            'extmetadata':{'LicenseShortName':{'value':licence},'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/4.0'},
                           'Artist':{'value':author},'Attribution':{'value':attribution}}}]}


class Response:
    def __init__(self,data):self.data=data;self.status=200
    def read(self,limit):return self.data[:limit]
    def __enter__(self):return self
    def __exit__(self,*args):return False


class Opener:
    """Answers Commons API calls with fixed pages and image downloads with a tiny JPEG."""
    def __init__(self,pages):self.pages=pages;self.urls=[]
    def open(self,request,timeout):
        url=request.full_url;self.urls.append(url)
        if url.startswith(p.API) and 'generator=search' in url:return Response(json.dumps({'query':{'pages':self.pages}}).encode())
        if url.startswith(p.API):return Response(json.dumps({'query':{'pages':[{'imageinfo':[{'thumburl':'https://upload.wikimedia.org/x-800.jpg'}]}]}}).encode())
        return Response(JPEG)


class CandidateTests(unittest.TestCase):
    def test_free_licence_author_and_subject_are_required(self):
        found=p.candidate(page(),SPEC,set())
        self.assertEqual((found['license'],found['author']),('CC BY-SA 4.0','Ex Ample'))
        for refused in (page(licence='CC BY-NC-SA 4.0'),page(licence='Copyrighted free use'),page(author=''),page(title='File:Kyoto station.jpg'),
                        page(width=1200),page(width=4000,height=4000),page(mime='image/png')):
            self.assertIsNone(p.candidate(refused,SPEC,set()))
    def test_uploader_attribution_wins_over_artist(self):
        self.assertEqual(p.candidate(page(attribution='Photo by Jane Doe'),SPEC,set())['author'],'Photo by Jane Doe')
    def test_cc0_gets_its_public_domain_dedication_url(self):
        self.assertEqual(p.candidate(page(licence='CC0'),SPEC,set())['license_url'],p.CC0_URL)
    def test_a_photo_already_on_the_site_is_not_reused(self):
        used={page()['imageinfo'][0]['descriptionurl']}
        self.assertIsNone(p.candidate(page(),SPEC,used))


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)/'run';self.out.mkdir()
    def test_known_ids_are_reused_and_new_ones_downloaded_with_credit(self):
        topic={'photos':[{'id':'porto-nuit'},{'id':'lisbonne-tram-28'},SPEC]}
        catalogue=[{'id':'porto-nuit','source_page':'a'},{'id':'lisbonne-tram-28','source_page':'b'}]
        opener=Opener([page(licence='CC BY-NC 4.0',title='File:Fushimi Inari NC.jpg'),page()])
        result=p.prepare(topic,catalogue,self.out,opener,compress=lambda data:data)
        self.assertEqual(result['ids'],['porto-nuit','lisbonne-tram-28','kyoto-fushimi-inari'])
        record=result['records'][0]
        self.assertEqual(record['credit_fr'],'Ex Ample / Wikimedia Commons — CC BY-SA 4.0.')
        self.assertEqual(record['alt_fr'],SPEC['alt'])
        self.assertTrue((self.out/'photos/kyoto-fushimi-inari-800.jpg').is_file())
        self.assertTrue(all(u.startswith(p.API) or 'upload.wikimedia.org' in u for u in opener.urls))
    def test_too_few_photos_hold_the_guide(self):
        topic={'photos':[{'id':'porto-nuit'},SPEC,dict(SPEC,id='autre')]}
        with self.assertRaisesRegex(ValueError,'guide_photos_insufficient'):
            p.prepare(topic,[{'id':'porto-nuit','source_page':'a'}],self.out,Opener([]),compress=lambda data:data)
    def test_unknown_id_without_search_words_is_refused(self):
        with self.assertRaisesRegex(ValueError,'unknown_id'):p.prepare({'photos':[{'id':'absente'}]},[],self.out,Opener([]))
    def test_download_outside_wikimedia_is_refused(self):
        with self.assertRaisesRegex(ValueError,'guide_photo_host'):p.download('https://example.com/x.jpg',Opener([]))


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.site=root/'site';self.run=root/'run'
        (self.site/'dist/assets/photos').mkdir(parents=True);(self.run/'photos').mkdir(parents=True)
        (self.site/'image-sources.json').write_text(json.dumps({'photos':[{'id':'porto-nuit'}]}))
        for suffix in ('.jpg','-800.jpg'):(self.run/'photos'/('kyoto'+suffix)).write_bytes(JPEG+suffix.encode())
        digest=lambda suffix:hashlib.sha256(JPEG+suffix.encode()).hexdigest()
        self.selection={'ids':['kyoto'],'records':[{'id':'kyoto','file':'photos/kyoto.jpg'}],'hashes':{'kyoto':{'sha256':digest('.jpg'),'sha256Small':digest('-800.jpg')}}}
    def test_files_and_credits_are_installed_together(self):
        self.assertEqual(p.install(self.selection,self.run,self.site,needed={'kyoto','porto-nuit'}),['kyoto'])
        self.assertTrue((self.site/'dist/assets/photos/kyoto-800.jpg').is_file())
        self.assertEqual([x['id'] for x in json.loads((self.site/'image-sources.json').read_text())['photos']],['porto-nuit','kyoto'])
    def test_changed_file_or_existing_id_is_never_installed(self):
        (self.run/'photos/kyoto.jpg').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'file_changed'):p.install(self.selection,self.run,self.site)
        self.selection['records'][0]['id']='porto-nuit';self.selection['hashes']['porto-nuit']=self.selection['hashes']['kyoto']
        with self.assertRaisesRegex(ValueError,'photo_exists'):p.install(self.selection,self.run,self.site)
    def test_photo_used_by_the_guide_must_exist(self):
        with self.assertRaisesRegex(ValueError,'unknown_id'):p.install(self.selection,self.run,self.site,needed={'absente'})


class AttachTests(unittest.TestCase):
    def test_cover_then_one_photo_per_section(self):
        article={'sections':[{'id':'a'},{'id':'b'}]}
        result=p.attach(article,['c','s1','s2','s3'])
        self.assertEqual((result['cover'],[s['image'] for s in result['sections']]),('c',['s1','s2']))
        self.assertNotIn('cover',article)


class RateLimitTests(unittest.TestCase):
    def test_one_pause_then_one_retry_after_http_429(self):
        import urllib.error
        from unittest.mock import patch
        calls=[]
        class Limited(Opener):
            def open(self,request,timeout):
                calls.append(request.full_url)
                if len(calls)==1:raise urllib.error.HTTPError(request.full_url,429,'Too Many Requests',{},None)
                return super().open(request,timeout)
        with patch.object(p.time,'sleep') as sleep:
            self.assertEqual(p.search(SPEC,Limited([page()]))[0]['title'],page()['title'])
        sleep.assert_called_once_with(p.RETRY_PAUSE)
        class AlwaysLimited(Opener):
            def open(self,request,timeout):raise urllib.error.HTTPError(request.full_url,429,'Too Many Requests',{},None)
        with patch.object(p.time,'sleep'),self.assertRaises(urllib.error.HTTPError):p.search(SPEC,AlwaysLimited([]))


class CompressionTests(unittest.TestCase):
    def test_recompression_keeps_size_and_drops_weight(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow is installed by the writing workflow')
        import io,random
        random.seed(1)
        image=Image.frombytes('RGB',(320,200),bytes(random.getrandbits(8) for _ in range(320*200*3)))
        raw=io.BytesIO();image.save(raw,'JPEG',quality=100)
        smaller=p.recompress(raw.getvalue())
        self.assertLess(len(smaller),len(raw.getvalue()))
        self.assertEqual(Image.open(io.BytesIO(smaller)).size,(320,200))


class RobustnessTests(unittest.TestCase):
    def test_a_broken_thumbnail_falls_back_to_the_next_candidate(self):
        import tempfile
        class Flaky(Opener):
            def open(self,request,timeout):
                if 'broken' in request.full_url:raise OSError('reset')
                return super().open(request,timeout)
        broken=page(title='File:Fushimi Inari broken.jpg');broken['imageinfo'][0]['thumburl']='https://upload.wikimedia.org/broken.jpg'
        with tempfile.TemporaryDirectory() as tmp:
            record,_=p.fetch_photo(SPEC,Path(tmp),set(),Flaky([broken,page()]),compress=lambda data:data)
        self.assertEqual(record['source_page'],page()['imageinfo'][0]['descriptionurl'])
    def test_redirect_outside_wikimedia_is_refused(self):
        import urllib.request
        handler=p.WikimediaRedirect()
        request=urllib.request.Request('https://upload.wikimedia.org/x.jpg')
        with self.assertRaisesRegex(ValueError,'redirect_host'):
            handler.redirect_request(request,None,302,'Found',{},'https://evil.example/x.jpg')
