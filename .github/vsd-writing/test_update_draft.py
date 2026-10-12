import copy
import unittest
from update_draft import create_update,digest,validate_additions

class UpdateDraftTests(unittest.TestCase):
    def setUp(self):
        self.article={'slug':'sintra','title':'Visiter Sintra','sections':[{'id':'billets','title':'Existant','paragraphs':['Conserver ce contenu.']}]}
        self.facts=[{'id':'c1','fact':'Le créneau est celui du palais.','source':0,'quote':'The time corresponds to entry in the Palace.'}]
        self.sections={'sections':[{'targetSectionId':'billets','title':'Comprendre le créneau','paragraph':'Le créneau indiqué sur le billet correspond à l’entrée au palais, et non à votre arrivée à l’entrée du parc.','claims':['c1']}]}
    def test_no_new_facts_never_calls_provider(self):
        def fail(*args):raise AssertionError('unexpected inference')
        self.assertEqual(create_update(self.article,[],'',fail)['status'],'no_update')
    def test_proposal_binds_base_without_modifying_it(self):
        original=copy.deepcopy(self.article);responses=iter([(self.sections,{}),({'supported':True,'issues':[],'checkedClaimIds':['c1']},{})])
        out=create_update(self.article,self.facts,'',lambda *a:next(responses))
        self.assertEqual(self.article,original)
        self.assertEqual(out['baseArticleSha256'],digest(original))
        self.assertFalse(out['publicationApproved'])
    def test_critic_rejection_stays_held(self):
        responses=iter([(self.sections,{}),({'supported':False,'issues':['Portée non démontrée'],'checkedClaimIds':['c1']},{})])
        self.assertEqual(create_update(self.article,self.facts,'',lambda *a:next(responses))['status'],'update_held_by_review')
    def test_unknown_citation_stops_before_critic(self):
        self.sections['sections'][0]['claims']=['invented']
        calls=[]
        def respond(*args):calls.append(1);return self.sections,{}
        with self.assertRaisesRegex(ValueError,'update_unproved_or_redundant'):create_update(self.article,self.facts,'',respond)
        self.assertEqual(len(calls),1)

    def test_missing_target_stops_before_critic(self):
        self.sections['sections'][0]['targetSectionId']='unknown'
        calls=[]
        def respond(*args):calls.append(args);return self.sections,{}
        with self.assertRaisesRegex(ValueError,'update_target_section'):
            create_update(self.article,self.facts,'',respond)
        self.assertEqual(len(calls),1)

    def test_existing_paragraph_is_rejected(self):
        self.article['sections'][0]['paragraphs'].append(self.sections['sections'][0]['paragraph'])
        with self.assertRaisesRegex(ValueError,'update_existing_paragraph'):
            create_update(self.article,self.facts,'',lambda *a:(self.sections,{}))

    def test_critic_receives_existing_guide_and_placement(self):
        import json
        calls=[]
        responses=iter([(self.sections,{}),({'supported':True,'issues':[],'checkedClaimIds':['c1']},{})])
        def respond(*args):calls.append(args);return next(responses)
        create_update(self.article,self.facts,'',respond)
        packet=json.loads(calls[1][0][1]['content'])
        self.assertEqual(packet['existingGuide'],self.article)
        self.assertEqual(packet['draft']['sections'][0]['targetSectionId'],'billets')
