import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
import select_render as s

NOW=dt.datetime(2026,10,12,tzinfo=dt.timezone.utc)
class SelectionTests(unittest.TestCase):
    def fixture(self,root,name='one',expiry='2026-11-01T00:00:00Z'):
        identity='reel-article-'+name;p=root/'reel-drafts'/identity;p.mkdir(parents=True)
        raw=json.dumps({'id':identity,'publicationApproved':False,'source':{'validUntil':expiry}}).encode()
        (p/'storyboard.json').write_bytes(raw);(p/'receipt.json').write_text(json.dumps({'storyboardSha256':s.sha(raw)}))
        return identity,s.sha(raw)
    def test_reservation_prevents_retry_and_preserves_identity(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);identity,digest=self.fixture(root);self.fixture(root,'two')
            plan=s.select(root,NOW);self.assertEqual(plan['selected'],identity)
            s.reserve(root,plan,'123',NOW)
            self.assertEqual(s.select(root,NOW)['selected'],'reel-article-two')
            with self.assertRaisesRegex(ValueError,'selection_changed'):s.reserve(root,plan,'124',NOW)
            self.assertEqual(json.loads((root/'voice-attempts'/f'{identity}.json').read_text())['runId'],'123')
    def test_existing_stock_is_skipped_but_changed_source_conflicts(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);identity,digest=self.fixture(root)
            folder=root/'voice-stock'/identity;(folder/'media').mkdir(parents=True)
            (folder/'stock.json').write_text(json.dumps({'id':identity}))
            receipt=folder/'media/receipt.json';receipt.write_text(json.dumps({'id':identity,'storyboardSha256':digest}))
            self.assertIsNone(s.select(root,NOW)['selected'])
            receipt.write_text(json.dumps({'id':identity,'storyboardSha256':'0'*64}))
            with self.assertRaisesRegex(ValueError,'source_conflict'):s.select(root,NOW)
    def test_expiry_and_stop_and_symlink(self):
        self.assertEqual(s.select('/missing',s.STOP)['status'],'period_ended')
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.fixture(root,expiry='2026-10-01T00:00:00Z')
            self.assertIsNone(s.select(root,NOW)['selected'])
            (root/'voice-attempts').symlink_to(root,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'symlink'):s.select(root,NOW)

if __name__=='__main__':unittest.main()
