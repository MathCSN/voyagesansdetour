"""Liens Stay22 « Allez » statiques, construits à partir du guide. Aucun script, iframe ni pixel."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote, urlencode

ENDPOINT = 'https://www.stay22.com/allez/'
# roam : Stay22 choisit le site de réservation le plus adapté (Booking.com, Expedia…) ;
# getyourguide : activités et billets, rémunérés via le même identifiant Stay22.
PROVIDERS = ('roam', 'getyourguide')
ORIGIN = 'https://voyagesansdetour.fr'
PREVIEW_ORIGIN = 'http://127.0.0.1:8770'
CONFIG_KEYS = {'schema_version', 'enabled', 'hosting_verified', 'links_verified', 'aid', 'endpoint', 'lang', 'currency',
               'campaign_prefix'}
GATES = ('enabled', 'hosting_verified', 'links_verified')
AID_PATTERN = re.compile(r'[a-z0-9_]{3,64}')
CAMPAIGN_MAX = 64


def validate_config(config: dict) -> dict:
    if not isinstance(config, dict) or set(config) != CONFIG_KEYS:
        raise ValueError('Stay22 : configuration incomplète ou champ non autorisé.')
    if type(config['schema_version']) is not int or config['schema_version'] != 2:
        raise ValueError('Stay22 : version de configuration invalide.')
    if any(type(config[name]) is not bool for name in GATES):
        raise ValueError('Stay22 : validations booléennes requises.')
    if (not isinstance(config['aid'], str) or not AID_PATTERN.fullmatch(config['aid']) or config['endpoint'] != ENDPOINT or
            config['lang'] != 'fr' or config['currency'] != 'EUR' or
            not isinstance(config['campaign_prefix'], str) or not AID_PATTERN.fullmatch(config['campaign_prefix'])):
        raise ValueError('Stay22 : AID, URL ou paramètre non validé.')
    if config['enabled'] and not (config['hosting_verified'] and config['links_verified']):
        raise ValueError('Stay22 : activation refusée sans validation du compte et des liens.')
    return config


def load_config(path) -> dict:
    return validate_config(json.loads(Path(path).read_text(encoding='utf-8')))


def is_active(config: dict, *, public: bool, origin: str) -> bool:
    """Liens réels uniquement dans la version publique du domaine prévu ; ailleurs, rien."""
    validate_config(config)
    return config['enabled'] and public and origin == ORIGIN


def validate_preview(root, out, *, public: bool, origin: str) -> None:
    root, out = Path(root).resolve(), Path(out)
    expected = root / 'previews/stay22/site'
    if (public or origin != PREVIEW_ORIGIN or out.resolve() != expected or
            any(path.is_symlink() for path in (root / 'previews', root / 'previews/stay22', out))):
        raise ValueError('Stay22 : aperçu réservé au dossier isolé previews/stay22/site et à localhost, jamais public/.')


def campaign_for(config: dict, slug: str) -> str:
    """Une campagne par guide (Stay22 demande « _ » plutôt que « - »)."""
    tail = re.sub(r'[^a-z0-9]+', '_', slug.lower()).strip('_')
    return (config['campaign_prefix'] + '_' + tail)[:CAMPAIGN_MAX].rstrip('_')


def coordinate(value: float) -> str:
    return f'{float(value):.6f}'.rstrip('0').rstrip('.')


def allez_url(config: dict, provider: str, *, campaign: str, address: str | None = None,
              lat: float | None = None, lng: float | None = None) -> str:
    validate_config(config)
    if provider not in PROVIDERS:
        raise ValueError('Stay22 : fournisseur non autorisé.')
    params = {'aid': config['aid']}
    if lat is not None and lng is not None:
        params.update(lat=coordinate(lat), lng=coordinate(lng))
    elif address and address.strip():
        params['address'] = address.strip()
    else:
        raise ValueError('Stay22 : lieu manquant (adresse ou coordonnées).')
    params.update(campaign=campaign, lang=config['lang'], currency=config['currency'])
    return ENDPOINT + provider + '?' + urlencode(params, quote_via=quote)
