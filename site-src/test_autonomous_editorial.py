import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import autonomous_editorial as intake


def article(source_url='https://official.example/source'):
    return {
        'slug': 'guide-nouveau', 'title': 'Guide nouveau', 'shortTitle': 'Guide nouveau',
        'destination': 'Porto', 'category': 'Conseils', 'description': 'Conseil vérifié.',
        'readMinutes': 3, 'summary': 'Résumé vérifié.', 'sourcesCheckedOn': '2026-10-01',
        'sections': [{'id': 'conseil', 'title': 'Conseil', 'paragraphs': ['Texte vérifié.']}],
        'faq': [], 'sources': [{'label': 'Source officielle', 'url': source_url}], 'related': [],
    }


class AutonomousEditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'editorial-candidates').mkdir()
        (self.root / 'articles.json').write_text(json.dumps([{
            'slug': 'guide-existant', 'title': 'Existant', 'shortTitle': 'Existant',
            'destination': 'Porto', 'category': 'Conseils', 'description': 'Existant',
            'readMinutes': 2, 'summary': 'Existant', 'sourcesCheckedOn': '2026-09-01',
            'sections': [{'id': 'x', 'title': 'X', 'paragraphs': ['X']}], 'faq': [],
            'sources': [{'label': 'Source', 'url': 'https://official.example/existing'}], 'related': [],
        }]))
        (self.root / 'editorial-queue.json').write_text(json.dumps({'schemaVersion': 1, 'drafts': [], 'promotions': []}))

    def tearDown(self):
        self.temp.cleanup()

    def candidate(self, release='2026-10-08T08:00:00Z', source_hash='a' * 64):
        return {
            'schemaVersion': 1, 'id': 'guide-nouveau-2026-10-08', 'releaseAt': release,
            'validUntil': '2026-11-08T00:00:00Z', 'article': article(),
            'sources': [{'url': 'https://official.example/source', 'sha256': source_hash,
                         'requiredText': ['Official source']}],
            'review': {'publicationApproved': False, 'fabricatedExperience': False, 'commercialClaims': False},
        }

    def test_admits_only_when_every_source_hash_matches(self):
        (self.root / 'editorial-candidates/candidate.json').write_text(json.dumps(self.candidate()))
        now = dt.datetime(2026, 10, 7, 8, tzinfo=dt.timezone.utc)
        result = intake.intake(self.root, now, fetcher=lambda url: {'sha256': 'a' * 64, 'text': 'Official source'})
        self.assertTrue(result['changed'])
        state = json.loads((self.root / 'editorial-queue.json').read_text())
        self.assertEqual(len(state['drafts']), 1)
        self.assertEqual(state['drafts'][0]['approval']['sha256'], intake.queue.approval_hash(state['drafts'][0]))

    def test_changed_source_stays_out_of_queue(self):
        (self.root / 'editorial-candidates/candidate.json').write_text(json.dumps(self.candidate()))
        result = intake.intake(self.root, dt.datetime(2026, 10, 7, 8, tzinfo=dt.timezone.utc),
                               fetcher=lambda url: {'sha256': 'b' * 64, 'text': 'Changed page'})
        self.assertFalse(result['changed'])
        self.assertEqual(result['candidates'][0]['status'], 'blocked')
        self.assertEqual(json.loads((self.root / 'editorial-queue.json').read_text())['drafts'], [])

    def test_dynamic_markup_change_is_allowed_only_with_required_anchor(self):
        (self.root / 'editorial-candidates/candidate.json').write_text(json.dumps(self.candidate()))
        result = intake.intake(self.root, dt.datetime(2026, 10, 7, 8, tzinfo=dt.timezone.utc),
                               fetcher=lambda url: {'sha256': 'b' * 64, 'text': 'Header Official source Footer'})
        self.assertTrue(result['changed'])
        self.assertEqual(result['candidates'][0]['sourceMatches'], ['anchors'])

    def test_missing_required_anchor_stays_out_of_queue(self):
        (self.root / 'editorial-candidates/candidate.json').write_text(json.dumps(self.candidate()))
        result = intake.intake(self.root, dt.datetime(2026, 10, 7, 8, tzinfo=dt.timezone.utc),
                               fetcher=lambda url: {'sha256': 'b' * 64, 'text': 'Different official page'})
        self.assertFalse(result['changed'])
        self.assertEqual(result['candidates'][0]['status'], 'blocked')

    def test_candidate_outside_window_is_not_fetched(self):
        candidate = self.candidate(release='2026-10-20T08:00:00Z')
        (self.root / 'editorial-candidates/candidate.json').write_text(json.dumps(candidate))
        calls = []
        result = intake.intake(self.root, dt.datetime(2026, 10, 7, 8, tzinfo=dt.timezone.utc),
                               fetcher=lambda url: calls.append(url) or {'sha256': 'a' * 64, 'text': 'Official source'})
        self.assertFalse(result['changed'])
        self.assertEqual(calls, [])
        self.assertEqual(result['candidates'][0]['status'], 'outside_window')


if __name__ == '__main__':
    unittest.main()
