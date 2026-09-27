import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from public_media import approved_files


class ApprovedMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'social-media/production/test-clip'
        self.folder.mkdir(parents=True)
        self.item = {'contentId': 'test-clip', 'approved': True, 'files': []}
        for name in ('reel.mp4', 'poster.jpg', 'credits.txt'):
            data = ('fixture ' + name).encode()
            (self.folder / name).write_bytes(data)
            self.item['files'].append({'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})

    def save(self, items=None):
        (self.root / 'public-media.json').write_text(json.dumps({'schemaVersion': 1, 'items': items if items is not None else [self.item]}))

    def test_exports_only_approved_files_and_never_extra_private_files(self):
        (self.folder / 'private-receipt.json').write_text('not public')
        self.save()
        self.assertEqual(set(approved_files(self.root)), {'production/test-clip/' + n for n in ('reel.mp4', 'poster.jpg', 'credits.txt')})

    def test_changed_bytes_are_rejected_even_at_same_size(self):
        self.save()
        target = self.folder / 'reel.mp4'
        target.write_bytes(b'x' * target.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            approved_files(self.root)

    def test_escaped_paths_unapproved_and_duplicate_items_are_rejected(self):
        for identity, approved in [('../private', True), ('test-clip', False)]:
            self.item.update(contentId=identity, approved=approved)
            self.save()
            with self.assertRaises(ValueError):
                approved_files(self.root)
        self.item.update(contentId='test-clip', approved=True)
        self.save([self.item, self.item])
        with self.assertRaises(ValueError):
            approved_files(self.root)

    def test_missing_credits_and_arbitrary_files_cannot_enter_public_build(self):
        self.item['files'][-1]['name'] = 'secret.json'
        self.save()
        with self.assertRaises(ValueError):
            approved_files(self.root)
        self.item['files'][-1]['name'] = 'dmsans-OFL.txt'
        (self.folder / 'credits.txt').rename(self.folder / 'dmsans-OFL.txt')
        self.save()
        with self.assertRaisesRegex(ValueError, 'credits required'):
            approved_files(self.root)

    def test_symlinked_media_and_parent_are_rejected(self):
        self.save()
        target = self.folder / 'reel.mp4'
        copied = self.root / 'elsewhere.mp4'
        target.rename(copied)
        target.symlink_to(copied)
        with self.assertRaises(ValueError):
            approved_files(self.root)
        target.unlink()
        copied.rename(target)
        original = self.root / 'original'
        self.folder.rename(original)
        self.folder.symlink_to(original, target_is_directory=True)
        with self.assertRaises(ValueError):
            approved_files(self.root)


if __name__ == '__main__':
    unittest.main()
