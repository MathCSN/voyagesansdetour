import copy
import json
import tempfile
import unittest
from pathlib import Path

from cloud_source_changes import push_file_requires_build, push_requires_build


def candidate_push():
    return {'size': 1, 'commits': [{
        'added': ['site-src/editorial-candidates/guide-candidate.json'],
        'modified': [], 'removed': [],
    }]}


class CloudSourceChangesTests(unittest.TestCase):
    def test_absent_or_empty_commit_list_requires_build(self):
        for event in ({}, {'size': 0, 'commits': []}, {'size': 1},
                      {'size': 1, 'commits': None}):
            with self.subTest(event=event):
                self.assertTrue(push_requires_build(event))

    def test_every_per_commit_file_list_must_be_present(self):
        for omitted in ('added', 'modified', 'removed'):
            event = candidate_push()
            del event['commits'][0][omitted]
            with self.subTest(omitted=omitted):
                self.assertTrue(push_requires_build(event))
        # The observed Actions payload lists commit metadata without file lists.
        self.assertTrue(push_requires_build({'size': 1, 'commits': [{'id': 'a' * 40}]}))

    def test_complete_candidate_only_push_does_not_require_build(self):
        event = candidate_push()
        event['size'] = 2
        event['commits'].append({'added': [],
                                 'modified': ['site-src/editorial-candidates/another.json'],
                                 'removed': ['site-src/editorial-candidates/old.json']})
        before = copy.deepcopy(event)
        self.assertFalse(push_requires_build(event))
        self.assertEqual(event, before)

    def test_source_or_workflow_change_requires_build(self):
        for path in ('site-src/autonomous_editorial.py', 'site-src/articles.json',
                     'site-src/editorial-queue.json', '.github/workflows/build-pages.yml',
                     'site-src/editorial-candidates/validator.py'):
            for change in ('added', 'modified', 'removed'):
                event = candidate_push()
                event['commits'][0][change].append(path)
                with self.subTest(path=path, change=change):
                    self.assertTrue(push_requires_build(event))

    def test_missing_inconsistent_or_truncated_commit_count_requires_build(self):
        for size in (None, 0, 2, True, '1'):
            event = candidate_push()
            event['size'] = size
            with self.subTest(size=size):
                self.assertTrue(push_requires_build(event))
        event = candidate_push()
        del event['size']
        self.assertTrue(push_requires_build(event))
        event = candidate_push()
        event['truncated'] = True
        self.assertTrue(push_requires_build(event))

    def test_malformed_payload_or_paths_require_build(self):
        for event in (None, [], 'event', {'size': 1, 'commits': [None]},
                      {'size': 1, 'commits': {'added': []}}):
            with self.subTest(event=event):
                self.assertTrue(push_requires_build(event))
        for malformed in (None, 'not-a-list', {}, [None], [3], [''],
                          ['site-src/editorial-candidates/../articles.json'],
                          ['/site-src/editorial-candidates/guide.json'],
                          ['site-src//editorial-candidates/guide.json']):
            event = candidate_push()
            event['commits'][0]['modified'] = malformed
            with self.subTest(malformed=malformed):
                self.assertTrue(push_requires_build(event))

    def test_empty_file_lists_do_not_prove_a_candidate_only_push(self):
        event = {'size': 1, 'commits': [{'added': [], 'modified': [], 'removed': []}]}
        self.assertTrue(push_requires_build(event))

    def test_event_file_missing_invalid_or_omitted_falls_back_to_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'push.json'
            self.assertTrue(push_file_requires_build(path))
            self.assertTrue(push_file_requires_build(None))
            for contents in ('{', '[]', '{"commits": []}'):
                path.write_text(contents)
                with self.subTest(contents=contents):
                    self.assertTrue(push_file_requires_build(path))
            path.write_text(json.dumps(candidate_push()))
            self.assertFalse(push_file_requires_build(path))


if __name__ == '__main__':
    unittest.main()
