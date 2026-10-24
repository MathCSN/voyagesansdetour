#!/usr/bin/env python3
"""Add freely licensed Wikimedia Commons photos to the social photo catalogue.

Each photo keeps its author, licence, source page and fingerprint. Only CC BY,
CC BY-SA, CC0 and public-domain files are accepted; anything else is refused.
Usage: python3 photo_intake.py <photo-id> "File:Commons title.jpg" [...]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import io
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

from PIL import Image

HERE = Path(__file__).resolve().parent
PHOTOS = HERE / "assets" / "photos"
CATALOGUE = PHOTOS / "catalogue.json"
API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = {"User-Agent": "VoyageSansDetour-social/1.0 (contact@voyagesansdetour.fr)"}
PHOTO_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,63}\Z")
MIN_SIDE = 1600
# Stored size: enough for a slow 9:16 pan at 1080 x 1920 without upscaling.
STORED_SHORT_SIDE = 1600
STORED_LONG_SIDE_MAX = 2880
JPEG_QUALITY = 84
LICENCES = {
    "CC BY 2.0": "https://creativecommons.org/licenses/by/2.0/",
    "CC BY 2.5": "https://creativecommons.org/licenses/by/2.5/",
    "CC BY 3.0": "https://creativecommons.org/licenses/by/3.0/",
    "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC BY-SA 2.0": "https://creativecommons.org/licenses/by-sa/2.0/",
    "CC BY-SA 2.5": "https://creativecommons.org/licenses/by-sa/2.5/",
    "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "Public domain": "https://commons.wikimedia.org/wiki/Help:Public_domain",
}


# Never an AI-generated image (Mathis's rule, CLAUDE.md): a category, template or mention is enough to refuse.
AI_MARKERS = re.compile(r"ai[- ]generated|generated (?:by|with) (?:an )?(?:ai|artificial intelligence)|artificial intelligence|"
                        r"midjourney|dall[·.\- ]?e|stable diffusion|text-to-image|image generator|adobe firefly|"
                        r"\bai[- ]art\b|\bgenai\b|neural network generated", re.IGNORECASE)


class Refused(ValueError):
    pass


def ai_generated(title: str, meta: dict) -> bool:
    fields = [title] + [plain_text(meta.get(key, {}).get("value", "")) for key in
                        ("Categories", "ImageDescription", "Credit", "Artist", "Attribution", "ObjectName")]
    return any(AI_MARKERS.search(field or "") for field in fields)


def plain_text(value: str) -> str:
    """Commons returns HTML for authors; keep only readable text."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return " ".join(text.split())


def credited_author(meta: dict, uploader: str | None = None) -> str:
    """A short public credit: never an e-mail address or a paragraph of usage requests."""
    for key in ("Attribution", "Artist"):
        raw = plain_text(meta.get(key, {}).get("value", ""))
        # "This Photo was taken by Jane Doe . Feel free to use…": keep the name only.
        word = r"(?:[A-ZÀ-Ý]\.|[A-ZÀ-Ý][\w’'-]+)"  # an initial keeps its period, a full word does not
        named = re.search(r"\b(?i:taken|photographed|shot|made|created)\s+(?i:by)\s+(" + word + r"(?:\s" + word + r"){0,5})", raw)
        value = named.group(1) if named else raw
        value = re.sub(r"\S+@\S+|https?://\S+", "", value)
        value = re.split(r"\.?\s*(?:Licen[cs]e|GFDL|CC[- ]BY)\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
        value = re.sub(r"^(?:I,\s*|(?:Photo(?:graph)?(?:ed)?|Taken|Picture)\s+by\s+)", "", " ".join(value.split()), flags=re.IGNORECASE)
        value = value.strip(" .,;:-")
        if 2 <= len(value) <= 80:
            return value
    # Commons' "Own work": the uploader is the author.
    if uploader and "own work" in plain_text(meta.get("Credit", {}).get("value", "")).lower():
        return uploader
    return "Auteur inconnu"


def licence_record(meta: dict) -> tuple[str, str]:
    name = plain_text(meta.get("LicenseShortName", {}).get("value", ""))
    if name not in LICENCES:
        raise Refused("Licence not accepted for social media: " + (name or "unknown"))
    return name, LICENCES[name]


def fetch_json(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    with urllib.request.urlopen(urllib.request.Request(url, headers=USER_AGENT), timeout=60) as response:
        return json.load(response)


def commons_info(title: str) -> dict:
    data = fetch_json({"action": "query", "titles": title, "prop": "imageinfo",
                       "iiprop": "url|size|extmetadata|mime|sha1|user", "iiurlwidth": STORED_LONG_SIDE_MAX})
    pages = list(data.get("query", {}).get("pages", {}).values())
    if len(pages) != 1 or "imageinfo" not in pages[0]:
        raise Refused("Commons file not found: " + title)
    info = pages[0]["imageinfo"][0]
    if info.get("mime") != "image/jpeg" or min(info["width"], info["height"]) < MIN_SIDE:
        raise Refused("Photo too small or not a JPEG: " + title)
    if ai_generated(title, info.get("extmetadata", {})):
        raise Refused("AI-generated or not clearly photographic: " + title)
    return info


def stored_size(width: int, height: int) -> tuple[int, int]:
    scale = STORED_SHORT_SIDE / min(width, height)
    scale = min(scale, STORED_LONG_SIDE_MAX / max(width, height), 1.0)
    return round(width * scale), round(height * scale)


def download(url: str) -> Image.Image:
    with urllib.request.urlopen(urllib.request.Request(url, headers=USER_AGENT), timeout=120) as response:
        raw = response.read(60_000_001)
    if len(raw) > 60_000_000:
        raise Refused("Photo download too large")
    image = Image.open(io.BytesIO(raw))
    image.load()
    return image.convert("RGB")


def load_catalogue() -> dict:
    if not CATALOGUE.exists():
        return {"schemaVersion": 1, "photos": {}}
    return json.loads(CATALOGUE.read_text())


def photo_record(photo_id: str, title: str, now: dt.datetime, folder: Path = PHOTOS, prefix: str = "assets/photos/") -> dict:
    """Download one Commons photo into folder and return its catalogue record (licence, author, fingerprint)."""
    if not PHOTO_ID.fullmatch(photo_id):
        raise Refused("Invalid photo id: " + photo_id)
    info = commons_info(title)
    meta = info.get("extmetadata", {})
    licence, licence_url = licence_record(meta)
    # "Artist" sometimes names the monument's architect; "Attribution" is the
    # credit requested by the uploader. "Credit" is kept for human review.
    author = credited_author(meta, info.get("user"))
    credit = plain_text(meta.get("Credit", {}).get("value", ""))
    image = download(info.get("thumburl") or info["url"])
    size = stored_size(*image.size)
    if size != image.size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (photo_id + ".jpg")
    image.save(path, quality=JPEG_QUALITY, optimize=True, progressive=True)
    raw = path.read_bytes()
    return {
        "file": prefix + path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "width": size[0], "height": size[1],
        "commonsTitle": title,
        "sourcePage": info["descriptionurl"],
        "author": author[:200],
        "commonsCredit": credit[:200],
        "licence": licence, "licenceUrl": licence_url,
        "originalSize": [info["width"], info["height"]],
        "commonsSha1": info.get("sha1"),
        "retrievedAt": now.isoformat().replace("+00:00", "Z"),
        "modifications": "Redimensionnée, recadrée et légendée pour les réseaux sociaux.",
    }


def add_photo(catalogue: dict, photo_id: str, title: str, now: dt.datetime) -> dict:
    if photo_id in catalogue["photos"]:
        raise Refused("Photo id already catalogued: " + photo_id)
    return {**catalogue, "photos": {**catalogue["photos"], photo_id: photo_record(photo_id, title, now)}}


def commons_search(query: str, limit: int = 20) -> list[str]:
    """File titles matching a Commons search (namespace File), best first."""
    data = fetch_json({"action": "query", "list": "search", "srnamespace": 6, "srsearch": query, "srlimit": limit})
    return [hit["title"] for hit in data.get("query", {}).get("search", []) if isinstance(hit.get("title"), str)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pairs", nargs="+", help="photo-id followed by its Commons title, repeated")
    args = parser.parse_args()
    if len(args.pairs) % 2:
        raise SystemExit("Provide pairs: photo-id title")
    PHOTOS.mkdir(parents=True, exist_ok=True)
    catalogue = load_catalogue()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    for photo_id, title in zip(args.pairs[::2], args.pairs[1::2]):
        try:
            catalogue = add_photo(catalogue, photo_id, title, now)
            print("added", photo_id, catalogue["photos"][photo_id]["licence"])
        except Refused as error:
            print("refused", photo_id, error)
    ordered = {"schemaVersion": 1, "photos": dict(sorted(catalogue["photos"].items()))}
    CATALOGUE.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
