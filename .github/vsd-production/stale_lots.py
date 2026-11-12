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
A page that cannot be read says nothing: its batches are left alone and listed as unread.
No scenario, render or batch file is ever touched.
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
THOUSANDS = re.compile(r"(?<=\d) (?=\d{3}(?!\d))")
NUMBER = re.compile(r"\d+(?:,\d+)?")


AROUND = 100   # characters read on each side of a figure, beyond the length of the quote itself


def plain(text: str) -> str:
    """Lower case, no accents, punctuation as spaces (the decimal comma stays), "1 041,50" in one piece. Thousands
    are joined first and line by line (one line per element of the page): "(… 2026) 500 bahts" and "7 h 15" followed
    by "938 bahts" in the next element are not numbers in the thousands."""
    lines = [THOUSANDS.sub("", p.normalized(line)) for line in text.split("\n")]
    return " ".join(destinations.ascii_fold(re.sub(r"[^\w\s,]", " ", " ".join(lines))).lower().split())


def numbers_gone(excerpt: str, page: str) -> list[str]:
    """[] when a passage of the page still gives every number of the quote beside at least half of the words that
    name something in it. Otherwise the numbers missing from the closest passage: all of them when no passage is
    close. Numbers are read whole: "30" is neither in "30 000" nor in "1,30"."""
    quote, text = plain(excerpt), plain(page)
    numbers = list(dict.fromkeys(NUMBER.findall(quote)))
    if not numbers:
        return []
    words = reel_formats.words_of(excerpt)
    whole = {number: re.compile(r"(?<![\d,])" + re.escape(number) + r"(?!\d|,\d)") for number in numbers}
    reach, best = len(quote) + AROUND, (0, 0, numbers)
    for at in sorted({match.start() for pattern in whole.values() for match in pattern.finditer(text)}):
        passage = text[max(0, at - reach):at + reach]
        missing = [number for number in numbers if not whole[number].search(passage)]
        named = len(words & set(re.findall(r"[a-z0-9]{4,}", passage)))
        if not missing and 2 * named >= len(words):
            return []
        best = max(best, (len(numbers) - len(missing), named, missing), key=lambda found: found[:2])
    return best[2] or numbers


def scenario_id(batch_id: str) -> str:
    """'ig-kyoto-2026-11-20-2-tiktok-v1' → 'ig-kyoto-2026-11-20-2': a copy on another network is the same post."""
    name = batch_id.removesuffix("-v1")
    return next((name.removesuffix("-" + channel) for channel in social_stock.CROSSPOSTS if name.endswith("-" + channel)), name)


def site_quotes(scenario: dict, root: Path) -> list[tuple[str, str]]:
    """(page, excerpt) for every quote the post takes from a page of the site, each once, in the order of the plans."""
    registry = json.loads((root / scenario["sources"]["file"]).read_text())["sources"]
    pages = {name: record["url"] for name, record in registry.items()
             if urllib.parse.urlsplit(str(record.get("url", ""))).hostname == SITE_HOST}
    quotes = [(pages[fact["source"]], fact["excerpt"]) for scene in scenario["scenes"] for fact in scene.get("facts", [])
              if fact.get("source") in pages and isinstance(fact.get("excerpt"), str)]
    return list(dict.fromkeys(quotes))


def examine(root: Path, now: dt.datetime, fetcher=a.fetch_page) -> list[dict]:
    """One row per batch still to come: how many of its quotes the site still gives, and which ones it lost."""
    index = json.loads((root / "reviewed-social" / "index.json").read_text())
    retired = {entry["batchId"] for entry in index.get("retirements", [])}
    pages: dict[str, str | None] = {}

    def text_of(url: str) -> str | None:
        if url not in pages:
            try:
                pages[url] = a.page_text(fetcher(url))   # one line per element of the page
            except (OSError, ValueError, http.client.HTTPException):  # unreachable, cut short, redirected or too large
                pages[url] = None
        return pages[url]

    def read(entry: dict) -> dict | None:
        path = root / "reviewed-social" / Path(entry["path"]).name
        if entry["batchId"] in retired or not path.is_file():
            return None
        item = json.loads(path.read_text())["items"][0]
        if p.instant(item["dueAt"]) <= now:
            return None
        row = {"batchId": entry["batchId"], "dueAt": item["dueAt"], "channel": item["payload"]["channel"], "scenario": scenario_id(entry["batchId"])}
        source = root / "scenarios" / (row["scenario"] + ".json")
        if not source.is_file():
            return {**row, "status": "unread", "why": "no_scenario"}
        quotes = site_quotes(json.loads(source.read_text()), root)
        texts = {url: text_of(url) for url in dict.fromkeys(url for url, _ in quotes)}
        if any(text is None for text in texts.values()):
            return {**row, "status": "unread", "why": "page_unreadable", "pages": sorted(texts)}
        lost = [(url, excerpt) for url, excerpt in quotes if p.normalized(excerpt) not in p.normalized(texts[url])]
        # A figure is what must never go out wrong: a lost quote whose numbers no passage of the page gives any more.
        missing = [{"quote": excerpt, "numbers": gone} for url, excerpt in lost if (gone := numbers_gone(excerpt, texts[url]))]
        gone_quotes = {entry["quote"] for entry in missing}
        return {**row, "status": "stale" if missing else "current", "pages": sorted(texts), "quotes": len(quotes),
                "found": len(quotes) - len(lost), "missing": missing, "reworded": [excerpt for _, excerpt in lost if excerpt not in gone_quotes]}

    rows = []
    for entry in index["items"]:
        try:
            row = read(entry)
        except (OSError, ValueError, LookupError, TypeError):
            # One batch that cannot be read (a file missing or oddly made) never keeps the others from being read.
            row = {"batchId": entry.get("batchId"), "dueAt": None, "status": "unread", "why": "unreadable_batch"}
        if row:
            rows.append(row)
    return rows


def decide(rows: list[dict], now: dt.datetime) -> list[dict]:
    """Each row with what is done about it: "none", "retire", or "report" with the reason it is not withdrawn."""
    read = [row for row in rows if row["status"] in ("current", "stale")]
    wide = 2 * sum(row["status"] == "stale" for row in read) > len(read)
    decided = []
    for row in rows:
        if row["status"] != "stale":
            decided.append({**row, "action": "none"})
        elif wide:
            decided.append({**row, "action": "report", "why": "more_than_half_of_the_batches_are_stale"})
        elif not row["found"]:
            decided.append({**row, "action": "report", "why": "no_quote_left_on_the_page"})
        elif p.instant(row["dueAt"]) - now < BUFFER_LEAD + MARGIN:
            decided.append({**row, "action": "report", "why": "may_already_be_in_buffer"})
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
    path.write_text(json.dumps({**index, "retirements": index.get("retirements", []) + entries}, ensure_ascii=False, indent=2) + "\n")
    return [entry["batchId"] for entry in entries]


def run(root: Path = HERE, now: dt.datetime | None = None, *, fetcher=a.fetch_page, withdraw: bool = False) -> dict:
    now = (now or p.utcnow()).astimezone(dt.timezone.utc).replace(microsecond=0)
    rows = decide(examine(Path(root), now, fetcher), now)
    retired = retire(Path(root), rows, now) if withdraw else []
    reported = [row["batchId"] for row in rows if row["action"] == "report" or (row["action"] == "retire" and not withdraw)]
    return {"status": "stale" if retired or reported else "current", "checked": sum(row["status"] != "unread" for row in rows),
            "retired": retired, "reported": reported, "unread": [row["batchId"] for row in rows if row["status"] == "unread"], "batches": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retire", action="store_true", help="withdraw the stale batches it is safe to withdraw")
    args = parser.parse_args()
    print(json.dumps(run(withdraw=args.retire), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
