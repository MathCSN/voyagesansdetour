import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
import authorize_recovery as recovery
import select_render as selector
from test_adopt_run import remote

NOW=dt.datetime(2026,10,12,8,tzinfo=dt.timezone.utc)
class RecoveryTests(unittest.TestCase):
    def setup_root(self,root):
        identity='reel-article-test';folder=root/'reel-drafts'/identity;folder.mkdir(parents=True)
        data=json.dumps({'id':identity,'publicationApproved':False,'source':{'validUntil':'2026-11-11T00:00:00+00:00'}}).encode()
        (folder/'storyboard.json').write_bytes(data);(folder/'receipt.json').write_text(json.dumps({'storyboardSha256':selector.sha(data)}))
        voice=root/'voice';voice.mkdir();(voice/'storyboard.py').write_text('fixed');(voice/'compose.py').write_text('fixed')
        selector.reserve(root,selector.select(root,NOW),'123',NOW)
        return identity
    def reader(self,path,*args):
        if '/artifacts?' in path:return json.dumps({'total_count':0,'artifacts':[]}).encode()
        return json.dumps({**remote(),'conclusion':'failure'}).encode()
    def test_one_retry_preserves_original_and_then_stops(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);identity=self.setup_root(root)
            grant=recovery.authorize(root,identity,NOW,self.reader)
            plan=selector.select(root,NOW);self.assertEqual(plan['previousRunId'],'123')
            selector.reserve(root,plan,'456',NOW)
            record=json.loads((root/'voice-attempts'/f'{identity}.json').read_text())
            self.assertEqual(record['previousAttempts'][0]['runId'],'123')
            self.assertEqual(record['recoveryAuthorization'],grant)
            self.assertIsNone(selector.select(root,NOW)['selected'])
            with self.assertRaisesRegex(ValueError,'retry_limit'):recovery.authorize(root,identity,NOW,self.reader)
    def test_live_success_or_media_artifact_cannot_be_retried(self):
        for variant in ('in_progress','success','artifact','partial'):
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);identity=self.setup_root(root)
                def reader(path,*args):
                    if '/artifacts?' in path:
                        return json.dumps({'total_count':1,'artifacts':[] if variant=='partial' else [{'name':'vsd-storyboard-media'}]}).encode()
                    data={**remote(),'conclusion':'failure'}
                    if variant=='in_progress':data['status']='in_progress'
                    if variant=='success':data['conclusion']='success'
                    return json.dumps(data).encode()
                with self.assertRaises(ValueError):recovery.authorize(root,identity,NOW,reader)
                self.assertFalse((root/'voice-recoveries').exists())
    def test_renderer_change_after_grant_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);identity=self.setup_root(root);recovery.authorize(root,identity,NOW,self.reader)
            (root/'voice/compose.py').write_text('changed again')
            with self.assertRaisesRegex(ValueError,'recovery_conflict'):selector.select(root,NOW)

if __name__=='__main__':unittest.main()
