"""Admit qualified Pins to the RSS feed of their board: fresh pictures, search-style titles, useful descriptions."""
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import urllib.request

from PIL import Image

import destinations
from pin_draft import FREE_LICENSES, HERE, ORIGIN, TITLE_MAX, article_path, pin_id, pin_title
from pin_intake import STOP, digest, renderer_sha256, slug_of, variant_of

FILES = ('pin.jpg', 'credits.txt', 'dmsans-OFL.txt', 'playfairdisplay-OFL.txt')
# Boards are declared in site-src/pinterest-additions.json: each feed lists its "countries";
# a feed listing "*" takes every country without a board of its own (inspirations-voyage.xml).
# A feed without the field serves the country in its name (preparer-<country>.xml).
COMMON = '*'
DEFAULT_FEEDS = ({'file': 'preparer-portugal.xml'}, {'file': 'preparer-espagne.xml'}, {'file': 'preparer-italie.xml'},
                 {'file': 'inspirations-voyage.xml', 'countries': [COMMON]})
# A young account does best with three to five fresh Pins a week, a guide's new pictures spread over two to four weeks (Tailwind, 2026).
CADENCE = dt.timedelta(days=3)       # one fresh Pin per board every three days
GUIDE_GAP = dt.timedelta(days=14)    # two Pins of the same guide are two weeks apart
MAX_PER_RUN = 1                      # Pins admitted by one daily run, all boards together
DESCRIPTION_MAX = 500
# A variant links to the same guide with its own campaign tag: Pinterest sees a distinct link, the audience report says which picture brought the visit.
CAMPAIGN = 'utm_source=pinterest&utm_medium=social&utm_content='


def require(value, code):
    if not value:
        raise ValueError(code)


def feed_countries(feed):
    countries = feed.get('countries')
    if countries is None:
        countries = [feed['file'].removeprefix('preparer-').removesuffix('.xml')]
    return countries


def feed_for(country, feeds):
    """The board's RSS file for a country: its own, else the common one, else None (the Pin waits)."""
    own = [f['file'] for f in feeds if country in feed_countries(f)]
    if own:
        return own[0]
    common = [f['file'] for f in feeds if COMMON in feed_countries(f)]
    return common[0] if common else None


def on_hold(last, board, now):
    # One Pin per board per cadence; a single date (older callers) applies to every board.
    previous = last.get(board) if isinstance(last, dict) else last
    return bool(previous) and now < previous + CADENCE


def select(articles, drafts, known, last, now, skip=frozenset(), feeds=DEFAULT_FEEDS, guide_last=None):
    require(now.tzinfo is not None, 'timezone_required')
    if now >= STOP:
        return None, 'period_ended'
    by_slug = {a['slug']: a for a in articles}
    require(len(by_slug) == len(articles), 'duplicate_article')
    waiting, candidates = False, []
    for folder in sorted(Path(drafts).glob('pin-*')):
        require(folder.is_dir() and not folder.is_symlink(), 'invalid_draft_folder')
        require(not (folder / 'draft.json').is_symlink(), 'manifest_symlink')
        candidates.append((folder, json.loads((folder / 'draft.json').read_text())))
    # Every guide's first Pin before any second one: a new guide never waits behind an old guide's variants.
    for folder, item in sorted(candidates, key=lambda pair: (variant_of(pair[1]), pair[0].name)):
        identity, variant, slug = item['id'], variant_of(item), slug_of(item)
        if identity in known or identity in skip:
            continue
        article = by_slug.get(slug)
        board = feed_for(article.get('country', 'portugal'), feeds) if article else None
        if not board:
            continue
        if on_hold(last, board, now) or ((guide_last or {}).get(slug) and now < guide_last[slug] + GUIDE_GAP):
            waiting = True
            continue
        require(folder.name == identity and identity == pin_id(article['slug'], variant), 'draft_identity')
        # A guide refreshed or a template changed after the draft is redrawn by pin_intake; never promote the old one.
        if item['articleSha256'] != digest(article) or item.get('rendererSha256') != renderer_sha256() or item['targetUrl'] != ORIGIN + article_path(article):
            continue
        headline = item.get('pinTitle') or item['title']
        require(item['title'] == article['title'] and headline == pin_title(article, variant) and 1 <= len(headline) <= TITLE_MAX, 'title_changed_or_too_long')
        require(item['status'] == 'draft_requires_review' and item['publicationApproved'] is False, 'draft_state')
        require(item.get('templateVersion') in (1, 2), 'unqualified_renderer')
        # Version 2 carries one of the guide's photos, accepted only with a free licence recorded in the draft.
        photo_ok = item.get('templateVersion') == 2 and item.get('externalPhotographs') is True and (item.get('photo') or {}).get('license') in FREE_LICENSES
        require(item.get('originalComposition') is True and (item.get('externalPhotographs') is False or photo_ok), 'unqualified_assets')
        for name in FILES:
            require((folder / name).is_file() and not (folder / name).is_symlink(), 'missing_or_symlink_file')
        require(hashlib.sha256((folder / 'pin.jpg').read_bytes()).hexdigest() == item['imageSha256'], 'image_changed')
        with Image.open(folder / 'pin.jpg') as image:
            require(image.format == 'JPEG' and image.size == (1000, 1500), 'image_format')
            image.verify()
        for name in FILES[2:]:
            require((folder / name).read_bytes() == (HERE / 'assets' / name).read_bytes(), 'license_changed')
        return (folder, item, article), 'eligible'
    return None, 'cadence_hold' if waiting else 'no_eligible_new_draft'


def describe(article, photo, identity, site):
    """What Pinterest indexes: the guide's own summary line with its figures, an invitation to save, one credit line."""
    trip = destinations.preposition(destinations.country_slug(article), destinations.load(site))
    origin = 'Photo : ' + photo['author'] + ' — ' + photo['license'] + '.' if photo else 'Composition typographique originale Voyage Sans Détour, assistée par IA.'
    closing = '📌 Enregistrez ce guide pour préparer votre voyage ' + trip + '. ' + origin + ' Crédits : ' + ORIGIN + '/social-media/production/' + identity + '/credits.txt'
    summary = ' '.join(str(article.get('description') or '').split())
    room = DESCRIPTION_MAX - len(closing) - 1
    if len(summary) > room:
        # Whole sentences only; a summary that cannot be shortened cleanly is left out rather than cut mid-word.
        sentences, summary = re.split(r'(?<=[.!?])\s+', summary), ''
        for sentence in sentences:
            if len((summary + ' ' + sentence).strip()) > room:
                break
            summary = (summary + ' ' + sentence).strip()
    return (summary + ' ' + closing).strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('public_target_redirect')


def verify_target(url, title):
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=20) as response:
        require(response.status == 200, 'public_target_unavailable')
        raw = response.read(2_000_001)
    require(len(raw) <= 2_000_000, 'public_target_too_large')
    text = html.unescape(raw.decode('utf-8'))
    require(title in text, 'public_title_not_found')
    return hashlib.sha256(raw).hexdigest()


def run(root=HERE.parents[1], now=None, fetcher=verify_target):
    root = Path(root)
    now = now or dt.datetime.now(dt.timezone.utc)
    production, site = root / '.github/vsd-production', root / 'site-src'
    ledger_path = production / 'pin-admissions.json'
    ledger = json.loads(ledger_path.read_text())
    config = json.loads((site / 'pinterest-additions.json').read_text())
    media = json.loads((site / 'public-media.json').read_text())
    legacy = json.loads((site / 'pinterest-rss.json').read_text())['items']
    known = {i['id'] for f in config['feeds'] for i in f['items']} | {i['id'] for i in legacy}
    articles = json.loads((site / 'articles.json').read_text())
    feeds, held, last, guide_last = config['feeds'], [], {}, {}
    slug_by_id = {pin_id(a['slug'], variant): a['slug'] for a in articles for variant in ('a', 'b', 'c')}
    country_of = {a['slug']: a.get('country', 'portugal') for a in articles}
    for entry in ledger['items']:
        slug = slug_by_id.get(entry['id'])
        board = feed_for(country_of.get(slug, 'portugal'), feeds)
        admitted = dt.datetime.fromisoformat(entry['admittedAt'].replace('Z', '+00:00'))
        if board and (board not in last or admitted > last[board]):
            last[board] = admitted
        if slug and (slug not in guide_last or admitted > guide_last[slug]):
            guide_last[slug] = admitted
    while True:
        selected, status = select(articles, production / 'pin-drafts', known, last, now, frozenset(h['id'] for h in held), feeds, guide_last)
        if not selected:
            return {'status': status, 'changed': False, 'publicationConfirmed': False, 'held': held}
        folder, item, article = selected
        identity = item['id']
        # An unreachable guide page holds this Pin only; the next draft can still go out.
        try:
            public_hash = fetcher(item['targetUrl'], item['title'])
            break
        except (OSError, ValueError):
            held.append({'id': identity, 'reason': 'public_target_unavailable'})
    require(not any(x['contentId'] == identity for x in media['items']), 'media_already_exists')
    feed = [f for f in feeds if f['file'] == feed_for(article.get('country', 'portugal'), feeds)]
    require(len(feed) == 1, 'connected_feed_missing')
    route, variant = article_path(article), variant_of(item)
    if variant == 'a':
        # A guide has one first Pin, here or in the historical feed; its variants are told apart by their campaign tag.
        require(not any(p['linkPath'] == route and not p.get('linkQuery') for f in config['feeds'] for p in f['items']), 'route_already_admitted')
        require(not any(p['link_path'] == route for p in legacy), 'route_already_in_legacy_feed')
    destination = site / 'social-media/production' / identity
    require(not destination.exists(), 'destination_exists')
    files = [{'name': name, 'bytes': (folder / name).stat().st_size, 'sha256': hashlib.sha256((folder / name).read_bytes()).hexdigest()} for name in FILES]
    photo = item.get('photo') if item.get('externalPhotographs') else None
    description = describe(article, photo, identity, site)
    require(len(description) <= DESCRIPTION_MAX, 'caption_too_long')
    pin = {'id': identity, 'title': item.get('pinTitle') or item['title'], 'description': description, 'linkPath': route, 'mediaId': identity,
           'width': 1000, 'height': 1500}
    if variant != 'a':
        pin['linkQuery'] = CAMPAIGN + identity
    feed[0]['items'].append(pin)
    media['items'].append({'contentId': identity, 'kind': 'pin', 'approved': True, 'files': files})
    ledger['items'].append({'id': identity, 'admittedAt': now.isoformat(), 'articleSha256': item['articleSha256'], 'imageSha256': item['imageSha256'],
                            'publicHtmlSha256': public_hash, 'method': 'published_guide_photo_template_v3', 'publicationConfirmed': False})
    destination.mkdir(parents=True)
    for name in FILES:
        shutil.copyfile(folder / name, destination / name)
    for path, value in [(site / 'pinterest-additions.json', config), (site / 'public-media.json', media), (ledger_path, ledger)]:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return {'status': 'admitted_to_feed_not_published', 'changed': True, 'id': identity, 'publicationConfirmed': False, 'held': held}


def switched_off(root):
    """Admission waits when cadence.json says so ("pins": {"enabled": false}); drafts are still drawn, none joins a feed."""
    path = Path(root) / '.github/vsd-production/cadence.json'
    return path.is_file() and json.loads(path.read_text()).get('pins', {}).get('enabled') is False


def run_many(root=HERE.parents[1], now=None, fetcher=verify_target, limit=MAX_PER_RUN):
    """Up to `limit` Pins in one run, each on a different board (the board cadence sees the Pin just admitted)."""
    if switched_off(root):
        return {'status': 'admission_switched_off', 'changed': False, 'ids': [], 'publicationConfirmed': False, 'held': []}
    results = []
    for _ in range(limit):
        results.append(run(root, now, fetcher))
        if not results[-1]['changed']:
            break
    admitted = [r['id'] for r in results if r['changed']]
    return {'status': 'admitted_to_feed_not_published' if admitted else results[-1]['status'], 'changed': bool(admitted), 'ids': admitted,
            'publicationConfirmed': False, 'held': results[-1]['held']}


if __name__ == '__main__':
    print(json.dumps(run_many()))
