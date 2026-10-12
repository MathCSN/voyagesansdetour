import datetime as dt
from html import escape
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import promote_catalogue as control
import promote_selected

CANDIDATE=control.promote_selected.storyboard.pilot.HERE.parent/'voice-revisions/complete-sentences/reel-article-portugal-sans-voiture-bagages'
NOW=dt.datetime(2026,10,12,12,tzinfo=dt.timezone.utc)
def source(url):
    draft=json.loads((CANDIDATE/'media/storyboard.json').read_text())
    return ('<link rel="canonical" href="'+draft['targetUrl']+'">'+''.join('<p>'+escape(e['text'])+'</p>' for e in draft['narration']['excerpts'])).encode()
def stage(c,s,n):return promote_selected.stage(c,s,n,source)
class PromotionTests(unittest.TestCase):
    def fixture(self,tmp):
        root=Path(tmp)/'production';root.mkdir();candidate=root/'voice-stock'/CANDIDATE.name;shutil.copytree(CANDIDATE,candidate)
        site=Path(tmp)/'site';site.mkdir();(site/'public-media.json').write_text('{"schemaVersion":1,"items":[]}')
        return root,site,candidate
    def test_stage_then_public_confirmation_then_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,site,candidate=self.fixture(tmp)
            result=control.run(root,site,NOW,lambda *a:None,stage)
            self.assertTrue(result['needsDeployment']);self.assertFalse((candidate/'public-media-proof.json').exists())
            fetch=lambda url,limit:(site/url.split('https://voyagesansdetour.fr/')[1]).read_bytes()
            result=control.run(root,site,NOW,fetch,stage)
            self.assertFalse(result['needsDeployment']);self.assertEqual(result['status'],'public_bytes_confirmed')
            before=(candidate/'public-media-proof.json').read_bytes()
            self.assertEqual(control.run(root,site,NOW,lambda *a:self.fail('network'),lambda *a:self.fail('stage'))['status'],'no_pending_selected_media')
            self.assertEqual(before,(candidate/'public-media-proof.json').read_bytes())
    def test_public_conflict_and_unavailable_do_not_approve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,site,candidate=self.fixture(tmp)
            with self.assertRaisesRegex(ValueError,'public_bytes_conflict'):control.run(root,site,NOW,lambda *a:b'wrong',stage)
            def unavailable(*a):raise TimeoutError('unavailable')
            with self.assertRaises(TimeoutError):control.run(root,site,NOW,unavailable,stage)
            self.assertFalse((candidate/'public-media-proof.json').exists())
    def test_existing_receipt_cannot_hide_changed_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,site,candidate=self.fixture(tmp)
            (candidate/'public-media-proof.json').write_text(json.dumps({'selectionSha256':'0'*64,'contentId':candidate.name}))
            with self.assertRaisesRegex(ValueError,'public_proof_conflict'):control.run(root,site,NOW)
    def test_expiry_and_stop_precede_staging(self):
        self.assertEqual(control.run('/absent','/absent',control.stock.STOP)['status'],'period_ended')
        with tempfile.TemporaryDirectory() as tmp:
            root,site,candidate=self.fixture(tmp)
            result=control.run(root,site,dt.datetime(2026,11,1,tzinfo=dt.timezone.utc),stage=lambda *a:self.fail('expired'))
            self.assertEqual(result['status'],'no_pending_selected_media')
if __name__=='__main__':unittest.main()
