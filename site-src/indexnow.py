#!/usr/bin/env python3
"""Tell IndexNow search engines (Bing, Yandex, Seznam, Naver) which pages changed.

Run after each deployment. Standard library only, no secret: an IndexNow key is public
by design, served at the root of the site so the engines can check who is speaking.
A failed ping never blocks a release; the daily build tries again the next day.

    python indexnow.py            pages whose sitemap date is today or yesterday
    python indexnow.py --all      every page of the sitemap (after a template change)
    python indexnow.py --dry-run  print what would be sent
"""
import argparse
import datetime as dt
import http.client
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ORIGIN = 'https://voyagesansdetour.fr'
HOST = 'voyagesansdetour.fr'
KEY = '941b7cd762a90f96205dab900f573e3e'
KEY_LOCATION = f'{ORIGIN}/{KEY}.txt'
ENDPOINT = 'https://api.indexnow.org/indexnow'
SITEMAP_NAMESPACE = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
RECENT_DAYS = 1
MAX_URLS = 10000
TIMEOUT_SECONDS = 20
USER_AGENT = 'VoyageSansDetour-IndexNow/1'


def changed_urls(sitemap_xml, today, since_days=RECENT_DAYS):
    """URLs of this site dated within the window; since_days=None selects them all."""
    earliest = None if since_days is None else today - dt.timedelta(days=since_days)
    selected = []
    for node in ET.fromstring(sitemap_xml).findall('s:url', SITEMAP_NAMESPACE):
        location = (node.findtext('s:loc', namespaces=SITEMAP_NAMESPACE) or '').strip()
        if not location.startswith(ORIGIN + '/'):
            continue
        if earliest is not None:
            try:
                modified = dt.date.fromisoformat((node.findtext('s:lastmod', namespaces=SITEMAP_NAMESPACE) or '').strip())
            except ValueError:
                continue
            if modified < earliest:
                continue
        selected.append(location)
    return selected[:MAX_URLS]


def fetch(url, opener):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Cache-Control': 'no-cache'})
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode('utf-8')


def submit(urls, opener):
    body = json.dumps({'host': HOST, 'key': KEY, 'keyLocation': KEY_LOCATION, 'urlList': urls}).encode()
    request = urllib.request.Request(ENDPOINT, data=body, method='POST', headers={
        'Content-Type': 'application/json; charset=utf-8', 'User-Agent': USER_AGENT})
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        return response.status


def run(today, since_days=RECENT_DAYS, dry_run=False, opener=None):
    """One ping; every outcome is a report, never an exception."""
    opener = opener or urllib.request.build_opener()
    try:
        # The query string steps over the CDN copy of the sitemap left by the previous release.
        urls = changed_urls(fetch(f'{ORIGIN}/sitemap.xml?indexnow={today.isoformat()}', opener), today, since_days)
        if not urls:
            return {'status': 'nothing_changed', 'urls': 0}
        if dry_run:
            return {'status': 'dry_run', 'urls': len(urls), 'urlList': urls}
        if fetch(f'{KEY_LOCATION}?indexnow={today.isoformat()}', opener).strip() != KEY:
            return {'status': 'key_not_published', 'urls': len(urls)}
        return {'status': 'submitted', 'urls': len(urls), 'httpStatus': submit(urls, opener)}
    except urllib.error.HTTPError as error:
        return {'status': 'refused', 'reason': f'http_{error.code}'}
    except (OSError, ValueError, ET.ParseError, http.client.HTTPException) as error:
        return {'status': 'unreachable', 'reason': type(error).__name__}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--all', action='store_true', help='send every page of the sitemap')
    parser.add_argument('--dry-run', action='store_true', help='print the pages without sending them')
    options = parser.parse_args(argv)
    today = dt.datetime.now(dt.timezone.utc).date()
    report = run(today, since_days=None if options.all else RECENT_DAYS, dry_run=options.dry_run)
    sys.stdout.write(json.dumps(report, ensure_ascii=False) + '\n')
    return 0 if report['status'] in ('submitted', 'nothing_changed', 'dry_run') else 1


if __name__ == '__main__':
    raise SystemExit(main())
