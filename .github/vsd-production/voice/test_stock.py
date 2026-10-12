import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import stock

class StockTests(unittest.TestCase):
    def test_stop_before_io(self):
        with patch('stock.inventory',side_effect=AssertionError('io')):
            self.assertFalse(stock.adopt('/missing','/missing',{},stock.STOP)['changed'])

    def test_link_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'escape').symlink_to('/etc/hosts')
            with self.assertRaisesRegex(ValueError,'symlink'):stock.inventory(root)

    def test_preserve_repeat_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();identity='reel-article-example'
            draft={'id':identity,'publicationApproved':False,'source':{'validUntil':'2026-10-27T00:00:00+00:00'}}
            (source/'storyboard.json').write_text(json.dumps(draft));(source/'media.txt').write_text('verified media')
            receipt={'id':identity,'status':'storyboard_media_requires_review','publicationAttempted':False,'paidInferenceCalls':0,'startedAt':'2026-10-12T00:00:00+00:00','finishedAt':'2026-10-12T00:01:00+00:00','validUntil':draft['source']['validUntil'],'storyboardSha256':stock.sha((source/'storyboard.json').read_bytes()),'files':[{'file':'media.txt','sha256':stock.sha((source/'media.txt').read_bytes())}]}
            (source/'receipt.json').write_text(json.dumps(receipt))
            cloud={'repository':'MathCSN/voyagesansdetour','artifactName':'vsd-storyboard-media','run':{'status':'completed','conclusion':'success','headBranch':'main','headSha':'a'*40,'databaseId':1,'url':'https://github.com/MathCSN/voyagesansdetour/actions/runs/1'},'receiptSha256':stock.sha((source/'receipt.json').read_bytes())}
            now=dt.datetime(2026,10,12,1,tzinfo=dt.timezone.utc);out=root/identity
            self.assertTrue(stock.adopt(source,out,cloud,now)['changed']);before=(out/'stock.json').read_bytes()
            self.assertFalse(stock.adopt(source,out,cloud,now)['changed']);self.assertEqual(before,(out/'stock.json').read_bytes())
            (out/'media/media.txt').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'conflict'):stock.adopt(source,out,cloud,now)
            self.assertEqual(before,(out/'stock.json').read_bytes())

if __name__=='__main__':unittest.main()
