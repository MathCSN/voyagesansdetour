import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import admit_guide as a
import test_guide_admission

class CalendarTests(unittest.TestCase):
    def setUp(self):
        fixture=test_guide_admission.AdmissionTests();fixture.setUp()
        self.proposal=fixture.proposal;self.now=fixture.now;self.fetch=fixture.fetch
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'out';self.out.mkdir()
        self.articles=[{'slug':'existing','publishedOn':'2026-09-01'}]
        self.queue={'schemaVersion':1,'drafts':[],'promotions':[]}
        self.save()
    def save(self):
        for name,data in [('articles.json',self.articles),('editorial-queue.json',self.queue),('editorial-updates.json',{'schemaVersion':1,'updates':[]})]:
            (self.root/name).write_text(json.dumps(data))
        (self.out/'guide-proposal.json').write_text(json.dumps(self.proposal))
    def run_admit(self):return a.run(self.out,self.root,self.now,self.fetch)
    def test_admission_preserves_evidence_and_replay_is_noop(self):
        self.assertTrue(self.run_admit()['changed'])
        state=json.loads((self.root/'editorial-queue.json').read_text())
        a.q.validate(self.articles,state,self.now)
        self.assertEqual(len(state['drafts']),1)
        evidence=json.loads(next((self.root/'editorial-guide-evidence').glob('*.json')).read_text())
        self.assertEqual(evidence['draftSha256'],a.q.digest(state['drafts'][0]))
        self.assertFalse(self.run_admit()['changed'])
        self.assertEqual(self.articles,json.loads((self.root/'articles.json').read_text()))
    def test_recent_publication_prevents_source_fetch_and_mutation(self):
        self.articles[0]['publishedOn']='2026-10-12';self.save()
        self.assertEqual(self.run_admit()['status'],'cadence_or_pending_hold')
        self.fetch.assert_not_called()
        self.assertEqual(json.loads((self.root/'editorial-queue.json').read_text()),self.queue)
    def test_guide_written_the_day_before_waits_for_its_two_day_slot(self):
        self.articles[0]['publishedOn']='2026-10-11';self.save()
        result=self.run_admit()
        self.assertTrue(result['changed'])
        self.assertEqual(result['releaseAt'],'2026-10-12T22:00:00Z')
        self.assertFalse(a.q.promote(self.root,self.now,source_fetcher=self.fetch))
        self.assertTrue(a.q.promote(self.root,a.q.instant('2026-10-13T05:41:00Z'),source_fetcher=self.fetch))
    def test_second_guide_waits_until_the_reserved_one_is_published(self):
        self.assertTrue(self.run_admit()['changed'])
        other=copy.deepcopy(self.proposal);other['article']['slug']='autre-guide'
        (self.out/'guide-proposal.json').write_text(json.dumps(other))
        self.assertEqual(self.run_admit()['status'],'cadence_or_pending_hold')
    def test_changed_source_does_not_enqueue(self):
        self.fetch.return_value={'sha256':'b'*64,'text':'Changed'}
        with self.assertRaises(ValueError):self.run_admit()
        self.assertFalse((self.root/'editorial-guide-evidence').exists())
    def test_missing_or_held_proposal_is_noop(self):
        self.proposal['status']='guide_held_by_review';self.save()
        self.assertEqual(self.run_admit()['status'],'review_held')
        (self.out/'guide-proposal.json').unlink()
        self.assertEqual(self.run_admit()['status'],'no_proposal')
        self.fetch.assert_not_called()
    def test_interrupted_evidence_cannot_be_overwritten(self):
        target=self.root/'editorial-guide-evidence';target.mkdir()
        file=target/('generated-'+self.proposal['article']['slug']+'.json');file.write_text('{}')
        with self.assertRaises(ValueError):self.run_admit()
        self.assertEqual(file.read_text(),'{}')
        self.assertEqual(json.loads((self.root/'editorial-queue.json').read_text()),self.queue)

    def test_admitted_guide_promotes_only_after_fresh_source_match(self):
        self.run_admit()
        self.fetch.reset_mock()
        self.assertTrue(a.q.promote(self.root,self.now,source_fetcher=self.fetch))
        self.assertEqual(self.fetch.call_count,2)
        state=json.loads((self.root/'editorial-queue.json').read_text())
        self.assertEqual(len(state['promotions']),1)
        self.assertIsNone(state['promotions'][0]['receipt'])
        self.assertFalse(a.q.promote(self.root,self.now,source_fetcher=self.fetch))
    def test_changed_source_at_release_keeps_both_files_unchanged(self):
        self.run_admit()
        before={name:(self.root/name).read_bytes() for name in ('articles.json','editorial-queue.json')}
        self.fetch.return_value={'sha256':'b'*64,'text':'Changed'}
        with self.assertRaisesRegex(ValueError,'changed before publication'):
            a.q.promote(self.root,self.now,source_fetcher=self.fetch)
        for name,raw in before.items():self.assertEqual((self.root/name).read_bytes(),raw)
    def test_tampered_admission_evidence_blocks_before_fetch(self):
        self.run_admit();self.fetch.reset_mock()
        file=next((self.root/'editorial-guide-evidence').glob('*.json'))
        proof=json.loads(file.read_text());proof['proposal']['article']['title']='Modified'
        file.write_text(json.dumps(proof))
        with self.assertRaises(ValueError):a.q.promote(self.root,self.now,source_fetcher=self.fetch)
        self.fetch.assert_not_called()
