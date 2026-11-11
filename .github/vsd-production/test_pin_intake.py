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
    def test_every_guide_gets_its_first_pin_before_any_variant_and_a_run_draws_several(self):
        from pin_intake import intake_many
        drawn=[]
        def renderer(article,output,variant='a'):
            drawn.append((article['slug'],variant));return self.fake(article,output,variant)
        articles=[{'slug':'ancien','title':'Ancien guide','cover':'x','publishedOn':'2026-10-01'},{'slug':'recent','title':'Guide récent','cover':'x','publishedOn':'2026-10-20'},
                  {'slug':'reserve','title':'Guide du lancement','cover':'x','publishedOn':'2026-09-01'}]
        with tempfile.TemporaryDirectory() as folder:
            now=dt.datetime(2026,10,24,tzinfo=dt.timezone.utc)
            result=intake_many(articles,['reserve'],folder,now,renderer,limit=4)
            self.assertEqual(result['ids'],['pin-recent','pin-ancien','pin-recent-b','pin-ancien-b'])
            again=intake_many(articles,['reserve'],folder,now,renderer,limit=10)
            self.assertEqual(again['ids'],['pin-reserve-b','pin-recent-c','pin-ancien-c','pin-reserve-c'])  # a reserved guide keeps its launch Pin, variants are new
            self.assertEqual(intake_many(articles,['reserve'],folder,now,renderer)['status'],'no_new_article')
    def fake(self,article,output,variant):
        import hashlib
        from pin_draft import pin_id
        from pin_intake import digest,renderer_sha256
        target=Path(output)/pin_id(article['slug'],variant);target.mkdir(parents=True);(target/'pin.jpg').write_bytes(variant.encode())
        manifest={'id':target.name,'variant':variant,'status':'draft_requires_review','publicationApproved':False,'title':article['title'],
                  'targetUrl':'https://voyagesansdetour.fr/portugal/'+article['slug']+'/','articleSha256':digest(article),
                  'imageSha256':hashlib.sha256(variant.encode()).hexdigest(),'rendererSha256':renderer_sha256()}
        (target/'draft.json').write_text(json.dumps(manifest));return target
    def test_a_redraw_interrupted_by_any_error_never_blocks_the_next_run(self):
        with tempfile.TemporaryDirectory() as folder:
            now=dt.datetime(2026,10,19,tzinfo=dt.timezone.utc)
            render({'slug':'guide','title':'Ancien titre'},folder)
            def missing_photo(article,output):raise OSError('photo file missing')
            self.assertEqual(intake([{'slug':'guide','title':'Nouveau titre'}],[],folder,now,missing_photo)['status'],'no_new_article')
            self.assertEqual([p.name for p in Path(folder).iterdir()],['pin-guide'])
            (Path(folder)/'pin-guide').rename(Path(folder)/'.pin-guide.previous')  # as a killed run would leave it
            self.assertEqual(intake([{'slug':'guide','title':'Nouveau titre'}],[],folder,now)['status'],'draft_refreshed_not_published')
            self.assertEqual([p.name for p in Path(folder).iterdir()],['pin-guide'])
    def test_a_guide_whose_slug_ends_like_a_variant_never_collides_with_another_guide_pin(self):
        from pin_intake import intake_many
        articles=[{'slug':'kyoto','title':'Kyoto','cover':'x','publishedOn':'2026-10-02'},{'slug':'kyoto-b','title':'Kyoto bis','cover':'x','publishedOn':'2026-10-01'}]
        with tempfile.TemporaryDirectory() as folder:
            ids=intake_many(articles,[],folder,dt.datetime(2026,10,24,tzinfo=dt.timezone.utc),lambda article,output,variant='a':self.fake(article,output,variant),limit=10)['ids']
            self.assertEqual(ids,['pin-kyoto','pin-kyoto-b','pin-kyoto-c'])  # 'pin-kyoto-b' is the guide kyoto-b, drawn once
            self.assertEqual(json.loads((Path(folder)/'pin-kyoto-b/draft.json').read_text())['title'],'Kyoto bis')
    def test_invalid_country_is_refused(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError,'invalid_country'):
            render({'slug':'x','title':'X','country':'../etc'},folder)
    def test_end_of_authorization_does_not_render(self):
        def fail(*args):raise AssertionError('render called')
        self.assertEqual(intake([],[],Path('unused'),STOP,fail)['status'],'period_ended')
