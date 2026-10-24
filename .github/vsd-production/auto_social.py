#!/usr/bin/env python3
"""Turn every published guide, from any country, into an Instagram reel and a Facebook photo post.

Unattended and bounded. For each channel whose queue covers less than three
weeks, the next free slot gets a post built from one published guide:
- the live guide page is snapshotted (dated, first line = URL): every figure on
  screen is quoted word for word from it (its "L'essentiel en chiffres" block);
- the photos are the guide's own free Commons photos, completed when needed by
  Commons featured pictures of the place; never an AI-generated image;
- the scenario is frozen with its own inputs (auto/<id>/: snapshot, source
  registry, photo records), validated by production.py's guards and layout
  before it enters catalogue.json. Nothing already written is ever modified.
Rendering, public media and the reviewed batch stay with production.py and
social_stock.py. Nothing is sent to any social network here.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

import destinations
from paths import article_path
import photo_intake
import production as p

HERE = Path(__file__).resolve().parent
SITE = HERE.parents[1] / "site-src"
AUTO = "auto"
AUTO_PHOTOS = "assets/photos/auto"
SLOT_HOUR = 17
HORIZON = dt.timedelta(days=21)        # the queue never covers less than three weeks
MIN_LEAD = dt.timedelta(days=2)        # time to render, deploy and import before the slot
MAX_LEAD = dt.timedelta(days=29)       # a source snapshot is valid 30 days (production.SOURCE_VALIDITY)
REVIEW_VALIDITY = dt.timedelta(days=30)
REPOST_COOLDOWN = dt.timedelta(days=42)
CROSS_CHANNEL_GAP = dt.timedelta(days=4)
MAX_GUIDE_SOURCE_AGE = dt.timedelta(days=45)
MAX_NEW_PER_RUN = 4
TITLE_WIDTHS = (34, 24, 18)            # characters per headline line, tried in turn until the layout fits
USER_AGENT = {"User-Agent": "VoyageSansDetour-social/1.0 (contact@voyagesansdetour.fr)"}
FEATURED = "incategory:Featured_pictures_on_Wikimedia_Commons"
GENERIC_TITLE_WORDS = {"panorama", "view", "vista", "from", "with", "near", "jpeg", "italy", "italia", "spain", "espana",
                       "portugal", "france", "photo", "picture", "image", "night", "sunset", "edit", "crop", "city"}
FONT_ASSETS = {
    "regular": {"file": "assets/dmsans-regular.ttf", "license": "OFL-1.1", "licenseFile": {"file": "assets/dmsans-OFL.txt"}},
    "bold": {"file": "assets/dmsans-bold.ttf", "license": "OFL-1.1", "licenseFile": {"file": "assets/dmsans-OFL.txt"}},
    "serif": {"file": "assets/playfair.ttf", "license": "OFL-1.1", "licenseFile": {"file": "assets/playfairdisplay-OFL.txt"}},
}
# Upbeat CC BY 4.0 tracks already qualified (provenance in evidence/), with the second the extract starts at.
MUSIC = (("happy-alley", 8), ("carefree", 1), ("almost-bliss", 0), ("ascending-the-vale", 0))
CATEGORY_EMOJI = {"itineraires": "🗺️", "transports": "🚆", "excursions": "🌄", "quartiers": "🏘️", "choisir": "🤔",
                  "preparer": "🎒", "budget": "💶", "quand partir": "📅", "road trip": "🚗", "road trips": "🚗"}


@dataclass(frozen=True)
class Channel:
    name: str
    prefix: str
    kind: str
    weekdays: tuple[int, ...]   # Monday = 0
    gap: dt.timedelta
    scenes: tuple[int, int]     # number of slides, hook and call to action included


CHANNELS = (
    # Instagram: one reel a week (server cadence 1 / 168 h), on Wednesday evening.
    Channel("instagram", "ig", "reel", (2,), dt.timedelta(days=7), (5, 7)),
    # Facebook: two photo posts a week; the site inventory publishes exactly six photos per post.
    Channel("facebook", "fb", "carousel", (3, 6), dt.timedelta(days=3), (6, 6)),
)


class Held(ValueError):
    """This guide cannot make this post now; the next guide is tried."""


# --- the published guide -------------------------------------------------

class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.lines.append(" ".join(data.split()))


def page_text(raw_html: str) -> str:
    parser = _Text()
    parser.feed(raw_html)
    return "\n".join(parser.lines)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Held("guide_redirects")


def fetch_page(url: str) -> str:
    request = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=30) as response:
        if response.status != 200:
            raise Held("guide_unavailable")
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise Held("guide_page_too_large")
    return raw.decode("utf-8")


def guide_url(article: dict) -> str:
    return p.ORIGIN + article_path(article)


def snapshot(article: dict, fetcher) -> str:
    """Dated text of the live guide, first line = its URL; refuses a page that is not this guide."""
    url = guide_url(article)
    try:
        raw = fetcher(url)
    except (OSError, ValueError) as error:
        raise Held("guide_unavailable") from error
    if article["title"] not in html.unescape(raw):
        raise Held("guide_title_not_published")
    return url + "\n" + page_text(raw) + "\n"


# --- what goes on screen --------------------------------------------------

def checked(value, maximum):
    """The production text guard, as a filter: None when the charter would refuse it."""
    try:
        return p.text(value, maximum)
    except p.Invalid:
        return None


def section_text(section: dict) -> str:
    parts = [section.get("title", ""), section.get("tip", "")] + list(section.get("paragraphs", [])) + list(section.get("bullets", []))
    table = section.get("table") or {}
    parts += table.get("headers", []) + [cell for row in table.get("rows", []) for cell in row]
    return p.normalized(" ".join(str(part) for part in parts))


def significant(value: str) -> set[str]:
    return {w for w in re.findall(r"[\wÀ-ÿ]{5,}", destinations.ascii_fold(value).lower())}


def section_of(value: str, label: str, sections: list[dict]) -> dict | None:
    """The section that talks about this figure: most words shared with its label, the figure itself as a tie-break."""
    words, best, best_score = significant(label), None, 0
    for section in sections:
        text = section_text(section)
        score = 2 * len(words & significant(text)) + (p.normalized(value) in text)
        if score > best_score:
            best, best_score = section, score
    return best


def kicker_of(section: dict | None, fallback: str) -> str:
    """'Jour 3 — Belém en train' → 'Jour 3'; 'Le train : cinq villages' → 'Le train'."""
    if section:
        title = section.get("title", "")
        for separator in (" — ", " : ", " – ", ", ", " et "):
            head = title.split(separator, 1)[0].strip()
            if head != title and 3 <= len(head) <= 32 and checked(head, 32):
                return head
        if len(title) <= 32 and checked(title, 32):
            return title
    return fallback


def usable_facts(article: dict, text: str) -> list[dict]:
    """Key figures quoted word for word from the snapshot; one headline value each, never twice."""
    page, facts, values = p.normalized(text), [], set()
    for fact in article.get("keyFacts") or []:
        value, label = str(fact.get("value", "")).strip(), str(fact.get("label", "")).strip()
        if not value or not label or value.lower() in values or "*" in value + label:
            continue
        if not (checked("*" + value + "*", 34) and checked(label, 120)):
            continue
        # The figure and its label together: a label whose figure changed on the page is never shown.
        excerpt = value + " " + label
        if p.normalized(excerpt) not in page or not checked(excerpt, 400):
            continue
        section = section_of(value, label, article.get("sections", []))
        values.add(value.lower())
        facts.append({"value": value, "label": label, "excerpt": excerpt, "section": section})
    return facts


def opening_sentence(article: dict, text: str) -> str:
    """The guide's short answer, first sentence: the sourced promise of the hook scene."""
    page = p.normalized(text)
    first = re.split(r"(?<=[.!?])\s", article.get("summary", "").strip(), maxsplit=1)[0]
    for candidate in (first, article["title"]):
        if candidate and p.normalized(candidate) in page and checked(candidate, 400):
            return candidate
    raise Held("no_quotable_opening")


def lines_of(value: str, width: int = 34, most: int = 2) -> list[str] | None:
    """One line if it fits, else the most balanced split in two ('La côte amalfitaine / sans voiture')."""
    words = value.split()
    if len(value) <= width:
        return [value]
    splits = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
    fitting = [pair for pair in splits if max(map(len, pair)) <= width]
    if most < 2 or not fitting:
        return None
    return list(min(fitting, key=lambda pair: (max(map(len, pair)), -len(pair[0]))))


NBSP = "\u00a0"
UNIT = r"(?:h|min|€|km|m|%|jours?|nuits?|trains?|marches|ans|cm)(?!\w)"


def unbreakable(value: str) -> str:
    """Glue a figure to its unit and its next figure for the renderer: '1 h 37', '9 €', '3 047'."""
    value = re.sub(r"(?<=\d) (?=" + UNIT + r"|\d)", NBSP, value)
    return re.sub(r"(?<=\bh) (?=\d)", NBSP, value)


def caption_line(fact: dict) -> str:
    value, label = fact["value"], fact["label"]
    emoji = ("💶" if "€" in value else "⏱️" if re.search(r"\b(min|h|jours?)\b", value) else
             "🚆" if "train" in label.lower() else "⛴️" if re.search(r"ferry|bateau|rabelo", label.lower()) else
             "🥾" if re.search(r"marches|km|sentier", value + label) else "📍")
    joined = value + (" " if re.match(r"(?:de |d’|d')", label) else " : ") + label
    return emoji + " " + joined


def call_detail(article: dict) -> str | None:
    description = article.get("description", "").strip()
    tail = description.rsplit(" : ", 1)[-1].strip()
    for candidate in (tail, description):
        if 20 <= len(candidate) <= 120:
            candidate = candidate[:1].upper() + candidate[1:]
            if checked(candidate, 120):
                return candidate
    return None


# --- photos ---------------------------------------------------------------

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
        except (photo_intake.Refused, OSError, ValueError, KeyError):
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


# --- slots and history ----------------------------------------------------

def history(root: Path) -> list[dict]:
    """Every post already planned or queued: scenarios, then reviewed batches (older formats included)."""
    rows = []
    for path in sorted((root / "scenarios").glob("*.json")):
        scenario = json.loads(path.read_text())
        rows.append({"id": scenario["id"], "channel": scenario["channel"], "url": scenario["targetUrl"], "dueAt": p.instant(scenario["publishAt"])})
    index = root / "reviewed-social" / "index.json"
    if index.is_file():
        for entry in json.loads(index.read_text()).get("items", []):
            path = root / "reviewed-social" / Path(entry["path"]).name
            if not path.is_file():
                continue
            for item in json.loads(path.read_text()).get("items", []):
                url = (item.get("review", {}).get("destination") or {}).get("url")
                rows.append({"id": entry["batchId"], "channel": item["payload"]["channel"], "url": url, "dueAt": p.instant(item["dueAt"])})
    return rows


def next_slot(channel: Channel, rows: list[dict], now: dt.datetime) -> dt.datetime:
    last = max((row["dueAt"] for row in rows if row["channel"] == channel.name), default=None)
    earliest = max(now + MIN_LEAD, last + channel.gap if last else now)
    day = earliest.replace(hour=SLOT_HOUR, minute=0, second=0, microsecond=0)
    while day < earliest or day.weekday() not in channel.weekdays:
        day += dt.timedelta(days=1)
    return day


def covered_until(channel: Channel, rows: list[dict]) -> dt.datetime | None:
    return max((row["dueAt"] for row in rows if row["channel"] == channel.name), default=None)


def guide_order(articles: list[dict], channel: Channel, rows: list[dict], slot: dt.datetime) -> list[dict]:
    """Guides never posted anywhere first, then never on this channel (newest first each), then the longest unposted after a cooldown."""
    def posts(article, name=None):
        url = guide_url(article)
        return [row for row in rows if row["url"] == url and (name is None or row["channel"] == name)]

    fresh, again = [], []
    for article in articles:
        everywhere = posts(article)
        mine = posts(article, channel.name)
        if not mine:
            fresh.append((bool(everywhere), article))
        elif slot - max(row["dueAt"] for row in mine) >= REPOST_COOLDOWN:
            again.append((max(row["dueAt"] for row in mine), article))
    # A guide without publication date counts as the oldest: new destinations go out first.
    fresh.sort(key=lambda pair: (not pair[0], pair[1].get("publishedOn") or "", pair[1]["slug"]), reverse=True)
    ordered = [article for _, article in fresh] + [article for _, article in sorted(again, key=lambda pair: (pair[0], pair[1]["slug"]))]
    # The same guide on both networks a few days apart only when nothing else is available.
    close = lambda article: any(abs(row["dueAt"] - slot) < CROSS_CHANNEL_GAP for row in posts(article))
    return [x for x in ordered if not close(x)] + [x for x in ordered if close(x)]


# --- scenario -------------------------------------------------------------

def rotate(items: list, offset: int) -> list:
    return items[offset % len(items):] + items[:offset % len(items)] if items else items


def sha_of(root: Path, relative: str) -> str:
    return hashlib.sha256((root / relative).read_bytes()).hexdigest()


def sealed_assets(root: Path, kind: str, reel_number: int) -> tuple[dict, float | None]:
    assets = {}
    for key, asset in FONT_ASSETS.items():
        assets[key] = {**asset, "sha256": sha_of(root, asset["file"]),
                       "licenseFile": {**asset["licenseFile"], "sha256": sha_of(root, asset["licenseFile"]["file"])}}
    if kind != "reel":
        return assets, None
    track, start = MUSIC[reel_number % len(MUSIC)]
    provenance_file = f"evidence/{track}-provenance.json"
    provenance = json.loads((root / provenance_file).read_text())
    assets["music"] = {"file": f"assets/{track}.mp3", "sha256": sha_of(root, f"assets/{track}.mp3"), "license": "CC-BY-4.0",
                       "licenseUrl": "https://creativecommons.org/licenses/by/4.0/", "commercialUseAllowed": True,
                       "title": provenance["title"], "author": provenance["composer"], "sourceUrl": provenance["sourceTrackPage"],
                       "provenance": {"file": provenance_file, "sha256": sha_of(root, provenance_file)}}
    return assets, start


def french_date(value: str) -> str:
    return dt.date.fromisoformat(value).strftime("%d/%m/%Y")


def scenes_for(article: dict, channel: Channel, facts: list[dict], photos: list[tuple[str, dict, str]],
               opening: str, place: str, country: str, width: int = 34) -> list[dict]:
    count = min(channel.scenes[1], len(photos), len(facts) + 2)
    if count < channel.scenes[0]:
        raise Held("not_enough_photos_or_figures")
    facts = facts[:count - 2]
    tag = f"Guide {article['destination']} · sources du {french_date(article['sourcesCheckedOn'])}"
    if len(tag) > 52:
        tag = f"Notre guide · sources du {french_date(article['sourcesCheckedOn'])}"
    word = "chiffres" if all(re.search(r"\d", fact["value"]) for fact in facts) else "repères"
    title_lines = lines_of(article["shortTitle"], width) or lines_of(article["destination"], width)
    if not title_lines:
        raise Held("short_title_too_long")
    remaining = list(photos)

    def photo_for(section=None):
        wanted = section.get("image") if section else None
        pick = next((ph for ph in remaining if ph[0] == wanted), remaining[0])
        remaining.remove(pick)
        return pick

    def scene(photo, kicker, headline, detail, seconds, facts_=None, cta=False):
        value = {"photo": photo[0], "focus": [0.5, 0.5], "kicker": kicker, "headline": headline}
        if detail:
            value["detail"] = detail
        if facts_:
            value["facts"] = facts_
            value["tag"] = tag
        if channel.kind == "reel":
            value["seconds"] = seconds
        else:
            value["alt"] = photo[2]
        if cta:
            value["cta"] = True
        return value

    hook_kicker = place if country.lower() == place.lower() else f"{country} · {place}"
    hook_kicker = hook_kicker if len(hook_kicker) <= 32 else place[:32]
    scenes = [scene(photo_for(), hook_kicker, title_lines + [f"*{len(facts)} {word}* à connaître"],
                    unbreakable(opening) if len(opening) <= 120 else None, 3.5, [{"source": "guide", "excerpt": opening}])]
    for fact in facts:
        scenes.append(scene(photo_for(fact["section"]), kicker_of(fact["section"], place), ["*" + fact["value"] + "*"],
                            unbreakable(fact["label"]), 4, [{"source": "guide", "excerpt": fact["excerpt"]}]))
    scenes.append(scene(photo_for(), "Le guide complet", title_lines, call_detail(article), 4.5, cta=True))
    return scenes


def build(root: Path, article: dict, channel: Channel, slot: dt.datetime, now: dt.datetime, text: str,
          photos: list[tuple[str, dict, str]], variant: int, reel_number: int, table: dict, width: int = 34) -> tuple[dict, dict]:
    """The scenario and its frozen inputs (relative path → content)."""
    country = destinations.name(destinations.country_slug(article), table)
    place = article["destination"] if len(article["destination"]) <= 22 else country
    facts = rotate(usable_facts(article, text), variant)
    photos = rotate(photos, variant)
    scenes = scenes_for(article, channel, facts, photos, opening_sentence(article, text), place, country, width)
    used = scenes[1:-1]
    identity = f"{channel.prefix}-{article['slug'][:70]}-{slot:%Y-%m-%d}"
    folder = f"{AUTO}/{identity}"
    stamp = p.stamp(now)
    url = guide_url(article)
    registry = {"schemaVersion": 1, "checkedOn": now.date().isoformat(),
                "method": "Page publiée du guide relevée automatiquement ; texte visible conservé tel quel, première ligne = URL.",
                "sources": {"guide": {"url": url, "publisher": "Voyage Sans Détour", "title": article["title"][:200],
                                      "retrievedAt": stamp, "snapshot": {"file": f"{folder}/guide.txt", "sha256": p.digest(text.encode())}}}}
    chosen = {photo_id: record for photo_id, record, _ in photos if photo_id in {s["photo"] for s in scenes}}
    catalogue = {"schemaVersion": 1, "photos": dict(sorted(chosen.items()))}
    inputs = {f"{folder}/guide.txt": text.encode(), f"{folder}/sources.json": json_bytes(registry), f"{folder}/photos.json": json_bytes(catalogue)}
    assets, start = sealed_assets(root, channel.kind, reel_number)
    emoji = CATEGORY_EMOJI.get(destinations.ascii_fold(article.get("category", "")).lower(), "✈️")
    hook = next(h for h in (f"{emoji} {article['title']}", f"{emoji} {article['shortTitle']} : {len(used)} repères avant de partir.") if len(h) <= 150)
    if channel.name == "instagram":
        cta = "🔗 Tous les prix, horaires et l’itinéraire : le guide complet est en lien dans la bio."
    else:
        cta = "🔗 Tous les prix, horaires et l’itinéraire dans le guide complet :"
    facts_used = [next(f for f in facts if "*" + f["value"] + "*" == s["headline"][0]) for s in used]
    scenario = {
        "schemaVersion": p.SCHEMA, "id": identity, "kind": channel.kind, "channel": channel.name,
        "destination": place, "title": f"{article['shortTitle']} : {len(used)} repères"[:150], "targetUrl": url,
        "publishAt": p.stamp(slot),
        "review": {"status": "reviewed_for_render", "checkedAt": stamp, "validUntil": p.stamp(now + REVIEW_VALIDITY),
                   "method": "Généré automatiquement (auto_social.py) depuis la page publiée du guide relevée le "
                             f"{now:%d/%m/%Y} : chaque chiffre est cité mot pour mot ; photos réelles sous licence libre "
                             "(Wikimedia Commons), aucune image générée par IA ; garde-fous de production.py passés avant la mise en file."},
        "sources": {"file": f"{folder}/sources.json", "sha256": p.digest(inputs[f"{folder}/sources.json"])},
        "photos": {"file": f"{folder}/photos.json", "sha256": p.digest(inputs[f"{folder}/photos.json"])},
        "caption": {"hook": hook, "lines": [caption_line(f) for f in facts_used][:5], "cta": cta,
                    "hashtags": destinations.hashtags(article, table)},
        "scenes": scenes,
    }
    if start is not None:
        scenario["musicStart"] = start
    scenario["assets"] = assets
    return scenario, inputs


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


# --- run ------------------------------------------------------------------

def write_new(root: Path, files: dict[str, bytes]) -> list[Path]:
    written = []
    for relative, raw in files.items():
        path = root / relative
        p.ensure(not path.exists(), "Refusing to overwrite an existing file: " + relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        written.append(path)
    return written


def remove(paths: list[Path]) -> None:
    for path in paths:
        if path.is_file():
            path.unlink()
    for path in paths:
        if path.parent.is_dir() and not any(path.parent.iterdir()):
            path.parent.rmdir()


def qualify(root: Path, scenario: dict, now: dt.datetime) -> None:
    """Exactly the checks production.py runs before rendering, layout included."""
    info = p.validate_scenario(scenario, root, now)
    size, carousel = (p.draw.SLIDE_SIZE, True) if scenario["kind"] == "carousel" else (p.draw.REEL_SIZE, False)
    p.prepared_scenes(scenario, root, info, size, carousel)
    p.caption(scenario, info)


def add_to_catalogue(root: Path, scenario: dict, relative: str) -> None:
    path = root / "catalogue.json"
    catalogue = json.loads(path.read_text())
    p.ensure(all(item["contentId"] != scenario["id"] for item in catalogue["items"]), "Scenario already catalogued")
    entry = {"contentId": scenario["id"], "notBefore": scenario["review"]["checkedAt"], "file": relative, "sha256": sha_of(root, relative)}
    items = sorted(catalogue["items"] + [entry], key=lambda item: (item["notBefore"], item["contentId"]))
    path.write_text(json.dumps({**catalogue, "items": items}, ensure_ascii=False, indent=2) + "\n")


def eligible_articles(articles: list[dict], now: dt.datetime) -> tuple[list[dict], list[dict]]:
    keep, held = [], []
    for article in articles:
        if not all(isinstance(article.get(key), str) and article[key] for key in ("slug", "title", "shortTitle", "destination", "sourcesCheckedOn")):
            held.append({"slug": article.get("slug"), "reason": "incomplete_guide"}); continue
        checked_on = dt.datetime.fromisoformat(article["sourcesCheckedOn"]).replace(tzinfo=dt.timezone.utc)
        if now - checked_on > MAX_GUIDE_SOURCE_AGE:
            held.append({"slug": article["slug"], "reason": "guide_sources_older_than_45_days"}); continue
        keep.append(article)
    return keep, held


def make_post(root, article, channel, slot, now, rows, texts, photos, site_photos, table, fetcher, searcher) -> dict:
    """One qualified scenario in the catalogue, or Held with the reason."""
    if article["slug"] not in texts:
        texts[article["slug"]] = snapshot(article, fetcher)
    text = texts[article["slug"]]
    if len(usable_facts(article, text)) < channel.scenes[0] - 2:
        raise Held("not_enough_quotable_figures")
    country = destinations.name(destinations.country_slug(article), table)
    chosen = gather_photos(article, channel.scenes[1], photos, site_photos, country, searcher)
    variant = sum(1 for row in rows if row["url"] == guide_url(article) and row["channel"] == channel.name)
    reels = sum(1 for row in rows if row["channel"] == "instagram")
    for width in TITLE_WIDTHS:
        scenario, inputs = build(root, article, channel, slot, now, text, chosen, variant, reels, table, width)
        relative = f"scenarios/{scenario['id']}.json"
        written = write_new(root, {**inputs, relative: json_bytes(scenario)})
        try:
            qualify(root, scenario, now)
        except p.Invalid as error:
            remove(written)
            # A title too wide for the frame is broken into shorter lines; any other refusal is final.
            if "Layout overflow" in str(error) and width != TITLE_WIDTHS[-1]:
                continue
            raise Held("guard: " + str(error)[:160]) from error
        add_to_catalogue(root, scenario, relative)
        return scenario
    raise Held("layout")


def generate(root: Path = HERE, site: Path = SITE, now: dt.datetime | None = None, *, fetcher=fetch_page,
             searcher=photo_intake.commons_search, downloader=None, limit: int = MAX_NEW_PER_RUN) -> dict:
    root, site = Path(root), Path(site)
    now = (now or p.utcnow()).astimezone(dt.timezone.utc).replace(microsecond=0)
    if now > p.HARD_STOP - MAX_LEAD:
        return {"status": "period_ended", "created": []}
    articles, held = eligible_articles(json.loads((site / "articles.json").read_text()), now)
    site_photos = {photo["id"]: photo for photo in json.loads((site / "image-sources.json").read_text())["photos"]}
    table = destinations.load(site)
    rows, created, texts = history(root), [], {}
    photos = Photos(root, now, downloader)
    for channel in CHANNELS:
        while len(created) < limit:
            last = covered_until(channel, rows)
            slot = next_slot(channel, rows, now)
            if (last and last >= now + HORIZON) or slot > now + MAX_LEAD:
                break
            made = None
            for article in guide_order(articles, channel, rows, slot):
                try:
                    made = make_post(root, article, channel, slot, now, rows, texts, photos, site_photos, table, fetcher, searcher)
                    break
                except Held as error:
                    held.append({"slug": article["slug"], "channel": channel.name, "reason": str(error)})
            if not made:
                break
            rows.append({"id": made["id"], "channel": channel.name, "url": made["targetUrl"], "dueAt": slot})
            created.append({"id": made["id"], "channel": channel.name, "publishAt": made["publishAt"], "guide": made["targetUrl"]})
    used = {record["file"] for path in (root / AUTO).glob("*/photos.json") for record in json.loads(path.read_text())["photos"].values()}
    remove([path for path in photos.created if path.relative_to(root).as_posix() not in used])
    coverage = {channel.name: covered_until(channel, rows) for channel in CHANNELS}
    short = [name for name, value in coverage.items() if not value or value < now + HORIZON]
    return {"status": "queue_short" if short else ("created" if created else "queue_covered"), "created": created,
            "coveredUntil": {name: p.stamp(value) if value else None for name, value in coverage.items()},
            "shortChannels": short, "held": held}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=MAX_NEW_PER_RUN)
    args = parser.parse_args()
    print(json.dumps(generate(limit=args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
