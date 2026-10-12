import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from pin_intake import intake,STOP
from pin_draft import render

class PinIntakeTests(unittest.TestCase):
    def test_existing_launch_pin_is_not_recreated_and_next_run_moves_on(self):
        articles=[{'slug':'reserved','title':'Réservé','publishedOn':'2026-10-12'}, {'slug':'new','title':'Un nouveau guide','publishedOn':'2026-10-11'}]
        with tempfile.TemporaryDirectory() as folder:
            now=dt.datetime(2026,10,12,tzinfo=dt.timezone.utc)
            first=intake(articles,['reserved'],folder,now)
            self.assertEqual(first['id'],'pin-new')
            self.assertFalse(first['publicationAttempted'])
            self.assertEqual(intake(articles,['reserved'],folder,now)['status'],'no_new_article')
            manifest=json.loads((Path(folder)/'pin-new/draft.json').read_text())
            self.assertFalse(manifest['publicationApproved'])
    def test_corrupt_existing_artifact_stops_instead_of_recreating(self):
        with tempfile.TemporaryDirectory() as folder:
            article={'slug':'new','title':'Guide'}
            target=render(article,folder);(target/'pin.jpg').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'draft_image_changed'):
                intake([article],[],folder,dt.datetime(2026,10,12,tzinfo=dt.timezone.utc))
    def test_end_of_authorization_does_not_render(self):
        def fail(*args):raise AssertionError('render called')
        self.assertEqual(intake([],[],Path('unused'),STOP,fail)['status'],'period_ended')
