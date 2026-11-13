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


# Photos of the site that illustrate one paragraph and cannot stand for the place under the call to action: a vehicle,
# a station, an interior, an animal, a terrace, a street like any other. Each photo of the site was looked at on
# 12/11/2026 (the last card of a reel had been put on a station sign, a hotel terrace and a dark door); a photo added
# to the site since then may close a post until someone lists it here.
NOT_A_CLOSING = frozenset({
    "lisbonne-miradouro", "lisbonne-cacilhas-ferry", "porto-tram-historique", "porto-metro-aeroport", "porto-caves-gaia",
    "guimaraes-teleferico-penha", "guimaraes-rua-santa-maria", "algarve-faro", "algarve-train", "douro-pinhao-gare",
    "douro-pinhao-azulejos", "seville-alcazar", "amalfi-ravello", "amalfi-ferry", "cinque-train", "thailande-train-nuit",
    "costa-rica-monteverde", "japon-shinkansen", "japon-nara-cerfs", "laponie-husky", "tenerife-adeje"})

# Files of Wikimedia Commons that are not the photograph as it was taken, never to be used whatever lists them: this
# one is a landscape version (3074 × 2304) uploaded in 2024 by another account from a portrait original (1536 × 2048)
# by Samuli Lintula; its margins were made up. Mathis's rule: real photographs only, no generated or extended image.
NOT_A_PHOTOGRAPH_AS_TAKEN = frozenset({"File:Snowball pyramid at Santa Claus' Village Large.jpg"})

# Photos that show numbers of their own (a display, a board of fares): a table is never laid over them, its figures
# would be read among theirs. `train-alfa-220` is the display of an Alfa Pendular carriage: "220 km/h · 10:22 · 21 °C".
OWN_FIGURES = frozenset({"train-alfa-220"})

# Where the subject of a photo of the site is (x, y from 0 to 1), when a vertical frame cut around its middle misses it:
# the gable of the Grand Palace stands on the right of its photo, under a wide evening sky.
# The temple of Tulum stands right of the middle of a panorama: cut around the middle, the frame slid off it.
# On the beach of Koh Samui a bather stands in the left third, cut by the edge of a centred frame: the sea, the
# jet-skis and the hill are on the right.
# The doe of Nara stands in the right half, her head at 85 % of the width: a centred frame kept her body and cut her
# neck (audit of 13/11/2026, on a reel and on a carousel). At 0.68 the 4:5 frame of a carousel holds her whole. The
# 9:16 frame of a reel is narrower than she is long and slides: it shows her head for part of the plan only.
SITE_FOCUS = {"thailande-bangkok-grand-palais": [0.72, 0.7], "yucatan-tulum": [0.645, 0.5], "thailande-koh-samui": [0.72, 0.5],
              "japon-nara-cerfs": [0.68, 0.5]}


def commons_title(source_page: str) -> str | None:
    parsed = urllib.parse.urlsplit(source_page or "")
    if parsed.hostname != "commons.wikimedia.org" or not parsed.path.startswith("/wiki/"):
        return None
    return urllib.parse.unquote(parsed.path.removeprefix("/wiki/")).replace("_", " ")


def guide_photo_ids(article: dict) -> list[str]:
    ids = [article.get("cover")] + [section.get("image") for section in article.get("sections", [])]
    return list(dict.fromkeys(i for i in ids if i))


def photo_candidates(article: dict, site_photos: dict, country: str, shared: dict | None = None) -> list[dict]:
    """The guide's own photos first, then the other hand-reviewed photos of the same place: the site's, then the social catalogue's."""
    own = guide_photo_ids(article)
    prefixes = {i.split("-", 1)[0] for i in own}
    related = [i for i in site_photos if i not in own and i.split("-", 1)[0] in prefixes]
    fallback = f"{article['destination']} ({country})."
    candidates = []
    for photo_id in own + related:
        record = site_photos.get(photo_id) or {}
        title = commons_title(record.get("source_page", ""))
        if title:
            # A photo the site publishes for this place was chosen to stand for it: it may close a post, unless it only
            # illustrates one paragraph (NOT_A_CLOSING).
            candidates.append({"id": photo_id, "title": title, "alt": record.get("alt_fr") or fallback, "author": record.get("author"),
                               "emblematic": photo_id not in NOT_A_CLOSING, **({"focus": SITE_FOCUS[photo_id]} if photo_id in SITE_FOCUS else {})})
    taken = {candidate["title"] for candidate in candidates}
    for photo_id, record in (shared or {}).items():
        title = record.get("commonsTitle")
        if photo_id.split("-", 1)[0] in prefixes and isinstance(title, str) and title not in taken:
            candidates.append({"id": photo_id, "title": title, "alt": record.get("alt") or fallback})
    return candidates


def slugged(value: str) -> str:
    """'Côte amalfitaine' → 'cote-amalfitaine': one spelling for comparing place names."""
    return re.sub(r"[^a-z0-9]+", "-", destinations.ascii_fold(value).lower()).strip("-")


def place_names(article: dict, table: dict) -> list[str]:
    """The only names a Commons search may use and a file title must carry: the guide's place in French, then the
    names reviewed by hand in destinations.EXONYMS (Lapland, London). A country is named only when the guide covers
    the whole country. Never a word taken from another photo's title: "Santa" (Claus Village) names half the world."""
    place = article["destination"].strip()
    names = {}
    for name in (place, *destinations.EXONYMS.get(slugged(place), ())):
        names.setdefault(slugged(name), name)
    return list(names.values())


def names_place(title: str, names: list[str]) -> bool:
    """One of the names as whole words of the file title: "Porto" is not in "Portofino"."""
    words = "-" + slugged(title.removeprefix("File:")) + "-"
    return any(f"-{slugged(name)}-" in words for name in names if slugged(name))


def homonyms(article: dict) -> list[str]:
    """Other places of the same country whose name holds the guide's (destinations.HOMONYMS): Porto Covo for Porto."""
    return list(destinations.HOMONYMS.get(slugged(article["destination"]), ()))


def names_another_place(record: dict, others: list[str]) -> bool:
    """The file's title or one of its Commons categories names a homonym of the guide's place: "Porto Covo Outubro
    2014" and "Foggy Fanal forest in Seixal, Porto Moniz" both carry the word "Porto" and neither is Porto."""
    texts = [str(record.get("commonsTitle") or ""), *str(record.get("categories") or "").split("|")]
    return any(names_place(text, others) for text in texts)


# A found file must show the place, not what lives or happens there: Commons files a coati on a beach of Yucatán, a
# flatfish off Tenerife or a football match in London under the name of the place. Its categories say so in English.
NOT_THE_PLACE = re.compile(
    r"\b(?:animals?|animalia|wildlife|fauna|flora|mammals?|mammalia|birds?(?!['’]?s?[ -]eye)|aves|fish(?:es)?|actinopterygii"
    r"|insects?|insecta|arthropod[as]?|reptiles?|reptilia|amphibia(?:ns)?|butterfl(?:y|ies)|lepidoptera|dragonfl(?:y|ies)|odonata"
    r"|bees?|spiders?|mollus[ck]s?|mollusca|cephalopod[as]?|octopus(?:es)?|[a-z]+idae|underwater|in flight|zoo"
    r"|flowers?|tulips?|plantae|fungi|mushrooms?|sports?|football|matches)\b", re.IGNORECASE)
# A Latin name in the title: "Tapaculo (Bothus podas), Tenerife". The second word ends as species names do, so that
# "Ribeira (Old town), Porto" stays a photo of the place.
SPECIES = re.compile(r"\([A-Z][a-z]+ [a-z]+(?:us|a|as|is|um|i|ae|es|ens|or)\)")


def shows_something_else(record: dict) -> bool:
    """An animal, a plant or a match rather than the place, by the file's own title and categories."""
    title = str(record.get("commonsTitle") or "")
    return bool(SPECIES.search(title) or NOT_THE_PLACE.search(title + "|" + str(record.get("categories") or "")))


def country_names(article: dict, table: dict) -> list[str]:
    """The guide's country as Commons writes it: its French name, then English and Spanish (destinations.EXONYMS)."""
    slug = destinations.country_slug(article)
    names = {}
    for name in (destinations.name(slug, table), *destinations.EXONYMS.get(slug, ())):
        names.setdefault(slugged(name), name)
    return list(names.values())


def tied_to_country(record: dict, names: list[str]) -> bool:
    """A found file is of the guide's place only if its title or its Commons categories also name the guide's country:
    "Chapada dos Guimarães" is in Brazil, "Swedish Lapland" is not Rovaniemi. Nothing said: no photo."""
    categories = str(record.get("categories") or "").split("|")
    return any(names_place(text, names) for text in [str(record.get("commonsTitle") or ""), *categories])


def featured_candidates(article: dict, names: list[str], country: str, searcher, countries: list[str] | None = None) -> list[dict]:
    """Commons featured pictures whose title names the place. Found without a human eye: marked `automatic`,
    they must also prove they left a camera and that they are in the guide's country (Photos.get).
    A guide of a whole country is never searched: a country's name in a title says nothing of what the picture shows."""
    countries = countries or []
    if {slugged(name) for name in names} & {slugged(name) for name in countries}:
        return []
    found, others = [], homonyms(article)
    for name in names:
        try:
            titles = searcher(f'"{name}" {FEATURED}')
        except (OSError, ValueError):
            continue
        for title in titles:
            # The place must be named in the file title: a search hit on the description alone is refused.
            # And it must be that place: "Porto Covo" names another town of the same country.
            if not names_place(title, names) or names_place(title, others):
                continue
            label = re.sub(r"\s+", " ", re.sub(r"\.(jpe?g)$", "", title.removeprefix("File:"), flags=re.IGNORECASE)).strip()
            found.append({"id": slugged(article["destination"])[:40] + "-" + hashlib.sha1(title.encode()).hexdigest()[:8], "title": title,
                          "alt": f"{article['destination']} ({country}) : {label}."[:300], "automatic": True, "countryNames": countries,
                          "homonyms": others})
    return found


class Photos:
    """Photo records already downloaded (shared catalogue and earlier auto posts), reused by Commons title."""

    def __init__(self, root: Path, now: dt.datetime, downloader=None):
        self.root, self.now = root, now
        self.download = downloader or self._download
        self.known: dict[str, tuple[str, dict]] = {}
        # Photos added and looked at by hand (photo_intake.py), candidates for the guides of the same place: the catalogue of
        # the hand-written scenarios (sealed by their fingerprints, only read here), then reviewed.json, which grows.
        hand = [path for path in (root / "assets" / "photos" / name for name in ("catalogue.json", "reviewed.json")) if path.is_file()]
        self.shared: dict[str, dict] = {}
        for path in hand:
            for photo_id, record in json.loads(path.read_text()).get("photos", {}).items():
                self.shared.setdefault(photo_id, record)
        catalogues = hand + sorted((root / AUTO).glob("*/photos.json"))
        for path in catalogues:
            for photo_id, record in json.loads(path.read_text()).get("photos", {}).items():
                if (root / record.get("file", "")).is_file():
                    self.known.setdefault(record.get("commonsTitle"), (photo_id, record))
        self.created: list[Path] = []
        self.refused: set[str] = set()

    @staticmethod
    def acceptable(candidate: dict, record: dict, fetched: bool) -> bool:
        """Nobody looked at a file found by the search: it must be a photograph (a camera in its own data when it is
        fetched today, nothing in its record that says otherwise), show the place rather than an animal, a plant or a
        match, be tied to the guide's country and name no other place of that country."""
        if photo_intake.unphotographic_record(record) or (fetched and not record.get("camera")):
            return False
        if shows_something_else(record) or names_another_place(record, candidate.get("homonyms") or []):
            return False
        return tied_to_country(record, candidate.get("countryNames") or [])

    def _download(self, photo_id: str, title: str) -> dict:
        return photo_intake.photo_record(photo_id, title, self.now, self.root / AUTO_PHOTOS, AUTO_PHOTOS + "/")

    def get(self, candidate: dict) -> tuple[str, dict] | None:
        title = candidate["title"]
        if title in self.refused or title in NOT_A_PHOTOGRAPH_AS_TAKEN:
            return None
        if title in self.known:
            # A file fetched by an earlier search is used again only if its record still passes today's rules.
            if candidate.get("automatic") and not self.acceptable(candidate, self.known[title][1], fetched=False):
                return None
            return self.known[title]
        try:
            record = self.download(candidate["id"], title)
        except (OSError, ValueError, KeyError):  # a refusal (photo_intake.Refused) is a ValueError
            self.refused.add(title)
            return None
        if candidate.get("automatic") and not self.acceptable(candidate, record, fetched=True):
            (self.root / record["file"]).unlink(missing_ok=True)
            self.refused.add(title)
            return None
        self.created.append(self.root / record["file"])
        # The site's photo credits are reviewed by hand: their author name wins over Commons' free text.
        if candidate.get("author") and checked(candidate["author"], 200):
            record = {**record, "author": candidate["author"]}
        self.known[title] = (candidate["id"], record)
        return self.known[title]


def closing_mark(candidate: dict, record: dict) -> dict:
    """The record with what decides where the photo may stand in a post, whatever an earlier post recorded: a photo of
    the site may close a post (`emblematic`) unless it is listed in NOT_A_CLOSING; a file found by the search never
    closes nor opens one (`automatic`: nobody looked at it); a photo added by hand keeps what its reviewer wrote in
    reviewed.json."""
    plain = {key: value for key, value in record.items() if key not in ("automatic", "emblematic")}
    if candidate.get("automatic"):
        return {**plain, "automatic": True}
    if "emblematic" in candidate:
        return {**plain, "emblematic": True} if candidate["emblematic"] else plain
    return {key: value for key, value in record.items() if key != "automatic"}


def new_photo(candidate: dict, photos: Photos, chosen: list) -> tuple[str, dict, str] | None:
    """The candidate as a photo of the post, or None: no caption the charter accepts, no file, or a picture already there."""
    got = photos.get(candidate) if checked(candidate["alt"], 300) else None
    if not got or got[0] in {photo[0] for photo in chosen}:
        return None
    same = got[1].get("commonsSha1")
    if same and same in {photo[1].get("commonsSha1") for photo in chosen}:
        return None
    record = {key: value for key, value in closing_mark(candidate, got[1]).items() if key != "figures"}
    if got[0] in OWN_FIGURES:
        record = {**record, "figures": True}
    # A photo reviewed by hand carries its own "focus" (reviewed.json); a photo of the site takes it from SITE_FOCUS.
    return (got[0], {**record, "focus": candidate["focus"]} if candidate.get("focus") else record, candidate["alt"])


def taken(candidates: list[dict], needed: int, photos: Photos, chosen: list) -> list[tuple[str, dict, str]]:
    """`chosen` completed with the candidates, in their order, up to `needed` photos."""
    chosen = list(chosen)
    for candidate in candidates:
        if len(chosen) >= needed:
            break
        photo = new_photo(candidate, photos, chosen)
        if photo:
            chosen.append(photo)
    return chosen


def gather_photos(article: dict, needed: int, photos: Photos, site_photos: dict, country: str, searcher,
                  table: dict | None = None) -> list[tuple[str, dict, str]]:
    """Up to `needed` distinct, freely licensed photographs of the place: (id, record, alt)."""
    chosen = taken(photo_candidates(article, site_photos, country, photos.shared), needed, photos, [])
    if len(chosen) < needed:
        found = featured_candidates(article, place_names(article, table or {}), country, searcher, country_names(article, table or {}))
        chosen = taken(found, needed, photos, chosen)
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
