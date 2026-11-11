import pathlib
import shutil
import tempfile
import unittest

import photo_variants

try:
    from PIL import Image
except ImportError:  # The site tests run without Pillow; the deployment installs it for this step only.
    Image = None


@unittest.skipIf(Image is None, 'Pillow absent')
class PhotoVariantsTest(unittest.TestCase):
    def setUp(self):
        self.folder = pathlib.Path(tempfile.mkdtemp(prefix='vsd-photos-'))
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / 'photos').mkdir()

    def photo(self, name, width, height):
        path = self.folder / name
        Image.new('RGB', (width, height), (30, 80, 200)).save(path, 'JPEG')
        return path

    def test_missing_copies_are_created_narrower_and_never_twice(self):
        self.photo('photos/kyoto.jpg', 1600, 1000)
        existing = self.photo('photos/kyoto-800.jpg', 800, 500)
        before = existing.read_bytes()
        written = photo_variants.build(self.folder)
        self.assertEqual([p.name for p in written], ['kyoto-1200.jpg'])
        with Image.open(self.folder / 'photos/kyoto-1200.jpg') as copy:
            self.assertEqual(copy.size, (1200, 750))
        self.assertEqual(existing.read_bytes(), before)
        self.assertEqual(photo_variants.build(self.folder), [])

    def test_a_small_photo_is_never_enlarged_and_copies_are_not_copied_again(self):
        self.photo('petite.jpg', 1000, 600)
        written = photo_variants.build(self.folder)
        self.assertEqual([p.name for p in written], ['petite-800.jpg'])
        self.assertEqual(sorted(p.name for p in self.folder.rglob('*.jpg')), ['petite-800.jpg', 'petite.jpg'])


if __name__ == '__main__':
    unittest.main()
