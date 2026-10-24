import copy
import datetime as dt
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
import guide_draft as g
import editorial_queue as q

PARAGRAPH=('À Kyoto, le ticket de bus coûte 230 yens et la ligne 5 relie la gare au pavillon d’Argent en 35 minutes ; '
           'on longe ensuite le chemin de la Philosophie sous les cerisiers, entre temples de bois et petits cafés.')


def topic():
    return {'slug':'kyoto-3-jours','destination':'Kyoto','country':'japon','continent':'asie','type':'itineraire',
            'question':'Comment passer trois jours à Kyoto en transports en commun ?','travelMonths':[3,4,10,11],'priority':80,
            'sources':[{'label':'Kyoto City Bus','url':'https://www2.city.kyoto.lg.jp/kotsu/webguide/en/'},{'label':'Kyoto Travel','url':'https://kyoto.travel/en/'}],
            'photos':[{'id':'lisbonne-tram-28'},{'id':'porto-nuit'},{'id':'sintra-regaleira'}]}


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,10,12,tzinfo=q.UTC)
        self.topic=topic()
        self.facts=[{'id':'c'+str(i),'fact':'Fait documenté '+str(i)} for i in range(1,6)]
        sections=[{'id':'partie-'+str(i),'title':'Partie '+str(i),'paragraphs':[PARAGRAPH,PARAGRAPH,PARAGRAPH],'claims':['c'+str(i)]} for i in range(1,5)]
        sections[-1]['claims']=['c4','c5']
        self.value={'title':'Kyoto en 3 jours : bus à 230 yens et temples','shortTitle':'Kyoto en 3 jours','description':'Trois jours à Kyoto en bus et à pied.',
                    'summary':'Le bus urbain coûte 230 yens et relie les temples.','keyFacts':[{'value':'230 ¥','label':'le trajet en bus urbain','claims':['c1']},
                    {'value':'35 min','label':'de la gare au pavillon d’Argent par la ligne 5','claims':['c2']},{'value':'3 jours','label':'pour voir l’essentiel de la ville','claims':['c3']}],
                    'sections':sections,'faq':[{'question':'Combien coûte le bus ?','answer':'230 yens le trajet.','claims':['c1']}]}

    def test_quota_hold_stops_before_credentials_sources_or_inference(self):
        hold={'status':'free_quota_hold','resumeAt':'2026-10-13T00:00:00Z'}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(g.os.environ,{'REPORT_DIR':tmp},clear=True), patch.object(g,'quota_hold',return_value=hold), patch.object(g.q,'load',side_effect=AssertionError('site read during hold')), patch.object(g,'source_fingerprint',side_effect=AssertionError('source fetch during hold')), patch.object(g,'call',side_effect=AssertionError('inference during hold')):
            self.assertEqual(g.main(),0)
            report=json.loads((Path(tmp)/'guide-report.json').read_text())
            self.assertEqual(report['status'],'free_quota_hold')
            self.assertEqual(report['callsAttempted'],0)
            self.assertEqual(report['sourceFetches'],0)
            self.assertFalse(report['publicationAttempted'])
    def test_full_calendar_stops_before_photos_sources_or_inference(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(g.os.environ,{'REPORT_DIR':tmp},clear=True), patch.object(g,'quota_hold',return_value=None), patch.object(g,'guide_release_at',return_value=None), patch.object(g.guide_photos,'prepare',side_effect=AssertionError('photo search on a full calendar')), patch.object(g,'source_fingerprint',side_effect=AssertionError('source fetch')), patch.object(g,'call',side_effect=AssertionError('inference')):
            self.assertEqual(g.main(),0)
            report=json.loads((Path(tmp)/'guide-report.json').read_text())
            self.assertEqual((report['status'],report['callsAttempted']),('calendar_full',0))
    def test_missing_photos_hold_the_guide_before_any_source_or_inference(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(g.os.environ,{'REPORT_DIR':tmp,'CLOUDFLARE_WORKERS_AI_TOKEN':'x'},clear=True), patch.object(g,'quota_hold',return_value=None), patch.object(g,'guide_release_at',return_value=self.now), patch.object(g.guide_photos,'prepare',side_effect=ValueError('guide_photos_insufficient')), patch.object(g,'source_fingerprint',side_effect=AssertionError('source fetch')), patch.object(g,'call',side_effect=AssertionError('inference')):
            self.assertEqual(g.main(),1)
            report=json.loads((Path(tmp)/'guide-report.json').read_text())
            self.assertEqual((report['reason'],report['callsAttempted']),('guide_photos_insufficient',0))
    def test_overlong_metadata_is_rejected_before_editorial_review(self):
        self.value['description']='x'*181
        with self.assertRaisesRegex(ValueError,'metadata_length'):
            g.validate_article_output(self.value,self.topic,self.facts,[],self.now)
    def test_valid_output_is_site_compatible(self):
        original=copy.deepcopy(self.value)
        article,citations=g.validate_article_output(self.value,self.topic,self.facts,[],self.now)
        q.validate_article(article,set())
        self.assertEqual(self.value,original)
        self.assertNotIn('claims',article['sections'][0])
        self.assertEqual(citations['partie-1'],['c1'])
        self.assertEqual(citations['keyfact-1'],['c2'])
        self.assertEqual(article['keyFacts'][0],{'value':'230 ¥','label':'le trajet en bus urbain'})
        self.assertEqual((article['country'],article['continent'],article['category']),('japon','asie','Itinéraires'))
    def test_key_figure_box_is_required_and_holds_a_number(self):
        for broken in ([],[{'value':'beaucoup','label':'de temples à voir','claims':['c1']}]*3,[{'value':'230 ¥','label':'le trajet en bus','claims':['inventé']}]*3):
            self.value['keyFacts']=broken
            with self.assertRaises(ValueError):g.validate_article_output(self.value,self.topic,self.facts,[],self.now)
    def test_tip_and_table_are_validated_and_reviewed_as_blocks(self):
        import guide_review
        self.value['sections'][0].update(tip='Prenez la ligne 5 avant 9 h : le trajet de 35 minutes reste fluide.',table={'headers':['Trajet','Prix'],'rows':[['Bus','230 ¥'],['Métro','220 ¥']]})
        article,citations=g.validate_article_output(self.value,self.topic,self.facts,[],self.now)
        ids={b['id'] for b in guide_review.public_blocks(article,citations,self.facts)}
        self.assertTrue({'keyfact-0','section-partie-1-tip','section-partie-1-table'}<=ids)
        self.value['sections'][0]['table']={'headers':['Trajet'],'rows':[['Bus']]}
        with self.assertRaisesRegex(ValueError,'guide_table'):g.validate_article_output(self.value,self.topic,self.facts,[],self.now)
    def test_unproved_section_is_rejected(self):
        self.value['sections'][0]['claims']=['invented']
        with self.assertRaisesRegex(ValueError,'unproved'):
            g.validate_article_output(self.value,self.topic,self.facts,[],self.now)
    def test_unproved_faq_is_rejected(self):
        self.value['faq'][0]['claims']=['invented']
        with self.assertRaisesRegex(ValueError,'faq_claims'):
            g.validate_article_output(self.value,self.topic,self.facts,[],self.now)
    def test_known_topic_is_not_regenerated(self):
        self.assertIsNone(g.select_topic([self.topic],[{'slug':self.topic['slug']}],self.now))
    def test_topic_url_with_credentials_or_query_is_rejected(self):
        self.topic['sources'][0]['url']='https://kyoto.travel/en/?utm=1'
        with self.assertRaisesRegex(ValueError,'outside_scope'):g.select_topic([self.topic],[],self.now)
    def test_insufficient_facts_never_calls_writer(self):
        def fail(*args):raise AssertionError('unexpected inference')
        with self.assertRaisesRegex(ValueError,'insufficient_facts'):
            g.create_guide(self.topic,self.facts[:2],[],self.now,'',fail)
    def test_critic_rejection_is_not_approval(self):
        answers=iter([(self.value,{}),({'supported':False,'issues':['Unsupported advice'],'checkedClaimIds':['c1','c2','c3','c4','c5']},{})])
        result=g.create_guide(self.topic,self.facts,[],self.now,'',lambda *args:next(answers))
        self.assertEqual(result['status'],'guide_held_by_review')
        self.assertFalse(result['publicationApproved'])
        self.assertFalse(g.revisable(result))
    def test_photos_become_cover_and_section_images_before_review(self):
        answers=iter([(self.value,{}),({'supported':True,'issues':[],'checkedClaimIds':['c1','c2','c3','c4','c5']},{})])
        seen=[]
        def reviewer(article,*args):seen.append(article);return {'supported':True},{}
        result=g.create_guide(self.topic,self.facts,[],self.now,'',lambda *args:next(answers),block_reviewer=reviewer,photo_ids=['porto-nuit','sintra-regaleira','lisbonne-tram-28'])
        article=result['article']
        self.assertEqual(article['cover'],'porto-nuit')
        self.assertEqual([s.get('image') for s in article['sections']],['sintra-regaleira','lisbonne-tram-28',None,None])
        self.assertIs(seen[0],article)

    def test_quote_identity_binds_source_and_exact_words(self):
        sources=[{'text':'First source sentence has useful details.'},{'text':'Second source sentence describes the collection.'}]
        catalog=g.quote_catalog(sources)
        result=g.bind_selected_quotes({'facts':[{'quoteId':'q2','fact':'La collection est décrite dans la source.','usefulness':'Décrire une visite documentée.'}]},catalog)
        self.assertEqual(result['facts'][0]['source'],1)
        self.assertEqual(result['facts'][0]['quote'],sources[1]['text'])

    def test_sentences_with_prices_and_durations_come_first(self):
        sources=[{'text':'A calm street lined with old wooden houses. The bus costs 230 yen per ride.'},{'text':'The garden is lovely in spring. The walk takes 35 minutes.'}]
        quotes=[row['quote'] for row in g.quote_catalog(sources)]
        self.assertEqual(quotes[:2],['The bus costs 230 yen per ride.','The walk takes 35 minutes.'])
        self.assertEqual(len(quotes),4)

    def test_invented_quote_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'unknown_or_duplicate_quote'):
            g.bind_selected_quotes({'facts':[{'quoteId':'q999','fact':'Inventé','usefulness':'Inventé'}]},[])

    def test_extended_fact_budget_keeps_all_exact_citations(self):
        from discover_facts import partition_facts
        sources=[{'text':' '.join('Sentence number '+str(i)+' contains a distinct verified fact.' for i in range(12))}]
        catalog=g.quote_catalog(sources)
        chosen={'facts':[{'quoteId':row['quoteId'],'fact':'Un fait documenté distinct.','usefulness':'Aide à préparer une visite.'} for row in catalog]}
        facts,rejected=partition_facts(g.bind_selected_quotes(chosen,catalog),sources,max_facts=12)
        self.assertEqual(len(facts),12);self.assertEqual(rejected,[])
        with self.assertRaisesRegex(ValueError,'fact_count'):
            partition_facts(g.bind_selected_quotes(chosen,catalog),sources)

    def test_short_body_gets_one_bounded_repair_then_review(self):
        short=copy.deepcopy(self.value)
        for section in short['sections']:
            section['paragraphs']=['Une description factuelle assez courte pour déclencher le contrôle du corps du guide.']
        answers=iter([(short,{}),(self.value,{}),({'supported':True,'issues':[],'checkedClaimIds':['c1','c2','c3','c4','c5']},{})])
        calls=[]
        def invoke(*args):calls.append(args);return next(answers)
        result=g.create_guide(self.topic,self.facts,[],self.now,'',invoke,block_reviewer=lambda *args:({'supported':True},{}))
        self.assertEqual(len(calls),3)
        self.assertEqual(result['status'],'guide_ready_for_pilot_review')
        self.assertFalse(result['publicationApproved'])

    def test_failed_length_repair_is_not_retried(self):
        short=copy.deepcopy(self.value)
        for section in short['sections']:
            section['paragraphs']=['Une description factuelle assez courte pour déclencher le contrôle du corps du guide.']
        calls=[]
        def invoke(*args):calls.append(args);return short,{}
        with self.assertRaisesRegex(ValueError,'guide_too_short'):
            g.create_guide(self.topic,self.facts,[],self.now,'',invoke)
        self.assertEqual(len(calls),2)

    def test_global_approval_cannot_override_failed_block_review(self):
        answers=iter([(self.value,{}),({'supported':True,'issues':[],'checkedClaimIds':['c1','c2','c3','c4','c5']},{})])
        result=g.create_guide(self.topic,self.facts,[],self.now,'',lambda *args:next(answers),block_reviewer=lambda *args:({'supported':False,'issues':[{'id':'description','issue':'Unsupported claim'}]},{}))
        self.assertTrue(result['review']['supported'])
        self.assertFalse(result['blockReview']['supported'])
        self.assertEqual(result['status'],'guide_held_by_review')
        self.assertFalse(result['publicationApproved'])
        self.assertTrue(g.revisable(result))

    def test_writer_instruction_follows_the_guide_type(self):
        self.assertIn('Quand partir',g.writer_instruction(dict(self.topic,type='quand-partir')))
        self.assertIn('par jours',g.writer_instruction(self.topic))
        self.assertIn('L’essentiel en chiffres',g.writer_instruction(self.topic))

    def test_meter_refuses_a_call_that_would_cross_the_neuron_budget(self):
        report={}
        meter=g.Meter(report,transport=lambda messages,max_tokens,token,model:({'ok':True},{'prompt_tokens':100000,'completion_tokens':10000}))
        meter([],1000,'x')
        self.assertEqual(report['callsAttempted'],1)
        self.assertGreater(report['neuronsUsed'],4000)
        with self.assertRaisesRegex(ValueError,'neuron_budget'):meter([],4000,'x')
        self.assertEqual(report['callsAttempted'],1)

    def test_unknown_topic_type_is_rejected(self):
        self.topic['type']='voyage-vecu'
        with self.assertRaisesRegex(ValueError,'guide_topic_type'):g.select_topic([self.topic],[],self.now)

    def test_topic_words_rank_first_and_wikis_never_give_prices(self):
        sources=[{'url':'https://fr.wikivoyage.org/wiki/Kyoto','text':'The museum opened in 1990. The bus to Arashiyama takes 40 minutes. A ticket costs 230 yens. Arashiyama has bamboo groves.'},
                 {'url':'https://www2.city.kyoto.lg.jp/kotsu/webguide/en/','text':'The one-day bus pass costs 700 yen.'}]
        quotes=[row['quote'] for row in g.quote_catalog(sources,['arashiyama','bus'])]
        self.assertEqual(quotes[:2],['The bus to Arashiyama takes 40 minutes.','The one-day bus pass costs 700 yen.'])
        self.assertNotIn('A ticket costs 230 yens.',quotes)
        self.assertEqual(quotes[-1],'Arashiyama has bamboo groves.')
