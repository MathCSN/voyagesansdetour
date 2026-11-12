#!/usr/bin/env python3
"""Withdraw queued posts that quote a guide which no longer says so.

A post quotes its guide word for word on the day it is made. A guide corrected afterwards (a fare read
again, a stage dropped from an itinerary) leaves the post waiting in the stock with the old figure. Each
day, before new posts are planned, every batch still to come is read again: each quote it takes from a
page of the site is looked for, word for word, on that page as it is published today.

A quote that is gone is looked for again as a passage: somewhere on the page, every number of the quote
beside at least half of the words that name something in it. Found, the guide words the same figure
otherwise ("0 $ la patinoire" became "0 $ l'entrée de la patinoire"): the quote is listed for a human
eye, and the batch stays. Not found, the guide no longer gives that figure ("977,50 pesos" once it says
1 041,50; a fare of 30 dh once the page only says "toutes les 30 minutes"): the batch is stale. What this
cannot see: a figure changed for a number that already stood in the same passage. With `--retire` a
stale batch is added to
`retirements` of reviewed-social/index.json: the panel will not send it, and auto_social.py gives its
slot and its guide to a new post (README, « Retirer un post en file »). A stale batch is only reported,
never withdrawn, when withdrawing it is not safe:
- its slot is less than BUFFER_LEAD + MARGIN away: the panel may already have handed it to Buffer, where
  it has to be deleted by hand;
- none of its quotes is left on the page: a guide rewritten from top to bottom and a broken page look the
  same from here;
- more than half of the batches read today are stale: that is a change of the site, not of one guide.
- the only numbers it lost are an order number under ten written without a unit ("7 départs" became "sept
  départs") or the pieces of a date ("12/11/2026" became "12 novembre 2026"): that is wording, to be read by
  a human eye. An ordinal ("2e classe") is never a figure.
A post is one thing: its batch and its copies on other networks are withdrawn or reported together, by
the slot that comes first. A page that cannot be read says nothing: its batches are left alone and listed
as unread. Quotes taken from another site (a carrier, a museum) are not read again here: the batches that
carry such figures are listed with the day the source was read, for the daily report.
No scenario, render or batch file is ever touched. A name read in the index must be an identifier, and
the source registry of a scenario is looked up among those of the production folder: nothing read in a
file is opened as a path.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import http.client
import json
from pathlib import Path
import re
import urllib.parse

import auto_social as a
import destinations
import production as p
import reel_formats
import social_stock

HERE = Path(__file__).resolve().parent
REASON = "figure_no_longer_in_guide"
# The panel hands a post to Buffer three days before its slot (vsd-admin); a withdrawal written today reaches the
# panel at its next hourly import, once this run is committed.
BUFFER_LEAD = dt.timedelta(hours=72)
MARGIN = dt.timedelta(hours=12)
SITE_HOST = urllib.parse.urlsplit(p.ORIGIN).hostname
QUOTE_SHOWN = 160
AROUND = 100   # characters read on each side of a figure, beyond the length of the quote itself
THOUSANDS = re.compile(r"(?<=\d) (?=\d{3}(?!\d))")
CELL = " | "                               # between two elements of a page, once folded (plain)
ROW_UNIT = 8                               # what may follow the last cell of a row in a quote: its unit, one short word
START, END = r"(?<![\d,])", r"(?!\d|,\d)"   # a number read whole: no digit or decimal comma on either side
RANK = r"(?:e(?:r|re|me)?|re|nde?)\b"      # "1er", "1ere", "1re", "2e", "2eme", "2nd", "2nde", and the "E" of "tram 15E"
# A number, never an ordinal: "2e classe", "1er dimanche" and "tram 15E" are read apart (ORDINAL).
NUMBER = re.compile(START + r"\d+(?:,\d+)?" + END + r"(?!" + RANK + r")")
ORDINAL = re.compile(START + r"\d+" + RANK)
GROUPED = re.compile(START + r"\d{1,3}(?: \d{3})+(?:,\d+)?" + END)
# How a guide may write the first ordinals in full: "2e classe" and "seconde classe" say the same.
IN_FULL = {"1": ("premier", "premiere"), "2": ("second", "seconde", "deuxieme"), "3": ("troisieme",), "4": ("quatrieme",),
           "5": ("cinquieme",), "6": ("sixieme",), "7": ("septieme",), "8": ("huitieme",), "9": ("neuvieme",), "10": ("dixieme",)}
# What makes a small number a figure: a price, a duration, a distance, a weight, a count of people, short or in full.
UNIT = re.compile(r"\s?(?:" + reel_formats.UNIT + r"|k€|(?:bahts?|pesos?|euros?|dollars?|livres?|yens?|dirhams?|EUR|MAD|THB|USD|CHF|GBP|JPY|MXN"
                  r"|heures?|minutes?|secondes?|mn|sec|kilom[eè]tres?|m[eè]tres?|kg|kilos?|semaines?|mois|ann[eé]es?|personnes?|adultes?|enfants?"
                  r"|[eé]toiles?|degr[eé]s?)\b)", re.IGNORECASE)
MONEY_BEFORE = re.compile(r"[€$£¥₫฿]\s?\Z")
DATES = (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b"),
         re.compile(rf"\b(\d{{1,2}})(?:er)? (?:{reel_formats.MONTHS})\b(?: (\d{{4}}))?", re.IGNORECASE),
         re.compile(rf"\b(?:{reel_formats.MONTHS}) (\d{{4}})\b", re.IGNORECASE))
UNREADABLE = (OSError, ValueError, LookupError, TypeError, AttributeError)
REGISTRY_FOLDERS = ("auto", "sources")   # where scenarios keep their source registries (auto_social.py, hand-written posts)


def folded(line: str) -> str:
    """Lower case, no accents, punctuation as spaces (the decimal comma stays)."""
    return " ".join(destinations.ascii_fold(re.sub(r"[^\w\s,]", " ", line)).lower().split())


def plain(text: str) -> str:
    """A page for looking numbers up, "1 041,50" in one piece. Thousands are joined first and line by line (one line
    per element of the page): "(… 2026) 500 bahts" and "7 h 15" followed by "938 bahts" in the next element are not
    numbers in the thousands. The elements stay apart (CELL): two cells of a table are told from one number."""
    lines = (folded(THOUSANDS.sub("", p.normalized(line))) for line in text.split("\n"))
    return CELL.join(line for line in lines if line)


def readings(excerpt: str) -> tuple[Counter, dict[str, tuple[str, str]]]:
    """The numbers of a quote, each with how many times it stands there, and those that may also be two cells of a
    table. Thousands are looked for in the quote as it is written: "768 / 838 ฿", "13 h 16. 265 pesos" and "bus 19
    (100 dh)" hold two numbers each. "Ligne 15 200 ¥" may be fifteen thousand two hundred, or a row whose cells "15"
    and "200" were joined in one quote: only where the quote has the shape of such a row, a label that ends on the
    number and nothing after it but its unit. "1 500 bahts la nuit en bungalow" is a price, whatever the page says."""
    quote, counts, rows = p.normalized(excerpt), Counter(), {}
    for group in GROUPED.finditer(quote):
        number, pieces = group[0].replace(" ", ""), group[0].split(" ")
        counts[number] += 1
        unit = quote[group.end():].strip()
        labelled = re.search(r"[^\W\d]\W*\Z", quote[:group.start()]) and len(unit) <= ROW_UNIT and " " not in unit
        if len(pieces) == 2 and not pieces[1].startswith("0") and labelled:
            rows[number] = (pieces[0], pieces[1])
    counts.update(NUMBER.findall(folded(GROUPED.sub(" ", quote))))
    return counts, rows


def ordinals(excerpt: str) -> list[str]:
    """The ordinals and lettered numbers of a quote, as written once folded: "1er", "2e", "15e" (tram 15E)."""
    return list(dict.fromkeys(ORDINAL.findall(folded(GROUPED.sub(" ", p.normalized(excerpt))))))


def whole(number: str) -> re.Pattern:
    """The number read whole: "30" is neither in "30 000" nor in "1,30"."""
    return re.compile(START + re.escape(number) + END + r"(?!" + RANK + r")")


def ordinal(token: str) -> re.Pattern:
    """That ordinal as the page may write it: the same rank in figures ("1er", "1re"), or in full for the first ten."""
    rank = re.match(r"\d+", token)[0]
    in_full = "|".join(IN_FULL.get(rank, ()))
    return re.compile(START + rank + RANK + (rf"|\b(?:{in_full})\b" if in_full else ""))


def in_cells(first: str, second: str) -> re.Pattern:
    """Two numbers as a row gives them: the first in one element of the page, the second opening the next one."""
    return re.compile(START + re.escape(first) + END + r"[^|]*" + re.escape(CELL) + re.escape(second) + END)


def numbers_gone(excerpt: str, page: str) -> list[str]:
    """[] when a passage of the page still gives every number of the quote, as many times as the quote does, and every
    ordinal, beside at least half of the words that name something in it. Otherwise what is missing from the closest
    passage, numbers first: all of them when no passage is close. A number in the thousands that such a passage only
    gives as two cells of a row comes back as "15|200": it may be a price that changed, it is never passed in silence.
    Limit: a figure replaced by a number the passage already gives for something else ("8 h" beside "9 h 8 min")."""
    (counts, rows), ranks, text = readings(excerpt), ordinals(excerpt), plain(page)
    if not counts and not ranks:
        return []
    words = reel_formats.words_of(excerpt)
    patterns = {**{number: whole(number) for number in counts}, **{rank: ordinal(rank) for rank in ranks}}
    cells = {number: in_cells(*pieces) for number, pieces in rows.items()}
    everything = [*counts, *ranks]

    def given(token: str, passage: str) -> bool:
        return len(patterns[token].findall(passage)) >= counts.get(token, 1)

    reach, best, doubt = len(folded(excerpt)) + AROUND, (0, 0, everything), None
    for at in sorted({match.start() for pattern in [*patterns.values(), *cells.values()] for match in pattern.finditer(text)}):
        passage = text[max(0, at - reach):at + reach]
        missing = [token for token in everything if not given(token, passage)]
        split = [token for token in missing if token in cells and cells[token].search(passage)]
        named = len(words & set(re.findall(r"[a-z0-9]{4,}", passage)))
        if len(split) == len(missing) and 2 * named >= len(words):
            if not split:
                return []
            doubt = ["|".join(rows[token]) for token in split]
        best = max(best, (len(everything) - len(missing), named, missing), key=lambda found: found[:2])
    return doubt or best[2] or everything


def only_wording(numbers: list[str], excerpt: str) -> bool:
    """What is missing is not a figure to watch: an ordinal ("1er dimanche"), the pieces of a date, or an order number
    under ten written without a unit ("7 départs par jour" may become "sept départs par jour"). Each occurrence of a
    lost number is looked at: in "2 € la traversée, 2 départs par heure" the lost "2" is a price."""
    quote = p.normalized(excerpt)
    dated = [match.span(group) for pattern in DATES for match in pattern.finditer(quote)
             for group in range(1, pattern.groups + 1) if match.group(group)]

    def soft(match: re.Match) -> bool:
        if any(start <= match.start() and match.end() <= end for start, end in dated):
            return True
        return len(match[0]) == 1 and not UNIT.match(quote, match.end()) and not MONEY_BEFORE.search(quote[:match.start()])

    for number in numbers:
        if ORDINAL.fullmatch(number) or "|" in number:   # an ordinal, or two cells that may be a thousand: to be read by eye
            continue
        found = list(whole(number).finditer(quote))
        if not found or not all(map(soft, found)):
            return False
    return True


def scenario_id(batch_id: str) -> str:
    """'ig-kyoto-2026-11-20-2-tiktok-v1' → 'ig-kyoto-2026-11-20-2': a copy on another network is the same post."""
    name = batch_id.removesuffix("-v1")
    return next((name.removesuffix("-" + channel) for channel in social_stock.CROSSPOSTS if name.endswith("-" + channel)), name)


def shelf(root: Path, folder: str) -> dict[str, Path]:
    """The JSON files of one folder of the production tree, by their name without ".json"; never a link to elsewhere."""
    return {path.stem: path for path in (root / folder).glob("*.json") if not path.is_symlink()}


def stored(files: dict[str, Path], name: str) -> dict | None:
    """The JSON file of that name on a shelf, None when there is none. The name is read in the index: it must be an
    identifier (letters, digits, dashes), and it is looked up among the files of the folder, never made into a path."""
    if not isinstance(name, str) or not p.ID.match(name):
        raise ValueError("Not an identifier: " + str(name))
    path = files.get(name)
    return json.loads(path.read_text()) if path else None


def registries(root: Path) -> dict[str, Path]:
    """The source registries of the production folder, by the relative path the scenarios give them. A scenario's
    registry is looked up in this list: a path written in a scenario is never opened as it is."""
    return {path.relative_to(root).as_posix(): path for folder in REGISTRY_FOLDERS for path in (root / folder).glob("**/sources.json")
            if not path.is_symlink()}


def quotes_of(scenario: dict, known: dict[str, Path]) -> tuple[list[tuple[str, str]], list[dict]]:
    """What the post quotes: (page, excerpt) for every quote taken from a page of the site, each once, in the order of
    the plans; and, for the figures taken from another site, that source with the day it was read."""
    registry = json.loads(known[str(scenario["sources"]["file"])].read_text())["sources"]
    facts = [fact for scene in scenario["scenes"] for fact in scene.get("facts", []) if isinstance(fact.get("excerpt"), str)]
    ours = {name for name, record in registry.items() if urllib.parse.urlsplit(str(record.get("url", ""))).hostname == SITE_HOST}
    site = list(dict.fromkeys((registry[fact["source"]]["url"], fact["excerpt"]) for fact in facts if fact.get("source") in ours))
    counted = {}
    for fact in facts:
        if fact.get("source") in registry and fact["source"] not in ours and re.search(r"\d", fact["excerpt"]):
            counted[fact["source"]] = counted.get(fact["source"], 0) + 1
    outside = [{"url": registry[name].get("url"), "retrievedAt": registry[name].get("retrievedAt"), "quotes": count} for name, count in counted.items()]
    return site, outside


def reread(quotes: list[tuple[str, str]], texts: dict[str, str]) -> dict:
    """The quotes of a post against the pages as they are today: found word for word, lost with a figure (or with an
    ordinal, or a number that only wording may explain: `wording`), or worded again with everything still there."""
    lost = [(url, excerpt) for url, excerpt in quotes if p.normalized(excerpt) not in p.normalized(texts[url])]
    missing = []
    for url, excerpt in lost:
        gone = numbers_gone(excerpt, texts[url])
        if gone:
            # A figure is what must never go out wrong: a lost quote whose numbers no passage of the page gives any more.
            missing.append({"quote": excerpt, "numbers": gone, "wording": only_wording(gone, excerpt)})
    gone_quotes = {entry["quote"] for entry in missing}
    return {"status": "stale" if missing else "current", "pages": sorted(texts), "quotes": len(quotes), "found": len(quotes) - len(lost),
            "missing": missing, "reworded": [excerpt for _, excerpt in lost if excerpt not in gone_quotes]}


class Reader:
    """Reads the batches still to come; each page of the site is fetched once."""

    def __init__(self, root: Path, now: dt.datetime, fetcher):
        self.root, self.now, self.fetcher = root, now, fetcher
        self.pages: dict[str, str | None] = {}
        self.registries = registries(root)
        self.batches, self.scenarios = shelf(root, "reviewed-social"), shelf(root, "scenarios")

    def text_of(self, url: str) -> str | None:
        if url not in self.pages:
            try:
                self.pages[url] = a.page_text(self.fetcher(url))   # one line per element of the page
            except (OSError, ValueError, http.client.HTTPException):  # unreachable, cut short, redirected or too large
                self.pages[url] = None
        return self.pages[url]

    def row(self, entry: dict) -> dict | None:
        """The batch read again, or None when it is not to come any more."""
        batch = stored(self.batches, entry["batchId"])
        item = batch["items"][0] if batch else None
        if not item or p.instant(item["dueAt"]) <= self.now:
            return None
        row = {"batchId": entry["batchId"], "dueAt": item["dueAt"], "channel": item["payload"]["channel"], "scenario": scenario_id(entry["batchId"])}
        scenario = stored(self.scenarios, row["scenario"])
        if not scenario:
            return {**row, "status": "unread", "why": "no_scenario"}
        quotes, outside = quotes_of(scenario, self.registries)
        row = {**row, "external": outside} if outside else row
        texts = {url: self.text_of(url) for url in dict.fromkeys(url for url, _ in quotes)}
        if any(text is None for text in texts.values()):
            return {**row, "status": "unread", "why": "page_unreadable", "pages": sorted(texts)}
        return {**row, **reread(quotes, texts)}


def examine(root: Path, now: dt.datetime, fetcher=a.fetch_page) -> list[dict]:
    """One row per batch still to come: how many of its quotes the site still gives, and which ones it lost."""
    index = json.loads((root / "reviewed-social" / "index.json").read_text())
    retired = {entry["batchId"] for entry in index.get("retirements", [])}
    reader, rows = Reader(root, now, fetcher), []
    for entry in index["items"]:
        if entry.get("batchId") in retired:
            continue
        try:
            row = reader.row(entry)
        except UNREADABLE:
            # One batch that cannot be read (a file missing or oddly made, a name that is not one) never keeps the
            # others from being read.
            row = {"batchId": str(entry.get("batchId")), "dueAt": None, "status": "unread", "why": "unreadable_batch"}
        if row:
            rows.append(row)
    return rows


def obstacle(batches: list[dict], now: dt.datetime, wide: bool) -> str | None:
    """Why the stale batches of one post are reported and not withdrawn; None when withdrawing them is safe."""
    if wide:
        return "more_than_half_of_the_batches_are_stale"
    if not any(row["found"] for row in batches):
        return "no_quote_left_on_the_page"
    if all(entry["wording"] for row in batches for entry in row["missing"]):
        return "only_an_order_number_or_a_date_changed"
    # The reel and its copy an hour later are one post: the slot that comes first decides for both.
    if min(p.instant(row["dueAt"]) for row in batches) - now < BUFFER_LEAD + MARGIN:
        return "may_already_be_in_buffer"
    return None


def decide(rows: list[dict], now: dt.datetime) -> list[dict]:
    """Each row with what is done about it: "none", "retire", or "report" with the reason it is not withdrawn."""
    read = [row for row in rows if row["status"] in ("current", "stale")]
    wide = 2 * sum(row["status"] == "stale" for row in read) > len(read)
    posts: dict[str, list[dict]] = {}
    for row in rows:
        if row["status"] == "stale":
            posts.setdefault(row["scenario"], []).append(row)
    why = {scenario: obstacle(batches, now, wide) for scenario, batches in posts.items()}
    decided = []
    for row in rows:
        if row["status"] != "stale":
            decided.append({**row, "action": "none"})
        elif why[row["scenario"]]:
            decided.append({**row, "action": "report", "why": why[row["scenario"]]})
        else:
            decided.append({**row, "action": "retire"})
    return decided


def evidence(row: dict, now: dt.datetime) -> str:
    short = lambda excerpt: excerpt if len(excerpt) <= QUOTE_SHOWN else excerpt[:QUOTE_SHOWN - 1] + "…"
    quoted = " ; ".join(f"« {short(entry['quote'])} » (ne se lit plus : {', '.join(entry['numbers'])})" for entry in row["missing"])
    return (f"Relecture du {now:%d/%m/%Y} : {', '.join(row['pages'])} ne donne plus {len(row['missing'])} des {row['quotes']} "
            f"citations du post, chiffre compris. {quoted}.")


def retire(root: Path, rows: list[dict], now: dt.datetime) -> list[str]:
    """Write the withdrawals decided by `decide`; returns the batches withdrawn."""
    chosen = {row["batchId"]: row for row in rows if row.get("action") == "retire"}
    if not chosen:
        return []
    path = root / "reviewed-social" / "index.json"
    index = json.loads(path.read_text())
    entries = [{"batchId": entry["batchId"], "batchSha256": entry["batchSha256"], "fileSha256": entry["fileSha256"], "itemIds": entry["itemIds"],
                "retiredAt": p.stamp(now), "reason": REASON, "evidence": evidence(chosen[entry["batchId"]], now)}
               for entry in index["items"] if entry["batchId"] in chosen]
    text = json.dumps({**index, "retirements": index.get("retirements", []) + entries}, ensure_ascii=False, indent=2) + "\n"
    with path.open("w", encoding="utf-8") as handle:   # the path is fixed; only the list of withdrawals grows
        handle.write(text)
    return [entry["batchId"] for entry in entries]


def run(root: Path = HERE, now: dt.datetime | None = None, *, fetcher=a.fetch_page, withdraw: bool = False) -> dict:
    now = (now or p.utcnow()).astimezone(dt.timezone.utc).replace(microsecond=0)
    rows = decide(examine(Path(root), now, fetcher), now)
    retired = retire(Path(root), rows, now) if withdraw else []
    reported = [row["batchId"] for row in rows if row["action"] == "report" or (row["action"] == "retire" and not withdraw)]
    return {"status": "stale" if retired or reported else "current", "checked": sum(row["status"] != "unread" for row in rows),
            "retired": retired, "reported": reported, "unread": [row["batchId"] for row in rows if row["status"] == "unread"],
            "external": [row["batchId"] for row in rows if row.get("external")], "batches": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retire", action="store_true", help="withdraw the stale batches it is safe to withdraw")
    args = parser.parse_args()
    print(json.dumps(run(withdraw=args.retire), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
