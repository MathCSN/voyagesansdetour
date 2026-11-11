"""Photos and video plans of a place for the automatic posts: the guide's own pictures first.

Every photo is a free Commons file (the guide's, then the site's other photos of the same place,
then Commons featured pictures whose title names the place). Every clip comes from clip_intake
(Pexels or Commons, licence checked). Each file is fetched once and reused; never an AI-generated
image or video. A file that no post ends up using is removed by the caller.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.parse

import clip_intake
import destinations
import photo_intake
from reel_formats import checked

AUTO = "auto"
AUTO_PHOTOS = "assets/photos/auto"
FEATURED = "incategory:Featured_pictures_on_Wikimedia_Commons"
GENERIC_TITLE_WORDS = {"panorama", "view", "vista", "from", "with", "near", "jpeg", "italy", "italia", "spain", "espana",
                       "portugal", "france", "photo", "picture", "image", "night", "sunset", "edit", "crop", "city"}


def commons_title(source_page: str) -> str | None:
    parsed = urllib.parse.urlsplit(source_page or "")
    if parsed.hostname != "commons.wikimedia.org" or not parsed.path.startswith("/wiki/"):
        return None
    return urllib.parse.unquote(parsed.path.removeprefix("/wiki/")).replace("_", " ")


def guide_photo_ids(article: dict) -> list[str]:
    ids = [article.get("cover")] + [section.get("image") for section in article.get("sections", [])]
    return list(dict.fromkeys(i for i in ids if i))


def photo_candidates(article: dict, site_photos: dict, country: str) -> list[dict]:
    """The guide's own photos first, then the site's other photos of the same place."""
    own = guide_photo_ids(article)
    prefixes = {i.split("-", 1)[0] for i in own}
    related = [i for i in site_photos if i not in own and i.split("-", 1)[0] in prefixes]
    candidates = []
    for photo_id in own + related:
        record = site_photos.get(photo_id) or {}
        title = commons_title(record.get("source_page", ""))
        if title:
            candidates.append({"id": photo_id, "title": title, "alt": record.get("alt_fr") or f"{article['destination']} ({country}).",
                               "author": record.get("author")})
    return candidates


def search_keywords(article: dict, candidates: list[dict]) -> list[str]:
    """The place name, then the local place names found in the guide's own Commons titles (Manarola, Granada…)."""
    words = [article["destination"]]
    for candidate in candidates:
        for word in re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ’'-]{4,}", candidate["title"].removeprefix("File:")):
            if destinations.ascii_fold(word).lower() not in GENERIC_TITLE_WORDS:
                words.append(word)
    return list(dict.fromkeys(words))[:6]


def featured_candidates(article: dict, keywords: list[str], country: str, searcher) -> list[dict]:
    found = []
    for keyword in keywords:
        try:
            titles = searcher(f'"{keyword}" {FEATURED}')
        except (OSError, ValueError):
            continue
        for title in titles:
            # The place must be named in the file title: a search hit on the description alone is refused.
            if destinations.ascii_fold(keyword).lower() not in destinations.ascii_fold(title).lower():
                continue
            name = re.sub(r"\s+", " ", re.sub(r"\.(jpe?g)$", "", title.removeprefix("File:"), flags=re.IGNORECASE)).strip()
            photo_id = re.sub(r"[^a-z0-9]+", "-", destinations.ascii_fold(article["destination"]).lower()).strip("-")[:40]
            photo_id += "-" + hashlib.sha1(title.encode()).hexdigest()[:8]
            found.append({"id": photo_id, "title": title, "alt": f"{article['destination']} ({country}) : {name}."[:300]})
    return found


class Photos:
    """Photo records already downloaded (shared catalogue and earlier auto posts), reused by Commons title."""

    def __init__(self, root: Path, now: dt.datetime, downloader=None):
        self.root, self.now = root, now
        self.download = downloader or self._download
        self.known: dict[str, tuple[str, dict]] = {}
        shared = root / "assets" / "photos" / "catalogue.json"
        catalogues = [shared] if shared.is_file() else []
        catalogues += sorted((root / AUTO).glob("*/photos.json"))
        for path in catalogues:
            for photo_id, record in json.loads(path.read_text()).get("photos", {}).items():
                if (root / record.get("file", "")).is_file():
                    self.known.setdefault(record.get("commonsTitle"), (photo_id, record))
        self.created: list[Path] = []
        self.refused: set[str] = set()

    def _download(self, photo_id: str, title: str) -> dict:
        return photo_intake.photo_record(photo_id, title, self.now, self.root / AUTO_PHOTOS, AUTO_PHOTOS + "/")

    def get(self, candidate: dict) -> tuple[str, dict] | None:
        title = candidate["title"]
        if title in self.known:
            return self.known[title]
        if title in self.refused:
            return None
        try:
            record = self.download(candidate["id"], title)
        except (OSError, ValueError, KeyError):  # a refusal (photo_intake.Refused) is a ValueError
            self.refused.add(title)
            return None
        self.created.append(self.root / record["file"])
        # The site's photo credits are reviewed by hand: their author name wins over Commons' free text.
        if candidate.get("author") and checked(candidate["author"], 200):
            record = {**record, "author": candidate["author"]}
        self.known[title] = (candidate["id"], record)
        return self.known[title]


def gather_photos(article: dict, needed: int, photos: Photos, site_photos: dict, country: str, searcher) -> list[tuple[str, dict, str]]:
    """Up to `needed` distinct, freely licensed photographs of the place: (id, record, alt)."""
    chosen, seen = [], set()

    def take(candidates):
        for candidate in candidates:
            if len(chosen) >= needed:
                return
            if not checked(candidate["alt"], 300):
                continue
            got = photos.get(candidate)
            if got and got[0] not in seen and got[1].get("commonsSha1") not in {c[1].get("commonsSha1") for c in chosen if c[1].get("commonsSha1")}:
                seen.add(got[0])
                chosen.append((got[0], got[1], candidate["alt"]))

    own = photo_candidates(article, site_photos, country)
    take(own)
    if len(chosen) < needed:
        take(featured_candidates(article, search_keywords(article, own), country, searcher))
    return chosen


class Clips:
    """Real video plans of a place, fetched once and reused; none when no provider is configured."""

    def __init__(self, root: Path, now: dt.datetime, cadence, finder=None, downloader=None):
        self.root, self.now, self.cadence = root, now, cadence
        self.find = finder or (lambda place: clip_intake.find(place, cadence.clip_providers, os.environ.get("PEXELS_API_KEY")))
        self.download = downloader or (lambda clip_id, candidate: clip_intake.clip_record(clip_id, candidate, now, root))
        self.known: dict[str, tuple[str, dict]] = {}
        for path in sorted((root / AUTO).glob("*/clips.json")):
            for clip_id, record in json.loads(path.read_text()).get("clips", {}).items():
                if (root / record.get("file", "")).is_file():
                    self.known.setdefault(record.get("sourcePage"), (clip_id, record))
        self.created: list[Path] = []

    def gather(self, article: dict) -> list[tuple[str, dict]]:
        """Up to `perReel` clips whose title or page names the guide's place: (id, record)."""
        if not self.cadence.clip_providers or self.cadence.clips_per_reel < 1:
            return []
        place, chosen = article["destination"], []
        try:
            candidates = self.find(place)
        except (OSError, ValueError):
            return []
        for candidate in candidates:
            if len(chosen) >= self.cadence.clips_per_reel:
                break
            if candidate["sourcePage"] not in self.known:
                try:
                    record = self.download(clip_intake.clip_id_for(place, candidate), candidate)
                except (OSError, ValueError, KeyError):  # a refusal (photo_intake.Refused) is a ValueError
                    continue
                self.created.append(self.root / record["file"])
                self.known[candidate["sourcePage"]] = (clip_intake.clip_id_for(place, candidate), record)
            chosen.append(self.known[candidate["sourcePage"]])
        return chosen
