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

    def test_label_names_the_country_and_place_never_a_fixed_angle(self):
        (self.site/'destinations.json').write_text(json.dumps({'countries':{'japon':{'name':'Japon','in':'au Japon'}}}))
        self.assertEqual(place_label({'country':'japon','destination':'Kyoto'},self.site),'JAPON · KYOTO')
        self.assertEqual(place_label({'country':'espagne','destination':'Andalousie'},self.site),'ESPAGNE · ANDALOUSIE')
        self.assertEqual(place_label({'destination':'Portugal'},self.site),'PORTUGAL')
        self.assertNotIn('VOITURE',place_label(GUIDE,self.site))

if __name__=='__main__':unittest.main()
