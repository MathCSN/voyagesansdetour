"""Which fast reel a guide becomes, and its plans (scenario schema 3).

Four formats, each taken from what already works for travel content (docs/strategie-videos.md):
- "prix"       the price first ("6 jours pour 380 €"): budget guides whose first figure is the budget itself;
- "itineraire" day by day, one stage per plan: itineraries;
- "tableau"    one screen to pause and save: "when to go" and any guide with a short table;
- "liste"      a fast numbered list of figures to know before leaving: every guide.
("express", two figures and out, is no longer made: it left reels almost empty. The name stays valid for the one
reel of that kind already in the catalogue.) Every reel says at least four different things (MIN_FACTS).
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
STAGE_DETAIL = 80                      # under a stage of an itinerary: its price and what it pays for, on three lines at most
DETAIL_MAX = 96                        # a label longer than three lines on screen is never shown; its figure stays in the guide
SOFT_PAUSE = re.compile(r" (?=(?:depuis|selon|en tarif|avec|à partir)\b)")
MIN_SHORT_LABEL = 18
FIGURE_MAX = 16                        # longer values are shown on white boxes, in two lines if needed
HOOK_SECONDS, CTA_SECONDS = 2.2, 2.4
FACT_SECONDS = (2.4, 4.0)
MAX_FACTS = {"liste": 5, "prix": 5, "tableau": 2, "express": 2}
MAX_STAGES, MIN_STAGES = 6, 3
TABLE_ROWS = (3, 5)
FORMAT_LABELS = {"liste": "les chiffres à connaître", "prix": "combien ça coûte", "itineraire": "jour par jour",
                 "tableau": "le tableau à garder", "express": "l’essentiel"}
EVERY_DAY = "*jour par jour*"          # the promise of an itinerary whose every day is shown
PRICE = re.compile(r"€|\$|¥|£|₫|฿|\bCHF\b|\bdh\b|\bMAD\b")
BUDGET = re.compile(r"\bbudget\b|\bau total\b|\ben tout\b|\bpar personne\b|\btout compris\b|\bhors vols?\b|\bsans le vol\b|"
                    r"\bpour \d+ (?:jours|nuits|semaines)\b|\bpar jour\b", re.IGNORECASE)
MIN_FACTS = 4                          # a reel that says fewer than four things is not worth a slot (audit of 12/11/2026)
# One space at most between the parts: section titles are plain text, and nothing here can backtrack.
DAY = re.compile(r"(Jours? \d+(?: ?(?:à|et|[-–]) ?\d+)?) ?[—–:,-] ?(\S.*)", re.IGNORECASE)
# The same file goes to Instagram and TikTok: "cette vidéo", never "ce reel".
SAVE_NOTE = "Enregistrez cette vidéo pour votre voyage"
PAUSE_NOTE = "Faites pause pour tout lire"
MONTHS = "janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre"
# The date a figure gives for itself: "relevé en juillet 2026", "(relevé de mars 2025)", "(Por Esto, juillet 2026)",
# "(octobre 2026)". Not a period ("du 2 novembre au 31 décembre 2026") nor a start ("depuis janvier 2026").
OWN_DATE = re.compile(rf"\brelevée?s? (?:en |de |d’|d'|le |du |au )((?:\d{{1,2}}(?:er)? )?(?:{MONTHS}) 20\d\d)"
                      rf"|\((?:[^()]*, )?((?:{MONTHS}) 20\d\d)\)", re.IGNORECASE)
SOURCES_READ = re.compile(r"sources du (\d\d)/(\d\d)/(20\d\d)\Z")
TAG_MAX = 52


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
    """Price, duration, train, boat, walk: the first that fits; a pin otherwise. A distance alone is not a walk."""
    tests = (("💶", "€" in value), ("⏱️", re.search(r"\b(min|h|jours?)\b", value)), ("🚆", "train" in label.lower()),
             ("⛴️", re.search(r"ferry|bateau|rabelo", label.lower())), ("🥾", re.search(r"marches|sentier|randonn|à pied", value + label)))
    return next((emoji for emoji, fits in tests if fits), "📍")


def caption_line(fact: dict) -> str:
    """'59 € : la cabine du train de nuit', but '180 exposants au marché' and '120 km entre Mérida et la gare':
    no colon when the label simply carries on from the figure (a bare number, or a label opening on a preposition)."""
    value, label = fact["value"], fact["label"]
    flows = re.fullmatch(r"[\d\s]+", value) or re.match(r"(?:de|d’|d'|entre|pour|par|sur|depuis|jusqu)\b", label)
    return caption_emoji(value, label) + " " + value + (" " if flows else " : ") + label


def in_enumeration(label: str, cut: int) -> bool:
    """A comma between two short items with more to come ('Valladolid, Chichén Itzá, Mérida, Uxmal et Tulum'):
    the middle of a list. A comma after a long clause ('…et 13 nuits (154 120 ¥), capsule ou dortoir') is a pause."""
    before = re.split(r", | et | ou ", label[:cut])[-1]
    after = re.split(r", | et | ou ", label[cut + 2:], maxsplit=1)
    return len(before.split()) <= 3 and len(after) == 2 and len(after[0].split()) <= 3


def short_label(label: str, limit: int = SHORT_LABEL) -> str:
    """The label up to a natural pause: still the guide's own words, short enough for a three-second plan."""
    if len(label) <= limit:
        return label
    # Never inside a parenthesis: "(Bahia, tombeaux saadiens, El Badi)" is dropped whole or kept whole.
    # Never inside a list: "Valladolid, Chichén Itzá, Mérida, Uxmal et Tulum" keeps all its places or is shown whole.
    cuts = [match.start() for match in re.finditer(r" \(| ; |, | : ", label)
            if label[:match.start()].count("(") == label[:match.start()].count(")")
            and not (match.group() == ", " and in_enumeration(label, match.start()))]
    fitting = [cut for cut in cuts if MIN_SHORT_LABEL <= cut <= limit]
    if not fitting:
        # No punctuation in reach: stop before what only qualifies the figure ("… pour un étranger | depuis le 27 mars").
        fitting = [match.start() for match in SOFT_PAUSE.finditer(label)
                   if MIN_SHORT_LABEL <= match.start() <= limit and label[:match.start()].count("(") == label[:match.start()].count(")")]
    return label[:max(fitting)].rstrip() if fitting else label


def seconds_for(detail: str | None) -> float:
    """Reading time: the figure alone, then about twenty characters a second."""
    low, high = FACT_SECONDS
    return round(min(high, max(low, 1.5 + len(detail or "") / 24)), 1)


def is_price(fact: dict) -> bool:
    return bool(PRICE.search(fact["value"]))


def opens_on_budget(fact: dict) -> bool:
    """A price that is the cost of the trip itself ('872 € : le budget serré pour 14 jours'), not the price of one
    thing in it: 'Laponie : le budget — 59 €' would sell a train cabin as the budget of Lapland."""
    return is_price(fact) and bool(BUDGET.search(fact["label"]))


def repeats_title(fact: dict, article: dict) -> bool:
    """'10 jours' under 'Yucatán en 10 jours': a plan that says the title again says nothing."""
    value, title = (re.sub(r"[^a-z0-9]+", "-", destinations.ascii_fold(text).lower()).strip("-") for text in (fact["value"], article.get("shortTitle", "")))
    return bool(value) and f"-{value}-" in f"-{title}-"


def source_tag(article: dict, checked_on: str) -> str:
    """The small label of a plan: whose figures these are and when the guide's sources were last read."""
    tag = f"Guide {article['destination']} · sources du {checked_on}"
    return tag if len(tag) <= TAG_MAX else f"Notre guide · sources du {checked_on}"


def dated_tag(fact: dict, tag: str) -> str:
    """A figure that carries its own date is labelled with it: "sources du 11/11/2026" under a fare read in July
    would date the fare wrongly. Any other figure keeps the date the guide's sources were last read."""
    match = OWN_DATE.search(fact["label"])
    # "(mars, avril 2026)" names two months: a period, not the date the figure was read.
    if not match or (match[2] and re.search(rf"\b(?:{MONTHS})\b", match[0][:match.start(2) - match.start()], re.IGNORECASE)):
        return tag
    date = (match[1] or match[2]).lower()
    # A figure is never read after the guide's sources were: "ouverture prévue (décembre 2026)" in a guide read in
    # November dates an opening, not the figure.
    read, (*day, month, year) = SOURCES_READ.search(tag), date.split()
    own = (int(year), MONTHS.split("|").index(month) + 1, int(re.sub(r"\D", "", day[0])) if day else 0)
    if read and own > (int(read[3]), int(read[2]), int(read[1])):
        return tag
    own = "chiffre " + ("du " if date[0].isdigit() else "d’" if date[0] in "ao" else "de ") + date
    return next(text for text in (tag.split(" · ")[0] + " · " + own, "Notre guide · " + own) if len(text) <= TAG_MAX)


def quoted(fact: dict, tag: str) -> tuple[str, str]:
    """What a plan quotes for its figure, and its label: the short quote, or the whole one when the label gives the
    figure's own date, so that the date on screen is read in the plan's own source."""
    own = dated_tag(fact, tag)
    return (fact["shortExcerpt"], tag) if own == tag else (fact["excerpt"], own)


def figure_lines(value: str) -> list[str] | None:
    """A short value is the yellow figure; a longer one ('19 au 28 février 2027') goes on white boxes."""
    if len(value) <= FIGURE_MAX:
        return ["*" + unbreakable(value) + "*"]
    lines = lines_of(value, 22)
    return [unbreakable(line) for line in lines] if lines else None


# --- what the guide offers --------------------------------------------------

def numbered(facts: list[dict], article: dict) -> list[dict]:
    """The figures a plan may show: a number on screen (a plan of fact without a figure says too little), not the
    title said again, and a label that fits."""
    return [f for f in facts if re.search(r"\d", f["value"]) and figure_lines(f["value"])
            and not repeats_title(f, article) and len(f["short"]) <= DETAIL_MAX]


def stages(article: dict, page: str, facts: list[dict]) -> list[dict]:
    """The 'Jour 3 — …' sections, as quoted on the page: day marker, place, and the figure the guide gives for that
    day when it fits under the stage (None otherwise: that stage stays in the guide)."""
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
            fact = next((f for f in facts if f["section"] is section and len(f["value"] + f["short"]) <= STAGE_DETAIL), None)
            found.append({"kicker": match[1], "lines": lines, "title": title, "section": section, "fact": fact})
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
    # Price first only where the guide's first figure is the cost of the trip itself: a budget guide whose first figure says so.
    if category == "budget" and facts and opens_on_budget(facts[0]):
        formats.append("prix")
    if sum(1 for step in stages(article, page, numbered(facts, article)) if step["fact"]) >= MIN_STAGES:
        formats.append("itineraire")
    if table_of(article, page):
        # "When to go" is a table before anything else; elsewhere the table comes after the guide's own format.
        formats.insert(0 if article.get("shortTitle", "").lower().startswith("quand partir") else len(formats), "tableau")
    # No "express" any more: two figures in twelve seconds left a reel almost empty (Yucatán, 20/11/2026).
    return formats + ["liste"]


def ordered(formats: list[str], used: list[str]) -> list[str]:
    """Formats never used for this guide first; then the least recently used."""
    fresh = [f for f in formats if f not in used]
    return fresh + sorted((f for f in formats if f in used), key=lambda f: max(i for i, u in enumerate(used) if u == f))


# --- plans -------------------------------------------------------------------

# Words that name nothing: two texts that share only these are not about the same thing.
EMPTY_WORDS = frozenset("pour entre dans avec sans sous vers chez depuis selon plus moins tout tous toute toutes cette leur leurs "
                        "dont comme aussi tres deux trois quatre jour jours nuit nuits prix tarif euros pesos".split())


def words_of(value: str) -> set[str]:
    """Words of four letters and more that name something; a dash separates two words ('Mérida–Cancún' names both towns)."""
    return set(re.findall(r"[a-z0-9]{4,}", destinations.ascii_fold(re.sub(r"[^\w\s]", " ", value)).lower())) - EMPTY_WORDS


# Kinds of places: "la tour des Clérigos" and "l’Andante Tour 3", "la villa des Mystères" and the villa Cimbrone, "un
# monument de la médina" and a lamp maker "in the medina" share such a word and nothing else. Alone it ties no figure
# to a photo; beside a name the two share, it counts.
PLACE_KINDS = frozenset("tour tours villa villas ville villes village villages medina place places pont ponts palais jardin jardins "
                        "musee musees temple temples eglise eglises cathedrale chateau plage plages marche marches parc parcs "
                        "quartier quartiers gare gares port ports centre monument monuments".split())


def words_shown(photo: tuple, target: set[str], family: str | None = None) -> int:
    """How many of these words the photo's caption, its Commons title and its identifier carry. `family`: the prefix
    all the photos of the post share says nothing of what one of them shows ("amalfi-positano" is a photo of Positano)."""
    prefix, _, rest = photo[0].partition("-")
    described = " ".join([(rest if prefix == family else photo[0]).replace("-", " "), photo[2], str(photo[1].get("commonsTitle", ""))])
    shared = target & words_of(described)
    return len(shared) if shared - PLACE_KINDS else 0


class Media:
    """Photos and clips still unused in this reel: a photo is never shown twice, and never under another place's name."""

    def __init__(self, photos: list[tuple[str, dict, str]], clips: list[tuple[str, dict]], reserve: int = 0, cover: str | None = None,
                 emblematic: tuple[str, ...] = (), everywhere: str = ""):
        self.photos, self.clips, self.reserve, self.cover = list(photos), list(clips), reserve, cover
        self.all = list(photos)
        # The pictures that can stand for the whole place under the call to action, the best first.
        self.emblematic = [photo_id for photo_id in emblematic if photo_id != cover]
        # Files found by the search (media_library.closing_mark): nobody looked at them, they never open a post.
        self.found = {photo[0] for photo in photos if photo[1].get("automatic") is True}
        prefixes = {photo[0].partition("-")[0] for photo in photos if photo[0] not in self.found}
        self.family = prefixes.pop() if len(prefixes) == 1 else None
        # The name of the place and of its country is in every caption: sharing it says nothing of what a photo shows.
        self.everywhere = words_of(everywhere)

    def target(self, text: str) -> set[str]:
        return words_of(text) - self.everywhere

    def shown_elsewhere(self, text: str) -> bool:
        """A photo of this post that another plan has taken, or that is kept for the call to action, shows what
        `text` names better than any photo still free: over another picture, that figure would name one place while
        the post shows it elsewhere. The figure stays in the guide."""
        target = self.target(text)
        return max((self.shared(ph, target) for ph in self.all), default=0) > max((self.shared(ph, target) for ph in self.free()), default=0)

    def shared(self, photo: tuple, target: set[str]) -> int:
        return words_shown(photo, target, self.family)

    def spare(self) -> str | None:
        """The last photo left that can close the post: no plan takes it, whatever it names."""
        left = [wanted for wanted in self.emblematic if any(ph[0] == wanted for ph in self.photos)]
        return left[0] if len(left) == 1 else None

    def free(self) -> list:
        """The photos a plan may take when it names what they show: all but the last one that can close the post. In a
        post completed by files found by the search, the cover too is kept: such a file never opens a post."""
        held = {self.spare(), self.cover if self.found else None}
        return [ph for ph in self.photos if ph[0] not in held]

    def room(self) -> int:
        return len(self.photos) + len(self.clips) - self.reserve

    def kept(self) -> set[str]:
        """The two pictures a plan takes only when its text names what they show: the cover, which opens the post
        otherwise, and the best one still free for the call to action. A plan that no photo shows is given another."""
        last = next((wanted for wanted in self.emblematic if any(ph[0] == wanted for ph in self.photos)), None)
        return {self.cover, last} - {None}

    def named(self, text: str, section: dict | None) -> tuple | None:
        """The photo that shows what `text` names: the one whose id, caption or title shares the most words with it.
        The section's own photo wins when it shares as many, and stands in when no photo shares any; it gives way
        when it shows something else ("Chichén Itzá à l'ouverture" is not shown by the cenote of that afternoon)."""
        target = self.target(text)
        shared = lambda ph: self.shared(ph, target)
        wanted = section.get("image") if section else None
        pool = self.free()
        own = next((ph for ph in pool if ph[0] == wanted), None)
        best = max(pool, key=shared, default=None)
        if own and (best is None or shared(own) or not shared(best)):
            return own
        return best if best is not None and shared(best) else None

    def photo(self, text: str = "", section: dict | None = None, strict: bool = False) -> tuple[str, str]:
        """A photo for this text. `strict`: only a photo that shows what the text names (a stage of an itinerary)."""
        pick = self.named(text, section)
        if not pick and (strict or len(self.photos) <= self.reserve):
            raise Held("no_photo_of_this_place" if strict else "not_enough_photos_or_figures")
        kept, free = self.kept(), self.free()
        pick = pick or next((ph for ph in free if ph[0] not in kept), free[0] if free else None)
        if not pick:
            raise Held("not_enough_photos_or_figures")
        self.photos.remove(pick)
        return ("photo", pick[0])

    def closing(self, required: bool = True) -> tuple[str, str]:
        """The picture under the call to action: one that stands for the place, a photo marked `emblematic` by hand
        or one the guide itself shows. Never a detail kept for one plan (a hut, a dog team) nor a file found by the
        search: `required`, the post waits for such a photo; otherwise any photo left will do (a carousel)."""
        pick = next((ph for wanted in self.emblematic for ph in self.photos if ph[0] == wanted), None)
        if not pick and (required or not self.photos):
            raise Held("no_emblematic_photo_for_the_call")
        pick = pick or self.photos[0]
        self.photos.remove(pick)
        return ("photo", pick[0])

    def moving(self, text: str = "", section: dict | None = None, strict: bool = False) -> tuple[str, str]:
        """A real clip of the destination when one is left and no photo shows this very plan."""
        if self.clips and not strict and not self.named(text, section):
            return ("clip", self.clips.pop(0)[0])
        return self.photo(text, section, strict)

    def opening(self, cover: str | None) -> tuple[str, str]:
        """The cover photo of the guide when it is still free: it is the picture people see first. When a plan took
        it, another photo that stands for the place, else one a person looked at; never the last one kept for the
        call to action, and never a file found by the search: the post waits rather than open on it."""
        self.reserve = max(0, self.reserve - 1)
        spare = self.spare()
        seen = [ph for ph in self.photos if ph[0] not in self.found]
        left = [ph for ph in seen if ph[0] != spare]
        pick = (next((ph for ph in seen if ph[0] == cover), None) or next((ph for ph in left if ph[0] in self.emblematic), None)
                or (left[0] if left else None))
        if not pick:
            raise Held("no_reviewed_photo_to_open_with")
        self.photos.remove(pick)
        return ("photo", pick[0])


def plan(layout: str, media: tuple[str, str], kicker: str, headline: list[str], seconds: float, *, detail=None, facts=None, tag=None, **extra) -> dict:
    scene = {media[0]: media[1], "focus": [0.5, 0.5], "layout": layout, "kicker": kicker, "headline": headline, "seconds": seconds}
    if detail:
        scene["detail"] = detail
    if facts:
        scene["facts"], scene["tag"] = facts, tag
    return {**scene, **{key: value for key, value in extra.items() if value}}


def fact_plan(fact: dict, media: Media, place: str, tag: str, badge: str | None = None) -> dict:
    headline = figure_lines(fact["value"])
    if not headline:
        raise Held("figure_too_long")
    detail = unbreakable(fact["short"])
    picture = media.moving(fact["label"], fact["section"])
    # The label above the figure is the section's name only over that section's own photo, or when the section has
    # none: "Aurores boréales" is not written over a picture of the village.
    own = fact["section"].get("image") if fact["section"] else None
    kicker = kicker_of(fact["section"], place) if not own or picture[1] == own else place
    excerpt, label = quoted(fact, tag)
    return plan("fact", picture, kicker, headline, seconds_for(detail), detail=detail,
                facts=[{"source": "guide", "excerpt": excerpt}], tag=label, badge=badge)


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
        return numbered(self.facts, self.article)

    def hook(self, promise: str) -> dict:
        return plan("hook", self.media.opening(self.media.cover), self.kicker, self.title_lines + [promise], HOOK_SECONDS,
                    facts=[{"source": "guide", "excerpt": self.opening}], tag=self.tag)


def placed(facts: list[dict], media: Media, limit: int, least: int):
    """The figures a post shows, as indexes of `facts`, each yielded when its photo is about to be taken: first those
    a free photo shows, up to `limit`; then, only to reach `least`, those that no photo of the post shows at all."""
    done = set()
    for wanted, most in ((True, limit), (False, least)):
        for index, fact in enumerate(facts):
            if index in done or len(done) >= most or media.shown_elsewhere(fact["label"]):
                continue
            if not wanted or media.named(fact["label"], fact["section"]):
                done.add(index)
                yield index


def figures_reel(fmt: str, brief: Brief) -> tuple[dict, list[dict], list[str]]:
    """"liste", "express" and "prix": one figure per plan; a budget opens on its first price."""
    chosen = brief.numbered
    lead = chosen.pop(0) if fmt == "prix" and chosen and opens_on_budget(chosen[0]) and len(chosen[0]["value"]) <= FIGURE_MAX else None
    if fmt == "prix":
        if not lead:
            raise Held("no_price_to_open_with")
        chosen = sorted(chosen, key=lambda f: not is_price(f))
    limit, plans = min(MAX_FACTS[fmt], brief.media.room()), {}
    # A figure that a photo shows goes first (the price of the huskies over the huskies); a figure that no photo shows
    # only fills the reel up to its four facts, and otherwise stays in the caption and the guide. A figure whose
    # photo another plan has taken is never put over a different place.
    for index in placed(chosen, brief.media, limit, min(limit, MIN_FACTS - bool(lead))):
        plans[index] = fact_plan(chosen[index], brief.media, brief.place, brief.tag)
    if len(plans) < 3:
        raise Held("not_enough_photos_or_figures")
    chosen, body = [chosen[index] for index in sorted(plans)], [plans[index] for index in sorted(plans)]
    for number, scene in enumerate(body, 1):
        scene["badge"] = f"{number}/{len(body)}"
    if lead:
        excerpt, label = quoted(lead, brief.tag)
        hook = plan("hook", brief.media.opening(brief.media.cover), "Combien ça coûte ?", brief.title_lines + ["*" + unbreakable(lead["value"]) + "*"],
                    round(HOOK_SECONDS + 0.6, 1), detail=unbreakable(lead["short"]), facts=[{"source": "guide", "excerpt": excerpt}], tag=label)
        return hook, body, [caption_line(f) for f in [lead] + chosen]
    verb = "retenir" if fmt == "express" else "connaître"
    return brief.hook(f"*{len(chosen)} chiffres à {verb}*"), body, [caption_line(f) for f in chosen]


def stage_plan(step: dict, picture: tuple[str, str], tag: str) -> dict:
    """One day of the itinerary and the figure the guide gives for it: a stage is never shown without one."""
    fact = step["fact"]
    excerpt, label = quoted(fact, tag)
    detail = "*" + unbreakable(fact["value"]) + "* " + unbreakable(fact["short"])
    return plan("fact", picture, step["kicker"], step["lines"], round(seconds_for(detail) - 0.4, 1), detail=detail,
                facts=[{"source": "guide", "excerpt": step["title"]}, {"source": "guide", "excerpt": excerpt}], tag=label)


def stage_line(step: dict) -> str:
    """The stage in the caption, with the figure its plan shows and that figure's whole label when it fits (its date is there)."""
    line, fact = f"📍 {step['kicker']} : {' '.join(step['lines'])}", step["fact"]
    return next((text for text in (f"{line} · {fact['value']} {label}" for label in (fact["label"], fact["short"])) if len(text) <= 160), line)


def itinerary_reel(brief: Brief) -> tuple[dict, list[dict], list[str]]:
    """"itineraire": one dated stage per plan, with its figure, shown only over a photo of that very place.
    A stage for which the guide gives no figure, or that no photo shows, stays in the guide."""
    body, lines = [], []
    for step in stages(brief.article, brief.page, brief.numbered):
        if brief.media.room() < 1:
            break
        if not step["fact"]:
            continue
        # The photo is chosen for what the plan will say (its name, its price), not for the whole title of the day.
        try:
            picture = brief.media.photo(" ".join(step["lines"] + [step["fact"]["short"]]), step["section"], strict=True)
        except Held:
            continue
        body.append(stage_plan(step, picture, brief.tag))
        lines.append(stage_line(step))
    if len(body) < MIN_STAGES:
        raise Held("not_enough_stages_with_a_figure_and_their_photo")
    # "Jour par jour" is promised only when every day of the guide is there; otherwise the hook counts what follows.
    every_day = len(body) == sum(1 for section in brief.article.get("sections", []) if DAY.fullmatch(str(section.get("title", "")).strip()))
    return brief.hook(EVERY_DAY if every_day else f"*{len(body)} étapes clés*"), body, lines


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
    # Then its figures, chosen as in a list: the one a free photo shows first, and never a figure whose photo is taken
    # (the fare of the ferry stays in the table, over the ferry, rather than go over another village).
    chosen, limit, plans = brief.numbered, min(MAX_FACTS["tableau"], brief.media.room()), {}
    for index in placed(chosen, brief.media, limit, limit):
        plans[index] = fact_plan(chosen[index], brief.media, brief.place, brief.tag)
    body += [plans[index] for index in sorted(plans)]
    return brief.hook("*le tableau à garder*"), body, [f"📅 {a} : {b}" for a, b in rows]


def label_of(fmt: str, scenes: list[dict]) -> str:
    """The format in the title of the post: no "jour par jour" for an itinerary that leaves days out."""
    partial = fmt == "itineraire" and scenes[0]["headline"][-1] != EVERY_DAY
    return "les étapes clés" if partial else FORMAT_LABELS[fmt]


def emblematic(photos: list) -> tuple[str, ...]:
    """The photos that can close a post, the guide's own first: those the site publishes for this place and those a
    human marked `emblematic` in reviewed.json (media_library.gather_photos). A photo added for one plan (a hut, a
    dog team) or found by the search is not one of them."""
    return tuple(photo[0] for photo in photos if photo[1].get("emblematic") is True)


def build(fmt: str, article: dict, facts: list[dict], photos: list, clips: list, opening: str, place: str, kicker: str,
          tag: str, title_lines: list[str], page: str) -> tuple[list[dict], list[str]]:
    """The plans of one reel and the useful lines of its caption. Raises Held when the guide cannot fill the format."""
    # The body takes the photos that show what it names; the hook and the call keep two, the cover first.
    # The picture people see first: the guide's cover, or its first photo when the cover is too small for a reel.
    # Never a file found by the search: nobody looked at it.
    seen = [photo[0] for photo in photos if photo[1].get("automatic") is not True]
    cover = article.get("cover") if article.get("cover") in seen else (seen[0] if seen else None)
    brief = Brief(article, facts, Media(photos, clips, reserve=2, cover=cover, emblematic=emblematic(photos), everywhere=kicker),
                  opening, place, kicker, tag, title_lines, page)
    if fmt in ("liste", "express", "prix"):
        hook, body, lines = figures_reel(fmt, brief)
    elif fmt == "itineraire":
        hook, body, lines = itinerary_reel(brief)
    elif fmt == "tableau":
        hook, body, lines = table_reel(brief)
    else:
        raise Held("unknown_format")
    # At least four different things said, the hook's own promise aside: figures, stages or table rows.
    said = {fact["excerpt"] for scene in [hook] + body for fact in scene.get("facts", [])} - {opening}
    if len(said) < MIN_FACTS:
        raise Held("fewer_than_four_facts")
    # The button is written in the scenario: a reel sealed before 12/11/2026 has none and keeps the card it was given.
    closing = plan("cta", brief.media.closing(), "Le guide complet", title_lines, CTA_SECONDS, note=SAVE_NOTE, button=p.MOTION_BUTTON)
    # A photo reviewed by hand may say where its subject is (reviewed.json, "focus"): the vertical frame is cut around it.
    records = {photo[0]: photo[1] for photo in photos}
    for scene in [hook] + body + [closing]:
        focus = records.get(scene.get("photo"), {}).get("focus")
        if isinstance(focus, list) and len(focus) == 2:
            scene["focus"] = focus
    # Three to five useful caption lines: the figures left unshown complete a short list.
    lines += [caption_line(f) for f in facts if caption_line(f) not in lines]
    lines = [line for line in lines if checked(line, 160)][:5]
    if len(lines) < 3:
        raise Held("not_enough_caption_lines")
    return [hook] + body + [closing], lines
