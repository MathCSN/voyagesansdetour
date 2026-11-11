"""Bounded draft intake. No RSS edits, approvals or social provider calls."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil

from pin_draft import HERE, VARIANTS, pin_id, render

STOP = dt.datetime(2027, 9, 14, 21, 59, 59, tzinfo=dt.timezone.utc)
MAX_PER_RUN = 4          # drafts drawn or redrawn by one daily run


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def renderer_sha256():
    return hashlib.sha256((HERE / 'pin_draft.py').read_bytes()).hexdigest()


def variant_of(manifest):
    return manifest.get('variant') if manifest.get('variant') in VARIANTS else 'a'


def slug_of(manifest):
    """'pin-kyoto-b' is variant "b" of the guide 'kyoto'; a draft without variant is the guide's first Pin."""
    variant, name = variant_of(manifest), manifest['id'].removeprefix('pin-')
    return name if variant == 'a' else name.removesuffix('-' + variant)


def draw(renderer, article, output, variant):
    # The first Pin keeps the historical call; the other variants name themselves.
    return renderer(article, output) if variant == 'a' else renderer(article, output, variant=variant)


def intake(articles, reserved, output, now, renderer=render, admitted=()):
    """One draft per call: a stale draft redrawn first, else the next missing Pin (every guide's first Pin, then its variants)."""
    if now.tzinfo is None:
        raise ValueError('timezone_required')
    if now >= STOP:
        return {'status': 'period_ended', 'created': 0}
    slugs = [a['slug'] for a in articles]
    if len(slugs) != len(set(slugs)):
        raise ValueError('duplicate_article')
    output = Path(output)
    if output.is_symlink():
        raise ValueError('output_symlink')
    # A reserved guide already has its first Pin in the historical feed; its variants are new pictures.
    known, by_slug, stale = {pin_id(slug) for slug in reserved}, {a['slug']: a for a in articles}, []
    if output.exists():
        for folder in output.iterdir():
            if folder.name.startswith('.') and folder.name.endswith('.previous') and folder.is_dir() and not folder.is_symlink():
                # Left by a redraw that was interrupted: put the old draft back if its place is free, drop the copy otherwise.
                original = folder.with_name(folder.name[1:].removesuffix('.previous'))
                if original.exists():
                    shutil.rmtree(folder)
                else:
                    folder.rename(original)
        for folder in output.iterdir():
            if folder.is_symlink() or not folder.is_dir():
                raise ValueError('invalid_draft_directory')
            manifest = json.loads((folder / 'draft.json').read_text())
            if manifest['status'] != 'draft_requires_review' or manifest['publicationApproved'] is not False:
                raise ValueError('unexpected_draft_state')
            slug, variant = slug_of(manifest), variant_of(manifest)
            if (folder.name != pin_id(slug, variant) or manifest['id'] != folder.name or not manifest['targetUrl'].startswith('https://voyagesansdetour.fr/')
                    or not manifest['targetUrl'].endswith('/' + slug + '/')):
                raise ValueError('draft_identity')
            if (folder / 'pin.jpg').is_symlink() or hashlib.sha256((folder / 'pin.jpg').read_bytes()).hexdigest() != manifest['imageSha256']:
                raise ValueError('draft_image_changed')
            known.add(manifest['id'])
            # A guide refreshed or a template changed after the draft would block promotion forever: redraw it.
            outdated = slug in by_slug and (manifest['articleSha256'] != digest(by_slug[slug]) or manifest.get('rendererSha256') != renderer_sha256())
            if manifest['id'] not in admitted and outdated:
                stale.append((folder, slug, variant))
    for folder, slug, variant in sorted(stale):
        # Keep the old draft aside until the new one renders; a guide that no longer renders stays stale and is skipped.
        backup = folder.with_name('.' + folder.name + '.previous')
        folder.rename(backup)
        try:
            target = draw(renderer, by_slug[slug], output, variant)
        except (ValueError, OSError, KeyError):
            if folder.exists():
                shutil.rmtree(folder)
            backup.rename(folder)
            continue
        shutil.rmtree(backup)
        return {'status': 'draft_refreshed_not_published', 'created': 1, 'id': target.name, 'publicationAttempted': False}
    held = []
    # 'pin-kyoto-b' must mean one thing: a guide whose slug ends like a variant of another guide keeps its first Pin only.
    ambiguous = {slug for slug in by_slug for variant in VARIANTS[1:] if slug.endswith('-' + variant) and slug.removesuffix('-' + variant) in by_slug}
    for variant in VARIANTS:
        for article in sorted(articles, key=lambda a: (a.get('publishedOn', ''), a['slug']), reverse=True):
            # A variant needs another photo of the guide: a guide without cover has its single typographic Pin.
            if pin_id(article['slug'], variant) in known or (variant != 'a' and not article.get('cover')):
                continue
            if variant != 'a' and (article['slug'] in ambiguous or pin_id(article['slug'], variant).removeprefix('pin-') in by_slug):
                continue
            # The public catalogue is the input; a queue/candidate is never selected.
            # A guide that cannot be drawn is held; it must not stop the drafts behind it.
            try:
                target = draw(renderer, article, output, variant)
            except (ValueError, OSError, KeyError) as error:
                held.append({'id': pin_id(article['slug'], variant), 'reason': str(error)})
                continue
            return {'status': 'draft_created_not_published', 'created': 1, 'id': target.name, 'publicationAttempted': False, 'held': held}
    return {'status': 'no_new_article', 'created': 0, 'publicationAttempted': False, 'held': held}


def intake_many(articles, reserved, output, now, renderer=render, admitted=(), limit=MAX_PER_RUN):
    """Up to `limit` drafts in one run: a new template or a batch of guides is absorbed in days, not months."""
    results = []
    for _ in range(limit):
        result = intake(articles, reserved, output, now, renderer, admitted)
        results.append(result)
        if not result.get('created'):
            break
    return {'status': results[-1]['status'], 'created': sum(r.get('created', 0) for r in results), 'ids': [r['id'] for r in results if r.get('id')],
            'publicationAttempted': False, 'held': results[-1].get('held', [])}


if __name__ == '__main__':
    articles = json.loads((HERE.parents[1] / 'site-src/articles.json').read_text())
    config = json.loads((HERE / 'pin-reservations.json').read_text())
    if config.get('schemaVersion') != 1:
        raise ValueError('reservation_schema')
    admitted = [i['id'] for i in json.loads((HERE / 'pin-admissions.json').read_text())['items']]
    print(json.dumps(intake_many(articles, config['reservedSlugs'], HERE / 'pin-drafts', dt.datetime.now(dt.timezone.utc), admitted=admitted)))
