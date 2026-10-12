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
    def test_changed_article_cannot_promote_old_draft(self):
        self.article['title']='Titre changé'
        with self.assertRaisesRegex(ValueError,'article_changed'):select([self.article],self.root,set(),None,NOW)
    def test_unconnected_board_does_not_receive_pin(self):
        self.article['destination']='Porto'
        self.assertEqual(select([self.article],self.root,set(),None,NOW)[1],'no_eligible_new_draft')
    def test_changed_image_is_rejected(self):
        (self.folder/'pin.jpg').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'image_changed'):select([self.article],self.root,set(),None,NOW)
    def test_unknown_renderer_is_rejected(self):
        p=self.folder/'draft.json';m=json.loads(p.read_text());m['rendererSha256']='0'*64;p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'unqualified_renderer'):select([self.article],self.root,set(),None,NOW)
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
    def test_unavailable_target_leaves_feed_and_media_unchanged(self):
        from pin_promotion import run
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);production,site=self.fixture(root)
            before=(site/'pinterest-additions.json').read_bytes()
            def unavailable(*args):raise ValueError('unavailable')
            with self.assertRaisesRegex(ValueError,'unavailable'):run(root,NOW,unavailable)
            self.assertEqual((site/'pinterest-additions.json').read_bytes(),before)
            self.assertFalse((site/'social-media').exists())
