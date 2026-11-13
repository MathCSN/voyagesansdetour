#!/usr/bin/env python3
"""Add freely licensed Wikimedia Commons photos to the social photo catalogue.

Each photo keeps its author, licence, source page and fingerprint. Only CC BY,
CC BY-SA, CC0 and public-domain photographs are accepted; anything else is refused.
Photos go to assets/photos/reviewed.json: looked at by a person, they complete the
automatic posts of the same place (same id prefix as the guide's photos: "laponie-…").
Add an "alt" line in French to each new record. catalogue.json is sealed by the
hand-written scenarios and is left alone unless --sealed-catalogue is given.
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
REVIEWED = PHOTOS / "reviewed.json"
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


# Only photographs (CLAUDE.md): never a drawing, a poster, an advert, a reproduced artwork, a map or a scan.
# Read in the file title and in its Commons categories; a work dated before 1950 is refused as well.
# "Coca-Cola advertisements on trams in Porto" files a photograph of a tram, not an advert: on a vehicle, it is let through.
NOT_A_PHOTO = re.compile(r"\b(?:illustrations?|illustrated|drawings?|engravings?|lithographs?|etchings?|woodcuts?|ukiyo-e|prints? (?:of|by|from)|"
                         r"posters?|(?:advertisements?|adverts?|ads?)(?! on (?:the |a )?(?:trams?|bus(?:es)?|trains?|metros?|taxis?|vehicles?)\b)|caricatures?|cartoons?|comics?|postcards?|paintings? (?:by|of|from|in)|"
                         r"oil on canvas|watercolou?rs?|frescos? by|maps? of|old maps|diagrams?|logos?|coats? of arms|book covers?|"
                         r"magazine covers?|scans? (?:of|from)|scanned|pd-art|google art project|renderings?|3d models?|puck \(magazine\))\b", re.IGNORECASE)
OLDEST_YEAR = 1950


# Only the photograph as it was taken (Mathis's rule: no generated nor extended image). A file that Commons files as
# retouched, cut out of or made from another file is not it, nor one whose title says "edit" or "cropped", nor one
# whose source is another Commons file. On 13/11/2026 a reel was withdrawn for such a file (a landscape version of a
# portrait photo, its margins made up), and a search returned two "edit" files filed under "Retouched pictures".
# ("Images with extracted images" files the original other images were cut out of: it is the photograph as taken.)
DERIVED = re.compile(r"retouched (?:pictures?|images?|photographs?)|derivative (?:works?|versions?)|(?<!with )extracted (?:images?|from)|images? extracted|"
                     r"cropp?ed (?:images?|versions?|from)|digitally (?:altered|manipulated|modified)|photomontages?|upscaled|"
                     r"(?:in|out)painted|generative fill|images? with borders? removed", re.IGNORECASE)
DERIVED_TITLE = re.compile(r"\b(?:edit|edited|cropped|retouched|derivative|upscaled)\b|\((?:crop|cropped|edit|edited|retouched)[^)]*\)", re.IGNORECASE)
ANOTHER_FILE = re.compile(r"\bFile:\S|\bderived from\b|\bderivative of\b|\bextracted from\b|\bcropped from\b|\bthis file was derived\b", re.IGNORECASE)


class Refused(ValueError):
    pass


def derived(title: str, categories: str, source: str) -> bool:
    """Not the photograph as taken, by its title, its Commons categories or its source (another Commons file)."""
    name = title.removeprefix("File:").rsplit(".", 1)[0].replace("_", " ")
    return bool(DERIVED_TITLE.search(name) or DERIVED.search(categories.replace("_", " ").replace("|", " | ")) or ANOTHER_FILE.search(source))


def derived_file(title: str, meta: dict) -> bool:
    return derived(title, plain_text(meta.get("Categories", {}).get("value", "")), plain_text(meta.get("Credit", {}).get("value", "")))


def derived_record(record: dict) -> bool:
    """A catalogued file whose title, categories or source say it is not the photograph as it was taken."""
    return derived(str(record.get("commonsTitle") or ""), str(record.get("categories") or ""), str(record.get("commonsCredit") or ""))


def not_a_photograph(title: str, meta: dict) -> bool:
    """An illustration, a poster, an advert, a reproduced artwork, or anything made before 1950."""
    fields = [title, plain_text(meta.get("Categories", {}).get("value", "")).replace("|", " | ")]
    if any(NOT_A_PHOTO.search(field or "") for field in fields):
        return True
    made = re.search(r"(?<!\d)(1\d{3}|20\d{2})(?!\d)", plain_text(meta.get("DateTimeOriginal", {}).get("value", "")))
    return bool(made) and int(made[1]) < OLDEST_YEAR


def unphotographic_record(record: dict) -> bool:
    """A catalogued file whose title or categories say it is not a photograph."""
    return any(isinstance(record.get(key), str) and NOT_A_PHOTO.search(record[key].replace("_", " ").replace("|", " | "))
               for key in ("commonsTitle", "categories"))


def camera_of(info: dict) -> str | None:
    """The camera named in the file's own data (EXIF): the plain sign that a file left a camera, not a scanner or a drawing table."""
    fields = {str(row.get("name")): str(row.get("value") or "").strip() for row in info.get("commonmetadata") or [] if isinstance(row, dict)}
    name = fields.get("Model") or fields.get("Make")
    return name[:80] if name else None


def ai_generated(title: str, meta: dict) -> bool:
    fields = [title] + [plain_text(meta.get(key, {}).get("value", "")) for key in
                        ("Categories", "ImageDescription", "Credit", "Artist", "Attribution", "ObjectName")]
    return any(AI_MARKERS.search(field or "") for field in fields)


# Every text field a photo record may carry, in the social catalogue or the site's image-sources.json.
RECORD_FIELDS = ("commonsTitle", "sourcePage", "source_page", "author", "commonsCredit", "categories", "description",
                 "alt", "alt_fr", "credit_fr", "file", "id")


def ai_record(record: dict) -> bool:
    """A catalogued photo whose record names an AI generator or an AI-generated category."""
    return any(isinstance(record.get(key), str) and AI_MARKERS.search(record[key].replace("_", " ")) for key in RECORD_FIELDS)


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
                       "iiprop": "url|size|extmetadata|mime|sha1|user|commonmetadata", "iiurlwidth": STORED_LONG_SIDE_MAX})
    pages = list(data.get("query", {}).get("pages", {}).values())
    if len(pages) != 1 or "imageinfo" not in pages[0]:
        raise Refused("Commons file not found: " + title)
    info = pages[0]["imageinfo"][0]
    if info.get("mime") != "image/jpeg" or min(info["width"], info["height"]) < MIN_SIDE:
        raise Refused("Photo too small or not a JPEG: " + title)
    if ai_generated(title, info.get("extmetadata", {})):
        raise Refused("AI-generated or not clearly photographic: " + title)
    if not_a_photograph(title, info.get("extmetadata", {})):
        raise Refused("Not a photograph (illustration, poster, artwork or old work): " + title)
    if derived_file(title, info.get("extmetadata", {})):
        raise Refused("Not the photograph as taken (retouched, cropped or made from another file): " + title)
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


def load_catalogue(path: Path = CATALOGUE) -> dict:
    if not path.exists():
        return {"schemaVersion": 1, "photos": {}}
    return json.loads(path.read_text())


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
    camera = camera_of(info)
    return {
        **({"camera": camera} if camera else {}),
        "file": prefix + path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "width": size[0], "height": size[1],
        "commonsTitle": title,
        "sourcePage": info["descriptionurl"],
        "author": author[:200],
        "commonsCredit": credit[:200],
        # Kept so the engine can re-check the "never AI" rule at render time.
        "categories": plain_text(meta.get("Categories", {}).get("value", ""))[:1000],
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
    parser.add_argument("--sealed-catalogue", action="store_true",
                        help="write to catalogue.json instead of reviewed.json: the hand-written scenarios seal that file by "
                             "fingerprint, so every one of them must be sealed again afterwards (seal_scenarios.py)")
    args = parser.parse_args()
    if len(args.pairs) % 2:
        raise SystemExit("Provide pairs: photo-id title")
    PHOTOS.mkdir(parents=True, exist_ok=True)
    # reviewed.json: photos a person looked at, offered to the automatic posts of the same place (media_library.py).
    target = CATALOGUE if args.sealed_catalogue else REVIEWED
    catalogue, other = load_catalogue(target), load_catalogue(REVIEWED if args.sealed_catalogue else CATALOGUE)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    for photo_id, title in zip(args.pairs[::2], args.pairs[1::2]):
        try:
            if photo_id in other["photos"]:
                raise Refused("Photo id already catalogued: " + photo_id)
            catalogue = add_photo(catalogue, photo_id, title, now)
            print("added", photo_id, catalogue["photos"][photo_id]["licence"])
        except Refused as error:
            print("refused", photo_id, error)
    ordered = {"schemaVersion": 1, "photos": dict(sorted(catalogue["photos"].items()))}
    target.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
