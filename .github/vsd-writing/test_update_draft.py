import copy
import unittest
from update_draft import create_update,digest,validate_additions,paragraph_defects

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


class ParagraphDefectTests(unittest.TestCase):
    """The three automatic updates published in October and November 2026, and clean text."""
    def test_the_copied_example_formula_is_refused(self):
        self.assertIn('update_boilerplate',paragraph_defects('Pour les consignes présentées par Italia.it, le sentier n. 509 mène au sanctuaire.'))
    def test_untranslated_italian_or_portuguese_is_refused(self):
        for text in ('Le sentier traverse un merveilleux bosco di lecci et cipressi.','Le pack MD2 ajoute un cadeau de cálice MD pour 15,00 €.'):
            with self.subTest(text=text):self.assertIn('update_untranslated',paragraph_defects(text))
    def test_a_price_glued_to_the_euro_sign_is_refused(self):
        self.assertIn('update_glued_price',paragraph_defects('La dégustation coûte 10€ par personne.'))
    def test_proper_nouns_and_french_y_stay_allowed(self):
        for text in ('Le Museu do Douro propose une dégustation à 10 € ; on y va depuis la rua do Choupelo.',
                     'Le Paço dos Duques domine le Largo da Oliveira, et l’Alcázar de Séville ouvre à 9 h 30.',
                     'Au Yucatán, la Ruta de los Cenotes relie Valladolid à Mérida ; le toucinho-do-céu coûte 2,40 €.'):
            with self.subTest(text=text):self.assertEqual(paragraph_defects(text),[])
    def test_a_defective_proposal_stops_before_the_critic(self):
        article={'slug':'douro','title':'Douro','sections':[{'id':'regua','title':'Régua','paragraphs':['Conserver ce contenu.']}]}
        facts=[{'id':'c1','fact':'Visite à 10 euros.','source':0,'quote':'10 euros.'}]
        value={'sections':[{'targetSectionId':'regua','title':'Visites du musée','paragraph':'Pour les consignes présentées par le Museu do Douro, la visite guidée avec dégustation coûte 10 € par personne.','claims':['c1']}]}
        with self.assertRaisesRegex(ValueError,'update_boilerplate'):validate_additions(value,facts,article)

