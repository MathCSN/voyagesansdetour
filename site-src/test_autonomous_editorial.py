import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def checklist(self, date, subject='guide-existant'):
        candidate = self.candidate(release=f'{date}T08:00:00Z')
        candidate['id'] = f'auto-mise-a-jour-{subject}-{date}'
        candidate['validUntil'] = '2027-02-16T08:00:00Z'
        candidate['article'].update(slug=f'mise-a-jour-{subject}-{date}',
                                    category='Mises à jour', related=[subject])
        return candidate

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

    def test_changed_facts_are_blocked_even_when_historical_anchors_remain(self):
        original = b'<h1>Official source</h1><p>Open daily. Tickets: 10 EUR.</p>'
        candidate = self.candidate(source_hash=intake.normalized_hash(original))
        path = self.root / 'editorial-candidates/candidate.json'
        path.write_text(json.dumps(candidate))
        before = {p: p.read_bytes() for p in (path, self.root / 'editorial-queue.json')}
        for changed in (
            b'<h1>Official source</h1><p>Permanently closed. Tickets: 10 EUR.</p>',
            b'<h1>Official source</h1><p>Open daily. Tickets: 25 EUR.</p>',
        ):
            with self.subTest(changed=changed):
                result = intake.intake(
                    self.root, dt.datetime(2026, 10, 7, 8, tzinfo=dt.timezone.utc),
                    fetcher=lambda url: {'sha256': intake.normalized_hash(changed),
                                         'text': changed.decode()},
                )
                self.assertFalse(result['changed'])
                self.assertEqual(result['candidates'][0]['status'], 'blocked')
                self.assertFalse((self.root / 'editorial-revalidation').exists())
                self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_script_and_style_changes_preserve_exact_visible_text_fingerprint(self):
        original = (b'<script>const version = 1;</script><style>h1{color:red}</style>'
                    b'<h1>Official source</h1><p>Open daily. Tickets: 10 EUR.</p>')
        changed = (b'<script>const version = 2;</script><style>h1{color:blue}</style>'
                   b'<h1>Official source</h1><p>Open daily. Tickets: 10 EUR.</p>')
        self.assertNotEqual(original, changed)
        self.assertEqual(intake.normalized_hash(original), intake.normalized_hash(changed))
        candidate = self.candidate(source_hash=intake.normalized_hash(original))
        (self.root / 'editorial-candidates/candidate.json').write_text(json.dumps(candidate))
        result = intake.intake(
            self.root, dt.datetime(2026, 10, 7, 8, tzinfo=dt.timezone.utc),
            fetcher=lambda url: {'sha256': intake.normalized_hash(changed),
                                 'text': 'Official source Open daily. Tickets: 10 EUR.'},
        )
        self.assertTrue(result['changed'])
        self.assertEqual(result['candidates'][0]['sourceMatches'], ['hash'])
        saved = json.loads((self.root / 'editorial-queue.json').read_text())['drafts'][0]
        self.assertEqual(saved['releaseAt'], candidate['releaseAt'])
        self.assertEqual(saved['validUntil'], candidate['validUntil'])
        self.assertEqual(saved['article'], candidate['article'])

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

    def test_rejected_queue_validation_does_not_leak_after_an_admission(self):
        valid = self.candidate()
        invalid = self.candidate()
        invalid['id'] = 'guide-invalide-2026-10-08'
        invalid['article']['slug'] = 'guide-invalide'
        # Candidate shape is valid; full queue validation rejects a review
        # whose source check claims a future date.
        invalid['article']['sourcesCheckedOn'] = '2026-10-09'
        paths = [self.root / 'editorial-candidates/a-valid.json',
                 self.root / 'editorial-candidates/b-invalid.json']
        for path, candidate in zip(paths, (valid, invalid)):
            path.write_text(json.dumps(candidate))
        before = {p: p.read_bytes() for p in paths}
        result = intake.intake(
            self.root, dt.datetime(2026, 10, 7, 8, tzinfo=dt.timezone.utc),
            fetcher=lambda url: {'sha256': 'a' * 64, 'text': 'Official source'},
        )
        self.assertEqual([item['status'] for item in result['candidates']],
                         ['admitted', 'invalid_candidate'])
        saved = json.loads((self.root / 'editorial-queue.json').read_text())
        self.assertEqual([item['id'] for item in saved['drafts']], [valid['id']])
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertFalse((self.root / f"editorial-revalidation/{invalid['id']}.json").exists())

    def test_conflicting_proof_does_not_leak_into_later_successful_admission(self):
        invalid = self.candidate()
        invalid['id'] = 'guide-conflit-2026-10-08'
        invalid['article']['slug'] = 'guide-conflit'
        valid = self.candidate()
        for name, candidate in (('a-conflict', invalid), ('b-valid', valid)):
            (self.root / f'editorial-candidates/{name}.json').write_text(json.dumps(candidate))
        proof_dir = self.root / 'editorial-revalidation'
        proof_dir.mkdir()
        conflict = proof_dir / f"{invalid['id']}.json"
        conflict.write_text('{"immutable": "existing proof"}\n')
        before = conflict.read_bytes()
        result = intake.intake(
            self.root, dt.datetime(2026, 10, 7, 8, tzinfo=dt.timezone.utc),
            fetcher=lambda url: {'sha256': 'a' * 64, 'text': 'Official source'},
        )
        self.assertEqual([item['status'] for item in result['candidates']],
                         ['invalid_candidate', 'admitted'])
        saved = json.loads((self.root / 'editorial-queue.json').read_text())
        self.assertEqual([item['id'] for item in saved['drafts']], [valid['id']])
        self.assertEqual(conflict.read_bytes(), before)

    def test_unreadable_or_non_object_candidate_does_not_stop_valid_candidate(self):
        (self.root / 'editorial-candidates/a-malformed.json').write_text('{')
        (self.root / 'editorial-candidates/b-array.json').write_text('[]')
        valid = self.candidate()
        (self.root / 'editorial-candidates/c-valid.json').write_text(json.dumps(valid))
        result = intake.intake(
            self.root, dt.datetime(2026, 10, 7, 8, tzinfo=dt.timezone.utc),
            fetcher=lambda url: {'sha256': 'a' * 64, 'text': 'Official source'},
        )
        self.assertEqual([item['status'] for item in result['candidates']],
                         ['invalid_candidate', 'invalid_candidate', 'admitted'])
        saved = json.loads((self.root / 'editorial-queue.json').read_text())
        self.assertEqual([item['id'] for item in saved['drafts']], [valid['id']])

    def test_historical_dated_copy_is_not_admitted_after_same_subject_was_published(self):
        prior = self.checklist('2027-01-03')
        candidate = self.checklist('2027-01-17')
        catalog_path = self.root / 'articles.json'
        articles = json.loads(catalog_path.read_text())
        articles.append(dict(prior['article'], publishedOn='2027-01-03', updatedOn='2027-01-03'))
        catalog_path.write_text(json.dumps(articles))
        path = self.root / 'editorial-candidates/historical-copy.json'
        path.write_text(json.dumps(candidate))
        before = {p: p.read_bytes() for p in (catalog_path, path, self.root / 'editorial-queue.json')}
        calls = []
        result = intake.intake(
            self.root, dt.datetime(2027, 1, 16, tzinfo=dt.timezone.utc),
            fetcher=lambda url: calls.append(url) or {'sha256': 'a' * 64, 'text': 'Official source'},
        )
        self.assertFalse(result['changed'])
        self.assertEqual(result['candidates'][0]['status'], 'duplicate_subject')
        self.assertEqual(result['candidates'][0]['subject'], 'guide-existant')
        self.assertEqual(calls, [])
        self.assertFalse((self.root / 'editorial-revalidation').exists())
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_historical_copy_is_blocked_by_an_already_admitted_checklist(self):
        prior = self.checklist('2027-01-03')
        state = {'schemaVersion': 1, 'drafts': [intake.approval_for(
            prior, dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc))], 'promotions': []}
        queue_path = self.root / 'editorial-queue.json'
        queue_path.write_text(json.dumps(state))
        candidate = self.checklist('2027-01-17')
        path = self.root / 'editorial-candidates/historical-copy.json'
        path.write_text(json.dumps(candidate))
        before = {p: p.read_bytes() for p in (queue_path, path)}
        calls = []
        result = intake.intake(
            self.root, dt.datetime(2027, 1, 16, tzinfo=dt.timezone.utc),
            fetcher=lambda url: calls.append(url) or {'sha256': 'a' * 64, 'text': 'Official source'},
        )
        self.assertFalse(result['changed'])
        self.assertEqual(result['candidates'][0]['status'], 'duplicate_subject')
        self.assertEqual(calls, [])
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_same_pass_admits_at_most_one_checklist_per_subject(self):
        catalog_path = self.root / 'articles.json'
        articles = json.loads(catalog_path.read_text())
        other = article()
        other['slug'] = 'autre-guide'
        articles.append(other)
        catalog_path.write_text(json.dumps(articles))
        first = self.checklist('2027-01-17')
        duplicate = self.checklist('2027-01-18')
        distinct = self.checklist('2027-01-17', subject='autre-guide')
        for name, candidate in (('a-first', first), ('b-duplicate', duplicate), ('c-distinct', distinct)):
            (self.root / f'editorial-candidates/{name}.json').write_text(json.dumps(candidate))
        calls = []
        result = intake.intake(
            self.root, dt.datetime(2027, 1, 16, tzinfo=dt.timezone.utc),
            fetcher=lambda url: calls.append(url) or {'sha256': 'a' * 64, 'text': 'Official source'},
        )
        self.assertEqual([item['status'] for item in result['candidates']],
                         ['admitted', 'duplicate_subject', 'admitted'])
        self.assertEqual(len(calls), 2)
        saved = json.loads((self.root / 'editorial-queue.json').read_text())
        self.assertEqual([item['id'] for item in saved['drafts']], [first['id'], distinct['id']])
        self.assertFalse((self.root / f"editorial-revalidation/{duplicate['id']}.json").exists())

    def test_rejected_checklist_does_not_reserve_the_subject(self):
        invalid = self.checklist('2027-01-17')
        invalid['article']['sourcesCheckedOn'] = '2027-01-17'
        valid = self.checklist('2027-01-18')
        for name, candidate in (('a-invalid', invalid), ('b-valid', valid)):
            (self.root / f'editorial-candidates/{name}.json').write_text(json.dumps(candidate))
        result = intake.intake(
            self.root, dt.datetime(2027, 1, 16, tzinfo=dt.timezone.utc),
            fetcher=lambda url: {'sha256': 'a' * 64, 'text': 'Official source'},
        )
        self.assertEqual([item['status'] for item in result['candidates']],
                         ['invalid_candidate', 'admitted'])
        saved = json.loads((self.root / 'editorial-queue.json').read_text())
        self.assertEqual([item['id'] for item in saved['drafts']], [valid['id']])

    def test_authorised_period_end_returns_before_any_read_write_or_fetch(self):
        for now in (intake.HARD_STOP, intake.HARD_STOP + dt.timedelta(seconds=1)):
            with self.subTest(now=now), patch.object(intake.queue, 'load') as load:
                calls = []
                nonexistent = self.root / 'missing-root'
                report_path = self.root / 'no-report-after-period.json'
                result = intake.intake(nonexistent, now, fetcher=lambda url: calls.append(url),
                                       output=report_path)
                self.assertEqual(result['status'], 'period_complete')
                self.assertFalse(result['changed'])
                self.assertEqual(result['candidates'], [])
                load.assert_not_called()
                self.assertEqual(calls, [])
                self.assertFalse(nonexistent.exists())
                self.assertFalse(report_path.exists())

    def test_candidate_windows_outside_authorised_period_are_never_fetched(self):
        at_end = self.candidate(release='2027-09-14T21:59:59Z')
        at_end['validUntil'] = '2027-09-14T22:00:00Z'
        late_expiry = self.candidate(release='2027-09-14T08:00:00Z')
        late_expiry['id'] = 'guide-expiry-too-late'
        late_expiry['validUntil'] = '2027-09-14T22:00:00Z'
        for name, candidate in (('a-release-at-stop', at_end), ('b-late-expiry', late_expiry)):
            (self.root / f'editorial-candidates/{name}.json').write_text(json.dumps(candidate))
        before = {path: path.read_bytes() for path in self.root.rglob('*.json')}
        calls = []
        result = intake.intake(
            self.root, dt.datetime(2027, 9, 13, tzinfo=dt.timezone.utc),
            fetcher=lambda url: calls.append(url),
        )
        self.assertFalse(result['changed'])
        self.assertEqual([item['status'] for item in result['candidates']],
                         ['invalid_candidate', 'invalid_candidate'])
        self.assertEqual(calls, [])
        self.assertFalse((self.root / 'editorial-revalidation').exists())
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_last_valid_window_can_expire_exactly_at_authorised_stop(self):
        candidate = self.candidate(release='2027-09-14T08:00:00Z')
        candidate['validUntil'] = '2027-09-14T21:59:59Z'
        (self.root / 'editorial-candidates/last-window.json').write_text(json.dumps(candidate))
        result = intake.intake(
            self.root, dt.datetime(2027, 9, 13, tzinfo=dt.timezone.utc),
            fetcher=lambda url: {'sha256': 'a' * 64, 'text': 'Official source'},
        )
        self.assertTrue(result['changed'])
        saved = json.loads((self.root / 'editorial-queue.json').read_text())['drafts'][0]
        self.assertEqual(saved['validUntil'], candidate['validUntil'])


if __name__ == '__main__':
    unittest.main()
