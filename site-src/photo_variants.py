#!/usr/bin/env python3
"""Lighter copies of the site's photos, so a phone never downloads the 1 600 px file.

Run by the deployment before the build (Pillow installed by the workflow). The copies are
derived files: they are written beside the originals, never committed, and generate.py only
lists in `srcset` the ones it finds. Without this step the site still builds, with the
800 px and 1 600 px files of the catalogue.

    python photo_variants.py            create the missing copies under dist/assets
"""
import pathlib
import sys

ASSETS = pathlib.Path(__file__).parent / 'dist' / 'assets'
# A phone screen is 360 to 430 points wide at 2 to 3 pixels per point: 1 200 px covers it.
WIDTHS = (1200, 800)
# Same encoding as the photo chain (guide_photos.py): progressive JPEG, no metadata.
JPEG_QUALITY = 72


def is_variant(path):
    return any(path.stem.endswith(f'-{width}') for width in WIDTHS)


def originals(folder):
    return sorted(p for p in folder.rglob('*.jpg') if p.is_file() and not p.is_symlink() and not is_variant(p))


def variant_path(original, width):
    return original.with_name(f'{original.stem}-{width}.jpg')


def build(folder=ASSETS):
    """Create each missing copy narrower than its original; return the files written."""
    from PIL import Image
    written = []
    for original in originals(folder):
        missing = [width for width in WIDTHS if not variant_path(original, width).exists()]
        if not missing:
            continue
        with Image.open(original) as image:
            image.load()
            for width in missing:
                if width >= image.width:
                    continue
                height = round(image.height * width / image.width)
                target = variant_path(original, width)
                image.convert('RGB').resize((width, height), Image.LANCZOS).save(
                    target, 'JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True)
                written.append(target)
    return written


def main():
    written = build()
    sys.stdout.write(f'{len(written)} copies de photos créées.\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
