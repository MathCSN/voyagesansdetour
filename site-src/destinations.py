#!/usr/bin/env python3
"""Destination catalogue: countries, continents and a fallback for any new country.

Standard library only. Shared by generate.py (pages) and editorial_queue.py (drafts):
a guide whose country is missing from destinations.json is still published, with a
name derived from its identifier, so the weekly writing chain never breaks the build.
"""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
CATALOGUE = ROOT / 'destinations.json'
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
# Top-level paths owned by fixed pages and files: a country can never take them.
FIXED_PATHS = frozenset({'guides', 'destinations', 'a-propos', 'methode', 'transparence', 'confidentialite',
                         'mentions-legales', 'credits', 'carnet', 'liens', 'formats-courts', 'assets',
                         'social-media', 'pinterest'})
PREPOSITIONS = ('en ', 'au ', 'aux ', 'à ')
FALLBACK_FLAG = '🌍'
LOWERCASE_WORDS = frozenset({'de', 'du', 'des', 'd', 'et', 'la', 'le', 'les'})


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path=CATALOGUE):
    """Return {'continents': {id: entry}, 'countries': {id: entry}} in file order."""
    data = json.loads(Path(path).read_text())
    require(isinstance(data, dict) and data.get('schemaVersion') == 1, f'{Path(path).name} : schemaVersion 1 requis.')
    continents = {}
    for entry in data.get('continents', []):
        require(isinstance(entry, dict) and {'id', 'name', 'preposition'} <= set(entry) <= {'id', 'name', 'preposition', 'short'},
                'Continent invalide.')
        require(SLUG.fullmatch(entry['id']) and entry['id'] not in continents, f'Identifiant de continent invalide : {entry["id"]}')
        # The menu uses the short label when the full name would not fit.
        continents[entry['id']] = dict(entry, short=entry.get('short', entry['name']))
    countries = {}
    for entry in data.get('countries', []):
        require(isinstance(entry, dict) and {'id', 'name', 'preposition', 'continent', 'iso', 'flag'} <= set(entry) <=
                {'id', 'name', 'preposition', 'continent', 'iso', 'flag', 'intro'}, f'Pays invalide : {entry}')
        slug = entry['id']
        require(isinstance(slug, str) and SLUG.fullmatch(slug) and slug not in countries, f'Identifiant de pays invalide : {slug}')
        require(slug not in FIXED_PATHS and slug not in continents, f'Identifiant de pays réservé : {slug}')
        require(entry['continent'] in continents, f'Continent inconnu pour {slug} : {entry["continent"]}')
        require(all(isinstance(entry[key], str) and entry[key] for key in ('name', 'preposition', 'flag')), f'Texte manquant pour {slug}')
        require(entry['preposition'].startswith(PREPOSITIONS), f'Préposition invalide pour {slug}')
        countries[slug] = dict(entry)
    require(continents and countries, 'Référentiel des destinations vide.')
    return {'continents': continents, 'countries': countries}


def reserved(catalogue):
    return FIXED_PATHS | set(catalogue['continents'])


def valid_country(value, catalogue):
    """Any well-formed identifier that does not collide with a fixed page or a continent."""
    return isinstance(value, str) and bool(SLUG.fullmatch(value)) and value not in reserved(catalogue)


def fallback_name(slug):
    words = slug.split('-')
    return ' '.join(w if i and w in LOWERCASE_WORDS else w.capitalize() for i, w in enumerate(words))


def country_info(slug, catalogue, continent=None):
    """Country entry with its continent; unknown countries get a readable fallback.

    The catalogue's continent wins; a guide's own continent only places a country the
    catalogue does not know yet. An unknown continent leaves the country unclassified.
    """
    known = catalogue['countries'].get(slug)
    if known:
        return dict(known, known=True)
    name = fallback_name(slug)
    return {'id': slug, 'name': name, 'preposition': 'en ' + name, 'flag': FALLBACK_FLAG, 'iso': '',
            'continent': continent if continent in catalogue['continents'] else None, 'known': False}
