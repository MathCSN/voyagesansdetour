"""Which fast reel a guide becomes, and its plans (scenario schema 3).

Five formats, each taken from what already works for travel content (docs/strategie-videos.md):
- "prix"       the price first ("6 jours pour 380 €"): budget guides;
- "itineraire" day by day, one stage per plan: itineraries;
- "tableau"    one screen to pause and save: "when to go" and any guide with a short table;
- "liste"      a fast numbered list of figures to know before leaving: every guide;
- "express"    two figures and out, under ten seconds: a guide's second or third reel.
Nothing is written here that the guide does not say: a figure, a stage or a table row is
shown only when it is read word for word in the dated snapshot of the published page.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

import destinations
import production as p

NBSP = " "
UNIT = r"(?:h|min|€|km|m|%|jours?|nuits?|trains?|marches|ans|cm|mm|°C|dh|\$|¥|£|₫|฿)(?!\w)"
SHORT_LABEL = 64                       # characters read comfortably in three seconds
MIN_SHORT_LABEL = 18
FIGURE_MAX = 16                        # longer values are shown on white boxes, in two lines if needed
HOOK_SECONDS, CTA_SECONDS = 2.2, 2.4
FACT_SECONDS = (2.4, 4.0)
MAX_FACTS = {"liste": 5, "prix": 5, "tableau": 2, "express": 2}
MAX_STAGES, MIN_STAGES = 6, 3
TABLE_ROWS = (3, 5)
FORMAT_LABELS = {"liste": "les chiffres à connaître", "prix": "combien ça coûte", "itineraire": "jour par jour",
                 "tableau": "le tableau à garder", "express": "l’essentiel"}
PRICE = re.compile(r"€|\$|¥|£|₫|฿|\bCHF\b|\bdh\b|\bMAD\b")
# One space at most between the parts: section titles are plain text, and nothing here can backtrack.
DAY = re.compile(r"(Jours? \d+(?: ?(?:à|et|[-–]) ?\d+)?) ?[—–:,-] ?(\S.*)", re.IGNORECASE)
SAVE_NOTE = "Enregistrez ce reel pour votre voyage"
PAUSE_NOTE = "Faites pause pour tout lire"


class Held(ValueError):
    """This guide cannot make this post now; the next format or the next guide is tried."""


def checked(value, maximum):
    """The production text guard, as a filter: None when the charter would refuse it."""
    try:
        return p.text(value, maximum)
    except p.Invalid:
        return None


def unbreakable(value: str) -> str:
    """Glue a figure to its unit and its next figure for the renderer: '1 h 37', '9 €', '3 047'."""
    value = re.sub(r"(?<=\d) (?=" + UNIT + r"|\d)", NBSP, value)
    return re.sub(r"(?<=\bh) (?=\d)", NBSP, value)


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


def caption_emoji(value: str, label: str) -> str:
    """Price, duration, train, boat, walk: the first that fits; a pin otherwise."""
    tests = (("💶", "€" in value), ("⏱️", re.search(r"\b(min|h|jours?)\b", value)), ("🚆", "train" in label.lower()),
             ("⛴️", re.search(r"ferry|bateau|rabelo", label.lower())), ("🥾", re.search(r"marches|km|sentier", value + label)))
    return next((emoji for emoji, fits in tests if fits), "📍")


def caption_line(fact: dict) -> str:
    value, label = fact["value"], fact["label"]
    joined = value + (" " if re.match(r"(?:de |d’|d')", label) else " : ") + label
    return caption_emoji(value, label) + " " + joined


def short_label(label: str, limit: int = SHORT_LABEL) -> str:
    """The label up to a natural pause: still the guide's own words, short enough for a three-second plan."""
    if len(label) <= limit:
        return label
    # Never inside a parenthesis: "(Bahia, tombeaux saadiens, El Badi)" is dropped whole or kept whole.
    cuts = [match.start() for match in re.finditer(r" \(| ; |, | : ", label) if label[:match.start()].count("(") == label[:match.start()].count(")")]
    fitting = [cut for cut in cuts if MIN_SHORT_LABEL <= cut <= limit]
    return label[:max(fitting)].rstrip() if fitting else label


def seconds_for(detail: str | None) -> float:
    """Reading time: the figure alone, then about twenty characters a second."""
    low, high = FACT_SECONDS
    return round(min(high, max(low, 1.5 + len(detail or "") / 24)), 1)


def is_price(fact: dict) -> bool:
    return bool(PRICE.search(fact["value"]))


def figure_lines(value: str) -> list[str] | None:
    """A short value is the yellow figure; a longer one ('19 au 28 février 2027') goes on white boxes."""
    if len(value) <= FIGURE_MAX:
        return ["*" + unbreakable(value) + "*"]
    lines = lines_of(value, 22)
    return [unbreakable(line) for line in lines] if lines else None


# --- what the guide offers --------------------------------------------------

def stages(article: dict, page: str, facts: list[dict]) -> list[dict]:
    """The 'Jour 3 — …' sections, as quoted on the page: day marker, place, and one figure when the guide gives it."""
    found = []
    for section in article.get("sections", []):
        title = str(section.get("title", "")).strip()
        match = DAY.fullmatch(title)
        if not match or p.normalized(title) not in page or not checked(title, 400):
            continue
        name = match[2].strip()
        # The whole name on one line when it is short; else the place before the first comma; else two lines.
        whole = [name] if len(name) <= 22 else []
        for candidate in dict.fromkeys(whole + [name.split(", ")[0], name.split(" : ")[0], re.split(r" et | puis ", name)[0], name]):
            lines = lines_of(candidate, 22)
            if not (len(candidate) >= 3 and lines and checked(match[1], 32) and all(checked(line, 34) for line in lines)):
                continue
            rest = name[len(candidate):].lstrip(" ,:—–").removeprefix("et ").strip()
            fact = next((f for f in facts if f["section"] is section), None)
            found.append({"kicker": match[1], "lines": lines, "title": title, "section": section, "fact": fact,
                          "rest": rest[:1].upper() + rest[1:] if 8 <= len(rest) <= 90 and checked(rest, 120) else None})
            break
    return found[:MAX_STAGES]


def table_of(article: dict, page: str) -> dict | None:
    """A whole short table of the guide (three to five rows), first two columns, every row read on the page."""
    for section in article.get("sections", []):
        table = section.get("table") or {}
        headers, rows = table.get("headers") or [], table.get("rows") or []
        if len(headers) < 2 or not TABLE_ROWS[0] <= len(rows) <= TABLE_ROWS[1] or any(len(row) < 2 for row in rows):
            continue
        cells = [[str(row[0]).strip(), str(row[1]).strip()] for row in rows]
        quoted = all(checked(a, 60) and checked(b, 60) and p.normalized(a + " " + b) in page for a, b in cells)
        title = lines_of(str(headers[1]).strip(), 22)
        if quoted and title and all(checked(line, 34) for line in title) and p.normalized(str(headers[1])) in page:
            return {"rows": cells, "title": title, "section": section}
    return None


def applicable(article: dict, facts: list[dict], page: str) -> list[str]:
    """The formats this guide can fill, the one that suits its type first."""
    category = p.normalized(str(article.get("category", ""))).lower()
    formats = []
    # Price first only where the guide's first figure is the cost of the trip itself: a budget guide.
    if category == "budget" and facts and is_price(facts[0]):
        formats.append("prix")
    if len(stages(article, page, facts)) >= MIN_STAGES:
        formats.append("itineraire")
    if table_of(article, page):
        # "When to go" is a table before anything else; elsewhere the table comes after the guide's own format.
        formats.insert(0 if article.get("shortTitle", "").lower().startswith("quand partir") else len(formats), "tableau")
    return formats + ["liste", "express"]


def ordered(formats: list[str], used: list[str]) -> list[str]:
    """Formats never used for this guide first; then the least recently used."""
    fresh = [f for f in formats if f not in used]
    return fresh + sorted((f for f in formats if f in used), key=lambda f: max(i for i, u in enumerate(used) if u == f))


# --- plans -------------------------------------------------------------------

def words_of(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{4,}", destinations.ascii_fold(value).lower()))


class Media:
    """Photos and clips still unused in this reel: a photo is never shown twice, and never under another place's name."""

    def __init__(self, photos: list[tuple[str, dict, str]], clips: list[tuple[str, dict]], reserve: int = 0, cover: str | None = None):
        self.photos, self.clips, self.reserve, self.cover = list(photos), list(clips), reserve, cover

    def room(self) -> int:
        return len(self.photos) + len(self.clips) - self.reserve

    def named(self, text: str, section: dict | None, keep_cover: bool = True) -> tuple | None:
        """The section's own photo, else the photo whose id, caption or title shares the most words with `text`."""
        wanted = section.get("image") if section else None
        own = next((ph for ph in self.photos if ph[0] == wanted), None)
        if own:
            return own
        target = words_of(text)
        # The cover is kept for the hook unless a stage of the itinerary is that very place.
        pool = [ph for ph in self.photos if not (keep_cover and ph[0] == self.cover)]
        scored = [(len(target & words_of(" ".join([ph[0].replace("-", " "), ph[2], str(ph[1].get("commonsTitle", ""))]))), ph) for ph in pool]
        best = max(scored, key=lambda pair: pair[0], default=(0, None))
        return best[1] if best[0] else None

    def photo(self, text: str = "", section: dict | None = None, strict: bool = False) -> tuple[str, str]:
        """A photo for this text. `strict`: only a photo that shows what the text names (a stage of an itinerary)."""
        pick = self.named(text, section, keep_cover=not strict)
        if not pick and (strict or len(self.photos) <= self.reserve):
            raise Held("no_photo_of_this_place" if strict else "not_enough_photos_or_figures")
        pick = pick or next((ph for ph in self.photos if ph[0] != self.cover), self.photos[0])
        self.photos.remove(pick)
        return ("photo", pick[0])

    def moving(self, text: str = "", section: dict | None = None, strict: bool = False) -> tuple[str, str]:
        """A real clip of the destination when one is left and no photo shows this very plan."""
        if self.clips and not strict and not self.named(text, section):
            return ("clip", self.clips.pop(0)[0])
        return self.photo(text, section, strict)

    def opening(self, cover: str | None) -> tuple[str, str]:
        """The cover photo of the guide when it is still free: it is the picture people see first."""
        self.reserve = max(0, self.reserve - 1)
        pick = next((ph for ph in self.photos if ph[0] == cover), self.photos[0] if self.photos else None)
        if not pick:
            raise Held("not_enough_photos_or_figures")
        self.photos.remove(pick)
        return ("photo", pick[0])


def plan(layout: str, media: tuple[str, str], kicker: str, headline: list[str], seconds: float, *, detail=None, facts=None, tag=None, **extra) -> dict:
    scene = {media[0]: media[1], "focus": [0.5, 0.5], "layout": layout, "kicker": kicker, "headline": headline, "seconds": seconds}
    if detail:
        scene["detail"] = detail
    if facts:
        scene["facts"], scene["tag"] = facts, tag
    return {**scene, **{key: value for key, value in extra.items() if value}}


def fact_plan(fact: dict, media: Media, place: str, tag: str, badge: str | None) -> dict:
    headline = figure_lines(fact["value"])
    if not headline:
        raise Held("figure_too_long")
    detail = unbreakable(fact["short"])
    return plan("fact", media.moving(fact["label"], fact["section"]), kicker_of(fact["section"], place), headline, seconds_for(detail), detail=detail,
                facts=[{"source": "guide", "excerpt": fact["shortExcerpt"]}], tag=tag, badge=badge)


@dataclass(frozen=True)
class Brief:
    """What every format needs to build its plans from one guide."""
    article: dict
    facts: list
    media: Media
    opening: str
    place: str
    kicker: str
    tag: str
    title_lines: list
    page: str

    @property
    def numbered(self) -> list[dict]:
        return [f for f in self.facts if figure_lines(f["value"])]

    def hook(self, promise: str) -> dict:
        return plan("hook", self.media.opening(self.article.get("cover")), self.kicker, self.title_lines + [promise], HOOK_SECONDS,
                    facts=[{"source": "guide", "excerpt": self.opening}], tag=self.tag)


def figures_reel(fmt: str, brief: Brief) -> tuple[dict, list[dict], list[str]]:
    """"liste", "express" and "prix": one figure per plan; a budget opens on its first price."""
    chosen = brief.numbered
    lead = chosen.pop(0) if fmt == "prix" and chosen and is_price(chosen[0]) and len(chosen[0]["value"]) <= FIGURE_MAX else None
    if fmt == "prix":
        if not lead:
            raise Held("no_price_to_open_with")
        chosen = sorted(chosen, key=lambda f: not is_price(f))
    chosen = chosen[:min(MAX_FACTS[fmt], brief.media.room())]
    if len(chosen) < (2 if fmt == "express" else 3):
        raise Held("not_enough_photos_or_figures")
    body = [fact_plan(fact, brief.media, brief.place, brief.tag, f"{n}/{len(chosen)}") for n, fact in enumerate(chosen, 1)]
    if lead:
        hook = plan("hook", brief.media.opening(brief.article.get("cover")), "Combien ça coûte ?", brief.title_lines + ["*" + unbreakable(lead["value"]) + "*"],
                    round(HOOK_SECONDS + 0.6, 1), detail=unbreakable(lead["short"]), facts=[{"source": "guide", "excerpt": lead["shortExcerpt"]}], tag=brief.tag)
        return hook, body, [caption_line(f) for f in [lead] + chosen]
    word = "chiffres" if all(re.search(r"\d", f["value"]) for f in chosen) else "repères"
    verb = "retenir" if fmt == "express" else "connaître"
    return brief.hook(f"*{len(chosen)} {word} à {verb}*"), body, [caption_line(f) for f in chosen]


def stage_plan(step: dict, picture: tuple[str, str], tag: str) -> dict:
    quotes, detail, fact = [{"source": "guide", "excerpt": step["title"]}], step["rest"], step["fact"]
    if fact and len(fact["value"] + fact["short"]) <= 100:
        detail = "*" + unbreakable(fact["value"]) + "* " + unbreakable(fact["short"])
        quotes.append({"source": "guide", "excerpt": fact["shortExcerpt"]})
    return plan("fact", picture, step["kicker"], step["lines"], round(seconds_for(detail) - 0.4, 1), detail=detail, facts=quotes, tag=tag)


def itinerary_reel(brief: Brief) -> tuple[dict, list[dict], list[str]]:
    """"itineraire": one dated stage per plan, shown only over a photo of that very place; the others stay in the guide."""
    body, lines = [], []
    for step in stages(brief.article, brief.page, brief.numbered):
        if brief.media.room() < 1:
            break
        try:
            picture = brief.media.photo(step["title"], step["section"], strict=True)
        except Held:
            continue
        body.append(stage_plan(step, picture, brief.tag))
        lines.append(f"📍 {step['kicker']} : {' '.join(step['lines'])}")
    if len(body) < MIN_STAGES:
        raise Held("not_enough_stages_with_their_photo")
    return brief.hook("*jour par jour*"), body, lines


def table_reel(brief: Brief) -> tuple[dict, list[dict], list[str]]:
    """"tableau": the guide's short table, whole, on one screen to pause; then two figures at most."""
    table = table_of(brief.article, brief.page)
    if not table:
        raise Held("no_short_table")
    if brief.media.room() < 1:
        raise Held("not_enough_photos_or_figures")
    rows = table["rows"]
    body = [plan("table", brief.media.photo(section=table["section"]), brief.place, table["title"], min(7.0, round(4.0 + 0.6 * len(rows), 1)),
                 rows=rows, facts=[{"source": "guide", "excerpt": a + " " + b} for a, b in rows], tag=brief.tag, note=PAUSE_NOTE)]
    body += [fact_plan(fact, brief.media, brief.place, brief.tag, None) for fact in brief.numbered[:min(MAX_FACTS["tableau"], brief.media.room())]]
    return brief.hook("*le tableau à garder*"), body, [f"📅 {a} : {b}" for a, b in rows]


def build(fmt: str, article: dict, facts: list[dict], photos: list, clips: list, opening: str, place: str, kicker: str,
          tag: str, title_lines: list[str], page: str) -> tuple[list[dict], list[str]]:
    """The plans of one reel and the useful lines of its caption. Raises Held when the guide cannot fill the format."""
    # The body takes the photos that show what it names; the hook and the call keep two, the cover first.
    brief = Brief(article, facts, Media(photos, clips, reserve=2, cover=article.get("cover")), opening, place, kicker, tag, title_lines, page)
    if fmt in ("liste", "express", "prix"):
        hook, body, lines = figures_reel(fmt, brief)
    elif fmt == "itineraire":
        hook, body, lines = itinerary_reel(brief)
    elif fmt == "tableau":
        hook, body, lines = table_reel(brief)
    else:
        raise Held("unknown_format")
    closing = plan("cta", brief.media.opening(None), "Le guide complet", title_lines, CTA_SECONDS, note=SAVE_NOTE)
    # Three to five useful caption lines: the figures left unshown complete a short list.
    lines += [caption_line(f) for f in facts if caption_line(f) not in lines]
    lines = [line for line in lines if checked(line, 160)][:5]
    if len(lines) < 3:
        raise Held("not_enough_caption_lines")
    return [hook] + body + [closing], lines
