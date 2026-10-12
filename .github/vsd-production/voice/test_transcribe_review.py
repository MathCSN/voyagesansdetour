import datetime as dt
import json
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import transcribe_review as review

FOLDER=Path(__file__).resolve().parent.parent/'voice-stock/reel-article-portugal-sans-voiture-bagages'
NOW=dt.datetime(2026,10,12,7,tzinfo=dt.timezone.utc)

class ReviewTests(unittest.TestCase):
    def test_no_io_after_stop(self):
        with patch('stock.validate',side_effect=AssertionError('io')):
            self.assertEqual(review.review('/absent','/absent',review.stock.STOP)['status'],'period_ended')

    def test_numbers_negation_names_are_not_normalized_away(self):
        for expected,actual in [('24 heures','48 heures'),('ne partez pas','partez'),('CP','SNCF')]:
            result=review.compare(expected,actual)
            self.assertFalse(result['exactNormalizedMatch']);self.assertTrue(result['differences'])
        self.assertTrue(review.compare('Un départ !','un départ.')['exactNormalizedMatch'])
        self.assertFalse(review.compare('Le guide','')['exactNormalizedMatch'])

    def test_expiry_before_transcription(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'expired_or_future_render'):
                review.review(FOLDER,Path(tmp)/'review.json',dt.datetime(2026,10,28,tzinfo=dt.timezone.utc),lambda p:self.fail('transcribe'))

    def test_review_never_approves_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'review.json';calls=[]
            def transcribe(path):
                calls.append(path)
                return [{'text':'Exemple incomplet','start':0,'end':1}]
            result=review.review(FOLDER,output,NOW,transcribe)
            self.assertEqual(len(calls),2);self.assertTrue(all(p.name=='reel.mp4' for p in calls))
            self.assertFalse(result['publicationApproved']);self.assertFalse(result['humanListeningPerformed'])
            self.assertTrue(all(v['comparison']['differences'] for v in result['voices']))
            before=output.read_bytes()
            with self.assertRaisesRegex(ValueError,'existing_review_preserved'):review.review(FOLDER,output,NOW,lambda p:self.fail('replay'))
            self.assertEqual(before,output.read_bytes())

    def test_transcription_failure_leaves_no_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'review.json'
            def fail(path):raise RuntimeError('model failed')
            with self.assertRaisesRegex(RuntimeError,'model failed'):review.review(FOLDER,output,NOW,fail)
            self.assertFalse(output.exists())

    def test_selector_skips_immutable_review_and_stops_on_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'stock';root.mkdir();shutil.copytree(FOLDER,root/FOLDER.name)
            out=Path(tmp)/'reports'
            report=out/(FOLDER.name+'.json')
            review.review(FOLDER,report,NOW,lambda p:[{'text':'Exemple','start':0,'end':1}])
            result=review.review_next(root,out,NOW,lambda p:self.fail('duplicate inference'))
            self.assertEqual(result['status'],'no_unreviewed_valid_stock')
            old=json.loads(report.read_text());old['stockSha256']='0'*64;report.write_text(json.dumps(old))
            with self.assertRaisesRegex(ValueError,'review_conflict'):
                review.review_next(root,out,NOW,lambda p:self.fail('inference'))

    def test_selector_skips_expired_stock_without_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'stock';root.mkdir();shutil.copytree(FOLDER,root/FOLDER.name)
            result=review.review_next(root,Path(tmp)/'reports',dt.datetime(2026,10,28,tzinfo=dt.timezone.utc),lambda p:self.fail('inference'))
            self.assertEqual(result['status'],'no_unreviewed_valid_stock')

class CatalogueTests(unittest.TestCase):
    def test_global_limit_and_separate_revision_report_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);families=root/'families';families.mkdir()
            for name in ['complete-sentences','second']:(families/name).mkdir()
            empty={'status':'no_unreviewed_valid_stock'};made={'status':'machine_transcription_requires_editorial_review'}
            with patch.object(review,'review_next',side_effect=[empty,made]) as select:
                self.assertEqual(review.review_catalogue(root/'original',families,root/'reports',NOW),made)
                self.assertEqual(select.call_count,2)
                self.assertEqual(select.call_args.args[1],root/'reports/revisions/complete-sentences')
            with patch.object(review,'review_next',return_value=made) as select:
                review.review_catalogue(root/'original',families,root/'reports',NOW)
                self.assertEqual(select.call_count,1)

    def test_conflict_is_not_skipped_and_stop_precedes_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(review,'review_next',side_effect=ValueError('review_conflict')) as select:
                with self.assertRaisesRegex(ValueError,'review_conflict'):
                    review.review_catalogue(tmp,Path(tmp)/'absent',tmp,NOW)
                self.assertEqual(select.call_count,1)
            with patch.object(review,'review_next',side_effect=AssertionError('io')):
                self.assertEqual(review.review_catalogue('/absent','/absent','/absent',review.stock.STOP)['status'],'period_ended')

    def test_revision_symlinks_are_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'escape').symlink_to(root,target_is_directory=True)
            with patch.object(review,'review_next',side_effect=AssertionError('io')):
                with self.assertRaisesRegex(ValueError,'revision_path'):
                    review.review_catalogue(root,root,root/'out',NOW)

if __name__=='__main__':unittest.main()
