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
            candidate = {"id":f"pending-{n}", "releaseAt":"2026-12-01T08:00:00Z", "validUntil":"2026-12-02T08:00:00Z",
                         "article": {"slug": f"already-{n}"}, "review": {"publicationApproved": False}}
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

    def test_same_subject_does_not_generate_another_dated_copy(self):
        with patch.object(generator.intake, "source_fingerprint", return_value={
            "sha256": "a" * 64, "text": "Official source Lisbonne"
        }):
            first = generator.generate(self.root, generator.dt.datetime(2026, 10, 7, tzinfo=generator.UTC))
            second = generator.generate(self.root, generator.dt.datetime(2026, 10, 8, tzinfo=generator.UTC))
        self.assertEqual(first["status"], "generated")
        self.assertEqual(second["status"], "subjects_covered")
        files = sorted((self.root / "editorial-candidates").glob("*.json"))
        self.assertEqual(len(files), 1)
        dates = [json.loads(path.read_text(encoding="utf-8"))["releaseAt"] for path in files]
        self.assertEqual(dates, ["2026-10-21T08:00:00Z"])

    def test_admitted_candidate_does_not_consume_capacity_twice(self):
        state = {"schemaVersion": 1, "drafts": [{"id": "admitted-0", "releaseAt": "2026-12-01T08:00:00Z", "validUntil":"2026-12-02T08:00:00Z", "article":{"slug":"admitted-article"}}], "promotions": []}
        (self.root / "editorial-queue.json").write_text(json.dumps(state), encoding="utf-8")
        for n in range(6):
            candidate = {"id": f"pending-{n}", "releaseAt":"2026-12-01T08:00:00Z", "validUntil":"2026-12-02T08:00:00Z", "article": {"slug": f"already-{n}"}, "review": {"publicationApproved": False}}
            (self.root / "editorial-candidates" / f"candidate-{n}.json").write_text(json.dumps(candidate), encoding="utf-8")
        admitted = {"id": "admitted-0", "releaseAt":"2026-12-01T08:00:00Z", "validUntil":"2026-12-02T08:00:00Z", "article": {"slug": "already-admitted"}, "review": {"publicationApproved": False}}
        (self.root / "editorial-candidates" / "admitted.json").write_text(json.dumps(admitted), encoding="utf-8")
        with patch.object(generator.intake, "source_fingerprint", return_value={
            "sha256": "a" * 64, "text": "Official source Lisbonne"
        }):
            result = generator.generate(self.root, generator.dt.datetime(2026, 10, 7, tzinfo=generator.UTC))
        self.assertEqual(result["status"], "generated")

    def test_skips_a_published_guide_with_a_non_html_source(self):
        second = copy.deepcopy(base_article())
        second["slug"] = "porto-verification"
        second["title"] = "Porto à vérifier"
        second["shortTitle"] = "Porto à vérifier"
        second["destination"] = "Porto"
        second["sources"] = [{"label": "Source officielle", "url": "https://example.com/porto"}]
        (self.root / "articles.json").write_text(json.dumps([base_article(), second]), encoding="utf-8")
        with patch.object(generator.intake, "source_fingerprint", side_effect=[
            ValueError("La source ne renvoie pas du HTML."),
            {"sha256": "a" * 64, "text": "Official source Porto"},
        ]):
            result = generator.generate(self.root, generator.dt.datetime(2026, 10, 7, tzinfo=generator.UTC))
        self.assertEqual(result["status"], "generated")
        self.assertIn("porto-verification", result["id"])

    def test_missed_candidates_do_not_fill_capacity_and_are_never_redated(self):
        directory = self.root / 'editorial-candidates'
        for n in range(generator.MAX_PENDING):
            candidate = {'id':f'expired-{n}', 'releaseAt':'2026-10-01T08:00:00Z',
                         'validUntil':'2026-11-01T08:00:00Z',
                         'article':{'slug':f'expired-{n}'},'review':{'publicationApproved':False}}
            (directory / f'expired-{n}.json').write_text(json.dumps(candidate))
        before = {p.name:p.read_bytes() for p in directory.glob('*.json')}
        with patch.object(generator.intake, 'source_fingerprint', return_value={'sha256':'a'*64,'text':'Official source Lisbonne'}):
            result = generator.generate(self.root, generator.dt.datetime(2026,10,7,tzinfo=generator.UTC))
        self.assertEqual(result['status'],'generated')
        for name, data in before.items():
            self.assertEqual((directory/name).read_bytes(),data)
        self.assertEqual(result['releaseAt'],'2026-10-21T08:00:00Z')

    def test_no_release_or_expiry_outside_authorised_period(self):
        with patch.object(generator.intake, 'source_fingerprint') as fetch:
            result=generator.generate(self.root,generator.dt.datetime(2027,9,2,tzinfo=generator.UTC))
        self.assertEqual(result['status'],'period_complete')
        fetch.assert_not_called()
        self.assertEqual(list((self.root/'editorial-candidates').glob('*.json')),[])
        with patch.object(generator.intake, 'source_fingerprint', return_value={'sha256':'a'*64,'text':'Official source Lisbonne'}):
            result=generator.generate(self.root,generator.dt.datetime(2027,8,30,tzinfo=generator.UTC))
        self.assertEqual(result['status'],'generated')
        candidate=json.loads(next((self.root/'editorial-candidates').glob('*.json')).read_text())
        self.assertEqual(candidate['validUntil'],generator.iso(generator.HARD_STOP))

    def test_published_checklist_cannot_be_repeated_or_used_as_a_new_source_guide(self):
        original=base_article()
        checklist=generator.make_article(original,'2026-10-01','2026-09-20')
        (self.root/'articles.json').write_text(json.dumps([original,checklist]))
        with patch.object(generator.intake,'source_fingerprint') as fetch:
            result=generator.generate(self.root,generator.dt.datetime(2026,10,7,tzinfo=generator.UTC))
        self.assertEqual(result['status'],'subjects_covered')
        fetch.assert_not_called()

    def test_another_guide_gets_its_own_slot_without_rewriting_first_candidate(self):
        with patch.object(generator.intake, 'source_fingerprint', return_value={'sha256':'a'*64,'text':'Official source Lisbonne'}):
            first=generator.generate(self.root,generator.dt.datetime(2026,10,7,tzinfo=generator.UTC))
            first_path=next((self.root/'editorial-candidates').glob('*.json'))
            before=first_path.read_bytes()
            porto=base_article();porto.update(slug='porto-guide',shortTitle='Porto',title='Porto en trois jours')
            (self.root/'articles.json').write_text(json.dumps([base_article(),porto]))
            second=generator.generate(self.root,generator.dt.datetime(2026,10,8,tzinfo=generator.UTC))
        self.assertEqual(second['status'],'generated')
        self.assertIn('porto-guide',second['id'])
        self.assertEqual(second['releaseAt'],'2026-11-04T08:00:00Z')
        self.assertEqual(first_path.read_bytes(),before)


if __name__ == "__main__":
    unittest.main()
