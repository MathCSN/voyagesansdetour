#!/usr/bin/env python3
"""Release reviewed articles only. Standard library; never generates editorial text."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
ORIGIN = 'https://voyagesansdetour.fr'
PARIS = ZoneInfo('Europe/Paris')
UTC = dt.timezone.utc
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')
INSTANT = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})\Z')
ARTICLE_KEYS = {'slug', 'title', 'shortTitle', 'destination', 'category', 'description',
                'readMinutes', 'summary', 'sections', 'faq', 'sources', 'related', 'sourcesCheckedOn'}
DRAFT_KEYS = {'id', 'article', 'releaseAt', 'validUntil', 'approval'}
PROMOTION_KEYS = {'id', 'slug', 'approvalSha256', 'articleSha256', 'releaseAt', 'validUntil',
                  'approvedAt', 'promotedAt', 'receipt'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def instant(value):
    require(isinstance(value, str) and INSTANT.fullmatch(value), 'Date avec fuseau explicite requise.')
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(UTC)
    except ValueError as error:
        raise ValueError('Date de calendrier invalide.') from error


def iso(value):
    return value.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def today(value):
    return value.astimezone(PARIS).date().isoformat()


def read_json(path):
    require(path.is_file() and not path.is_symlink(), 'Fichier éditorial absent ou lien symbolique.')
    require(path.stat().st_size <= 2 * 1024 * 1024, 'Fichier éditorial trop volumineux.')
    return json.loads(path.read_text())


def write_json(path, data):
    # Both files are committed together by the workflow; a partial local write
    # fails validation instead of permitting an unrecorded release.
    temporary = path.with_name(path.name + '.tmp')
    require(not temporary.exists() and not temporary.is_symlink(), 'Fichier temporaire déjà présent.')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def approval_hash(draft):
    """The approval covers the content AND its release window/approval instant."""
    return digest({key: draft[key] for key in ('id', 'article', 'releaseAt', 'validUntil')} |
                  {'approvedAt': draft['approval']['approvedAt']})


def validate_article(article, published_slugs):
    require(isinstance(article, dict) and set(article) == ARTICLE_KEYS, 'Champs du brouillon invalides.')
    require(isinstance(article['slug'], str) and SLUG.fullmatch(article['slug']), 'Slug invalide.')
    for key in ('title', 'shortTitle', 'destination', 'category', 'description', 'summary'):
        require(isinstance(article[key], str) and 0 < len(article[key]) <= 3000, 'Texte du brouillon invalide.')
    require(type(article['readMinutes']) is int and 1 <= article['readMinutes'] <= 60, 'Durée de lecture invalide.')
    checked = dt.date.fromisoformat(article['sourcesCheckedOn'])
    require(checked.isoformat() == article['sourcesCheckedOn'], 'Date de contrôle invalide.')
    require(isinstance(article['sections'], list) and 1 <= len(article['sections']) <= 30, 'Sections invalides.')
    ids = set()
    for section in article['sections']:
        require(isinstance(section, dict) and {'id', 'title', 'paragraphs'} <= set(section) <=
                {'id', 'title', 'paragraphs', 'bullets', 'table'}, 'Section invalide.')
        require(isinstance(section['id'], str) and SLUG.fullmatch(section['id']) and section['id'] not in ids,
                'Identifiant de section invalide ou dupliqué.')
        ids.add(section['id'])
        require(isinstance(section['title'], str) and section['title'], 'Titre de section absent.')
        for key in ('paragraphs', 'bullets'):
            if key in section:
                require(isinstance(section[key], list) and section[key] and
                        all(isinstance(p, str) and p for p in section[key]), 'Paragraphes invalides.')
        if 'table' in section:
            table = section['table']
            require(isinstance(table, dict) and set(table) == {'headers', 'rows'} and
                    isinstance(table['headers'], list) and table['headers'] and
                    all(isinstance(v, str) for v in table['headers']) and isinstance(table['rows'], list) and
                    all(isinstance(row, list) and len(row) == len(table['headers']) and
                        all(isinstance(v, str) for v in row) for row in table['rows']), 'Tableau invalide.')
    require(isinstance(article['faq'], list) and all(isinstance(q, dict) and set(q) == {'question', 'answer'} and
            all(isinstance(v, str) and v for v in q.values()) for q in article['faq']), 'FAQ invalide.')
    require(isinstance(article['sources'], list) and article['sources'], 'Sources absentes.')
    for source in article['sources']:
        require(isinstance(source, dict) and set(source) == {'label', 'url'}, 'Source invalide.')
        require(isinstance(source['label'], str) and source['label'] and isinstance(source['url'], str), 'Source invalide.')
        url = urllib.parse.urlsplit(source['url'])
        require(url.scheme == 'https' and url.hostname and not url.username and not url.password, 'Source HTTPS requise.')
    require(isinstance(article['related'], list) and len(set(article['related'])) == len(article['related']) and
            all(slug in published_slugs for slug in article['related']), 'Lien lié non encore publié ou dupliqué.')


def validate(articles, queue, now):
    require(isinstance(articles, list) and articles, 'Catalogue publié absent.')
    slugs = [a['slug'] for a in articles]
    require(len(set(slugs)) == len(slugs), 'Slug publié dupliqué.')
    require(isinstance(queue, dict) and set(queue) == {'schemaVersion', 'drafts', 'promotions'} and
            type(queue['schemaVersion']) is int and queue['schemaVersion'] == 1, 'Version/champs de file invalides.')
    require(isinstance(queue['drafts'], list) and len(queue['drafts']) <= 52 and
            isinstance(queue['promotions'], list) and len(queue['promotions']) <= 1024, 'Capacité de file dépassée.')
    ids, draft_slugs, promoted_slugs = set(), set(), set()
    for draft in queue['drafts']:
        require(isinstance(draft, dict) and set(draft) == DRAFT_KEYS, 'Champs de brouillon invalides.')
        require(isinstance(draft['id'], str) and SLUG.fullmatch(draft['id']) and draft['id'] not in ids, 'ID de sortie dupliqué/invalide.')
        ids.add(draft['id'])
        validate_article(draft['article'], set(slugs))
        slug = draft['article']['slug']
        require(slug not in slugs and slug not in draft_slugs, 'Un brouillon ne peut remplacer un guide existant.')
        draft_slugs.add(slug)
        approval = draft['approval']
        require(isinstance(approval, dict) and set(approval) == {'approvedAt', 'sha256'} and
                isinstance(approval['sha256'], str) and HASH.fullmatch(approval['sha256']), 'Approbation absente.')
        approved, release, expiry = map(instant, (approval['approvedAt'], draft['releaseAt'], draft['validUntil']))
        require(approved <= now and approved <= release < expiry and
                draft['article']['sourcesCheckedOn'] <= today(approved), 'Fenêtre éditoriale invalide.')
        require(approval['sha256'] == approval_hash(draft), 'Brouillon ou fenêtre modifié après approbation.')
    for entry in queue['promotions']:
        require(isinstance(entry, dict) and set(entry) == PROMOTION_KEYS, 'Journal de promotion invalide.')
        require(entry['id'] not in ids and entry['slug'] in slugs and entry['slug'] not in promoted_slugs,
                'Promotion dupliquée ou guide promu retiré du catalogue.')
        ids.add(entry['id']); promoted_slugs.add(entry['slug'])
        require(all(isinstance(entry[k], str) and HASH.fullmatch(entry[k]) for k in ('approvalSha256', 'articleSha256')),
                'Empreinte de promotion invalide.')
        approved, release, promoted, expiry = map(instant, (entry['approvedAt'], entry['releaseAt'], entry['promotedAt'], entry['validUntil']))
        require(approved <= release <= promoted < expiry and promoted <= now, 'Chronologie de promotion invalide.')
        if entry['receipt'] is None:
            article = next(a for a in articles if a['slug'] == entry['slug'])
            require(digest(article) == entry['articleSha256'], 'Guide modifié avant confirmation de sortie.')
        else:
            receipt = entry['receipt']
            require(isinstance(receipt, dict) and set(receipt) == {'verifiedAt', 'url', 'htmlSha256'} and
                    receipt['url'] == ORIGIN + '/portugal/' + entry['slug'] + '/' and
                    isinstance(receipt['htmlSha256'], str) and HASH.fullmatch(receipt['htmlSha256']), 'Preuve de sortie invalide.')
            require(promoted <= instant(receipt['verifiedAt']) < expiry and instant(receipt['verifiedAt']) <= now,
                    'Preuve de sortie hors fenêtre contrôlée.')


def load(root=ROOT, now=None):
    now = now or dt.datetime.now(UTC)
    articles, queue = read_json(root / 'articles.json'), read_json(root / 'editorial-queue.json')
    validate(articles, queue, now)
    return articles, queue


def check_pending(queue, now, margin=0):
    for entry in queue['promotions']:
        if entry['receipt'] is None:
            require(now + dt.timedelta(seconds=margin) < instant(entry['validUntil']),
                    'Sortie non confirmée : contrôle expiré ou marge insuffisante ; site précédent conservé.')
            require(today(instant(entry['promotedAt'])) == today(now) == today(now + dt.timedelta(seconds=margin)),
                    'Sortie non confirmée sur un autre jour : réconcilier avant tout nouveau déploiement.')


def published_articles(root=ROOT, now=None):
    """Generator reads only the durable catalogue; future drafts never leak."""
    now = now or dt.datetime.now(UTC)
    articles, queue = load(root, now)
    check_pending(queue, now)
    return articles


def promote(root=ROOT, now=None):
    now = now or dt.datetime.now(UTC)
    articles, queue = load(root, now)
    check_pending(queue, now, 900)
    due = sorted((d for d in queue['drafts'] if instant(d['releaseAt']) <= now), key=lambda d: (instant(d['releaseAt']), d['id']))
    # An expired approval is never silently extended or interpreted as a skip.
    for draft in due:
        require(now + dt.timedelta(seconds=900) < instant(draft['validUntil']), 'Brouillon arrivé à échéance mais contrôle expiré ou marge insuffisante.')
    latest = max(dt.datetime.combine(dt.date.fromisoformat(a.get('publishedOn', '2026-09-14')), dt.time(), PARIS).astimezone(UTC)
                 for a in articles)
    if queue['promotions']:
        latest = max(latest, max(instant(p['promotedAt']) for p in queue['promotions']))
    if not due or any(p['receipt'] is None for p in queue['promotions']) or now < latest + dt.timedelta(hours=336):
        return False
    draft = due[0]
    article = dict(draft['article'], publishedOn=today(now), updatedOn=today(now))
    entry = dict(id=draft['id'], slug=article['slug'], approvalSha256=draft['approval']['sha256'],
                 articleSha256=digest(article), releaseAt=draft['releaseAt'], validUntil=draft['validUntil'],
                 approvedAt=draft['approval']['approvedAt'], promotedAt=iso(now), receipt=None)
    articles.append(article); queue['drafts'].remove(draft); queue['promotions'].append(entry)
    validate(articles, queue, now)
    write_json(root / 'articles.json', articles)
    write_json(root / 'editorial-queue.json', queue)
    return True


def manifest(root, output, now):
    articles, queue = load(root, now)
    check_pending(queue, now, 900)
    entries = []
    for entry in queue['promotions']:
        if entry['receipt'] is not None:
            continue
        path = output / 'portugal' / entry['slug'] / 'index.html'
        require(path.is_file() and not path.is_symlink(), 'Page promue absente du build.')
        entries.append({'id': entry['id'], 'articleSha256': entry['articleSha256'],
                        'htmlSha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'schemaVersion': 1, 'articlesSha256': digest(articles), 'queueSha256': digest(queue), 'entries': entries}


def check_manifest(root, expected, now, margin=900):
    articles, queue = load(root, now)
    require(isinstance(expected, dict) and set(expected) == {'schemaVersion', 'articlesSha256', 'queueSha256', 'entries'} and
            expected['schemaVersion'] == 1 and expected['articlesSha256'] == digest(articles) and
            expected['queueSha256'] == digest(queue), 'Build et sources de sortie différents.')
    pending = {p['id']: p for p in queue['promotions'] if p['receipt'] is None}
    require(isinstance(expected['entries'], list) and len(expected['entries']) == len(pending) and
            {e.get('id') for e in expected['entries']} == set(pending), 'Manifeste de sortie incomplet.')
    for entry in expected['entries']:
        require(set(entry) == {'id', 'articleSha256', 'htmlSha256'} and
                entry['articleSha256'] == pending[entry['id']]['articleSha256'] and
                isinstance(entry['htmlSha256'], str) and HASH.fullmatch(entry['htmlSha256']), 'Empreinte de build invalide.')
    check_pending(queue, now, margin)
    return articles, queue


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_public(url):
    request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'VoyageSansDetour-ReleaseCheck/1'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
        require(response.status == 200 and response.geturl() == url and
                response.headers.get_content_type() == 'text/html', 'Page publique non confirmée.')
        data = response.read(2 * 1024 * 1024 + 1)
        require(len(data) <= 2 * 1024 * 1024, 'Réponse publique trop volumineuse.')
        return data


def confirm(root, expected, now=None, fetcher=fetch_public):
    fixed_clock = now is not None
    now = now or dt.datetime.now(UTC)
    _, queue = check_manifest(root, expected, now, 0)
    by_id = {p['id']: p for p in queue['promotions']}
    for item in expected['entries']:
        entry = by_id[item['id']]
        url = ORIGIN + '/portugal/' + entry['slug'] + '/'
        require(hashlib.sha256(fetcher(url)).hexdigest() == item['htmlSha256'], 'HTML public différent du build : aucune confirmation.')
        checked = now if fixed_clock else dt.datetime.now(UTC)
        require(checked < instant(entry['validUntil']), 'Contrôle expiré avant preuve publique.')
        entry['receipt'] = {'verifiedAt': iso(checked), 'url': url, 'htmlSha256': item['htmlSha256']}
    if expected['entries']:
        write_json(root / 'editorial-queue.json', queue)
    return bool(expected['entries'])


def preserve_remote(local_root, remote_root, now=None):
    """A stale Mac checkout must not erase cloud promotions/receipts."""
    now = now or dt.datetime.now(UTC)
    local_articles, local = load(local_root, now)
    if not (remote_root / 'editorial-queue.json').exists():
        return
    _, remote = load(remote_root, now)
    by_id = {p['id']: p for p in local['promotions']}
    local_slugs = {a['slug'] for a in local_articles}
    require(all(by_id.get(p['id']) == p and p['slug'] in local_slugs for p in remote['promotions']),
            'Promotions cloud absentes/différentes localement : synchroniser articles.json et editorial-queue.json avant publication.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('validate', 'promote', 'manifest', 'check-window', 'confirm', 'preserve-remote'))
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--site-output', type=Path)
    parser.add_argument('--manifest-json')
    parser.add_argument('--remote-root', type=Path)
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    now = dt.datetime.now(UTC)
    outputs = {}
    if args.command == 'promote':
        outputs['changed'] = 'true' if promote(args.root, now) else 'false'
        _, queue = load(args.root, now)
        outputs['pending'] = 'true' if any(p['receipt'] is None for p in queue['promotions']) else 'false'
    elif args.command == 'manifest':
        outputs['manifest'] = canonical(manifest(args.root, args.site_output or args.root / 'public', now)).decode()
    elif args.command in ('check-window', 'confirm'):
        require(args.manifest_json is not None, 'Manifeste requis.')
        expected = json.loads(args.manifest_json)
        if args.command == 'check-window':
            check_manifest(args.root, expected, now)
        else:
            outputs['changed'] = 'true' if confirm(args.root, expected) else 'false'
    elif args.command == 'preserve-remote':
        require(args.remote_root is not None, 'Source distante requise.')
        preserve_remote(args.root, args.remote_root)
    else:
        load(args.root, now)
    if args.github_output:
        with args.github_output.open('a') as output:
            for key, value in outputs.items():
                output.write(key + '=' + value + '\n')
    else:
        print(json.dumps(outputs or {'status': 'validated'}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(str(error))
