#!/usr/bin/env python3
"""Offline, bounded production of photo reels and carousels. No publication.

Each scene shows a real, freely licensed photo of the place, one concrete and
dated fact, and readable text. Every fact must be quoted word for word from a
dated snapshot of an official page or of a published guide. The runner selects
at most one due scenario, verifies sources/rights/fingerprints, renders and
keeps a receipt for idempotent retries. It never researches facts or publishes.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from PIL import __version__ as pillow_version

import social_render as draw
from photo_intake import LICENCES

HERE = Path(__file__).resolve().parent
W, H = draw.REEL_SIZE
FPS = draw.FPS
SCHEMA = 2
RENDERER_CONTRACT = 3
SUPPORTED_RECEIPT_CONTRACTS = (3,)
ORIGIN = "https://voyagesansdetour.fr"
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,95}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")
HARD_STOP = dt.datetime(2027, 9, 14, 21, 59, 59, tzinfo=dt.timezone.utc)
SOURCE_VALIDITY = dt.timedelta(days=30)
REVIEW_WINDOW = dt.timedelta(days=31)
SCENE_COUNT = {"reel": (5, 8), "carousel": (5, 8)}
REEL_SECONDS = (15, 45)
SCENE_SECONDS = (2.5, 6)
CAPTION_LINES = (3, 5)
INSTAGRAM_CAPTION_MAX = 2200
MUSIC_FADE_OUT = 1.5
REEL_BUTTON = {"instagram": "Le guide complet → lien en bio", "facebook": "Le guide complet → voyagesansdetour.fr"}
# The charter forbids the defensive boilerplate that emptied the old posts.
FORBIDDEN = ("sans récit", "voix de synthèse", "aucune approbation", "si possible",
             "ne suffit pas", "consultez les horaires et alertes", "aucun personnage virtuel")
# Lisbon lifts and funiculars closed since the Glória accident (September 2025);
# Carris lists Santa Justa as "Encerrado temporariamente" on 24/10/2026. Lift this when they reopen.
CLOSED_SERVICES = re.compile(r"\b(santa justa|gl[oó]ria|bica|lavra)\b", re.IGNORECASE)


class Invalid(ValueError):
    pass


def ensure(condition, message):
    if not condition:
        raise Invalid(message)


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def stamp(value):
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def instant(value):
    ensure(isinstance(value, str), "Timestamp must be a string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Invalid("Invalid timestamp") from error
    ensure(parsed.tzinfo is not None, "Timezone required")
    return parsed.astimezone(dt.timezone.utc)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def normalized(value):
    return " ".join(value.split())


def safe_path(root, relative):
    ensure(isinstance(relative, str) and "\\" not in relative, "Relative POSIX file path required")
    name = PurePosixPath(relative)
    ensure(not name.is_absolute() and name.parts and all(p not in (".", "..") for p in name.parts), "Unsafe file path")
    ensure(str(name) == relative, "Noncanonical file path")
    root = Path(root)
    ensure(not root.is_symlink(), "Root symlink forbidden")
    for part in (name, *name.parents):
        ensure(not (root / part).is_symlink(), "Symlink forbidden")
    path = root / name
    ensure(path.is_file(), "Required file missing: " + relative)
    return path


def verified_file(root, entry):
    ensure(isinstance(entry, dict) and HASH.fullmatch(entry.get("sha256", "")), "Missing file fingerprint")
    path = safe_path(root, entry.get("file"))
    ensure(digest(path.read_bytes()) == entry["sha256"], "File fingerprint changed: " + entry["file"])
    return path


def load_json(path):
    ensure(path.stat().st_size <= 512 * 1024, "JSON input too large")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            ensure(key not in result, "Duplicate JSON field")
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique_pairs)


def text(value, maximum=220):
    ensure(isinstance(value, str) and 0 < len(value.strip()) <= maximum and value == value.strip(),
           f"Invalid or too long text (max {maximum}): {str(value)[:90]!r}")
    ensure(not any(ord(c) < 32 or ord(c) == 127 for c in value), "Control character in text")
    ensure(not any(phrase in value.lower() for phrase in FORBIDDEN), "Boilerplate forbidden by the charter: " + value)
    ensure(not CLOSED_SERVICES.search(value), "Closed service (Lisbon lifts and funiculars): " + value)
    return value


def https(value):
    parsed = urlsplit(text(value, 1000))
    ensure(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.port, "HTTPS public URL required")
    return parsed


def credits_url(scenario):
    return f"{ORIGIN}/social-media/production/{scenario['id']}/credits.txt"


def check_review(scenario, now):
    review = scenario.get("review", {})
    ensure(review.get("status") == "reviewed_for_render", "Unreviewed scenario")
    checked, expiry = instant(review.get("checkedAt")), instant(review.get("validUntil"))
    ensure(checked <= now < expiry <= HARD_STOP, "Review outside its validity window")
    ensure(expiry - checked <= REVIEW_WINDOW, "Review window exceeds one month")
    publish = instant(scenario.get("publishAt"))
    ensure(checked < publish < expiry, "Publication slot outside the review window")
    return checked, expiry


def load_sources(scenario, root, checked, expiry):
    registry = load_json(verified_file(root, scenario.get("sources", {})))
    ensure(registry.get("schemaVersion") == 1 and isinstance(registry.get("sources"), dict), "Invalid source registry")
    snapshots = {}
    for source_id, record in registry["sources"].items():
        retrieved = instant(record.get("retrievedAt"))
        ensure(retrieved <= checked, "Source snapshot postdates the review: " + source_id)
        ensure(expiry <= retrieved + SOURCE_VALIDITY, "Review outlives its source snapshot: " + source_id)
        https(record.get("url"))
        snapshot = verified_file(root, record.get("snapshot", {})).read_text()
        ensure(snapshot.split("\n", 1)[0].strip() == record["url"], "Snapshot does not belong to its URL: " + source_id)
        snapshots[source_id] = (record, normalized(snapshot))
    return snapshots


def load_photos(scenario, root):
    catalogue = load_json(verified_file(root, scenario.get("photos", {})))
    ensure(catalogue.get("schemaVersion") == 1 and isinstance(catalogue.get("photos"), dict), "Invalid photo catalogue")
    return catalogue["photos"]


def check_photo(photos, photo_id, root):
    record = photos.get(photo_id)
    ensure(isinstance(record, dict), "Unknown photo: " + str(photo_id))
    ensure(record.get("licence") in LICENCES and record.get("licenceUrl") == LICENCES[record["licence"]], "Photo licence not accepted: " + photo_id)
    ensure(text(record.get("author"), 200) and https(record.get("sourcePage")).hostname == "commons.wikimedia.org", "Photo attribution missing: " + photo_id)
    verified_file(root, record)
    return record


def check_scene(scene, kind, snapshots, last):
    ensure(isinstance(scene.get("headline"), list) and 1 <= len(scene["headline"]) <= 3, "Headline requires one to three lines")
    for line in scene["headline"]:
        text(line, 34)
        ensure(line.count("*") % 2 == 0, "Unbalanced highlight markers")
    text(scene.get("kicker"), 32)
    if scene.get("detail") is not None:
        text(scene["detail"], 120)
    focus = scene.get("focus", [0.5, 0.5])
    ensure(isinstance(focus, list) and len(focus) == 2 and all(type(v) in (int, float) and 0 <= v <= 1 for v in focus), "Invalid photo focus")
    if kind == "reel":
        seconds = scene.get("seconds")
        ensure(type(seconds) in (int, float) and SCENE_SECONDS[0] <= seconds <= SCENE_SECONDS[1], "Scene duration invalid")
        ensure(abs(seconds * FPS - round(seconds * FPS)) < 1e-6, "Scene duration must use whole frames")
    else:
        text(scene.get("alt"), 300)
    ensure(bool(scene.get("cta")) == last, "Only the last scene is the call to action")
    facts = scene.get("facts", [])
    ensure(isinstance(facts, list) and (facts or last), "Each scene needs at least one sourced fact")
    if facts:
        text(scene.get("tag"), 52)
    used = set()
    for fact in facts:
        ensure(fact.get("source") in snapshots, "Unknown fact source: " + str(fact.get("source")))
        excerpt = normalized(text(fact.get("excerpt"), 400))
        ensure(excerpt in snapshots[fact["source"]][1], "Fact excerpt is not in its dated snapshot: " + excerpt)
        used.add(fact["source"])
    return used


def check_caption(scenario):
    caption = scenario.get("caption", {})
    text(caption.get("hook"), 150)
    lines = caption.get("lines")
    ensure(isinstance(lines, list) and CAPTION_LINES[0] <= len(lines) <= CAPTION_LINES[1], "Caption needs three to five useful lines")
    for line in lines:
        text(line, 160)
    cta = text(caption.get("cta"), 160)
    if scenario["channel"] == "instagram":
        ensure("bio" in cta.lower(), "Instagram call to action must point to the link in bio")
    tags = caption.get("hashtags")
    ensure(isinstance(tags, list) and 2 <= len(tags) <= 5 and all(re.fullmatch(r"#[A-Za-z0-9À-ÿ]+", tag) for tag in tags), "Invalid hashtags")


def check_assets(scenario, root):
    assets = scenario.get("assets", {})
    for name in ("regular", "bold", "serif"):
        asset = assets.get(name, {})
        verified_file(root, asset)
        ensure(asset.get("license") == "OFL-1.1", "Unexpected font licence")
        verified_file(root, asset.get("licenseFile", {}))
    if scenario["kind"] != "reel":
        ensure("music" not in assets, "Carousel contains unused audio")
        return
    music = assets.get("music", {})
    verified_file(root, music)
    ensure(music.get("license") == "CC-BY-4.0" and music.get("commercialUseAllowed") is True, "Music rights unqualified")
    ensure(music.get("licenseUrl") == "https://creativecommons.org/licenses/by/4.0/", "Music licence URL changed")
    provenance = load_json(verified_file(root, music.get("provenance", {})))
    ensure(provenance.get("commercialUseAllowed") is True and provenance.get("license") == "CC BY 4.0" and provenance["download"]["sha256"] == music["sha256"], "Music provenance mismatch")
    ensure(music.get("title") == provenance.get("title") and music.get("author") == provenance.get("composer") and music.get("sourceUrl") == provenance.get("sourceTrackPage"), "Music attribution mismatch")
    start = scenario.get("musicStart", 0)
    ensure(type(start) in (int, float) and 0 <= start <= 60, "Invalid music start")


def validate_scenario(scenario, root, now):
    ensure(scenario.get("schemaVersion") == SCHEMA and ID.fullmatch(scenario.get("id", "")), "Invalid scenario identity: only the photo format (schema 2) is produced")
    ensure(scenario.get("kind") in SCENE_COUNT, "Unsupported kind: photo reel or carousel only")
    ensure(scenario.get("channel") in ("instagram", "facebook"), "Unsupported channel")
    ensure(scenario.get("voice") is None and scenario.get("presenter") is None, "No synthetic voice or virtual presenter")
    text(scenario.get("title"), 150); text(scenario.get("destination"), 22)
    target = https(scenario.get("targetUrl"))
    ensure(target.hostname == "voyagesansdetour.fr" and re.fullmatch(r"/[a-z]+(?:-[a-z]+)*/[a-z0-9-]+/", target.path) and not target.query and not target.fragment, "Unexpected target")
    checked, expiry = check_review(scenario, now)
    snapshots = load_sources(scenario, root, checked, expiry)
    photos = load_photos(scenario, root)
    check_caption(scenario)
    check_assets(scenario, root)
    scenes = scenario.get("scenes")
    low, high = SCENE_COUNT[scenario["kind"]]
    ensure(isinstance(scenes, list) and low <= len(scenes) <= high, f"Require {low} to {high} scenes")
    photo_ids = [scene.get("photo") for scene in scenes]
    ensure(len(set(photo_ids)) == len(photo_ids), "A photo cannot be repeated inside one post")
    headlines = [normalized(draw.plain(" ".join(scene.get("headline") or []))).lower() for scene in scenes]
    ensure(len(set(headlines)) == len(headlines), "A headline cannot be repeated inside one post")
    used, records = set(), {}
    for index, scene in enumerate(scenes):
        used |= check_scene(scene, scenario["kind"], snapshots, index == len(scenes) - 1)
        records[scene["photo"]] = check_photo(photos, scene["photo"], root)
    ensure(used, "No sourced fact in this post")
    duration = sum(scene.get("seconds", 0) for scene in scenes)
    if scenario["kind"] == "reel":
        ensure(REEL_SECONDS[0] <= duration <= REEL_SECONDS[1], "Render duration out of bounds")
    sources = {source_id: snapshots[source_id][0] for source_id in sorted(used)}
    checked_on = min(instant(record["retrievedAt"]) for record in sources.values()).date()
    return {"duration": duration, "sources": sources, "photos": records, "sourceCheckedOn": str(checked_on)}


def fingerprint(scenario, contract_version=RENDERER_CONTRACT):
    # A new intended visual version needs a new ID; receipts keep their contract.
    ensure(contract_version in SUPPORTED_RECEIPT_CONTRACTS, "Unsupported historical renderer contract")
    return digest(canonical({"scenario": scenario, "rendererContractVersion": contract_version}))


def caption(scenario, info):
    block = scenario["caption"]
    cta = block["cta"] + ("\n" + scenario["targetUrl"] if scenario["channel"] == "facebook" else "")
    credit = "Photos libres (Wikimedia Commons)"
    if scenario["kind"] == "reel":
        credit += " et musique de Kevin MacLeod (CC BY 4.0)"
    value = "\n\n".join([block["hook"], "\n".join(block["lines"]), cta,
                         credit + " — crédits : " + credits_url(scenario), " ".join(block["hashtags"])]) + "\n"
    ensure(len(value) <= INSTAGRAM_CAPTION_MAX, "Instagram caption exceeds 2200 characters")
    return value


def credits_text(scenario, info):
    lines = [f"Voyage Sans Détour — {scenario['title']}", f"Guide : {scenario['targetUrl']}", "", "PHOTOS"]
    share_alike = False
    for n, scene in enumerate(scenario["scenes"], 1):
        photo = info["photos"][scene["photo"]]
        share_alike |= "SA" in photo["licence"]
        lines.append(f"{n}. {photo['author']} — « {photo['commonsTitle'].removeprefix('File:')} », Wikimedia Commons, {photo['sourcePage']}")
        lines.append(f"   Licence {photo['licence']} : {photo['licenceUrl']}. Modifications : recadrage, "
                     + ("mouvement lent, " if scenario["kind"] == "reel" else "") + "dégradé et texte ajoutés.")
    if share_alike:
        lines += ["", "Les visuels créés à partir de photos sous licence CC BY-SA sont diffusés sous la même licence (CC BY-SA 4.0 : https://creativecommons.org/licenses/by-sa/4.0/)."]
    if scenario["kind"] == "reel":
        music = scenario["assets"]["music"]
        lines += ["", "MUSIQUE", f"« {music['title']} » — {music['author']} (incompetech.com), {music['sourceUrl']}",
                  f"Licence CC BY 4.0 : {music['licenseUrl']}. Modifications : extrait, fondus, niveau ajusté. Aucune voix."]
    lines += ["", "POLICES", "DM Sans et Playfair Display — SIL Open Font License 1.1 (notices jointes).", "",
              f"SOURCES (relevées le {info['sourceCheckedOn']})"]
    for record in info["sources"].values():
        lines.append(f"- {record['publisher']} — {record['title']} : {record['url']} (relevé le {record['retrievedAt'][:10]})")
    lines += ["", "Montage : Voyage Sans Détour, préparé avec l’aide d’outils d’IA ; faits relevés sur les pages officielles citées."]
    return "\n".join(lines) + "\n"


def probe(video):
    return json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]))


def verify_video(video, duration, audio):
    result = probe(video)
    streams = result["streams"]
    videos = [s for s in streams if s["codec_type"] == "video"]
    audios = [s for s in streams if s["codec_type"] == "audio"]
    ensure(len(videos) == 1 and (videos[0]["width"], videos[0]["height"], videos[0]["codec_name"], videos[0]["pix_fmt"]) == (W, H, "h264", "yuv420p"), "Video specifications differ")
    ensure(videos[0]["r_frame_rate"] == f"{FPS}/1", "Frame rate differs")
    ensure(abs(float(result["format"]["duration"]) - duration) <= 0.1, "Duration differs")
    ensure(len(audios) == int(audio), "Audio stream count differs")
    if audio:
        ensure(audios[0]["codec_name"] == "aac" and audios[0]["sample_rate"] == "48000", "Audio specifications differ")
        ensure(0 < int(audios[0].get("bit_rate", 0)) < 128000, "Instagram audio must remain below 128 kb/s")
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    loudness = None
    if audio:
        measurement = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-af", "ebur128=peak=true", "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True).stderr
        summary = measurement.rsplit("Summary:", 1)[-1]
        integrated = re.search(r"I:\s*(-?[\d.]+) LUFS", summary)
        peak = re.search(r"Peak:\s*(-?[\d.]+) dBFS", summary)
        ensure(integrated and peak, "Loudness measurement unavailable")
        loudness = {"integratedLufs": float(integrated[1]), "truePeakDbfs": float(peak[1])}
        ensure(-22 <= loudness["integratedLufs"] <= -13 and loudness["truePeakDbfs"] <= -1, "Music level outside delivery range")
    return {"width": W, "height": H, "fps": FPS, "durationSeconds": float(result["format"]["duration"]), "videoCodec": "h264", "pixelFormat": "yuv420p", "videoBitrateBps": int(videos[0].get("bit_rate", 0)), "audioCodec": "aac" if audio else None, "audioSampleRate": 48000 if audio else None, "audioBitrateBps": int(audios[0]["bit_rate"]) if audio else None, "fullDecodePassed": True, "loudness": loudness}


def verify_receipt(folder, expected_fingerprint):
    receipt = load_json(safe_path(folder, "receipt.json"))
    ensure(receipt.get("fingerprint") == expected_fingerprint and receipt.get("status") == "rendered_not_published", "Existing identity has different inputs or incomplete receipt")
    ensure(isinstance(receipt.get("files"), list) and receipt["files"], "Empty receipt inventory")
    for entry in receipt["files"]:
        verified_file(folder, entry)
    return receipt


def fonts_of(scenario, root):
    return draw.Fonts(*(str(root / scenario["assets"][name]["file"]) for name in ("regular", "bold", "serif")))


def prepared_scenes(scenario, root, info, size, carousel):
    paths = [str(root / info["photos"][scene["photo"]]["file"]) for scene in scenario["scenes"]]
    try:
        return draw.prepare(scenario["scenes"], paths, fonts_of(scenario, root), size, carousel, REEL_BUTTON[scenario["channel"]])
    except draw.LayoutError as error:
        raise Invalid("Layout overflow: " + str(error)) from error


def encode_reel(scenario, root, destination, info, prepared):
    video = destination / "reel.mp4"
    duration = info["duration"]
    start = scenario.get("musicStart", 0)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "rawvideo", "-pixel_format", "rgb24",
               "-video_size", f"{W}x{H}", "-framerate", str(FPS), "-i", "pipe:0",
               "-ss", str(start), "-i", str(root / scenario["assets"]["music"]["file"]), "-map", "0:v:0", "-map", "1:a:0",
               "-af", f"atrim=0:{duration},asetpts=PTS-STARTPTS,afade=t=in:d=0.3,afade=t=out:st={duration - MUSIC_FADE_OUT}:d={MUSIC_FADE_OUT},loudnorm=I=-16:TP=-1.5:LRA=9",
               "-c:a", "aac", "-b:a", "96k", "-ar", "48000",
               "-t", str(duration), "-c:v", "libx264", "-threads", "2", "-preset", "medium", "-crf", "23",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-map_metadata", "-1", str(video)]
    with (destination / "encode.log").open("wb") as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            for frame in draw.reel_frames(prepared):
                process.stdin.write(frame.tobytes())
            process.stdin.close()
            ensure(process.wait(timeout=300) == 0, "Encoding failed; inspect encode.log")
        except BaseException:
            if process.poll() is None:
                process.kill(); process.wait()
            raise
    return verify_video(video, duration, True)


def render(scenario, root, destination, now, info):
    started = time.monotonic()
    carousel = scenario["kind"] == "carousel"
    spec = None
    if carousel:
        prepared = prepared_scenes(scenario, root, info, draw.SLIDE_SIZE, True)
        images = [draw.slide(scene, i) for i, scene in enumerate(prepared)]
    else:
        ensure(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe required")
        prepared = prepared_scenes(scenario, root, info, draw.REEL_SIZE, False)
        images = [draw.still(scene, i, len(prepared)) for i, scene in enumerate(prepared)]
    for i, image in enumerate(images):
        image.save(destination / f"scene-{i + 1:02}.jpg", quality=90)
    draw.contact_sheet(images).save(destination / "apercu.jpg", quality=90)
    if not carousel:
        images[0].save(destination / "poster.jpg", quality=92)
        spec = encode_reel(scenario, root, destination, info, prepared)
    (destination / "legende.txt").write_text(caption(scenario, info))
    (destination / "credits.txt").write_text(credits_text(scenario, info))
    for asset in ("regular", "serif"):
        license_file = root / scenario["assets"][asset]["licenseFile"]["file"]
        shutil.copyfile(license_file, destination / license_file.name)
    write_json(destination / "scenario.json", scenario)
    files = [{"file": path.name, "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
             for path in sorted(destination.iterdir()) if path.is_file()]
    receipt = {"schemaVersion": 1, "contentId": scenario["id"], "status": "rendered_not_published",
               "fingerprint": fingerprint(scenario), "createdAt": stamp(now), "renderFinishedAt": stamp(utcnow()),
               "rendererContractVersion": RENDERER_CONTRACT, "rendererSha256": digest(Path(__file__).read_bytes()),
               "drawingSha256": digest(Path(draw.__file__).read_bytes()),
               "kind": scenario["kind"], "channel": scenario["channel"], "publishAt": scenario["publishAt"],
               "reviewValidUntil": scenario["review"]["validUntil"], "sourceCheckedOn": info["sourceCheckedOn"],
               "targetUrl": scenario["targetUrl"], "voice": None, "presenter": None,
               "sourceUrls": sorted(record["url"] for record in info["sources"].values()),
               "photos": {photo_id: {"licence": record["licence"], "author": record["author"], "sourcePage": record["sourcePage"]} for photo_id, record in info["photos"].items()},
               "video": spec, "files": files,
               "runtime": {"wallSeconds": round(time.monotonic() - started, 3), "encoderThreads": 2, "pillowVersion": pillow_version,
                           "ffmpegVersion": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0] if spec else None},
               "publication": {"uploaded": False, "scheduled": False, "published": False, "readyForAutomaticImport": False},
               "cost": {"newPaidService": False, "providerCalls": 0, "monetarySpendEur": 0}}
    write_json(destination / "receipt.json", receipt)
    return receipt


@contextlib.contextmanager
def exclusive(output):
    output = Path(output)
    ensure(not output.is_symlink(), "Output symlink forbidden")
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".production.lock"
    ensure(not lock.is_symlink(), "Lock symlink forbidden")
    with lock.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Invalid("A production job already holds this output") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def catalogue_entries(root):
    catalogue = load_json(safe_path(root, "catalogue.json"))
    ensure(catalogue.get("schemaVersion") == SCHEMA and isinstance(catalogue.get("items"), list) and len(catalogue["items"]) <= 100, "Invalid catalogue")
    entries, identifiers, filenames = [], set(), set()
    for entry in catalogue["items"]:
        ensure(ID.fullmatch(entry.get("contentId", "")) and entry["contentId"] not in identifiers, "Duplicate/invalid catalogue identity")
        ensure(entry.get("file") not in filenames, "Duplicate scenario file")
        identifiers.add(entry["contentId"]); filenames.add(entry["file"])
        scenario = load_json(verified_file(root, entry))
        ensure(scenario.get("id") == entry["contentId"], "Catalogue identity differs")
        due, expiry = instant(entry.get("notBefore")), instant(scenario["review"]["validUntil"])
        ensure(due < expiry, "Scenario expires before production date")
        entries.append((due, entry, scenario))
    return sorted(entries, key=lambda item: (item[0], item[1]["contentId"]))


def run(root=HERE, output=None, *, now=None, validate_only=False):
    root, output = Path(root), Path(output or Path(root) / "output")
    now = now or utcnow()
    ensure(now.tzinfo is not None, "Clock must include timezone")
    ensure(output.absolute() != root.absolute(), "Output cannot replace source directory")
    if now > HARD_STOP:
        return {"status": "period_ended", "produced": 0}
    entries = catalogue_entries(root)
    with exclusive(output):
        completed, skipped, validated = [], [], []
        for due, entry, scenario in entries:
            destination = output / scenario["id"]
            ensure(not destination.is_symlink(), "Artifact symlink forbidden")
            if destination.exists():
                historical = load_json(safe_path(destination, "receipt.json"))
                verify_receipt(destination, fingerprint(scenario, historical.get("rendererContractVersion", 1)))
                completed.append(scenario["id"])
                continue
            if due > now:
                skipped.append({"id": scenario["id"], "reason": "not_due"}); continue
            if instant(scenario["review"]["validUntil"]) <= now:
                skipped.append({"id": scenario["id"], "reason": "review_expired"}); continue
            info = validate_scenario(scenario, root, now)
            if validate_only:
                # Layout validation is meaningful without encoding video.
                size, carousel = (draw.SLIDE_SIZE, True) if scenario["kind"] == "carousel" else (draw.REEL_SIZE, False)
                prepared_scenes(scenario, root, info, size, carousel)
                caption(scenario, info)
                validated.append({"id": scenario["id"], "kind": scenario["kind"], "durationSeconds": info["duration"]})
                continue
            with tempfile.TemporaryDirectory(prefix=".render-", dir=output) as temporary:
                staged = Path(temporary) / "artifact"; staged.mkdir()
                receipt = render(scenario, root, staged, now, info)
                # Expiry during rendering never yields stock.
                ensure(utcnow() < instant(scenario["review"]["validUntil"]) and utcnow() <= HARD_STOP, "Review expired during rendering")
                staged.rename(destination)
            return {"status": "rendered_not_published", "contentId": scenario["id"], "kind": scenario["kind"], "produced": 1,
                    "output": str(destination), "wallSeconds": receipt["runtime"]["wallSeconds"]}
        if validate_only:
            return {"status": "validated", "produced": 0, "validated": validated, "completed": completed}
        future = [item for item in skipped if item["reason"] == "not_due"]
        expired = [item for item in skipped if item["reason"] == "review_expired"]
        return {"status": "idle", "produced": 0, "completed": completed, "skipped": skipped,
                "productionReadiness": {"status": "waiting_for_due_scenario" if future else "no_new_renderable_scenario",
                                        "futureScenarios": len(future), "expiredScenarios": len(expired),
                                        "renderedArtifacts": len(completed), "catalogueSize": len(entries),
                                        "publicationStockVerified": False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=HERE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args.root, args.output, validate_only=args.validate)
        print(json.dumps(result, ensure_ascii=False))
    except (Invalid, OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        raise SystemExit("Production stopped: " + str(error)) from error


if __name__ == "__main__":
    main()
