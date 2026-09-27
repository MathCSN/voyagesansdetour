import copy
import datetime as dt
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import production as p


class ProductionGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "bundle"
        self.root.mkdir()
        for folder in ("assets", "evidence", "scenarios"):
            shutil.copytree(p.HERE / folder, self.root / folder)
        shutil.copyfile(p.HERE / "catalogue.json", self.root / "catalogue.json")
        self.scenario_file = self.root / "scenarios/porto-aeroport-trois-reflexes.json"
        self.scenario = p.load_json(self.scenario_file)
        self.now = p.instant(self.scenario["review"]["checkedAt"]) + dt.timedelta(seconds=1)
        clock = mock.patch.object(p, "utcnow", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.output = Path(self.temporary.name) / "output"

    def save(self):
        p.write_json(self.scenario_file, self.scenario)
        catalogue = p.load_json(self.root / "catalogue.json")
        catalogue["items"][0]["sha256"] = p.digest(self.scenario_file.read_bytes())
        p.write_json(self.root / "catalogue.json", catalogue)

    def fake_render(self, scenario, root, destination, now, info):
        # Fixture is only for crash/retry semantics; it never asserts media QA.
        (destination / "sentinel.bin").write_bytes(b"test-artifact")
        receipt = {"status": "rendered_not_published", "fingerprint": p.fingerprint(scenario), "runtime": {"wallSeconds": 0},
                   "files": [{"file": "sentinel.bin", "sha256": p.digest(b"test-artifact")}, {"file": "reel.mp4", "sha256": p.digest(b"test-video")}]}
        (destination / "reel.mp4").write_bytes(b"test-video")
        p.write_json(destination / "receipt.json", receipt)
        return receipt

    def test_real_snapshot_has_current_evidence_and_layout_fits(self):
        info = p.validate_scenario(self.scenario, self.root, self.now)
        self.assertEqual(info["duration"], 28)
        for i, scene in enumerate(self.scenario["scenes"]):
            im, _ = p.build_scene(self.scenario, scene, i, self.root)
            self.assertEqual(im.size, (1080, 1920))
        self.assertIn("CC BY 4.0", p.caption(self.scenario, info))
        self.assertLessEqual(len(p.caption(self.scenario, info)), 2200)

    def test_wrong_article_bytes_cannot_render(self):
        path = self.root / self.scenario["source"]["article"]["file"]
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(p.Invalid, "fingerprint"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_mutated_scenario_without_new_catalogue_review_stops(self):
        self.scenario["scenes"][0]["title"][0] = "Rome."
        p.write_json(self.scenario_file, self.scenario)
        with self.assertRaisesRegex(p.Invalid, "fingerprint"):
            p.run(self.root, self.output, now=self.now)

    def test_expired_content_does_not_invoke_renderer(self):
        with mock.patch.object(p, "render") as render:
            result = p.run(self.root, self.output, now=p.instant("2026-10-28T00:00:00Z"))
        render.assert_not_called()
        self.assertEqual(result["skipped"][0]["reason"], "review_expired")

    def test_future_content_does_not_invoke_renderer(self):
        with mock.patch.object(p, "render") as render:
            result = p.run(self.root, self.output, now=self.now - dt.timedelta(days=1))
        render.assert_not_called()
        self.assertEqual(result["skipped"][0]["reason"], "not_due")

    def test_hard_stop_never_generates(self):
        with mock.patch.object(p, "render") as render:
            result = p.run(self.root, self.output, now=p.HARD_STOP + dt.timedelta(seconds=1))
        render.assert_not_called()
        self.assertEqual(result["status"], "period_ended")

    def test_source_expiry_cannot_be_extended_by_changing_only_review(self):
        self.scenario["review"]["checkedAt"] = "2026-10-20T10:00:00Z"
        self.scenario["review"]["validUntil"] = "2026-11-01T10:00:00Z"
        with self.assertRaisesRegex(p.Invalid, "source review window"):
            p.validate_scenario(self.scenario, self.root, p.instant("2026-10-21T10:00:00Z"))

    def test_audio_bytes_and_rights_are_bound(self):
        self.scenario["assets"]["music"]["commercialUseAllowed"] = False
        with self.assertRaisesRegex(p.Invalid, "rights"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_music_attribution_cannot_be_substituted(self):
        self.scenario["assets"]["music"]["author"] = "Someone else"
        with self.assertRaisesRegex(p.Invalid, "attribution"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_invented_evidence_excerpt_stops(self):
        self.scenario["scenes"][2]["evidence"][0]["supportingText"] = "The card can be shared."
        with self.assertRaisesRegex(p.Invalid, "excerpt"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_missing_scene_evidence_stops(self):
        self.scenario["scenes"][2]["evidence"] = []
        with self.assertRaisesRegex(p.Invalid, "Each scene"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_unpublished_source_guide_stops(self):
        self.scenario["targetUrl"] = "https://voyagesansdetour.fr/portugal/something-else/"
        with self.assertRaisesRegex(p.Invalid, "target mismatch"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_offline_package_forbids_path_traversal_and_symlinks(self):
        with self.assertRaises(p.Invalid):
            p.safe_path(self.root, "../outside.json")
        with self.assertRaises(p.Invalid):
            p.safe_path(self.root, "/tmp/outside.json")
        (self.root / "redirect.json").symlink_to(self.scenario_file)
        with self.assertRaisesRegex(p.Invalid, "Symlink"):
            p.safe_path(self.root, "redirect.json")

    def test_missing_ai_disclosure_and_presenter_cannot_slip_in(self):
        self.scenario["aiAssisted"] = False
        with self.assertRaisesRegex(p.Invalid, "disclosure"):
            p.validate_scenario(self.scenario, self.root, self.now)
        self.scenario["aiAssisted"] = True
        self.scenario["presenter"] = "alma"
        with self.assertRaisesRegex(p.Invalid, "Presenter"):
            p.validate_scenario(self.scenario, self.root, self.now)

    def test_layout_overflow_stops_before_encoding(self):
        self.scenario["scenes"][0]["title"] = ["W" * 26]
        with self.assertRaisesRegex(p.Invalid, "Layout overflow"):
            p.build_scene(self.scenario, self.scenario["scenes"][0], 0, self.root)

    def test_silent_format_has_no_implicit_music_or_voice(self):
        self.scenario["format"] = "silent_text"
        del self.scenario["assets"]["music"]
        info = p.validate_scenario(self.scenario, self.root, self.now)
        self.assertNotIn("Almost Bliss", p.caption(self.scenario, info))
        self.assertEqual(self.scenario["presenter"], "none")

    def test_retry_reuses_verified_artifact_instead_of_rendering(self):
        with mock.patch.object(p, "render", side_effect=self.fake_render) as render:
            first = p.run(self.root, self.output, now=self.now)
            second = p.run(self.root, self.output, now=self.now)
        self.assertEqual(first["produced"], 1)
        self.assertEqual(second["produced"], 0)
        self.assertEqual(render.call_count, 1)

    def test_changed_content_cannot_replace_existing_identity(self):
        with mock.patch.object(p, "render", side_effect=self.fake_render):
            p.run(self.root, self.output, now=self.now)
        self.scenario["caption"] += "\nNouvelle formulation."
        self.save()
        with self.assertRaisesRegex(p.Invalid, "different inputs"):
            p.run(self.root, self.output, now=self.now)

    def test_corrupted_artifact_never_claims_successful_retry(self):
        with mock.patch.object(p, "render", side_effect=self.fake_render):
            p.run(self.root, self.output, now=self.now)
        (self.output / self.scenario["id"] / "reel.mp4").write_bytes(b"changed")
        with self.assertRaisesRegex(p.Invalid, "fingerprint"):
            p.run(self.root, self.output, now=self.now)

    def test_crash_leaves_no_completed_artifact(self):
        with mock.patch.object(p, "render", side_effect=RuntimeError("Interrupted")):
            with self.assertRaisesRegex(RuntimeError, "Interrupted"):
                p.run(self.root, self.output, now=self.now)
        self.assertFalse((self.output / self.scenario["id"]).exists())
        self.assertFalse(any(pth.name.startswith(".render-") for pth in self.output.iterdir()))

    def test_two_simultaneous_jobs_cannot_render_same_directory(self):
        with p.exclusive(self.output):
            with self.assertRaisesRegex(p.Invalid, "already holds"):
                p.run(self.root, self.output, now=self.now)

    def test_duplicate_json_fields_rejected(self):
        path = self.root / "duplicate.json"
        path.write_text('{"id": "one", "id": "two"}')
        with self.assertRaisesRegex(p.Invalid, "Duplicate JSON"):
            p.load_json(path)


if __name__ == "__main__":
    unittest.main()
