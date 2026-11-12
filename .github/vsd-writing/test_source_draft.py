import copy
import unittest
from source_draft import validate

class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.sources=[{'text':'The palace requires a timed entry ticket. Take the train to Sintra.'}]
        self.draft={'title':'Préparer une visite à Sintra','claims':[
            {'id':'c1','fact':'Le palais demande un billet avec créneau.','source':0,'quote':'The palace requires a timed entry ticket.'},
            {'id':'c2','fact':'Il est possible de prendre le train vers Sintra.','source':0,'quote':'Take the train to Sintra.'}],
            'sections':[{'title':'Préparer son trajet','paragraph':'Une proposition de paragraphe pour la visite. '*4,'claims':['c1','c2']} for _ in range(3)]}
    def test_valid_exact_evidence(self):
        validate(self.draft,self.sources)
    def test_fabricated_quote_rejected(self):
        self.draft['claims'][0]['quote']='The palace is always free for everyone.'
        with self.assertRaisesRegex(ValueError,'quote_not_in_source'):validate(self.draft,self.sources)
    def test_unknown_claim_rejected(self):
        self.draft['sections'][0]['claims']=['invented']
        with self.assertRaisesRegex(ValueError,'section_claims'):validate(self.draft,self.sources)
    def test_unapproved_source_rejected(self):
        self.draft['claims'][0]['source']=-1
        with self.assertRaisesRegex(ValueError,'source_index'):validate(self.draft,self.sources)
    def test_duplicate_claim_rejected(self):
        self.draft['claims'][1]['id']='c1'
        with self.assertRaisesRegex(ValueError,'claim_id'):validate(self.draft,self.sources)

class ProviderAccessTests(unittest.TestCase):
    """A token the model provider refuses must fail the run; a busy or broken provider only holds it."""
    def call_with(self,code):
        import datetime as dt,urllib.error
        from unittest import mock
        import source_draft
        class Opener:
            def open(self,request,timeout=None):raise urllib.error.HTTPError(request.full_url,code,'refused',None,None)
        with mock.patch.object(source_draft,'HARD_STOP',dt.datetime(2999,1,1,tzinfo=dt.timezone.utc)), \
             mock.patch.object(source_draft,'quota_hold',return_value=None), \
             mock.patch.object(source_draft.urllib.request,'build_opener',return_value=Opener()):
            return source_draft.call([{'role':'user','content':'x'}],10,'jeton-secret')

    def test_a_refused_or_revoked_token_is_a_setup_failure(self):
        from source_draft import ProviderAccessError
        for code in (401,403):
            with self.subTest(code=code):
                with self.assertRaises(ProviderAccessError) as raised:self.call_with(code)
                self.assertEqual(str(raised.exception),'provider_access_refused')
                self.assertNotIn('jeton-secret',repr(raised.exception))

    def test_other_provider_errors_keep_their_http_error(self):
        import urllib.error
        for code in (429,500,503):
            with self.subTest(code=code):
                with self.assertRaises(urllib.error.HTTPError) as raised:self.call_with(code)
                self.assertEqual(raised.exception.code,code)

if __name__=='__main__': unittest.main()

class LedgerTests(unittest.TestCase):
    def test_changed_fact_stops_before_inference(self):
        from source_draft import bind_facts
        with self.assertRaisesRegex(ValueError,'reviewed_fact_changed'):
            bind_facts([{'text':'different page'}, {'text':'different page'}])
    def test_ledger_is_copied_not_rewritten_by_output(self):
        from source_draft import bind_facts, FACTS
        sources=[{'text':' '.join(f['quote'] for f in FACTS if f['source']==i)} for i in range(2)]
        result=bind_facts(sources)
        result[0]['fact']='injected'
        self.assertNotEqual(FACTS[0]['fact'],'injected')

class QualityGateTests(unittest.TestCase):
    def test_generic_conclusion_repeating_all_facts_is_rejected(self):
        from source_draft import validate_coverage
        draft={'claims':[{'id':'c1'},{'id':'c2'}], 'sections':[
            {'claims':['c1']},{'claims':['c2']},{'claims':['c1','c2']}]}
        with self.assertRaisesRegex(ValueError,'section_without_new_fact'):validate_coverage(draft)
    def test_omitted_fact_rejected(self):
        from source_draft import validate_coverage
        with self.assertRaisesRegex(ValueError,'unused_ledger_fact'):
            validate_coverage({'claims':[{'id':'c1'},{'id':'c2'}],'sections':[{'claims':['c1']}]})
    def test_review_with_unexamined_claim_rejected(self):
        from source_draft import check_review
        with self.assertRaisesRegex(ValueError,'review_coverage'):
            check_review({'supported':True,'issues':[],'checkedClaimIds':['c1']},{'claims':[{'id':'c1'},{'id':'c2'}]})
    def test_contradictory_review_rejected(self):
        from source_draft import check_review
        with self.assertRaisesRegex(ValueError,'review_contradictory'):
            check_review({'supported':True,'issues':['unsupported'],'checkedClaimIds':['c1']},{'claims':[{'id':'c1'}]})
