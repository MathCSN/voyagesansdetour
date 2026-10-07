#!/usr/bin/env python3
"""Admit only near-date, source-stable editorial candidates.

This is deliberately conservative: it does not generate text, follow links
from source pages, or rewrite an approval. A candidate is copied into the
normal reviewed queue only when every declared HTTPS source returns HTML whose
normalized bytes have the exact SHA-256 recorded in the candidate manifest.
"""
import argparse
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

import editorial_queue as queue

ROOT = Path(__file__).resolve().parent
UTC = dt.timezone.utc
LOOKAHEAD = dt.timedelta(hours=72)
MAX_SOURCE_BYTES = 4 * 1024 * 1024
HASH = re.compile(r'^[0-9a-f]{64}$')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now_utc(value=None):
    value = value or dt.datetime.now(UTC)
    return value.astimezone(UTC).replace(microsecond=0)


def read_json(path):
    require(path.is_file() and not path.is_symlink(), f'Fichier candidat absent: {path.name}')
    require(path.stat().st_size <= 2 * 1024 * 1024, 'Candidat trop volumineux.')
    return json.loads(path.read_text(encoding='utf-8'))


class _VisibleText(HTMLParser):
    """Extract visible source text while ignoring scripts and page chrome bytes."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {'script', 'style', 'noscript', 'svg', 'template'}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag.lower() in {'script', 'style', 'noscript', 'svg', 'template'} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def normalized_hash(data):
    parser = _VisibleText()
    parser.feed(data.decode('utf-8', errors='replace'))
    text = re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()
    require(text, 'Source HTML sans texte visible.')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def source_fingerprint(url, opener=None):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password,
            'Source HTTPS invalide.')
    opener = opener or urllib.request.build_opener()
    request = urllib.request.Request(url, headers={
        'Accept': 'text/html,application/xhtml+xml',
        'Cache-Control': 'no-cache',
        'User-Agent': 'VoyageSansDetour-editorial-recheck/1',
    })
    with opener.open(request, timeout=15) as response:
        require(response.status == 200, f'Source non disponible ({response.status}).')
        content_type = (response.headers.get('content-type') or '').lower()
        require('text/html' in content_type or 'application/xhtml+xml' in content_type,
                'La source ne renvoie pas du HTML.')
        data = response.read(MAX_SOURCE_BYTES + 1)
    require(len(data) <= MAX_SOURCE_BYTES, 'Source trop volumineuse.')
    parser = _VisibleText()
    parser.feed(data.decode('utf-8', errors='replace'))
    text = re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()
    require(text, 'Source HTML sans texte visible.')
    return {'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'text': text}


def revalidate_source(entry, fetcher=source_fingerprint):
    observed = fetcher(entry['url'])
    expected = entry['sha256']
    if observed['sha256'] == expected:
        return 'hash'
    anchors = entry.get('requiredText', [])
    folded = observed['text'].casefold()
    require(isinstance(anchors, list) and anchors and
            all(isinstance(anchor, str) and anchor.strip() and anchor.casefold() in folded for anchor in anchors),
            'Source visible text modifiée ou repères absents.')
    return 'anchors'


def validate_candidate(candidate, published_slugs):
    require(isinstance(candidate, dict) and set(candidate) ==
            {'schemaVersion', 'id', 'releaseAt', 'validUntil', 'article', 'sources', 'review'},
            'Champs du candidat invalides.')
    require(candidate['schemaVersion'] == 1, 'Version de candidat inconnue.')
    require(isinstance(candidate['id'], str) and queue.SLUG.fullmatch(candidate['id']), 'ID candidat invalide.')
    release = queue.instant(candidate['releaseAt'])
    expiry = queue.instant(candidate['validUntil'])
    require(release < expiry, 'Fenêtre de candidat invalide.')
    article = candidate['article']
    queue.validate_article(article, published_slugs)
    require(candidate['review'].get('publicationApproved') is False,
            'Un candidat déjà approuvé doit suivre la file normale.')
    require(candidate['review'].get('fabricatedExperience') is False and
            candidate['review'].get('commercialClaims') is False,
            'La politique éditoriale du candidat est incompatible.')
    entries = candidate['sources']
    require(isinstance(entries, list) and entries, 'Manifest de sources absent.')
    urls = set()
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) == {'url', 'sha256', 'requiredText'}, 'Entrée source invalide.')
        url = entry['url']
        parsed = urllib.parse.urlsplit(url)
        require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password,
                'Source HTTPS invalide.')
        require(url not in urls and HASH.fullmatch(entry['sha256']), 'Source dupliquée ou empreinte invalide.')
        require(isinstance(entry['requiredText'], list) and 1 <= len(entry['requiredText']) <= 4 and
                all(isinstance(anchor, str) and 2 <= len(anchor.strip()) <= 120 for anchor in entry['requiredText']),
                'Repères source invalides.')
        urls.add(url)
    article_urls = {source['url'] for source in article['sources']}
    require(urls == article_urls, 'Le manifest ne couvre pas exactement les sources de l’article.')
    return release, expiry


def approval_for(candidate, approved_at):
    draft = {
        'id': candidate['id'],
        'article': candidate['article'],
        'releaseAt': candidate['releaseAt'],
        'validUntil': candidate['validUntil'],
        'approval': {'approvedAt': approved_at.isoformat().replace('+00:00', 'Z')},
    }
    draft['approval']['sha256'] = queue.approval_hash(draft)
    return draft


def intake(root=ROOT, now=None, fetcher=source_fingerprint, output=None):
    now = now_utc(now)
    articles, state = queue.load(root, now)
    published_slugs = {article['slug'] for article in articles}
    known_ids = {draft['id'] for draft in state['drafts']} | {entry['id'] for entry in state['promotions']}
    known_slugs = published_slugs | {draft['article']['slug'] for draft in state['drafts']}
    changed = False
    report = []
    candidates_dir = root / 'editorial-candidates'
    for path in sorted(candidates_dir.glob('*.json')):
        candidate = read_json(path)
        try:
            release, expiry = validate_candidate(candidate, published_slugs)
            if candidate['id'] in known_ids or candidate['article']['slug'] in known_slugs:
                report.append({'id': candidate['id'], 'status': 'already_known'})
                continue
            if release < now:
                report.append({'id': candidate['id'], 'status': 'expired_before_admission'})
                continue
            if release > now + LOOKAHEAD:
                report.append({'id': candidate['id'], 'status': 'outside_window'})
                continue
            observed = []
            blocked = None
            for source in candidate['sources']:
                try:
                    actual = revalidate_source(source, fetcher)
                except Exception as error:
                    blocked = f'source_unavailable:{type(error).__name__}'
                    break
                observed.append({'url': source['url'], 'match': actual})
            proof = {
                'schemaVersion': 1,
                'candidateId': candidate['id'],
                'observedAt': now.isoformat().replace('+00:00', 'Z'),
                'sources': [{'url': item['url'], 'expectedSha256': next(s['sha256'] for s in candidate['sources'] if s['url'] == item['url']),
                             'match': item['match']} for item in observed],
            }
            if blocked:
                report.append({'id': candidate['id'], 'status': 'blocked', 'reason': blocked})
                continue
            draft = approval_for(candidate, now)
            # Validate the full queue before writing a single byte.
            state['drafts'].append(draft)
            queue.validate(articles, state, now)
            proof_dir = root / 'editorial-revalidation'
            proof_dir.mkdir(parents=True, exist_ok=True)
            proof_path = proof_dir / f"{candidate['id']}.json"
            proof_text = json.dumps(proof, ensure_ascii=False, indent=2) + '\n'
            if proof_path.exists():
                require(proof_path.read_text(encoding='utf-8') == proof_text, 'Preuve de revalidation immuable contradictoire.')
            else:
                proof_path.write_text(proof_text, encoding='utf-8')
            known_ids.add(candidate['id'])
            known_slugs.add(candidate['article']['slug'])
            changed = True
            report.append({'id': candidate['id'], 'status': 'admitted',
                           'releaseAt': candidate['releaseAt'], 'validUntil': candidate['validUntil'],
                           'sourceCount': len(observed), 'sourceMatches': sorted({item['match'] for item in observed}),
                           'approvedAt': draft['approval']['approvedAt']})
        except Exception as error:
            report.append({'id': candidate.get('id', path.name), 'status': 'invalid_candidate',
                           'reason': type(error).__name__})
    if changed:
        temporary = root / 'editorial-queue.json.tmp'
        require(not temporary.exists() and not temporary.is_symlink(), 'Fichier temporaire de file déjà présent.')
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(root / 'editorial-queue.json')
    result = {'schemaVersion': 1, 'changed': changed, 'observedAt': now.isoformat().replace('+00:00', 'Z'), 'candidates': report}
    if output:
        Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = intake(args.root, output=args.report)
    for candidate in result['candidates']:
        print(f"{candidate['id']}: {candidate['status']}" +
              (f" ({candidate['reason']})" if 'reason' in candidate else ''))
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a', encoding='utf-8') as handle:
            handle.write(f"changed={str(result['changed']).lower()}\n")


if __name__ == '__main__':
    main()
