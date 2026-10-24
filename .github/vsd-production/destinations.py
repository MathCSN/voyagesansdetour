"""Country names, prepositions and hashtags for social posts and Pins, any country.

The site keeps its countries in site-src/destinations.json. Accepted shapes:
{"countries": {"italie": {"name": "Italie", "in": "en Italie"}}} or a list of
{"slug"|"id": ..., "name": ..., "in"|"preposition": ...}. A country missing from
the file still works: its name comes from its slug and its preposition from
French usage ("au", "aux", "en").
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import unicodedata

SITE = Path(__file__).resolve().parents[2] / "site-src"
DEFAULT_COUNTRY = "portugal"
# French masculine country names take "au"; plural ones take "aux". Everything else takes "en".
MASCULINE = {"portugal", "japon", "canada", "mexique", "maroc", "bresil", "chili", "perou", "vietnam", "cambodge",
             "laos", "danemark", "royaume-uni", "montenegro", "luxembourg", "kenya", "senegal", "costa-rica",
             "guatemala", "panama", "nepal", "sri-lanka", "cap-vert", "liban", "qatar", "oman", "pays-de-galles"}
PLURAL = {"etats-unis", "pays-bas", "emirats-arabes-unis", "philippines", "maldives", "seychelles", "acores", "canaries", "baleares"}
# One hashtag per guide type, chosen for French searches; unknown types fall back to the generic one.
TYPE_HASHTAGS = {"itineraires": "#Itineraire", "itineraire": "#Itineraire", "transports": "#VoyageEnTrain",
                 "excursions": "#Excursion", "quartiers": "#OuDormir", "ou dormir": "#OuDormir", "choisir": "#IdeeVoyage",
                 "preparer": "#ConseilsVoyage", "budget": "#VoyagePasCher", "quand partir": "#QuandPartir",
                 "road trip": "#RoadTrip", "road trips": "#RoadTrip", "que voir": "#QueVoir", "week-end": "#WeekEnd"}
GENERIC_TYPE_HASHTAG = "#ConseilsVoyage"
BRAND_HASHTAG = "#VoyageSansDetour"
MAX_HASHTAGS = 5


def ascii_fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


def hashtag(value: str) -> str | None:
    words = re.findall(r"[A-Za-z0-9]+", ascii_fold(value).replace("’", " ").replace("'", " "))
    tag = "".join(word[:1].upper() + word[1:] for word in words)
    return "#" + tag if 2 <= len(tag) <= 40 else None


def _entries(raw) -> dict:
    if isinstance(raw, dict) and isinstance(raw.get("countries"), dict):
        return raw["countries"]
    items = raw.get("countries") if isinstance(raw, dict) else raw
    if isinstance(items, list):
        return {item.get("slug") or item.get("id"): item for item in items if isinstance(item, dict)}
    return {}


def load(site: Path = SITE) -> dict:
    path = Path(site) / "destinations.json"
    if not path.is_file():
        return {}
    try:
        return {key: value for key, value in _entries(json.loads(path.read_text())).items() if isinstance(key, str) and isinstance(value, dict)}
    except (OSError, ValueError, AttributeError):
        return {}


def country_slug(article: dict) -> str:
    return article.get("country") or DEFAULT_COUNTRY


def name(slug: str, table: dict) -> str:
    entry = table.get(slug, {})
    value = entry.get("name") or entry.get("label")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return " ".join(part.capitalize() for part in slug.split("-"))


def preposition(slug: str, table: dict) -> str:
    """'en Italie', 'au Portugal', 'aux États-Unis'."""
    entry = table.get(slug, {})
    for key in ("in", "preposition", "inLabel"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            value = value.strip()
            # A bare article ("au") is completed with the name.
            return value if " " in value else value + " " + name(slug, table)
    folded = ascii_fold(slug)
    article = "aux" if folded in PLURAL else "au" if folded in MASCULINE else "en"
    return article + " " + name(slug, table)


def type_hashtag(article: dict) -> str:
    category = ascii_fold(str(article.get("category", ""))).lower().strip()
    tag = TYPE_HASHTAGS.get(category, GENERIC_TYPE_HASHTAG)
    if tag == "#VoyageEnTrain" and "train" not in (article.get("slug", "") + " " + article.get("title", "")).lower():
        return GENERIC_TYPE_HASHTAG
    return tag


def hashtags(article: dict, table: dict) -> list[str]:
    """Destination, country, country trip, guide type, brand: five at most, no duplicates."""
    country = name(country_slug(article), table)
    candidates = [hashtag(article.get("destination", "")), hashtag(country), hashtag("Voyage " + country),
                  type_hashtag(article), BRAND_HASHTAG]
    result = []
    for tag in candidates:
        if tag and tag.lower() not in {t.lower() for t in result}:
            result.append(tag)
    return result[:MAX_HASHTAGS]
