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
    def test_stale_draft_is_rendered_again_from_the_updated_guide(self):
        with tempfile.TemporaryDirectory() as folder:
            now=dt.datetime(2026,10,19,tzinfo=dt.timezone.utc)
            render({'slug':'guide','title':'Ancien titre'},folder)
            result=intake([{'slug':'guide','title':'Nouveau titre'}],[],folder,now)
            self.assertEqual(result['status'],'draft_refreshed_not_published')
            self.assertEqual(json.loads((Path(folder)/'pin-guide/draft.json').read_text())['title'],'Nouveau titre')
            self.assertEqual(intake([{'slug':'guide','title':'Nouveau titre'}],[],folder,now)['status'],'no_new_article')
    def test_draft_from_a_previous_template_is_rendered_again(self):
        with tempfile.TemporaryDirectory() as folder:
            article={'slug':'guide','title':'Un guide'}
            target=render(article,folder);p=target/'draft.json';m=json.loads(p.read_text());m['rendererSha256']='0'*64;p.write_text(json.dumps(m))
            result=intake([article],[],folder,dt.datetime(2026,10,19,tzinfo=dt.timezone.utc))
            self.assertEqual(result['status'],'draft_refreshed_not_published')
            self.assertNotEqual(json.loads(p.read_text())['rendererSha256'],'0'*64)
    def test_failed_redraw_keeps_the_old_draft_and_moves_on(self):
        with tempfile.TemporaryDirectory() as folder:
            now=dt.datetime(2026,10,19,tzinfo=dt.timezone.utc)
            render({'slug':'guide','title':'Ancien titre'},folder)
            def renderer(article,output):
                if article['slug']=='guide':raise ValueError('title_overflow')
                return render(article,output)
            result=intake([{'slug':'guide','title':'Titre trop long'},{'slug':'autre','title':'Un autre guide'}],[],folder,now,renderer)
            self.assertEqual(result['id'],'pin-autre')
            self.assertEqual(json.loads((Path(folder)/'pin-guide/draft.json').read_text())['title'],'Ancien titre')
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()),['pin-autre','pin-guide'])
    def test_admitted_draft_is_never_rendered_again(self):
        with tempfile.TemporaryDirectory() as folder:
            render({'slug':'guide','title':'Ancien titre'},folder)
            result=intake([{'slug':'guide','title':'Nouveau titre'}],[],folder,dt.datetime(2026,10,19,tzinfo=dt.timezone.utc),admitted=['pin-guide'])
            self.assertEqual(result['status'],'no_new_article')
            self.assertEqual(json.loads((Path(folder)/'pin-guide/draft.json').read_text())['title'],'Ancien titre')
    def test_guide_outside_portugal_gets_its_country_path(self):
        with tempfile.TemporaryDirectory() as folder:
            now=dt.datetime(2026,10,24,tzinfo=dt.timezone.utc)
            article={'slug':'cinque-terre','title':'Cinque Terre sans voiture','country':'italie','publishedOn':'2026-10-24'}
            self.assertEqual(intake([article],[],folder,now)['id'],'pin-cinque-terre')
            self.assertEqual(json.loads((Path(folder)/'pin-cinque-terre/draft.json').read_text())['targetUrl'],'https://voyagesansdetour.fr/italie/cinque-terre/')
            self.assertEqual(intake([article],[],folder,now)['status'],'no_new_article')
    def test_unrenderable_new_guide_is_held_and_the_next_one_drafted(self):
        with tempfile.TemporaryDirectory() as folder:
            now=dt.datetime(2026,10,24,tzinfo=dt.timezone.utc)
            articles=[{'slug':'casse','title':'X','country':'Pas un pays','publishedOn':'2026-10-24'},{'slug':'bon','title':'Un bon guide','publishedOn':'2026-10-23'}]
            result=intake(articles,[],folder,now)
            self.assertEqual(result['id'],'pin-bon');self.assertEqual(result['held'],[{'id':'pin-casse','reason':'invalid_country'}])
    def test_invalid_country_is_refused(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError,'invalid_country'):
            render({'slug':'x','title':'X','country':'../etc'},folder)
    def test_end_of_authorization_does_not_render(self):
        def fail(*args):raise AssertionError('render called')
        self.assertEqual(intake([],[],Path('unused'),STOP,fail)['status'],'period_ended')
