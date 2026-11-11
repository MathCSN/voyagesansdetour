import unittest
from discover_facts import eligible_urls,validate_facts,validate_review
class DiscoveryTests(unittest.TestCase):
    def test_every_published_guide_can_receive_automatic_updates(self):
        import json
        from pathlib import Path
        articles=json.loads((Path(__file__).resolve().parents[2]/'site-src/articles.json').read_text())
        for article in articles:
            with self.subTest(guide=article['slug']):
                self.assertGreaterEqual(len(eligible_urls(article)),2)
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

class UnreachableSourceTests(unittest.TestCase):
    """One dead source is skipped and noted; only a broken configuration fails the run."""
    URLS=['https://www.cp.pt/info/en/w/a','https://www.cp.pt/info/en/w/b','https://www.cp.pt/info/en/w/c']

    def article(self):
        return {'slug':'guide-test','title':'Guide de test','category':'Itinéraires',
                'sources':[{'label':f'Source {i}','url':url} for i,url in enumerate(self.URLS)]}

    def fetcher(self,dead):
        import urllib.error
        def fetch(url,opener=None):
            if url in dead:raise urllib.error.HTTPError(url,503,'Service Unavailable',None,None)
            return {'sha256':'0'*64,'text':'Visible text of '+url}
        return fetch

    def run_main(self,dead,token='token',facts=None):
        import datetime as dt,json,os,tempfile
        from pathlib import Path
        from unittest import mock
        import discover_facts
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'site-src';root.mkdir()
            (root/'articles.json').write_text(json.dumps([self.article()]))
            out=Path(folder)/'report'
            env={'REPORT_DIR':str(out),'GUIDE_SLUG':'guide-test','CLOUDFLARE_WORKERS_AI_TOKEN':token}
            calls=mock.Mock(return_value=({'facts':facts or []},{'neurons':1}))
            with mock.patch.dict(os.environ,env),mock.patch.object(discover_facts,'ROOT',root), \
                 mock.patch.object(discover_facts,'HARD_STOP',dt.datetime(2999,1,1,tzinfo=dt.timezone.utc)), \
                 mock.patch.object(discover_facts,'quota_hold',return_value=None), \
                 mock.patch.object(discover_facts,'source_fingerprint',self.fetcher(dead)), \
                 mock.patch.object(discover_facts,'call',calls):
                code=discover_facts.main()
            return code,json.loads((out/'discovery-report.json').read_text()),calls

    def test_unreachable_source_is_skipped_and_noted(self):
        from discover_facts import read_sources
        sources,skipped=read_sources(self.article(),self.URLS,self.fetcher({self.URLS[1]}))
        self.assertEqual([s['url'] for s in sources],[self.URLS[0],self.URLS[2]])
        self.assertEqual([s['label'] for s in sources],['Source 0','Source 2'])
        self.assertEqual(skipped,[{'url':self.URLS[1],'errorType':'HTTPError','reason':'http_503'}])

    def test_refused_document_and_network_failure_are_skipped_too(self):
        from discover_facts import read_sources
        def fetch(url,opener=None):
            if url==self.URLS[0]:raise ValueError('La source ne renvoie pas du HTML.')
            if url==self.URLS[1]:raise TimeoutError('timed out')
            return {'sha256':'0'*64,'text':'Visible text'}
        sources,skipped=read_sources(self.article(),self.URLS,fetch)
        self.assertEqual(len(sources),1)
        self.assertEqual([s['reason'] for s in skipped],['La source ne renvoie pas du HTML.','timeouterror'])

    def test_run_continues_with_the_remaining_sources(self):
        code,report,calls=self.run_main({self.URLS[0]})
        self.assertEqual(code,0)
        self.assertEqual(report['status'],'no_new_facts')
        self.assertEqual([s['url'] for s in report['sources']],self.URLS[1:])
        self.assertEqual([s['url'] for s in report['skippedSources']],[self.URLS[0]])
        self.assertEqual(calls.call_count,1)

    def test_no_reachable_source_holds_the_run_without_failing_the_workflow(self):
        code,report,calls=self.run_main(set(self.URLS))
        self.assertEqual(code,0)
        self.assertEqual(report['status'],'held_no_source')
        self.assertEqual(len(report['skippedSources']),3)
        self.assertEqual(report['callsAttempted'],0)
        calls.assert_not_called()

    def test_broken_configuration_still_fails_the_workflow(self):
        code,report,_=self.run_main(set(),token='')
        self.assertEqual(code,1)
        self.assertEqual((report['status'],report['reason']),('held_no_retry','missing_secret'))

class GuideRotationTests(unittest.TestCase):
    def guides(self,count):
        sources=[{'url':'https://www.cp.pt/info/en/w/a'},{'url':'https://www.cp.pt/info/en/w/b'}]
        return [{'slug':f'guide-{i:03d}','sources':sources} for i in range(count)]

    def test_a_catalogue_growing_every_two_days_never_freezes_the_rotation(self):
        # day % len(catalogue) stayed on the same two guides while one guide was added every two days.
        import datetime as dt
        from discover_facts import select_guide
        start=dt.datetime(2026,11,4,12,tzinfo=dt.timezone.utc)
        visited={select_guide(self.guides(22+day//2),start+dt.timedelta(days=day))['slug'] for day in range(120)}
        self.assertGreaterEqual(len(visited),20)

    def test_selection_is_stable_within_a_day_and_bounded(self):
        import datetime as dt
        from discover_facts import select_guide,rotation
        morning=dt.datetime(2026,11,11,6,tzinfo=dt.timezone.utc)
        evening=dt.datetime(2026,11,11,22,tzinfo=dt.timezone.utc)
        self.assertEqual(rotation(morning),rotation(evening))
        guides=self.guides(7)
        self.assertIs(select_guide(guides,morning),select_guide(guides,evening))

class SourceContextTests(unittest.TestCase):
    def test_context_is_derived_from_selected_source_not_model(self):
        from discover_facts import attach_context
        fact={'id':'c1','source':0,'quote':'Time limit - 24 hours'}
        source={'url':'https://www.cp.pt/info/en/w/left-luggage','label':'CP — consignes','text':'Automatic lockers. Time limit - 24 hours. Station hours apply.'}
        result=attach_context([fact],[source])[0]
        self.assertEqual(result['sourceContext']['url'],source['url'])
        self.assertIn('Station hours apply.',result['sourceContext']['excerpt'])
        self.assertNotIn('sourceContext',fact)
