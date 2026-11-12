import copy
import json
import unittest
from pathlib import Path
from update_draft import (create_update,digest,validate_additions,paragraph_defects,addition_defects,
                          new_figures,is_retired,retired_updates)

class UpdateDraftTests(unittest.TestCase):
    def setUp(self):
        self.article={'slug':'sintra','title':'Visiter Sintra','sections':[{'id':'billets','title':'Existant','paragraphs':['Conserver ce contenu.']}]}
        self.facts=[{'id':'c1','fact':'Le créneau est celui du palais.','source':0,'quote':'The time corresponds to entry in the Palace.'}]
        self.sections={'sections':[{'targetSectionId':'billets','title':'Comprendre le créneau','paragraph':'Le créneau de 9 h 30 indiqué sur le billet correspond à l’entrée au palais, et non à votre arrivée à l’entrée du parc.','claims':['c1']}]}
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


PATCHES=Path(__file__).resolve().parents[2]/'site-src'/'editorial-update-patches'
RETIRED_IDS=('auto-9ae6e3fad9f7224cb01ef3a3','auto-d23444808a9f02eea681bd67','auto-23704ea99841fc4e556c61f4')
CINQUE_TERRE_WITHOUT_BOSCO=('Le sentier n. 509 mène au santuario della Madonna di Soviore, à une altitude de 418 mètres, et permet de découvrir '
    'un merveilleux bosco et cipressi. Selon Italia.it, la Cinque Terre Card permet également de participer à des escursioni a tema '
    'naturalistico et letterario, entre avril et août, pour découvrir les lieux tels que Punta Mesco, La casa del Doganiere et Meriggiare pallido e assorto.')


def retired_patch(identity):
    return json.loads((PATCHES/(identity+'.json')).read_text(encoding='utf-8'))


class ParagraphDefectTests(unittest.TestCase):
    """The three automatic updates published in October and November 2026, the reviewer's cases, and clean French."""
    def test_the_copied_example_formula_is_refused(self):
        self.assertIn('update_boilerplate',paragraph_defects('Pour les consignes présentées par Italia.it, le sentier n. 509 mène au sanctuaire.'))
    def test_a_price_glued_to_the_euro_sign_is_refused(self):
        self.assertIn('update_glued_price',paragraph_defects('La dégustation coûte 10€ par personne.'))
    def test_untranslated_italian_portuguese_or_english_is_refused(self):
        for text in (CINQUE_TERRE_WITHOUT_BOSCO,
                     'Le sentier traverse un merveilleux bosco di lecci, puis la casa del guardiano.',
                     'Il sentiero porta al santuario in due ore e costa dieci euro.',
                     'The trail leads to the sanctuary in two hours and costs ten euros.',
                     'O comboio parte às sete e meia e chega ao Pinhão duas horas depois.',
                     'Le sentier 509 mène au santuario de Soviore en 1 h 40, à travers un bosco de chênes verts, et les escursioni guidées du parc coûtent 7,50 €.'):
            with self.subTest(text=text):self.assertIn('update_untranslated',paragraph_defects(text))
    def test_a_sentence_without_french_words_is_refused(self):
        self.assertIn('update_not_french',paragraph_defects('Sentiero panoramico, vista mozzafiato, costo dieci euro, durata due ore, partenza ogni mattina presto.'))
    def test_a_foreign_sentence_or_clause_inside_french_is_refused(self):
        # Reviewer's cases on PR 45: « La », « Il » or « Un » open Italian and Spanish sentences too,
        # and a foreign list after a colon is judged on its own.
        for text in ('La carte se prend en gare et coûte 19,50 € par jour en haute saison. La carta comprende treni regionali, autobus locali, sentieri costieri, bagni pubblici, connessione internet gratuita.',
                     'La carte se prend en gare et coûte 19,50 € par jour en haute saison. Il biglietto giornaliero costa diciannove euro e i bambini sotto i quattro anni viaggiano gratis.',
                     'Le billet coûte 697 pesos depuis mars. Un boleto único reemplaza ahora el doble pago federal y estatal en la taquilla del centro de visitantes.',
                     'Le musée ouvre à 10 h et coûte 12 €. Le panneau précise : free entry every first Sunday, guided tours daily, children under five go free.',
                     'O Paço dos Duques fica perto dos jardins dos condes, a 300 metros do castelo.',
                     'Le marché vend du fish and chips à 14,50 £, puis cheap and cheerful street food and drinks.'):
            with self.subTest(text=text):self.assertTrue(set(paragraph_defects(text))&{'update_untranslated','update_not_french'})
    def test_french_with_foreign_names_dishes_and_homographs_stays_allowed(self):
        for text in ('Après 3 km, on est las de monter : le bus 435 redescend pour 2 €.',
                     'Goûtez les spaghetti alle vongole du port, à 14 € l’assiette.',
                     'On y sert le bacalhau à brás à 9 € et la francesinha à 11 €.',
                     'Le jamón ibérico se vend 8 € les 100 g au Mercado de San Miguel ; l’açaí, 15 reais.',
                     'Depuis la Ponte da Arrábida, le bus 500 longe le Douro jusqu’à la Foz en 25 minutes.',
                     'Le Museu do Douro propose une dégustation à 10 € ; on y va depuis la rua do Choupelo.',
                     'Le Paço dos Duques domine le Largo da Oliveira, et l’Alcázar de Séville ouvre à 9 h 30.',
                     'Au Yucatán, la Ruta de los Cenotes relie Valladolid à Mérida ; le toucinho-do-céu coûte 2,40 €.',
                     'Le billet Top of the Rock coûte 49 $ ; le sapin se dresse entre les 49e et 50e Rues.',
                     'Via dell’Amore, miradouro da Graça, Madonna di Soviore et Tren Maya gardent leur nom.',
                     'Les bols de « bún chả » coûtent 50 000 dongs dans le Vieux Quartier.',
                     'Les places des Rockettes se réservent sur rockettes.com ou sur ticketmaster.com, à partir de 53 $ en semaine pour la séance de 11 h.',
                     'Les horaires d’hiver se vérifient sur nlg.it et sur trenitalia.it : le dernier train quitte Monterosso à 23 h 37 et coûte 5,20 €.',
                     'Avec un sac à dos, on monte sans peine au marché du Bolhão, où le bacalhau com natas se vend 9,80 € la part à emporter.',
                     'Un fish and chips se paie 14,50 £ au marché de Borough, et un bed and breakfast du quartier revient à 95 £ la nuit en décembre.',
                     'La patinoire ouvre chaque jour : lundi, mardi, mercredi, jeudi, vendredi 10 h, samedi, dimanche 9 h, dernière entrée 21 h 15, tarif enfant 11,50 £.',
                     'Le billet « Skip the Line to the Top of the Rock » coûte 71 $ et donne accès à la terrasse sans attendre, de 9 h à 23 h.'):
            with self.subTest(text=text):self.assertEqual(paragraph_defects(text),[])
    def test_known_limits_are_left_to_the_model_reviewer(self):
        # Two foreign dishes in one sentence look like the Cinque Terre paragraph and are held back;
        # a short foreign sentence carries too few words to judge. The prompt and the reviewer cover both.
        self.assertIn('update_untranslated',paragraph_defects('Sur le port de Cetara, les spaghetti alle vongole se paient 16,50 € l’assiette et la colatura di alici 9,50 € le flacon.'))
        self.assertEqual(paragraph_defects('Le train de 8 h 12 rejoint Vernazza en 4 minutes pour 5,20 €. Prossima fermata Vernazza. Descendez côté mer.'),[])
        # A Spanish sentence whose function words French shares (« se », « en », « la ») passes, as on main.
        self.assertEqual(paragraph_defects('Le billet coûte 697 pesos depuis mars. El boleto único cuesta 697 pesos y se paga en la taquilla del centro.'),[])
    def test_no_published_paragraph_is_refused(self):
        articles=json.loads((PATCHES.parent/'articles.json').read_text(encoding='utf-8'))
        flagged=[p for a in articles for s in a['sections'] for p in s.get('paragraphs',[]) if paragraph_defects(p)]
        self.assertEqual(flagged,[])


class AdditionDefectTests(unittest.TestCase):
    def setUp(self):
        self.article={'slug':'douro','title':'Douro','keyFacts':[{'value':'8 €','label':'le Museu do Douro'}],
                      'sections':[{'id':'regua','title':'Régua','paragraphs':['Entrée 8 €, ouvert de 10 h à 17 h 30.']}]}
    def test_a_paragraph_without_a_new_figure_is_refused(self):
        for text in ('Le musée offre une expérience plus calme et accessible aux visiteurs.',
                     'Au Museu do Douro, l’entrée coûte 8 € et le musée ouvre à 10 h.'):
            with self.subTest(text=text):self.assertEqual(addition_defects(text,[],self.article,[]),['update_no_new_figure'])
    def test_a_new_price_or_duration_is_accepted(self):
        text='Au Museu do Douro, la visite guidée coûte 14 € et dure 45 minutes.'
        self.assertEqual(new_figures(text,self.article),['14 €','45 minutes'])
        self.assertEqual(addition_defects(text,[],self.article,[]),[])
    def test_the_three_retired_paragraphs_never_come_back(self):
        retired=retired_updates()
        self.assertEqual({entry['patchId'] for entry in retired},set(RETIRED_IDS))
        for identity in RETIRED_IDS:
            patch=retired_patch(identity)
            with self.subTest(identity=identity):
                self.assertTrue(is_retired(patch['paragraph'],[],retired))
                facts=[f for f in patch['reviewEvidence']['proposal']['facts'] if f['id'] in patch['reviewEvidence']['proposal']['additions'][0]['claims']]
                self.assertTrue(is_retired('Un paragraphe entièrement récrit en français avec 12 € et 30 minutes.',facts,retired))
    def test_the_london_paragraph_is_refused_even_reworded(self):
        london=retired_patch('auto-23704ea99841fc4e556c61f4')
        self.assertIn('update_no_new_figure',addition_defects(london['paragraph'],[],self.article,[]))
        self.assertIn('update_retired',addition_defects(london['paragraph'].replace('désormais','maintenant'),
            [{'quote':'There’ll also be dedicated sessions for wheelchair users and reduced-capacity relaxed sessions'}],self.article))
    def test_a_defective_proposal_stops_before_the_critic(self):
        facts=[{'id':'c1','fact':'Visite à 12 euros.','source':0,'quote':'12 euros.'}]
        value={'sections':[{'targetSectionId':'regua','title':'Visites du musée','paragraph':'Pour les consignes présentées par le Museu do Douro, la visite guidée avec dégustation coûte 12 € par personne.','claims':['c1']}]}
        with self.assertRaisesRegex(ValueError,'update_boilerplate'):validate_additions(value,facts,self.article)
