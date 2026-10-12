import datetime as dt
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import select_catalogue as selection

ROOT=Path(__file__).resolve().parent.parent
ID='reel-article-porto-3-jours-sans-voiture'
NOW=dt.datetime(2026,10,12,12,tzinfo=dt.timezone.utc)
class CatalogueTests(unittest.TestCase):
    def fixture(self,root):
        folder=root/'voice-stock'/ID;shutil.copytree(ROOT/'voice-revisions/clear-v1'/ID,folder)
        (folder/'selection.json').unlink();(folder/'transcription.json').unlink()
        reports=root/'voice-reviews';reports.mkdir();report=reports/(ID+'.json')
        shutil.copyfile(ROOT/'voice-reviews/revisions/clear-v1'/(ID+'.json'),report)
        return folder,report
    def evaluator(self,folder,report,now,preferred):
        result=json.loads((ROOT/'voice-revisions/clear-v1'/ID/'selection.json').read_text())
        result['transcriptionSha256']=selection.stock.sha(report.read_bytes());return result
    def test_preserve_once_then_skip_without_re_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder,report=self.fixture(root)
            self.assertTrue(selection.run(root,NOW,self.evaluator)['changed'])
            before=(folder/'selection.json').read_bytes()
            self.assertFalse(selection.run(root,NOW,lambda *a,**k:self.fail('duplicate'))['changed'])
            self.assertEqual(before,(folder/'selection.json').read_bytes())
    def test_ambiguous_voice_does_not_create_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder,_=self.fixture(root)
            result=selection.run(root,NOW,lambda *a,**k:{'status':'held_transcription_ambiguities'})
            self.assertTrue(result['changed']);self.assertFalse((folder/'selection.json').exists())
            self.assertFalse(selection.run(root,NOW,lambda *a,**k:self.fail('unchanged hold repeated'))['changed'])
    def test_partial_transcript_recovery_requires_exact_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder,report=self.fixture(root)
            (folder/'transcription.json').write_bytes(report.read_bytes())
            self.assertTrue(selection.run(root,NOW,self.evaluator)['changed'])
            (folder/'transcription.json').write_text('changed')
            with self.assertRaisesRegex(ValueError,'existing_selection_conflict'):selection.run(root,NOW,self.evaluator)
    def test_different_partial_transcript_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder,_=self.fixture(root);(folder/'transcription.json').write_text('different')
            with self.assertRaisesRegex(ValueError,'existing_decision_conflict'):selection.run(root,NOW,self.evaluator)
            self.assertFalse((folder/'selection.json').exists())
    def test_stop_precedes_io(self):
        self.assertEqual(selection.run('/absent',selection.stock.STOP)['status'],'period_ended')

if __name__=='__main__':unittest.main()
