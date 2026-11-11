#!/usr/bin/env python3
"""Turn every published guide, from any country, into Instagram reels and carousels and Facebook photo posts.

Unattended and bounded. Every free slot of cadence.json (Paris time) within three
weeks gets a post built from one published guide:
- the live guide page is snapshotted (dated, first line = URL): every figure on
  screen is quoted word for word from it (its "L'essentiel en chiffres" block,
  its section titles, its tables);
- a reel takes the format that suits the guide (docs/strategie-videos.md): price
  first for a budget, day by day for an itinerary, a table to pause for "when to
  go", a fast numbered list otherwise; a second reel of the same guide takes
  another format;
- the photos are the guide's own free Commons photos, completed when needed by
  Commons featured pictures of the place; real video plans are added when a free
  clip names the place; never an AI-generated image or video;
- the scenario is frozen with its own inputs (auto/<id>/: snapshot, source
  registry, photo and clip records), validated by production.py's guards and
  layout before it enters catalogue.json. Nothing already written is ever modified.
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
from zoneinfo import ZoneInfo

import clip_intake
import destinations
from media_library import AUTO, AUTO_PHOTOS, Clips, Photos, gather_photos
import motion_render
from paths import article_path
import photo_intake
import production as p
import reel_formats
from reel_formats import Held, caption_line, checked, kicker_of, lines_of, unbreakable

HERE = Path(__file__).resolve().parent
SITE = HERE.parents[1] / "site-src"
CADENCE_FILE = "cadence.json"
HORIZON = dt.timedelta(days=21)        # every free slot of the next three weeks is filled
MIN_LEAD = dt.timedelta(days=2)        # time to render, deploy and import before the slot
MAX_LEAD = dt.timedelta(days=29)       # a source snapshot is valid 30 days (production.SOURCE_VALIDITY)
WEEK = dt.timedelta(days=7)
REVIEW_VALIDITY = dt.timedelta(days=30)
REPOST_COOLDOWN = dt.timedelta(days=42)
CROSS_CHANNEL_GAP = dt.timedelta(days=4)
MAX_GUIDE_SOURCE_AGE = dt.timedelta(days=45)
MAX_NEW_PER_RUN = 6                    # what one workflow run renders
CAPTION_MAX = 1000                     # a short, lively caption: past this, detail lines are dropped (never under three)
TITLE_WIDTHS = (34, 24, 18)            # characters per headline line, tried in turn until the layout fits
REEL_TITLE_WIDTHS = (16, 20, 25)       # a reel hook is read in a second: two short lines in large type first
USER_AGENT = {"User-Agent": "VoyageSansDetour-social/1.0 (contact@voyagesansdetour.fr)"}
FONT_ASSETS = {
    "regular": {"file": "assets/dmsans-regular.ttf", "license": "OFL-1.1", "licenseFile": {"file": "assets/dmsans-OFL.txt"}},
    "bold": {"file": "assets/dmsans-bold.ttf", "license": "OFL-1.1", "licenseFile": {"file": "assets/dmsans-OFL.txt"}},
    "serif": {"file": "assets/playfair.ttf", "license": "OFL-1.1", "licenseFile": {"file": "assets/playfairdisplay-OFL.txt"}},
}
# Noto Sans draws what DM Sans lacks (₫, Vietnamese and Polish letters…): no empty box on screen.
FALLBACK_FONT_ASSETS = {
    "fallbackRegular": {"file": "assets/notosans-regular.ttf", "license": "OFL-1.1", "licenseFile": {"file": "assets/notosans-OFL.txt"}},
    "fallbackBold": {"file": "assets/notosans-bold.ttf", "license": "OFL-1.1", "licenseFile": {"file": "assets/notosans-OFL.txt"}},
}
# Upbeat CC BY 4.0 tracks already qualified (provenance in evidence/), with the second the extract starts at.
MUSIC = (("happy-alley", 8), ("carefree", 1), ("almost-bliss", 0), ("ascending-the-vale", 0))
CATEGORY_EMOJI = {"itineraires": "🗺️", "transports": "🚆", "excursions": "🌄", "quartiers": "🏘️", "choisir": "🤔",
                  "preparer": "🎒", "budget": "💶", "quand partir": "📅", "road trip": "🚗", "road trips": "🚗"}


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
PREFIXES = {("instagram", "reel"): "ig", ("instagram", "carousel"): "igc", ("facebook", "carousel"): "fb"}
# The site inventory publishes exactly six photos per photo post; a reel needs a hook, a call and one fact at least.
SCENES = {"reel": (3, 8), "carousel": (6, 6)}
# Used when cadence.json is absent (tests): what the publication panel accepts today, two posts per network per week.
DEFAULT_CADENCE = {
    "schemaVersion": 1, "timezone": "Europe/Paris",
    "channels": {
        "instagram": {"weeklyLimit": 2, "minGapHours": 40, "slots": [{"weekday": "tuesday", "time": "19:00", "kind": "reel"},
                                                                      {"weekday": "sunday", "time": "21:00", "kind": "reel"}]},
        "facebook": {"weeklyLimit": 2, "minGapHours": 60, "slots": [{"weekday": "thursday", "time": "18:00", "kind": "carousel"},
                                                                     {"weekday": "sunday", "time": "18:00", "kind": "carousel"}]},
    },
    "clips": {"providers": [], "perReel": 2},
}


@dataclass(frozen=True)
class Slot:
    weekday: int                # Monday = 0
    hour: int
    minute: int
    kind: str


@dataclass(frozen=True)
class Channel:
    name: str
    weekly_limit: int
    gap: dt.timedelta
    slots: tuple[Slot, ...]
    zone: ZoneInfo


@dataclass(frozen=True)
class Post:
    """What one post is: its network, its kind, and how many scenes it needs."""
    name: str
    kind: str

    @property
    def prefix(self) -> str:
        return PREFIXES[(self.name, self.kind)]

    @property
    def scenes(self) -> tuple[int, int]:
        return SCENES[self.kind]


@dataclass(frozen=True)
class Cadence:
    channels: tuple[Channel, ...]
    clip_providers: tuple[str, ...]
    clips_per_reel: int


def load_cadence(root: Path) -> Cadence:
    """Slots in local time, per network. A slot marked "enabled": false is documented but not used yet."""
    path = Path(root) / CADENCE_FILE
    raw = json.loads(path.read_text()) if path.is_file() else DEFAULT_CADENCE
    p.ensure(raw.get("schemaVersion") == 1 and isinstance(raw.get("channels"), dict), "Invalid cadence file")
    zone = ZoneInfo(raw.get("timezone", "Europe/Paris"))
    channels = []
    for name, entry in raw["channels"].items():
        slots = []
        for slot in entry.get("slots", []):
            match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", str(slot.get("time", "")))
            p.ensure(match and slot.get("weekday") in WEEKDAYS and (name, slot.get("kind")) in PREFIXES, "Invalid cadence slot for " + name)
            if slot.get("enabled", True):
                slots.append(Slot(WEEKDAYS.index(slot["weekday"]), int(match[1]), int(match[2]), slot["kind"]))
        limit, gap = entry.get("weeklyLimit"), entry.get("minGapHours")
        p.ensure(type(limit) is int and 0 <= limit <= 14 and type(gap) in (int, float) and 12 <= gap <= 168, "Invalid cadence limits for " + name)
        channels.append(Channel(name, limit, dt.timedelta(hours=gap), tuple(slots), zone))
    clips = raw.get("clips", {})
    providers = tuple(provider for provider in clips.get("providers", []) if provider in clip_intake.SOURCE_HOSTS)
    return Cadence(tuple(channels), providers, int(clips.get("perReel", 2)))


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


def drawable(root: Path, value: str) -> bool:
    """Every character has a glyph in the brand font or its fallback: nothing shows as an empty box."""
    fonts = [str(Path(root) / asset["file"]) for asset in (FONT_ASSETS["bold"], FALLBACK_FONT_ASSETS["fallbackBold"])]
    return all(any(motion_render.has_glyph(font, char) for font in fonts) for char in value)


def usable_facts(article: dict, text: str, root: Path = HERE) -> list[dict]:
    """Key figures quoted word for word from the snapshot; one headline value each, never twice."""
    page, facts, values = p.normalized(text), [], set()
    for fact in (f for f in article.get("keyFacts") or [] if isinstance(f, dict)):
        value, label = str(fact.get("value", "")).strip(), str(fact.get("label", "")).strip()
        if not value or not label or value.lower() in values or "*" in value + label:
            continue
        if not (checked("*" + value + "*", 34) and checked(label, 120) and drawable(root, value + label)):
            continue
        # The figure and its label together: a label whose figure changed on the page is never shown.
        excerpt = value + " " + label
        if p.normalized(excerpt) not in page or not checked(excerpt, 400):
            continue
        section = section_of(value, label, article.get("sections", []))
        values.add(value.lower())
        # Reels show the label up to its first natural pause: a prefix of the quote, so still the page's own words.
        short = reel_formats.short_label(label)
        facts.append({"value": value, "label": label, "excerpt": excerpt, "section": section, "short": short, "shortExcerpt": value + " " + short})
    return facts


def opening_sentence(article: dict, text: str) -> str:
    """The guide's short answer, first sentence: the sourced promise of the hook scene."""
    page = p.normalized(text)
    first = re.split(r"(?<=[.!?])\s", article.get("summary", "").strip(), maxsplit=1)[0]
    for candidate in (first, article["title"]):
        if candidate and p.normalized(candidate) in page and checked(candidate, 400):
            return candidate
    raise Held("no_quotable_opening")


def call_detail(article: dict) -> str | None:
    description = article.get("description", "").strip()
    tail = description.rsplit(" : ", 1)[-1].strip()
    for candidate in (tail, description):
        if 20 <= len(candidate) <= 120:
            candidate = candidate[:1].upper() + candidate[1:]
            if checked(candidate, 120):
                return candidate
    return None


# --- slots and history ----------------------------------------------------

def history(root: Path) -> list[dict]:
    """Every post already planned or queued: scenarios, then reviewed batches (older formats included)."""
    rows = []
    for path in sorted((root / "scenarios").glob("*.json")):
        scenario = json.loads(path.read_text())
        rows.append({"id": scenario["id"], "channel": scenario["channel"], "kind": scenario["kind"], "format": scenario.get("format"),
                     "url": scenario["targetUrl"], "dueAt": p.instant(scenario["publishAt"])})
    index = root / "reviewed-social" / "index.json"
    if index.is_file():
        for entry in json.loads(index.read_text()).get("items", []):
            path = root / "reviewed-social" / Path(entry["path"]).name
            if not path.is_file():
                continue
            for item in json.loads(path.read_text()).get("items", []):
                url = (item.get("review", {}).get("destination") or {}).get("url")
                kind = "reel" if item["payload"].get("kind") in ("reel", "video") else "carousel"
                rows.append({"id": entry["batchId"], "channel": item["payload"]["channel"], "kind": kind, "format": None, "url": url,
                             "dueAt": p.instant(item["dueAt"])})
    return rows


def slot_instants(channel: Channel, start: dt.datetime, end: dt.datetime) -> list[tuple[dt.datetime, str]]:
    """The channel's weekly slots between two instants, in UTC; local time follows summer and winter time."""
    found, day = [], start.astimezone(channel.zone).date()
    while day <= end.astimezone(channel.zone).date():
        for slot in channel.slots:
            if day.weekday() == slot.weekday:
                at = dt.datetime(day.year, day.month, day.day, slot.hour, slot.minute, tzinfo=channel.zone).astimezone(dt.timezone.utc)
                if start <= at <= end:
                    found.append((at, slot.kind))
        day += dt.timedelta(days=1)
    return sorted(found)


def open_slots(channel: Channel, rows: list[dict], now: dt.datetime) -> list[tuple[dt.datetime, str]]:
    """Free slots of the next three weeks: far enough from every queued post, never above the weekly limit."""
    # A post appears twice in the history once it is queued (its scenario and its reviewed batch): count each instant once.
    taken = sorted({row["dueAt"] for row in rows if row["channel"] == channel.name})
    free = []
    for at, kind in slot_instants(channel, now + MIN_LEAD, now + min(HORIZON, MAX_LEAD)):
        if any(abs(at - other) < channel.gap for other in taken):
            continue
        # The publication panel counts posts over any seven days: no window that would hold the new post may pass the limit.
        nearby = [other for other in taken if abs(other - at) < WEEK] + [at]
        if any(sum(first <= other < first + WEEK for other in nearby) > channel.weekly_limit for first in nearby if first <= at):
            continue
        free.append((at, kind))
        taken.append(at)
    return free


def covered_until(name: str, rows: list[dict]) -> dt.datetime | None:
    return max((row["dueAt"] for row in rows if row["channel"] == name), default=None)


def guide_order(articles: list[dict], post: Post, rows: list[dict], slot: dt.datetime) -> list[dict]:
    """Guides never posted anywhere first, then never in this form on this network (newest first each), then the longest unposted after a cooldown."""
    def posts(article, mine=False):
        url = guide_url(article)
        return [row for row in rows if row["url"] == url and (not mine or (row["channel"], row["kind"]) == (post.name, post.kind))]

    fresh, again = [], []
    for article in articles:
        everywhere = posts(article)
        mine = posts(article, mine=True)
        if not mine:
            fresh.append((bool(everywhere), article))
        elif slot - max(row["dueAt"] for row in mine) >= REPOST_COOLDOWN:
            again.append((max(row["dueAt"] for row in mine), article))
    # A guide without publication date counts as the oldest: new destinations go out first.
    fresh.sort(key=lambda pair: (not pair[0], pair[1].get("publishedOn") or "", pair[1]["slug"]), reverse=True)
    ordered = [article for _, article in fresh] + [article for _, article in sorted(again, key=lambda pair: (pair[0], pair[1]["slug"]))]
    # The same guide twice within a few days, on any network, only when nothing else is available.
    close = lambda article: any(abs(row["dueAt"] - slot) < CROSS_CHANNEL_GAP for row in posts(article))
    return [x for x in ordered if not close(x)] + [x for x in ordered if close(x)]


# --- scenario -------------------------------------------------------------

def rotate(items: list, offset: int) -> list:
    return items[offset % len(items):] + items[:offset % len(items)] if items else items


def sha_of(root: Path, relative: str) -> str:
    return hashlib.sha256((root / relative).read_bytes()).hexdigest()


def sealed_assets(root: Path, kind: str, reel_number: int) -> tuple[dict, float | None]:
    assets = {}
    for key, asset in {**FONT_ASSETS, **FALLBACK_FONT_ASSETS}.items():
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


def scenes_for(article: dict, channel: Post, facts: list[dict], photos: list[tuple[str, dict, str]],
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


def build(root: Path, article: dict, channel: Post, slot: dt.datetime, now: dt.datetime, text: str,
          photos: list[tuple[str, dict, str]], variant: int, reel_number: int, table: dict, width: int = 34) -> tuple[dict, dict]:
    """The scenario and its frozen inputs (relative path → content)."""
    country = destinations.name(destinations.country_slug(article), table)
    place = article["destination"] if len(article["destination"]) <= 22 else country
    facts = rotate(usable_facts(article, text, root), variant)
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
    hook = next((h for h in (f"{emoji} {article['title']}", f"{emoji} {article['shortTitle']} : {len(used)} repères avant de partir.") if len(h) <= 150), f"{emoji} {article['shortTitle']}"[:150])
    if channel.name == "instagram":
        cta = "📌 Enregistrez ce carrousel pour votre voyage. 🔗 Prix, horaires et détails : le guide complet est en lien dans la bio."
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
    return fitted_caption(scenario, {}), inputs


def fitted_caption(scenario: dict, clips: dict) -> dict:
    """The scenario with its written caption within CAPTION_MAX: detail lines are dropped from the end, never under three."""
    lines = scenario["caption"]["lines"]
    for count in range(len(lines), p.CAPTION_LINES[0] - 1, -1):
        candidate = scenario if count == len(lines) else {**scenario, "caption": {**scenario["caption"], "lines": lines[:count]}}
        if len(p.caption(candidate, {"clips": clips})) <= CAPTION_MAX:
            return candidate
    raise Held("caption_too_long")


def reel_title_lines(article: dict, width: int) -> list[str]:
    lines = lines_of(article["shortTitle"], width) or lines_of(article["destination"], width)
    if not lines:
        raise Held("short_title_too_long")
    return lines


def build_reel(root: Path, article: dict, slot: dt.datetime, now: dt.datetime, text: str, photos: list[tuple[str, dict, str]],
               clips: list[tuple[str, dict]], fmt: str, variant: int, reel_number: int, table: dict, width: int) -> tuple[dict, dict]:
    """A fast reel (schema 3) in one format, and its frozen inputs (relative path → content)."""
    country = destinations.name(destinations.country_slug(article), table)
    place = article["destination"] if len(article["destination"]) <= 22 else country
    facts = rotate(usable_facts(article, text, root), variant)
    tag = f"Guide {article['destination']} · sources du {french_date(article['sourcesCheckedOn'])}"
    if len(tag) > 52:
        tag = f"Notre guide · sources du {french_date(article['sourcesCheckedOn'])}"
    kicker = place if country.lower() == place.lower() else f"{country} · {place}"
    kicker = kicker if len(kicker) <= 32 else place[:32]
    scenes, lines = reel_formats.build(fmt, article, facts, rotate(photos, variant), clips, opening_sentence(article, text), place, kicker, tag,
                                       reel_title_lines(article, width), p.normalized(text))
    identity = f"ig-{article['slug'][:70]}-{slot:%Y-%m-%d}"
    folder = f"{AUTO}/{identity}"
    stamp = p.stamp(now)
    url = guide_url(article)
    registry = {"schemaVersion": 1, "checkedOn": now.date().isoformat(),
                "method": "Page publiée du guide relevée automatiquement ; texte visible conservé tel quel, première ligne = URL.",
                "sources": {"guide": {"url": url, "publisher": "Voyage Sans Détour", "title": article["title"][:200],
                                      "retrievedAt": stamp, "snapshot": {"file": f"{folder}/guide.txt", "sha256": p.digest(text.encode())}}}}
    used_photos = {scene["photo"] for scene in scenes if "photo" in scene}
    used_clips = {scene["clip"] for scene in scenes if "clip" in scene}
    catalogue = {"schemaVersion": 1, "photos": dict(sorted((photo_id, record) for photo_id, record, _ in photos if photo_id in used_photos))}
    inputs = {f"{folder}/guide.txt": text.encode(), f"{folder}/sources.json": json_bytes(registry), f"{folder}/photos.json": json_bytes(catalogue)}
    if used_clips:
        inputs[f"{folder}/clips.json"] = json_bytes({"schemaVersion": 1, "clips": dict(sorted((clip_id, record) for clip_id, record in clips if clip_id in used_clips))})
    assets, start = sealed_assets(root, "reel", reel_number)
    emoji = CATEGORY_EMOJI.get(destinations.ascii_fold(article.get("category", "")).lower(), "✈️")
    label = reel_formats.FORMAT_LABELS[fmt]
    hook = next((h for h in (f"{emoji} {article['title']}", f"{emoji} {article['shortTitle']} : {label}.") if len(h) <= 150), f"{emoji} {article['shortTitle']}"[:150])
    scenario = {
        "schemaVersion": p.MOTION_SCHEMA, "id": identity, "kind": "reel", "channel": "instagram", "format": fmt,
        "destination": place, "title": f"{article['shortTitle']} : {label}"[:150], "targetUrl": url,
        "publishAt": p.stamp(slot),
        "review": {"status": "reviewed_for_render", "checkedAt": stamp, "validUntil": p.stamp(now + REVIEW_VALIDITY),
                   "method": "Généré automatiquement (auto_social.py) depuis la page publiée du guide relevée le "
                             f"{now:%d/%m/%Y} : chaque chiffre, étape ou ligne de tableau est cité mot pour mot ; photos et vidéos "
                             "réelles sous licence libre, aucune image ni vidéo générée par IA ; garde-fous de production.py passés avant la mise en file."},
        "sources": {"file": f"{folder}/sources.json", "sha256": p.digest(inputs[f"{folder}/sources.json"])},
        "photos": {"file": f"{folder}/photos.json", "sha256": p.digest(inputs[f"{folder}/photos.json"])},
        "caption": {"hook": hook, "lines": lines,
                    "cta": "📌 Enregistrez ce reel pour votre voyage. 🔗 Prix, horaires et détails : le guide complet est en lien dans la bio.",
                    "hashtags": destinations.hashtags(article, table)},
        "scenes": scenes, "musicStart": start, "assets": assets,
    }
    if used_clips:
        scenario["clips"] = {"file": f"{folder}/clips.json", "sha256": p.digest(inputs[f"{folder}/clips.json"])}
    return fitted_caption(scenario, {clip_id: record for clip_id, record in clips if clip_id in used_clips}), inputs


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
    # Written beside, then moved in place: an interrupted run never leaves half a catalogue.
    draft = path.with_name(path.name + ".new")
    draft.write_text(json.dumps({**catalogue, "items": items}, ensure_ascii=False, indent=2) + "\n")
    draft.replace(path)


def eligible_articles(articles: list[dict], now: dt.datetime) -> tuple[list[dict], list[dict]]:
    keep, held = [], []
    for article in articles:
        if not all(isinstance(article.get(key), str) and article[key] for key in ("slug", "title", "shortTitle", "destination", "sourcesCheckedOn")):
            held.append({"slug": article.get("slug"), "reason": "incomplete_guide"}); continue
        try:
            checked_on = dt.datetime.fromisoformat(article["sourcesCheckedOn"]).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            held.append({"slug": article["slug"], "reason": "incomplete_guide"}); continue
        if now - checked_on > MAX_GUIDE_SOURCE_AGE:
            held.append({"slug": article["slug"], "reason": "guide_sources_older_than_45_days"}); continue
        keep.append(article)
    return keep, held


def commit(root: Path, scenario: dict, inputs: dict, now: dt.datetime) -> None:
    """Write a scenario with its inputs and keep it only if every production guard accepts it."""
    relative = f"scenarios/{scenario['id']}.json"
    written = write_new(root, {**inputs, relative: json_bytes(scenario)})
    try:
        qualify(root, scenario, now)
        add_to_catalogue(root, scenario, relative)
    except Exception:
        # Whatever stops a post (a guard, a missing file, a full disk), nothing of it stays behind:
        # an orphan scenario would count as a taken slot and block its own identity for ever.
        remove(written)
        raise


def make_reel(root, article, slot, now, rows, text, chosen, clips, table) -> dict:
    """The first format of the guide that passes every guard; a format already used for this guide comes last."""
    facts = usable_facts(article, text, root)
    mine = sorted((row for row in rows if row["url"] == guide_url(article) and (row["channel"], row["kind"]) == ("instagram", "reel")), key=lambda row: row["dueAt"])
    formats = reel_formats.ordered(reel_formats.applicable(article, facts, p.normalized(text)), [row["format"] for row in mine if row.get("format")])
    reels = sum(1 for row in rows if (row["channel"], row["kind"]) == ("instagram", "reel"))
    reason = "no_format"
    for fmt in formats:
        for width in REEL_TITLE_WIDTHS:
            try:
                scenario, inputs = build_reel(root, article, slot, now, text, chosen, clips, fmt, len(mine), reels, table, width)
                commit(root, scenario, inputs, now)
                return scenario
            except Held as error:
                reason = str(error)
                break
            except p.Invalid as error:
                reason = "guard: " + str(error)[:160]
                # A title too wide for the frame is broken into shorter lines; any other refusal moves to the next format.
                if "Headline too long" not in str(error):
                    break
    raise Held(reason)


def make_post(root, article, post, slot, now, rows, texts, photos, clips, site_photos, table, fetcher, searcher) -> dict:
    """One qualified scenario in the catalogue, or Held with the reason."""
    if article["slug"] not in texts:
        texts[article["slug"]] = snapshot(article, fetcher)
    text = texts[article["slug"]]
    if len(usable_facts(article, text, root)) < 2:
        raise Held("not_enough_quotable_figures")
    country = destinations.name(destinations.country_slug(article), table)
    chosen = gather_photos(article, post.scenes[1], photos, site_photos, country, searcher)
    if post.kind == "reel":
        return make_reel(root, article, slot, now, rows, text, chosen, clips.gather(article), table)
    if len(usable_facts(article, text, root)) < post.scenes[0] - 2:
        raise Held("not_enough_quotable_figures")
    variant = sum(1 for row in rows if row["url"] == guide_url(article) and (row["channel"], row["kind"]) == (post.name, post.kind))
    for width in TITLE_WIDTHS:
        scenario, inputs = build(root, article, post, slot, now, text, chosen, variant, 0, table, width)
        try:
            commit(root, scenario, inputs, now)
        except p.Invalid as error:
            # A title too wide for the frame is broken into shorter lines; any other refusal is final.
            if "Layout overflow" in str(error) and width != TITLE_WIDTHS[-1]:
                continue
            raise Held("guard: " + str(error)[:160]) from error
        return scenario
    raise Held("layout")


def generate(root: Path = HERE, site: Path = SITE, now: dt.datetime | None = None, *, fetcher=fetch_page,
             searcher=photo_intake.commons_search, downloader=None, clip_finder=None, clip_downloader=None,
             limit: int = MAX_NEW_PER_RUN) -> dict:
    root, site = Path(root), Path(site)
    now = (now or p.utcnow()).astimezone(dt.timezone.utc).replace(microsecond=0)
    if now > p.HARD_STOP - MAX_LEAD:
        return {"status": "period_ended", "created": []}
    cadence = load_cadence(root)
    articles, held = eligible_articles(json.loads((site / "articles.json").read_text()), now)
    site_photos = {photo["id"]: photo for photo in json.loads((site / "image-sources.json").read_text())["photos"]}
    table = destinations.load(site)
    rows, created, texts, short = history(root), [], {}, []
    photos = Photos(root, now, downloader)
    clips = Clips(root, now, cadence, clip_finder, clip_downloader)
    for channel in cadence.channels:
        exhausted = set()                # kinds for which no guide is left: later slots of that kind are not retried
        for slot, kind in open_slots(channel, rows, now):
            if len(created) >= limit:
                break
            if kind in exhausted:
                continue
            post, made = Post(channel.name, kind), None
            for article in guide_order(articles, post, rows, slot):
                try:
                    made = make_post(root, article, post, slot, now, rows, texts, photos, clips, site_photos, table, fetcher, searcher)
                    break
                except Held as error:
                    held.append({"slug": article["slug"], "channel": channel.name, "kind": kind, "reason": str(error)})
                except (OSError, ValueError, KeyError, TypeError) as error:  # a guard refusal (p.Invalid) is a ValueError
                    # One guide that breaks (odd data, a file that will not download) never stops the others.
                    held.append({"slug": article["slug"], "channel": channel.name, "kind": kind,
                                 "reason": "error: " + type(error).__name__ + ": " + str(error)[:120]})
            if not made:
                exhausted.add(kind)
                short.append(channel.name)
                continue
            rows.append({"id": made["id"], "channel": channel.name, "kind": kind, "format": made.get("format"), "url": made["targetUrl"], "dueAt": slot})
            created.append({"id": made["id"], "channel": channel.name, "kind": kind, "format": made.get("format"),
                            "publishAt": made["publishAt"], "guide": made["targetUrl"]})
    used = {record["file"] for name, key in (("photos.json", "photos"), ("clips.json", "clips"))
            for path in (root / AUTO).glob("*/" + name) for record in json.loads(path.read_text())[key].values()}
    remove([path for path in photos.created + clips.created if path.relative_to(root).as_posix() not in used])
    coverage = {channel.name: covered_until(channel.name, rows) for channel in cadence.channels}
    short = sorted(set(short))
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
