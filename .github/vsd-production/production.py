#!/usr/bin/env python3
"""Offline, bounded production from immutable reviewed scenarios. No publication.

The runner selects at most one due scenario, verifies sources/rights/fingerprints,
renders a portable artifact and keeps a receipt for idempotent retries. It never
researches facts, invents a review, calls a generator or renews an expired source.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time
from functools import lru_cache
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version

HERE = Path(__file__).resolve().parent
W, H, FPS = 1080, 1920, 30
SCHEMA = 1
RENDERER_CONTRACT = 1
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,95}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")
HARD_STOP = dt.datetime(2027, 9, 14, 21, 59, 59, tzinfo=dt.timezone.utc)
COLORS = {"cobalt": ("#234CDD", "#F7F4EC", "#E6EE77"),
          "ink": ("#142A43", "#F7F4EC", "#F8DE55")}


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
    ensure(isinstance(value, str) and 0 < len(value.strip()) <= maximum and value == value.strip(), "Invalid text")
    ensure(not any(ord(c) < 32 or ord(c) == 127 for c in value), "Control character in text")
    return value


def https(value):
    parsed = urlsplit(text(value, 1000))
    ensure(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.port, "HTTPS public URL required")
    return parsed


def validate_scenario(scenario, root, now):
    ensure(scenario.get("schemaVersion") == SCHEMA and ID.fullmatch(scenario.get("id", "")), "Invalid scenario identity")
    ensure(scenario.get("format") in ("music_text", "silent_text"), "Unsupported format: this job has no voice generation")
    ensure(scenario.get("presenter") == "none", "Presenter assets are not supported by this renderer")
    ensure(scenario.get("theme") in COLORS, "Unknown theme")
    ensure(scenario.get("aiAssisted") is True, "Assisted editing disclosure required")
    text(scenario.get("title"), 150); text(scenario.get("destination"), 22)
    ensure(isinstance(scenario.get("hashtags"), list) and 1 <= len(scenario["hashtags"]) <= 8 and all(re.fullmatch(r"#[A-Za-z0-9À-ÿ]+", tag) for tag in scenario["hashtags"]), "Invalid hashtags")
    ensure(isinstance(scenario.get("caption"), str) and 0 < len(scenario["caption"]) <= 1400, "Caption missing or too long")
    for line in scenario["caption"].split("\n"):
        if line:
            text(line, 300)
    target = https(scenario.get("targetUrl"))
    ensure(target.hostname == "voyagesansdetour.fr" and target.path.startswith("/portugal/") and not target.query and not target.fragment, "Unexpected target")
    review = scenario.get("review", {})
    ensure(review.get("status") == "reviewed_for_render", "Unreviewed scenario")
    checked, expiry = instant(review.get("checkedAt")), instant(review.get("validUntil"))
    ensure(checked <= now < expiry <= HARD_STOP, "Review outside its validity window")
    ensure(expiry - checked <= dt.timedelta(days=31), "Review window exceeds one month")
    source = scenario.get("source", {})
    article_path = verified_file(root, source.get("article", {}))
    article = load_json(article_path)
    checked_on = dt.date.fromisoformat(article.get("sourcesCheckedOn", ""))
    ensure(checked_on <= now.date() and now.date() <= checked_on + dt.timedelta(days=30), "Source needs fresh editorial review")
    ensure(checked.date() >= checked_on, "Scenario review predates source")
    ensure(expiry.date() <= checked_on + dt.timedelta(days=30), "Scenario expiry exceeds source review window")
    ensure(source.get("checkedOn") == str(checked_on), "Mismatched source date")
    ensure(target.path == "/portugal/" + article.get("slug", "") + "/", "Article target mismatch")
    notes_path = verified_file(root, source.get("researchEvidence", {}))
    ensure(notes_path.stat().st_size > 100, "Empty research evidence")
    proof = load_json(verified_file(root, source.get("publicationEvidence", {})))
    ensure(proof.get("url") == scenario["targetUrl"] and proof.get("httpStatus") == 200 and proof.get("matchesLocalBuild") is True and HASH.fullmatch(proof.get("htmlSha256", "")), "Source guide publication not evidenced")
    ensure(instant(proof["checkedAt"]) <= checked, "Source publication postdates scenario review")
    official_urls = {s["url"] for s in article["sources"]}
    sections = {s["id"]: s for s in article["sections"]}
    used = set()
    scenes = scenario.get("scenes")
    ensure(isinstance(scenes, list) and 4 <= len(scenes) <= 8, "Require four to eight scenes")
    for scene in scenes:
        ensure(scene.get("layout") in ("intro", "route", "ticket", "checklist", "outro"), "Unknown scene layout")
        ensure(type(scene.get("seconds")) in (int, float) and math.isfinite(scene["seconds"]) and 3 <= scene["seconds"] <= 8, "Scene duration invalid")
        ensure(abs(scene["seconds"] * FPS - round(scene["seconds"] * FPS)) < 1e-6, "Scene duration must use whole frames")
        text(scene.get("label"), 40)
        ensure(isinstance(scene.get("title"), list) and 1 <= len(scene["title"]) <= 3, "Title requires one to three lines")
        for line in scene["title"]:
            text(line, 26)
        ensure(isinstance(scene.get("body"), list) and 1 <= len(scene["body"]) <= 3, "Body requires one to three lines")
        for line in scene["body"]:
            text(line, 49)
        text(scene.get("note"), 74)
        ensure(isinstance(scene.get("graphicLabels"), list) and len(scene["graphicLabels"]) == 3, "Three graphic labels required")
        for line in scene["graphicLabels"]:
            text(line, 22)
        ensure(isinstance(scene.get("evidence"), list) and scene["evidence"], "Each scene needs evidence")
        for claim in scene["evidence"]:
            ensure(claim.get("sectionId") in sections and claim.get("url") in official_urls, "Unknown evidence reference")
            quote = text(claim.get("supportingText"), 800)
            ensure(quote in json.dumps(sections[claim["sectionId"]], ensure_ascii=False), "Evidence excerpt changed or is not in article")
            used.add(claim["url"])
    duration = sum(scene["seconds"] for scene in scenes)
    ensure(15 <= duration <= 45, "Render duration out of bounds")
    assets = scenario.get("assets", {})
    for name in ("regular", "bold", "serif"):
        asset = assets.get(name, {})
        verified_file(root, asset)
        ensure(asset.get("license") == "OFL-1.1", "Unexpected font licence")
        verified_file(root, asset.get("licenseFile", {}))
    if scenario["format"] == "music_text":
        music = assets.get("music", {})
        verified_file(root, music)
        ensure(music.get("license") == "CC-BY-4.0" and music.get("commercialUseAllowed") is True, "Music rights unqualified")
        ensure(music.get("licenseUrl") == "https://creativecommons.org/licenses/by/4.0/", "Music licence URL changed")
        provenance = load_json(verified_file(root, music.get("provenance", {})))
        ensure(provenance.get("commercialUseAllowed") is True and provenance.get("license") == "CC BY 4.0" and provenance["download"]["sha256"] == music["sha256"], "Music provenance mismatch")
        ensure(music.get("title") == provenance.get("title") and music.get("author") == provenance.get("composer") and music.get("sourceUrl") == provenance.get("sourceTrackPage"), "Music attribution mismatch")
    else:
        ensure("music" not in assets, "Silent scenario contains unused audio")
    return {"duration": duration, "sourceUrls": sorted(used), "sourceCheckedOn": str(checked_on)}


def fingerprint(scenario):
    # An existing immutable artifact survives later bugfixes. Its own renderer
    # hash stays in the receipt; a new intended visual version needs a new ID.
    return digest(canonical({"scenario": scenario, "rendererContractVersion": RENDERER_CONTRACT}))


@lru_cache(maxsize=128)
def get_font(path, size):
    return ImageFont.truetype(str(path), size)


def draw_line(draw, line, x, y, font_path, size, color, width=896):
    f = get_font(str(font_path), size)
    ensure(draw.textlength(line, font=f) <= width, "Layout overflow: " + line)
    draw.text((x, y), line, font=f, fill=color, anchor="lt")


def build_scene(scenario, scene, index, root):
    primary, paper, accent = COLORS[scenario["theme"]]
    dark = index % 2 == 0
    bg, fg = (primary, paper) if dark else (paper, primary)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    regular, bold, serif = (root / scenario["assets"][name]["file"] for name in ("regular", "bold", "serif"))
    draw_line(d, "VOYAGE SANS DÉTOUR", 88, 183, bold, 28, fg)
    d.line((88, 245, 958, 245), fill=fg, width=2)
    draw_line(d, scenario["destination"].upper(), 88, 283, bold, 27, fg)
    draw_line(d, f"{index + 1:02} / {len(scenario['scenes']):02}", 814, 287, bold, 23, fg, 145)
    d.rounded_rectangle((86, 364, 962, 421), 26, fill=accent)
    draw_line(d, scene["label"], 111, 380, bold, 25, primary, 826)
    for n, line in enumerate(scene["title"]):
        size = 99 if len(line) < 18 else 82
        draw_line(d, line, 84, 486 + 122 * n, serif, size, fg)
    # All graphic motifs are original abstract compositions. The route motif is
    # explicitly a preparation sequence, never an operator map or trip duration.
    top = 935
    d.rounded_rectangle((88, top, 961, top + 333), 30, fill=paper if dark else "#E8EAF4")
    if scene["layout"] in ("intro", "outro"):
        draw_line(d, "SANS DÉTOUR", 139, top + 47, bold, 51, primary, 775)
        draw_line(d, "UNE ARRIVÉE MIEUX PRÉPARÉE", 139, top + 128, regular, 29, primary, 775)
        for n in range(3):
            d.rounded_rectangle((140 + n * 259, top + 216, 351 + n * 259, top + 265), 22, fill=accent)
    elif scene["layout"] == "route":
        for n in range(3):
            x = 171 + n * 345
            if n < 2:
                d.line((x, top + 139, x + 345, top + 139), fill=primary, width=8)
            d.ellipse((x - 30, top + 109, x + 30, top + 169), fill=primary)
            draw_line(d, str(n + 1), x - 9, top + 120, bold, 24, paper, 30)
        draw_line(d, "ADRESSE", 127, top + 216, bold, 20, primary, 200)
        draw_line(d, "PARCOURS", 460, top + 216, bold, 20, primary, 200)
        draw_line(d, "ARRIVÉE", 817, top + 216, bold, 20, primary, 125)
        draw_line(d, "VOTRE PRÉPARATION · SCHÉMA", 140, top + 48, regular, 25, primary, 775)
    elif scene["layout"] == "ticket":
        for n in range(2):
            x = 142 + n * 398
            d.rounded_rectangle((x, top + 56, x + 350, top + 260), 22, fill=primary)
            draw_line(d, f"0{n + 1}", x + 28, top + 83, serif, 60, accent, 290)
            draw_line(d, "UNE PERSONNE", x + 28, top + 180, bold, 24, paper, 300)
    else:
        for n, label in enumerate(scene["graphicLabels"]):
            yy = top + 58 + n * 81
            d.rounded_rectangle((142, yy, 182, yy + 40), 12, fill=primary)
            draw_line(d, label, 211, yy + 5, bold, 28, primary, 680)
    for n, line in enumerate(scene["body"]):
        draw_line(d, line, 88, 1335 + 58 * n, bold, 34, fg)
    # Separate small note accommodates the source date on every scene.
    draw_line(d, scene["note"], 88, 1550, regular, 23, fg)
    draw_line(d, "voyagesansdetour.fr · le guide et ses sources", 88, 1621, bold, 25, fg)
    draw_line(d, "MONTAGE ASSISTÉ PAR IA · SANS RÉCIT VÉCU", 88, 1744, regular, 20, fg)
    draw_line(d, "Sources contrôlées le " + scenario["source"]["checkedOn"], 88, 1784, regular, 20, fg)
    return im, (bg, fg, accent)


def frame(base, colors, index, local_t, elapsed, duration):
    im = base.copy(); d = ImageDraw.Draw(im)
    bg, fg, accent = colors
    # Animated top route line and small orbit are decorative; text stays still.
    phase = local_t * 0.68 + index
    cx, cy = 861, 792
    d.arc((cx - 116, cy - 73, cx + 116, cy + 73), 198, 348, fill=fg, width=3)
    angle = math.radians(198 + (local_t * 28) % 150)
    x, y = cx + 116 * math.cos(angle), cy + 73 * math.sin(angle)
    d.ellipse((x - 8, y - 8, x + 8, y + 8), fill=accent)
    yy = 1700
    d.rounded_rectangle((88, yy, 961, yy + 6), 3, fill=fg)
    d.rounded_rectangle((88, yy - 1, 88 + max(3, 873 * elapsed / duration), yy + 7), 4, fill=accent)
    # Light beat-linked stepping over the three intro blocks, without flashing.
    if index in (0, 5):
        beat = int(local_t / (60 / 90)) % 3
        x = 140 + beat * 259
        d.rounded_rectangle((x + 10, 1158, x + 201, 1193), 16, fill=fg)
    return im


def caption(scenario, info):
    value = scenario["caption"] + "\n\nLe guide et ses sources : " + scenario["targetUrl"]
    value += "\nSources contrôlées le " + info["sourceCheckedOn"] + ". Consultez les horaires et alertes pour votre date."
    value += "\n\nTexte et montage assistés par IA. Propositions documentées, sans récit de trajet vécu. Aucun personnage virtuel ni voix de synthèse dans cette vidéo."
    if scenario["format"] == "music_text":
        music = scenario["assets"]["music"]
        value += ("\n\nMusique : « " + music["title"] + " » — " + music["author"] + ".\n" + music["sourceUrl"] +
                  "\nLicence CC BY 4.0 : " + music["licenseUrl"] + "\nModifications : extrait, niveau ajusté, fondus d’entrée et de sortie, synchronisation au montage. Aucune approbation de l’auteur n’est revendiquée.")
    value += "\n\n" + " ".join(scenario["hashtags"]) + "\n"
    ensure(len(value) <= 2200, "Instagram caption exceeds 2200 characters")
    return value


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
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    loudness = None
    if audio:
        measurement = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-af", "ebur128=peak=true", "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True).stderr
        summary = measurement.rsplit("Summary:", 1)[-1]
        integrated = re.search(r"I:\s*(-?[\d.]+) LUFS", summary)
        peak = re.search(r"Peak:\s*(-?[\d.]+) dBFS", summary)
        ensure(integrated and peak, "Loudness measurement unavailable")
        loudness = {"integratedLufs": float(integrated[1]), "truePeakDbfs": float(peak[1])}
        ensure(-22 <= loudness["integratedLufs"] <= -14 and loudness["truePeakDbfs"] <= -1, "Music level outside delivery range")
    return {"width": W, "height": H, "fps": FPS, "durationSeconds": float(result["format"]["duration"]), "videoCodec": "h264", "pixelFormat": "yuv420p", "audioCodec": "aac" if audio else None, "audioSampleRate": 48000 if audio else None, "fullDecodePassed": True, "loudness": loudness}


def verify_receipt(folder, expected_fingerprint):
    receipt = load_json(safe_path(folder, "receipt.json"))
    ensure(receipt.get("fingerprint") == expected_fingerprint and receipt.get("status") == "rendered_not_published", "Existing identity has different inputs or incomplete receipt")
    ensure(isinstance(receipt.get("files"), list) and receipt["files"], "Empty receipt inventory")
    for entry in receipt["files"]:
        verified_file(folder, entry)
    return receipt


def render(scenario, root, destination, now, info):
    started = time.monotonic()
    ensure(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe required")
    bases = [build_scene(scenario, scene, i, root) for i, scene in enumerate(scenario["scenes"])]
    for i, (base, colors) in enumerate(bases):
        base.save(destination / f"scene-{i + 1:02}.jpg", quality=92)
    contact = Image.new("RGB", (360 * 3, 640 * math.ceil(len(bases) / 3)), "#F7F4EC")
    for i, (base, _) in enumerate(bases):
        contact.paste(base.resize((360, 640), Image.Resampling.LANCZOS), ((i % 3) * 360, (i // 3) * 640))
    contact.save(destination / "apercu.jpg", quality=94)
    base, colors = bases[0]
    frame(base, colors, 0, 1, 1, info["duration"]).save(destination / "poster.jpg", quality=94)
    music = scenario["format"] == "music_text"
    video = destination / "reel.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{W}x{H}", "-framerate", str(FPS), "-i", "pipe:0"]
    if music:
        command += ["-i", str(root / scenario["assets"]["music"]["file"]), "-map", "0:v:0", "-map", "1:a:0", "-af", f"atrim=0:{info['duration']},asetpts=PTS-STARTPTS,afade=t=in:d=0.5,afade=t=out:st={info['duration'] - 1.5}:d=1.5,loudnorm=I=-18:TP=-1.5:LRA=7", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    else:
        command += ["-an"]
    command += ["-t", str(info["duration"]), "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-map_metadata", "-1", str(video)]
    with (destination / "encode.log").open("wb") as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            elapsed_frames = 0
            for i, scene in enumerate(scenario["scenes"]):
                base, colors = bases[i]
                count = round(scene["seconds"] * FPS)
                for n in range(count):
                    rendered = frame(base, colors, i, n / FPS, (elapsed_frames + n) / FPS, info["duration"])
                    process.stdin.write(rendered.tobytes())
                elapsed_frames += count
            process.stdin.close()
            ensure(process.wait(timeout=120) == 0, "Encoding failed; inspect encode.log")
        except BaseException:
            if process.poll() is None:
                process.kill(); process.wait()
            raise
    spec = verify_video(video, info["duration"], music)
    (destination / "legende.txt").write_text(caption(scenario, info))
    (destination / "credits.txt").write_text(
        "Voyage Sans Détour — compositions et graphiques originaux.\n"
        "Schémas de préparation, pas de carte de transport à l’échelle.\n"
        "Polices DM Sans et Playfair Display : SIL OFL 1.1 ; avis inclus.\n\n" + caption(scenario, info))
    for asset in ("regular", "serif"):
        license_file = root / scenario["assets"][asset]["licenseFile"]["file"]
        shutil.copyfile(license_file, destination / license_file.name)
    write_json(destination / "scenario.json", scenario)
    # The receipt is final and atomically moved together with its files. A crash
    # before that move produces no completed state and never a social send.
    files = [{"file": path.name, "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
             for path in sorted(destination.iterdir()) if path.is_file()]
    receipt = {"schemaVersion": SCHEMA, "contentId": scenario["id"], "status": "rendered_not_published",
               "fingerprint": fingerprint(scenario), "createdAt": stamp(now), "renderFinishedAt": stamp(utcnow()),
               "rendererContractVersion": RENDERER_CONTRACT, "rendererSha256": digest(Path(__file__).read_bytes()),
               "reviewValidUntil": scenario["review"]["validUntil"], "sourceCheckedOn": info["sourceCheckedOn"],
               "targetUrl": scenario["targetUrl"], "format": scenario["format"], "presenter": "none", "voice": None,
               "sourceUrls": info["sourceUrls"], "video": spec, "files": files,
               "runtime": {"wallSeconds": round(time.monotonic() - started, 3), "encoderThreads": 2,
                           "pillowVersion": pillow_version, "ffmpegVersion": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]},
               "publication": {"uploaded": False, "scheduled": False, "published": False, "readyForAutomaticImport": False},
               "cost": {"newPaidService": False, "providerCalls": 0, "monetarySpendEur": 0},
               "limitations": ["No source refresh or editorial generation is performed by this job.", "A rendered MP4 is not a final social payload review or publication.", "Bit-identical encoding across different FFmpeg/Pillow builds is not promised; immutable inputs and exact output hashes are recorded."]}
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


def run(root=HERE, output=None, *, now=None, validate_only=False):
    root, output = Path(root), Path(output or Path(root) / "output")
    now = now or utcnow()
    ensure(now.tzinfo is not None, "Clock must include timezone")
    ensure(output.absolute() != root.absolute(), "Output cannot replace source directory")
    if now > HARD_STOP:
        return {"status": "period_ended", "produced": 0}
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
    with exclusive(output):
        completed, skipped = [], []
        for due, entry, scenario in sorted(entries, key=lambda item: (item[0], item[1]["contentId"])):
            destination = output / scenario["id"]
            ensure(not destination.is_symlink(), "Artifact symlink forbidden")
            if destination.exists():
                verify_receipt(destination, fingerprint(scenario))
                completed.append(scenario["id"])
                continue
            if due > now:
                skipped.append({"id": scenario["id"], "reason": "not_due"}); continue
            if instant(scenario["review"]["validUntil"]) <= now:
                skipped.append({"id": scenario["id"], "reason": "review_expired"}); continue
            info = validate_scenario(scenario, root, now)
            if validate_only:
                # Layout validation is meaningful without rendering video.
                for i, scene in enumerate(scenario["scenes"]):
                    build_scene(scenario, scene, i, root)
                caption(scenario, info)
                return {"status": "validated", "contentId": scenario["id"], "produced": 0, "durationSeconds": info["duration"]}
            with tempfile.TemporaryDirectory(prefix=".render-", dir=output) as temporary:
                staged = Path(temporary) / "artifact"; staged.mkdir()
                receipt = render(scenario, root, staged, now, info)
                # Re-check expiry at completion, independent of the injected
                # selection clock. Expiry during rendering never yields stock.
                ensure(utcnow() < instant(scenario["review"]["validUntil"]) and utcnow() <= HARD_STOP, "Review expired during rendering")
                staged.rename(destination)
            return {"status": "rendered_not_published", "contentId": scenario["id"], "produced": 1, "output": str(destination), "videoSha256": next(f["sha256"] for f in receipt["files"] if f["file"] == "reel.mp4"), "wallSeconds": receipt["runtime"]["wallSeconds"]}
        return {"status": "idle", "produced": 0, "completed": completed, "skipped": skipped}


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
