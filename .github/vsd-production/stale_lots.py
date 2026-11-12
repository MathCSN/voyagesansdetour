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
No scenario, render or batch file is ever touched; identifiers and paths read in the index must stay
inside the production folder.
"""
from __future__ import annotations

import argparse
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
# A number, never an ordinal: "2e classe", "1er dimanche" and "tram 15E" count nothing.
NUMBER = re.compile(r"(?<![\d,])\d+(?:,\d+)?(?!\d|,\d)(?!(?:er|ere|re|e|eme|nd|nde)\b)")
GROUPED = re.compile(r"(?<![\d,])\d{1,3}(?: \d{3})+(?:,\d+)?(?!\d|,\d)")
UNIT = re.compile(r"\s?(?:" + reel_formats.UNIT + r"|bahts?\b|pesos?\b|euros?\b|dollars?\b|livres?\b|yens?\b)")
DATES = (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b"),
         re.compile(rf"\b(\d{{1,2}})(?:er)? (?:{reel_formats.MONTHS})\b(?: (\d{{4}}))?", re.IGNORECASE),
         re.compile(rf"\b(?:{reel_formats.MONTHS}) (\d{{4}})\b", re.IGNORECASE))
UNREADABLE = (OSError, ValueError, LookupError, TypeError)


def folded(line: str) -> str:
    """Lower case, no accents, punctuation as spaces (the decimal comma stays)."""
    return " ".join(destinations.ascii_fold(re.sub(r"[^\w\s,]", " ", line)).lower().split())


def plain(text: str) -> str:
    """A page for looking numbers up, "1 041,50" in one piece. Thousands are joined first and line by line (one line
    per element of the page): "(… 2026) 500 bahts" and "7 h 15" followed by "938 bahts" in the next element are not
    numbers in the thousands."""
    return folded(" ".join(THOUSANDS.sub("", p.normalized(line)) for line in text.split("\n")))


def readings(excerpt: str) -> dict[str, tuple[str, ...]]:
    """Each number of a quote with the ways it may be written on the page. "15 200" is fifteen thousand two hundred, or
    two cells of a table joined in one quote ("Ligne 15" and "200 ¥"): the number in one piece, else its pieces."""
    quote, found = folded(p.normalized(excerpt)), {}
    for group in GROUPED.finditer(quote):
        pieces = group[0].split(" ")
        # "20 000" is one number: a cell of a table does not begin with a zero.
        found[group[0].replace(" ", "")] = () if any(piece.startswith("0") for piece in pieces[1:]) else tuple(pieces)
    rest = GROUPED.sub(" ", quote)
    return {**{number: () for number in NUMBER.findall(rest)}, **found}


def whole(number: str) -> re.Pattern:
    """The number read whole: "30" is neither in "30 000" nor in "1,30"."""
    return re.compile(r"(?<![\d,])" + re.escape(number) + r"(?!\d|,\d)")


def numbers_gone(excerpt: str, page: str) -> list[str]:
    """[] when a passage of the page still gives every number of the quote beside at least half of the words that
    name something in it. Otherwise the numbers missing from the closest passage: all of them when no passage is
    close."""
    numbers, text = readings(excerpt), plain(page)
    if not numbers:
        return []
    words = reel_formats.words_of(excerpt)
    patterns = {number: whole(number) for number in {*numbers, *(piece for pieces in numbers.values() for piece in pieces)}}
    reach, best = len(folded(excerpt)) + AROUND, (0, 0, list(numbers))
    for at in sorted({match.start() for pattern in patterns.values() for match in pattern.finditer(text)}):
        passage = text[max(0, at - reach):at + reach]
        given = lambda number: bool(patterns[number].search(passage))
        missing = [number for number, pieces in numbers.items() if not (given(number) or (pieces and all(map(given, pieces))))]
        named = len(words & set(re.findall(r"[a-z0-9]{4,}", passage)))
        if not missing and 2 * named >= len(words):
            return []
        best = max(best, (len(numbers) - len(missing), named, missing), key=lambda found: found[:2])
    return best[2] or list(numbers)


def only_wording(numbers: list[str], excerpt: str) -> bool:
    """These numbers are not figures to watch: pieces of a date, or an order number under ten written without a unit
    ("7 départs par jour" may become "sept départs par jour"; "2 € la traversée" may not become anything else)."""
    quote = p.normalized(excerpt)
    dated = {part.lstrip("0") for pattern in DATES for match in pattern.finditer(quote) for part in match.groups() if part}
    bare = {match[0] for match in re.finditer(r"(?<![\d,€$£¥])\b\d\b(?![\d,])", quote) if not UNIT.match(quote, match.end())}
    return all(number.lstrip("0") in dated or number in bare for number in numbers)


def scenario_id(batch_id: str) -> str:
    """'ig-kyoto-2026-11-20-2-tiktok-v1' → 'ig-kyoto-2026-11-20-2': a copy on another network is the same post."""
    name = batch_id.removesuffix("-v1")
    return next((name.removesuffix("-" + channel) for channel in social_stock.CROSSPOSTS if name.endswith("-" + channel)), name)


def inside(root: Path, relative: str) -> Path:
    """The file at this path of the production folder. A name read in the index or in a scenario never leads out."""
    base, path = root.resolve(), (root / relative).resolve()
    if not path.is_relative_to(base):
        raise ValueError("Path outside the production folder: " + relative)
    return path


def stored(root: Path, folder: str, name: str) -> dict | None:
    """The JSON file `<folder>/<name>.json`, None when there is none; the name is an identifier, nothing else."""
    if not p.ID.match(str(name)):
        raise ValueError("Not an identifier: " + str(name))
    path = inside(root, f"{folder}/{name}.json")
    return json.loads(path.read_text()) if path.is_file() else None


def quotes_of(scenario: dict, root: Path) -> tuple[list[tuple[str, str]], list[dict]]:
    """What the post quotes: (page, excerpt) for every quote taken from a page of the site, each once, in the order of
    the plans; and, for the figures taken from another site, that source with the day it was read."""
    registry = json.loads(inside(root, str(scenario["sources"]["file"])).read_text())["sources"]
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
    """The quotes of a post against the pages as they are today: found word for word, lost with a figure, or worded again."""
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

    def text_of(self, url: str) -> str | None:
        if url not in self.pages:
            try:
                self.pages[url] = a.page_text(self.fetcher(url))   # one line per element of the page
            except (OSError, ValueError, http.client.HTTPException):  # unreachable, cut short, redirected or too large
                self.pages[url] = None
        return self.pages[url]

    def row(self, entry: dict) -> dict | None:
        """The batch read again, or None when it is not to come any more."""
        batch = stored(self.root, "reviewed-social", entry["batchId"])
        item = batch["items"][0] if batch else None
        if not item or p.instant(item["dueAt"]) <= self.now:
            return None
        row = {"batchId": entry["batchId"], "dueAt": item["dueAt"], "channel": item["payload"]["channel"], "scenario": scenario_id(entry["batchId"])}
        scenario = stored(self.root, "scenarios", row["scenario"])
        if not scenario:
            return {**row, "status": "unread", "why": "no_scenario"}
        quotes, outside = quotes_of(scenario, self.root)
        row = {**row, "external": outside} if outside else row
        texts = {url: self.text_of(url) for url in dict.fromkeys(url for url, _ in quotes)}
        if any(text is None for text in texts.values()):
            return {**row, "status": "unread", "why": "page_unreadable", "pages": sorted(texts)}
        return {**row, **reread(quotes, texts)}


def examine(root: Path, now: dt.datetime, fetcher=a.fetch_page) -> list[dict]:
    """One row per batch still to come: how many of its quotes the site still gives, and which ones it lost."""
    index = json.loads(inside(root, "reviewed-social/index.json").read_text())
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
    path = inside(root, "reviewed-social/index.json")
    index = json.loads(path.read_text())
    entries = [{"batchId": entry["batchId"], "batchSha256": entry["batchSha256"], "fileSha256": entry["fileSha256"], "itemIds": entry["itemIds"],
                "retiredAt": p.stamp(now), "reason": REASON, "evidence": evidence(chosen[entry["batchId"]], now)}
               for entry in index["items"] if entry["batchId"] in chosen]
    path.write_text(json.dumps({**index, "retirements": index.get("retirements", []) + entries}, ensure_ascii=False, indent=2) + "\n")
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
