import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import storyboard

NOW=dt.datetime(2026,10,12,tzinfo=dt.timezone.utc)
FOLDER=storyboard.pilot.HERE.parent/'reel-drafts/reel-article-portugal-sans-voiture-bagages'

class StoryboardTests(unittest.TestCase):
    def test_annual_stop_before_io(self):
        with patch('storyboard.prepare',side_effect=AssertionError('io')):
            self.assertEqual(storyboard.run('/missing','/missing',storyboard.pilot.STOP)['generated'],0)

    def test_modified_storyboard_is_rejected_before_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/FOLDER.name;folder.mkdir()
            for name in ('receipt.json','storyboard.json'):(folder/name).write_bytes((FOLDER/name).read_bytes())
            (folder/'storyboard.json').write_text((folder/'storyboard.json').read_text()+' ')
            with self.assertRaisesRegex(ValueError,'storyboard_changed'):
                storyboard.prepare(folder,NOW,lambda u:self.fail('network'))

    def test_expiration_precedes_network(self):
        with self.assertRaisesRegex(ValueError,'source_review_expired'):
            storyboard.prepare(FOLDER,dt.datetime(2026,10,28,tzinfo=dt.timezone.utc),lambda u:self.fail('network'))

    def test_exact_text_and_readable_chunks(self):
        draft=json.loads((FOLDER/'storyboard.json').read_text())
        from html import escape
        html='<link rel="canonical" href="'+draft['targetUrl']+'">'+''.join('<p>'+escape(e['text'])+'</p>' for e in draft['narration']['excerpts'])
        data,chunks,headings,badges,_,_=storyboard.prepare(FOLDER,NOW,lambda u:html.encode())
        self.assertTrue(all(len(c)<=70 for c in chunks))
        self.assertEqual(len(chunks),len(headings));self.assertEqual(len(chunks),len(badges))
        self.assertEqual(' '.join(chunks),' '.join([draft['narration']['hook']]+[e['text'] for e in draft['narration']['excerpts']]+[draft['narration']['closing']]))

if __name__=='__main__':unittest.main()
