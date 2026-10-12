import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import storyboard

NOW=dt.datetime(2026,10,12,tzinfo=dt.timezone.utc)
FOLDER=storyboard.pilot.HERE.parent/'reel-drafts/reel-article-portugal-sans-voiture-bagages'

class StoryboardTests(unittest.TestCase):
    def test_annual_stop_before_io(self):
        with patch('storyboard.prepare',side_effect=AssertionError('io')):
            self.assertEqual(storyboard.run('/missing','/missing',storyboard.pilot.STOP)['generated'],0)

    def test_modified_storyboard_is_rejected_before_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/FOLDER.name;folder.mkdir()
            for name in ('receipt.json','storyboard.json'):(folder/name).write_bytes((FOLDER/name).read_bytes())
            (folder/'storyboard.json').write_text((folder/'storyboard.json').read_text()+' ')
            with self.assertRaisesRegex(ValueError,'storyboard_changed'):
                storyboard.prepare(folder,NOW,lambda u:self.fail('network'))

    def test_expiration_precedes_network(self):
        with self.assertRaisesRegex(ValueError,'source_review_expired'):
            storyboard.prepare(FOLDER,dt.datetime(2026,10,28,tzinfo=dt.timezone.utc),lambda u:self.fail('network'))

    def test_exact_text_and_readable_chunks(self):
        draft=json.loads((FOLDER/'storyboard.json').read_text())
        from html import escape
        html='<link rel="canonical" href="'+draft['targetUrl']+'">'+''.join('<p>'+escape(e['text'])+'</p>' for e in draft['narration']['excerpts'])
        data,chunks,headings,badges,_,_=storyboard.prepare(FOLDER,NOW,lambda u:html.encode())
        self.assertTrue(all(len(c)<=70 for c in chunks))
        self.assertEqual(len(chunks),len(headings));self.assertEqual(len(chunks),len(badges))
        self.assertEqual(' '.join(chunks),' '.join([draft['narration']['hook']]+[e['text'] for e in draft['narration']['excerpts']]+[draft['narration']['closing']]))

    def test_sentence_flow_preserves_full_source_sentences_and_readable_captions(self):
        from html import escape
        from PIL import Image,ImageDraw,ImageFont
        draft=json.loads((FOLDER/'storyboard.json').read_text())
        narration=draft['narration']
        html='<link rel="canonical" href="'+draft['targetUrl']+'">'+''.join('<p>'+escape(e['text'])+'</p>' for e in narration['excerpts'])
        _,sentences,headings,badges,_,_=storyboard.prepare(FOLDER,NOW,lambda u:html.encode(),sentence_flow=True)
        self.assertEqual(len(sentences),6)
        self.assertIn('Un petit sac de journée pliable évite aussi d’emporter toutes vos affaires à chaque promenade.',sentences)
        self.assertEqual(' '.join(sentences),' '.join([narration['hook']]+[e['text'] for e in narration['excerpts']]+[narration['closing']]))
        font=ImageFont.truetype(str(storyboard.pilot.HERE.parent/'assets/dmsans-bold.ttf'),45)
        draw=ImageDraw.Draw(Image.new('RGB',(1080,1920)))
        for sentence in sentences:self.assertLessEqual(len(storyboard.compose.wrap(draw,sentence,font,820)),3)
        self.assertEqual(len(headings),6);self.assertEqual(len(badges),6)

    def test_new_topic_uses_exact_source_headings_and_fits_real_scene(self):
        from html import escape
        from PIL import ImageFont
        folder=FOLDER.parent/'reel-article-lisbonne-porto-train'
        draft=json.loads((folder/'storyboard.json').read_text())
        html='<link rel="canonical" href="'+draft['targetUrl']+'">'+''.join('<p>'+escape(e['text'])+'</p>' for e in draft['narration']['excerpts'])
        _,sentences,headings,badges,_,_=storyboard.prepare(folder,NOW,lambda u:html.encode(),sentence_flow=True)
        self.assertEqual(' '.join(headings[0]),'Lisbonne–Porto en train')
        self.assertIn('Alfa Pendular ou Intercidades ?', [' '.join(h) for h in headings])
        self.assertFalse(any('BAGAGES' in b for b in badges))
        assets=storyboard.pilot.HERE.parent/'assets'
        fonts={n:ImageFont.truetype(str(assets/file),size) for n,file,size in [('title','playfair.ttf',85),('caption','dmsans-bold.ttf',45),('small','dmsans-bold.ttf',29),('tiny','dmsans-regular.ttf',23)]}
        for i,sentence in enumerate(sentences):
            self.assertLessEqual(len(headings[i]),3)
            self.assertEqual(storyboard.compose.scene(i,0,fonts,sentence,headings,badges).size,(1080,1920))
        self.assertEqual(' '.join(sentences),' '.join([draft['narration']['hook']]+[e['text'] for e in draft['narration']['excerpts']]+[draft['narration']['closing']]))

    def test_porto_full_sentences_fit_without_text_changes(self):
        from html import escape
        from PIL import Image,ImageDraw,ImageFont
        folder=FOLDER.parent/'reel-article-porto-3-jours-sans-voiture'
        draft=json.loads((folder/'storyboard.json').read_text())
        html='<link rel="canonical" href="'+draft['targetUrl']+'">'+''.join('<p>'+escape(e['text'])+'</p>' for e in draft['narration']['excerpts'])
        _,sentences,_,_,_,_=storyboard.prepare(folder,NOW,lambda u:html.encode(),sentence_flow=True)
        draw=ImageDraw.Draw(Image.new('RGB',(1080,1920)))
        font=ImageFont.truetype(str(storyboard.pilot.HERE.parent/'assets/dmsans-bold.ttf'),45)
        sizes=[]
        for text in sentences:
            selected,lines=storyboard.compose.caption_layout(draw,text,font)
            self.assertGreaterEqual(selected.size,38);self.assertLessEqual(len(lines),3)
            self.assertEqual(' '.join(lines),text);sizes.append(selected.size)
        self.assertTrue(any(size<45 for size in sizes))
        with self.assertRaisesRegex(ValueError,'subtitle_line_overflow'):
            storyboard.compose.caption_layout(draw,'Une phrase beaucoup trop longue. '*30,font)

if __name__=='__main__':unittest.main()
