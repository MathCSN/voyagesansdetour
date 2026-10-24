"""Pages de lieu GetYourGuide (« lisbonne-l42 ») des guides, résolues une fois et mises en cache.

La recherche GetYourGuide par mot-clé peut afficher une autre ville : on lie donc la page du lieu.
Son identifiant vient du widget officiel partenaire (réponse HTML publique, sans clé d'API) ;
il n'est retenu que si le nom de la page correspond exactement au lieu du guide. Sinon : pas de lien.

    python3 gyg_locations.py --update   # résout les lieux manquants et réécrit le cache
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import datetime
import json
from pathlib import Path
import re
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import affiliates

ROOT = Path(__file__).resolve().parent
CACHE_NAME = 'getyourguide-locations.json'
WIDGET = 'https://widget.getyourguide.com/default/activities.frame'
PARTNER_KEY = 'getyourguide'
RETRY_DAYS = 30
TIMEOUT_SECONDS = 20
MAX_BYTES = 2_000_000
USER_AGENT = 'Mozilla/5.0 (compatible; VoyageSansDetour/1.0; +https://voyagesansdetour.fr/)'
LINK = re.compile(r'getyourguide\.[a-z.]+/(?:[a-z]{2}-[a-z]{2}/)?([a-z0-9]+(?:-[a-z0-9]+)*-l[0-9]+)/')
KEY_PATTERN = re.compile(r'[a-z0-9-]+\|[a-z0-9-]+')
DATE_PATTERN = re.compile(r'\d{4}-\d{2}-\d{2}')
ENTRY_KEYS = {'place', 'country', 'path', 'checkedOn'}


def partner_id(root: Path = ROOT) -> str:
    config = affiliates.load_config(root / 'affiliates.json')
    return next(p['id'] for p in config['partners'] if p['key'] == PARTNER_KEY)


def widget_url(query: str, partner: str | None = None) -> str:
    params = {'locale_code': 'fr-FR', 'widget': 'activities', 'number_of_items': '6',
              'partner_id': partner or partner_id(), 'q': query}
    return WIDGET + '?' + urlencode(params, quote_via=quote)


def fetch(query: str) -> str:
    request = Request(widget_url(query), headers={'User-Agent': USER_AGENT, 'Accept-Language': 'fr-FR'})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - URL fixe du widget officiel
        return response.read(MAX_BYTES).decode('utf-8', 'replace')


def matches(path: str, place: str, country: str | None = None) -> bool:
    """« lisbonne-l42 » correspond à Lisbonne ; « santarem-portugal-l1441 » à Santarém, Portugal.
    Un simple préfixe ne suffit pas : « porto-vecchio » n'est pas Porto."""
    base = re.sub(r'-l[0-9]+$', '', path)
    name = affiliates.slugify(place)
    return bool(name) and (base == name or (bool(country) and base == name + '-' + affiliates.slugify(country)))


def location_from_html(html: str, place: str, country: str | None = None) -> str | None:
    for path, _ in Counter(LINK.findall(html or '')).most_common():
        if matches(path, place, country):
            return path
    return None


# --- cache -------------------------------------------------------------------------------

def empty() -> dict:
    return {'schemaVersion': 1, 'locations': {}}


def validate(cache: dict) -> dict:
    if not isinstance(cache, dict) or set(cache) != {'schemaVersion', 'locations'} or cache['schemaVersion'] != 1:
        raise ValueError(f'{CACHE_NAME} : schemaVersion 1 et locations requis.')
    if not isinstance(cache['locations'], dict):
        raise ValueError(f'{CACHE_NAME} : locations doit être un objet.')
    for key, entry in cache['locations'].items():
        if not KEY_PATTERN.fullmatch(key) or not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
            raise ValueError(f'{CACHE_NAME} : entrée invalide {key}.')
        path = entry['path']
        if path is not None and not (isinstance(path, str) and affiliates.LOCATION_PATTERN.fullmatch(path)):
            raise ValueError(f'{CACHE_NAME} : page de lieu invalide pour {key}.')
        if not (isinstance(entry['checkedOn'], str) and DATE_PATTERN.fullmatch(entry['checkedOn'])):
            raise ValueError(f'{CACHE_NAME} : date de contrôle invalide pour {key}.')
    return cache


def load(path: Path) -> dict:
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))


def paths(path: Path) -> dict:
    """{clé du lieu: page} des lieux résolus ; un cache absent ne casse pas la génération."""
    path = Path(path)
    if not path.is_file():
        return {}
    return {key: entry['path'] for key, entry in load(path)['locations'].items() if entry['path']}


def save(path: Path, cache: dict) -> None:
    Path(path).write_text(json.dumps(validate(cache), ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


# --- résolution --------------------------------------------------------------------------

def needed(articles: list, countries: dict) -> dict:
    """Tous les lieux que les guides peuvent lier : {clé: (lieu, nom du pays)}."""
    result = {}
    for article in articles:
        country_name, _ = affiliates.country_of(article, countries)
        for place in affiliates.places_for(article, articles, country_name) + affiliates.title_places(article, country_name):
            result.setdefault(place.key, (place.name, country_name))
    return result


def needed_keys(articles: list, countries: dict) -> set:
    return set(needed(articles, countries))


def is_settled(entry: dict | None, today: str) -> bool:
    if not entry:
        return False
    if entry['path']:
        return True
    age = datetime.date.fromisoformat(today) - datetime.date.fromisoformat(entry['checkedOn'])
    return age.days < RETRY_DAYS


def update(cache: dict, articles: list, countries: dict, *, fetch=fetch, today: str | None = None) -> dict:
    """Nouveau cache où chaque lieu manquant (ou échec ancien) est résolu ; l'original n'est pas modifié."""
    today = today or datetime.date.today().isoformat()
    result = copy.deepcopy(validate(cache))
    for key, (place, country) in sorted(needed(articles, countries).items()):
        if is_settled(result['locations'].get(key), today):
            continue
        try:
            html = fetch(place)
        except (OSError, ValueError) as error:
            print(f'GetYourGuide : {place} non résolu ({error.__class__.__name__}), nouvel essai plus tard.')
            continue
        result['locations'][key] = {'place': place, 'country': country, 'path': location_from_html(html, place, country),
                                    'checkedOn': today}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--update', action='store_true', help='résoudre les lieux manquants et réécrire le cache')
    args = parser.parse_args()
    import editorial_queue
    cache_path = ROOT / CACHE_NAME
    cache = load(cache_path) if cache_path.is_file() else empty()
    articles = editorial_queue.published_articles(ROOT)
    countries = affiliates.load_countries(ROOT / 'destinations.json')
    if args.update:
        cache = update(cache, articles, countries)
        save(cache_path, cache)
    for key in sorted(needed_keys(articles, countries)):
        entry = cache['locations'].get(key)
        print(key, '→', (entry or {}).get('path') or 'aucune page fiable (pas de lien)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
