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

class GuideSelectionTests(unittest.TestCase):
    def test_unknown_override_cannot_supply_arbitrary_source(self):
        import datetime as dt
        from discover_facts import select_guide
        with self.assertRaisesRegex(ValueError,'unknown_or_ineligible_guide'):
            select_guide([],dt.datetime.now(dt.timezone.utc),'https://evil.example')
    def test_override_selects_existing_article_only(self):
        import datetime as dt
        from discover_facts import select_guide
        article={'slug':'bagages','sources':[{'url':'https://www.cp.pt/info/en/w/luggage'},{'url':'https://www.metrolisboa.pt/en/better-manners-better-rides/'}]}
        self.assertIs(select_guide([article],dt.datetime.now(dt.timezone.utc),'bagages'),article)

class SourceCoverageTests(unittest.TestCase):
    def test_every_source_is_visited_with_three_page_bound(self):
        from discover_facts import source_window
        for n in range(1,11):
            urls=[f'https://www.cp.pt/info/en/w/test-{i}' for i in range(n)]
            article={'sources':[{'url':u} for u in urls]}
            windows=[source_window(article,p) for p in range((n+2)//3)]
            self.assertTrue(all(1<=len(w)<=3 for w in windows))
            self.assertEqual([u for w in windows for u in w],urls)
            self.assertEqual(source_window(article,len(windows)),windows[0])
    def test_negative_pass_rejected(self):
        from discover_facts import source_window
        with self.assertRaisesRegex(ValueError,'invalid_source_pass'):source_window({},-1)

class SourceContextTests(unittest.TestCase):
    def test_context_is_derived_from_selected_source_not_model(self):
        from discover_facts import attach_context
        fact={'id':'c1','source':0,'quote':'Time limit - 24 hours'}
        source={'url':'https://www.cp.pt/info/en/w/left-luggage','label':'CP — consignes','text':'Automatic lockers. Time limit - 24 hours. Station hours apply.'}
        result=attach_context([fact],[source])[0]
        self.assertEqual(result['sourceContext']['url'],source['url'])
        self.assertIn('Station hours apply.',result['sourceContext']['excerpt'])
        self.assertNotIn('sourceContext',fact)
