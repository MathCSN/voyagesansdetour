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
        guide=dict(guide,keyFacts=[{'value':'40 min','label':'de train entre deux villes'},{'value':'19 €','label':'une entrée de monument'},{'value':'300 000 ₫','label':'un prix en dongs'}])
        manifests={v:json.loads((render(guide,self.output,site=self.site,variant=v)/'draft.json').read_text()) for v in ('a','b','c')}
        self.assertEqual([m['id'] for m in manifests.values()],['pin-andalousie','pin-andalousie-b','pin-andalousie-c'])
        self.assertEqual([m['photo']['id'] for m in manifests.values()],['grenade-alhambra','grenade-albaicin','seville-plaza'])
        self.assertEqual(len({m['imageSha256'] for m in manifests.values()}),3)
        self.assertEqual(manifests['a']['pinTitle'],GUIDE['title'])
        self.assertEqual(manifests['b']['pinTitle'],'L’Andalousie en train : itinéraire jour par jour, prix et conseils')
        self.assertEqual(manifests['c']['pinTitle'],'L’Andalousie en train : les chiffres à connaître avant de partir')
        self.assertTrue(all(len(m['pinTitle'])<=100 for m in manifests.values()))

    def test_a_figure_goes_on_a_pin_only_over_a_photo_of_the_place_it_names_and_is_never_cut_mid_sentence(self):
        from pin_draft import fact_fits_photo, fitted_label, font, FONTS
        from PIL import ImageDraw
        lagos={'id':'algarve-ponta-piedade','alt_fr':'Les falaises de la Ponta da Piedade, à Lagos.','source_page':'https://commons.wikimedia.org/wiki/File:Ponta_da_Piedade.jpg'}
        tavira={'id':'algarve-tavira','alt_fr':'Le pont romain de Tavira.','source_page':'https://commons.wikimedia.org/wiki/File:Tavira.jpg'}
        everywhere={'algarve','portugal'}
        fare={'value':'3,60 €','label':'Faro → Tavira en train régional, 33 minutes'}
        self.assertFalse(fact_fits_photo(fare,lagos,everywhere))   # review of 13/11/2026
        self.assertTrue(fact_fits_photo({'value':'8,30 €','label':'Faro → Lagos, 1 h 35'},lagos,everywhere))
        self.assertTrue(fact_fits_photo({'value':'1,60 €','label':'le billet le moins cher de la ligne'},tavira,everywhere))
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

if __name__=='__main__':unittest.main()
