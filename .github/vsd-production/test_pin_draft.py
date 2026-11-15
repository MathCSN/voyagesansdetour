import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from pin_draft import render,place_label

PHOTO={'id':'grenade-alhambra','file':'photos/grenade-alhambra.jpg','source_page':'https://commons.wikimedia.org/wiki/File:Alhambra.jpg',
       'author':'Jane Doe','license':'CC BY-SA 4.0','license_url':'https://creativecommons.org/licenses/by-sa/4.0/',
       'credit_fr':'Jane Doe / Wikimedia Commons — CC BY-SA 4.0.'}
GUIDE={'slug':'andalousie','title':'L’Andalousie en train : Séville, Cordoue et Grenade','shortTitle':'L’Andalousie en train',
       'country':'espagne','cover':'grenade-alhambra','keyFacts':[{'value':'40 min','label':'Séville → Cordoue en AVE'}]}

class PinDraftTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        self.site=root/'site';(self.site/'dist/assets/photos').mkdir(parents=True);self.output=root/'drafts'
        Image.new('RGB',(1600,1067),'#7a9cc6').save(self.site/'dist/assets/photos/grenade-alhambra.jpg')
        (self.site/'image-sources.json').write_text(json.dumps({'photos':[PHOTO]}))

    def test_guide_with_a_free_cover_photo_gets_a_photo_pin(self):
        folder=render(GUIDE,self.output,site=self.site)
        manifest=json.loads((folder/'draft.json').read_text())
        self.assertEqual(manifest['templateVersion'],2);self.assertTrue(manifest['externalPhotographs'])
        self.assertEqual(manifest['photo']['license'],'CC BY-SA 4.0');self.assertEqual(manifest['photo']['author'],'Jane Doe')
        self.assertIn('Jane Doe',(folder/'credits.txt').read_text())
        with Image.open(folder/'pin.jpg') as image:self.assertEqual(image.size,(1000,1500))

    def test_guide_without_cover_keeps_the_typographic_pin_with_its_key_fact(self):
        guide={k:v for k,v in GUIDE.items() if k!='cover'}
        manifest=json.loads((render(guide,self.output,site=self.site)/'draft.json').read_text())
        self.assertEqual(manifest['templateVersion'],1);self.assertFalse(manifest['externalPhotographs'])

    def test_cover_with_a_non_free_license_is_refused(self):
        (self.site/'image-sources.json').write_text(json.dumps({'photos':[dict(PHOTO,license='All rights reserved')]}))
        with self.assertRaisesRegex(ValueError,'photo_license'):render(GUIDE,self.output,site=self.site)

    def test_ai_generated_cover_is_never_drawn(self):
        for field, value in (("source_page", "https://commons.wikimedia.org/wiki/File:Alhambra_Stable_Diffusion.jpg"),
                             ("categories", "AI-generated images"), ("credit_fr", "Image Midjourney.")):
            with self.subTest(field=field):
                (self.site/'image-sources.json').write_text(json.dumps({'photos':[dict(PHOTO,**{field:value})]}))
                with self.assertRaisesRegex(ValueError,'photo_ai_generated'):render(GUIDE,self.output,site=self.site)

    def test_each_variant_takes_another_photo_of_the_guide_and_its_own_title(self):
        for name in ('grenade-albaicin','seville-plaza'):
            Image.new('RGB',(1600,1067),'#c69c7a').save(self.site/('dist/assets/photos/'+name+'.jpg'))
        photos=[PHOTO]+[dict(PHOTO,id=name,file='photos/'+name+'.jpg',author='Auteur '+name) for name in ('grenade-albaicin','seville-plaza')]
        (self.site/'image-sources.json').write_text(json.dumps({'photos':photos}))
        guide=dict(GUIDE,category='Itinéraires',sections=[{'image':'grenade-albaicin'},{'image':'grenade-alhambra'},{'image':'seville-plaza'}],
                   keyFacts=[{'value':'40 min','label':'Séville → Cordoue en AVE'},{'value':'19 €','label':'l’Alhambra'},{'value':'300 000 ₫','label':'un prix en dongs'}])
        # Review of 13/11/2026: the memo "b" carries three figures on one photo; "Séville → Cordoue" and "l’Alhambra" name
        # places the Albaicín photo is not of, so no memo is drawn on it.
        with self.assertRaisesRegex(ValueError,'not_enough_key_facts'):
            render(guide,self.output,site=self.site,variant='b')
        # Since the review of the Pins (15/11/2026) a figure that names nothing goes on the cover only, or on a photo of
        # what it measures; on the Albaicín, figures of the Albaicín.
        guide=dict(guide,keyFacts=[{'value':'40 min','label':'à pied dans l’Albaicín'},{'value':'19 €','label':'la nuit dans l’Albaicín'},{'value':'7','label':'miradors dans l’Albaicín'}])
        manifests={v:json.loads((render(guide,self.output,site=self.site,variant=v)/'draft.json').read_text()) for v in ('a','b','c')}
        self.assertEqual([m['id'] for m in manifests.values()],['pin-andalousie','pin-andalousie-b','pin-andalousie-c'])
        self.assertEqual([m['photo']['id'] for m in manifests.values()],['grenade-alhambra','grenade-albaicin','seville-plaza'])
        self.assertEqual(len({m['imageSha256'] for m in manifests.values()}),3)
        self.assertEqual(manifests['a']['pinTitle'],GUIDE['title'])
        # No day in the guide: no « jour par jour » (review of the Pins); « c » shows no figure, its title promises none.
        self.assertEqual(manifests['b']['pinTitle'],'L’Andalousie en train : itinéraire, prix et conseils')
        self.assertEqual(manifests['c']['pinTitle'],'L’Andalousie en train')   # a photo with no caption: the short title
        self.assertTrue(all(len(m['pinTitle'])<=100 for m in manifests.values()))

    def test_a_figure_goes_on_a_pin_only_over_a_photo_of_the_place_it_names_and_is_never_cut_mid_sentence(self):
        from pin_draft import fact_fits_photo, fitted_label, font, FONTS
        from PIL import ImageDraw
        lagos={'id':'algarve-ponta-piedade','alt_fr':'Les falaises de la Ponta da Piedade, à Lagos.','source_page':'https://commons.wikimedia.org/wiki/File:Ponta_da_Piedade.jpg'}
        tavira={'id':'algarve-tavira','alt_fr':'Le pont romain de Tavira.','source_page':'https://commons.wikimedia.org/wiki/File:Tavira.jpg'}
        everywhere={'algarve','portugal'}
        fare={'value':'3,60 €','label':'Faro → Tavira en train régional, 33 minutes'}
        self.assertFalse(fact_fits_photo(fare,lagos,everywhere))   # review of 13/11/2026
        # Since the review of PR 55 a Pin's photo shows every place its figure names: Faro is not on the cliffs of Lagos.
        self.assertFalse(fact_fits_photo({'value':'8,30 €','label':'Faro → Lagos, 1 h 35'},lagos,everywhere))
        self.assertTrue(fact_fits_photo({'value':'182','label':'marches jusqu’au pied des falaises de Lagos'},lagos,everywhere))
        # A figure that names nothing: on the guide's cover, or on a photo of what it measures (review of the Pins).
        self.assertTrue(fact_fits_photo({'value':'1,60 €','label':'le billet le moins cher de la ligne'},tavira,everywhere,cover=True))
        self.assertFalse(fact_fits_photo({'value':'1,60 €','label':'le billet le moins cher de la ligne'},tavira,everywhere))
        self.assertTrue(fact_fits_photo({'value':'2 €','label':'le pont romain à pied'},tavira,everywhere))
        from pin_draft import commons_title_of
        self.assertEqual(commons_title_of({'source_page':'https://commons.wikimedia.org/wiki/File:Castelo_de_S%C3%A3o_Jorge.jpg'}),'File:Castelo de São Jorge.jpg')
        draw=ImageDraw.Draw(Image.new('RGB',(10,10)))
        face=font(FONTS['regular'],34)
        cut=fitted_label(draw,'le budget serré pour 14 jours et 13 nuits (154 120 ¥), capsule ou dortoir, repas à 1 000 ¥, hors vol — estimation',face,860)
        self.assertFalse(cut.endswith((',','—','(','-')))
        self.assertEqual(cut,'le budget serré pour 14 jours et 13 nuits (154 120 ¥), capsule ou dortoir, repas à 1 000 ¥, hors vol')
        window='la fenêtre où Bangkok, Chiang Mai et la mer d’Andaman sont tous au sec (12 à 24 mm à Bangkok, 0 à 13 mm à Chiang Mai)'
        self.assertEqual(fitted_label(draw,window,face,860),'la fenêtre où Bangkok, Chiang Mai et la mer d’Andaman sont tous au sec')
        costa='par personne à deux pour 14 jours : navettes, bus, parcs et 13 nuits en chambre 1-2 étoiles, hors repas et vols'
        self.assertNotEqual(fitted_label(draw,costa,face,860),'par personne à deux pour 14 jours : navettes, bus')
        self.assertIsNone(fitted_label(draw,'le plafond quotidien du métro en zones 1-2 en sans contact pour un trajet en heure pleine, aux heures creuses seulement le week-end',face,860,most=1))

    def test_a_variant_without_a_photo_of_its_own_is_not_drawn(self):
        with self.assertRaisesRegex(ValueError,'no_distinct_photo'):render(GUIDE,self.output,site=self.site,variant='b')
        with self.assertRaisesRegex(ValueError,'no_distinct_photo'):render({k:v for k,v in GUIDE.items() if k!='cover'},self.output,site=self.site,variant='c')

    def test_search_title_follows_the_kind_of_guide(self):
        from pin_draft import pin_title
        self.assertEqual(pin_title({'title':'T','shortTitle':'Quand partir à Tenerife','category':'Choisir'},'b'),'Quand partir à Tenerife : la meilleure période, mois par mois')
        self.assertEqual(pin_title({'title':'T','shortTitle':'Budget Japon, 2 semaines','category':'Budget'},'b'),'Budget Japon, 2 semaines : combien ça coûte, poste par poste')
        self.assertEqual(pin_title({'title':'T','shortTitle':'Sintra','category':'Inconnue'},'b'),'Sintra : l’essentiel à savoir avant de partir')

    def test_label_names_the_country_and_place_never_a_fixed_angle(self):
        (self.site/'destinations.json').write_text(json.dumps({'countries':{'japon':{'name':'Japon','in':'au Japon'}}}))
        self.assertEqual(place_label({'country':'japon','destination':'Kyoto'},self.site),'JAPON · KYOTO')
        self.assertEqual(place_label({'country':'espagne','destination':'Andalousie'},self.site),'ESPAGNE · ANDALOUSIE')
        self.assertEqual(place_label({'destination':'Portugal'},self.site),'PORTUGAL')
        self.assertNotIn('VOITURE',place_label(GUIDE,self.site))


class PinReviewOfTheFifteenth(unittest.TestCase):
    """Review of the Pins and captions, 15/11/2026: one test per case."""

    def test_the_search_title_never_says_its_short_title_twice_nor_two_colons(self):
        from pin_draft import search_title, pin_title
        self.assertEqual(search_title({'shortTitle':'Laponie : le budget','title':'x','category':'Budget'}),'Laponie : le budget — combien ça coûte, poste par poste')
        self.assertEqual(search_title({'shortTitle':'Lisbonne ou Porto ?','title':'x','category':'Choisir'}),'Lisbonne ou Porto ? — comment choisir, chiffres à l’appui')
        self.assertEqual(search_title({'shortTitle':'Où dormir à Lisbonne','title':'x','category':'Quartiers'}),'Où dormir à Lisbonne : quartier par quartier')
        # « jour par jour » only for a guide told day by day.
        self.assertEqual(search_title({'shortTitle':'Guimarães en une journée','title':'x','category':'Itinéraires'}),'Guimarães en une journée : itinéraire, prix et conseils')
        days={'shortTitle':'Le Vietnam en 15 jours','title':'x','category':'Itinéraires','sections':[{'title':'Jours 1 à 3 — Hanoï'}]}
        self.assertEqual(search_title(days),'Le Vietnam en 15 jours : itinéraire jour par jour, prix et conseils')
        # « c » shows no figure: its title promises none.
        # Review of PR 55: « c » says what its photo shows, never « le guide pratique » nor a promise of figures.
        self.assertEqual(pin_title({'shortTitle':'Le Japon en 2 semaines','title':'x'},'c',{'alt_fr':'La pagode Chureito et le mont Fuji.'}),
                         'Le Japon en 2 semaines : la pagode Chureito et le mont Fuji')
        self.assertEqual(pin_title({'shortTitle':'Lisbonne ou Porto ?','title':'x'},'c',{'alt_fr':'Tower Bridge au-dessus de la Tamise.'}),
                         'Lisbonne ou Porto ? — Tower Bridge au-dessus de la Tamise')

    def test_a_line_never_begins_with_a_colon_and_a_figure_keeps_its_unit(self):
        from pin_draft import wrap, font, FONTS
        from PIL import ImageDraw
        draw, face = ImageDraw.Draw(Image.new('RGB',(10,10))), font(FONTS['serif'],72)
        for text in ('Le Japon en 2 semaines : le budget ; les prix','Lisbonne ou Porto ? comment choisir'):
            for width in range(520, 900, 40):
                self.assertFalse(any(line.lstrip()[:1] in ':;?' for line in wrap(draw,text,face,width)), (text, width))
        for width in range(260, 900, 30):
            lines = wrap(draw,'ouvert jusqu’à 22 h le samedi, départ à 9 h 51',font(FONTS['regular'],34),width)
            self.assertFalse(any(line.startswith(('h ','h\u00a0','51')) or line.endswith((' 22',' 9')) for line in lines), lines)

    def test_the_credit_keeps_no_space_inside_brackets_and_fits_the_pin(self):
        from pin_draft import credits, credit_line
        from PIL import ImageDraw
        photo={'author':'Daniel Lu ( User:dllu )','source_page':'https://commons.wikimedia.org/wiki/File:X.jpg','license':'CC BY-SA 4.0','license_url':'https://creativecommons.org/licenses/by-sa/4.0/'}
        self.assertIn('Daniel Lu (User:dllu)',credits(photo))
        image=Image.new('RGB',(1000,1500),'black');credit_line(ImageDraw.Draw(image),1440,{**photo,'author':'Un auteur au nom très long '*4})
        self.assertIsNone(image.crop((935,1400,1000,1500)).getbbox())   # nothing drawn past the right margin

    def test_a_journey_goes_over_its_means_of_transport_or_not_at_all(self):
        from pin_draft import fact_fits_photo
        cases=[({'value':'13–16 min','label':'entre deux métros en journée'},{'id':'porto-sao-bento','alt_fr':'Les panneaux d’azulejos bleus du hall de la gare de São Bento.'},{'porto','portugal'}),
               ({'value':'2 h 40','label':'Rome → Salerne en Italo'},{'id':'amalfi-ferry','alt_fr':'Un ferry dans le port d’Amalfi.'},{'amalfitaine','italie'}),
               ({'value':'2 h 58','label':'Lisbonne → Porto en Alfa Pendular'},{'id':'porto-rabelo','alt_fr':'Un bateau rabelo sur le Douro.'},{'portugal'}),
               ({'value':'100 à 160 dh','label':'le taxi au départ de l’aéroport selon la zone'},{'id':'marrakech-place-jemaa-el-fna','alt_fr':'La place Jemaa el-Fna.'},{'marrakech','maroc'}),
               ({'value':'200 dh','label':'le taxi de l’aéroport à la médina'},{'id':'marrakech-place-jemaa-el-fna','alt_fr':'La place Jemaa el-Fna.'},{'marrakech','maroc'}),
               ({'value':'12 h 35','label':'Bangkok → Chiang Mai par le train de nuit n° 9'},{'id':'thailande-wat-arun','alt_fr':'Le Wat Arun, à Bangkok.'},{'thailande'}),
               ({'value':'59 €','label':'la cabine privative du train de nuit Helsinki–Rovaniemi'},{'id':'laponie-village-pere-noel','alt_fr':'Le village du Père Noël, à Rovaniemi.'},{'laponie','finlande'})]
        for fact, photo, everywhere in cases:
            photo={**photo,'source_page':'https://commons.wikimedia.org/wiki/File:X.jpg'}
            self.assertFalse(fact_fits_photo(fact,photo,everywhere,cover=True),fact['label'])
        train={'id':'laponie-train-nuit-rovaniemi','alt_fr':'Le train de nuit à voitures-lits en gare de Rovaniemi.','source_page':'https://commons.wikimedia.org/wiki/File:Sleeper_train.jpg'}
        self.assertTrue(fact_fits_photo(cases[-1][0],train,{'laponie','finlande'}))

    def test_no_price_of_a_reindeer_ride_over_huskies(self):
        from pin_draft import fact_fits_photo
        huskies={'id':'laponie-huskies','alt_fr':'Un attelage de huskies sur une piste enneigée.','source_page':'https://commons.wikimedia.org/wiki/File:Dogs.jpg'}
        everywhere={'laponie','finlande'}
        self.assertFalse(fact_fits_photo({'value':'30 à 60 €','label':'une balade en traîneau à renne de 400 ou 800 m'},huskies,everywhere))
        self.assertFalse(fact_fits_photo({'value':'0 €','label':'rencontrer le Père Noël dans son bureau'},huskies,everywhere))
        self.assertTrue(fact_fits_photo({'value':'63 €','label':'la courte balade en huskies au village'},huskies,everywhere))

    def test_two_pins_never_share_a_picture_and_the_closed_lift_is_left_out(self):
        from pin_draft import taken_by_other_pins, LEFT_OUT
        import hashlib, pin_draft
        renderer=hashlib.sha256(Path(pin_draft.__file__).read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            for identity, variant, photo in (('pin-portugal-sans-voiture-bagages-c','c','lisbonne-alfama-tram'),('pin-ou-dormir-lisbonne-quartiers-b','b','lisbonne-x'),
                                             ('pin-porto-weekend-b','b','porto-ribeira')):
                (Path(temp)/identity).mkdir();(Path(temp)/identity/'draft.json').write_text(json.dumps({'id':identity,'variant':variant,'photo':{'id':photo},'rendererSha256':renderer}))
            self.assertEqual(taken_by_other_pins('ou-dormir-lisbonne-quartiers',temp),{'lisbonne-alfama-tram','porto-ribeira'})
            # A guide whose slug begins another one's ("porto", "porto-weekend") does not take that guide's photos.
            self.assertIn('porto-ribeira',taken_by_other_pins('porto',temp))
            self.assertNotIn('porto-ribeira',taken_by_other_pins('porto-weekend',temp))
        self.assertIn('lisbonne-santa-justa',LEFT_OUT)


class PinReviewOfPullRequest55(unittest.TestCase):
    """Review of PR 55 (15/11/2026)."""

    def test_a_figure_that_names_another_place_than_the_photo_is_refused(self):
        from pin_draft import fact_fits_photo
        porto={'id':'porto-rabelo','alt_fr':'Un bateau rabelo sur le Douro, face aux façades de la Ribeira, à Porto.','source_page':'https://commons.wikimedia.org/wiki/File:Rabelo.jpg'}
        everywhere={'portugal'}
        for value,label in (('41 km²','la commune de Porto, contre 100 km² pour Lisbonne'),('3 € / 4 €','la taxe touristique par nuit : Porto / Lisbonne'),
                            ('1,40 € / 1,72 €','le trajet en ville : Andante Z2 à Porto, zapping à Lisbonne')):
            self.assertFalse(fact_fits_photo({'value':value,'label':label},porto,everywhere,cover=True),label)
        self.assertFalse(fact_fits_photo({'value':'1,40 €','label':'le trajet en ville avec la carte Andante'},porto,everywhere,cover=True))
        self.assertTrue(fact_fits_photo({'value':'41 km²','label':'la commune de Porto'},porto,everywhere,cover=True))

    def test_a_walk_never_goes_over_a_vehicle(self):
        from pin_draft import fact_fits_photo
        import place_names
        tram={'id':'lisbonne-tram28','alt_fr':'Un tram jaune de la ligne 28 dans une rue de Lisbonne.','source_page':'https://commons.wikimedia.org/wiki/File:Tram.jpg'}
        alfama={'id':'lisbonne-alfama','alt_fr':'Les toits de l’Alfama, à Lisbonne.','source_page':'https://commons.wikimedia.org/wiki/File:Alfama.jpg'}
        walk={'value':'20 min','label':'à pied de la Baixa à l’Alfama, en montée'}
        self.assertEqual(place_names.wanted_ways(walk['label']),{'walk'})
        self.assertFalse(fact_fits_photo(walk,tram,{'portugal','lisbonne'},cover=True))
        self.assertTrue(fact_fits_photo(walk,alfama,{'portugal','lisbonne'},cover=True))
        self.assertFalse(place_names.strict_journey('20 min à pied de la Baixa à l’Alfama'))
        self.assertTrue(place_names.other_ride(place_names.vehicle('lisbonne-tram28',tram['alt_fr'],'File:Tram.jpg'),walk['label']))

if __name__=='__main__':unittest.main()
