"""Offline tests for auto_social.py: guide pages, Commons and downloads are faked."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from PIL import Image

import auto_social as a
import destinations
import photo_intake
import production as p

HERE = Path(__file__).resolve().parent
NOW = dt.datetime(2026, 11, 2, 5, 17, tzinfo=dt.timezone.utc)  # a Monday
ASSETS = ["assets/dmsans-regular.ttf", "assets/dmsans-bold.ttf", "assets/playfair.ttf", "assets/dmsans-OFL.txt",
          "assets/playfairdisplay-OFL.txt"] + [f"assets/{t}.mp3" for t, _ in a.MUSIC] + [f"evidence/{t}-provenance.json" for t, _ in a.MUSIC]
FACTS = [{"value": "4 h 10", "label": "de train entre Tokyo et Kyoto en Nozomi"},
         {"value": "14 170 ¥", "label": "le billet Nozomi en siège réservé"},
         {"value": "500 ¥", "label": "l’entrée du temple Kiyomizu-dera"},
         {"value": "10 000", "label": "torii rouges sur la colline du Fushimi Inari"},
         {"value": "7 jours", "label": "la durée du Japan Rail Pass le plus vendu"},
         {"value": "2 min", "label": "entre deux trains sur la ligne Yamanote"}]


def guide(slug="kyoto-train", country="japon", **extra):
    article = {"slug": slug, "title": "Kyoto en train depuis Tokyo : Nozomi, temples et torii", "shortTitle": "Kyoto en train",
               "destination": "Kyoto", "country": country, "category": "Itinéraires", "cover": "kyoto-1",
               "description": "Shinkansen, temples et quartiers : Kyoto en deux jours depuis Tokyo, prix 2026.",
               "summary": "Le Nozomi relie Tokyo à Kyoto en un peu plus de deux heures. Comptez deux jours sur place.",
               "keyFacts": FACTS, "publishedOn": "2026-10-30", "updatedOn": "2026-10-30", "sourcesCheckedOn": "2026-10-28",
               "sections": [{"title": "Le train : Nozomi ou Hikari", "image": "kyoto-2", "paragraphs": ["Le Nozomi met 4 h 10 aller-retour."]},
                            {"title": "Jour 1 — Kiyomizu-dera et Gion", "image": "kyoto-3", "paragraphs": ["L’entrée du temple coûte 500 ¥."]},
                            {"title": "Jour 2 — Fushimi Inari", "image": "kyoto-4", "paragraphs": ["Des milliers de torii rouges."]}]}
    return {**article, **extra}


def page(article):
    facts = "".join(f"<div><strong>{f['value']}</strong><span>{f['label']}</span></div>" for f in article.get("keyFacts", []))
    return (f"<html><head><title>{article['title']}</title><script>var x=1;</script></head><body><h1>{article['title']}</h1>"
            f"<p>{article['summary']}</p><section>{facts}</section></body></html>")


class Fixture:
    def __init__(self, articles, photos=6):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root, self.site = base / "prod", base / "site"
        for relative in ASSETS:
            (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HERE / relative, self.root / relative)
        for folder in ("scenarios", "reviewed-social", "assets/photos"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        (self.root / "catalogue.json").write_text(json.dumps({"schemaVersion": 2, "items": []}))
        (self.root / "reviewed-social/index.json").write_text(json.dumps({"schemaVersion": 1, "items": []}))
        self.site.mkdir()
        (self.site / "articles.json").write_text(json.dumps(articles, ensure_ascii=False))
        site_photos = [{"id": f"kyoto-{n}", "source_page": f"https://commons.wikimedia.org/wiki/File:Kyoto_{n}.jpg",
                        "author": f"Photographe {n}", "license": "CC BY 4.0", "alt_fr": f"Kyoto, vue {n}."} for n in range(1, photos + 1)]
        (self.site / "image-sources.json").write_text(json.dumps({"photos": site_photos}, ensure_ascii=False))
        self.pages = {a.guide_url(article): page(article) for article in articles}
        self.downloads = []

    def fetch(self, url):
        if url not in self.pages:
            raise OSError("HTTP Error 404")
        return self.pages[url]

    def download(self, photo_id, title):
        self.downloads.append(title)
        folder = self.root / a.AUTO_PHOTOS
        folder.mkdir(parents=True, exist_ok=True)
        shade = int(hashlib.sha1(title.encode()).hexdigest()[:2], 16)
        Image.new("RGB", (2400, 1600), (shade, 120, 200 - shade // 2)).save(folder / f"{photo_id}.jpg", quality=80)
        raw = (folder / f"{photo_id}.jpg").read_bytes()
        return {"file": f"{a.AUTO_PHOTOS}/{photo_id}.jpg", "sha256": hashlib.sha256(raw).hexdigest(), "width": 2400, "height": 1600,
                "commonsTitle": title, "sourcePage": "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"),
                "author": "Auteur Commons", "licence": "CC BY-SA 4.0", "licenceUrl": photo_intake.LICENCES["CC BY-SA 4.0"],
                "commonsSha1": hashlib.sha1(title.encode()).hexdigest(), "retrievedAt": p.stamp(NOW)}

    def run(self, now=NOW, **kwargs):
        options = {"fetcher": self.fetch, "searcher": lambda query: [], "downloader": self.download, **kwargs}
        return a.generate(self.root, self.site, now, **options)

    def scenario(self, identity):
        return json.loads((self.root / "scenarios" / f"{identity}.json").read_text())

    def cleanup(self):
        self.temp.cleanup()


class GeneratorTests(unittest.TestCase):
    def fixture(self, articles=None, **kwargs):
        fixture = Fixture(articles or [guide()], **kwargs)
        self.addCleanup(fixture.cleanup)
        return fixture

    def test_a_new_guide_from_any_country_yields_a_reel_and_a_photo_post_that_pass_every_guard(self):
        f = self.fixture()
        result = f.run(limit=2)
        self.assertEqual([c["channel"] for c in result["created"]], ["instagram", "facebook"])
        reel, photos = (f.scenario(c["id"]) for c in result["created"])
        self.assertEqual((reel["kind"], photos["kind"]), ("reel", "carousel"))
        self.assertEqual(reel["targetUrl"], "https://voyagesansdetour.fr/japon/kyoto-train/")
        self.assertEqual(len(photos["scenes"]), 6)
        for scenario in (reel, photos):
            a.qualify(f.root, scenario, NOW)  # production.py's own guards and layout
            self.assertEqual(len({s["photo"] for s in scenario["scenes"]}), len(scenario["scenes"]))
            self.assertTrue(all(s.get("facts") for s in scenario["scenes"][:-1]))
            self.assertIn("Japon · Kyoto", scenario["scenes"][0]["kicker"])
            tags = scenario["caption"]["hashtags"]
            self.assertLessEqual(len(tags), 5)
            self.assertNotIn("#VoyageSansVoiture", tags)
            self.assertEqual(tags[:3], ["#Kyoto", "#Japon", "#VoyageJapon"])
        catalogue = json.loads((f.root / "catalogue.json").read_text())
        self.assertEqual({i["contentId"] for i in catalogue["items"]}, {c["id"] for c in result["created"]})

    def test_figures_are_quoted_word_for_word_from_the_dated_page_snapshot(self):
        f = self.fixture()
        identity = f.run(limit=1)["created"][0]["id"]
        snapshot = (f.root / a.AUTO / identity / "guide.txt").read_text()
        self.assertEqual(snapshot.splitlines()[0], "https://voyagesansdetour.fr/japon/kyoto-train/")
        self.assertNotIn("var x", snapshot)
        values = {fact["value"] for fact in FACTS}
        for scene in f.scenario(identity)["scenes"][1:-1]:
            self.assertIn(p.normalized(scene["facts"][0]["excerpt"]), p.normalized(snapshot))
            self.assertIn(scene["headline"][0].strip("*"), values)
            self.assertTrue(scene["facts"][0]["excerpt"].startswith(scene["headline"][0].strip("*")))

    def test_slots_follow_the_cadence_after_the_queue(self):
        f = self.fixture([guide(f"guide-{n}", title=f"Guide {n} : Kyoto") for n in range(4)])
        result = f.run(limit=20)
        due = {name: [p.instant(c["publishAt"]) for c in result["created"] if c["channel"] == name] for name in ("instagram", "facebook")}
        self.assertTrue(all(d.weekday() == 2 and d.hour == 17 for d in due["instagram"]))
        self.assertTrue(all(d.weekday() in (3, 6) for d in due["facebook"]))
        self.assertTrue(all(b - a_ >= dt.timedelta(days=3) for a_, b in zip(due["facebook"], due["facebook"][1:])))
        self.assertGreaterEqual(min(due["instagram"]), NOW + a.MIN_LEAD)
        self.assertLessEqual(max(due["instagram"] + due["facebook"]), NOW + a.MAX_LEAD)

    def test_a_covered_queue_creates_nothing_and_existing_posts_are_never_rewritten(self):
        f = self.fixture([guide(f"guide-{n}", title=f"Guide {n} : Kyoto") for n in range(10)])
        first = f.run(limit=20)
        self.assertTrue(first["created"])
        snapshot = {path: path.read_bytes() for path in f.root.rglob("*") if path.is_file()}
        again = f.run(limit=20)
        self.assertEqual((again["created"], again["status"]), ([], "queue_covered"))
        self.assertEqual({path: path.read_bytes() for path in f.root.rglob("*") if path.is_file()}, snapshot)

    def test_the_queue_is_topped_up_to_three_weeks_newest_guide_first(self):
        articles = [guide(f"guide-{n}", title=f"Guide {n} : Kyoto", publishedOn=f"2026-10-{10 + n}") for n in range(10)]
        f = self.fixture(articles)
        result = f.run(limit=20)
        self.assertEqual(result["shortChannels"], [])
        for channel in ("instagram", "facebook"):
            self.assertGreaterEqual(p.instant(result["coveredUntil"][channel]), NOW + a.HORIZON)
        self.assertEqual(result["created"][0]["guide"], "https://voyagesansdetour.fr/japon/guide-9/")

    def test_queued_batches_count_as_taken_slots(self):
        f = self.fixture()
        batch = {"items": [{"dueAt": "2026-11-25T17:00:00Z", "payload": {"channel": "instagram"},
                            "review": {"destination": {"url": "https://voyagesansdetour.fr/portugal/x/"}}}]}
        (f.root / "reviewed-social/old-v1.json").write_text(json.dumps(batch))
        (f.root / "reviewed-social/index.json").write_text(json.dumps({"schemaVersion": 1, "items": [{"path": ".github/vsd-production/reviewed-social/old-v1.json", "batchId": "old-v1"}]}))
        result = f.run(limit=2)
        self.assertEqual([c["channel"] for c in result["created"]], ["facebook"])  # Instagram covered until 25/11

    def test_an_unpublished_guide_is_held_without_any_file(self):
        f = self.fixture()
        f.pages = {}
        result = f.run()
        self.assertEqual(result["created"], [])
        self.assertEqual({h["reason"] for h in result["held"]}, {"guide_unavailable"})
        self.assertEqual(result["status"], "queue_short")
        self.assertFalse((f.root / a.AUTO).exists())

    def test_figures_missing_from_the_live_page_are_never_used(self):
        f = self.fixture()
        f.pages = {url: html.replace("14 170 ¥", "14 000 ¥") for url, html in f.pages.items()}
        reel = f.scenario(f.run(limit=1)["created"][0]["id"])
        self.assertNotIn("*14 170 ¥*", [s["headline"][0] for s in reel["scenes"]])

    def test_guide_with_stale_sources_is_held(self):
        f = self.fixture([guide(sourcesCheckedOn="2026-08-01")])
        result = f.run()
        self.assertEqual(result["created"], [])
        self.assertEqual(result["held"][0]["reason"], "guide_sources_older_than_45_days")

    def test_too_few_photos_holds_the_photo_post_but_not_the_reel(self):
        f = self.fixture(photos=5)
        result = f.run(limit=2)
        self.assertEqual([c["channel"] for c in result["created"]], ["instagram"])
        self.assertIn({"slug": "kyoto-train", "channel": "facebook", "reason": "not_enough_photos_or_figures"}, result["held"])

    def test_featured_pictures_complete_the_guide_photos_only_when_they_name_the_place(self):
        f = self.fixture(photos=5)
        hits = ["File:Paris night.jpg", "File:Kyoto Kinkaku-ji in autumn.jpg"]
        result = f.run(limit=2, searcher=lambda query: hits if "Featured_pictures" in query else [])
        self.assertEqual([c["channel"] for c in result["created"]], ["instagram", "facebook"])
        self.assertNotIn("File:Paris night.jpg", f.downloads)
        self.assertIn("File:Kyoto Kinkaku-ji in autumn.jpg", f.downloads)

    def test_site_author_name_replaces_commons_free_text(self):
        f = self.fixture()
        identity = f.run(limit=1)["created"][0]["id"]
        records = json.loads((f.root / a.AUTO / identity / "photos.json").read_text())["photos"]
        self.assertEqual(records["kyoto-1"]["author"], "Photographe 1")

    def test_photos_are_downloaded_once_and_reused_by_later_posts(self):
        f = self.fixture()
        f.run(limit=2)
        self.assertEqual(len(f.downloads), len(set(f.downloads)))

    def test_photo_whose_caption_names_a_closed_lift_is_skipped(self):
        f = self.fixture(photos=7)
        sources = json.loads((f.site / "image-sources.json").read_text())
        sources["photos"][1]["alt_fr"] = "L’ascenseur de Santa Justa."
        (f.site / "image-sources.json").write_text(json.dumps(sources, ensure_ascii=False))
        for c in f.run(limit=2)["created"]:
            self.assertNotIn("kyoto-2", [s["photo"] for s in f.scenario(c["id"])["scenes"]])

    def test_a_guide_is_reposted_only_after_the_cooldown_with_another_angle(self):
        f = self.fixture()
        first = f.run(limit=1)["created"][0]
        reels = lambda result: [c for c in result["created"] if c["channel"] == "instagram"]
        self.assertEqual(reels(f.run(NOW + dt.timedelta(days=7))), [])  # next Wednesday: too soon for the same guide
        later = p.instant(first["publishAt"]) + a.REPOST_COOLDOWN - a.MIN_LEAD
        (f.site / "articles.json").write_text(json.dumps([guide(sourcesCheckedOn=later.date().isoformat())], ensure_ascii=False))
        second = reels(f.run(later))
        self.assertTrue(second)
        self.assertNotEqual(f.scenario(first["id"])["scenes"][1]["headline"], f.scenario(second[0]["id"])["scenes"][1]["headline"])

    def test_period_end(self):
        f = self.fixture()
        self.assertEqual(f.run(p.HARD_STOP)["status"], "period_ended")


class TextTests(unittest.TestCase):
    def test_figures_stay_on_one_line(self):
        self.assertEqual(a.unbreakable("de 8 h 30 à 9 h 30, dès 9 €, 3 047 azulejos"),
                         "de 8 h 30 à 9 h 30, dès 9 €, 3 047 azulejos")

    def test_kicker_comes_from_the_section_title(self):
        self.assertEqual(a.kicker_of({"title": "Jour 3 — Belém en train"}, "X"), "Jour 3")
        self.assertEqual(a.kicker_of({"title": "La Via dell’Amore et le sentier côtier"}, "X"), "La Via dell’Amore")
        self.assertEqual(a.kicker_of(None, "Kyoto"), "Kyoto")

    def test_figure_is_matched_to_the_section_about_it(self):
        sections = [{"title": "Le train", "paragraphs": ["Un train toutes les 30 minutes."]},
                    {"title": "La Via dell’Amore", "paragraphs": ["De Riomaggiore à Manarola, sur réservation."]}]
        self.assertEqual(a.section_of("30 min", "la Via dell’Amore, de Riomaggiore à Manarola, sur réservation", sections)["title"], "La Via dell’Amore")

    def test_title_lines_are_balanced(self):
        self.assertEqual(a.lines_of("La côte amalfitaine sans voiture", 24), ["La côte amalfitaine", "sans voiture"])
        self.assertIsNone(a.lines_of("Un titre beaucoup trop long pour tenir sur deux lignes étroites", 12))


class DestinationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.site = Path(temp.name)

    def test_without_destinations_file_names_and_prepositions_fall_back(self):
        table = destinations.load(self.site)
        self.assertEqual(destinations.preposition("portugal", table), "au Portugal")
        self.assertEqual(destinations.preposition("italie", table), "en Italie")
        self.assertEqual(destinations.preposition("etats-unis", table), "aux Etats Unis")

    def test_destinations_file_wins_in_both_shapes(self):
        (self.site / "destinations.json").write_text(json.dumps({"countries": {"etats-unis": {"name": "États-Unis", "in": "aux États-Unis"}}}))
        self.assertEqual(destinations.preposition("etats-unis", destinations.load(self.site)), "aux États-Unis")
        (self.site / "destinations.json").write_text(json.dumps([{"slug": "japon", "name": "Japon", "preposition": "au"}]))
        self.assertEqual(destinations.preposition("japon", destinations.load(self.site)), "au Japon")

    def test_site_monde_format_is_read_as_is(self):
        (self.site / "destinations.json").write_text(json.dumps({"schemaVersion": 1,
            "continents": [{"id": "asie", "name": "Asie", "preposition": "en Asie"}],
            "countries": [{"id": "japon", "name": "Japon", "preposition": "au Japon", "continent": "asie", "iso": "JP", "flag": "🇯🇵"}]}, ensure_ascii=False))
        table = destinations.load(self.site)
        self.assertEqual((destinations.name("japon", table), destinations.preposition("japon", table)), ("Japon", "au Japon"))
        self.assertEqual(destinations.preposition("perou", table), "au Perou")  # absent country: fallback

    def test_hashtags_are_five_at_most_without_duplicates(self):
        tags = destinations.hashtags({"destination": "Portugal", "category": "Préparer"}, {})
        self.assertEqual(tags, ["#Portugal", "#VoyagePortugal", "#ConseilsVoyage", "#VoyageSansDetour"])
        tags = destinations.hashtags({"destination": "Côte amalfitaine", "country": "italie", "category": "Transports",
                                      "slug": "naples-ferry"}, {})
        self.assertEqual(tags, ["#CoteAmalfitaine", "#Italie", "#VoyageItalie", "#ConseilsVoyage", "#VoyageSansDetour"])


class PhotoIntakeTests(unittest.TestCase):
    def test_ai_generated_files_are_refused(self):
        self.assertTrue(photo_intake.ai_generated("File:Lisbon.jpg", {"Categories": {"value": "AI-generated images|Lisbon"}}))
        self.assertTrue(photo_intake.ai_generated("File:Kyoto made with Midjourney.jpg", {}))
        self.assertTrue(photo_intake.ai_generated("File:X.jpg", {"ImageDescription": {"value": "Created with Stable Diffusion"}}))
        self.assertFalse(photo_intake.ai_generated("File:Manarola.jpg", {"Categories": {"value": "Manarola|Featured pictures"}}))

    def test_public_credit_is_short_and_never_an_email(self):
        meta = {"Attribution": {"value": "This Photo was taken by Jane Doe. Feel free to use my photos, but please mention me as the author. Write to jane@example.org or on my talk page"},
                "Artist": {"value": "<a href='//commons.wikimedia.org/wiki/User:Jane'>Jane Doe</a>"}}
        self.assertEqual(photo_intake.credited_author(meta), "Jane Doe")
        self.assertEqual(photo_intake.credited_author({"Artist": {"value": "I, Alvesgaspar"}}), "Alvesgaspar")
        long_request = "This Photo was taken by Timothy A. Gonsalves . Feel free to use my photos, but please mention me as the author. I would much appreciate if you send me an email tagooty@yahoo.com"
        self.assertEqual(photo_intake.credited_author({"Artist": {"value": long_request}}), "Timothy A. Gonsalves")
        self.assertEqual(photo_intake.credited_author({"Artist": {"value": "x" * 300}, "Credit": {"value": "Own work"}}, "Tagooty"), "Tagooty")
        self.assertEqual(photo_intake.credited_author({"Artist": {"value": "Photo by Paolo Costa Baldi. License: GFDL/CC-BY-SA 3.0"}}), "Paolo Costa Baldi")


if __name__ == "__main__":
    unittest.main()
