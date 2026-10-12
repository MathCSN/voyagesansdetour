import copy
import datetime as dt
import html
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import reel_intake as reel

NOW=dt.datetime(2026,10,12,6,tzinfo=dt.timezone.utc)


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);self.root=base/'.github/vsd-production';self.root.mkdir(parents=True)
        self.site=base/'site-src';self.site.mkdir();self.output=self.root/'reel-drafts'
        (self.root/'reel-reservations.json').write_text('{"schemaVersion":1,"reservedSlugs":[]}')
        self.article={'slug':'bagages-portugal','title':'Préparer ses bagages','sourcesCheckedOn':'2026-10-01',
                      'publishedOn':'2026-10-10','sources':[{'url':'https://example.com/official'}],
                      'sections':[{'id':'sac','paragraphs':['Préparez les affaires du trajet dans une poche accessible, pour les retrouver sans défaire tout le sac.']},
                                  {'id':'depart','paragraphs':['La veille du départ, rassemblez les objets en charge et vérifiez les rangements avant de quitter la chambre.']}]}
        self.save()
    def save(self):
        (self.site/'articles.json').write_text(json.dumps([self.article],ensure_ascii=False))
    def fetch(self,url):
        return ('<html><link rel="canonical" href="'+url+'">'+''.join('<p>'+html.escape(s['paragraphs'][0])+'</p>' for s in self.article['sections'])+'</html>').encode()
    def run_intake(self,fetcher=None,now=NOW):
        return reel.run(self.root,self.output,now,self.fetch if fetcher is None else fetcher)
    def test_public_excerpts_create_one_immutable_draft(self):
        result=self.run_intake();self.assertEqual(result['created'],1)
        folder=self.output/result['id'];before=(folder/'storyboard.json').read_bytes()
        fetch=Mock(side_effect=AssertionError('known content fetch'))
        self.assertEqual(self.run_intake(fetch)['created'],0)
        self.assertEqual(before,(folder/'storyboard.json').read_bytes())
        self.assertFalse(json.loads(before)['publicationApproved'])
    def test_changed_article_does_not_reset_prior_identity(self):
        self.run_intake();self.article['title']='Un nouveau titre';self.save()
        self.assertEqual(self.run_intake(Mock(side_effect=AssertionError('fetch')))['created'],0)
    def test_missing_or_expired_source_date_blocks_before_fetch(self):
        for value in [None,'2026-08-01','2026-11-01']:
            self.article['sourcesCheckedOn']=value;self.save()
            self.assertEqual(self.run_intake(Mock(side_effect=AssertionError('fetch')))['created'],0)
        self.assertFalse(self.output.exists())
    def test_unpublished_excerpt_or_wrong_canonical_cannot_create_draft(self):
        for page in [b'<link rel="canonical" href="https://other.example/"><p>other</p>',
                     b'<link rel="canonical" href="https://voyagesansdetour.fr/portugal/bagages-portugal/"><p>changed</p>']:
            with self.assertRaises(ValueError):self.run_intake(lambda url:page)
        self.assertFalse(self.output.exists())
    def test_corruption_is_not_repaired_by_overwriting(self):
        result=self.run_intake();(self.output/result['id']/'storyboard.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'storyboard_changed'):self.run_intake()
    def test_annual_stop_reads_and_fetches_nothing(self):
        self.assertEqual(reel.run(Path('/absent'),now=reel.STOP,fetcher=Mock(side_effect=AssertionError('fetch')))['created'],0)

if __name__=='__main__':unittest.main()
