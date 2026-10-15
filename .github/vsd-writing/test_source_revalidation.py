import copy
import unittest
from unittest.mock import Mock
from guide_revision import revalidate_changed_sources

class SourceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.fact={'id':'c1','fact':'Le musée présente un escalier.','quote':'An original staircase.','sourceContext':{'url':'https://official.example/page','excerpt':'Old context'}}
        self.proposal={'facts':[self.fact],'sourceManifest':[{'url':'https://official.example/page','sha256':'old'}]}
        self.docs={'https://official.example/page':{'sha256':'new','text':'Current context. An original staircase. New restriction.'}}
        self.call=Mock(return_value=({'checks':[{'id':'c1','entailed':True,'unsupportedDetails':[]}]},{}))
    def test_refresh_requires_new_review_and_preserves_original(self):
        before=copy.deepcopy(self.proposal)
        facts,manifest=revalidate_changed_sources(self.proposal,self.docs,'token',self.call)
        self.assertEqual(self.proposal,before)
        self.assertIn('New restriction',facts[0]['sourceContext']['excerpt'])
        self.assertEqual(manifest[0]['sha256'],'new')
        self.call.assert_called_once()
        self.assertIn('New restriction',self.call.call_args.args[0][1]['content'])
    def test_missing_or_ambiguous_quote_stops_without_inference(self):
        for text in ['Not the quote',self.fact['quote']*2]:
            self.docs['https://official.example/page']['text']=text
            with self.assertRaises(ValueError):revalidate_changed_sources(self.proposal,self.docs,'token',self.call)
        self.call.assert_not_called()
    def test_new_restriction_can_reject_old_fact(self):
        self.call.return_value=({'checks':[{'id':'c1','entailed':False,'unsupportedDetails':['Restriction omitted']}]},{})
        with self.assertRaisesRegex(ValueError,'refreshed_facts_held'):
            revalidate_changed_sources(self.proposal,self.docs,'token',self.call)
