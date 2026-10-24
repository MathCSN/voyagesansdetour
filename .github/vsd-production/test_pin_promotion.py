import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from pin_draft import render
from pin_promotion import select,STOP

NOW=dt.datetime(2026,10,19,tzinfo=dt.timezone.utc)
class PinPromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.article={'slug':'test-guide','title':'Un guide pour le Portugal','destination':'Portugal'}
        self.folder=render(self.article,self.root)
    def test_exact_title_can_be_selected_only_after_cadence(self):
        chosen,status=select([self.article],self.root,set(),NOW-dt.timedelta(days=7),NOW)
        self.assertEqual(status,'eligible');self.assertEqual(chosen[1]['title'],self.article['title'])
        self.assertEqual(select([self.article],self.root,set(),NOW-dt.timedelta(days=6),NOW)[1],'cadence_hold')
    def test_known_id_never_republished(self):
        self.assertEqual(select([self.article],self.root,{'pin-test-guide'},None,NOW)[1],'no_eligible_new_draft')
    def test_changed_article_skips_old_draft_without_blocking(self):
        self.article['title']='Titre changé'
        self.assertEqual(select([self.article],self.root,set(),None,NOW)[1],'no_eligible_new_draft')
    def test_stale_draft_does_not_block_next_fresh_draft(self):
        other={'slug':'autre-guide','title':'Un autre guide du Portugal','destination':'Porto'}
        render(other,self.root)
        self.article['title']='Titre changé'
        chosen,status=select([self.article,other],self.root,set(),None,NOW)
        self.assertEqual(status,'eligible');self.assertEqual(chosen[1]['id'],'pin-autre-guide')
    def test_city_guide_reaches_the_portugal_preparation_board(self):
        city={'slug':'guide-porto','title':'Un guide pour Porto','destination':'Porto'}
        render(city,self.root)
        chosen,status=select([city],self.root,set(),None,NOW)
        self.assertEqual(status,'eligible');self.assertEqual(chosen[1]['id'],'pin-guide-porto')
    def test_changed_image_is_rejected(self):
        (self.folder/'pin.jpg').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'image_changed'):select([self.article],self.root,set(),None,NOW)
    def test_draft_from_another_template_waits_for_redraw(self):
        p=self.folder/'draft.json';m=json.loads(p.read_text());m['rendererSha256']='0'*64;p.write_text(json.dumps(m))
        self.assertEqual(select([self.article],self.root,set(),None,NOW)[1],'no_eligible_new_draft')
    def test_guide_outside_portugal_waits_for_a_connected_board(self):
        spain={'slug':'andalousie','title':'Andalousie en train','country':'espagne'}
        folder=render(spain,self.root)
        self.assertEqual(json.loads((folder/'draft.json').read_text())['targetUrl'],'https://voyagesansdetour.fr/espagne/andalousie/')
        chosen,status=select([spain,self.article],self.root,set(),None,NOW)
        self.assertEqual(status,'eligible');self.assertEqual(chosen[1]['id'],'pin-test-guide')
        self.assertEqual(select([spain],self.root,{'pin-test-guide'},None,NOW)[1],'no_eligible_new_draft')
    def test_stop_date(self):
        self.assertEqual(select([self.article],self.root,set(),None,STOP)[1],'period_ended')

class PinAdmissionTests(unittest.TestCase):
    def fixture(self,root):
        production=root/'.github/vsd-production';production.mkdir(parents=True)
        site=root/'site-src';site.mkdir()
        article={'slug':'test-guide','title':'Un guide pour le Portugal','destination':'Portugal'}
        render(article,production/'pin-drafts')
        for path,value in [(site/'articles.json',[article]),(site/'public-media.json',{'schemaVersion':1,'items':[]}),(site/'pinterest-rss.json',{'items':[]}),(site/'pinterest-additions.json',{'schemaVersion':1,'feeds':[{'file':'preparer-portugal.xml','title':'Préparation','items':[]}]}),(production/'pin-admissions.json',{'schemaVersion':1,'items':[]})]:path.write_text(json.dumps(value))
        return production,site
    def test_admission_persists_bound_media_feed_and_receipt_without_second_send(self):
        from pin_promotion import run
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);production,site=self.fixture(root)
            result=run(root,NOW,lambda url,title:'a'*64)
            self.assertEqual(result['status'],'admitted_to_feed_not_published')
            self.assertFalse(result['publicationConfirmed'])
            self.assertTrue((site/'social-media/production/pin-test-guide/pin.jpg').is_file())
            self.assertEqual(json.loads((site/'pinterest-additions.json').read_text())['feeds'][0]['items'][0]['id'],'pin-test-guide')
            self.assertEqual(run(root,NOW+dt.timedelta(days=8),lambda *a: self.fail('Must not refetch'))['status'],'no_eligible_new_draft')
    def test_unavailable_target_is_held_without_blocking_or_changing_files(self):
        from pin_promotion import run
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);production,site=self.fixture(root)
            before=(site/'pinterest-additions.json').read_bytes()
            def unavailable(*args):raise OSError('HTTP Error 404')
            result=run(root,NOW,unavailable)
            self.assertEqual(result['status'],'no_eligible_new_draft');self.assertEqual(result['held'],[{'id':'pin-test-guide','reason':'public_target_unavailable'}])
            self.assertEqual((site/'pinterest-additions.json').read_bytes(),before)
            self.assertFalse((site/'social-media').exists())
    def test_unavailable_target_lets_the_next_draft_through(self):
        from pin_promotion import run
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);production,site=self.fixture(root)
            other={'slug':'autre-guide','title':'Un autre guide','country':'portugal'}
            render(other,production/'pin-drafts')
            (site/'articles.json').write_text(json.dumps([json.loads((site/'articles.json').read_text())[0],other]))
            def fetch(url,title):
                if 'autre-guide' in url:raise OSError('HTTP Error 404')
                return 'a'*64
            result=run(root,NOW,fetch)
            self.assertEqual(result['id'],'pin-test-guide');self.assertEqual(result['held'][0]['id'],'pin-autre-guide')
