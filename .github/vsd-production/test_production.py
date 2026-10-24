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


class ProductionGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "bundle"
        self.root.mkdir()
        for folder in ("assets", "evidence", "scenarios", "sources"):
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
            info = p.validate_scenario(scenario, self.root, self.now)
            size, carousel = (p.draw.SLIDE_SIZE, True) if scenario["kind"] == "carousel" else (p.draw.REEL_SIZE, False)
            self.assertEqual(len(p.prepared_scenes(scenario, self.root, info, size, carousel)), len(scenario["scenes"]))
            kinds.add(scenario["kind"])
        self.assertEqual(kinds, {"reel", "carousel"})

    def test_caption_is_short_and_lively_with_one_credit_line(self):
        for _, _, scenario in p.catalogue_entries(self.root):
            info = p.validate_scenario(scenario, self.root, self.now)
            text = p.caption(scenario, info)
            self.assertTrue(text.startswith(scenario["caption"]["hook"]))
            self.assertLessEqual(len(text), 1000)
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
        reels = sorted(p.instant(s["publishAt"]) for _, _, s in p.catalogue_entries(self.root) if s["channel"] == "instagram")
        self.assertTrue(all(b - a >= dt.timedelta(hours=168) for a, b in zip(reels, reels[1:])), "one Instagram post per 168 h")

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
        with mock.patch.object(p, "render") as render:
            early = p.run(self.root, self.output, now=self.now - dt.timedelta(hours=1))
            late = p.run(self.root, self.output, now=p.instant(self.scenario["review"]["validUntil"]))
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
