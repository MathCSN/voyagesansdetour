#!/usr/bin/env python3
"""The site's icon files, drawn from the logo: a yellow « v » in Georgia on the brand blue.

Same drawing as the former inline SVG icon (64 px square, corners rounded at 13 px, letter of
47 px on a baseline at 46 px). Run by hand when the logo changes; the three files are committed
and generate.py serves them at the root of the site. Needs Pillow and the Georgia font.

    python favicon_files.py [path/to/Georgia.ttf]
"""
import pathlib
import sys

OUT = pathlib.Path(__file__).parent / 'dist'
GEORGIA = '/System/Library/Fonts/Supplemental/Georgia.ttf'
BLUE, YELLOW = '#214fe6', '#f8de55'
# Measures of the logo on its 64 px grid.
GRID, CORNER, LETTER_SIZE, LETTER_X, BASELINE = 64, 13, 47, 32, 46
# Drawn larger then reduced, so the curves of the letter stay smooth at 16 px.
OVERSAMPLING = 8
ICO_SIZES = (16, 32, 48)
PNG_SIZE = 96
# iOS rounds the corners itself: its icon fills the whole square.
TOUCH_SIZE = 180


def draw(size, font_path, rounded=True):
    from PIL import Image, ImageDraw, ImageFont
    side = size * OVERSAMPLING
    unit = side / GRID
    image = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle((0, 0, side - 1, side - 1), radius=CORNER * unit if rounded else 0, fill=BLUE)
    font = ImageFont.truetype(font_path, round(LETTER_SIZE * unit))
    # « ms »: horizontally centred on the point, which sits on the baseline.
    pen.text((LETTER_X * unit, BASELINE * unit), 'v', font=font, fill=YELLOW, anchor='ms')
    return image.resize((size, size), Image.LANCZOS)


def build(font_path=GEORGIA, out=OUT):
    """Write the three icon files; return their paths."""
    icon, png, touch = out / 'favicon.ico', out / 'favicon.png', out / 'apple-touch-icon.png'
    largest = draw(max(ICO_SIZES), font_path)
    largest.save(icon, format='ICO', append_images=[draw(size, font_path) for size in ICO_SIZES[:-1]],
                 sizes=[(size, size) for size in ICO_SIZES])
    draw(PNG_SIZE, font_path).save(png, 'PNG', optimize=True)
    draw(TOUCH_SIZE, font_path, rounded=False).convert('RGB').save(touch, 'PNG', optimize=True)
    return [icon, png, touch]


def main():
    font_path = sys.argv[1] if len(sys.argv) > 1 else GEORGIA
    if not pathlib.Path(font_path).is_file():
        sys.stderr.write(f'Police introuvable : {font_path}\n')
        return 1
    for path in build(font_path):
        sys.stdout.write(f'{path.name} : {path.stat().st_size} octets\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
