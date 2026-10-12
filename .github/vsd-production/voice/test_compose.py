import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import compose


class TimingTests(unittest.TestCase):
    def sample(self):
        segments=[];cursor=0
        for text in compose.SENTENCES:
            segments.append({'text':text,'sampleRate':22050,'startSample':cursor,'endSample':cursor+22050})
            cursor+=22050+4410
        return {'segments':segments,'durationSeconds':(cursor-4410)/22050}

    def test_sentence_cues_cover_exact_audio(self):
        self.assertEqual(len(compose.validate_timing(self.sample())),4)
        self.assertEqual(compose.timecode(26460),'00:00:01,200')

    def test_shifted_or_rewritten_subtitle_rejected(self):
        for key,value in [('startSample',0),('text','Texte non prononcé')]:
            sample=copy.deepcopy(self.sample());sample['segments'][1][key]=value
            with self.assertRaises(ValueError):compose.validate_timing(sample)

    def test_audio_length_mismatch_rejected(self):
        sample=self.sample();sample['durationSeconds']+=1
        with self.assertRaisesRegex(ValueError,'cover_audio'):compose.validate_timing(sample)

    def test_french_question_mark_stays_with_word(self):
        class Draw:
            def textlength(self, value, font):return len(value)
        self.assertEqual(compose.wrap(Draw(),'Bonjour Portugal ?',None,13),['Bonjour','Portugal ?'])

    def test_period_end_precedes_file_reads(self):
        with patch('compose.load_json',side_effect=AssertionError('read')):
            self.assertEqual(compose.compose(Path('/missing'),Path('/missing-output'),compose.STOP)['generated'],0)

if __name__=='__main__':unittest.main()
