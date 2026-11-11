#!/usr/bin/env python3
"""Turn rendered photo posts into public media and reviewed social stock.

For each rendered scenario (output/<id>/receipt.json): copy the public files to
site-src/social-media/production/<id>/, list them in site-src/public-media.json,
write the reviewed batch reviewed-social/<id>-v1.json and its index entry.
Nothing is sent to Buffer: the publication panel imports the batches.

An Instagram reel can also go, as the same file, to TikTok, YouTube Shorts and Facebook
Reels: one more batch per network, only for the networks switched on in cadence.json
("crossposts"). All are off until the panel accepts those formats.

`--verify-public` checks, after deployment, that every queued asset URL serves
the exact bytes recorded in its batch.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

import production as p

HERE = Path(__file__).resolve().parent
SITE = HERE.parent.parent / "site-src"
PUBLIC_DIR = SITE / "social-media" / "production"
PUBLIC_MEDIA = SITE / "public-media.json"
STOCK = HERE / "reviewed-social"
INDEX = STOCK / "index.json"
PREFIX = ".github/vsd-production/reviewed-social/"
REEL_FILES = ("reel.mp4", "poster.jpg", "credits.txt", "dmsans-OFL.txt", "playfairdisplay-OFL.txt")
SLIDE_COUNT = 6  # site inventory (public_media.py) publishes exactly six photos per post
FONT_NOTICES = ("credits.txt", "dmsans-OFL.txt", "playfairdisplay-OFL.txt")
FORMAT_DOCS = {
    "instagram": ["https://support.buffer.com/en-us/articles/sharing-videos-through-buffer-LOe2p2rnAI",
                  "https://developers.buffer.com/types/InstagramPostMetadataInput.html",
                  "https://developers.buffer.com/guides/posts-and-scheduling.html"],
    "facebook": ["https://support.buffer.com/en-us/articles/using-facebook-with-buffer-jY1AM9fz2G",
                 "https://developers.buffer.com/types/FacebookPostMetadataInput.html",
                 "https://developers.buffer.com/guides/posts-and-scheduling.html"],
}
USER_AGENT = {"User-Agent": "VoyageSansDetour-stock/1.0 (contact@voyagesansdetour.fr)"}
CADENCE = HERE / "cadence.json"
# The same vertical file on other networks: payload kind, and whether the caption can point to a link in the bio.
CROSSPOSTS = {"tiktok": {"kind": "video", "bio": True}, "youtube": {"kind": "short", "bio": False}, "facebook": {"kind": "reel", "bio": False}}
CROSSPOST_DOCS = ["https://developers.buffer.com/guides/posts-and-scheduling.html"]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def public_files(scenario: dict) -> tuple[str, ...]:
    if scenario["kind"] == "reel":
        return REEL_FILES
    p.ensure(len(scenario["scenes"]) == SLIDE_COUNT, "The site publishes carousels of exactly six photos")
    return tuple(f"scene-{n:02}.jpg" for n in range(1, SLIDE_COUNT + 1)) + FONT_NOTICES


def media_url(content_id: str, name: str) -> str:
    return f"{p.ORIGIN}/social-media/production/{content_id}/{name}"


def payload_revision(payload: dict) -> str:
    """Same canonical form as bufferPayloadRevision() in the cloud bundle."""
    canonical = {"schemaVersion": 1, "channel": payload["channel"], "kind": payload["kind"], "text": payload["text"],
                 "aiGenerated": payload["aiGenerated"], "tiktokTitle": None,
                 "assets": [{"url": a["url"], "sha256": a["sha256"], "mimeType": a["mimeType"], "altText": a.get("altText")} for a in payload["assets"]]}
    return sha(json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode())


def batch_sha(batch: dict) -> str:
    """Same canonical form as describeStockBatch(): sorted keys, no spaces."""
    return sha(json.dumps(batch, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def destination_live(url: str) -> bool:
    request = urllib.request.Request(url, headers=USER_AGENT, method="HEAD")
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status == 200


def payload_kind(scenario: dict) -> str:
    """A reel is a reel; six photos are a "photos" post on Facebook and a "carousel" on Instagram."""
    if scenario["kind"] == "reel":
        return "reel"
    return "carousel" if scenario["channel"] == "instagram" else "photos"


def enabled_crossposts(path: Path = CADENCE) -> dict[str, dt.timedelta]:
    """Networks that also receive each Instagram reel, with the delay after the Instagram slot."""
    if not path.is_file():
        return {}
    entries = json.loads(path.read_text()).get("crossposts", {})
    return {name: dt.timedelta(hours=float(entry.get("delayHours", 1))) for name, entry in entries.items()
            if name in CROSSPOSTS and isinstance(entry, dict) and entry.get("enabled") is True}


def crosspost_caption(scenario: dict, text: str, channel: str) -> str:
    """The reel's caption for another network: where no bio link exists, the guide's address is written out."""
    if CROSSPOSTS[channel]["bio"]:
        return text
    cta = scenario["caption"]["cta"]
    p.ensure(text.count(cta) == 1, "Caption call to action not found")
    return text.replace(cta, "📌 Enregistrez cette vidéo pour votre voyage. 🔗 Le guide complet : " + scenario["targetUrl"])


def build_crosspost(scenario: dict, folder: Path, now: str, channel: str, delay: dt.timedelta) -> dict:
    """One more batch for the same rendered reel, on another network, a little after the Instagram slot."""
    p.ensure(scenario["kind"] == "reel" and scenario["channel"] == "instagram" and channel in CROSSPOSTS, "Only an Instagram reel is cross-posted")
    batch = build_batch(scenario, folder, now)
    item = batch["items"][0]
    content = f"vsd-production:{channel}:{scenario['id']}:photo-v1"
    payload = {**item["payload"], "channel": channel, "kind": CROSSPOSTS[channel]["kind"],
               "text": crosspost_caption(scenario, item["payload"]["text"], channel)}
    review = {**item["review"], "contentId": content, "payloadRevision": payload_revision(payload),
              "formatCapability": {**item["review"]["formatCapability"], "sourceUrls": CROSSPOST_DOCS}}
    due = p.stamp(p.instant(scenario["publishAt"]) + delay)
    p.ensure(p.instant(due) < p.instant(scenario["review"]["validUntil"]), "Cross-post slot outside the review window")
    return {"schemaVersion": 1, "batchId": f"{scenario['id']}-{channel}-v1",
            "items": [{**item, "contentId": content, "deduplicationKey": content, "dueAt": due, "payload": payload, "review": review}]}


def build_batch(scenario: dict, folder: Path, now: str) -> dict:
    content = f"vsd-production:{scenario['channel']}:{scenario['id']}:photo-v1"
    valid = scenario["review"]["validUntil"]
    verified = {"status": "verified", "observedAt": now, "validUntil": valid}
    if scenario["kind"] == "reel":
        assets = [{"url": media_url(scenario["id"], "reel.mp4"), "sha256": sha((folder / "reel.mp4").read_bytes()), "mimeType": "video/mp4"}]
        media = {**{key: assets[0][key] for key in ("url", "mimeType", "sha256")}, "required": True, **verified}
    else:
        assets = [{"url": media_url(scenario["id"], f"scene-{n:02}.jpg"), "sha256": sha((folder / f"scene-{n:02}.jpg").read_bytes()),
                   "mimeType": "image/jpeg", "altText": scene["alt"]} for n, scene in enumerate(scenario["scenes"], 1)]
        media = {"required": True, "url": None, "sha256": None,
                 "items": [{"url": a["url"], "sha256": a["sha256"], "mimeType": a["mimeType"], **verified} for a in assets]}
    payload = {"schemaVersion": 1, "channel": scenario["channel"], "kind": payload_kind(scenario),
               "text": (folder / "legende.txt").read_text(), "aiGenerated": False, "assets": assets}
    receipt = p.load_json(folder / "receipt.json")
    review = {
        "schemaVersion": 1, "contentId": content, "approved": True, "reviewedAt": now, "validUntil": valid,
        "payloadRevision": payload_revision(payload),
        "checks": {"editorialApproved": True, "rightsApproved": True, "creditsPreserved": True, "disclosurePreserved": True,
                   "formatRequirementsVerified": True, "requiresPaidCall": False,
                   "sources": {"status": "verified", "observedAt": scenario["review"]["checkedAt"], "validUntil": valid},
                   "syntheticPerson": False, "providerSyntheticSettingVerified": False},
        "media": media,
        "destination": {"url": scenario["targetUrl"], **verified},
        "monetization": {"containsAffiliateLinks": False, "partnerApproved": False, "linksVerified": False, "disclosurePreserved": False},
        "formatCapability": {**verified, "automaticPublishing": True, "verificationMethod": "official_documentation", "sourceUrls": FORMAT_DOCS[scenario["channel"]]},
        "evidence": {"status": "rendered_local_bytes_verified_public_deploy_pending", "format": "photo_" + scenario["kind"],
                     "rendererContractVersion": receipt["rendererContractVersion"], "receiptSha256": sha((folder / "receipt.json").read_bytes()),
                     "scenarioFingerprint": receipt["fingerprint"], "sourceCheckedOn": receipt["sourceCheckedOn"], "sourceUrls": receipt["sourceUrls"],
                     "creditsUrl": p.credits_url(scenario), "voice": None, "music": scenario["assets"].get("music", {}).get("title"),
                     "note": "Les octets publics sont à contrôler après déploiement avec social_stock.py --verify-public. Un créneau prévu n'est pas une réservation Buffer."},
    }
    item = {"contentId": content, "deduplicationKey": content, "title": scenario["title"], "dueAt": scenario["publishAt"],
            "payload": payload, "review": review}
    return {"schemaVersion": 1, "batchId": scenario["id"] + "-v1", "items": [item]}


def publish_media(scenario: dict, folder: Path, inventory: dict) -> dict:
    target = PUBLIC_DIR / scenario["id"]
    target.mkdir(parents=True, exist_ok=True)
    files = []
    for name in public_files(scenario):
        shutil.copyfile(folder / name, target / name)
        raw = (target / name).read_bytes()
        files.append({"name": name, "sha256": sha(raw), "bytes": len(raw)})
    if scenario["kind"] == "carousel":
        entry = {"contentId": scenario["id"], "kind": "photos", "approved": True, "files": files}
    else:
        entry = {"contentId": scenario["id"], "approved": True, "files": files}
    kept = [item for item in inventory["items"] if item["contentId"] != scenario["id"]]
    return {**inventory, "items": kept + [entry]}


def index_entry(batch: dict) -> dict:
    path = STOCK / (batch["batchId"] + ".json")
    path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n")
    return {"path": PREFIX + path.name, "fileSha256": sha(path.read_bytes()), "batchId": batch["batchId"],
            "batchSha256": batch_sha(batch), "itemIds": [batch["items"][0]["contentId"]]}


def admit(now: dt.datetime) -> dict:
    stamp = p.stamp(now.replace(microsecond=0))
    inventory = json.loads(PUBLIC_MEDIA.read_text())
    index = json.loads(INDEX.read_text())
    admitted, crossposts = [], enabled_crossposts()
    for _, _, scenario in p.catalogue_entries(HERE):
        folder = HERE / "output" / scenario["id"]
        batch_id = scenario["id"] + "-v1"
        if not folder.exists() or any(entry["batchId"] == batch_id for entry in index["items"]):
            continue
        p.verify_receipt(folder, p.fingerprint(scenario))
        p.ensure(p.instant(scenario["publishAt"]) > now, "Publication slot already passed: " + scenario["id"])
        p.ensure(destination_live(scenario["targetUrl"]), "Guide page not reachable: " + scenario["targetUrl"])
        inventory = publish_media(scenario, folder, inventory)
        batches = [build_batch(scenario, folder, stamp)]
        if scenario["kind"] == "reel" and scenario["channel"] == "instagram":
            for channel, delay in crossposts.items():
                try:
                    batches.append(build_crosspost(scenario, folder, stamp, channel, delay))
                except p.Invalid:
                    continue  # a copy that cannot be made never holds back the reel itself
        index = {**index, "items": index["items"] + [index_entry(batch) for batch in batches]}
        admitted += [batch["batchId"] for batch in batches]
    PUBLIC_MEDIA.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    return {"status": "admitted", "batches": admitted}


def verify_public() -> dict:
    index = json.loads(INDEX.read_text())
    photo_batches = {scenario["id"] + suffix for _, _, scenario in p.catalogue_entries(HERE) for suffix in ["-v1"] + [f"-{name}-v1" for name in CROSSPOSTS]}
    report = []
    for entry in index["items"]:
        if entry["batchId"] not in photo_batches:
            continue
        batch = json.loads((HERE.parent.parent / entry["path"]).read_text())
        for asset in batch["items"][0]["payload"]["assets"]:
            try:
                with urllib.request.urlopen(urllib.request.Request(asset["url"], headers=USER_AGENT), timeout=60) as response:
                    ok = sha(response.read()) == asset["sha256"]
            except OSError:
                ok = False
            report.append({"batchId": entry["batchId"], "url": asset["url"], "ok": ok})
    return {"status": "verified" if all(row["ok"] for row in report) else "mismatch", "checked": len(report),
            "failures": [row for row in report if not row["ok"]]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-public", action="store_true")
    args = parser.parse_args()
    result = verify_public() if args.verify_public else admit(p.utcnow())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "mismatch":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
