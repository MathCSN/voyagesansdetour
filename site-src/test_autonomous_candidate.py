import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import autonomous_candidate as generator


def base_article():
    return {
        "slug": "lisbonne-3-jours-sans-voiture",
        "title": "Lisbonne en 3 jours, sans voiture",
        "shortTitle": "Lisbonne en 3 jours",
        "destination": "Lisbonne",
        "category": "Itinéraires",
        "description": "Un parcours de trois journées à adapter.",
        "readMinutes": 4,
        "summary": "Un secteur par jour et des pauses.",
        "sections": [{"id": "itineraire", "title": "Itinéraire", "paragraphs": ["Un secteur par jour."]}],
        "faq": [{"question": "Combien de jours ?", "answer": "Trois journées complètes."}],
        "sources": [{"label": "Source officielle", "url": "https://example.com/source"}],
        "related": [],
    }


class AutonomousCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vsd-candidate-")
        self.root = Path(self.temp.name)
        (self.root / "editorial-candidates").mkdir()
        (self.root / "articles.json").write_text(json.dumps([base_article()]), encoding="utf-8")
        (self.root / "editorial-queue.json").write_text(
            json.dumps({"schemaVersion": 1, "drafts": [], "promotions": []}), encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_generates_one_source_bound_candidate(self):
        with patch.object(generator.intake, "source_fingerprint", return_value={
            "sha256": "a" * 64, "text": "Official source Lisbonne"
        }):
            result = generator.generate(self.root, generator.dt.datetime(2026, 10, 7, tzinfo=generator.UTC))
        self.assertEqual(result["status"], "generated")
        files = list((self.root / "editorial-candidates").glob("*.json"))
        self.assertEqual(len(files), 1)
        candidate = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertFalse(candidate["review"]["publicationApproved"])
        self.assertFalse(candidate["review"]["fabricatedExperience"])
        self.assertFalse(candidate["review"]["commercialClaims"])
        self.assertEqual(candidate["sources"][0]["sha256"], "a" * 64)
        self.assertIn("mise-a-jour", candidate["article"]["slug"])

    def test_capacity_does_not_write(self):
        for n in range(generator.MAX_PENDING):
            candidate = {"article": {"slug": f"already-{n}"}, "review": {"publicationApproved": False}}
            (self.root / "editorial-candidates" / f"candidate-{n}.json").write_text(json.dumps(candidate), encoding="utf-8")
        with patch.object(generator.intake, "source_fingerprint") as fetch:
            result = generator.generate(self.root, generator.dt.datetime(2026, 10, 7, tzinfo=generator.UTC))
        self.assertEqual(result["status"], "capacity")
        fetch.assert_not_called()

    def test_source_failure_is_closed_without_file(self):
        with patch.object(generator.intake, "source_fingerprint", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                generator.generate(self.root, generator.dt.datetime(2026, 10, 7, tzinfo=generator.UTC))
        self.assertEqual(list((self.root / "editorial-candidates").glob("*.json")), [])

    def test_existing_candidate_advances_the_next_release(self):
        with patch.object(generator.intake, "source_fingerprint", return_value={
            "sha256": "a" * 64, "text": "Official source Lisbonne"
        }):
            first = generator.generate(self.root, generator.dt.datetime(2026, 10, 7, tzinfo=generator.UTC))
            second = generator.generate(self.root, generator.dt.datetime(2026, 10, 8, tzinfo=generator.UTC))
        self.assertEqual(first["status"], "generated")
        self.assertEqual(second["status"], "generated")
        files = sorted((self.root / "editorial-candidates").glob("*.json"))
        self.assertEqual(len(files), 2)
        dates = [json.loads(path.read_text(encoding="utf-8"))["releaseAt"] for path in files]
        self.assertEqual(dates, ["2026-10-21T08:00:00Z", "2026-11-04T08:00:00Z"])


if __name__ == "__main__":
    unittest.main()
