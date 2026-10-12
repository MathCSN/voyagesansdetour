import copy
import datetime as dt
import unittest
import guide_draft as g
import editorial_queue as q

class GuideTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,10,12,tzinfo=q.UTC)
        self.topic={'slug':'aveiro-art-nouveau','destination':'Aveiro','question':'Que voir ?','sources':[{'label':'Musée','url':'https://museusdeaveiro.cm-aveiro.pt/museu-arte-nova/o-museu'},{'label':'Exposition','url':'https://museusdeaveiro.cm-aveiro.pt/museu-arte-nova/exposicao-permanente'}]}
        self.facts=[{'id':'c'+str(i),'fact':'Fait documenté '+str(i)} for i in range(1,5)]
        self.value={'title':'Le musée Art nouveau à Aveiro','shortTitle':'Art nouveau','description':'Préparer la visite du musée.','summary':'Comprendre la collection présentée par le musée.','sections':[{'id':'partie-'+str(i),'title':'Partie '+str(i),'paragraphs':['Ce paragraphe de test représente une description documentée de la collection du musée. Il sert uniquement à exercer la validation du format éditorial et de ses références, dans une donnée synthétique sans publication ni appel à une source distante.'],'claims':['c'+str(i)]} for i in range(1,5)],'faq':[{'question':'Que voir ?','answer':'La collection du musée.','claims':['c1']}]}
    def test_valid_output_is_site_compatible(self):
        original=copy.deepcopy(self.value)
        article,citations=g.validate_article_output(self.value,self.topic,self.facts,[],self.now)
        q.validate_article(article,set())
        self.assertEqual(self.value,original)
        self.assertNotIn('claims',article['sections'][0])
        self.assertEqual(citations['partie-1'],['c1'])
    def test_unproved_section_is_rejected(self):
        self.value['sections'][0]['claims']=['invented']
        with self.assertRaisesRegex(ValueError,'unproved'):
            g.validate_article_output(self.value,self.topic,self.facts,[],self.now)
    def test_unproved_faq_is_rejected(self):
        self.value['faq'][0]['claims']=['invented']
        with self.assertRaisesRegex(ValueError,'faq_claims'):
            g.validate_article_output(self.value,self.topic,self.facts,[],self.now)
    def test_known_topic_is_not_regenerated(self):
        self.assertIsNone(g.select_topic([self.topic],[{'slug':self.topic['slug']}]))
    def test_external_topic_url_is_rejected(self):
        self.topic['sources'][0]['url']='https://untrusted.example/source'
        with self.assertRaisesRegex(ValueError,'outside_scope'):g.select_topic([self.topic],[])
    def test_insufficient_facts_never_calls_writer(self):
        def fail(*args):raise AssertionError('unexpected inference')
        with self.assertRaisesRegex(ValueError,'insufficient_facts'):
            g.create_guide(self.topic,self.facts[:2],[],self.now,'',fail)
    def test_critic_rejection_is_not_approval(self):
        answers=iter([(self.value,{}),({'supported':False,'issues':['Unsupported advice'],'checkedClaimIds':['c1','c2','c3','c4']},{})])
        result=g.create_guide(self.topic,self.facts,[],self.now,'',lambda *args:next(answers))
        self.assertEqual(result['status'],'guide_held_by_review')
        self.assertFalse(result['publicationApproved'])
