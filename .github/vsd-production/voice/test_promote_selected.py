import datetime as dt
from html import escape
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import promote_selected as p
ROOT=p.storyboard.pilot.HERE.parent
CANDIDATE=ROOT/'voice-revisions/complete-sentences/reel-article-portugal-sans-voiture-bagages'
NOW=dt.datetime(2026,10,12,8,tzinfo=dt.timezone.utc)

def fetch(url):
    d=json.loads((CANDIDATE/'media/storyboard.json').read_text())
    return ('<link rel="canonical" href="'+d['targetUrl']+'">'+''.join('<p>'+escape(e['text'])+'</p>' for e in d['narration']['excerpts'])).encode()

class PromotionTests(unittest.TestCase):
    def test_stop_before_io(self):
        with patch('stock.validate',side_effect=AssertionError('io')):
            self.assertEqual(p.stage('/absent','/absent',p.stock.STOP)['status'],'period_ended')

    def test_stage_repeat_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);manifest=site/'public-media.json';manifest.write_text('{"schemaVersion":1,"items":[]}')
            result=p.stage(CANDIDATE,site,NOW,fetch)
            self.assertTrue(result['changed']);self.assertFalse(result['socialPublicationAttempted'])
            saved=manifest.read_bytes()
            self.assertFalse(p.stage(CANDIDATE,site,NOW,fetch)['changed'])
            self.assertEqual(saved,manifest.read_bytes())
            target=site/'social-media/production'/result['mediaId']/'reel.mp4';target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'existing_files_conflict'):p.stage(CANDIDATE,site,NOW,fetch)
            self.assertEqual(saved,manifest.read_bytes());self.assertEqual(target.read_bytes(),b'changed')

    def test_public_source_change_prevents_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);(site/'public-media.json').write_text('{"schemaVersion":1,"items":[]}')
            with self.assertRaisesRegex(ValueError,'public_excerpt_changed'):p.stage(CANDIDATE,site,NOW,lambda u:b'<p>Changed</p>')
            self.assertFalse((site/'social-media').exists())

if __name__=='__main__':unittest.main()
