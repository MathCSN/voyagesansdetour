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
import place_names
import production as p

NBSP = " "
UNIT = r"(?:h|min|€|km|m|%|jours?|nuits?|trains?|marches|ans|cm|mm|°C|dh|\$|¥|£|₫|฿)(?!\w)"
SHORT_LABEL = 64                       # characters read comfortably in three seconds
STAGE_DETAIL = 80                      # under a stage of an itinerary: its price and what it pays for, on three lines at most
CAPTION_LINE = 160                     # characters of one useful line of a caption
DETAIL_MAX = 96                        # a label longer than three lines on screen is never shown; its figure stays in the guide
SOFT_PAUSE = re.compile(r" (?=(?:depuis|selon|en tarif|avec|à partir)\b)")
MIN_SHORT_LABEL = 18
FIGURE_MAX = 16                        # longer values are shown on white boxes, in two lines if needed
HOOK_SECONDS, CTA_SECONDS = 2.2, 2.4
FACT_SECONDS = (2.4, 4.0)
MAX_FACTS = {"liste": 5, "prix": 5, "tableau": 2, "express": 2}
MAX_STAGES, MIN_STAGES = 6, 4          # an itinerary shows four dated stages at least: each one is one thing said
UNDER_TABLE = (4, 64)                  # a price under a table: in a table of four rows at most, in two lines at most
TABLE_ROWS = (3, 5)
FORMAT_LABELS = {"liste": "les chiffres à connaître", "prix": "combien ça coûte", "itineraire": "jour par jour",
                 "tableau": "le tableau à garder", "express": "l’essentiel"}
EVERY_DAY = "*jour par jour*"          # the promise of an itinerary whose every day is shown
PRICE = re.compile(r"€|\$|¥|£|₫|฿|\bCHF\b|\bdh\b|\bMAD\b|\bbahts?\b|\bpesos?\b")
BUDGET = re.compile(r"\bbudget\b|\bau total\b|\ben tout\b|\bpar personne\b|\btout compris\b|\bhors vols?\b|\bsans le vol\b|"
                    r"\bpour \d+ (?:jours|nuits|semaines)\b|\bpar jour\b", re.IGNORECASE)
MIN_FACTS = 4                          # a reel that says fewer than four things is not worth a slot (audit of 12/11/2026)
# One space at most between the parts: section titles are plain text, and nothing here can backtrack.
DAY_HEAD = re.compile(r"Jours? \d", re.IGNORECASE)
DAY = re.compile(r"(Jours? \d+(?: ?(?:à|et|[-–]) ?\d+)?) ?[—–:,-] ?(\S.*)", re.IGNORECASE)
# The same file goes to Instagram and TikTok: "cette vidéo", never "ce reel".
SAVE_NOTE = "Enregistrez cette vidéo pour votre voyage"
PAUSE_NOTE = "Faites pause pour tout lire"
MONTHS = "janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre"
# The date a figure gives for itself: "relevé en juillet 2026", "(relevé de mars 2025)", "(Por Esto, juillet 2026)",
# "(octobre 2026)". Not a period ("du 2 novembre au 31 décembre 2026") nor a start ("depuis janvier 2026").
OWN_DATE = re.compile(rf"\brelevée?s? (?:en |de |d’|d'|le |du |au )((?:\d{{1,2}}(?:er)? )?(?:{MONTHS}) 20\d\d)"
                      rf"|\((?:[^()]*, )?((?:{MONTHS}) 20\d\d)\)", re.IGNORECASE)
# "(novembre 2026)" after an opening, a festival or a deadline dates that event, not the day the figure was read.
EVENT = re.compile(r"\b(?:ouvertures?|réouvertures?|inaugurations?|festivals?|fêtes?|carnavals?|éditions?|prévue?s?)\b", re.IGNORECASE)
YEAR = re.compile(r"\b20\d\d\b")
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
    # Never a line that ends on an article, a preposition or a number ("…pour Bangkok, le / Nord", "Le Japon en 2 /
    # semaines"), nor a cut inside a name ("Les Cinque / Terre en train").
    spans = [(start, end) for _, start, end in place_names.names(value, sentence=True)]
    cut_name = lambda pair: any(start < len(pair[0]) < end for start, end in spans)
    return list(min(fitting, key=lambda pair: (dangling(pair[0]) or cut_name(pair) or cut_number(pair), max(map(len, pair)), -len(pair[0]))))


def cut_number(pair: tuple[str, str]) -> bool:
    """A number at the end of a line, cut from what it counts ("Le Japon en 2 / semaines"); a year before a preposition
    is not ("du 28 octobre 2026 / au 3 janvier 2027")."""
    last, following = pair[0].split()[-1], pair[1].split()[0].lower()
    return last.isdigit() and following not in DANGLING


# Small words that open what follows: a line never ends on one of them.
DANGLING = frozenset("le la les l’ l' un une des du de d’ d' à au aux en et ou pour par sur dans chez vers sans".split())


def dangling(line: str) -> bool:
    last = line.split()[-1].lower() if line.split() else ""
    return last in DANGLING or last.endswith(("’", "'"))


def joined_title(short: str, label: str) -> str:
    """'Kyoto en train : jour par jour'; a short title that already carries a colon or ends a question takes a dash."""
    return f"{short} — {label}" if ":" in short or short.rstrip().endswith(("?", "!")) else f"{short} : {label}"


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


class Line(str):
    """A line of a caption that can also be said shorter (`short`), for a caption that runs past its limit."""

    def __new__(cls, text: str, short: str | None = None):
        line = super().__new__(cls, text)
        line.short = text if short is None else short
        return line


def caption_emoji(value: str, label: str) -> str:
    """Price, duration, boat, journey, ticket, walk: the first that fits; a pin otherwise. A distance alone is not a
    walk, and a line is a journey by what it opens on: "le Grand Bouddha du Tōdai-ji, …, à 45 minutes par le train"
    is the fee of a temple, not a train."""
    first = place_names.folded(label)[:place_names.OPENING_WORDS]
    opening, ways = " ".join(first), place_names.ways(first)
    # The pictogram of a journey is the one of the means of transport its line names: a bus is not a train ("le
    # minibus Phantip", "bus de remplacement"), and a ticket for a town is no journey at all.
    ride = ride_emoji(first, ways, label)
    tests = (("💶", is_money(value)), ("⏱️", re.search(r"\b(min|h|jours?)\b", value)), (ride, ride),
             ("🎟️", re.match(r"(?:l )?entree\b", opening)), ("🥾", re.search(r"marches|sentier|randonn|à pied", value + label)))
    return next((emoji for emoji, fits in tests if fits), "📍")


def ride_emoji(first: list[str], ways: set[str], label: str) -> str | None:
    if "water" in ways or "rabelo" in first:
        return "⛴️"
    if "road" in ways:
        return "🚌"
    if "metro" in ways or "tram" in ways:
        return "🚇"
    if "rail" in ways or place_names.journey(label):
        return "🚆"
    return None


WHEN_TO_GO = "quand partir"


def when_to_go(article: dict) -> bool:
    """A guide that says when to go: its title promises a moment, not figures."""
    return article.get("shortTitle", "").lower().startswith(WHEN_TO_GO)


# A price in any currency the guides give: the yen and the dong are prices too ("176 ¥" went under a pin).
CURRENCY_SIGNS = frozenset("€¥₫£$฿")
CURRENCY_WORDS = frozenset("baht bahts dirham dirhams dh peso pesos yen yens dong dongs couronne couronnes "
                           "nok sek dkk mxn thb vnd jpy mad".split())


def is_money(value: str) -> bool:
    return bool(CURRENCY_SIGNS & set(value) or CURRENCY_WORDS & set(place_names.folded(value)))


def caption_line(fact: dict) -> str:
    """'59 € : la cabine du train de nuit', but '180 exposants au marché' and '120 km entre Mérida et la gare':
    no colon when the label simply carries on from the figure (a bare number, or a label opening on a preposition)."""
    value, label = fact["value"], fact["label"]
    # "64 mm à Koh Samui", not "64 mm : à Koh Samui": a colon never stands before a preposition.
    flows = re.fullmatch(r"[\d\s]+", value) or re.match(r"(?:de|d’|d'|du|des|entre|pour|par|sur|depuis|jusqu|à|au|aux|en|dans|chez|vers|avant|après)(?!\w)", label)
    return caption_emoji(value, label) + " " + value + (" " if flows else " : ") + label


# What a figure holds under: left out, the figure would be promised to everyone, all day, all year.
CONDITION = re.compile(r"\(?(?:aux? heures? (?:creuses|de pointe)|hors |en (?:semaine|basse saison|haute saison|prévente)|le week-end|"
                       r"sur réservation|sous conditions?|à partir de |dès |uniquement|seulement|sauf |pour les moins de |avant \d|après \d)", re.IGNORECASE)


def in_enumeration(label: str, cut: int) -> bool:
    """A comma between two short items with more to come ('Valladolid, Chichén Itzá, Mérida, Uxmal et Tulum'):
    the middle of a list. A comma after a long clause ('…et 13 nuits (154 120 ¥), capsule ou dortoir') is a pause."""
    before = re.split(r", | et | ou ", label[:cut])[-1]
    after = re.split(r", | et | ou ", label[cut + 2:], maxsplit=1)
    if len(after) < 2 or len(after[0].split()) > 3:
        return False
    # "…de la Bahia, des tombeaux saadiens ou d’El Badi": the item after the comma carries on a list of "de …".
    return len(before.split()) <= 3 or bool(re.match(r"(?:des?|du) |d[’']", after[0]) and re.search(r"\b(?:des?|du) |\bd[’']", before))


def short_label(label: str, limit: int = SHORT_LABEL) -> str:
    """The label up to a natural pause: still the guide's own words, short enough for a three-second plan."""
    if len(label) <= limit:
        return label
    # Never inside a parenthesis: "(Bahia, tombeaux saadiens, El Badi)" is dropped whole or kept whole.
    # Never inside a list: "Valladolid, Chichén Itzá, Mérida, Uxmal et Tulum" keeps all its places or is shown whole.
    # Never before what a price depends on: "le plafond du métro en zones 1-2, aux heures creuses" cut at its comma
    # would promise that fare all day.
    cuts = [match.start() for match in re.finditer(r" \(| ; |, | : ", label)
            if label[:match.start()].count("(") == label[:match.start()].count(")")
            and not (match.group() == ", " and in_enumeration(label, match.start()))
            and not CONDITION.match(label[match.end():])]
    fitting = [cut for cut in cuts if MIN_SHORT_LABEL <= cut <= limit]
    if not fitting:
        # No punctuation in reach: stop before what only qualifies the figure ("… pour un étranger | depuis le 27 mars").
        fitting = [match.start() for match in SOFT_PAUSE.finditer(label)
                   if MIN_SHORT_LABEL <= match.start() <= limit and label[:match.start()].count("(") == label[:match.start()].count(")")]
    return label[:max(fitting)].rstrip() if fitting else label


def promise_of(article: dict) -> str | None:
    """What the guide's own title promises after its colon ("Quand partir en Thaïlande : le bon mois pour Bangkok, le
    Nord, l'Andaman et Koh Samui"): the precise hook of a post that has no figure to open on."""
    title = article.get("title", "")
    promise = title.split(" : ", 1)[1].strip() if " : " in title else ""
    promise = promise[:1].upper() + promise[1:]
    return promise if 20 <= len(promise) <= 90 and checked(promise, 120) else None


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
    if match[2] and EVENT.search(fact["label"]):
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


def naming_columns(rows: list[list]) -> int | None:
    """How many leading columns it takes to tell the rows of a table apart: one as a rule, two where the first repeats
    ("Alfa Pendular | Turística", "Alfa Pendular | Conforto"). None when a column must still follow and none is left."""
    for count in range(1, min(len(row) for row in rows)):
        if len({tuple(str(cell).strip() for cell in row[:count]) for row in rows}) == len(rows):
            return count
    return None


def prices_in_several_columns(headers: list, rows: list[list], named: int) -> bool:
    """Prices in several columns ("Jour A", "Jour B", "Jour C" of the Treno Card): the first alone would say the
    cheapest is the price. Such a table stays in the guide."""
    priced = [column for column in range(named, len(headers)) if all(is_money(str(row[column])) for row in rows if len(row) > column)]
    return len(priced) > 1


def table_of(article: dict, page: str) -> dict | None:
    """A whole short table of the guide (three to five rows): the columns that name each row, then the next one, every
    row read on the page. "Alfa Pendular : Turística" three times told nothing; the fare is in the column after."""
    for section in article.get("sections", []):
        table = section.get("table") or {}
        headers, rows = table.get("headers") or [], table.get("rows") or []
        if len(headers) < 2 or not TABLE_ROWS[0] <= len(rows) <= TABLE_ROWS[1] or any(len(row) < 2 for row in rows):
            continue
        named = naming_columns(rows)
        if not named or named >= len(headers) or prices_in_several_columns(headers, rows, named):
            continue
        cells = [[" ".join(str(cell).strip() for cell in row[:named]), str(row[named]).strip()] for row in rows]
        quoted = all(checked(a, 60) and checked(b, 60) and p.normalized(a + " " + b) in page for a, b in cells)
        title = lines_of(str(headers[named]).strip(), 22)
        fits = p.motion.table_fits(cells, TABLE_FONTS)
        if quoted and fits and title and all(checked(line, 34) for line in title) and p.normalized(str(headers[named])) in page:
            return {"rows": cells, "title": title, "header": str(headers[named]).strip(), "section": section}
    return None


# The type a reel's table is drawn in (production.MOTION_FONTS): a table is chosen only when its rows hold in it.
TABLE_FONTS = p.motion.Fonts(*(str(p.HERE / "assets" / name) for name in (
    "dmsans-regular.ttf", "dmsans-bold.ttf", "playfair.ttf", "notosans-regular.ttf", "notosans-bold.ttf")))


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
        formats.insert(0 if when_to_go(article) else len(formats), "tableau")
    # No "express" any more: two figures in twelve seconds left a reel almost empty (Yucatán, 20/11/2026).
    return formats + ["liste"]


def ordered(formats: list[str], used: list[str]) -> list[str]:
    """Formats never used for this guide first; then the least recently used."""
    fresh = [f for f in formats if f not in used]
    return fresh + sorted((f for f in formats if f in used), key=lambda f: max(i for i, u in enumerate(used) if u == f))


# --- plans -------------------------------------------------------------------

# Names of sections that sum the guide up: above a figure they say nothing.
SUMMED_UP = re.compile(r"\b(?:en bref|l.essentiel|avant tout|a retenir|resume|recapitulatif|comparatif|coup d.oeil)\b")
# Where one waits for a ride: not a picture to stand for a whole place.
STOPS = frozenset("gare station quai quais platform stazione estacao estacion terminal arret".split())

# Words that name nothing: two texts that share only these are not about the same thing.
EMPTY_WORDS = frozenset("pour entre dans avec sans sous vers chez depuis selon plus moins tout tous toute toutes cette leur leurs "
                        "dont comme aussi tres deux trois quatre jour jours nuit nuits prix tarif euros pesos".split())


def words_of(value: str, numbers: bool = False) -> set[str]:
    """Words of four letters and more that name something; a dash separates two words ('Mérida–Cancún' names both towns).
    A number names nothing: "2026" in a Commons title does not make a photo of the rate of the euro on 6 November 2026.
    `numbers`: keep them (stale_lots.py counts the words of a quote beside its numbers)."""
    found = re.findall(r"[a-z0-9]{4,}", destinations.ascii_fold(re.sub(r"[^\w\s]", " ", value)).lower())
    return {word for word in found if numbers or not word.isdigit()} - EMPTY_WORDS


# Kinds of places: "la tour des Clérigos" and "l’Andante Tour 3", "la villa des Mystères" and the villa Cimbrone, "un
# monument de la médina" and a lamp maker "in the medina" share such a word and nothing else. Alone it ties no figure
# to a photo; beside a name the two share, it counts.
PLACE_KINDS = frozenset("tour tours villa villas ville villes village villages medina place places pont ponts palais jardin jardins "
                        "musee musees temple temples eglise eglises cathedrale chateau plage plages marche marches parc parcs "
                        "quartier quartiers gare gares port ports centre monument monuments".split()) | (place_names.GENERIC - {"train", "trains"})


def words_shared(photo: tuple, target: set[str], family: str | None = None, kinds: bool = False) -> set[str]:
    """Which of these words the photo's caption, its Commons title and its identifier carry. `family`: the prefix
    all the photos of the post share says nothing of what one of them shows ("amalfi-positano" is a photo of Positano).
    `kinds`: a kind of place shared alone counts too (for the photo the guide itself put beside that text)."""
    prefix, _, rest = photo[0].partition("-")
    described = " ".join([(rest if prefix == family else photo[0]).replace("-", " "), photo[2], str(photo[1].get("commonsTitle", ""))])
    shared = target & words_of(described)
    return shared if kinds or shared - PLACE_KINDS else set()


def words_shown(photo: tuple, target: set[str], family: str | None = None, kinds: bool = False) -> int:
    return len(words_shared(photo, target, family, kinds))


def section_place(section: dict | None, country: frozenset | set) -> str:
    """The stretch of a section's title that names its places ("Jours 6 et 7 — Hué" → "Hué", "Jours 5 à 8 — Kyoto
    et Nara" → "Kyoto et Nara"); "" when it names none, or when the section sums the guide up."""
    title = str((section or {}).get("title") or "")
    if not title or SUMMED_UP.search(destinations.ascii_fold(title).lower()):
        return ""
    return place_names.titled(title, country)


class Media:
    """Photos and clips still unused in this reel: a photo is never shown twice, and never under another place's name."""

    def __init__(self, photos: list[tuple[str, dict, str]], clips: list[tuple[str, dict]], reserve: int = 0, cover: str | None = None,
                 emblematic: tuple[str, ...] = (), everywhere: str = "", outings: tuple = (), reserved: str | None = None):
        self.photos, self.clips, self.reserve, self.cover = list(photos), list(clips), reserve, cover
        # The guide's own cover: the opening takes it first when no plan has (review of PR 57). A carousel otherwise
        # opens on a photo that turns from post to post (`cover`).
        self.reserved = reserved
        # The places the guide sends its reader to for a day out (place_names.outings): Essaouira, Ouzoud, the Ourika
        # for Marrakech. A photo of one of them never opens a post; a quarter or a nearby town is no outing.
        self.outings = tuple(outings)
        self.all = list(photos)
        # The pictures that can stand for the whole place under the call to action, the best first.
        self.emblematic = [photo_id for photo_id in emblematic if photo_id != cover]
        # Files found by the search (media_library.closing_mark): nobody looked at them, they never open a post.
        self.found = {photo[0] for photo in photos if photo[1].get("automatic") is True}
        prefixes = {photo[0].partition("-")[0] for photo in photos if photo[0] not in self.found}
        self.family = prefixes.pop() if len(prefixes) == 1 else None
        # The name of the place and of its country is in every caption: sharing it says nothing of what a photo shows.
        self.everywhere, self.country = words_of(everywhere), place_names.words(everywhere)

    def target(self, text: str) -> set[str]:
        return words_of(text) - self.everywhere

    def shown_elsewhere(self, text: str) -> bool:
        """A photo of this post that another plan has taken, or that is kept for the call to action, shows what
        `text` names better than any photo still free: over another picture, that figure would name one place while
        the post shows it elsewhere. The figure stays in the guide."""
        # A fact that names a place is not concerned: its photo is chosen by that place alone, and any free photo of it
        # will do ("44 620 ¥ Tokyo–Kyoto–Hiroshima" over Shibuya once the shinkansen is taken).
        if self.located(text):
            return False
        # A town's ticket is shown by any metro, tram, bus or train of the town: the metro taken by another plan does not
        # keep it from a tram (review of PR 57).
        if place_names.TOWN_TICKETS & set(place_names.folded(text)):
            return False
        target = self.target(text)
        return max((self.shared(ph, target) for ph in self.all), default=0) > max((self.shared(ph, target) for ph in self.free()), default=0)

    def shared(self, photo: tuple, target: set[str]) -> int:
        return words_shown(photo, target, self.family)

    def described(self, photo: tuple) -> set[str]:
        """The words of what says what a photo shows: its identifier, its caption and its Commons title, without
        where the view is taken from nor a place the caption only compares with (place_names.pictured)."""
        prefix, _, rest = photo[0].partition("-")
        return place_names.pictured(rest if prefix == self.family else photo[0], photo[2], str(photo[1].get("commonsTitle", "")), self.country)

    def told(self, photo: tuple) -> set[str]:
        """What the photo says itself, in its caption and its title: not the identifier it is filed under."""
        return place_names.pictured("", photo[2], str(photo[1].get("commonsTitle", "")), self.country)

    def places(self, text: str) -> set[str]:
        """The words of the precise places a fact names (Similan, Kinkaku-ji, Uxmal), the destination aside."""
        return place_names.proper(text, self.country)

    def located(self, text: str) -> bool:
        """The fact is about one place or one part of the destination: only a photo of it will do."""
        return bool(place_names.names(text, self.country) or place_names.region(text))

    def opens_on(self, text: str, photo_id: str, title: str) -> bool:
        """The opening may say this over that photo (place_names.opening_fits, as production.py reads it)."""
        photo = next((ph for ph in self.all if ph[0] == photo_id), None)
        return not photo or place_names.opening_fits(text, title, self.described(photo), self.country)

    def where(self, fact: dict) -> str:
        """The places a fact that names none is about: those its section's title names ("les tombeaux coûtent 150 000 ₫
        chacun" in "Jours 6 et 7 — Hué" is about Hué, and went over Ha Long once the photo of Hué was taken)."""
        if self.located(fact["label"]):
            return ""
        return section_place(fact.get("section"), self.country)

    def about(self, fact: dict) -> str:
        """What a photo is chosen for: the fact, and the places of its section when it names none itself."""
        # The figure with its label: "*10 trains* directs par jour entre Cordoue et Grenade" is a journey by train.
        said = f"{fact['value']} {fact['label']}" if re.search(r"[^\W\d_]{3,}", fact["value"]) else fact["label"]
        where = self.where(fact)
        return f"{said} ({where})" if where else said

    def recorded(self, photo: tuple) -> list:
        """The precise places the record of a photo names, whole (place_names.record)."""
        return place_names.record(photo[0], photo[2], str(photo[1].get("commonsTitle", "")), self.country, self.family)

    def fits(self, reading, photo: tuple) -> int:
        """How well this photo is a photo of what a fact is about (place_names.fits), as production.py judges it."""
        return place_names.fits(reading, self.described(photo), self.told(photo), self.recorded(photo))

    def beside(self, own: tuple, text: str, target: set[str]) -> set[str]:
        """What the photo the guide put beside a text that names no place shows of what the text says: the words the
        two share, were it a kind of place ("Le pont en métro" and the photo of the bridge)."""
        return words_shared(own, target, self.family, kinds=True)

    def left_for(self, text: str, avoid: frozenset = frozenset()) -> list:
        """The free photos a fact that none of them shows may still take: none when the fact names a precise place or
        a part of the destination. "350 mm de pluie à Phuket" went over the inside of a sleeping car, and "42 €
        l'entrée de SantaPark" over huskies (13/11/2026): such a fact stays in the caption and in the guide."""
        if self.located(text) or place_names.strict_journey(text):
            return []
        return [ph for ph in self.free() if ph[0] not in avoid and not self.misleads(text, ph)]

    def takeable(self, text: str, avoid: frozenset = frozenset()) -> list:
        """The photos a figure that none of them shows may take, the plainest first: not the two reserved ones."""
        kept = self.kept()
        return sorted((ph for ph in self.left_for(text, avoid) if ph[0] not in kept), key=self.plain)

    def misleads(self, text: str, photo: tuple) -> bool:
        """The photo shows another train than the one the fact names, or another means of transport than its journey's."""
        # A train borrowed from another guide's photos (media_library.vehicle_candidates) goes only under a fact that
        # names it: "le train de Lisbonne à Sintra" went over an Alfa Pendular, which does not go to Sintra (review of
        # PR 57).
        borrowed = set(photo[1].get("borrowedFor") or ())
        named = place_names.brands(place_names.words(text))
        if borrowed and not borrowed & named:
            return True
        on = place_names.vehicle(photo[0], photo[2], str(photo[1].get("commonsTitle", "")))
        # A fact of trains that names no place goes over a train, else it stays in the guide: « 85×55×35 cm … sur les
        # trains internationaux CP » went over the roofs of Alfama (counter-review of PR 57).
        if place_names.ways(place_names.folded(text)) == {"rail"} and not self.located(text) and "rail" not in on:
            return True
        if place_names.brand_clash(text, self.described(photo)) or place_names.other_ride(on, text):
            return True
        # "2 € la traversée du Tage en ferry vers Cacilhas" over a church of Alfama: a ride to another place goes over
        # that ride (review of PR 56).
        return place_names.ride_needed(text, self.described(photo), self.country) and not place_names.ride(self.told(photo), text)

    def above(self, section: dict | None, photo_id: str, place: str, label: str = "") -> str:
        """The label written above a figure: the name of its section over that section's own photo; over another
        photo, or when the section has none, that name only if it says no place, no part of the destination and no
        means of transport the photo is not of ("Le Nord" is not written over the Grand Palace of Bangkok, nor "Le
        Sud" over Tràng An, nor "Dans le métro" over a taxi); the place otherwise. Never the name of a section that
        sums the guide up ("En bref" says nothing), nor a name with a year over a figure of another year."""
        name = kicker_of(section, place)
        if name != place and not self.says_of(name, label, photo_id):
            return place
        own = section.get("image") if section else None
        if own:
            return name if photo_id == own else place
        photo = next((ph for ph in self.all if ph[0] == photo_id), None)
        if not photo:
            return name
        shown = self.described(photo)
        # A title begins with a capital by grammar ("Budget", "Aurores boréales"): its first word alone is no place.
        named = place_names.names(name, self.country, sentence=True)
        if named and not any(place_names.shows(one, place_names.widened(shown)) for one in named):
            return place
        region = place_names.region(name)
        if region and not named and not region <= place_names.words(photo[2]):
            return place
        ways = place_names.ways(place_names.folded(name))
        return place if ways and not ways & place_names.ways(shown) else name

    def says_of(self, name: str, label: str, photo_id: str) -> bool:
        """A section's name may stand above this figure: it sums nothing up, carries no other year than the figure's,
        and speaks of the figure (announces)."""
        years, dated = set(YEAR.findall(name)), set(YEAR.findall(label))
        if SUMMED_UP.search(destinations.ascii_fold(name).lower()) or (years and dated and not years & dated):
            return False
        return not label or self.announces(name, label, photo_id)

    def announces(self, name: str, label: str, photo_id: str) -> bool:
        """The section's name speaks of this figure: a day of the itinerary ("Jours 3 à 5"), or a word the figure or
        its photo shares with it ("Dans le train" over a train). "Quand partir" over "45 jours sans visa", "Le
        calendrier de l'hiver 2026" over the cap of the Tube said nothing of the figure (review of PR 54)."""
        if DAY_HEAD.match(name):
            return True
        photo = next((ph for ph in self.all if ph[0] == photo_id), None)
        record = " ".join([photo[0].replace("-", " "), photo[2], str(photo[1].get("commonsTitle", ""))]) if photo else ""
        return bool(words_of(name) & (words_of(label) | words_of(record)))

    def spare(self) -> str | None:
        """The last photo left that can close the post: no plan takes it, whatever it names."""
        left = [wanted for wanted in self.emblematic if any(ph[0] == wanted for ph in self.photos)]
        return left[0] if len(left) == 1 else None

    def free(self) -> list:
        """The photos a plan may take when it names what they show: all but the last one that can close the post. In a
        post completed by files found by the search, the cover too is kept: such a file never opens a post."""
        held = {self.spare(), self.cover if self.found else None}
        shown = self.subjects_shown()
        # Never the same subject twice in one post: El Castillo opened the carousel of Yucatán and came back on a plan
        # under another file name (review of PR 56). Never two trains borrowed from other guides in one post.
        taken = self.taken()
        borrowed = any(self.borrowed(ph) for ph in taken)
        # A train borrowed from another guide never joins a post that shows that train already, nor the reverse: two
        # Alfa Pendular stood in one post of « Portugal bagages » (review of PR 57).
        trains = set().union(*(self.brands_shown(ph) for ph in taken)) if taken else set()
        lent = set().union(*(self.brands_shown(ph) for ph in taken if self.borrowed(ph))) if borrowed else set()
        return [ph for ph in self.photos if ph[0] not in held and not self.subjects(ph) & shown and not (borrowed and self.borrowed(ph))
                and not (self.borrowed(ph) and self.brands_shown(ph) & trains) and not self.brands_shown(ph) & lent]

    def brands_shown(self, photo: tuple) -> set[str]:
        """The trains a photo shows by name ("Un train Alfa Pendular de CP à quai")."""
        return place_names.brands(self.told(photo))

    def taken(self) -> list:
        """The photos this post has already taken."""
        return [ph for ph in self.all if ph not in self.photos]

    @staticmethod
    def borrowed(photo: tuple) -> bool:
        """A photo of a train filed under another guide, offered for the fact that names that train only."""
        return bool(photo[1].get("borrowedFor"))

    def subjects(self, photo: tuple) -> set:
        """What a photo is of (place_names.photo_subjects): a monument of the table reviewed by hand, or the places its
        caption names when it names two at least."""
        return place_names.photo_subjects(photo[2], str(photo[1].get("commonsTitle", "")), self.country, str(photo[1].get("categories", "")))

    def subjects_shown(self) -> set:
        """The subjects of the photos this post has already taken."""
        return {subject for ph in self.taken() for subject in self.subjects(ph)}

    def excursion(self, photo: tuple) -> bool:
        """A photo of a place the guide sends its reader to for a day out ("Des barques bleues au pied de la Skala du
        port, à Essaouira" in a guide of Marrakech): an outing, never the place the post opens on (review of PR 56)."""
        return place_names.on_an_outing(photo[2], str(photo[1].get("commonsTitle", "")), self.outings, self.country)

    def room(self) -> int:
        return len(self.photos) + len(self.clips) - self.reserve

    def kept(self) -> set[str]:
        """The two pictures a plan takes only when its text names what they show: the cover, which opens the post
        otherwise, and the best one still free for the call to action. A plan that no photo shows is given another."""
        last = next((wanted for wanted in self.emblematic if any(ph[0] == wanted for ph in self.photos)), None)
        return {self.cover, last} - {None}

    def ride(self, text: str, pool: list, own: tuple | None, target: set[str], wider: set[str]) -> tuple | None:
        """For a journey ("Tokyo → Kyoto en Nozomi"), a photo of the ride before a town it names: the guide's own
        photo of it, else the one that names the most places of the journey; a ride of the same kind as the one the
        text opens on (never a shinkansen for "Le bus 205 pour le Kinkaku-ji"), and never one that stands somewhere
        else: its record names one of the places of the journey, whole, or no place at all ("Hué → Đà Nẵng en
        train" went over the train street of Hanoi, "Tokyo → Kyoto" over the sign of Shin-Fuji station)."""
        reading = place_names.read(text, self.country)
        # A ride by what its caption and title show, never by the identifier it is filed under ("train-campanha").
        rides = [ph for ph in pool if place_names.ride(self.told(ph), text) and place_names.on_the_way(self.recorded(ph), reading)]
        if not rides:
            return None
        places = self.places(text)
        return own if own in rides else max(rides, key=lambda ph: (len(places & self.described(ph)), self.shared(ph, target), self.shared(ph, wider)))

    def of_the_region(self, region: set[str], pool: list, own: tuple | None, section: dict | None) -> tuple | None:
        """The photo of the part of the destination a fact is about ("222 h de soleil au sud" went over Garachico, on
        the north coast): a photo whose caption says that part; the photo of the fact's own section when that section
        is about that part ("Le sud : Costa Adeje") and the photo names no precise place; else a photo that names no
        precise place. Never a photo of a precise place whose caption does not say that part (Masca under "Le sud")."""
        said = lambda value: region <= place_names.words(value)
        if own and said(own[2]):
            return own
        if own and said((section or {}).get("title", "")) and not self.recorded(own):
            return own
        ranked = [ph for ph in pool if said(ph[2])] + [ph for ph in pool if not self.recorded(ph)]
        return next(iter(ranked), None)

    def of_the_place(self, text: str, pool: list, own: tuple | None, target: set[str], wider: set[str], also: str = "") -> tuple | None:
        """The photo of the place a fact is about, None when none is: whole names, never a word of one ("la balade
        en barque de Tràng An à Ninh Bình" went over the bay of Ha Long, filed "Quảng Ninh"). The first place a fact
        names wins wherever the record names it; another place it lists, only when the photo's caption or title says
        it; a place it only situates the first one in, only when the photo names no other place (place_names.fits)."""
        reading = place_names.read(text, self.country)
        named = [ph for ph in pool if self.fits(reading, ph)]
        if not named:
            return None
        # Between two photos of it, the one that shows what the plan then says ("Mérida et Uxmal" and its "l'entrée
        # d'Uxmal": Uxmal), the more places of the fact, the closer; then the guide's own.
        then = place_names.read(also, self.country).first if also else None
        many = lambda ph: sum(place_names.shows(name, self.described(ph)) for name in ((reading.first,) if reading.first else ()) + reading.listed)
        close = lambda ph: (bool(then and place_names.shows(then, self.described(ph))), many(ph), self.fits(reading, ph),
                            len(words_shared(ph, target, self.family, kinds=True)))
        best = max(named, key=lambda ph: (close(ph), self.shared(ph, wider)))
        return own if own in named and close(own) >= close(best) else best

    def sharing(self, pool: list, own: tuple | None, target: set[str], wider: set[str]) -> tuple | None:
        """The photo that shares the most words with a text, None when none shares any. The guide's own photo for that
        text wins when it shares a word, and stands in when no photo shares any."""
        shared = lambda ph: self.shared(ph, target)
        best = max(pool, key=lambda ph: (shared(ph), self.shared(ph, wider)), default=None)
        # The guide put its own photo beside this text: a kind of place the two share ("Le pont en métro" and the photo
        # of the bridge) is proof enough for that photo, and for no other.
        mine = words_shared(own, target, self.family, kinds=True) if own else set()
        if own and (best is None or not shared(best) or (mine and not any(mine < words_shared(ph, target, self.family) for ph in pool))):
            return own
        return best if best is not None and shared(best) else None

    def named(self, text: str, section: dict | None, avoid: frozenset = frozenset(), also: str = "") -> tuple | None:
        """The photo that shows what `text` names. A fact about a place goes over a photo of that place, read as
        production.py reads it (place_names.fits); a journey over a ride on the way; a part of the destination over a
        photo of that part; any other fact over the photo whose id, caption or title shares the most words with it.
        The section's own photo wins when it shares a word, and stands in when no photo shares any; it gives way
        when it shows something else ("Chichén Itzá à l'ouverture" is not shown by the cenote of that afternoon), or
        when another photo shares all it shares and more (the Grand Palace, not Wat Arun, for "le Grand Palais de
        Bangkok": the two are in Bangkok). `avoid`: photos kept for a plan still to come. `also`: what else the plan
        says, to choose between two photos that share as much with `text` (the train, not the cathedral, for "Mérida–
        Tulum en train direct" and its "train direct Mérida Teya → Tulum")."""
        target, wider = self.target(text), self.target(text + " " + also)
        wanted = section.get("image") if section else None
        # Never a photo of another train than the one the fact names ("Intercidades" over an Alfa Pendular).
        # …nor of another means of transport than the one of a journey (the boats of Tràng An for the night train).
        pool = [ph for ph in self.free() if ph[0] not in avoid and not self.misleads(text, ph)]
        own = next((ph for ph in pool if ph[0] == wanted), None)
        if place_names.journey(text):
            pick = self.ride(text, pool, own, target, wider)
            if pick or place_names.strict_journey(text):
                return pick
        # A fact that names a precise place goes over a photo that names that place, or over none: a word they share
        # ("îles") is not enough, and a photo that names nothing is not a photo of that place either.
        if place_names.names(text, self.country):
            return self.of_the_place(text, pool, own, target, wider, also)
        region = place_names.region(text)
        if region:
            return self.of_the_region(region, pool, own, section)
        beside = self.beside(own, text, target) if own else set()
        if beside and not any(beside < words_shared(ph, target, self.family) for ph in pool):
            return own
        return self.sharing(pool, own, target, wider)

    def photo(self, text: str = "", section: dict | None = None, strict: bool = False, avoid: frozenset = frozenset(),
              also: str = "") -> tuple[str, str]:
        """A photo for this text. `strict`: only a photo that shows what the text names (a stage of an itinerary)."""
        pick = self.named(text, section, avoid, also)
        located = self.located(text)
        if not pick and (strict or located or len(self.photos) <= self.reserve):
            raise Held("no_photo_of_this_place" if strict or located else "not_enough_photos_or_figures")
        # The opening and the ending are reserved before the figures: a figure that no photo shows takes a photo left
        # free, never the cover nor the photo kept for the call to action. "100 à 160 dh le taxi au départ de
        # l'aéroport" took Jemaa el-Fna and the reels of Marrakech had only Essaouira left to open on (review of PR 56).
        pick = pick or next(iter(self.takeable(text, avoid)), None)
        if not pick:
            raise Held("not_enough_photos_or_figures")
        self.photos.remove(pick)
        return ("photo", pick[0])

    def plain(self, photo: tuple) -> tuple:
        """How well a photo stands under a fact that names no place (a budget, a rate of exchange): a photo that stands
        for the destination first; never before it a station, a platform, a vehicle or a detail of one paragraph
        ("872 € le budget" went over the platform of Shin-Fuji, the rate of the euro over the deer of Nara)."""
        detail = bool((place_names.RIDES | STOPS) & self.described(photo))
        return (not photo[1].get("emblematic"), detail, bool(self.recorded(photo)))

    def closing(self) -> tuple[str, str]:
        """The picture under the call to action: one that stands for the place, a photo marked `emblematic` by hand
        or one the guide itself shows; else any photo of the destination the post has not shown, the plainest first,
        that repeats none of its subjects (a reel of Porto, of the Japan budget or of Lapland waited for an emblematic
        photo the subjects had all used: review of PR 57). Never a file found by the search, a train borrowed from
        another guide or an outing."""
        shown = self.subjects_shown()
        fresh = [ph for ph in self.photos if not self.subjects(ph) & shown and not self.borrowed(ph)]
        pick = next((ph for wanted in self.emblematic for ph in fresh if ph[0] == wanted), None)
        seen = sorted((ph for ph in fresh if ph[0] not in self.found and not self.excursion(ph)), key=self.plain)
        if not pick and not seen:
            raise Held("no_photo_left_for_the_call")
        pick = pick or seen[0]
        self.photos.remove(pick)
        return ("photo", pick[0])

    def moving(self, text: str = "", section: dict | None = None, strict: bool = False) -> tuple[str, str]:
        """A real clip of the destination when one is left and no photo shows this very plan."""
        # A clip is a view of the destination, nobody knows of which place: never under a fact that names one.
        if self.clips and not strict and not self.located(text) and not self.named(text, section):
            return ("clip", self.clips.pop(0)[0])
        return self.photo(text, section, strict)

    def opening(self, cover: str | None) -> tuple[str, str]:
        """The cover photo of the guide when it is still free: it is the picture people see first. When a plan took
        it, another photo that stands for the place, else one a person looked at; never the last one kept for the
        call to action, and never a file found by the search: the post waits rather than open on it."""
        self.reserve = max(0, self.reserve - 1)
        spare = self.spare()
        shown = self.subjects_shown()
        seen = [ph for ph in self.photos if ph[0] not in self.found and not self.subjects(ph) & shown and not self.borrowed(ph)]
        left = [ph for ph in seen if ph[0] != spare]
        # A photo that shows numbers of its own (a display, a board of fares) opens a post only when no other can.
        left = [ph for ph in left if not ph[1].get("figures")] or left
        # The post opens on the destination, never on an outing ("…, à Essaouira" opened the reels of Marrakech once a
        # figure had taken Jemaa el-Fna): with only outings left, the post waits (review of PR 56).
        left = [ph for ph in left if not self.excursion(ph)]
        seen = [ph for ph in seen if not self.excursion(ph)]
        # The guide's own cover first (review of PR 57), then the photo this post opens on.
        pick = (next((ph for ph in seen if ph[0] == self.reserved), None) or next((ph for ph in seen if ph[0] == cover), None)
                or next((ph for ph in left if ph[0] in self.emblematic), None) or (left[0] if left else None))
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
    picture = media.moving(media.about(fact), fact["section"])
    # The label above the figure is the section's name only over that section's own photo, or when the section has
    # none: "Aurores boréales" is not written over a picture of the village.
    # …and a name that carries a year is not written over a figure of another year ("La ligne du Nord en 2026" over
    # "38,3 % des Alfa Pendular à l'heure en 2025").
    kicker = media.above(fact["section"], picture[1], place, fact["label"])
    excerpt, label = quoted(fact, tag)
    where, facts = located_by_section(fact, media, excerpt)
    return plan("fact", picture, kicker, headline, seconds_for(detail), detail=detail, facts=facts, tag=label, badge=badge, where=where)


def located_by_section(fact: dict, media: Media, excerpt: str) -> tuple[str | None, list[dict]]:
    """The plan's quotes and, for a fact that names no place in a section about one, the title of that section: quoted
    like the figure, it tells the guard on places (production.py) which place the plan is about."""
    heading = fact.get("heading")
    quotes = [{"source": "guide", "excerpt": excerpt}]
    if not heading or not media.where(fact):
        return None, quotes
    return heading, [{"source": "guide", "excerpt": heading}] + quotes


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
        # A "quand partir" guide promises a moment, not "4 chiffres": the hook says what its own title promises
        # ("Le bon mois pour Bangkok, le Nord, l'Andaman et Koh Samui"), quoted from the guide (review of 13/11/2026).
        told = promise_of(self.article) if when_to_go(self.article) else None
        picture = self.media.opening(self.media.cover)
        # Under the title, a promise that names places only over a photo of one of them (review of PR 53).
        if told and not self.media.opens_on(told, picture[1], self.article.get("shortTitle", "")):
            told = None
        if told:
            return plan("hook", picture, self.kicker, self.title_lines + [promise], HOOK_SECONDS,
                        detail=unbreakable(told), facts=[{"source": "guide", "excerpt": self.article["title"]}], tag=self.tag)
        return plan("hook", picture, self.kicker, self.title_lines + [promise], HOOK_SECONDS,
                    facts=[{"source": "guide", "excerpt": self.opening}], tag=self.tag)


def placed(facts: list[dict], media: Media, limit: int, least: int):
    """The figures a post shows, as indexes of `facts`, each yielded when its photo is about to be taken: first those
    a free photo shows, up to `limit`; then, only to reach `least`, those that no photo of the post shows at all."""
    done = set()
    # A town's ticket goes over any metro, tram, bus or train of the town: it comes after the other figures, which only
    # one ride may show ("l'Andante Tour 3 : métro, bus et trains" took the metro on the bridge Luís I, and "2 min de
    # métro D" was left without a photo: review of PR 57). The post still reads in the guide's order.
    order = sorted(range(len(facts)), key=lambda index: bool(place_names.TOWN_TICKETS & set(place_names.folded(media.about(facts[index])))))
    for wanted, most in ((True, limit), (False, least)):
        for index in order:
            fact = facts[index]
            about = media.about(fact)
            if index in done or len(done) >= most or media.shown_elsewhere(about):
                continue
            # In the second round a figure takes a photo that does not show it: never one that shows another place.
            if media.named(about, fact["section"]) if wanted else media.takeable(about):
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
    whole, short = (f"{line} · {fact['value']} {label}" for label in (fact["label"], fact["short"]))
    # The short form is what the plan itself shows: a caption too long says every stage shorter before it drops one.
    return Line(next((text for text in (whole, short) if len(text) <= CAPTION_LINE), line), short if len(short) <= CAPTION_LINE else line)


def stage_photo(media: Media, step: dict, later: list[dict]) -> tuple[str, str] | None:
    """The photo of one day, or None when no photo shows it. It is chosen for what the plan will say, not for the whole
    title of the day: the place it names first ("Valladolid" over Valladolid, not over the train that goes there),
    else what its figure names. A day keeps its own photo: an earlier one never takes the picture the guide put beside
    a later day ("Mérida–Tulum en train" does not take the ruins of "Tulum et le retour")."""
    kept = frozenset(other["section"].get("image") for other in later) - {step["section"].get("image"), None}
    name, figure = " ".join(step["lines"]), step["fact"]["short"]
    # A figure that is a journey with its two ends and its means ("de l'aéroport de Cancún à Valladolid en Tren Maya")
    # goes over a ride of it, as the guard reads it: never over a street of Valladolid (review of PR 54).
    tries = [(name + " " + figure, "")] if place_names.strict_journey(figure) else [(name, figure), (name + " " + figure, "")]
    for said, also in tries:
        try:
            return media.photo(said, step["section"], strict=True, avoid=kept, also=also)
        except Held:
            continue
    return None


def itinerary_reel(brief: Brief) -> tuple[dict, list[dict], list[str]]:
    """"itineraire": one dated stage per plan, with its figure, shown only over a photo of that very place.
    A stage for which the guide gives no figure, or that no photo shows, stays in the guide."""
    body, lines = [], []
    steps = [step for step in stages(brief.article, brief.page, brief.numbered) if step["fact"]]
    for number, step in enumerate(steps):
        if brief.media.room() < 1:
            break
        picture = stage_photo(brief.media, step, steps[number + 1:])
        if not picture:
            continue
        body.append(stage_plan(step, picture, brief.tag))
        lines.append(stage_line(step))
    if len(body) < MIN_STAGES:
        raise Held("not_enough_stages_with_a_figure_and_their_photo")
    # "Jour par jour" is promised only when every day of the guide is there; otherwise the hook counts what follows.
    every_day = len(body) == sum(1 for section in brief.article.get("sections", []) if DAY.fullmatch(str(section.get("title", "")).strip()))
    return brief.hook(EVERY_DAY if every_day else f"*{len(body)} étapes clés*"), body, lines


HOLLOW_HEADING = frozenset({"notre", "votre", "choix"})   # words of a column heading that name nothing ("Notre choix")


def table_lines(heading: str, rows: list[list[str]]) -> list[str]:
    """The table in the caption, a row a line. The first one says what the table lists ("Le train de nuit pour Chiang
    Mai · Départ de Bangkok — N° 9 : 18 h 40"): four times alone, with nothing to say where they leave from, tell
    nothing (review of 12/11/2026). Only where that heading names something, two words that count at least: "Jour A
    — 1 jour : 22 €" or "Étape — 1 à 3 : Manuel Antonio" says less than the bare row."""
    mark = lambda value: "💶" if is_money(value) else "📅"
    lines = [f"{mark(value)} {label} : {value}" for label, value in rows]
    named = f"{mark(rows[0][1])} {heading} — {rows[0][0]} : {rows[0][1]}"
    telling = len(words_of(heading) - HOLLOW_HEADING) >= 2
    return [named if telling and len(named) <= CAPTION_LINE else lines[0]] + lines[1:]


def table_kicker(brief: Brief, section: dict, photo_id: str) -> str:
    """The name of the table's section when it names what the table's photo shows ("Le train de nuit pour Chiang Mai"
    over a night train); the place otherwise: "En bref", "Arriver" or "Le parcours" name nothing."""
    label = kicker_of(section, brief.place)
    photo = next((ph for ph in brief.media.all if ph[0] == photo_id), None)
    named = photo and words_shared(photo, brief.media.target(label), brief.media.family, kinds=True)
    # "Alfa Pendular ou Intercidades" over the inside of an Alfa: the label would name a train the photo is not.
    if named and place_names.label_clash(label, brief.media.described(photo)):
        return brief.place
    return label if named else brief.place


def caption_heading(brief: Brief, section: dict, kicker: str) -> str:
    """The name the caption gives the table: the plan's label, else the section's name when it says something."""
    if kicker != brief.place:
        return kicker
    named = kicker_of(section, brief.place)
    return named if named != brief.place and table_kicker_names(brief, named) else brief.place


def table_kicker_names(brief: Brief, label: str) -> bool:
    """The section's name says something of the table (it is no summary nor a bare "Arriver")."""
    return any(words_shared(photo, brief.media.target(label), brief.media.family, kinds=True) for photo in brief.media.all)


def under_table(brief: Brief, photo_id: str, rows: list[list[str]]) -> dict | None:
    """The price the guide gives for what the table lists (the berth of the trains whose departures it gives): the
    first price that the table's own photo shows better than any other photo of the post. Only under a short table,
    in two lines, and only a figure dated like the rest of the plan."""
    photo = next((ph for ph in brief.media.all if ph[0] == photo_id), None)
    if not photo or len(rows) > UNDER_TABLE[0]:
        return None
    listed = set(re.findall(r"\d+(?:,\d+)?", " ".join(cell for row in rows for cell in row)))
    for fact in brief.numbered:
        target = brief.media.target(fact["label"])
        shown = brief.media.shared(photo, target)
        # Never a price the table already gives in one of its rows: it would be said twice on one screen.
        if (is_price(fact) and not listed & set(re.findall(r"\d+(?:,\d+)?", fact["value"]))
                and len(fact["value"] + " " + fact["short"]) <= UNDER_TABLE[1] and dated_tag(fact, brief.tag) == brief.tag
                and shown > max((brief.media.shared(ph, target) for ph in brief.media.all if ph is not photo), default=0)):
            return fact
    return None


def table_ride(table: dict) -> str:
    """The text a table of journeys is read as, to choose its photo ("" for any other table)."""
    said = " ".join([table.get("header", ""), str((table.get("section") or {}).get("title", ""))])
    if not place_names.journeys_table(table["rows"], said):
        return ""
    return said + " " + " ".join(" ".join(row) for row in table["rows"])


def table_reel(brief: Brief) -> tuple[dict, list[dict], list[str]]:
    """"tableau": the guide's short table, whole, on one screen to pause; then two figures at most."""
    table = table_of(brief.article, brief.page)
    if not table:
        raise Held("no_short_table")
    if brief.media.room() < 1:
        raise Held("not_enough_photos_or_figures")
    rows = table["rows"]
    # Never under a table a photo that shows numbers of its own (the display of a carriage, "220 km/h · 10:22 · 21 °C",
    # read around and behind the fares on 12/11/2026).
    figures = frozenset(photo[0] for photo in brief.media.all if photo[1].get("figures"))
    # A table of journeys ("Séville → Cordoue (AVE) | 40 à 48 min") goes over a ride of its means, as a journey does:
    # its train durations went over the Mezquita (review of PR 54).
    ride = table_ride(table)
    picture = brief.media.photo(ride, table["section"], strict=bool(ride), avoid=figures) if ride else brief.media.photo(section=table["section"], avoid=figures)
    # The table is named by its section ("Le train de nuit pour Chiang Mai" above "Départ de Bangkok"), and the price
    # the guide gives for what it lists is written under it.
    price = under_table(brief, picture[1], rows)
    quotes = [{"source": "guide", "excerpt": a + " " + b} for a, b in rows] + ([{"source": "guide", "excerpt": price["shortExcerpt"]}] if price else [])
    # A heading that carries a number ("Aller simple 2026") is quoted like any figure on screen: the guard reads it in the guide.
    if re.search(r"\d", table["header"]):
        quotes.append({"source": "guide", "excerpt": table["header"]})
    kicker = table_kicker(brief, table["section"], picture[1])
    body = [plan("table", picture, kicker, table["title"], min(7.0, round(4.0 + 0.6 * len(rows), 1)),
                 detail="*" + unbreakable(price["value"]) + "* " + unbreakable(price["short"]) if price else None,
                 rows=rows, facts=quotes, tag=brief.tag, note=PAUSE_NOTE)]
    # Then its figures, chosen as in a list: the one a free photo shows first, and never a figure whose photo is taken
    # (the fare of the ferry stays in the table, over the ferry, rather than go over another village).
    # A figure that one of the table's rows already gives for the same thing has been said ("35,70 €" in Turística): it
    # gets no plan of its own. The same amount for something else ("10 €" the bus pass, "10 €" a ferry) is another figure.
    def listed(fact: dict) -> bool:
        return any(p.normalized(fact["value"]) == p.normalized(value) and words_of(fact["label"]) & words_of(label) for label, value in rows)

    chosen = [fact for fact in brief.numbered if fact is not price and not listed(fact)]
    limit, plans = min(MAX_FACTS["tableau"], brief.media.room()), {}
    for index in placed(chosen, brief.media, limit, limit):
        plans[index] = fact_plan(chosen[index], brief.media, brief.place, brief.tag)
    body += [plans[index] for index in sorted(plans)]
    # The caption is no photo: it keeps the section's name ("Alfa Pendular ou Intercidades") when the plan could not.
    told = caption_heading(brief, table["section"], kicker)
    heading = " ".join(table["title"]) if told == brief.place else told + " · " + " ".join(table["title"])
    # The caption gives the table, then the figures the reel shows after it, before any figure left unshown.
    shown = [caption_line(chosen[index]) for index in sorted(plans)]
    return brief.hook("*le tableau à garder*"), body, ([caption_line(price)] if price else []) + table_lines(heading, rows) + shown


def label_of(fmt: str, scenes: list[dict]) -> str:
    """The format in the title of the post: no "jour par jour" for an itinerary that leaves days out."""
    partial = fmt == "itineraire" and scenes[0]["headline"][-1] != EVERY_DAY
    return "les étapes clés" if partial else FORMAT_LABELS[fmt]


def said_by(hook: dict, body: list[dict], opening: str) -> set[str]:
    """The different things a reel says, the hook's own promise aside: each row of a table, and one thing per other
    plan, its figure (a stage also quotes the title of its day: that is not a second thing said)."""
    said = {fact["excerpt"] for fact in hook.get("facts", [])} - {opening}
    for scene in body:
        quotes = [fact["excerpt"] for fact in scene.get("facts", [])]
        # The heading of a table, quoted when it carries a number, names the table: it is not one more thing said.
        heading = p.normalized(" ".join(scene["headline"]))
        said |= set(quotes[-1:] if scene["layout"] != "table" else [quote for quote in quotes if p.normalized(quote) != heading])
    return said


def emblematic(photos: list) -> tuple[str, ...]:
    """The photos that can close a post, the guide's own first: those the site publishes for this place and those a
    human marked `emblematic` in reviewed.json (media_library.gather_photos). A photo added for one plan (a hut, a
    dog team) or found by the search is not one of them."""
    return tuple(photo[0] for photo in photos if photo[1].get("emblematic") is True)


def marked(scenes: list[dict], photos: list) -> None:
    """Each plan of a reel is given what its photo's record says: its caption (production.py reads it to refuse a photo
    of another place) and where its subject is. A photo reviewed by hand may say so (reviewed.json, "focus"), and may
    give another point for this narrow frame ("focusVertical": the doe of Nara, whose head a point good for a 4:5
    slide left out of the frame for half the plan)."""
    records, captions = {photo[0]: photo[1] for photo in photos}, {photo[0]: photo[2] for photo in photos if photo[2]}
    for scene in scenes:
        if scene.get("photo") in captions:
            scene["alt"] = captions[scene["photo"]]
        record = records.get(scene.get("photo"), {})
        focus = record.get("focusVertical") or record.get("focus")
        if isinstance(focus, list) and len(focus) == 2:
            scene["focus"] = focus


def build(fmt: str, article: dict, facts: list[dict], photos: list, clips: list, opening: str, place: str, kicker: str,
          tag: str, title_lines: list[str], page: str) -> tuple[list[dict], list[str]]:
    """The plans of one reel and the useful lines of its caption. Raises Held when the guide cannot fill the format."""
    # The body takes the photos that show what it names; the hook and the call keep two, the cover first.
    # The picture people see first: the guide's cover, or its first photo when the cover is too small for a reel.
    # Never a file found by the search: nobody looked at it.
    seen = [photo[0] for photo in photos if photo[1].get("automatic") is not True]
    # Never an outing in its place ("Des barques bleues… à Essaouira" opened the reels of Marrakech: review of PR 56).
    # The outings are read in the guide's sections, never in the kicker: a long kicker is cut to the place alone (Codex,
    # review of PR 57), and a guide of a region or a quarter of the town is no outing (review of PR 57).
    outings = place_names.outings(article, place_names.words(kicker))
    records = {photo[0]: photo for photo in photos}
    home = [photo_id for photo_id in seen if not place_names.on_an_outing(records[photo_id][2], str(records[photo_id][1].get("commonsTitle", "")),
                                                                          outings, place_names.words(kicker))]
    cover = article.get("cover") if article.get("cover") in seen else None
    if cover is None and seen:
        cover = (home or seen)[0]
    brief = Brief(article, facts, Media(photos, clips, reserve=2, cover=cover, emblematic=emblematic(photos), everywhere=kicker, outings=outings,
                                        reserved=cover),
                  opening, place, kicker, tag, title_lines, page)
    if fmt in ("liste", "express", "prix"):
        hook, body, lines = figures_reel(fmt, brief)
    elif fmt == "itineraire":
        hook, body, lines = itinerary_reel(brief)
    elif fmt == "tableau":
        hook, body, lines = table_reel(brief)
    else:
        raise Held("unknown_format")
    if len(said_by(hook, body, opening)) < MIN_FACTS:
        raise Held("fewer_than_four_facts")
    # The button is written in the scenario: a reel sealed before 12/11/2026 has none and keeps the card it was given.
    closing = plan("cta", brief.media.closing(), "Le guide complet", title_lines, CTA_SECONDS, note=SAVE_NOTE, button=p.MOTION_BUTTON)
    marked([hook] + body + [closing], photos)
    # Three to five useful caption lines: the figures left unshown complete a short list.
    lines += [caption_line(f) for f in facts if caption_line(f) not in lines]
    lines = [line for line in lines if checked(line, CAPTION_LINE)][:5]
    if len(lines) < 3:
        raise Held("not_enough_caption_lines")
    return [hook] + body + [closing], lines
