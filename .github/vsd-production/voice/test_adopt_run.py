import datetime as dt
import io
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
import zipfile
import adopt_run as a

NOW=dt.datetime(2026,10,12,8,tzinfo=dt.timezone.utc)
FIXTURE=Path(__file__).resolve().parent.parent/'voice-stock/reel-article-lisbonne-porto-train'
def remote():return {'id':123,'repository':{'full_name':a.REPO,'private':False},'head_repository':{'full_name':a.REPO},'head_branch':'main','path':a.WORKFLOW,'event':'schedule','run_attempt':1,'status':'completed','conclusion':'success','head_sha':'a'*40,'html_url':f'https://github.com/{a.REPO}/actions/runs/123'}
class AdoptionTests(unittest.TestCase):
    def test_wrong_origin_retry_failure_and_workflow_are_rejected(self):
        for key,value in [('head_branch','other'),('run_attempt',2),('conclusion','failure'),('path','other.yml'),('event','pull_request')]:
            r=remote();r[key]=value
            with self.assertRaisesRegex(ValueError,'untrusted'):a.qualify_run(r,'123')
        r=remote();r['head_repository']={'full_name':'other/repo'}
        with self.assertRaises(ValueError):a.qualify_run(r,'123')
    def test_stop_and_empty_run_do_not_download(self):
        self.assertEqual(a.run('/missing','123',a.stock.STOP,lambda *x:self.fail('read'))['status'],'period_ended')
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def reader(path,*args):calls.append(path);return json.dumps(remote()).encode()
            self.assertEqual(a.run(tmp,'123',NOW,reader)['status'],'no_reserved_render');self.assertEqual(len(calls),1)
    def test_unsafe_archive_paths_and_links(self):
        for name,mode in [('../escape',0),('/absolute',0),('link',stat.S_IFLNK|0o777)]:
            raw=io.BytesIO()
            with zipfile.ZipFile(raw,'w') as z:
                entry=zipfile.ZipInfo(name);entry.external_attr=mode<<16;z.writestr(entry,'outside')
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(ValueError,'archive_path'):a.unpack(raw.getvalue(),tmp)
                self.assertFalse(list(Path(tmp).iterdir()))
    def test_verified_artifact_is_preserved_once_and_tamper_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);identity=FIXTURE.name;draft=root/'reel-drafts'/identity;draft.mkdir(parents=True)
            shutil.copyfile(FIXTURE/'media/storyboard.json',draft/'storyboard.json')
            receipt=json.loads((FIXTURE/'media/receipt.json').read_text())
            attempts=root/'voice-attempts';attempts.mkdir()
            attempt={'id':identity,'status':'reserved_before_render','runId':'123','publicationApproved':False,'storyboardSha256':receipt['storyboardSha256'],'validUntil':receipt['validUntil']}
            (attempts/f'{identity}.json').write_text(json.dumps(attempt))
            raw=io.BytesIO()
            with zipfile.ZipFile(raw,'w') as z:
                for p in (FIXTURE/'media').rglob('*'):
                    if p.is_file():z.write(p,str(p.relative_to(FIXTURE/'media')))
            def reader(path,*args):
                if path.endswith('/zip'):return raw.getvalue()
                if '/artifacts?' in path:return json.dumps({'total_count':1,'artifacts':[{'id':7,'name':'vsd-storyboard-media','expired':False,'size_in_bytes':len(raw.getvalue())}]}).encode()
                return json.dumps(remote()).encode()
            self.assertTrue(a.run(root,'123',NOW,reader)['changed'])
            manifest=root/'voice-stock'/identity/'stock.json';before=manifest.read_bytes()
            self.assertFalse(a.run(root,'123',NOW,reader)['changed']);self.assertEqual(before,manifest.read_bytes())
            (draft/'storyboard.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'source_changed'):a.run(root,'123',NOW,reader)

if __name__=='__main__':unittest.main()
