#!/usr/bin/env python3
"""Real, freely licensed video plans of a place, for reels. Never an AI-generated video.

Two sources, both checked the same way (licence, author, source page, no AI mark):
- Wikimedia Commons (no key): CC BY, CC BY-SA, CC0 or public-domain files whose title names the place;
- Pexels (free API key in PEXELS_API_KEY, optional): portrait stock clips whose page address names
  the place. Pexels forbids generative-AI uploads in its terms; its licence allows commercial use
  and modification without attribution, the author is credited anyway.
Pixabay is not used: its API does not say which videos are AI-generated.

Only a few seconds are fetched, from the middle of the file, and stored as a silent
1080 x 1920, 30 fps H.264 clip with its fingerprint.
Usage: python3 clip_intake.py <place> [--provider commons|pexels]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request

import destinations
import photo_intake

HERE = Path(__file__).resolve().parent
CLIPS = "assets/clips/auto"
PEXELS_API = "https://api.pexels.com/v1/videos/search"
PEXELS_LICENCE = "Pexels License"
LICENCES = {**photo_intake.LICENCES, PEXELS_LICENCE: "https://www.pexels.com/license/"}
SOURCE_HOSTS = {"commons": "commons.wikimedia.org", "pexels": "www.pexels.com"}
# The only servers a clip is ever fetched from, over HTTPS only.
STREAM_HOSTS = {"commons": ("upload.wikimedia.org",), "pexels": ("videos.pexels.com",)}
CLIP_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,63}\Z")
CLIP_SECONDS = 4.0
MIN_DURATION, MAX_DURATION = 8.0, 900.0
MIN_HEIGHT = 1440            # a 9:16 crop of a smaller landscape frame would be enlarged too much
MIN_PORTRAIT_WIDTH = 1080
MAX_CLIP_BYTES = 6_000_000
# A talk, a report or a screen recording is not a view of the place.
NOT_A_VIEW = re.compile(r"\b(speech|interview|lecture|conference|news|press|talk|tutorial|animation|simulation|logo|"
                        r"discours|conf[ée]rence|entretien|reportage|tower of hanoi)\b", re.IGNORECASE)
Refused = photo_intake.Refused


def folded(value: str) -> str:
    return destinations.ascii_fold(value).lower()


def names_place(text: str, place: str) -> bool:
    """The place as whole words in a title or a page address ('ha-long-bay' names 'Ha Long')."""
    words = re.sub(r"[^a-z0-9]+", " ", folded(urllib.parse.unquote(text)))
    return bool(place.strip()) and f" {re.sub(r'[^a-z0-9]+', ' ', folded(place)).strip()} " in f" {words} "


def safe_stream(url: str, provider: str) -> str:
    parsed = urllib.parse.urlsplit(str(url))
    if parsed.scheme != "https" or parsed.hostname not in STREAM_HOSTS[provider] or parsed.username or parsed.port:
        raise Refused("Clip stream outside the accepted servers")
    return str(url)


def segment_start(duration: float) -> float:
    """A few seconds from the middle: openings carry titles, endings carry credits."""
    return round(max(0.0, min(duration - CLIP_SECONDS - 0.5, duration * 0.4)), 1)


# --- Wikimedia Commons ----------------------------------------------------

def commons_search(place: str, limit: int = 20) -> list[str]:
    return photo_intake.commons_search(f'filetype:video intitle:"{place}"', limit)


def commons_video(title: str) -> dict:
    data = photo_intake.fetch_json({"action": "query", "titles": title, "prop": "videoinfo",
                                    "viprop": "url|size|mime|derivatives|extmetadata|sha1|user"})
    pages = list(data.get("query", {}).get("pages", {}).values())
    if len(pages) != 1 or "videoinfo" not in pages[0]:
        raise Refused("Commons video not found: " + title)
    return pages[0]["videoinfo"][0]


def commons_candidate(title: str, place: str, info: dict) -> dict:
    """A Commons video accepted as a view of the place, with the stream to cut from."""
    meta = info.get("extmetadata", {})
    if not names_place(title, place) or NOT_A_VIEW.search(title):
        raise Refused("Title does not name the place or is not a view: " + title)
    if photo_intake.ai_generated(title, meta):
        raise Refused("AI-generated or not clearly filmed: " + title)
    licence, licence_url = photo_intake.licence_record(meta)
    duration, width, height = float(info.get("duration") or 0), int(info.get("width") or 0), int(info.get("height") or 0)
    if not MIN_DURATION <= duration <= MAX_DURATION:
        raise Refused("Video too short or too long: " + title)
    if not (height >= MIN_HEIGHT or (height > width and width >= MIN_PORTRAIT_WIDTH)):
        raise Refused("Video too small for a vertical frame: " + title)
    # The smallest transcode that still fills the frame; the original file otherwise.
    streams = [d for d in info.get("derivatives", []) if "webm" in d.get("type", "") and int(d.get("height") or 0) >= MIN_HEIGHT]
    stream = safe_stream(min(streams, key=lambda d: int(d["height"]))["src"] if streams else info["url"], "commons")
    return {"provider": "commons", "title": title, "stream": stream, "duration": duration, "sourcePage": info["descriptionurl"],
            "author": photo_intake.credited_author(meta, info.get("user"))[:200], "licence": licence, "licenceUrl": licence_url,
            "categories": photo_intake.plain_text(meta.get("Categories", {}).get("value", ""))[:1000], "sourceSha1": info.get("sha1")}


def commons_candidates(place: str, searcher=commons_search, inspector=commons_video) -> list[dict]:
    found = []
    for title in searcher(place):
        try:
            found.append(commons_candidate(title, place, inspector(title)))
        except (Refused, OSError, ValueError, KeyError):
            continue
    return found


# --- Pexels ---------------------------------------------------------------

def pexels_search(place: str, key: str) -> list[dict]:
    query = urllib.parse.urlencode({"query": place, "orientation": "portrait", "size": "medium", "per_page": 20})
    request = urllib.request.Request(PEXELS_API + "?" + query, headers={"Authorization": key, **photo_intake.USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response).get("videos", [])


def pexels_candidate(video: dict, place: str) -> dict:
    page = str(video.get("url", ""))
    parsed = urllib.parse.urlsplit(page)
    if parsed.scheme != "https" or parsed.hostname != SOURCE_HOSTS["pexels"] or not names_place(parsed.path, place):
        raise Refused("Pexels page does not name the place")
    author = str((video.get("user") or {}).get("name", "")).strip()
    described = " ".join([page, author] + [str(tag) for tag in video.get("tags") or []])
    if photo_intake.AI_MARKERS.search(described.replace("-", " ")) or NOT_A_VIEW.search(parsed.path.replace("-", " ")):
        raise Refused("AI-generated or not a view of the place")
    duration = float(video.get("duration") or 0)
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4" and int(f.get("height") or 0) > int(f.get("width") or 0)
             and int(f.get("width") or 0) >= MIN_PORTRAIT_WIDTH and urllib.parse.urlsplit(str(f.get("link", ""))).hostname in STREAM_HOSTS["pexels"]]
    if not author or not files or not MIN_DURATION <= duration <= MAX_DURATION:
        raise Refused("Pexels clip unusable")
    return {"provider": "pexels", "title": parsed.path.strip("/").split("/")[-1], "stream": safe_stream(min(files, key=lambda f: int(f["width"]))["link"], "pexels"),
            "duration": duration, "sourcePage": page, "author": author[:200], "licence": PEXELS_LICENCE, "licenceUrl": LICENCES[PEXELS_LICENCE]}


def pexels_candidates(place: str, key: str | None, searcher=pexels_search) -> list[dict]:
    if not key:
        return []
    found = []
    for video in searcher(place, key):
        try:
            found.append(pexels_candidate(video, place))
        except (Refused, ValueError, TypeError):
            continue
    return found


# --- download --------------------------------------------------------------

def cut(stream: str, start: float, target: Path) -> None:
    """Fetch CLIP_SECONDS from `start` and store them silent, cropped to 9:16, 1080 x 1920 at 30 fps."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-protocol_whitelist", "https,tls,tcp",
               "-user_agent", photo_intake.USER_AGENT["User-Agent"],
               "-ss", str(start), "-t", str(CLIP_SECONDS), "-i", stream, "-an",
               "-vf", "crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920,fps=30,format=yuv420p",
               "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-maxrate", "8M", "-bufsize", "16M",
               "-movflags", "+faststart", "-map_metadata", "-1", str(target)]
    subprocess.run(command, check=True, timeout=300, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def clip_record(clip_id: str, candidate: dict, now: dt.datetime, root: Path = HERE, cutter=cut) -> dict:
    """Download one candidate into assets/clips/auto and return its catalogue record."""
    if not CLIP_ID.fullmatch(clip_id):
        raise Refused("Invalid clip id: " + clip_id)
    folder = Path(root) / CLIPS
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (clip_id + ".mp4")
    if path.exists():
        raise Refused("Clip file already present: " + clip_id)   # nothing already written is overwritten
    start = segment_start(candidate["duration"])
    try:
        cutter(candidate["stream"], start, path)
    except (subprocess.SubprocessError, OSError) as error:
        path.unlink(missing_ok=True)
        raise Refused("Clip cannot be fetched: " + candidate["title"]) from error
    if not path.is_file() or not 20_000 <= path.stat().st_size <= MAX_CLIP_BYTES:
        path.unlink(missing_ok=True)
        raise Refused("Clip empty or too heavy: " + candidate["title"])
    record = {key: candidate[key] for key in ("provider", "title", "sourcePage", "author", "licence", "licenceUrl")}
    for key in ("categories", "sourceSha1"):
        if candidate.get(key):
            record[key] = candidate[key]
    return {"file": f"{CLIPS}/{path.name}", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **record,
            "start": start, "seconds": CLIP_SECONDS, "retrievedAt": now.isoformat().replace("+00:00", "Z"),
            "modifications": "Extrait de quelques secondes, recadré en vertical, son retiré, texte ajouté."}


def clip_id_for(place: str, candidate: dict) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", folded(place)).strip("-")[:36] or "clip"
    return f"{stem}-{candidate['provider'][:1]}{hashlib.sha1(candidate['sourcePage'].encode()).hexdigest()[:8]}"


def find(place: str, providers: tuple[str, ...], pexels_key: str | None = None) -> list[dict]:
    """Candidates for a place, Pexels first: a stock clip is a single clean plan, a Commons file may be a whole film."""
    found = []
    if "pexels" in providers:
        try:
            found += pexels_candidates(place, pexels_key)
        except (OSError, ValueError):
            pass
    if "commons" in providers:
        try:
            found += commons_candidates(place)
        except (OSError, ValueError):
            pass
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("place")
    parser.add_argument("--provider", action="append", choices=sorted(SOURCE_HOSTS))
    args = parser.parse_args()
    providers = tuple(args.provider or SOURCE_HOSTS)
    for candidate in find(args.place, providers, os.environ.get("PEXELS_API_KEY")):
        print(json.dumps({key: candidate[key] for key in ("provider", "title", "licence", "author", "duration", "sourcePage")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
