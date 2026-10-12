import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import auto_select as select

ROOT=Path(__file__).resolve().parent.parent
CANDIDATE=ROOT/'voice-revisions/clear-v1/reel-article-porto-3-jours-sans-voiture'
REPORT=ROOT/'voice-reviews/revisions/clear-v1/reel-article-porto-3-jours-sans-voiture.json'
NOW=dt.datetime(2026,10,12,10,tzinfo=dt.timezone.utc)
class SelectionTests(unittest.TestCase):
    def test_only_exact_text_or_equal_single_digit_is_admissible(self):
        self.assertEqual(select.equivalents('Porto !','porto.'),[])
        self.assertEqual(len(select.equivalents('3 jours','trois jours')),1)
        for a,b in [('3 jours','quatre jours'),('ne partez pas','partez'),('limiter','imiter'),('Porto','portons'),('fleuve','feuf'),('24 heures','24h')]:
            self.assertIsNone(select.equivalents(a,b))

    def test_stop_precedes_io(self):
        with patch.object(select.stock,'validate',side_effect=AssertionError('IO')):
            self.assertEqual(select.evaluate('/absent','/absent',select.stock.STOP)['status'],'period_ended')

    def test_wrong_model_and_changed_reference_rejected_before_network(self):
        for key,value,error in [('modelRevision','0'*40,'unqualified_report'),('expectedText','invented','expected_text_changed')]:
            data=json.loads(REPORT.read_text());data[key]=value
            with tempfile.TemporaryDirectory() as tmp:
                report=Path(tmp)/'report.json';report.write_text(json.dumps(data))
                draft=json.loads((CANDIDATE/'media/storyboard.json').read_text())
                html='<link rel="canonical" href="'+draft['targetUrl']+'">'+''.join('<p>'+e['text']+'</p>' for e in draft['narration']['excerpts'])
                with self.assertRaisesRegex(ValueError,error):
                    select.evaluate(CANDIDATE,report,NOW,fetcher=lambda u:html.encode())

    def test_forged_comparison_is_recomputed(self):
        data=json.loads(REPORT.read_text());data['voices'][0]['comparison']['differences']=[]
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'report.json';report.write_text(json.dumps(data))
            draft=json.loads((CANDIDATE/'media/storyboard.json').read_text())
            html='<link rel="canonical" href="'+draft['targetUrl']+'">'+''.join('<p>'+e['text']+'</p>' for e in draft['narration']['excerpts'])
            with self.assertRaisesRegex(ValueError,'comparison_changed'):
                select.evaluate(CANDIDATE,report,NOW,fetcher=lambda u:html.encode())

if __name__=='__main__':unittest.main()
