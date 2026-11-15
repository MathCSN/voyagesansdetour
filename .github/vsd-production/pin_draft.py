"""Draw the unpublished Pins of a published guide: up to three, each with its own photo, title and look.

What sends readers from Pinterest to travel blogs (docs/strategie-videos.md): a real photo of the
place, a large title that repeats what people type ("2 semaines au Japon : itinéraire et budget"),
and several fresh Pins per guide, each with a different picture. So one guide gives:
- variant "a" (pin-<slug>): the cover photo, the short title and the first key figure;
- variant "b" (pin-<slug>-b): another photo of the guide and its three key figures, to save as a memo;
- variant "c" (pin-<slug>-c): a third photo above a plain band with the search-style title.
A variant is drawn only with a photo no other variant uses; a guide without cover keeps its
typographic Pin. Never an AI-generated image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.parse

from PIL import Image, ImageDraw, ImageFont

import destinations
from photo_intake import ai_record
import place_names
import production
import reel_formats
import social_render as base

HERE = Path(__file__).resolve().parent
SITE = HERE.parents[1] / 'site-src'
ORIGIN = 'https://voyagesansdetour.fr'
SIZE = (1000, 1500)
VARIANTS = ('a', 'b', 'c')
TITLE_MAX = 100
FREE_LICENSES = ('CC BY 2.0', 'CC BY 3.0', 'CC BY 4.0', 'CC BY-SA 2.0', 'CC BY-SA 3.0', 'CC BY-SA 4.0', 'CC0', 'CC0 1.0', 'Public domain')
INK, NIGHT, YELLOW, BLUE, PAPER = '#142A43', '#0E1B2B', '#F5D547', '#234CDD', '#F7F4EC'
FONTS = {'serif': 'playfair.ttf', 'bold': 'dmsans-bold.ttf', 'regular': 'dmsans-regular.ttf'}
# Noto Sans draws what the brand fonts lack (₫, Vietnamese letters…): never an empty box on a Pin.
FALLBACKS = {'playfair.ttf': 'notosans-bold.ttf', 'dmsans-bold.ttf': 'notosans-bold.ttf', 'dmsans-regular.ttf': 'notosans-regular.ttf'}
# What people type on Pinterest for each kind of guide, after the destination.
TITLE_ENDINGS = {'itineraires': 'itinéraire jour par jour, prix et conseils', 'itineraire': 'itinéraire jour par jour, prix et conseils',
                 'budget': 'combien ça coûte, poste par poste', 'choisir': 'comment choisir, chiffres à l’appui',
                 'transports': 'trajets, horaires et prix', 'excursions': 'l’excursion à la journée, pas à pas',
                 'quartiers': 'où dormir, quartier par quartier', 'que faire': 'que faire et que voir, avec les prix',
                 'preparer': 'bien préparer son départ'}
WHEN_TO_GO = 'la meilleure période, mois par mois'
DEFAULT_ENDING = 'l’essentiel à savoir avant de partir'


def article_path(article):
    # Same rule as the site: guides live under their country, Portugal by default.
    country = article.get('country', 'portugal')
    if not isinstance(country, str) or not re.fullmatch(r'[a-z]+(?:-[a-z]+)*', country):
        raise ValueError('invalid_country')
    return '/' + country + '/' + article['slug'] + '/'


def pin_id(slug, variant='a'):
    return 'pin-' + slug + ('' if variant == 'a' else '-' + variant)


def font(name, size):
    return ImageFont.truetype(str(HERE / 'assets' / name), size)


def write(draw, xy, text, face, fill):
    base.draw_plain(draw, xy, text, face, fill)


def width_of(draw, text, face):
    return base.text_width(draw, text, face)


# What a line never begins with, and what is never cut from what it measures: "Lisbonne ou Porto ?", "22 h", "9 h 51".
GLUED = ((re.compile(r' ([:;?!»])'), '\u00a0\\1'), (re.compile(r'(\d) (?=[^\s\d]{1,3}(?:\s|$))'), '\\1\u00a0'),
         (re.compile(r'\b([hH]) (?=\d)'), '\\1\u00a0'))


def glued(text):
    for pattern, replacement in GLUED:
        text = pattern.sub(replacement, text)
    return text


def wrap(draw, text, face, width):
    lines, line = [], ''
    for word in (w for w in re.split(r'[ \t\n]+', glued(text)) if w):
        candidate = (line + ' ' + word).strip()
        if width_of(draw, word, face) > width:
            raise ValueError('word_overflow')
        if width_of(draw, candidate, face) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def fit(draw, text, sizes, width, height, gap, name=FONTS['serif']):
    for size in sizes:
        face = font(name, size)
        lines = wrap(draw, text, face, width)
        if len(lines) * (size + gap) <= height:
            return face, size, lines
    raise ValueError('title_overflow')


# --- what the Pin says ------------------------------------------------------

def key_facts(article):
    return [fact for fact in article.get('keyFacts') or [] if fact.get('value') and fact.get('label')]


def key_fact(article):
    facts = article.get('keyFacts') or []
    return facts[0] if facts and facts[0].get('value') and facts[0].get('label') else None


def everywhere_of(article, site=SITE):
    """The words every photo of the guide shares: its destination and its country."""
    country = destinations.name(destinations.country_slug(article), destinations.load(site))
    return place_names.words((article.get('destination') or '') + ' ' + country)


def commons_title_of(photo):
    page = photo.get('source_page') or ''
    return urllib.parse.unquote(page.rsplit('/wiki/', 1)[-1]).replace('_', ' ') if '/wiki/' in page else ''


def fact_fits_photo(fact, photo, everywhere, cover=False):
    """A Pin has one photo: a figure goes on it only when it names no place but the photo's own (the same reading as
    a post, place_names.fits). "Faro → Tavira" stood over the Ponta da Piedade of Lagos, "Séville → Cordoue" over the
    Alhambra (review of 13/11/2026). A journey goes over its means of transport or not at all, a taxi included: the
    night train over the village of Santa Claus, "Rome → Salerne en Italo" over a ferry (review of the Pins,
    15/11/2026). A figure that names nothing goes on the guide's cover, or on a photo of what it measures: no price of a
    reindeer ride over huskies."""
    text = fact['value'] + ' ' + fact['label']
    caption, title = photo.get('alt_fr') or '', commons_title_of(photo)
    shown = place_names.pictured(photo['id'], caption, title, everywhere)
    found = place_names.record(photo['id'], caption, title, everywhere)
    on = place_names.vehicle(photo['id'], caption, title)
    if place_names.brand_clash(text, shown) or place_names.other_ride(on, text):
        return False
    # The means read in the label as it opens ("le taxi au départ de l'aéroport"), else with its figure ("10 trains").
    wanted = place_names.wanted_ways(fact['label']) or place_names.wanted_ways(text)
    if wanted and (place_names.journey(fact['label']) or place_names.journey(text) or 'other' in wanted):
        return place_names.ride(shown, text) and place_names.on_the_way(found, place_names.read(fact['label'], everywhere))
    reading = place_names.read(text, everywhere)
    if reading.all:
        return bool(place_names.fits(reading, shown, place_names.pictured('', caption, title, everywhere), found))
    region = place_names.region(text)
    if region:
        return not (found and not region <= place_names.words(caption))
    described = ' '.join([photo['id'].replace('-', ' '), caption, place_names.readable(title)])
    shared = reel_formats.words_of(fact['label']) & reel_formats.words_of(described) - set(everywhere)
    return cover or bool(shared - reel_formats.PLACE_KINDS)


def facts_for(article, photo, site=SITE, count=1):
    """The first key figures of the guide that this photo can carry, in the guide's order, at most `count`."""
    everywhere = everywhere_of(article, site)
    cover = photo.get('id') == article.get('cover')
    return [fact for fact in key_facts(article) if fact_fits_photo(fact, photo, everywhere, cover)][:count]


# What a figure holds under: a line is never cut before it (the same list as the posts').
CONDITION = reel_formats.CONDITION


def fitted_label(draw, label, face, width, most=2):
    """The label in `most` lines at most: whole, or cut at a pause into a full phrase. Never a line that ends on a
    comma, a dash or an open bracket ("…hors vol —", "…(12 à 24 mm à Bangkok,"), never before a condition of the
    figure. None when no such cut exists: the figure is not shown."""
    if len(wrap(draw, label, face, width)) <= most:
        return label
    cuts = sorted({match.start() for match in re.finditer(r' \(| ; |, | — | : ', label)}, reverse=True)
    for cut in cuts:
        head, rest = label[:cut].rstrip(' ,;:—-'), label[cut:].lstrip(' ,;:—-(')
        # Never inside a list after a colon ("…pour 14 jours : navettes, bus" left out the parks and the nights), and
        # never what drops a condition further on ("…, hors repas et vols").
        listed = label[cut:cut + 2] == ', ' and ' : ' in label[:cut]
        if (len(head) >= 18 and head.count('(') == head.count(')') and not listed and not CONDITION.search(rest)
                and len(wrap(draw, head, face, width)) <= most):
            return head
    return None


def place_label(article, site=SITE):
    # 'ITALIE · CINQUE TERRE': the country from destinations.json, then the destination when it differs.
    country = destinations.name(destinations.country_slug(article), destinations.load(site))
    place = (article.get('destination') or '').strip()
    label = country if not place or place.lower() == country.lower() else country + ' · ' + place
    return label.upper() if len(label) <= 34 else country.upper()


def search_title(article):
    """The short title, then the words people add when they search this kind of guide: joined as a post's title is
    ("Laponie : le budget — combien ça coûte…", never two colons), without what the short title already says ("Où
    dormir à Lisbonne — quartier par quartier"), and "jour par jour" only for a guide told day by day."""
    short = (article.get('shortTitle') or article['title']).strip()
    category = destinations.ascii_fold(str(article.get('category', ''))).lower().strip()
    ending = WHEN_TO_GO if short.lower().startswith('quand partir') else TITLE_ENDINGS.get(category, DEFAULT_ENDING)
    if 'jour par jour' in ending and not told_by_day(article):
        ending = ending.replace('itinéraire jour par jour', 'itinéraire')
    return reel_formats.joined_title(short, not_said(short, ending))


def told_by_day(article):
    return any(reel_formats.DAY.fullmatch(str(section.get('title', '')).strip()) for section in article.get('sections') or [])


def not_said(short, ending):
    """The ending without its clauses that the short title already says ("où dormir" after "Où dormir à Lisbonne")."""
    said = set(place_names.folded(short))
    clauses = ending.split(', ')
    while len(clauses) > 1 and {word for word in place_names.folded(clauses[0]) if len(word) >= 3} <= said:
        clauses = clauses[1:]
    return ', '.join(clauses)


def pin_title(article, variant='a'):
    """The Pin's own title, 100 characters at most: the guide's title, or its search-style variants."""
    title, short = article['title'].strip(), (article.get('shortTitle') or article['title']).strip()
    # Variant "c" shows no figure: its title promises none (review of the Pins, 15/11/2026).
    choices = {'a': [title, search_title(article)], 'b': [search_title(article), reel_formats.joined_title(short, DEFAULT_ENDING)],
               'c': [reel_formats.joined_title(short, 'le guide pratique')]}[variant]
    for choice in choices + [short]:
        if 1 <= len(choice) <= TITLE_MAX:
            return choice
    raise ValueError('title_overflow')


# --- photos ----------------------------------------------------------------

def catalogue(site):
    return {photo['id']: photo for photo in json.loads((Path(site) / 'image-sources.json').read_text())['photos']}


def checked_photo(photo, site):
    """A catalogued photo with a free licence, an author, a source page, a file, and no AI mark."""
    if photo.get('license') not in FREE_LICENSES or not photo.get('author') or not photo.get('source_page'):
        raise ValueError('photo_license')
    # Real photographs only (CLAUDE.md): never a photo whose record names an AI generator or category.
    if ai_record(photo):
        raise ValueError('photo_ai_generated')
    path = Path(site) / 'dist/assets' / photo.get('file', '')
    if not photo.get('file') or not path.is_file():
        raise ValueError('photo_file_missing')
    return photo, path


def cover_photo(article, site):
    # The guide's own cover, only when its catalogue entry carries a free licence and an author.
    cover = article.get('cover')
    if not cover:
        return None
    photos = catalogue(site)
    if cover not in photos:
        raise ValueError('photo_missing_from_catalogue')
    return checked_photo(photos[cover], site)


# Photos a Pin never takes, though the guide shows them: read on the image (review of the Pins, 15/11/2026).
LEFT_OUT = {'lisbonne-santa-justa': "l'ascenseur de Santa Justa, fermé selon le guide « Où dormir à Lisbonne »"}


def taken_by_other_pins(slug, drafts=None):
    """The photos the Pins of other guides already show: two Pins never share their picture (the tram of Alfama was on
    "Où dormir à Lisbonne" and on "Voyager léger au Portugal")."""
    folder = Path(drafts) if drafts else HERE / 'pin-drafts'
    taken = set()
    for manifest in folder.glob('*/draft.json'):
        draft = json.loads(manifest.read_text())
        # A draft of an older renderer is to be redrawn, and may change its picture: it holds none.
        current = draft.get('rendererSha256') == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if current and not draft['id'].removeprefix('pin-').startswith(slug):
            taken.add((draft.get('photo') or {}).get('id'))
    return taken - {None}


def guide_photos(article, site):
    """The guide's photos in reading order, cover first, each once, only those that pass every check."""
    photos = catalogue(site)
    ids = [article.get('cover')] + [section.get('image') for section in article.get('sections') or []]
    found = []
    for identity in dict.fromkeys(i for i in ids if i and i not in LEFT_OUT):
        try:
            found.append(checked_photo(photos[identity], site))
        except (KeyError, ValueError):
            continue
    return found


def variant_photo(article, site, variant, drafts=None):
    """Variant "b" takes the guide's second photo, "c" its third: a fresh Pin is a different picture."""
    taken = taken_by_other_pins(article['slug'], drafts)
    photos = [found for found in guide_photos(article, site) if found[0]['id'] == article.get('cover') or found[0]['id'] not in taken]
    index = VARIANTS.index(variant)
    if not article.get('cover') or len(photos) <= index:
        raise ValueError('no_distinct_photo')
    return photos[index]


# --- drawing ---------------------------------------------------------------

def cropped(path, size, top=0.5):
    with Image.open(path) as source:
        source = source.convert('RGB')
        scale = max(size[0] / source.width, size[1] / source.height)
        resized = source.resize((round(source.width * scale), round(source.height * scale)), Image.LANCZOS)
    left, upper = (resized.width - size[0]) // 2, round((resized.height - size[1]) * top)
    return resized.crop((left, upper, left + size[0], upper + size[1]))


def shaded(image, start, strength):
    # Dark gradient from `start` down so the text stays readable on any photo.
    shade = Image.new('L', (1, SIZE[1]))
    for y in range(SIZE[1]):
        shade.putpixel((0, y), 0 if y < start else min(strength, int((y - start) / (SIZE[1] - start) * strength * 1.28)))
    return Image.composite(Image.new('RGB', SIZE, NIGHT), image, shade.resize(SIZE))


def label_pill(draw, x, y, label):
    small = font(FONTS['bold'], 26)
    draw.rounded_rectangle((x, y, x + 40 + width_of(draw, label, small), y + 56), radius=28, fill=YELLOW)
    write(draw, (x + 20, y + 12), label, small, INK)


def credit_line(draw, y, photo, sizes=(22, 20, 18)):
    """'Photo : author — licence', within the Pin's width: smaller, then on two lines, never cut at the edge
    ("laponie" lost the end of its licence)."""
    text = 'Photo : ' + production.tight_brackets(photo['author']) + ' — ' + photo['license']
    for size in sizes:
        face = font(FONTS['regular'], size)
        if width_of(draw, text, face) <= 860:
            write(draw, (70, y), text, face, '#D8DEE8')
            return
    face = font(FONTS['regular'], sizes[-1])
    for i, line in enumerate(wrap(draw, text, face, 860)[:2]):
        write(draw, (70, y - 12 + i * (sizes[-1] + 4)), line, face, '#D8DEE8')


def footer(draw, photo):
    write(draw, (70, 1385), 'voyagesansdetour.fr', font(FONTS['bold'], 38), 'white')
    credit_line(draw, 1440, photo)


def draw_photo_pin(article, photo, path, site=SITE):
    """Variant "a": the cover in full, the short title and the first key figure."""
    image = shaded(cropped(path, SIZE), 450, 235)
    draw = ImageDraw.Draw(image)
    label_pill(draw, 70, 70, place_label(article, site))
    heading, size, lines = fit(draw, article.get('shortTitle') or article['title'], (96, 88, 80, 72, 64), 860, 420, 16)
    label_face = font(FONTS['regular'], 34)
    shown = [(fact, fitted_label(draw, fact['label'], label_face, 860)) for fact in facts_for(article, photo, site, len(key_facts(article)))]
    fact, label = next(((fact, label) for fact, label in shown if label), (None, None))
    y = 1010 - len(lines) * (size + 16) - (0 if fact else -150)
    for line in lines:
        write(draw, (70, y), line, heading, 'white')
        y += size + 16
    if fact:
        write(draw, (70, y + 30), fact['value'], font(FONTS['bold'], 84), YELLOW)
        for i, line in enumerate(wrap(draw, label, label_face, 860)):
            write(draw, (70, y + 135 + i * 46), line, label_face, 'white')
    footer(draw, photo)
    return image


def draw_figures_pin(article, photo, path, site=SITE):
    """Variant "b": a memo to save. The title, then three key figures with what they measure."""
    # Three figures this photo can carry, each said whole in two lines: else no memo is drawn on this photo.
    probe = ImageDraw.Draw(Image.new('RGB', (10, 10)))
    facts = [(fact, fitted_label(probe, fact['label'], font(FONTS['regular'], 32), 860)) for fact in facts_for(article, photo, site, len(key_facts(article)))]
    facts = [(fact, label) for fact, label in facts if label][:3]
    if len(facts) < 3:
        raise ValueError('not_enough_key_facts')
    # A veil over the whole photo first: the title sits at the top, where a gradient alone would leave it on bright sky.
    image = shaded(Image.blend(cropped(path, SIZE), Image.new('RGB', SIZE, NIGHT), 0.5), 120, 215)
    draw = ImageDraw.Draw(image)
    label_pill(draw, 70, 70, place_label(article, site))
    heading, size, lines = fit(draw, article.get('shortTitle') or article['title'], (84, 76, 68, 60), 860, 300, 14)
    y = 190
    for line in lines:
        write(draw, (70, y), line, heading, 'white')
        y += size + 14
    y = max(y + 40, 560)
    value_face, label_face = font(FONTS['bold'], 76), font(FONTS['regular'], 32)
    for fact, label in facts:
        draw.line((70, y, 930, y), fill=YELLOW, width=3)
        if width_of(draw, fact['value'], value_face) > 860:
            raise ValueError('figure_overflow')
        write(draw, (70, y + 22), fact['value'], value_face, YELLOW)
        for i, line in enumerate(wrap(draw, label, label_face, 860)):
            write(draw, (70, y + 122 + i * 42), line, label_face, 'white')
        y += 250
    footer(draw, photo)
    return image


def draw_title_pin(article, photo, path, site=SITE):
    """Variant "c": the photo untouched on top, the search-style title on a plain band below."""
    image = Image.new('RGB', SIZE, NIGHT)
    image.paste(cropped(path, (1000, 860)), (0, 0))
    draw = ImageDraw.Draw(image)
    label_pill(draw, 70, 832, place_label(article, site))
    heading, size, lines = fit(draw, pin_title(article, 'b'), (72, 66, 60, 54, 48), 860, 380, 14)
    y = 930
    for line in lines:
        write(draw, (70, y), line, heading, 'white')
        y += size + 14
    draw.rounded_rectangle((70, 1318, 640, 1392), radius=37, fill=YELLOW)
    write(draw, (100, 1334), 'Le guide complet sur le blog', font(FONTS['bold'], 34), INK)
    write(draw, (70, 1418), 'voyagesansdetour.fr', font(FONTS['bold'], 30), 'white')
    credit_line(draw, 1458, photo, (20, 18))
    return image


def draw_typographic_pin(article):
    image = Image.new('RGB', SIZE, PAPER)
    draw = ImageDraw.Draw(image)
    small, regular = font(FONTS['bold'], 25), font(FONTS['regular'], 32)
    draw.rectangle((0, 0, 1000, 20), fill=BLUE)
    write(draw, (80, 85), 'VOYAGE SANS DÉTOUR', small, BLUE)
    draw.rounded_rectangle((80, 205, 410, 260), radius=27, fill='#E6EE77')
    write(draw, (104, 215), 'LE GUIDE À GARDER', small, INK)
    heading, size, lines = fit(draw, article['title'], (86, 80, 74, 68, 62), 840, 630, 22)
    y = 340
    for line in lines:
        write(draw, (80, y), line, heading, INK)
        y += size + 22
    draw.line((80, 1090, 920, 1090), fill=BLUE, width=3)
    fact = key_fact(article)
    if fact:
        write(draw, (80, 1115), fact['value'], font(FONTS['bold'], 60), BLUE)
        write(draw, (80, 1195), wrap(draw, fact['label'], regular, 840)[0], regular, INK)
    else:
        write(draw, (80, 1160), 'Le guide complet, prix et trajets vérifiés.', regular, INK)
    draw.rounded_rectangle((80, 1320, 920, 1410), radius=20, fill=BLUE)
    write(draw, (135, 1347), 'voyagesansdetour.fr', font(FONTS['bold'], 40), 'white')
    return image


DRAWERS = {'a': draw_photo_pin, 'b': draw_figures_pin, 'c': draw_title_pin}


def credits(photo):
    fonts = 'Polices DM Sans, Playfair Display et Noto Sans : licences OFL jointes.'
    if not photo:
        return 'Composition typographique Voyage Sans Détour, assistée par IA. ' + fonts + '\n'
    return ('Photo : ' + production.tight_brackets(photo['author']) + ', ' + photo['source_page'] + ' — ' + photo['license'] + ' (' + photo['license_url'] + ').\n'
            'Recadrage, dégradé et texte ajoutés par Voyage Sans Détour ; épingle diffusée sous la même licence. ' + fonts + '\n')


def render(article, output, site=SITE, variant='a'):
    slug = article['slug']
    if not isinstance(slug, str) or not slug or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in slug):
        raise ValueError('invalid_slug')
    title = article['title']
    if not isinstance(title, str) or not 1 <= len(title) <= 200:
        raise ValueError('invalid_title')
    if variant not in VARIANTS:
        raise ValueError('invalid_variant')
    target_url = ORIGIN + article_path(article)
    identity = pin_id(slug, variant)
    target = Path(output) / identity
    if target.exists():
        raise ValueError('existing_draft_preserved')
    base.use_fallbacks({str(HERE / 'assets' / brand): str(HERE / 'assets' / other) for brand, other in FALLBACKS.items()})
    found = cover_photo(article, site) if variant == 'a' else variant_photo(article, site, variant, output)
    photo = found[0] if found else None
    image = DRAWERS[variant](article, *found, site=site) if found else draw_typographic_pin(article)
    headline = pin_title(article, variant)
    target.mkdir(parents=True)
    image.save(target / 'pin.jpg', quality=92)
    raw = json.dumps(article, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    manifest = {'schemaVersion': 1, 'id': identity, 'status': 'draft_requires_review', 'publicationApproved': False,
                'title': title, 'pinTitle': headline, 'variant': variant, 'targetUrl': target_url,
                'articleSha256': hashlib.sha256(raw).hexdigest(), 'imageSha256': hashlib.sha256((target / 'pin.jpg').read_bytes()).hexdigest(),
                'width': SIZE[0], 'height': SIZE[1], 'templateVersion': 2 if photo else 1,
                'rendererSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'originalComposition': True, 'externalPhotographs': bool(photo),
                'limitations': ['Draft only; target publication, board, caption, duplicate registry and rendered layout require review.']}
    if photo:
        manifest['photo'] = {k: photo[k] for k in ('id', 'author', 'source_page', 'license', 'license_url')}
    (target / 'draft.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    for name in ('dmsans-OFL.txt', 'playfairdisplay-OFL.txt'):
        (target / name).write_bytes((HERE / 'assets' / name).read_bytes())
    (target / 'credits.txt').write_text(credits(photo))
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--articles', type=Path, required=True)
    parser.add_argument('--slug', required=True)
    parser.add_argument('--variant', choices=VARIANTS, default='a')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    matches = [a for a in json.loads(args.articles.read_text()) if a['slug'] == args.slug]
    if len(matches) != 1:
        raise ValueError('article_missing_or_ambiguous')
    print(render(matches[0], args.output, variant=args.variant))
