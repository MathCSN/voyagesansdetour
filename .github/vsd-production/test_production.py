import copy
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import photo_intake
import production as p
import seal_scenarios
import social_stock

HEAVY = {".jpg", ".mp3", ".ttf"}


def link_or_copy(source, target):
    # Large binaries are hard-linked for speed; tests replace them, never write through.
    if Path(source).suffix in HEAVY:
        os.link(source, target)
    else:
        shutil.copy2(source, target)


def within_review(scenario):
    # Each scenario is checked inside its own review window: posts are generated on different days.
    return p.instant(scenario["review"]["checkedAt"]) + dt.timedelta(seconds=1)


class ProductionGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "bundle"
        self.root.mkdir()
        # auto/ holds the inputs of posts generated from guides; the catalogue references it once one exists.
        for folder in ("assets", "evidence", "scenarios", "sources", "auto"):
            if (p.HERE / folder).is_dir():
                shutil.copytree(p.HERE / folder, self.root / folder, copy_function=link_or_copy)
        shutil.copyfile(p.HERE / "catalogue.json", self.root / "catalogue.json")
        self.catalogue = p.load_json(self.root / "catalogue.json")
        self.scenario_file = self.root / "scenarios/ig-lisbonne-tram28-tarifs-2026-10.json"
        self.scenario = p.load_json(self.scenario_file)
        self.now = p.instant(self.scenario["review"]["checkedAt"]) + dt.timedelta(seconds=1)
        clock = mock.patch.object(p, "utcnow", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.output = Path(self.temporary.name) / "output"

    def save(self, scenario=None, path=None):
        scenario, path = scenario or self.scenario, path or self.scenario_file
        p.write_json(path, scenario)
        for item in self.catalogue["items"]:
            if item["file"] == str(path.relative_to(self.root)):
                item["sha256"] = p.digest(path.read_bytes())
        p.write_json(self.root / "catalogue.json", self.catalogue)

    def reseal(self, scenario, relative):
        """Refresh the fingerprint of a registry the scenario points to."""
        for key in ("sources", "photos"):
            if scenario[key]["file"] == relative:
                scenario[key]["sha256"] = p.digest((self.root / relative).read_bytes())

    def only(self, scenario_id):
        self.catalogue["items"] = [item for item in self.catalogue["items"] if item["contentId"] == scenario_id]
        p.write_json(self.root / "catalogue.json", self.catalogue)

    def fake_render(self, scenario, root, destination, now, info):
        (destination / "reel.mp4").write_bytes(b"test-video")
        receipt = {"status": "rendered_not_published", "rendererContractVersion": p.RENDERER_CONTRACT, "fingerprint": p.fingerprint(scenario),
                   "runtime": {"wallSeconds": 0}, "files": [{"file": "reel.mp4", "sha256": p.digest(b"test-video")}]}
        p.write_json(destination / "receipt.json", receipt)
        return receipt

    # --- The shipped stock -------------------------------------------------

    def test_every_shipped_scenario_validates_and_fits_its_frame(self):
        self.assertGreaterEqual(len(self.catalogue["items"]), 8)
        kinds = set()
        for _, _, scenario in p.catalogue_entries(self.root):
            info = p.validate_scenario(scenario, self.root, within_review(scenario))
            size, carousel = (p.draw.SLIDE_SIZE, True) if scenario["kind"] == "carousel" else (p.draw.REEL_SIZE, False)
            self.assertEqual(len(p.prepared_scenes(scenario, self.root, info, size, carousel)), len(scenario["scenes"]))
            kinds.add(scenario["kind"])
        self.assertEqual(kinds, {"reel", "carousel"})

    # Queued on 11/11/2026 two characters over, before auto_social.py kept every caption under the limit
    # (fitted_caption). A queued post is never rewritten: the exception is named, the limit stays for all others.
    LONGER_QUEUED_CAPTIONS = {"ig-japon-budget-2-semaines-2026-11-15": 1002}

    def test_caption_is_short_and_lively_with_one_credit_line(self):
        for _, _, scenario in p.catalogue_entries(self.root):
            info = p.validate_scenario(scenario, self.root, within_review(scenario))
            text = p.caption(scenario, info)
            self.assertTrue(text.startswith(scenario["caption"]["hook"]))
            self.assertLessEqual(len(text), self.LONGER_QUEUED_CAPTIONS.get(scenario["id"], 1000), scenario["id"])
            self.assertEqual(text.count("crédits : "), 1)
            self.assertIn(p.credits_url(scenario), text)
            self.assertNotIn("CC BY-SA", text)
            for phrase in p.FORBIDDEN:
                self.assertNotIn(phrase, text.lower())
            if scenario["channel"] == "facebook":
                self.assertIn(scenario["targetUrl"], text)

    def test_credits_file_names_every_photo_author_and_licence(self):
        info = p.validate_scenario(self.scenario, self.root, self.now)
        credits = p.credits_text(self.scenario, info)
        for record in info["photos"].values():
            self.assertIn(record["author"], credits)
            self.assertIn(record["licenceUrl"], credits)
        self.assertIn("Kevin MacLeod", credits)
        self.assertIn("relevé le 2026-10-24", credits)

    def test_publication_slots_cover_four_weeks(self):
        slots = sorted(p.instant(s["publishAt"]) for _, _, s in p.catalogue_entries(self.root))
        self.assertGreaterEqual((slots[-1] - slots[0]).days, 21)
        # The publication panel counts posts per network over any seven days: the queue never asks for more than cadence.json allows.
        limits = {name: entry["weeklyLimit"] for name, entry in json.loads((p.HERE / "cadence.json").read_text())["channels"].items()}
        # A post withdrawn from the stock will never go out: the post made again for its slot does not count twice.
        retired = {entry["batchId"] for entry in json.loads((p.HERE / "reviewed-social" / "index.json").read_text()).get("retirements", [])}
        for channel, limit in limits.items():
            due = sorted(p.instant(s["publishAt"]) for _, _, s in p.catalogue_entries(self.root) if s["channel"] == channel and s["id"] + "-v1" not in retired)
            for moment in due:
                self.assertLessEqual(sum(moment - dt.timedelta(days=7) < other <= moment for other in due), limit, channel)

    # --- The charter, enforced ----------------------------------------------

    def test_old_text_card_format_is_refused(self):
        self.scenario.update(schemaVersion=1, format="music_text")
        with self.assertRaisesRegex(p.Invalid, "photo format"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_synthetic_voice_or_presenter_is_refused(self):
        for key in ("voice", "presenter"):
            scenario = copy.deepcopy(self.scenario)
            scenario[key] = "fr_FR-siwis-medium"
            with self.assertRaisesRegex(p.Invalid, "synthetic voice"):
                p.validate_scenario(scenario, self.root, self.now)

    def test_defensive_boilerplate_is_refused(self):
        self.scenario["caption"]["lines"][0] = "Propositions documentées, sans récit de voyage vécu."
        with self.assertRaisesRegex(p.Invalid, "Boilerplate"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_closed_lisbon_lifts_are_refused(self):
        for name in ("Elevador de Santa Justa", "Ascensor da Glória", "la Bica", "Lavra"):
            scenario = copy.deepcopy(self.scenario)
            scenario["scenes"][1]["detail"] = name + " : 6,20 €."
            with self.assertRaisesRegex(p.Invalid, "Closed service"):
                p.validate_scenario(scenario, self.root, self.now)

    def test_repeated_photo_is_refused(self):
        self.scenario["scenes"][1]["photo"] = self.scenario["scenes"][0]["photo"]
        with self.assertRaisesRegex(p.Invalid, "photo cannot be repeated"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_repeated_headline_is_refused(self):
        self.scenario["scenes"][2]["headline"] = list(self.scenario["scenes"][1]["headline"])
        with self.assertRaisesRegex(p.Invalid, "headline cannot be repeated"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_scene_without_sourced_fact_is_refused(self):
        del self.scenario["scenes"][1]["facts"]
        with self.assertRaisesRegex(p.Invalid, "sourced fact"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_invented_fact_is_refused(self):
        self.scenario["scenes"][0]["facts"][0]["excerpt"] = "Elétrico (1 viagem) 1,00"
        with self.assertRaisesRegex(p.Invalid, "not in its dated snapshot"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_changed_source_snapshot_stops(self):
        path = self.root / "sources/social-2026-10-24/carris-tarifas-2026.txt"
        path.write_text(path.read_text() + "\nmodifié")
        with self.assertRaisesRegex(p.Invalid, "fingerprint"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_review_cannot_outlive_its_sources(self):
        self.scenario["review"]["validUntil"] = "2026-11-24T00:00:00Z"
        with self.assertRaisesRegex(p.Invalid, "outlives its source"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_non_free_photo_licence_is_refused(self):
        relative = self.scenario["photos"]["file"]
        catalogue = p.load_json(self.root / relative)
        photo_id = self.scenario["scenes"][0]["photo"]
        catalogue["photos"][photo_id]["licence"] = "CC BY-NC 4.0"
        p.write_json(self.root / relative, catalogue)
        self.reseal(self.scenario, relative)
        with self.assertRaisesRegex(p.Invalid, "licence not accepted"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_ai_generated_photo_is_refused_by_the_engine(self):
        relative = self.scenario["photos"]["file"]
        photo_id = self.scenario["scenes"][0]["photo"]
        for field, value in (("categories", "AI-generated images of Portugal|Lisbon"),
                             ("commonsTitle", "File:Lisbon tram, made with Midjourney.jpg"),
                             ("commonsCredit", "Created with DALL·E 3")):
            with self.subTest(field=field):
                catalogue = p.load_json(self.root / relative)
                original = dict(catalogue["photos"][photo_id])
                catalogue["photos"][photo_id][field] = value
                p.write_json(self.root / relative, catalogue)
                self.reseal(self.scenario, relative)
                with self.assertRaisesRegex(p.Invalid, "AI-generated image refused"):
                    p.validate_scenario(self.scenario, self.root, self.now)
                catalogue["photos"][photo_id] = original
                p.write_json(self.root / relative, catalogue)
                self.reseal(self.scenario, relative)

    def test_altered_photo_bytes_stop(self):
        photo_id = self.scenario["scenes"][0]["photo"]
        path = self.root / "assets/photos" / (photo_id + ".jpg")
        raw = path.read_bytes()
        path.unlink()
        path.write_bytes(raw + b"0")
        with self.assertRaisesRegex(p.Invalid, "fingerprint"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_music_attribution_cannot_be_substituted(self):
        self.scenario["assets"]["music"]["author"] = "Someone Else"
        with self.assertRaisesRegex(p.Invalid, "attribution"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_guides_outside_portugal_are_valid_targets(self):
        self.scenario["targetUrl"] = "https://voyagesansdetour.fr/espagne/madrid-3-jours/"
        p.validate_scenario(self.scenario, self.root, self.now)
        self.scenario["targetUrl"] = "https://voyagesansdetour.fr/espagne/../madrid/"
        with self.assertRaisesRegex(p.Invalid, "Unexpected target"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_instagram_cta_must_point_to_the_bio(self):
        self.scenario["caption"]["cta"] = "Le guide complet est sur le site."
        with self.assertRaisesRegex(p.Invalid, "link in bio"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_headline_overflow_stops_before_encoding(self):
        self.scenario["scenes"][1]["headline"] = ["W" * 30, "W" * 30]
        info = p.validate_scenario(self.scenario, self.root, self.now)
        with self.assertRaisesRegex(p.Invalid, "Layout overflow"):
            p.prepared_scenes(self.scenario, self.root, info, p.draw.REEL_SIZE, False)

    def test_carousel_renders_six_portrait_slides_with_credits(self):
        scenario_id = "fb-sintra-budget-2026-11"
        self.only(scenario_id)
        result = p.run(self.root, self.output, now=self.now)
        self.assertEqual(result["produced"], 1)
        folder = self.output / scenario_id
        slides = sorted(folder.glob("scene-*.jpg"))
        self.assertEqual(len(slides), 6)
        from PIL import Image
        with Image.open(slides[0]) as first:
            self.assertEqual(first.size, (1080, 1350))
        self.assertIn("Wikimedia Commons", (folder / "credits.txt").read_text())
        p.verify_receipt(folder, p.fingerprint(p.load_json(folder / "scenario.json")))

    # --- Idempotence and safety, kept from the previous engine --------------

    def test_expired_and_future_content_do_not_invoke_renderer(self):
        # Generated posts are reviewed on their own day: test before the first window and after the last.
        reviews = [scenario["review"] for _, _, scenario in p.catalogue_entries(self.root)]
        with mock.patch.object(p, "render") as render:
            early = p.run(self.root, self.output, now=min(p.instant(r["checkedAt"]) for r in reviews) - dt.timedelta(hours=1))
            late = p.run(self.root, self.output, now=max(p.instant(r["validUntil"]) for r in reviews))
        render.assert_not_called()
        self.assertEqual(early["productionReadiness"]["status"], "waiting_for_due_scenario")
        self.assertEqual(late["productionReadiness"]["expiredScenarios"], len(self.catalogue["items"]))

    def test_hard_stop_never_generates(self):
        self.assertEqual(p.run(self.root, self.output, now=p.HARD_STOP + dt.timedelta(seconds=1))["status"], "period_ended")

    def test_retry_reuses_verified_artifact_instead_of_rendering(self):
        self.only(self.scenario["id"])
        with mock.patch.object(p, "render", side_effect=self.fake_render) as render:
            first = p.run(self.root, self.output, now=self.now)
            second = p.run(self.root, self.output, now=self.now)
        self.assertEqual((first["produced"], second["produced"], render.call_count), (1, 0, 1))

    def test_changed_content_cannot_replace_existing_identity(self):
        self.only(self.scenario["id"])
        with mock.patch.object(p, "render", side_effect=self.fake_render):
            p.run(self.root, self.output, now=self.now)
        self.scenario["caption"]["hook"] += " Nouvelle formulation."
        self.save()
        with self.assertRaisesRegex(p.Invalid, "different inputs"):
            p.run(self.root, self.output, now=self.now)

    def test_corrupted_artifact_never_claims_successful_retry(self):
        self.only(self.scenario["id"])
        with mock.patch.object(p, "render", side_effect=self.fake_render):
            p.run(self.root, self.output, now=self.now)
        (self.output / self.scenario["id"] / "reel.mp4").write_bytes(b"changed")
        with self.assertRaisesRegex(p.Invalid, "fingerprint"):
            p.run(self.root, self.output, now=self.now)

    def test_crash_leaves_no_completed_artifact(self):
        with mock.patch.object(p, "render", side_effect=RuntimeError("Interrupted")):
            with self.assertRaisesRegex(RuntimeError, "Interrupted"):
                p.run(self.root, self.output, now=self.now)
        self.assertFalse(any(path.name.startswith((".render-", "ig-", "fb-")) for path in self.output.iterdir()))

    def test_two_simultaneous_jobs_cannot_render_same_directory(self):
        with p.exclusive(self.output):
            with self.assertRaisesRegex(p.Invalid, "already holds"):
                p.run(self.root, self.output, now=self.now)

    def test_offline_package_forbids_path_traversal_and_symlinks(self):
        self.scenario["sources"]["file"] = "../catalogue.json"
        with self.assertRaisesRegex(p.Invalid, "Unsafe file path"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_duplicate_json_fields_rejected(self):
        path = self.root / "duplicate.json"
        path.write_text('{"id": "one", "id": "two"}')
        with self.assertRaisesRegex(p.Invalid, "Duplicate JSON"):
            p.load_json(path)

    def test_video_qa_rejects_high_audio_bitrate(self):
        result = {"streams": [{"codec_type": "video", "width": 1080, "height": 1920, "codec_name": "h264", "pix_fmt": "yuv420p", "r_frame_rate": "30/1"},
                              {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "bit_rate": "161693"}],
                  "format": {"duration": "24"}}
        with mock.patch.object(p, "probe", return_value=result):
            with self.assertRaisesRegex(p.Invalid, "below 128"):
                p.verify_video(Path("not-read.mp4"), 24, True)


class StockAndIntake(unittest.TestCase):
    def test_hashes_match_the_cloud_bundle_on_an_existing_batch(self):
        # Parity with bufferPayloadRevision() and describeStockBatch(): reuse a batch the controller already accepted.
        index = json.loads((p.HERE / "reviewed-social/index.json").read_text())
        entry = next(item for item in index["items"] if item["batchId"] == "facebook-porto-photos-2026-10-12-v1")
        batch = json.loads((p.HERE.parent.parent / entry["path"]).read_text())
        item = batch["items"][0]
        self.assertEqual(social_stock.payload_revision(item["payload"]), item["review"]["payloadRevision"])
        self.assertEqual(social_stock.batch_sha(batch), entry["batchSha256"])

    def test_six_photos_are_a_carousel_on_instagram_and_a_photo_post_on_facebook(self):
        self.assertEqual(social_stock.payload_kind({"kind": "carousel", "channel": "instagram"}), "carousel")
        self.assertEqual(social_stock.payload_kind({"kind": "carousel", "channel": "facebook"}), "photos")
        self.assertEqual(social_stock.payload_kind({"kind": "reel", "channel": "instagram"}), "reel")

    def test_cross_posts_stay_off_until_switched_on(self):
        # The shipped cadence.json: TikTok alone is on (panel deployed and channel seen connected on 2026-11-11).
        self.assertEqual(social_stock.enabled_crossposts(), {"tiktok": dt.timedelta(hours=1)})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cadence.json"
            path.write_text(json.dumps({"crossposts": {"tiktok": {"enabled": True, "delayHours": 1}, "youtube": {"enabled": False}, "snapchat": {"enabled": True}}}))
            self.assertEqual(social_stock.enabled_crossposts(path), {"tiktok": dt.timedelta(hours=1)})

    FAST_REEL = "output/ig-japon-budget-2-semaines-2026-11-15"

    def fast_reel(self):
        folder = p.HERE / self.FAST_REEL
        return folder, json.loads((folder / "scenario.json").read_text())

    def test_a_cross_post_is_the_same_reel_with_its_own_identity_slot_and_caption(self):
        folder, scenario = self.fast_reel()
        main = social_stock.build_batch(scenario, folder, scenario["review"]["checkedAt"])["items"][0]
        for channel, kind in (("tiktok", "reel"), ("youtube", "short"), ("facebook", "reel")):
            batch = social_stock.build_crosspost(scenario, folder, scenario["review"]["checkedAt"], channel, dt.timedelta(hours=2))
            item = batch["items"][0]
            text = item["payload"]["text"]
            self.assertEqual(batch["batchId"], f"{scenario['id']}-{channel}-v1")
            self.assertEqual((item["payload"]["channel"], item["payload"]["kind"]), (channel, kind))
            self.assertEqual(item["payload"]["assets"], main["payload"]["assets"])
            self.assertEqual(p.instant(item["dueAt"]) - p.instant(main["dueAt"]), dt.timedelta(hours=2))
            self.assertNotEqual(item["contentId"], main["contentId"])
            self.assertEqual(item["review"]["contentId"], item["contentId"])
            self.assertEqual(item["review"]["payloadRevision"], social_stock.payload_revision(item["payload"]))
            self.assertNotIn("lien dans la bio", text)
            self.assertNotIn("ce reel", text)
            self.assertIn("crédits : " + p.credits_url(scenario), text)
            if channel != "tiktok":
                self.assertIn("Le guide complet : " + scenario["targetUrl"], text)
        with self.assertRaisesRegex(p.Invalid, "Only an Instagram reel"):
            social_stock.build_crosspost({**scenario, "kind": "carousel"}, folder, scenario["review"]["checkedAt"], "tiktok", dt.timedelta(hours=1))

    def test_tiktok_copy_names_the_site_and_cites_the_tiktok_documentation(self):
        folder, scenario = self.fast_reel()
        main = social_stock.build_batch(scenario, folder, scenario["review"]["checkedAt"])["items"][0]
        item = social_stock.build_crosspost(scenario, folder, scenario["review"]["checkedAt"], "tiktok", dt.timedelta(hours=1))["items"][0]
        text = item["payload"]["text"]
        # Same facts, same credits, same hashtags; only the call to action changes: no clickable link in a TikTok caption.
        self.assertIn("📌 Enregistrez cette vidéo pour votre voyage. 🔗 Prix, horaires et détails : le guide complet sur voyagesansdetour.fr", text)
        self.assertNotIn(scenario["targetUrl"], text)
        self.assertEqual(text.replace(social_stock.CROSSPOSTS["tiktok"]["cta"], scenario["caption"]["cta"]), main["payload"]["text"])
        self.assertLessEqual(len(text), 2200)
        self.assertLessEqual(len(social_stock.HASHTAG.findall(text)), 5)
        self.assertIs(item["payload"]["aiGenerated"], False)
        self.assertEqual(item["review"]["formatCapability"]["sourceUrls"], social_stock.CROSSPOST_DOCS["tiktok"])
        self.assertTrue(any("TikTokPostMetadataInput" in url for url in social_stock.CROSSPOST_DOCS["tiktok"]))
        self.assertEqual(p.instant(item["dueAt"]), p.instant(scenario["publishAt"]) + dt.timedelta(hours=1))

    def test_tiktok_copy_over_tiktok_limits_is_refused(self):
        folder, scenario = self.fast_reel()
        with tempfile.TemporaryDirectory() as temporary:
            copy_ = Path(temporary) / scenario["id"]
            copy_.mkdir()
            for name in ("reel.mp4", "receipt.json"):
                os.link(folder / name, copy_ / name)
            caption = (folder / "legende.txt").read_text()
            (copy_ / "legende.txt").write_text(caption.rstrip("\n") + " #Tokyo #Kyoto\n")
            with self.assertRaisesRegex(p.Invalid, "hashtags"):
                social_stock.build_crosspost(scenario, copy_, scenario["review"]["checkedAt"], "tiktok", dt.timedelta(hours=1))
            # The same caption stays fine where the limit does not exist.
            social_stock.build_crosspost(scenario, copy_, scenario["review"]["checkedAt"], "youtube", dt.timedelta(hours=1))
            (copy_ / "legende.txt").write_text(caption.replace("\n\n📌", "\n" + "x" * 2200 + "\n\n📌"))
            with self.assertRaisesRegex(p.Invalid, "2200"):
                social_stock.build_crosspost(scenario, copy_, scenario["review"]["checkedAt"], "tiktok", dt.timedelta(hours=1))

    def test_an_old_slow_reel_is_not_cross_posted(self):
        folder = p.HERE / "output/ig-vietnam-itineraire-15-jours-2026-11-25"
        scenario = json.loads((folder / "scenario.json").read_text())
        with self.assertRaisesRegex(p.Invalid, "Only a fast reel"):
            social_stock.build_crosspost(scenario, folder, scenario["review"]["checkedAt"], "tiktok", dt.timedelta(hours=1))

    def test_a_reel_queued_before_a_network_was_switched_on_gets_its_copy_later(self):
        folder, scenario = self.fast_reel()
        entry = {"batchId": scenario["id"] + "-v1"}
        index = {"items": [entry], "retirements": []}
        on = {"tiktok": dt.timedelta(hours=1)}
        due = p.instant(scenario["publishAt"])
        early = due - dt.timedelta(days=3)
        batches = social_stock.later_crossposts(scenario, folder, index, on, early)
        self.assertEqual([batch["batchId"] for batch in batches], [scenario["id"] + "-tiktok-v1"])
        admitted = json.loads((social_stock.STOCK / (scenario["id"] + "-v1.json")).read_text())["items"][0]
        self.assertEqual(batches[0]["items"][0]["payload"]["assets"], admitted["payload"]["assets"])
        # Nothing when the network is off, the copy exists, the slot is too close, or the reel was withdrawn or never queued.
        self.assertEqual(social_stock.later_crossposts(scenario, folder, index, {}, early), [])
        twice = {**index, "items": [entry, {"batchId": scenario["id"] + "-tiktok-v1"}]}
        self.assertEqual(social_stock.later_crossposts(scenario, folder, twice, on, early), [])
        self.assertEqual(social_stock.later_crossposts(scenario, folder, index, on, due - dt.timedelta(hours=20)), [])
        retired = {**index, "retirements": [{"batchId": entry["batchId"]}]}
        self.assertEqual(social_stock.later_crossposts(scenario, folder, retired, on, early), [])
        self.assertEqual(social_stock.later_crossposts(scenario, folder, {"items": [], "retirements": []}, on, early), [])
        old = p.HERE / "output/ig-vietnam-itineraire-15-jours-2026-11-25"
        old_scenario = json.loads((old / "scenario.json").read_text())
        old_index = {"items": [{"batchId": old_scenario["id"] + "-v1"}], "retirements": []}
        self.assertEqual(social_stock.later_crossposts(old_scenario, old, old_index, on, p.instant(old_scenario["publishAt"]) - dt.timedelta(days=3)), [])

    def test_a_copy_never_points_to_a_file_other_than_the_one_already_public(self):
        folder, scenario = self.fast_reel()
        index = {"items": [{"batchId": scenario["id"] + "-v1"}], "retirements": []}
        early = p.instant(scenario["publishAt"]) - dt.timedelta(days=3)
        with tempfile.TemporaryDirectory() as temporary:
            stock = Path(temporary)
            admitted = json.loads((social_stock.STOCK / (scenario["id"] + "-v1.json")).read_text())
            admitted["items"][0]["payload"]["assets"][0]["sha256"] = "0" * 64
            (stock / (scenario["id"] + "-v1.json")).write_text(json.dumps(admitted))
            self.assertEqual(social_stock.later_crossposts(scenario, folder, index, {"tiktok": dt.timedelta(hours=1)}, early, stock=stock), [])

    def test_carousel_must_have_six_photos_for_the_site_inventory(self):
        scenario = {"kind": "carousel", "scenes": [{}] * 5}
        with self.assertRaisesRegex(p.Invalid, "exactly six"):
            social_stock.public_files(scenario)

    def test_photo_intake_accepts_only_free_licences(self):
        self.assertEqual(photo_intake.licence_record({"LicenseShortName": {"value": "CC BY-SA 4.0"}})[0], "CC BY-SA 4.0")
        for name in ("CC BY-NC 4.0", "CC BY-ND 4.0", "All rights reserved", ""):
            with self.assertRaises(photo_intake.Refused):
                photo_intake.licence_record({"LicenseShortName": {"value": name}})

    def test_photo_intake_never_upscales(self):
        self.assertEqual(photo_intake.stored_size(6000, 4000), (2400, 1600))
        self.assertEqual(photo_intake.stored_size(1700, 1650), (1648, 1600))
        self.assertEqual(photo_intake.stored_size(1200, 1000), (1200, 1000))

    def test_sealing_is_stable(self):
        scenario = json.loads((p.HERE / "scenarios/fb-sintra-budget-2026-11.json").read_text())
        self.assertEqual(seal_scenarios.seal(scenario), scenario)


if __name__ == "__main__":
    unittest.main()
