import unittest
from discover_facts import eligible_urls,validate_facts,validate_review
class DiscoveryTests(unittest.TestCase):
    def test_only_reviewed_hosts_and_html_candidates(self):
        a={'sources':[{'url':u} for u in ['https://evil.example/a','https://www.cp.pt/a.pdf','https://www.cp.pt/info/en/w/luggage','https://user:password@www.cp.pt/','http://www.cp.pt/']]}
        self.assertEqual(eligible_urls(a),['https://www.cp.pt/info/en/w/luggage'])
    def test_empty_result_is_normal_not_fabricated(self):
        self.assertEqual(validate_facts({'facts':[]},[]),[])
    def test_quote_absent_fails(self):
        r={'facts':[{'id':'c1','fact':'Une affirmation suffisamment longue.','source':0,'quote':'citation non présente ici','usefulness':'Choisir une gare de départ.'}]}
        with self.assertRaisesRegex(ValueError,'quote_not_in_source'):validate_facts(r,[{'text':'different'}])
    def test_duplicate_review_cannot_hide_unchecked_fact(self):
        decision={'id':'c1','supported':True,'newInformation':True,'useful':True,'reason':'Preuve exacte'}
        with self.assertRaisesRegex(ValueError,'decision_id'):validate_review({'decisions':[decision,decision]},[{'id':'c1'},{'id':'c2'}])
    def test_known_information_is_not_an_update(self):
        decision={'id':'c1','supported':True,'newInformation':False,'useful':True,'reason':'Déjà présent dans le guide'}
        self.assertEqual(validate_review({'decisions':[decision]},[{'id':'c1'}]),set())

class FactQuarantineTests(unittest.TestCase):
    def fact(self,identity,source):
        return {'id':identity,'fact':'Le fait est explicitement documenté.','source':source,'quote':'A sufficiently long exact quotation.','usefulness':'Choisir une gare de départ.'}
    def test_invalid_source_never_enters_retained_facts(self):
        from discover_facts import partition_facts
        good,bad=partition_facts({'facts':[self.fact('c1',0),self.fact('c2',6)]},[{'text':'A sufficiently long exact quotation.'}])
        self.assertEqual([x['id'] for x in good],['c1'])
        self.assertEqual(bad,[{'index':1,'id':'c2','reason':'source_index'}])
    def test_all_bad_returns_empty_not_approval(self):
        from discover_facts import partition_facts
        good,bad=partition_facts({'facts':[self.fact('c1',6)]},[])
        self.assertEqual(good,[]);self.assertEqual(len(bad),1)
    def test_duplicates_fail_whole_packet(self):
        from discover_facts import partition_facts
        with self.assertRaisesRegex(ValueError,'duplicate_fact_identity'):
            partition_facts({'facts':[self.fact('c1',0),self.fact('c1',6)]},[{'text':'A sufficiently long exact quotation.'}])
