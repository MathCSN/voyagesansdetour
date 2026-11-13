"""Offline tests for auto_social.py: guide pages, Commons and downloads are faked."""
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from PIL import Image

import auto_social as a
import clip_intake
import destinations
import media_library
import motion_render
import photo_intake
import production as p
import reel_formats

HERE = Path(__file__).resolve().parent
NOW = dt.datetime(2026, 11, 2, 5, 17, tzinfo=dt.timezone.utc)  # a Monday
ASSETS = ["assets/dmsans-regular.ttf", "assets/dmsans-bold.ttf", "assets/playfair.ttf", "assets/dmsans-OFL.txt",
          "assets/playfairdisplay-OFL.txt", "assets/notosans-regular.ttf", "assets/notosans-bold.ttf", "assets/notosans-OFL.txt"]
ASSETS += [f"assets/{t}.mp3" for t, _ in a.MUSIC] + [f"evidence/{t}-provenance.json" for t, _ in a.MUSIC]
PARIS = ZoneInfo("Europe/Paris")
FACTS = [{"value": "4 h 10", "label": "de train entre Tokyo et Kyoto en Nozomi"},
         {"value": "14 170 ¥", "label": "le billet Nozomi en siège réservé"},
         {"value": "500 ¥", "label": "l’entrée du temple Kiyomizu-dera"},
         {"value": "10 000", "label": "torii rouges sur la colline du Fushimi Inari"},
         {"value": "7 jours", "label": "la durée du Japan Rail Pass le plus vendu"},
         {"value": "2 min", "label": "entre deux trains sur la ligne Yamanote"}]
SECTIONS = [{"title": "Le train : Nozomi ou Hikari", "image": "kyoto-2", "paragraphs": ["Le Nozomi met 4 h 10 aller-retour."]},
            {"title": "Avant de partir", "paragraphs": ["L’entrée du temple coûte 500 ¥."]},
            {"title": "Les torii", "paragraphs": ["Des milliers de torii rouges."]}]
DAYS = [{"title": "Jour 1 — Kiyomizu-dera, le temple sur pilotis", "image": "kyoto-3", "paragraphs": ["L’entrée du temple coûte 500 ¥."]},
        {"title": "Jour 2 — Fushimi Inari et ses torii", "image": "kyoto-4", "paragraphs": ["Des milliers de torii rouges."]},
        {"title": "Jour 3 — Arashiyama", "image": "kyoto-5", "paragraphs": ["La bambouseraie."]},
        {"title": "Jour 4 — Osaka", "paragraphs": ["Une ville sans photo dans ce guide."]}]
GION = {"title": "Jour 6 — Gion et ses ruelles", "image": "kyoto-7", "paragraphs": ["Le quartier des maisons de thé."]}
LANES = {"value": "30 min", "label": "de marche dans les ruelles de Gion"}
TABLE = {"title": "En bref", "table": {"headers": ["Votre envie", "Les meilleurs mois", "À savoir"],
                                        "rows": [["Cerisiers en fleurs", "Fin mars à début avril", "Réservez tôt"],
                                                 ["Érables rouges", "Mi-novembre", "Temples illuminés le soir"],
                                                 ["Moins de monde", "Janvier et février", "Froid sec"]]}}


# What the photos of the guide show, as the site says it: a fact that names a place only goes over the photo of that place.
CAPTIONS = {2: "Un shinkansen Nozomi à quai.", 3: "Le temple Kiyomizu-dera sur ses pilotis.", 4: "Les torii rouges du Fushimi Inari.",
            5: "La bambouseraie d’Arashiyama.", 7: "Une ruelle de Gion et ses maisons de thé."}


def guide(slug="kyoto-train", country="japon", **extra):
    article = {"slug": slug, "title": "Kyoto en train depuis Tokyo : Nozomi, temples et torii", "shortTitle": "Kyoto en train",
               "destination": "Kyoto", "country": country, "category": "Transports", "cover": "kyoto-1",
               "description": "Shinkansen, temples et quartiers : Kyoto en deux jours depuis Tokyo, prix 2026.",
               "summary": "Le Nozomi relie Tokyo à Kyoto en un peu plus de deux heures. Comptez deux jours sur place.",
               "keyFacts": FACTS, "publishedOn": "2026-10-30", "updatedOn": "2026-10-30", "sourcesCheckedOn": "2026-10-28",
               "sections": SECTIONS}
    return {**article, **extra}


def page(article):
    facts = "".join(f"<div><strong>{f['value']}</strong><span>{f['label']}</span></div>" for f in article.get("keyFacts", []))
    sections = ""
    for section in article.get("sections", []):
        table = section.get("table") or {"headers": [], "rows": []}
        cells = "".join(f"<th>{h}</th>" for h in table["headers"]) + "".join(f"<td>{c}</td>" for row in table["rows"] for c in row)
        sections += f"<h2>{section['title']}</h2><table>{cells}</table>"
    return (f"<html><head><title>{article['title']}</title><script>var x=1;</script></head><body><h1>{article['title']}</h1>"
            f"<p>{article['summary']}</p><section>{facts}</section>{sections}</body></html>")


class Fixture:
    def __init__(self, articles, photos=8, cadence=None):
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
        if cadence:
            (self.root / a.CADENCE_FILE).write_text(json.dumps(cadence))
        self.site.mkdir()
        (self.site / "articles.json").write_text(json.dumps(articles, ensure_ascii=False))
        site_photos = [{"id": f"kyoto-{n}", "source_page": f"https://commons.wikimedia.org/wiki/File:Kyoto_{n}.jpg",
                        "author": f"Photographe {n}", "license": "CC BY 4.0", "alt_fr": CAPTIONS.get(n, f"Kyoto, vue {n}.")} for n in range(1, photos + 1)]
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
                "commonsSha1": hashlib.sha1(title.encode()).hexdigest(), "retrievedAt": p.stamp(NOW),
                **({} if "no camera" in title else {"camera": "FUJIFILM X-T4"}),
                "categories": "Bonn|United Nations" if "elsewhere" in title else "Featured pictures of Japan|Kyoto"}

    def clip(self, clip_id, candidate):
        folder = self.root / clip_intake.CLIPS
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{clip_id}.mp4").write_bytes(b"real-plan:" + candidate["sourcePage"].encode())
        record = {key: candidate[key] for key in ("provider", "title", "sourcePage", "author", "licence", "licenceUrl")}
        return {"file": f"{clip_intake.CLIPS}/{clip_id}.mp4", "sha256": hashlib.sha256((folder / f"{clip_id}.mp4").read_bytes()).hexdigest(),
                **record, "start": 12.0, "seconds": clip_intake.CLIP_SECONDS, "retrievedAt": p.stamp(NOW)}

    def run(self, now=NOW, **kwargs):
        options = {"fetcher": self.fetch, "searcher": lambda query: [], "downloader": self.download, "clip_downloader": self.clip, **kwargs}
        # Layout is checked without decoding any video: a clip is one grey frame here.
        with mock.patch.object(motion_render, "clip_frames", lambda path, count: iter([Image.new("RGB", motion_render.SIZE, (90, 90, 90))] * count)):
            return a.generate(self.root, self.site, now, **options)

    def scenario(self, identity):
        return json.loads((self.root / "scenarios" / f"{identity}.json").read_text())

    def cleanup(self):
        self.temp.cleanup()


def pexels(place="Kyoto", **extra):
    return {"provider": "pexels", "title": "kyoto-street-at-dusk-123", "stream": "https://videos.pexels.com/x.mp4", "duration": 14.0,
            "sourcePage": "https://www.pexels.com/video/kyoto-street-at-dusk-123/", "author": "Aiko Tanaka",
            "licence": clip_intake.PEXELS_LICENCE, "licenceUrl": clip_intake.LICENCES[clip_intake.PEXELS_LICENCE], **extra}


WITH_CLIPS = {**a.DEFAULT_CADENCE, "clips": {"providers": ["pexels"], "perReel": 2}}


class GeneratorTests(unittest.TestCase):
    def fixture(self, articles=None, **kwargs):
        fixture = Fixture(articles or [guide()], **kwargs)
        self.addCleanup(fixture.cleanup)
        return fixture

    def reel(self, f, **kwargs):
        made = [c for c in f.run(**kwargs)["created"] if c["kind"] == "reel"]
        self.assertTrue(made)
        return f.scenario(made[0]["id"])

    def test_a_new_guide_from_any_country_yields_a_fast_reel_and_a_photo_post_that_pass_every_guard(self):
        f = self.fixture()
        result = f.run(limit=3)
        self.assertEqual({(c["channel"], c["kind"]) for c in result["created"]}, {("instagram", "reel"), ("facebook", "carousel")})
        reel = f.scenario(next(c["id"] for c in result["created"] if c["kind"] == "reel"))
        photos = f.scenario(next(c["id"] for c in result["created"] if c["kind"] == "carousel"))
        self.assertEqual((reel["schemaVersion"], reel["format"], photos["schemaVersion"]), (3, "liste", 2))
        self.assertEqual(reel["targetUrl"], "https://voyagesansdetour.fr/japon/kyoto-train/")
        self.assertEqual(len(photos["scenes"]), 6)
        for scenario in (reel, photos):
            a.qualify(f.root, scenario, NOW)  # production.py's own guards and layout
            self.assertEqual(len({s["photo"] for s in scenario["scenes"]}), len(scenario["scenes"]))
            self.assertTrue(all(s.get("facts") for s in scenario["scenes"][:-1]))
            self.assertIn("Japon · Kyoto", scenario["scenes"][0]["kicker"])
            tags = scenario["caption"]["hashtags"]
            self.assertLessEqual(len(tags), 5)
            self.assertEqual(tags[:3], ["#Kyoto", "#Japon", "#VoyageJapon"])
        catalogue = json.loads((f.root / "catalogue.json").read_text())
        self.assertEqual({i["contentId"] for i in catalogue["items"]}, {c["id"] for c in result["created"]})

    def test_a_caption_never_runs_past_a_thousand_characters(self):
        line = "📍 " + "x" * 140
        scenario = {"kind": "reel", "channel": "instagram", "id": "ig-" + "a" * 70 + "-2026-11-15",
                    "caption": {"hook": "💶 " + "h" * 140, "lines": [line] * 5, "cta": "c" * 150, "hashtags": ["#Japon", "#Voyage"]}}
        self.assertGreater(len(p.caption(scenario, {})), a.CAPTION_MAX)
        fitted = a.fitted_caption(scenario, {})
        self.assertEqual(fitted["caption"]["lines"], [line] * 3)  # detail lines go first, never fewer than three
        self.assertLessEqual(len(p.caption(fitted, {})), a.CAPTION_MAX)
        self.assertEqual(len(scenario["caption"]["lines"]), 5)  # the draft itself is left as it was
        short = {**scenario, "caption": {**scenario["caption"], "lines": ["📍 court"] * 5}}
        self.assertIs(a.fitted_caption(short, {}), short)
        with self.assertRaisesRegex(a.Held, "caption_too_long"):
            a.fitted_caption({**scenario, "caption": {**scenario["caption"], "lines": [line + "y" * 17] * 5, "cta": "c" * 160}}, {})
        # Every post the generator queues goes through it.
        f = self.fixture()
        for created in f.run(limit=3)["created"]:
            made = f.scenario(created["id"])
            self.assertLessEqual(len(p.caption(made, {})), a.CAPTION_MAX)

    def test_a_fast_reel_opens_on_its_promise_and_stays_short(self):
        reel = self.reel(self.fixture())
        hook, facts, call = reel["scenes"][0], reel["scenes"][1:-1], reel["scenes"][-1]
        self.assertEqual((hook["layout"], call["layout"]), ("hook", "cta"))
        self.assertEqual(hook["headline"], ["Kyoto en train", f"*{len(facts)} chiffres à connaître*"])
        self.assertLessEqual(sum(s["seconds"] for s in reel["scenes"]), 30)
        self.assertTrue(all(s["seconds"] <= 4 for s in facts))  # a new picture every four seconds at most
        self.assertEqual([s["badge"] for s in facts], [f"{n}/{len(facts)}" for n in range(1, len(facts) + 1)])
        self.assertIn("bio", reel["caption"]["cta"])
        self.assertIn("Enregistrez", reel["caption"]["cta"])

    def test_figures_are_quoted_word_for_word_from_the_dated_page_snapshot(self):
        f = self.fixture()
        reel = self.reel(f)
        snapshot = (f.root / a.AUTO / reel["id"] / "guide.txt").read_text()
        self.assertEqual(snapshot.splitlines()[0], "https://voyagesansdetour.fr/japon/kyoto-train/")
        self.assertNotIn("var x", snapshot)
        values = {fact["value"] for fact in FACTS}
        for scene in reel["scenes"][1:-1]:
            figure = scene["headline"][0].strip("*").replace(" ", " ")
            self.assertIn(p.normalized(scene["facts"][0]["excerpt"]), p.normalized(snapshot))
            self.assertIn(figure, values)
            self.assertTrue(scene["facts"][0]["excerpt"].startswith(figure))

    def test_slots_are_paris_evenings_inside_the_weekly_limit(self):
        f = self.fixture([guide(f"guide-{n}", title=f"Guide {n} : Kyoto") for n in range(8)])
        result = f.run(limit=20)
        due = {name: sorted(p.instant(c["publishAt"]) for c in result["created"] if c["channel"] == name) for name in ("instagram", "facebook")}
        local = lambda moment: (moment.astimezone(PARIS).weekday(), moment.astimezone(PARIS).hour)
        self.assertEqual({local(d) for d in due["instagram"]}, {(1, 19), (6, 21)})
        self.assertEqual({local(d) for d in due["facebook"]}, {(3, 18), (6, 18)})
        for moments in due.values():
            self.assertGreaterEqual(len(moments), 5)  # three weeks at two posts a week
            self.assertGreaterEqual(min(moments), NOW + a.MIN_LEAD)
            self.assertLessEqual(max(moments), NOW + a.HORIZON)
            for moment in moments:
                self.assertLessEqual(sum(moment - a.WEEK < other <= moment for other in moments), 2)

    def test_free_slots_before_a_queued_post_are_filled_and_its_neighbours_left_alone(self):
        f = self.fixture([guide(f"guide-{n}", title=f"Guide {n} : Kyoto") for n in range(8)])
        batch = {"items": [{"dueAt": "2026-11-11T17:00:00Z", "payload": {"channel": "instagram", "kind": "reel"},
                            "review": {"destination": {"url": "https://voyagesansdetour.fr/portugal/x/"}}}]}
        (f.root / "reviewed-social/old-v1.json").write_text(json.dumps(batch))
        (f.root / "reviewed-social/index.json").write_text(json.dumps({"schemaVersion": 1, "items": [{"path": ".github/vsd-production/reviewed-social/old-v1.json", "batchId": "old-v1"}]}))
        due = sorted(p.instant(c["publishAt"]) for c in f.run(limit=20)["created"] if c["channel"] == "instagram")
        queued = p.instant("2026-11-11T17:00:00Z")
        self.assertTrue(all(abs(moment - queued) >= dt.timedelta(hours=40) for moment in due))  # Tuesday 10/11 is too close
        self.assertEqual(due[0], dt.datetime(2026, 11, 8, 20, 0, tzinfo=dt.timezone.utc))        # Sunday 21:00 in Paris
        self.assertNotIn(dt.datetime(2026, 11, 10, 18, 0, tzinfo=dt.timezone.utc), due)

    def test_a_post_listed_as_scenario_and_as_queued_batch_counts_once_in_the_weekly_limit(self):
        f = self.fixture([guide(f"guide-{n}", title=f"Guide {n} : Kyoto") for n in range(8)])
        first = [c for c in f.run(limit=1)["created"]][0]
        scenario = f.scenario(first["id"])
        batch = {"items": [{"dueAt": scenario["publishAt"], "payload": {"channel": "instagram", "kind": "reel"},
                            "review": {"destination": {"url": scenario["targetUrl"]}}}]}
        (f.root / "reviewed-social/queued-v1.json").write_text(json.dumps(batch))
        (f.root / "reviewed-social/index.json").write_text(json.dumps({"schemaVersion": 1, "items": [{"path": ".github/vsd-production/reviewed-social/queued-v1.json", "batchId": "queued-v1"}]}))
        due = sorted(p.instant(c["publishAt"]) for c in f.run(limit=20)["created"] if c["channel"] == "instagram")
        self.assertEqual(len(due), 4)  # the four other slots of the three weeks are still filled (three if the queued post counted twice)

    def test_a_slot_switched_off_is_ignored_and_an_instagram_carousel_slot_makes_a_carousel(self):
        cadence = {"schemaVersion": 1, "timezone": "Europe/Paris", "channels": {"instagram": {"weeklyLimit": 4, "minGapHours": 20, "slots": [
            {"weekday": "thursday", "time": "09:00", "kind": "carousel"}, {"weekday": "friday", "time": "18:00", "kind": "reel", "enabled": False}]}}}
        f = self.fixture(cadence=cadence)
        created = f.run(limit=1)["created"]
        self.assertEqual([(c["channel"], c["kind"]) for c in created], [("instagram", "carousel")])
        carousel = f.scenario(created[0]["id"])
        self.assertTrue(carousel["id"].startswith("igc-"))
        self.assertEqual(p.instant(carousel["publishAt"]).astimezone(PARIS).strftime("%A %H:%M"), "Thursday 09:00")
        self.assertIn("bio", carousel["caption"]["cta"])
        self.assertIn("fallbackBold", carousel["assets"])  # no empty box on a slide either

    def test_what_the_generator_builds_passes_the_guard_on_places_and_a_faulty_plan_is_refused(self):
        # Review of 13/11/2026: five mutations of the wiring survived the suite (the date gate replaced by False, a date
        # in 2027, plans without their caption, the fallback photo). Every test ran before the gate: none met the guard.
        later = dt.datetime(2026, 11, 16, 5, 17, tzinfo=dt.timezone.utc)
        self.assertLess(p.instant(p.PLACES_FROM), dt.datetime(2026, 11, 14, tzinfo=dt.timezone.utc))
        f = self.fixture()
        made = [f.scenario(c["id"]) for c in f.run(now=later, limit=4)["created"]]
        self.assertEqual({scenario["kind"] for scenario in made}, {"reel", "carousel"})
        captions = {f"kyoto-{n}": CAPTIONS.get(n, f"Kyoto, vue {n}.") for n in range(1, 9)}
        for scenario in made:
            self.assertGreaterEqual(p.instant(scenario["review"]["checkedAt"]), p.instant(p.PLACES_FROM))
            p.validate_scenario(scenario, f.root, later)
            # Each plan carries the caption of its photo: the guard reads what the generator read.
            self.assertTrue(all(scene["alt"] == captions[scene["photo"]] for scene in scenario["scenes"] if "photo" in scene), scenario["id"])
            # A fact that names a place stands over the photo of that place, in the scenario itself.
            over = {scene["photo"] for scene in scenario["scenes"][1:-1] if "Kiyomizu" in str(scene.get("detail"))}
            self.assertLessEqual(over, {"kyoto-3"})
            with mock.patch.object(p, "photos_of_another_place", return_value=["plan 2 names phuket over kyoto-3 (kiyomizu)"]):
                with self.assertRaisesRegex(p.Invalid, "Photo of another place than its plan names: plan 2 names phuket"):
                    p.validate_scenario(scenario, f.root, later)
                # The gate only spares what was sealed before the guard existed.
                with mock.patch.object(p, "PLACES_FROM", "2027-06-01T00:00:00Z"):
                    p.validate_scenario(scenario, f.root, later)
        # The real guard, on a real plan moved over another photo, refuses it.
        carousel = next(scenario for scenario in made if scenario["kind"] == "carousel")
        index = next(i for i, scene in enumerate(carousel["scenes"]) if "Kiyomizu" in str(scene.get("detail")))
        moved = {**carousel, "scenes": [({**scene, "photo": "kyoto-4", "alt": captions["kyoto-4"]} if i == index else scene) for i, scene in enumerate(carousel["scenes"])]}
        records = {f"kyoto-{n}": {"commonsTitle": f"File:Kyoto {n}.jpg"} for n in range(1, 9)}
        self.assertEqual(p.photos_of_another_place(carousel, records), [])
        self.assertEqual(p.photos_of_another_place(moved, records), [f"plan {index + 1} names kiyomizu over kyoto-4 (fushimi, inari)"])

    def test_a_guide_whose_photos_name_none_of_the_places_its_figures_name_is_held_with_its_reason(self):
        with mock.patch.dict(CAPTIONS, clear=True):
            f = self.fixture()
            result = f.run(limit=4)
        self.assertEqual(result["created"], [])
        self.assertEqual({(row["kind"], row["reason"]) for row in result["held"]}, {("reel", "fewer_than_four_facts"), ("carousel", "not_enough_figures_with_their_photo")})
        self.assertEqual(list((f.root / "scenarios").glob("*.json")), [])

    def test_a_file_that_is_not_the_photograph_as_taken_is_never_fetched_nor_reused(self):
        banned = next(iter(media_library.NOT_A_PHOTOGRAPH_AS_TAKEN))
        f = self.fixture()
        photos = media_library.Photos(f.root, NOW, lambda *args: self.fail("a banned file must not be downloaded"))
        photos.known[banned] = ("laponie-village-boules-neige", {"commonsTitle": banned, "file": "assets/photos/x.jpg"})
        self.assertIsNone(photos.get({"id": "laponie-village-boules-neige", "title": banned, "alt": "Une pyramide de boules de neige."}))

    def test_a_file_made_from_another_one_is_refused_at_intake_at_reuse_and_at_render(self):
        derived = photo_intake.derived
        self.assertTrue(derived("File:Snowball pyramid at Santa Claus' Village Large.jpg", "Rovaniemi", "File:Snowball_pyramid_at_Santa_Claus'_Village.jpg"))
        self.assertTrue(derived("File:Kinkaku-ji (edit).jpg", "Kyoto", "Own work"))
        self.assertTrue(derived("File:Tokyo Tower cropped.jpg", "", "Own work"))
        self.assertTrue(derived("File:Fuji.jpg", "Mount Fuji|Retouched pictures", "Own work"))
        self.assertTrue(derived("File:Fuji.jpg", "Extracted images", "Own work"))
        # The original other images were cut out of, a word that only looks like one, a photo sharing service: all fine.
        for title, categories, source in (("File:Playa Maya, Ko Phi Phi.JPG", "Images with extracted images|Ko Phi Phi Le", "Own work"),
                                          ("File:Rice crop in Sapa.jpg", "Sa Pa", "Travail personnel"), ("File:Edith Piaf street.jpg", "", "own work"),
                                          ("File:Lisboa (38916561925).jpg", "Lisbon", "https://www.flickr.com/photos/x/38916561925/")):
            self.assertFalse(derived(title, categories, source), title)
        with mock.patch.object(photo_intake, "fetch_json", return_value={"query": {"pages": {"1": {"imageinfo": [{
                "mime": "image/jpeg", "width": 4000, "height": 3000, "extmetadata": {"Categories": {"value": "Retouched pictures|Kyoto"}}}]}}}}):
            with self.assertRaisesRegex(photo_intake.Refused, "Not the photograph as taken"):
                photo_intake.commons_info("File:Kyoto 9.jpg")
        f = self.fixture()
        photos = media_library.Photos(f.root, NOW, lambda *args: self.fail("a derived file must not be downloaded"))
        self.assertIsNone(photos.get({"id": "kyoto-9", "title": "File:Kyoto temple (cropped).jpg", "alt": "Un temple."}))
        photos.known["File:Kyoto 9.jpg"] = ("kyoto-9", {"commonsTitle": "File:Kyoto 9.jpg", "categories": "Retouched pictures", "file": "assets/photos/x.jpg"})
        self.assertIsNone(photos.get({"id": "kyoto-9", "title": "File:Kyoto 9.jpg", "alt": "Un temple."}))
        # At render: a scenario reviewed since the rule whose catalogue files such a photo is refused.
        later = dt.datetime(2026, 11, 16, 5, 17, tzinfo=dt.timezone.utc)
        scenario = f.scenario(f.run(now=later, limit=1)["created"][0]["id"])
        with mock.patch.object(p, "derived_record", lambda record: True):
            with self.assertRaisesRegex(p.Invalid, "Not the photograph as taken"):
                p.validate_scenario(scenario, f.root, later)

    def test_a_photo_keeps_its_point_of_interest_from_the_generator_to_the_scenario_in_each_format(self):
        # The doe of Nara: 0.68 holds her whole on a 4:5 slide; the 9:16 frame of a reel needs its own point.
        with mock.patch.dict(media_library.SITE_FOCUS, {"kyoto-3": [0.68, 0.5]}), mock.patch.dict(media_library.SITE_FOCUS_VERTICAL, {"kyoto-3": [0.81, 0.5]}):
            f = self.fixture()
            made = {scenario["kind"]: scenario for scenario in (f.scenario(c["id"]) for c in f.run(limit=4)["created"])}
        focus = lambda kind: {scene["photo"]: scene["focus"] for scene in made[kind]["scenes"] if "photo" in scene}
        self.assertEqual((focus("carousel")["kyoto-3"], focus("reel")["kyoto-3"]), ([0.68, 0.5], [0.81, 0.5]))
        self.assertEqual({tuple(value) for photo, value in focus("reel").items() if photo != "kyoto-3"}, {(0.5, 0.5)})
        # In the narrow frame her head (0.76 to 0.865 of a 2521 × 1600 photo) stays in from the first image to the last.
        size, point = (2521, 1600), media_library.SITE_FOCUS_VERTICAL["japon-nara-cerfs"]
        for index in range(3):
            for progress in (0.0, 0.25, 0.5, 0.75, 1.0):
                for zoom in (1.0, 1.0 + motion_render.ZOOM_RANGE + motion_render.PUNCH):
                    slide = motion_render.drift_of(size, progress, index)
                    left, _, right, _ = motion_render.base.cover_box(size, motion_render.SIZE, zoom, (point[0] + slide, point[1]))
                    self.assertTrue(left <= 0.76 * size[0] and 0.865 * size[0] <= right, (index, progress, zoom, left, right))

    def test_a_cadence_with_every_slot_switched_off_stops_the_generator_without_an_error(self):
        # 13/11/2026: the generator is stopped this way until its choice of photos is fixed; the rest of the daily run goes on.
        slots = [{"weekday": "thursday", "time": "09:00", "kind": "carousel", "enabled": False}, {"weekday": "friday", "time": "18:00", "kind": "reel", "enabled": False}]
        cadence = {"schemaVersion": 1, "timezone": "Europe/Paris", "channels": {
            "instagram": {"weeklyLimit": 4, "minGapHours": 20, "slots": slots},
            "facebook": {"weeklyLimit": 2, "minGapHours": 60, "slots": [{"weekday": "sunday", "time": "18:00", "kind": "carousel", "enabled": False}]}}}
        f = self.fixture(cadence=cadence)
        result = f.run(limit=20)
        self.assertEqual((result["status"], result["created"], result["shortChannels"]), ("queue_covered", [], []))
        self.assertEqual(result["coveredUntil"], {"instagram": None, "facebook": None})
        self.assertEqual(list((f.root / "scenarios").glob("*.json")), [])

    def test_the_doe_of_nara_keeps_her_head_on_a_slide(self):
        # Audit of 13/11/2026: a centred 4:5 frame cut her at the neck (her muzzle ends at 86 % of a 2521 × 1600 photo).
        size, focus = (2521, 1600), media_library.SITE_FOCUS["japon-nara-cerfs"]
        left, _, right, _ = p.draw.cover_box(size, p.draw.SLIDE_SIZE, 1.0 + p.draw.ZOOM_RANGE / 2, tuple(focus))
        self.assertTrue(left <= 0.45 * size[0] and 0.87 * size[0] <= right, (left, right))

    def test_a_covered_queue_creates_nothing_and_existing_posts_are_never_rewritten(self):
        f = self.fixture([guide(f"guide-{n}", title=f"Guide {n} : Kyoto") for n in range(14)])
        first = f.run(limit=30)
        self.assertTrue(first["created"])
        snapshot = {path: path.read_bytes() for path in f.root.rglob("*") if path.is_file()}
        again = f.run(limit=30)
        self.assertEqual((again["created"], again["status"]), ([], "queue_covered"))
        self.assertEqual({path: path.read_bytes() for path in f.root.rglob("*") if path.is_file()}, snapshot)

    def test_the_queue_is_topped_up_newest_guide_first(self):
        articles = [guide(f"guide-{n}", title=f"Guide {n} : Kyoto", publishedOn=f"2026-10-{10 + n}") for n in range(14)]
        f = self.fixture(articles)
        result = f.run(limit=30)
        self.assertEqual(result["shortChannels"], [])
        self.assertEqual(result["created"][0]["guide"], "https://voyagesansdetour.fr/japon/guide-13/")

    def test_a_queue_that_cannot_be_filled_is_reported_short(self):
        result = self.fixture().run(limit=30)  # one guide for six slots a network
        self.assertEqual((result["status"], result["shortChannels"]), ("queue_short", ["facebook", "instagram"]))

    def test_a_guide_that_breaks_is_held_with_nothing_left_behind_and_the_next_one_goes_out(self):
        f = self.fixture([guide("casse", title="Guide cassé : Kyoto", publishedOn="2026-11-01"), guide("sain", title="Guide sain : Kyoto", publishedOn="2026-10-01")])
        original = a.qualify
        def qualify(root, scenario, now):
            if "casse" in scenario["id"]:
                raise OSError("disk full")
            return original(root, scenario, now)
        with mock.patch.object(a, "qualify", qualify):
            result = f.run(limit=1)
        self.assertEqual([c["guide"] for c in result["created"]], ["https://voyagesansdetour.fr/japon/sain/"])
        self.assertIn("error: OSError: disk full", [h["reason"] for h in result["held"]])
        self.assertEqual([path.name for path in (f.root / "scenarios").iterdir()], [result["created"][0]["id"] + ".json"])
        self.assertEqual([path.name for path in (f.root / a.AUTO).iterdir()], [result["created"][0]["id"]])

    def test_a_guide_with_an_unreadable_date_is_held_not_fatal(self):
        result = self.fixture([guide("date", title="Guide date : Kyoto", sourcesCheckedOn="octobre 2026"), guide()]).run(limit=1)
        self.assertIn({"slug": "date", "reason": "incomplete_guide"}, result["held"])
        self.assertEqual(len(result["created"]), 1)

    def test_no_seven_day_window_ever_holds_more_than_the_limit_even_between_two_queued_posts(self):
        monday = dt.datetime(2026, 11, 2, tzinfo=dt.timezone.utc)
        channel = a.Channel("instagram", 2, dt.timedelta(hours=40), (a.Slot(6, 21, 0, "reel"),), PARIS)
        rows = [{"channel": "instagram", "dueAt": monday + dt.timedelta(days=days, hours=17)} for days in (3, 9)]  # Thursday 5, Wednesday 11
        self.assertEqual(a.open_slots(channel, rows, monday)[0][0], dt.datetime(2026, 11, 15, 20, 0, tzinfo=dt.timezone.utc))  # Sunday 8 would be the third in seven days

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
        self.assertNotIn("*14 170 ¥*", [s["headline"][0] for s in self.reel(f)["scenes"]])

    def test_a_figure_no_font_can_draw_is_left_out(self):
        facts = [{"value": "938 ฿", "label": "la couchette du train de nuit"}] + FACTS
        reel = self.reel(self.fixture([guide(keyFacts=facts)]))
        self.assertFalse(any("฿" in line for scene in reel["scenes"] for line in scene["headline"]))

    def test_guide_with_stale_sources_is_held(self):
        f = self.fixture([guide(sourcesCheckedOn="2026-08-01")])
        result = f.run()
        self.assertEqual(result["created"], [])
        self.assertEqual(result["held"][0]["reason"], "guide_sources_older_than_45_days")

    def test_too_few_photos_holds_the_photo_post_and_the_reel(self):
        f = self.fixture(photos=5)
        result = f.run(limit=30)
        self.assertEqual(result["created"], [])
        self.assertIn({"slug": "kyoto-train", "channel": "facebook", "kind": "carousel", "reason": "not_enough_photos_or_figures"}, result["held"])
        self.assertIn({"slug": "kyoto-train", "channel": "instagram", "kind": "reel", "reason": "fewer_than_four_facts"}, result["held"])

    def test_featured_pictures_complete_the_guide_photos_only_when_they_name_the_place(self):
        f = self.fixture(photos=5)
        hits = ["File:Paris night.jpg", "File:Kyoto Kinkaku-ji in autumn.jpg"]
        result = f.run(limit=30, searcher=lambda query: hits if "Featured_pictures" in query else [])
        self.assertEqual({c["channel"] for c in result["created"]}, {"instagram", "facebook"})
        self.assertNotIn("File:Paris night.jpg", f.downloads)
        self.assertIn("File:Kyoto Kinkaku-ji in autumn.jpg", f.downloads)

    def test_site_author_name_replaces_commons_free_text(self):
        f = self.fixture()
        identity = f.run(limit=1)["created"][0]["id"]
        records = json.loads((f.root / a.AUTO / identity / "photos.json").read_text())["photos"]
        self.assertEqual(records["kyoto-1"]["author"], "Photographe 1")

    def test_photos_are_downloaded_once_and_reused_by_later_posts(self):
        f = self.fixture()
        f.run(limit=30)
        self.assertEqual(len(f.downloads), len(set(f.downloads)))

    def test_photo_whose_caption_names_a_closed_lift_is_skipped(self):
        f = self.fixture(photos=9)
        sources = json.loads((f.site / "image-sources.json").read_text())
        sources["photos"][1]["alt_fr"] = "L’ascenseur de Santa Justa."
        (f.site / "image-sources.json").write_text(json.dumps(sources, ensure_ascii=False))
        for c in f.run(limit=30)["created"]:
            self.assertNotIn("kyoto-2", [s["photo"] for s in f.scenario(c["id"])["scenes"]])

    def test_a_guide_comes_back_after_the_cooldown_in_another_format(self):
        f = self.fixture()
        first = self.reel(f, limit=1)
        reels = lambda result: [c for c in result["created"] if c["kind"] == "reel"]
        self.assertEqual(reels(f.run(NOW + dt.timedelta(days=7))), [])  # too soon for the same guide
        later = p.instant(first["publishAt"]) + a.REPOST_COOLDOWN - a.MIN_LEAD
        (f.site / "articles.json").write_text(json.dumps([guide(sourcesCheckedOn=later.date().isoformat())], ensure_ascii=False))
        second = reels(f.run(later))
        # The two-figure "express" reel is gone (too thin): the guide comes back as a list that opens on other figures.
        again = f.scenario(second[0]["id"])
        self.assertEqual((first["format"], again["format"]), ("liste", "liste"))
        self.assertNotEqual(first["scenes"][1]["headline"], again["scenes"][1]["headline"])

    def test_period_end(self):
        f = self.fixture()
        self.assertEqual(f.run(p.HARD_STOP)["status"], "period_ended")

    # --- formats ------------------------------------------------------------

    def test_a_budget_guide_opens_on_its_price(self):
        facts = [{"value": "872 €", "label": "le budget serré pour 14 jours et 13 nuits (154 120 ¥), capsule ou dortoir"}] + FACTS
        reel = self.reel(self.fixture([guide(category="Budget", shortTitle="Budget Japon", keyFacts=facts)]))
        hook = reel["scenes"][0]
        self.assertEqual((reel["format"], hook["kicker"], hook["headline"]), ("prix", "Combien ça coûte ?", ["Budget Japon", "*872 €*"]))
        self.assertEqual(hook["detail"], reel_formats.unbreakable("le budget serré pour 14 jours et 13 nuits (154 120 ¥)"))
        self.assertEqual(hook["facts"][0]["excerpt"], "872 € le budget serré pour 14 jours et 13 nuits (154 120 ¥)")
        self.assertEqual(reel["scenes"][1]["headline"], ["*14 170 ¥*"])  # prices first

    def test_an_itinerary_goes_day_by_day_and_never_shows_a_stage_over_another_place(self):
        bamboo = {"value": "1 000 ¥", "label": "la traversée en barque de la rivière Hozu à Arashiyama"}
        nara = {"title": "Jour 5 — Nara", "image": "kyoto-6", "paragraphs": ["Les daims du parc."]}
        reel = self.reel(self.fixture([guide(category="Itinéraires", sections=DAYS + [nara, GION], keyFacts=FACTS + [bamboo, LANES])]))
        stages = reel["scenes"][1:-1]
        # Four days out of six are shown: the hook counts them instead of promising every day.
        self.assertEqual((reel["format"], reel["scenes"][0]["headline"][-1]), ("itineraire", "*4 étapes clés*"))
        self.assertEqual(reel["title"], "Kyoto en train : les étapes clés")
        self.assertEqual([(s["kicker"], s["headline"], s["photo"]) for s in stages],
                         [("Jour 1", ["Kiyomizu-dera"], "kyoto-3"), ("Jour 2", ["Fushimi Inari", "et ses torii"], "kyoto-4"), ("Jour 3", ["Arashiyama"], "kyoto-5"),
                          ("Jour 6", ["Gion et ses ruelles"], "kyoto-7")])
        self.assertEqual(stages[0]["facts"][0]["excerpt"], "Jour 1 — Kiyomizu-dera, le temple sur pilotis")
        self.assertEqual(stages[0]["detail"], "*500 ¥* l’entrée du temple Kiyomizu-dera")
        # Every stage shown carries a figure of the guide, on screen and in the caption with its whole label.
        self.assertTrue(all(len(s["facts"]) == 2 and "*" in s["detail"] for s in stages))
        self.assertIn("📍 Jour 2 : Fushimi Inari et ses torii · 10 000 torii rouges sur la colline du Fushimi Inari", reel["caption"]["lines"])
        self.assertIn("📍 Jour 3 : Arashiyama · 1 000 ¥ la traversée en barque de la rivière Hozu à Arashiyama", reel["caption"]["lines"])
        shown = json.dumps(reel["scenes"], ensure_ascii=False)
        self.assertNotIn("Osaka", shown)  # no photo of Osaka in this guide
        self.assertNotIn("Nara", shown)   # a photo, but no figure for that day: the stage stays in the guide

    def test_day_by_day_is_promised_only_when_every_day_of_the_guide_is_shown(self):
        bamboo = {"value": "1 000 ¥", "label": "la traversée en barque de la rivière Hozu à Arashiyama"}
        reel = self.reel(self.fixture([guide(category="Itinéraires", sections=DAYS[:3] + [GION], keyFacts=FACTS + [bamboo, LANES])]))
        self.assertEqual((reel["format"], reel["scenes"][0]["headline"][-1]), ("itineraire", "*jour par jour*"))
        self.assertEqual([s["kicker"] for s in reel["scenes"][1:-1]], ["Jour 1", "Jour 2", "Jour 3", "Jour 6"])
        # Three days are three things said: an itinerary shows four stages at least, or the guide takes another format.
        short = self.reel(self.fixture([guide(category="Itinéraires", sections=DAYS[:3], keyFacts=FACTS + [bamboo])]))
        self.assertEqual(short["format"], "liste")
        self.assertEqual(reel["title"], "Kyoto en train : jour par jour")

    def test_an_itinerary_whose_days_have_no_figure_takes_another_format(self):
        # Two days out of three with a figure (review of 12/11/2026: "Valladolid, la base de l'intérieur" said nothing).
        reel = self.reel(self.fixture([guide(category="Itinéraires", sections=DAYS)]))
        self.assertEqual(reel["format"], "liste")
        self.assertTrue(all(any(c.isdigit() for c in s["headline"][0]) for s in reel["scenes"][1:-1]))

    def test_a_when_to_go_guide_becomes_a_table_to_pause(self):
        article = guide(category="Choisir", shortTitle="Quand partir à Kyoto", sections=[TABLE] + SECTIONS)
        reel = self.reel(self.fixture([article]))
        table = reel["scenes"][1]
        self.assertEqual((reel["format"], table["layout"], table["headline"]), ("tableau", "table", ["Les meilleurs mois"]))
        self.assertEqual(table["rows"][0], ["Cerisiers en fleurs", "Fin mars à début avril"])
        self.assertEqual(table["note"], "Faites pause pour tout lire")
        self.assertEqual([fact["excerpt"] for fact in table["facts"]][1], "Érables rouges Mi-novembre")
        # The first row says what the table lists; "Quand partir" names nothing the photo shows, the place stays above.
        lines = reel["caption"]["lines"]
        first = lines.index("📅 Les meilleurs mois — Cerisiers en fleurs : Fin mars à début avril")
        self.assertEqual(lines[first + 1], "📅 Érables rouges : Mi-novembre")
        self.assertEqual(table["kicker"], "Kyoto")

    def test_a_table_too_long_to_read_is_never_cut(self):
        rows = [[f"Mois {n}", "16 °C"] for n in range(12)]
        article = guide(sections=[{"title": "Mois par mois", "table": {"headers": ["Mois", "Kyoto"], "rows": rows}}] + SECTIONS)
        self.assertEqual(self.reel(self.fixture([article]))["format"], "liste")

    # --- real video plans ---------------------------------------------------

    def test_a_free_clip_that_names_the_place_becomes_a_plan_with_its_credit(self):
        f = self.fixture(cadence=WITH_CLIPS)
        reel = self.reel(f, clip_finder=lambda place: [pexels()])
        clips = [s["clip"] for s in reel["scenes"] if "clip" in s]
        self.assertEqual(len(clips), 1)
        self.assertNotIn("clip", reel["scenes"][0])   # the cover is always a chosen photo
        self.assertNotIn("clip", reel["scenes"][-1])
        record = json.loads((f.root / a.AUTO / reel["id"] / "clips.json").read_text())["clips"][clips[0]]
        self.assertEqual((record["author"], record["licence"]), ("Aiko Tanaka", "Pexels License"))
        info = p.validate_scenario(reel, f.root, NOW)
        self.assertIn("Vidéo : Aiko Tanaka", p.credits_text(reel, info))
        self.assertIn("Photos et vidéos libres (Pexels, Wikimedia Commons)", p.caption(reel, info))

    def test_without_a_provider_no_clip_is_ever_fetched(self):
        calls = []
        reel = self.reel(self.fixture(), clip_finder=lambda place: calls.append(place) or [pexels()])
        self.assertEqual((calls, [s for s in reel["scenes"] if "clip" in s]), ([], []))

    def test_an_unused_clip_is_not_left_in_the_repository(self):
        f = self.fixture(photos=2, cadence=WITH_CLIPS)  # too few photos: no reel is made
        f.run(clip_finder=lambda place: [pexels()])
        self.assertEqual(list((f.root / "assets").rglob("*.mp4")), [])


class ClipGuards(unittest.TestCase):
    def test_pexels_clip_must_name_the_place_and_never_be_ai(self):
        video = {"url": "https://www.pexels.com/video/kyoto-street-at-dusk-123/", "duration": 14, "user": {"name": "Aiko Tanaka"},
                 "video_files": [{"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://videos.pexels.com/a.mp4"},
                                 {"file_type": "video/mp4", "width": 2160, "height": 3840, "link": "https://videos.pexels.com/b.mp4"}]}
        self.assertEqual(clip_intake.pexels_candidate(video, "Kyoto")["stream"], "https://videos.pexels.com/a.mp4")
        for change in ({"url": "https://www.pexels.com/video/tokyo-street-123/"}, {"url": "https://www.pexels.com/video/kyoto-ai-generated-temple-9/"},
                       {"url": "https://example.org/video/kyoto-1/"}, {"duration": 3}, {"user": {}},
                       {"video_files": [{"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "https://videos.pexels.com/a.mp4"}]}):
            with self.assertRaises(clip_intake.Refused):
                clip_intake.pexels_candidate({**video, **change}, "Kyoto")
        self.assertEqual(clip_intake.pexels_candidates("Kyoto", None, searcher=lambda place, key: [video]), [])  # no key, no call

    def test_commons_video_needs_a_free_licence_the_place_in_its_title_and_a_real_view(self):
        info = {"duration": 60.0, "width": 3840, "height": 2160, "url": "https://upload.wikimedia.org/x.webm", "user": "Uploader",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Kyoto_from_above.webm",
                "derivatives": [{"type": 'video/webm; codecs="vp9"', "height": 1080, "src": "https://upload.wikimedia.org/x.1080p.webm"},
                                {"type": 'video/webm; codecs="vp9"', "height": 1440, "src": "https://upload.wikimedia.org/x.1440p.webm"}],
                "extmetadata": {"LicenseShortName": {"value": "CC BY 3.0"}, "Artist": {"value": "Jane Doe"}}}
        accepted = clip_intake.commons_candidate("File:Kyoto from above.webm", "Kyoto", info)
        self.assertEqual((accepted["stream"], accepted["licence"], accepted["author"]), ("https://upload.wikimedia.org/x.1440p.webm", "CC BY 3.0", "Jane Doe"))
        refusals = [("File:Osaka from above.webm", info), ("File:Kyoto mayor speech.webm", info),
                    ("File:Kyoto from above.webm", {**info, "extmetadata": {"LicenseShortName": {"value": "CC BY-NC 4.0"}}}),
                    ("File:Kyoto from above.webm", {**info, "extmetadata": {**info["extmetadata"], "Categories": {"value": "AI-generated videos"}}}),
                    ("File:Kyoto from above.webm", {**info, "height": 720, "width": 1280}), ("File:Kyoto from above.webm", {**info, "duration": 3.0})]
        for title, changed in refusals:
            with self.assertRaises(clip_intake.Refused):
                clip_intake.commons_candidate(title, "Kyoto", changed)

    def test_a_clip_is_fetched_only_from_the_known_servers_and_never_over_an_existing_file(self):
        self.assertEqual(clip_intake.safe_stream("https://upload.wikimedia.org/x.webm", "commons"), "https://upload.wikimedia.org/x.webm")
        for url, provider in (("http://upload.wikimedia.org/x.webm", "commons"), ("https://example.org/x.webm", "commons"),
                              ("https://upload.wikimedia.org/x.webm", "pexels"), ("file:///etc/passwd", "pexels"), ("concat:a|b", "commons")):
            with self.assertRaises(clip_intake.Refused):
                clip_intake.safe_stream(url, provider)
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / clip_intake.CLIPS).mkdir(parents=True)
            (Path(folder) / clip_intake.CLIPS / "kyoto-p12345678.mp4").write_bytes(b"kept")
            with self.assertRaisesRegex(clip_intake.Refused, "already present"):
                clip_intake.clip_record("kyoto-p12345678", pexels(), NOW, Path(folder), cutter=lambda *args: self.fail("must not fetch"))
            self.assertEqual((Path(folder) / clip_intake.CLIPS / "kyoto-p12345678.mp4").read_bytes(), b"kept")

    def test_the_middle_of_the_file_is_cut_never_its_opening_title(self):
        self.assertEqual(clip_intake.segment_start(100.0), 40.0)
        self.assertEqual(clip_intake.segment_start(8.0), 3.2)

    def test_the_engine_refuses_an_ai_clip_a_foreign_licence_and_changed_bytes(self):
        f = Fixture([guide()], cadence=WITH_CLIPS)
        self.addCleanup(f.cleanup)
        reel = f.scenario(next(c["id"] for c in f.run(clip_finder=lambda place: [pexels()])["created"] if c["kind"] == "reel"))
        registry = f.root / reel["clips"]["file"]
        original = json.loads(registry.read_text())
        clip_id = next(iter(original["clips"]))
        for change, message in (({"title": "kyoto-made-with-midjourney"}, "AI-generated video refused"), ({"licence": "CC BY-NC 4.0"}, "Clip licence not accepted"),
                                ({"licence": "CC BY 4.0", "licenceUrl": photo_intake.LICENCES["CC BY 4.0"]}, "Clip licence does not match its source"),
                                ({"sourcePage": "https://example.org/kyoto"}, "Clip attribution missing"), ({"sha256": "0" * 64}, "File fingerprint changed")):
            registry.write_text(json.dumps({**original, "clips": {clip_id: {**original["clips"][clip_id], **change}}}))
            changed = {**reel, "clips": {**reel["clips"], "sha256": p.digest(registry.read_bytes())}}
            with self.assertRaisesRegex(p.Invalid, message):
                p.validate_scenario(changed, f.root, NOW)


class FastReelGuards(unittest.TestCase):
    def setUp(self):
        self.f = Fixture([guide()])
        self.addCleanup(self.f.cleanup)
        self.reel = self.f.scenario(next(c["id"] for c in self.f.run()["created"] if c["kind"] == "reel"))

    def refused(self, message, mutate):
        scenario = json.loads(json.dumps(self.reel))
        mutate(scenario)
        with self.assertRaisesRegex(p.Invalid, message):
            a.qualify(self.f.root, scenario, NOW)

    def test_a_figure_on_screen_must_be_read_in_the_plan_own_quote(self):
        self.refused("not quoted from this plan", lambda s: s["scenes"][1].update(headline=["*3 h 59*"]))
        self.refused("not quoted from this plan", lambda s: s["scenes"][0].update(headline=["Kyoto en train", "*dès 99 €*"]))

    def test_a_label_cannot_date_a_figure_with_a_date_its_plan_does_not_quote(self):
        self.refused("does not quote with that date", lambda s: s["scenes"][1].update(tag="Guide Kyoto · chiffre de juillet 2026"))

    def test_a_label_that_is_not_text_is_refused_not_a_crash(self):
        self.refused("", lambda s: s["scenes"][-1].update(tag=["Guide Kyoto · chiffre de juillet 2026"]))

    def test_the_hook_announces_only_the_plans_that_follow(self):
        self.refused("not quoted from this plan", lambda s: s["scenes"][0].update(headline=["Kyoto en train", "*9 chiffres à connaître*"]))

    def test_the_button_is_the_site_name_on_the_last_plan_only(self):
        self.assertEqual(self.reel["scenes"][-1]["button"], p.MOTION_BUTTON)
        self.refused("Only the last plan carries the button", lambda s: s["scenes"][1].update(button=p.MOTION_BUTTON))
        self.refused("Only the last plan carries the button", lambda s: s["scenes"][-1].update(button="Le lien est en bio"))
        self.refused("Only the last plan carries the button", lambda s: s["scenes"][-1].update(button=p.MOTION_BUTTON_BEFORE))

    def test_first_plan_is_the_hook_and_last_plan_the_call(self):
        self.refused("First plan is the hook", lambda s: s["scenes"][0].update(layout="fact"))
        self.refused("First plan is the hook", lambda s: s["scenes"][-1].update(layout="table"))

    def test_a_plan_cannot_drag_and_a_reel_cannot_run_long(self):
        self.refused("Scene duration invalid", lambda s: s["scenes"][1].update(seconds=9))
        self.refused("Render duration out of bounds", lambda s: [scene.update(seconds=7) for scene in s["scenes"]])

    def test_a_character_no_font_can_draw_stops_before_rendering(self):
        self.refused("No font draws this character", lambda s: s["scenes"][1].update(detail="la couchette en bahts (฿)"))

    def test_a_number_cannot_be_smuggled_in_plain_text_or_cut_out_of_a_larger_one(self):
        self.refused("Number on screen is not in this plan", lambda s: s["scenes"][1].update(detail="de train, dès 99 € en promo"))
        self.refused("Number on screen is not in this plan", lambda s: s["scenes"][-1].update(headline=["Kyoto pour 12 €"]))
        self.assertTrue(p.whole("8 €", "le ticket à 8 € en gare"))
        self.assertFalse(p.whole("8 €", "le ticket à 18 € en gare"))
        self.assertFalse(p.whole("4 h 1", "4 h 10 de train"))

    def test_unknown_format_and_missing_fallback_font_are_refused(self):
        self.refused("A fast reel needs a known format", lambda s: s.update(format="vlog"))
        self.refused("Missing file fingerprint", lambda s: s["assets"].pop("fallbackBold"))


class ReelTextTests(unittest.TestCase):
    def test_a_long_label_stops_at_a_natural_pause_and_never_inside_a_parenthesis(self):
        self.assertEqual(reel_formats.short_label("de séjour sans visa pour les Français (e-visa à 25 $ au-delà, jusqu’à 90 jours)"),
                         "de séjour sans visa pour les Français")
        self.assertEqual(reel_formats.short_label("l’entrée d’un grand monument de la médina (Bahia, tombeaux saadiens, El Badi) selon les sources"),
                         "l’entrée d’un grand monument de la médina")
        self.assertEqual(reel_formats.short_label("le billet Nozomi"), "le billet Nozomi")

    def test_reading_time_follows_the_text(self):
        self.assertEqual(reel_formats.seconds_for("court"), 2.4)
        self.assertEqual(reel_formats.seconds_for("x" * 48), 3.5)
        self.assertEqual(reel_formats.seconds_for("x" * 200), 4.0)

    def test_a_long_value_goes_on_boxes_instead_of_overflowing(self):
        self.assertEqual(reel_formats.figure_lines("19 au 28 février 2027"), ["19 au 28 février 2027"])
        self.assertEqual(reel_formats.figure_lines("du 28 octobre 2026 au 3 janvier 2027"), ["du 28 octobre 2026", "au 3 janvier 2027"])
        self.assertIsNone(reel_formats.figure_lines("une valeur beaucoup trop longue pour deux lignes de vingt-deux signes"))
        self.assertEqual(reel_formats.figure_lines("2 h 32"), ["*2 h 32*"])

    def test_formats_follow_the_guide_and_rotate(self):
        self.assertEqual(reel_formats.ordered(["itineraire", "liste", "express"], []), ["itineraire", "liste", "express"])
        self.assertEqual(reel_formats.ordered(["itineraire", "liste", "express"], ["itineraire"]), ["liste", "express", "itineraire"])
        self.assertEqual(reel_formats.ordered(["liste", "express"], ["liste", "express"]), ["liste", "express"])


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

    def test_a_figure_that_one_section_alone_gives_belongs_to_it(self):
        # Review of 12/11/2026: "604 pesos l'entrée d'Uxmal" went under "Jour 3", whose words it shares, though the guide
        # gives that price under "Jours 4-6" only.
        sections = [{"title": "Jour 3 : Chichén Itzá à l’ouverture", "paragraphs": ["L’entrée pour un étranger coûte 697 pesos ; Uxmal attendra Mérida. Comptez 1 604 pesos à deux."]},
                    {"title": "Jours 4-6 : Mérida et Uxmal", "paragraphs": ["Le site est à 80 km : 604 pesos pour un étranger."]}]
        self.assertEqual(a.section_of("604 pesos", "l’entrée d’Uxmal pour un étranger, à l’ouverture", sections)["title"], "Jours 4-6 : Mérida et Uxmal")
        # Given by both, or by none: the words of its label decide, as before.
        both = [sections[0], {**sections[1], "paragraphs": ["Le site est à 80 km : 697 pesos aussi."]}]
        self.assertEqual(a.section_of("697 pesos", "l’entrée de Chichén Itzá pour un étranger", both)["title"], "Jour 3 : Chichén Itzá à l’ouverture")
        # …even when other sections give the figure too: "445 mm" belongs to "Le golfe", not to "En bref".
        thai = [{"title": "En bref : deux côtes en miroir", "paragraphs": ["Le golfe de Koh Samui prend sa pluie en novembre : octobre à décembre (263 à 445 mm)."]},
                {"title": "Le golfe : Koh Samui, Koh Phangan", "paragraphs": ["445 mm en novembre, le pic de l’année."]},
                {"title": "Mois par mois", "table": {"headers": ["Mois", "Koh Samui"], "rows": [["Novembre", "445 mm"]]}}]
        self.assertEqual(a.section_of("445 mm", "de pluie à Koh Samui en novembre : le golfe est trempé quand l’Andaman sèche", thai)["title"], "Le golfe : Koh Samui, Koh Phangan")
        # A section that only sums the guide up is about none of its figures: the district keeps its own.
        for title in ("Le comparatif en un coup d’œil", "Avant tout", "En bref", "L’essentiel"):
            districts = [{"title": "Baixa et Chiado", "paragraphs": ["De l’aéroport à Rossio, comptez une petite demi-heure en métro."]},
                         {"title": title, "table": {"headers": ["Quartier", "Métro"], "rows": [["Baixa", "25 min"], ["Saldanha", "18 min"]]}}]
            self.assertEqual(a.section_of("25 min", "de l’aéroport à Rossio, en métro", districts)["title"], "Baixa et Chiado", title)

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

    def test_an_illustration_a_poster_or_an_old_work_is_not_a_photograph(self):
        refuse = photo_intake.not_a_photograph
        self.assertTrue(refuse("File:Rose O'Neill - When We All Believe (Santa Claus and children illustration from the 1903 December 2 issue of Puck).jpg", {}))
        self.assertTrue(refuse("File:Santa Claus - Sunkist Ad (1928).jpg", {}))
        self.assertTrue(refuse("File:Kyoto.jpg", {"Categories": {"value": "Ukiyo-e|Woodcuts of Kyoto"}}))
        self.assertTrue(refuse("File:Kyoto street.jpg", {"DateTimeOriginal": {"value": "<time datetime='1931-05-02'>2 May 1931</time>"}}))
        self.assertTrue(refuse("File:Lapland.jpg", {"Categories": {"value": "Travel posters of Finland"}}))
        recent = {"DateTimeOriginal": {"value": "2019-02-27 21:14:08"}, "Categories": {"value": "Aurora borealis in Finland|Featured pictures on Wikimedia Commons"}}
        self.assertFalse(refuse("File:Aurora borealis over Saana fell.jpg", recent))
        self.assertFalse(refuse("File:Santa Maria in Trastevere church in Rome (12).jpg", {"Categories": {"value": "Interior of Santa Maria in Trastevere"}}))
        self.assertFalse(refuse("File:Lisbon Praça do Comércio BW 2018-10-03 13-29-10.jpg", {}))
        # A photograph of a tram that carries an advert is filed under "advertisements on trams": still a photograph.
        tram = {"DateTimeOriginal": {"value": "2014-10-22 11:00"}, "Categories": {"value": "Taken with Sony SLT-A55V|Oporto trams in 2014|Coca-Cola advertisements on trams in Porto"}}
        self.assertFalse(refuse("File:2014-P53 Porto (15088676433).jpg", tram))
        self.assertTrue(refuse("File:Porto.jpg", {"Categories": {"value": "Advertisements in Porto"}}))
        self.assertTrue(refuse("File:Port wine advertisement.jpg", {}))
        self.assertTrue(refuse("File:Advertisement on a magazine page.jpg", {}))
        self.assertTrue(refuse("File:Lisbon.jpg", {"Categories": {"value": "Ads on walls in Lisbon"}}))
        self.assertTrue(photo_intake.unphotographic_record({"commonsTitle": "File:Santa Claus - Sunkist Ad (1928).jpg", "categories": "Sunkist advertisements"}))
        self.assertFalse(photo_intake.unphotographic_record({"commonsTitle": "File:Teide Canadas.jpg", "categories": "Teide"}))

    def test_the_camera_is_read_from_the_file_own_data(self):
        info = {"commonmetadata": [{"name": "Make", "value": "NIKON CORPORATION"}, {"name": "Model", "value": "NIKON D850"}]}
        self.assertEqual(photo_intake.camera_of(info), "NIKON D850")
        self.assertEqual(photo_intake.camera_of({"commonmetadata": [{"name": "Make", "value": "Canon"}]}), "Canon")
        self.assertIsNone(photo_intake.camera_of({"commonmetadata": [{"name": "Software", "value": "Adobe Photoshop"}]}))
        self.assertIsNone(photo_intake.camera_of({}))


LAPLAND = {"slug": "laponie-budget-rovaniemi", "country": "finlande", "destination": "Laponie", "shortTitle": "Laponie : le budget",
           "title": "Combien coûte un voyage en Laponie ? Le budget de Rovaniemi", "category": "Budget"}


class PlacePhotoTests(unittest.TestCase):
    """A post shows the place it names: the audit of 12/11/2026 found a Lapland reel made of churches and old adverts."""

    def fixture(self, articles=None, **kwargs):
        fixture = Fixture(articles or [guide()], **kwargs)
        self.addCleanup(fixture.cleanup)
        return fixture

    def test_only_the_place_and_its_known_names_are_searched_never_a_word_from_a_photo_title(self):
        article = guide(**LAPLAND)
        names = media_library.place_names(article, {})
        self.assertEqual(names, ["Laponie", "Lapland", "Laponia"])
        asked = []
        hits = ["File:Santa Claus - Sunkist Ad (1928).jpg", "File:Dome of Cattedrale di Santa Maria del Fiore (Florence).jpg",
                "File:Balcones de la Avenida Maritima - Santa Cruz de La Palma 14.jpg", "File:Reindeer in Finnish Lapland.jpg",
                "File:Laplander dog.jpg"]
        found = media_library.featured_candidates(article, names, "Finlande", lambda query: asked.append(query) or hits)
        self.assertEqual({candidate["title"] for candidate in found}, {"File:Reindeer in Finnish Lapland.jpg"})
        self.assertTrue(all(candidate["automatic"] for candidate in found))
        self.assertEqual(len(asked), 3)
        self.assertFalse(any(word in query for query in asked for word in ("Santa", "Claus", "Village", "Rovaniemi")))

    def test_a_place_is_known_by_its_reviewed_names_only(self):
        self.assertEqual(media_library.place_names(guide(), {}), ["Kyoto"])
        self.assertEqual(media_library.place_names(guide(destination="Japon"), {}), ["Japon", "Japan"])
        self.assertEqual(media_library.place_names(guide(destination="Thaïlande", country="thailande"), {}), ["Thaïlande", "Thailand", "Tailandia"])
        self.assertEqual(media_library.place_names(guide(destination="Yucatán", country="mexique"), {}), ["Yucatán"])
        self.assertEqual(media_library.country_names(guide(), {}), ["Japon", "Japan"])
        self.assertEqual(media_library.country_names(guide(**LAPLAND), {}), ["Finlande", "Finland", "Finlandia"])
        self.assertEqual(media_library.country_names(guide(country="portugal"), {"portugal": {"name": "Portugal"}}), ["Portugal"])

    def test_a_whole_country_is_never_searched(self):
        # "Portugal" or "Japon" in a title says nothing of what the picture shows: a sea squirt, a war photograph.
        for article in (guide(destination="Portugal", country="portugal"), guide(destination="Japon"), guide(destination="Vietnam", country="vietnam")):
            asked = []
            hits = ["File:Piña de mar (Phallusia mammillata), Parque natural de la Arrábida, Portugal, 2020-07-21, DD 07.jpg", "File:Viet Cong soldier, Vietnam.jpg"]
            found = media_library.featured_candidates(article, media_library.place_names(article, {}), "x", lambda query: asked.append(query) or hits,
                                                      media_library.country_names(article, {}))
            self.assertEqual((found, asked), ([], []))

    def test_a_namesake_in_another_country_is_refused(self):
        # The reviewer's cases of 12/11/2026: macaws of Chapada dos Guimarães (Brazil) under a Guimarães reel, and others.
        tied = media_library.tied_to_country
        portugal, finland = ["Portugal"], ["Finlande", "Finland", "Finlandia"]
        macaws = {"commonsTitle": "File:189 Red-and-green macaw couple flying in Chapada dos Guimarães National Park Photo by Giles Laurent.jpg",
                  "categories": "Featured pictures of Mato Grosso|Wiki Loves Earth 2025 in Brazil|Ara chloropterus in flight", "camera": "ILCE-1"}
        church = {"commonsTitle": "File:Church of Our Lady of Consolation in Guimaraes (3).jpg",
                  "categories": "Igreja de Nossa Senhora da Consolação e Santos Passos|Featured pictures of Portugal"}
        self.assertFalse(tied(macaws, portugal))
        self.assertTrue(tied(church, portugal))
        self.assertFalse(tied({"commonsTitle": "File:Porto Alegre - Brazil Landscape-Night.jpg", "categories": "Porto Alegre at night|Featured pictures of Brazil"}, portugal))
        self.assertTrue(tied({"commonsTitle": "File:Porto-Ponte Dom Luis I-14-2011-gje.jpg", "categories": "Ponte Luís I|Quality images of Portugal"}, portugal))
        self.assertTrue(tied({"commonsTitle": "File:Ribeira, Porto, Portugal (2).jpg", "categories": ""}, portugal))
        self.assertFalse(tied({"commonsTitle": "File:Abisko National Park, Swedish Lapland.jpg", "categories": "Abisko National Park|Featured pictures of Sweden"}, finland))
        self.assertFalse(tied({"commonsTitle": "File:Sarek, Laponia World Heritage, Sweden.jpg", "categories": "Sarek National Park"}, finland))
        self.assertTrue(tied({"commonsTitle": "File:Path to Pallastunturi, Muonio, Lapland, Finland, 2021 September.jpg", "categories": ""}, finland))
        self.assertFalse(tied({"commonsTitle": "File:Kyoto.jpg"}, ["Japon", "Japan"]))  # nothing says where: in doubt, no photo
        self.assertFalse(media_library.names_place("File:Castelo de Guimarães.jpg", ["Lisbonne", "Lisbon", "Lisboa"]))
        guimaraes = guide(slug="guimaraes-une-journee-sans-voiture", destination="Guimarães", country="portugal")
        found = media_library.featured_candidates(guimaraes, media_library.place_names(guimaraes, {}), "Portugal",
                                                  lambda query: [macaws["commonsTitle"], church["commonsTitle"]], portugal)
        self.assertEqual([candidate["countryNames"] for candidate in found], [portugal, portugal])

    def test_the_generator_drops_a_found_photo_that_nothing_ties_to_the_country(self):
        f = self.fixture(photos=5)
        hits = ["File:Kyoto Protocol signing, elsewhere.jpg", "File:Kyoto Kinkaku-ji in autumn.jpg"]
        result = f.run(limit=30, searcher=lambda query: hits if "Featured_pictures" in query else [])
        records = [record for path in (f.root / a.AUTO).glob("*/photos.json") for record in json.loads(path.read_text())["photos"].values()]
        used = {record["commonsTitle"] for record in records}
        self.assertIn("File:Kyoto Protocol signing, elsewhere.jpg", f.downloads)
        self.assertNotIn("File:Kyoto Protocol signing, elsewhere.jpg", used)
        self.assertIn("File:Kyoto Kinkaku-ji in autumn.jpg", used)
        self.assertEqual({path.name for path in (f.root / a.AUTO_PHOTOS).glob("*.jpg")}, {Path(record["file"]).name for record in records})
        self.assertTrue(result["created"])

    def test_the_place_is_a_whole_word_of_the_file_title(self):
        named = media_library.names_place
        self.assertTrue(named("File:Ribeira, Porto (2).jpg", ["Porto"]))
        self.assertFalse(named("File:Portofino harbour.jpg", ["Porto"]))
        self.assertTrue(named("File:Puente de la Torre, Londres, Inglaterra, 2014-08-11, DD 092.JPG", ["Londres"]))
        self.assertTrue(named("File:194 White-nosed coati at the beach in Yucatán Photo by Giles Laurent.jpg", ["Yucatán"]))
        self.assertTrue(named("File:Chichen Itza-Yucatan-Mexico0222.jpg", ["Yucatán"]))
        self.assertFalse(named("File:Santa Cruz de La Palma.jpg", ["Laponie", "Lapland"]))

    def test_an_automatic_find_without_a_camera_is_refused_and_leaves_no_file(self):
        f = self.fixture(photos=5)
        hits = ["File:Kyoto old print, no camera.jpg", "File:Kyoto Kinkaku-ji in autumn.jpg"]
        result = f.run(limit=30, searcher=lambda query: hits if "Featured_pictures" in query else [])
        self.assertIn("File:Kyoto old print, no camera.jpg", f.downloads)
        used = {record["commonsTitle"] for path in (f.root / a.AUTO).glob("*/photos.json") for record in json.loads(path.read_text())["photos"].values()}
        self.assertIn("File:Kyoto Kinkaku-ji in autumn.jpg", used)
        self.assertNotIn("File:Kyoto old print, no camera.jpg", used)
        kept = {path.name for path in (f.root / a.AUTO_PHOTOS).glob("*.jpg")}
        self.assertEqual(len(kept), len(used))
        self.assertTrue(result["created"])

    def test_hand_reviewed_photos_complete_a_guide_and_the_sealed_catalogue_is_never_written(self):
        sealed = HERE / "assets/photos/catalogue.json"
        before = hashlib.sha256(sealed.read_bytes()).hexdigest()
        with mock.patch.object(photo_intake, "add_photo", lambda catalogue, photo_id, title, now: {**catalogue, "photos": {**catalogue["photos"], photo_id: {"commonsTitle": title, "licence": "CC0"}}}), \
                tempfile.TemporaryDirectory() as folder, mock.patch.object(photo_intake, "REVIEWED", Path(folder) / "reviewed.json"), \
                mock.patch("sys.argv", ["photo_intake.py", "kyoto-gion", "File:Gion.jpg", "lisbonne-alfama-toits", "File:Deja.jpg"]), \
                mock.patch("builtins.print"):
            photo_intake.main()
            written = json.loads((Path(folder) / "reviewed.json").read_text())["photos"]
        self.assertEqual(list(written), ["kyoto-gion"])  # an id of the sealed catalogue is refused, not shadowed
        self.assertEqual(hashlib.sha256(sealed.read_bytes()).hexdigest(), before)
        self._guide_completed_from("reviewed.json")
        self._guide_completed_from("catalogue.json")

    def _guide_completed_from(self, catalogue_name):
        f = self.fixture(photos=3)
        records = {}
        for name in ("gion", "fushimi", "arashiyama"):
            Image.new("RGB", (2400, 1600), (40, 90, 140)).save(f.root / f"assets/photos/kyoto-{name}.jpg", quality=80)
            raw = (f.root / f"assets/photos/kyoto-{name}.jpg").read_bytes()
            records[f"kyoto-{name}"] = {"file": f"assets/photos/kyoto-{name}.jpg", "sha256": hashlib.sha256(raw).hexdigest(), "width": 2400, "height": 1600,
                                        "commonsTitle": f"File:{name}.jpg", "sourcePage": f"https://commons.wikimedia.org/wiki/File:{name}.jpg",
                                        "author": "Photographe", "licence": "CC BY 4.0", "licenceUrl": photo_intake.LICENCES["CC BY 4.0"],
                                        "commonsSha1": hashlib.sha1(name.encode()).hexdigest(), "retrievedAt": p.stamp(NOW), "alt": f"Kyoto, {name}."}
        records["osaka-chateau"] = {**records["kyoto-gion"], "commonsTitle": "File:Osaka.jpg"}
        (f.root / "assets/photos" / catalogue_name).write_text(json.dumps({"schemaVersion": 1, "photos": records}))
        made = [c for c in f.run(limit=30)["created"] if c["kind"] == "reel"]
        self.assertTrue(made)
        used = {scene["photo"] for scene in f.scenario(made[0]["id"])["scenes"]}
        self.assertTrue(used & {"kyoto-gion", "kyoto-fushimi", "kyoto-arashiyama"})
        self.assertNotIn("osaka-chateau", used)
        self.assertEqual(f.downloads, [f"File:Kyoto {n}.jpg" for n in (1, 2, 3)])


class DensityTests(unittest.TestCase):
    """A reel says at least four things, never its own title again, and a retired post gives its slot back."""

    def fixture(self, articles=None, **kwargs):
        fixture = Fixture(articles or [guide()], **kwargs)
        self.addCleanup(fixture.cleanup)
        return fixture

    def reels(self, result, f):
        return [f.scenario(c["id"]) for c in result["created"] if c["kind"] == "reel"]

    def test_a_reel_with_fewer_than_four_distinct_facts_is_not_made(self):
        f = self.fixture(photos=5)  # five photos: a hook, a call and three figures at most
        result = f.run(limit=30)
        self.assertEqual(self.reels(result, f), [])
        self.assertIn("fewer_than_four_facts", {row["reason"] for row in result["held"] if row.get("kind") == "reel"})
        self.assertNotIn("express", reel_formats.applicable(guide(), a.usable_facts(guide(), page(guide()), f.root), ""))
        g = self.fixture(photos=6)
        made = self.reels(g.run(limit=30), g)[0]
        self.assertEqual(len({fact["excerpt"] for scene in made["scenes"][1:-1] for fact in scene["facts"]}), 4)

    def test_a_figure_that_repeats_the_title_is_left_out(self):
        facts = [{"value": "7 jours", "label": "pour voir Kyoto, Nara et Osaka sans courir"}] + FACTS
        f = self.fixture([guide(shortTitle="Kyoto en 7 jours", keyFacts=facts)])
        reel = self.reels(f.run(limit=1), f)[0]
        self.assertNotIn(["*7" + reel_formats.NBSP + "jours*"], [scene["headline"] for scene in reel["scenes"]])
        self.assertEqual(reel["scenes"][1]["headline"], ["*4" + reel_formats.NBSP + "h" + reel_formats.NBSP + "10*"])

    def test_a_budget_reel_opens_on_a_price_only_when_that_price_is_the_budget(self):
        cabin = [{"value": "59 €", "label": "la cabine privative du train de nuit Helsinki–Rovaniemi"}] + FACTS
        f = self.fixture([guide(category="Budget", shortTitle="Laponie : le budget", keyFacts=cabin)])
        reel = self.reels(f.run(limit=1), f)[0]
        self.assertEqual(reel["format"], "liste")
        # Four figures, not five: only one of them is shown by a photo of this guide, the others just fill the reel.
        self.assertEqual(reel["scenes"][0]["headline"][-1], "*4 chiffres à connaître*")
        self.assertEqual(reel["title"], "Laponie : le budget — les chiffres à connaître")
        self.assertTrue(reel_formats.opens_on_budget({"value": "872 €", "label": "le budget serré pour 14 jours et 13 nuits"}))
        self.assertTrue(reel_formats.opens_on_budget({"value": "1 370 €", "label": "par personne, hors vol"}))
        self.assertFalse(reel_formats.opens_on_budget({"value": "0 €", "label": "rencontrer le Père Noël dans son bureau"}))
        self.assertFalse(reel_formats.opens_on_budget({"value": "10 jours", "label": "le budget temps du voyage"}))

    def test_a_title_never_carries_two_colons(self):
        self.assertEqual(a.joined_title("Laponie : le budget", "combien ça coûte"), "Laponie : le budget — combien ça coûte")
        self.assertEqual(a.joined_title("Lisbonne ou Porto ?", "4 repères"), "Lisbonne ou Porto ? — 4 repères")
        self.assertEqual(a.joined_title("Kyoto en train", "jour par jour"), "Kyoto en train : jour par jour")

    def test_a_retired_post_gives_back_its_slot_and_its_guide_under_a_new_identity(self):
        f = self.fixture()
        first = f.run(limit=1)["created"][0]
        before = (f.root / "scenarios" / f"{first['id']}.json").read_bytes()
        batch = {"schemaVersion": 1, "batchId": first["id"] + "-v1", "items": [{"dueAt": first["publishAt"], "payload": {"channel": "instagram", "kind": "reel"},
                                                                               "review": {"destination": {"url": first["guide"]}}}]}
        (f.root / "reviewed-social" / (first["id"] + "-v1.json")).write_text(json.dumps(batch))
        entry = {"batchId": first["id"] + "-v1", "path": f"x/{first['id']}-v1.json"}
        (f.root / "reviewed-social/index.json").write_text(json.dumps({"schemaVersion": 1, "items": [entry]}))
        self.assertNotIn(first["publishAt"], [c["publishAt"] for c in f.run(limit=1)["created"]])  # queued: its slot is taken
        for path in (f.root / "scenarios").glob("*.json"):
            if path.stem != first["id"]:
                path.unlink()
        catalogue = json.loads((f.root / "catalogue.json").read_text())
        (f.root / "catalogue.json").write_text(json.dumps({**catalogue, "items": [i for i in catalogue["items"] if i["contentId"] == first["id"]]}))
        (f.root / "reviewed-social/index.json").write_text(json.dumps({"schemaVersion": 1, "items": [entry], "retirements": [{"batchId": entry["batchId"]}]}))
        again = f.run(limit=1)["created"][0]
        self.assertEqual((again["publishAt"], again["id"], again["guide"]), (first["publishAt"], first["id"] + "-2", first["guide"]))
        self.assertEqual((f.root / "scenarios" / f"{first['id']}.json").read_bytes(), before)

    def test_a_when_to_go_guide_is_not_promised_prices_and_an_itinerary(self):
        article = guide(category="Choisir", shortTitle="Quand partir à Kyoto", sections=[TABLE] + SECTIONS)
        f = self.fixture([article])
        posts = [f.scenario(c["id"]) for c in f.run(limit=30)["created"] if c["channel"] == "facebook"]
        self.assertTrue(posts)
        self.assertNotIn("itinéraire", posts[0]["caption"]["cta"])
        self.assertIn("meilleure période", posts[0]["caption"]["cta"])
        other = self.fixture()
        plain = [other.scenario(c["id"]) for c in other.run(limit=30)["created"] if c["channel"] == "facebook"]
        self.assertIn("prix, horaires", plain[0]["caption"]["cta"])


class StageTests(unittest.TestCase):
    def test_a_dash_separates_two_towns(self):
        self.assertTrue({"merida", "cancun", "tren", "maya"} <= reel_formats.words_of("Jour 7 : Mérida–Cancún en Tren Maya"))

    def test_a_stage_carries_its_price_with_what_it_pays_for(self):
        label = "l’entrée de Chichén Itzá pour un étranger depuis le « boleto único » du 27 mars 2026 (105 pesos de tarif INAH inclus)"
        fact = {"value": "697 pesos", "label": label, "short": reel_formats.short_label(label), "shortExcerpt": "697 pesos " + label}
        step = {"kicker": "Jour 3", "lines": ["Chichén Itzá"], "title": "Jour 3 : Chichén Itzá à l’ouverture", "fact": fact}
        # No punctuation within reach: the label stops before what only qualifies the figure, still the guide's own words.
        shown = "l’entrée de Chichén Itzá pour un étranger"
        self.assertEqual(fact["short"], shown)
        fact["shortExcerpt"] = "697 pesos " + shown
        scene = reel_formats.stage_plan(step, ("photo", "yucatan-cenote"), "Guide Yucatán")
        self.assertEqual(scene["detail"], "*697 pesos* " + shown)
        self.assertEqual(scene["facts"][1]["excerpt"], "697 pesos " + shown)
        self.assertEqual(reel_formats.short_label("Cancún–Playa del Carmen et Playa del Carmen–Tulum en tarif touriste international (octobre 2026)"),
                         "Cancún–Playa del Carmen et Playa del Carmen–Tulum")

    def test_a_stage_whose_figure_does_not_fit_has_none(self):
        day = {"title": "Jour 3 — Chichén Itzá"}
        fact = {"value": "697 pesos", "label": "l’entrée", "short": "l’entrée", "section": day}
        stage = lambda facts: reel_formats.stages({"sections": [day]}, "Jour 3 — Chichén Itzá", facts)[0]["fact"]
        self.assertIs(stage([fact]), fact)
        self.assertIsNone(stage([{**fact, "short": "x" * 90}]))  # longer than three lines under the stage: not shown, so no stage
        self.assertIsNone(stage([{**fact, "section": {"title": "Un autre jour"}}]))

    def test_the_first_photo_opens_the_reel_when_the_cover_is_too_small_for_it(self):
        article = guide(cover="kyoto-absente")
        facts = [{**fact, "short": fact["label"], "shortExcerpt": fact["value"] + " " + fact["label"], "excerpt": fact["value"] + " " + fact["label"], "section": None}
                 for fact in FACTS]
        photos = [(f"kyoto-{n}", {"commonsTitle": f"File:Kyoto {n}.jpg", "emblematic": True}, CAPTIONS.get(n, f"Kyoto, vue {n}.")) for n in range(1, 8)]
        scenes, _ = reel_formats.build("liste", article, facts, photos, [], "Le Nozomi relie Tokyo à Kyoto.", "Kyoto", "Japon · Kyoto", "Guide Kyoto",
                                       ["Kyoto en train"], "")
        self.assertEqual(scenes[0]["photo"], "kyoto-1")
        self.assertNotIn("kyoto-1", [scene["photo"] for scene in scenes[1:]])


class ShownTests(unittest.TestCase):
    """Each plan shows what its text names (review of 12/11/2026)."""

    PHOTOS = [("lap-aurore", {"commonsTitle": "File:Aurora.jpg"}, "Une aurore boréale en Laponie."),
              ("lap-bureau", {"commonsTitle": "File:Office.jpg"}, "Le bureau du Père Noël illuminé, à Rovaniemi."),
              ("lap-cabane", {"commonsTitle": "File:Hut.jpg"}, "Une cabane sous la neige."),
              ("lap-huskies", {"commonsTitle": "File:Dogs.jpg"}, "Un attelage de huskies."),
              ("lap-train", {"commonsTitle": "File:Train.jpg"}, "Le train de nuit en gare de Rovaniemi."),
              ("lap-traineau", {"commonsTitle": "File:Sleigh.jpg", "focus": [0.8, 0.55]}, "Une balade en traîneau tiré par un renne."),
              ("lap-village", {"commonsTitle": "File:Village.jpg"}, "Le village sous la neige en décembre, à Rovaniemi."),
              ("lap-pyramide", {"commonsTitle": "File:Balls.jpg", "emblematic": True}, "Une pyramide de boules de neige.")]
    FIGURES = [("59 €", "la cabine privative du train de nuit Helsinki–Rovaniemi"), ("0 €", "rencontrer le Père Noël dans son bureau"),
               ("30 à 60 €", "une balade en traîneau à renne de 400 ou 800 m"), ("63 €", "la courte balade en huskies au village"),
               ("42 €", "l’entrée adulte de SantaPark, ouvert du 31 octobre au 23 janvier"), ("−6 °C", "la maximale moyenne de décembre à Rovaniemi")]

    def build(self, fmt="liste", photos=None, figures=None):
        facts = [{"value": value, "label": label, "short": reel_formats.short_label(label), "shortExcerpt": value + " " + reel_formats.short_label(label),
                  "excerpt": value + " " + label, "section": None} for value, label in figures or self.FIGURES]
        article = guide(cover="absente", shortTitle="Laponie : le budget", destination="Laponie")
        return reel_formats.build(fmt, article, facts, list(photos or self.PHOTOS), [], "Phrase d’ouverture.", "Laponie", "Finlande · Laponie",
                                  "Guide Laponie · sources du 24/10/2026", ["Laponie :", "le budget"], "")

    def test_the_call_to_action_is_shown_over_an_emblematic_photo_never_a_detail(self):
        scenes, _ = self.build()
        self.assertEqual(scenes[-1]["photo"], "lap-pyramide")  # the one a human marked; the hut was free too
        # Nothing emblematic left: the reel waits for such a photo rather than closing on a hut.
        plain = [(photo_id, {"commonsTitle": record["commonsTitle"]}, alt) for photo_id, record, alt in self.PHOTOS]
        with self.assertRaisesRegex(reel_formats.Held, "no_emblematic_photo_for_the_call"):
            self.build(photos=plain)

    def test_a_figure_that_names_the_photo_kept_for_the_call_stays_in_the_guide(self):
        # One photo left that can close the post: no plan takes it, and the figure that names it is not put elsewhere.
        photos = [("lap-aurore", {"commonsTitle": "File:Aurora.jpg", "emblematic": True}, "Une aurore boréale."),
                  ("lap-village", {"commonsTitle": "File:Village.jpg", "emblematic": True}, "Le village sous la neige en décembre, à Rovaniemi."),
                  ("lap-cabane", {"commonsTitle": "File:Hut.jpg"}, "Une cabane sous la neige.")]
        media = reel_formats.Media(photos, [], reserve=2, cover="lap-aurore", emblematic=reel_formats.emblematic(photos))
        self.assertEqual(media.spare(), "lap-village")
        # It names a place: no free photo names it, so it gets no plan at all, neither in the first round nor after.
        self.assertIsNone(media.named("la maximale moyenne de décembre à Rovaniemi", None))
        self.assertEqual(media.left_for("la maximale moyenne de décembre à Rovaniemi"), [])
        self.assertFalse(media.shown_elsewhere("la cabine du train de nuit"))
        self.assertEqual(media.photo("la cabine du train de nuit")[1], "lap-cabane")
        self.assertEqual(media.closing()[1], "lap-village")

    def test_the_last_card_names_the_site_and_nothing_one_network_only_has(self):
        scenes, _ = self.build()
        self.assertEqual(scenes[-1]["note"], "Enregistrez cette vidéo pour votre voyage")
        self.assertEqual((scenes[-1]["button"], p.MOTION_BUTTON), ("voyagesansdetour.fr", "voyagesansdetour.fr"))
        self.assertTrue(all("button" not in scene for scene in scenes[:-1]))
        for text in (scenes[-1]["note"], scenes[-1]["button"]):
            self.assertNotRegex(text.lower(), r"\bbio\b|\breel\b|instagram|tiktok")

    def test_a_plan_of_fact_always_shows_a_number(self):
        scenes, _ = self.build(figures=[("Février à avril", "la meilleure fenêtre pour les aurores")] + self.FIGURES)
        self.assertNotIn("Février", json.dumps(scenes, ensure_ascii=False))
        self.assertTrue(all(any(c.isdigit() for c in scene["headline"][0]) for scene in scenes[1:-1]))

    def test_a_figure_with_its_own_date_is_labelled_with_that_date(self):
        tag, dated = "Guide Yucatán · sources du 11/11/2026", lambda label: reel_formats.dated_tag({"label": label}, "Guide Yucatán · sources du 11/11/2026")
        self.assertEqual(dated("le billet Mérida–Cancún aéroport en tarif touriste international, relevé en juillet 2026"), "Guide Yucatán · chiffre de juillet 2026")
        self.assertEqual(dated("Cancún–Playa del Carmen et Playa del Carmen–Tulum en tarif touriste international (octobre 2026)"), "Guide Yucatán · chiffre d’octobre 2026")
        self.assertEqual(dated("une nuit en capsule ; 7 000 à 20 000 ¥ la chambre en business hôtel (relevé de mars 2025)"), "Guide Yucatán · chiffre de mars 2025")
        self.assertEqual(dated("une torta de Guimarães chez Clarinha, rua de Santa Maria (Guia Repsol, mai 2026)"), "Guide Yucatán · chiffre de mai 2026")
        self.assertEqual(dated("le tarif plein, relevé le 3 août 2026"), "Guide Yucatán · chiffre du 3 août 2026")
        # A period of validity or a start is not the date the figure was read: the guide's own date stays.
        for label in ("la Treno Card de deux jours, du 2 novembre au 31 décembre 2026", "la balade en barque, depuis janvier 2026 (≈ 10,70 €)",
                      "l’entrée pour un étranger depuis le « boleto único » du 27 mars 2026 (105 pesos de tarif INAH inclus)", "le billet en siège réservé"):
            self.assertEqual(dated(label), tag)
        self.assertEqual(dated("la haute saison des baleines (mars, avril 2026)"), tag)  # two months: a period
        # A figure is never read after the guide's sources were: a later month is an opening or an event, not a reading.
        self.assertEqual(dated("l’entrée du nouveau musée, ouverture prévue (décembre 2026)"), tag)
        self.assertEqual(dated("le forfait de deux jours (novembre 2026)"), "Guide Yucatán · chiffre de novembre 2026")
        # A month in brackets after an opening, a festival or a deadline dates that event, even in the past.
        for label in ("l’entrée du festival des lanternes (novembre 2026)", "le billet, à l’ouverture de la nouvelle ligne (octobre 2026)",
                      "le billet du carnaval (février 2026)", "le tarif réduit, prévu (mai 2026)"):
            self.assertEqual(dated(label), tag)
        # An ordinary reading keeps its date, whatever the label says of hours or thresholds.
        for label in ("le musée, ouvert tous les jours (octobre 2026)", "le pass à partir de 12 ans (octobre 2026)", "le tarif jusqu’à 25 ans (octobre 2026)"):
            self.assertEqual(dated(label), "Guide Yucatán · chiffre d’octobre 2026")
        self.assertEqual(dated("les deux trajets, relevés d’octobre 2026"), "Guide Yucatán · chiffre d’octobre 2026")
        self.assertEqual(dated("le tarif plein, relevé le 11 novembre 2026"), "Guide Yucatán · chiffre du 11 novembre 2026")
        self.assertEqual(dated("le tarif plein, relevé le 15 novembre 2026"), tag)  # after the day the sources were read
        long = reel_formats.dated_tag({"label": "le forfait, relevé en septembre 2026"}, "Guide Parc national des Cinque Terre · sources du 11/11/2026")
        self.assertEqual(long, "Notre guide · chiffre de septembre 2026")

    def test_the_plan_quotes_the_date_its_label_gives(self):
        fare = ("977,50 pesos", "le billet du train de nuit en tarif touriste international, relevé en juillet 2026")
        scenes, _ = self.build(figures=[fare] + self.FIGURES[1:])
        plan = next(scene for scene in scenes if "977,50" in scene["headline"][0])
        self.assertEqual(plan["detail"], "le billet du train de nuit en tarif touriste international")  # the short label on screen
        self.assertEqual(plan["tag"], "Guide Laponie · chiffre de juillet 2026")
        self.assertEqual(plan["facts"][0]["excerpt"], " ".join(fare))  # the whole quote, so the date is read in the plan's source
        self.assertEqual({scene["tag"] for scene in scenes[1:-1] if scene is not plan}, {"Guide Laponie · sources du 24/10/2026"})

    def test_a_figure_that_no_photo_shows_stays_out_of_the_reel(self):
        scenes, lines = self.build()
        shown = {scene["headline"][0].strip("*").replace(reel_formats.NBSP, " "): scene["photo"] for scene in scenes[1:-1]}
        self.assertEqual(shown, {"59 €": "lap-train", "0 €": "lap-bureau", "30 à 60 €": "lap-traineau", "63 €": "lap-huskies", "−6 °C": "lap-village"})
        self.assertNotIn("42 €", shown)  # no photo of SantaPark: its price is not put over a cabin in the woods
        self.assertEqual([scene["badge"] for scene in scenes[1:-1]], [f"{n}/5" for n in range(1, 6)])
        self.assertEqual(len(lines), 5)

    def test_a_reviewed_photo_is_framed_around_its_subject(self):
        scenes, _ = self.build()
        frames = {scene["photo"]: scene["focus"] for scene in scenes}
        self.assertEqual(frames["lap-traineau"], [0.8, 0.55])
        self.assertEqual(frames["lap-train"], [0.5, 0.5])

    def test_a_stage_takes_the_photo_of_what_it_says_and_its_caption_line_carries_its_price(self):
        media = reel_formats.Media([("yuc-castillo", {"commonsTitle": "File:Templo el Castillo - Chichen Itza.jpg"}, "La pyramide de Chichén Itzá."),
                                    ("yuc-cenote", {"commonsTitle": "File:Cenote Ik Kil.jpg"}, "Un cenote entouré de lianes.")], [], cover="yuc-castillo")
        day = {"image": "yuc-cenote"}
        # The guide gives the cenote to the whole day; the plan only says "Chichén Itzá à l'ouverture, 697 pesos l'entrée".
        self.assertEqual(media.named("Chichén Itzá à l’ouverture l’entrée de Chichén Itzá pour un étranger", day)[0], "yuc-castillo")
        self.assertEqual(media.named("Ik Kil l’après-midi", day)[0], "yuc-cenote")
        self.assertEqual(media.named("Une journée sans rien de nommé", day)[0], "yuc-cenote")
        fact = {"value": "697 pesos", "label": "l’entrée de Chichén Itzá pour un étranger depuis le 27 mars 2026", "short": "l’entrée de Chichén Itzá pour un étranger"}
        step = {"kicker": "Jour 3", "lines": ["Chichén Itzá", "à l’ouverture"], "fact": fact}
        self.assertEqual(reel_formats.stage_line(step),
                         "📍 Jour 3 : Chichén Itzá à l’ouverture · 697 pesos l’entrée de Chichén Itzá pour un étranger depuis le 27 mars 2026")
        long = {**fact, "label": fact["label"] + " " + "x" * 120}
        self.assertEqual(reel_formats.stage_line({**step, "fact": long}), "📍 Jour 3 : Chichén Itzá à l’ouverture · 697 pesos l’entrée de Chichén Itzá pour un étranger")
        # Each line can be said shorter, as its plan says it: a caption too long shortens every stage before it drops one.
        self.assertEqual(reel_formats.stage_line(step).short, "📍 Jour 3 : Chichén Itzá à l’ouverture · 697 pesos l’entrée de Chichén Itzá pour un étranger")

    def test_a_caption_too_long_says_every_stage_shorter_before_it_drops_one(self):
        # Review of 12/11/2026: the screen promised "4 étapes clés" and the caption gave three, Tulum cut for length.
        stages = [reel_formats.Line(f"📍 Jour {n} : étape · 100 pesos " + "x" * 120, f"📍 Jour {n} : étape · 100 pesos l’entrée") for n in range(1, 5)]
        scenario = {"kind": "reel", "channel": "instagram", "id": "ig-" + "a" * 70 + "-2026-11-15",
                    "caption": {"hook": "🗺️ " + "h" * 140, "lines": stages, "cta": "c" * 150, "hashtags": ["#Mexique", "#Voyage"]}}
        self.assertGreater(len(p.caption(scenario, {})), a.CAPTION_MAX)
        fitted = a.fitted_caption(scenario, {})
        self.assertEqual(fitted["caption"]["lines"], [stage.short for stage in stages])
        self.assertTrue(all(type(line) is str for line in fitted["caption"]["lines"]))
        self.assertLessEqual(len(p.caption(fitted, {})), a.CAPTION_MAX)


class FoundPhotoTests(unittest.TestCase):
    """What the search may keep (verification of 12/11/2026: Porto Covo for Porto, coatis for Yucatán)."""

    def test_a_namesake_in_the_same_country_is_refused(self):
        porto = guide(slug="porto-3-jours", destination="Porto", country="portugal")
        chapel = "File:Azulejo facade of the Capela das Almas in Porto (4).jpg"
        hits = ["File:Porto Covo Outubro 2014-3.jpg", "File:Foggy Fanal forest in Seixal, Porto Moniz, Madeira, 2023 May.jpg", chapel,
                "File:Dragonfly Porto Covo August 2021-4.jpg", "File:Porto de Mós castle.jpg"]
        found = media_library.featured_candidates(porto, ["Porto"], "Portugal", lambda query: hits, ["Portugal"])
        self.assertEqual([candidate["title"] for candidate in found], [chapel])
        # A title may be silent while the categories say where the picture was taken.
        beach = {"commonsTitle": "File:Atlantic waves near Porto.jpg", "categories": "Beaches of Porto Covo|Water waves of Portugal", "camera": "NIKON D800E"}
        there = {"commonsTitle": chapel, "categories": "Featured pictures of Porto|Azulejos in Portugal", "camera": "NIKON D3300"}
        self.assertFalse(media_library.Photos.acceptable(found[0], beach, fetched=True))
        self.assertTrue(media_library.Photos.acceptable(found[0], there, fetched=True))
        self.assertEqual(media_library.homonyms(guide()), [])

    def test_an_animal_a_plant_or_a_match_is_not_a_photo_of_the_place(self):
        other = media_library.shows_something_else
        for title, categories in (
                ("File:194 White-nosed coati at the beach in Yucatán Photo by Giles Laurent.jpg", "Beaches of Yucatán|Nasua narica in Mexico|Mammals of Mexico"),
                ("File:196 Laughing gulls at the beach in Yucatán Photo by Giles Laurent.jpg", "Leucophaeus atricilla in flight|Beaches of Yucatán"),
                ("File:Tapaculo (Bothus podas), franja marina Teno-Rasca, Tenerife, España, 2022-01-05, DD 64.jpg", "Protected areas of Spain"),
                ("File:London Bees v Millwall Lionesses, 15 April 2017 (062).jpg", "Featured pictures of sports in London"),
                ("File:Red and white tulip at Myddelton House, Enfield, London.jpg", "Featured pictures of flowers"),
                ("File:Pot-bellied pigs in Lisbon Zoo 2008.jpg", "Featured pictures of Lisbon"),
                ("File:Red admiral on purple coneflower in New York.jpg", "Nymphalidae of New York (state)")):
            self.assertTrue(other({"commonsTitle": title, "categories": categories}), title)
        for title, categories in (
                ("File:Vista de Garachico, Tenerife, España, 2012-12-13, DD 05.jpg", "Featured pictures of Tenerife"),
                ("File:London Eye at Night (long exposure).JPG", "London Eye at night"),
                ("File:Ribeira (Old town), Porto.jpg", "Featured pictures of Porto"),
                ("File:Long Island City New York May 2015 panorama 3.jpg", "East River (New York)|Bird's-eye views of New York City"),
                ("File:Lisbon (Lisboa) historic elevator Santa Justa.jpg", "Fishing boats in Lisbon|Featured pictures of Lisbon")):
            self.assertFalse(other({"commonsTitle": title, "categories": categories}), title)
        candidate = {"countryNames": ["Mexique", "Mexico"], "homonyms": []}
        coati = {"commonsTitle": "File:194 White-nosed coati at the beach in Yucatán.jpg", "categories": "Beaches of Yucatán|Mammals of Mexico", "camera": "ILCE-1"}
        self.assertFalse(media_library.Photos.acceptable(candidate, coati, fetched=True))

    def test_only_a_photo_of_the_site_or_one_marked_by_hand_may_close_a_post(self):
        mark = media_library.closing_mark
        self.assertEqual(mark({"emblematic": True}, {"file": "a.jpg"}), {"file": "a.jpg", "emblematic": True})  # the site's photo
        # Found by the search: never, and said so in the record, whatever an earlier post recorded.
        self.assertEqual(mark({"automatic": True}, {"file": "a.jpg", "emblematic": True}), {"file": "a.jpg", "automatic": True})
        self.assertEqual(mark({}, {"file": "a.jpg", "emblematic": True}), {"file": "a.jpg", "emblematic": True})  # marked in reviewed.json
        self.assertEqual(mark({}, {"file": "a.jpg"}), {"file": "a.jpg"})                                        # added for one plan
        # A photo of the site that only illustrates one paragraph (a station sign, a hotel terrace) closes nothing.
        self.assertEqual(mark({"emblematic": False}, {"file": "a.jpg", "emblematic": True, "automatic": True}), {"file": "a.jpg"})
        article = guide(cover="japon-fuji-chureito", sections=[{"title": "Le train", "image": "japon-shinkansen"}])
        site = {photo_id: {"source_page": f"https://commons.wikimedia.org/wiki/File:{photo_id}.jpg", "alt_fr": "Une photo du Japon."}
                for photo_id in ("japon-fuji-chureito", "japon-shinkansen", "japon-tokyo-shibuya")}
        marks = {c["id"]: c["emblematic"] for c in media_library.photo_candidates(article, site, "Japon")}
        self.assertEqual(marks, {"japon-fuji-chureito": True, "japon-shinkansen": False, "japon-tokyo-shibuya": True})
        # A photo of the site whose subject is off centre says where it is: the vertical frame is cut around it.
        palace = {"thailande-bangkok-grand-palais": {"source_page": "https://commons.wikimedia.org/wiki/File:Palace.jpg", "alt_fr": "Le Grand Palais de Bangkok."}}
        thai = guide(slug="thailande", cover="thailande-bangkok-grand-palais", sections=[])
        self.assertEqual(media_library.photo_candidates(thai, palace, "Thaïlande")[0]["focus"], [0.72, 0.7])
        got = media_library.gather_photos(thai, 1, mock.Mock(shared={}, get=lambda candidate: ("thailande-bangkok-grand-palais", {"file": "a.jpg"})), palace, "Thaïlande", lambda query: [])
        self.assertEqual(got[0][1], {"file": "a.jpg", "emblematic": True, "focus": [0.72, 0.7]})
        published = {photo["id"] for photo in json.loads((HERE.parents[1] / "site-src" / "image-sources.json").read_text())["photos"]}
        self.assertEqual(media_library.NOT_A_CLOSING - published, set())  # every listed photo is one the site publishes
        f = Fixture([guide()], photos=5)
        self.addCleanup(f.cleanup)
        found = "File:Kyoto Kinkaku-ji in autumn.jpg"
        made = f.run(limit=30, searcher=lambda query: [found] if "Featured_pictures" in query else [])["created"]
        reel = f.scenario(next(c["id"] for c in made if c["kind"] == "reel"))
        records = json.loads((f.root / a.AUTO / reel["id"] / "photos.json").read_text())["photos"]
        closing = records[reel["scenes"][-1]["photo"]]
        self.assertTrue(closing["emblematic"])
        self.assertNotEqual(closing["commonsTitle"], found)
        self.assertNotIn("emblematic", next((r for r in records.values() if r["commonsTitle"] == found), {}))


class PhotoPostTests(unittest.TestCase):
    """A photo post follows the reels' rules (verification of 12/11/2026: two prices over another site of Yucatán)."""

    PHOTOS = [("yuc-castillo", {"commonsTitle": "File:Templo el Castillo - Chichen Itza.jpg", "emblematic": True}, "La pyramide d’El Castillo, à Chichén Itzá."),
              ("yuc-cenote", {"commonsTitle": "File:Cenote Ik Kil.jpg", "emblematic": True}, "Un cenote entouré de lianes, dans le Yucatán."),
              ("yuc-tulum", {"commonsTitle": "File:Tulum.jpg", "emblematic": True}, "Les ruines de Tulum au-dessus de la mer."),
              ("yuc-merida", {"commonsTitle": "File:Catedral.jpg"}, "La cathédrale de Mérida."),
              ("yuc-train", {"commonsTitle": "File:Tren Maya.jpg"}, "Une rame du Tren Maya en gare de Teya."),
              ("yuc-uxmal", {"commonsTitle": "File:Uxmal.jpg", "emblematic": True}, "La pyramide du Devin à Uxmal.")]
    FIGURES = [("10 jours", "pour enchaîner Valladolid, Chichén Itzá, Mérida, Uxmal et Tulum sans courir"),
               ("977,50 pesos", "le billet Mérida–Cancún aéroport en tarif touriste international, relevé en juillet 2026"),
               ("697 pesos", "l’entrée de Chichén Itzá pour un étranger"),
               ("120 km", "entre Mérida et la gare de Teya, selon le site officiel du Tren Maya"),
               ("45 jours", "la durée du passe ferroviaire"),
               ("232 et 246 pesos", "Cancún–Playa del Carmen et Playa del Carmen–Tulum (octobre 2026)")]

    def scenes(self, figures=None, photos=None):
        article = guide(shortTitle="Yucatán en 10 jours", destination="Yucatán", country="mexique", sourcesCheckedOn="2026-11-11", sections=[])
        facts = [{"value": value, "label": label, "excerpt": value + " " + label, "section": None} for value, label in figures or self.FIGURES]
        return a.scenes_for(article, a.Post("facebook", "carousel"), facts, list(photos or self.PHOTOS), "Phrase d’ouverture.", "Yucatán", "Mexique")

    def test_each_figure_takes_the_photo_that_shows_it_and_the_title_is_not_said_again(self):
        scenes = self.scenes()
        shown = {scene["headline"][0].strip("*"): scene["photo"] for scene in scenes[1:-1]}
        # The fare from Mérida to Cancún goes over Mérida, not over the train: that train stands "en gare de Teya",
        # which is none of the two ends of the journey. The distance to Teya goes over it.
        self.assertEqual(shown, {"977,50 pesos": "yuc-merida", "697 pesos": "yuc-castillo", "120 km": "yuc-train", "232 et 246 pesos": "yuc-tulum"})
        self.assertNotIn("10 jours", shown)   # the title said again
        # The entrance fee took the cover it names: the next photo of the guide opens the post, another one closes it.
        self.assertEqual((scenes[0]["photo"], scenes[-1]["photo"]), ("yuc-cenote", "yuc-uxmal"))
        self.assertEqual(scenes[0]["headline"][-1], "*4 chiffres* à connaître")
        tags = {scene["headline"][0].strip("*"): scene["tag"] for scene in scenes[1:-1]}
        self.assertEqual(tags["977,50 pesos"], "Guide Yucatán · chiffre de juillet 2026")
        self.assertEqual(tags["232 et 246 pesos"], "Guide Yucatán · chiffre d’octobre 2026")
        self.assertEqual(tags["697 pesos"], "Guide Yucatán · sources du 11/11/2026")

    def test_a_figure_whose_photo_another_plan_took_is_never_put_over_another_place(self):
        # Two figures name Chichén Itzá and one photo shows it: the second stays in the guide rather than go over Uxmal.
        figures = [("697 pesos", "l’entrée de Chichén Itzá pour un étranger"), ("3 h", "la visite de Chichén Itzá à l’ouverture")] + self.FIGURES[1:2] + self.FIGURES[3:]
        scenes = self.scenes(figures)
        shown = {scene["headline"][0].strip("*").replace(reel_formats.NBSP, " "): scene["photo"] for scene in scenes[1:-1]}
        self.assertEqual(shown["697 pesos"], "yuc-castillo")
        self.assertNotIn("3 h", shown)
        with self.assertRaisesRegex(reel_formats.Held, "not_enough_figures_with_their_photo"):
            self.scenes(figures[:2] + [("2 h", "la baignade au pied de la pyramide de Chichén Itzá"), ("4 h", "le retour depuis Chichén Itzá"), ("5 h", "la nuit à Chichén Itzá")])


class CaptionTextTests(unittest.TestCase):
    def test_an_enumeration_is_never_cut_before_its_last_items(self):
        label = "pour enchaîner Valladolid, Chichén Itzá, Mérida, Uxmal et Tulum sans courir"
        self.assertEqual(reel_formats.short_label(label), label)
        # "de la Bahia, des tombeaux saadiens ou d’El Badi" is one list: cut after its first item, the plan would name
        # the palace alone over a photo of the tombs.
        fee = "l’entrée de la Bahia, des tombeaux saadiens ou d’El Badi pour un adulte étranger, de 9 h à 17 h"
        self.assertEqual(reel_formats.short_label(fee), fee)
        self.assertEqual(reel_formats.short_label("le budget serré pour 14 jours et 13 nuits (154 120 ¥), capsule ou dortoir, konbini et un seul long trajet en shinkansen"),
                         "le budget serré pour 14 jours et 13 nuits (154 120 ¥)")
        self.assertEqual(reel_formats.short_label("le trajet en Tren Maya de Mérida à l’aéroport de Cancún, avec arrêts à Izamal, Chichén Itzá et Valladolid (Por Esto, juillet 2026)"),
                         "le trajet en Tren Maya de Mérida à l’aéroport de Cancún")

    def test_a_caption_line_reads_as_a_sentence(self):
        line = reel_formats.caption_line
        self.assertEqual(line({"value": "180", "label": "exposants et plus au marché de Noël de Bryant Park"}), "📍 180 exposants et plus au marché de Noël de Bryant Park")
        self.assertEqual(line({"value": "120 km", "label": "entre Mérida et la gare de Chichén Itzá"}), "📍 120 km entre Mérida et la gare de Chichén Itzá")
        self.assertEqual(line({"value": "59 €", "label": "la cabine privative du train de nuit"}), "💶 59 € : la cabine privative du train de nuit")
        self.assertEqual(line({"value": "45 jours", "label": "de séjour sans visa"}), "⏱️ 45 jours de séjour sans visa")
        self.assertEqual(line({"value": "287", "label": "marches jusqu’au sommet de la tour"}), "🥾 287 marches jusqu’au sommet de la tour")


def figures(pairs, sections=None):
    """Key figures as usable_facts gives them to the formats."""
    return [{"value": value, "label": label, "short": reel_formats.short_label(label), "shortExcerpt": value + " " + reel_formats.short_label(label),
             "excerpt": value + " " + label, "section": (sections or {}).get(value)} for value, label in pairs]


class RealGuideTests(unittest.TestCase):
    """Posts the generator built for published guides, as found by the review of the pull request (12/11/2026)."""

    AMALFI = [("amalfi-positano", {"commonsTitle": "File:Positano (Italy) 02.jpg", "emblematic": True}, "Les maisons de Positano en cascade jusqu’à la plage."),
              ("amalfi-ferry", {"commonsTitle": "File:Traghetto Amalfi - Salerno (9704145024).jpg"}, "Un ferry entre Amalfi et Salerne, au pied des falaises."),
              ("amalfi-sentiero", {"commonsTitle": "File:Sentiero degli Dei 15 Campania.jpg", "emblematic": True}, "Le sentier des Dieux à Agerola, au-dessus de la mer."),
              ("amalfi-ville", {"commonsTitle": "File:Amalfi (Italy).jpg", "emblematic": True}, "Amalfi vue de la mer, entre falaises et port."),
              ("cote-amalfitaine-1ea2dd94", {"commonsTitle": "File:Atrani (Costiera Amalfitana, 23-8-2011).jpg", "automatic": True},
               "Côte amalfitaine (Italie) : Atrani (Costiera Amalfitana, 23-8-2011).")]
    AMALFI_FIGURES = [("1 h 39", "Rome → Salerne en Italo, 10 trains par jour, dès 14,90 €"), ("12 €", "le ferry Travelmar Salerne → Amalfi, 35 minutes"),
                      ("17 €", "Salerne → Positano en ferry, 70 minutes"), ("10 €", "le ticket bus SITA COSTIERASITA, illimité pendant 24 h"),
                      ("7,8 km", "le sentier des Dieux, de Bomerano à Nocelle, en 3 à 4 heures"),
                      ("20 €", "Pompéi (25 € avec la villa des Mystères), gratuit le 1er dimanche du mois")]
    FERRIES = {"title": "Arriver : Salerne plutôt que Naples", "image": "amalfi-ferry",
               "table": {"headers": ["Ferry Travelmar 2026", "Prix", "Durée"],
                         "rows": [["Salerne → Amalfi", "12 €", "35 min"], ["Salerne → Positano", "17 €", "70 min"], ["Amalfi → Positano", "10 €", "25 min"],
                                  ["Amalfi → Minori", "5 €", "—"], ["Boucle Salerne–Positano–Amalfi–Salerne", "39 €", "journée"]]}}
    MARRAKECH = [("marrakech-place-jemaa-el-fna", {"commonsTitle": "File:Jamaa El Fna, Marrakesh, Morocco, 20250124 1804 7017.jpg", "emblematic": True},
                  "La place Jemaa el-Fna en fin de journée, entre parasols verts et étals, au cœur de la médina de Marrakech."),
                 ("marrakech-bahia", {"commonsTitle": "File:Bahia Palace large court.jpg", "emblematic": True}, "La grande cour carrelée de zelliges du palais de la Bahia, à Marrakech."),
                 ("marrakech-majorelle", {"commonsTitle": "File:Le jardin des majorelle 16.JPG", "emblematic": True}, "La villa bleue du jardin Majorelle."),
                 ("marrakech-85ffbf38", {"commonsTitle": "File:Lamp maker, Medina of Marrakech.jpg", "automatic": True}, "Marrakech (Maroc) : Lamp maker, Medina of Marrakech."),
                 ("marrakech-fecfeec6", {"commonsTitle": "File:Maroc Marrakech Saadiens Luc Viatour 5.jpg", "automatic": True}, "Marrakech (Maroc) : Maroc Marrakech Saadiens Luc Viatour 5.")]

    def amalfi_table_reel(self):
        article = guide(slug="cote-amalfitaine-sans-voiture", country="italie", cover="amalfi-positano", destination="Côte amalfitaine",
                        shortTitle="La côte amalfitaine sans voiture", category="Itinéraires", sections=[self.FERRIES])
        read = p.normalized("Prix " + " ".join(row[0] + " " + row[1] for row in self.FERRIES["table"]["rows"]))
        return reel_formats.build("tableau", article, figures(self.AMALFI_FIGURES), list(self.AMALFI), [], "Phrase d’ouverture.", "Côte amalfitaine",
                                  "Italie · Côte amalfitaine", "Guide Côte amalfitaine · sources du 24/10/2026", ["La côte amalfitaine", "sans voiture"], read)

    def test_the_amalfi_coast_table_reel_opens_on_its_cover_and_puts_no_amalfi_fare_over_positano(self):
        scenes, _ = self.amalfi_table_reel()
        self.assertEqual(scenes[0]["photo"], "amalfi-positano")  # the guide's cover, not the view of Atrani the search found
        self.assertEqual((scenes[1]["layout"], scenes[1]["photo"]), ("table", "amalfi-ferry"))
        named = [scene["photo"] for scene in scenes[2:-1] if "Amalfi" in scene["detail"]]
        self.assertNotIn("amalfi-positano", named)
        # The ferry fares are in the table, over the ferry: said again, they would go over another village.
        shown = {scene["headline"][0].strip("*").replace(reel_formats.NBSP, " "): scene["photo"] for scene in scenes[2:-1]}
        self.assertEqual(shown, {"10 €": "cote-amalfitaine-1ea2dd94", "7,8 km": "amalfi-sentiero"})
        self.assertEqual(scenes[-1]["photo"], "amalfi-ville")

    def test_the_prefix_all_the_photos_share_names_nothing(self):
        media = reel_formats.Media(list(self.AMALFI), [], reserve=2, cover="amalfi-positano", emblematic=reel_formats.emblematic(self.AMALFI),
                                   everywhere="Italie · Côte amalfitaine")
        self.assertEqual(media.family, "amalfi")
        shared = {photo[0]: media.shared(photo, {"amalfi"}) for photo in self.AMALFI}
        self.assertEqual(shared, {"amalfi-positano": 0, "amalfi-ferry": 1, "amalfi-sentiero": 0, "amalfi-ville": 1, "cote-amalfitaine-1ea2dd94": 0})
        # In a guide of several towns the prefix is the town: it tells the photos apart.
        towns = [("seville-alcazar", {"commonsTitle": "File:A.jpg"}, "Une porte du palais."), ("grenade-myrtes", {"commonsTitle": "File:B.jpg"}, "La cour des Myrtes.")]
        self.assertEqual(reel_formats.Media(towns, []).named("le Real Alcázar de Séville", None)[0], "seville-alcazar")

    def test_a_kind_of_place_alone_ties_no_figure_to_a_photo(self):
        media = reel_formats.Media(list(self.MARRAKECH), [], reserve=2, cover="marrakech-place-jemaa-el-fna",
                                   emblematic=reel_formats.emblematic(self.MARRAKECH), everywhere="Maroc · Marrakech")
        # "Médina" names no monument: the fee of the Saadian tombs goes over the tombs, not over a lamp maker "in the medina".
        monument = "l’entrée d’un grand monument de la médina (Bahia, tombeaux saadiens, El Badi) selon les sources"
        self.assertEqual(media.named(monument, None)[0], "marrakech-bahia")
        # Once the garden has its plan, the palace is the last photo that can close the post: the tombs take the fee.
        media.photo("le jardin Majorelle selon les relevés 2023-2024")
        self.assertEqual((media.spare(), media.named(monument, None)[0]), ("marrakech-bahia", "marrakech-fecfeec6"))
        self.assertIsNone(media.named("le prix attendu d’un petit taxi de l’aéroport à la médina", None))
        porto = [("porto-vue-clerigos", {"commonsTitle": "File:View of Porto Cathedral from Clérigos Tower, 20250605 1724 9965.jpg"},
                  "La cathédrale et les toits de Porto vus depuis la tour des Clérigos."),
                 ("porto-metro-aeroport", {"commonsTitle": "File:Aeroporto metro station (Porto) - 3.jpg"}, "La station de métro Aeroporto, terminus de la ligne E à Porto."),
                 ("porto-rabelo", {"commonsTitle": "File:View of Ribeira (21).jpg"}, "Un bateau rabelo sur le Douro, face aux façades de la Ribeira.")]
        city = reel_formats.Media(porto, [], everywhere="Portugal · Porto")
        self.assertEqual(city.named("l’Andante Tour 3 : métro, bus et trains urbains pendant 72 h", None)[0], "porto-metro-aeroport")
        self.assertEqual(city.named("la tour des Clérigos et son musée, billet de jour", None)[0], "porto-vue-clerigos")
        # The photo the guide put beside a day is that day's photo when the two share a kind of place: "Le pont en
        # métro" goes over the bridge, not over the quays that share "Douro" with it.
        days = porto + [("porto-ponte-luis", {"commonsTitle": "File:Puente Don Luis I, Oporto, Portugal, 2012-05-09, DD 13.JPG"},
                         "Le pont Luís I et la Ribeira vus depuis la Serra do Pilar, à Gaia."),
                        ("porto", {"commonsTitle": "File:Porto-Panorama de Ribeira-Rabelos-20120910.jpg"},
                         "Les façades de Ribeira au bord du Douro à Porto, avec des bateaux rabelos au premier plan.")]
        crossing = "Le pont en métro de métro D au-dessus du Douro"
        # The fact names the Douro: it goes over a photo whose record names the Douro, with or without the section's
        # own photo (the bridge, whose caption does not say which river it spans), and never over the airport's metro.
        for section in ({"image": "porto-ponte-luis"}, None):
            self.assertIn(reel_formats.Media(days, [], everywhere="Portugal · Porto").named(crossing, section)[0], ("porto-rabelo", "porto"))
        # The section's photo gives way to one that shares all it shares and more: the Grand Palace, not Wat Arun, for
        # the fee of the Grand Palace (both are in Bangkok); it keeps a text another photo only half shares.
        bangkok = [("thailande-wat-arun", {"commonsTitle": "File:Wat Arun.jpg"}, "Le temple Wat Arun au bord du fleuve Chao Phraya, à Bangkok."),
                   ("thailande-bangkok-grand-palais", {"commonsTitle": "File:Roof.jpg"}, "Les toits du Grand Palais de Bangkok au coucher du soleil."),
                   ("thailande-ferry", {"commonsTitle": "File:Ferry.jpg"}, "Un ferry sur le fleuve Chao Phraya.")]
        thai = lambda: reel_formats.Media(bangkok, [], everywhere="Thaïlande")
        self.assertEqual(thai().named("le Grand Palais de Bangkok et le Wat Phra Kaew", {"image": "thailande-wat-arun"})[0], "thailande-bangkok-grand-palais")
        self.assertEqual(thai().named("la traversée du fleuve en ferry depuis Bangkok", {"image": "thailande-wat-arun"})[0], "thailande-wat-arun")
        villa = ("amalfi-ravello", {"commonsTitle": "File:Villa Cimbrone Ravello 12.JPG"}, "Les jardins de la villa Cimbrone, à Ravello.")
        self.assertEqual(reel_formats.words_shown(villa, reel_formats.words_of("Pompéi (25 € avec la villa des Mystères)")), 0)
        self.assertEqual(reel_formats.words_shown(villa, reel_formats.words_of("la villa Cimbrone et ses jardins")), 3)

    def test_a_stage_takes_the_photo_of_the_place_it_names_before_the_photo_of_what_its_figure_names(self):
        photos = [("yucatan-cenote", {"commonsTitle": "File:Cenote Ik Kil.jpg", "emblematic": True}, "Un cenote entouré de lianes."),
                  ("yucatan-merida-cathedrale", {"commonsTitle": "File:Catedral.jpg"}, "La cathédrale de Mérida."),
                  ("yucatan-tren-maya-merida", {"commonsTitle": "File:Tren Maya.jpg"}, "Une rame du Tren Maya en gare de Mérida-Teya."),
                  ("yucatan-valladolid-calzada", {"commonsTitle": "File:Calzada de los Frailes.jpg"}, "La calzada de los Frailes, à Valladolid."),
                  ("yucatan-chichen-itza", {"commonsTitle": "File:El Castillo, Chichen Itza.jpg"}, "La pyramide d’El Castillo, à Chichén Itzá."),
                  ("yucatan-tulum", {"commonsTitle": "File:Tulum.jpg"}, "Les ruines de Tulum au-dessus de la mer."),
                  ("yucatan-uxmal-pyramide", {"commonsTitle": "File:Uxmal.jpg", "emblematic": True}, "La pyramide du Devin à Uxmal.")]
        days = [{"title": "Jours 1-2 — Valladolid"}, {"title": "Jour 3 — Chichén Itzá à l’ouverture", "image": "yucatan-cenote"},
                {"title": "Jour 7 — Mérida–Tulum en train direct"}, {"title": "Jours 8-10 — Tulum et le retour", "image": "yucatan-tulum"}]
        pairs = [("1 h 43", "de l’aéroport de Cancún à Valladolid en Tren Maya"), ("697 pesos", "l’entrée de Chichén Itzá pour un étranger"),
                 ("5 h 16", "le train direct Mérida Teya → Tulum de 7 h"), ("265 pesos", "les ruines de Tulum pour un étranger")]
        facts = figures(pairs, {value: day for (value, _), day in zip(pairs, days)})
        article = guide(slug="yucatan", country="mexique", cover="yucatan-cenote", destination="Yucatán", shortTitle="Yucatán en 10 jours", sections=days)
        read = p.normalized(" ".join(day["title"] for day in days))
        scenes, _ = reel_formats.build("itineraire", article, facts, photos, [], "Phrase d’ouverture.", "Yucatán", "Mexique · Yucatán",
                                       "Guide Yucatán · sources du 12/11/2026", ["Yucatán en", "10 jours"], read)
        # "Valladolid" is shown over Valladolid, though the train photo shares more words with the figure of that day.
        # The train to Tulum takes the train, not the ruins the guide put beside the days in Tulum, nor the cathedral that
        # shares "Mérida" as well: what the plan says of its figure decides between the two. Four stages, four figures.
        self.assertEqual([(scene["headline"], scene["photo"]) for scene in scenes[1:-1]],
                         [(["Valladolid"], "yucatan-valladolid-calzada"), (["Chichén Itzá", "à l’ouverture"], "yucatan-chichen-itza"),
                          (["Mérida–Tulum en", "train direct"], "yucatan-tren-maya-merida"), (["Tulum et le retour"], "yucatan-tulum")])
        self.assertEqual(scenes[0]["headline"][-1], "*jour par jour*")
        self.assertIn("*265 pesos*", scenes[4]["detail"])
        # One thing said per stage: its figure. The title of the day it also quotes is not a second one.
        self.assertEqual(len(reel_formats.said_by(scenes[0], scenes[1:-1], "Phrase d’ouverture.")), 4)
        with self.assertRaisesRegex(reel_formats.Held, "not_enough_stages"):
            reel_formats.build("itineraire", {**article, "sections": days[:3]}, facts[:3], photos, [], "Phrase d’ouverture.", "Yucatán", "Mexique · Yucatán",
                               "Guide Yucatán · sources du 12/11/2026", ["Yucatán en", "10 jours"], read)

    def test_a_table_is_named_by_its_section_and_carries_the_price_of_what_it_lists(self):
        trains = {"title": "Le train de nuit pour Chiang Mai", "image": "thailande-train-nuit",
                  "table": {"headers": ["Train", "Départ de Bangkok", "Arrivée à Chiang Mai", "2e classe"],
                            "rows": [["N° 7 (autorail de jour)", "7 h 30", "17 h 50", "558 ฿ assis"], ["N° 9 (couchettes récentes)", "18 h 40", "7 h 15", "938 / 1 038 ฿"],
                                     ["N° 13 (couchettes)", "20 h 05", "8 h 45", "768 / 838 ฿"], ["N° 51 (couchettes)", "22 h 30", "11 h 40", "728 / 798 ฿"]]}}
        photos = [("thailande-phi-phi", {"commonsTitle": "File:Phi Phi.jpg", "emblematic": True}, "La plage de Ko Phi Phi Don."),
                  ("thailande-train-nuit", {"commonsTitle": "File:Sleeper.jpg"}, "Une voiture-couchettes d’un train de nuit thaïlandais."),
                  ("thailande-bangkok-grand-palais", {"commonsTitle": "File:Roof.jpg"}, "Les toits du Grand Palais de Bangkok au coucher du soleil."),
                  ("thailande-railay", {"commonsTitle": "File:Railay.jpg"}, "La plage de Railay, près de Krabi."),
                  ("thailande-wat-arun", {"commonsTitle": "File:Wat Arun.jpg", "emblematic": True}, "Le temple Wat Arun au bord du fleuve Chao Phraya.")]
        pairs = [("938 bahts", "la couchette haute climatisée de 2e classe du train 9 (≈ 25 €, tarif SRT de novembre 2026)"),
                 ("500 bahts", "le Grand Palais de Bangkok et le Wat Phra Kaew, de 8 h 30 à 16 h 30 (≈ 13 €)"),
                 ("330 bahts", "le minibus Phantip de Surat Thani à Krabi, 6 départs de 9 h à 16 h 30, 3 h de route")]
        article = guide(slug="thailande", country="thailande", cover="thailande-phi-phi", destination="Thaïlande", shortTitle="La Thaïlande en 2 semaines", sections=[trains])
        read = p.normalized("Départ de Bangkok " + " ".join(row[0] + " " + row[1] for row in trains["table"]["rows"]))
        scenes, lines = reel_formats.build("tableau", article, figures(pairs), photos, [], "Phrase d’ouverture.", "Thaïlande", "Thaïlande",
                                           "Guide Thaïlande · sources du 12/11/2026", ["La Thaïlande", "en 2 semaines"], read)
        table = scenes[1]
        # The plan says where the trains go (its section) and what the berth costs (the price that its own photo shows).
        self.assertEqual((table["layout"], table["kicker"], table["headline"], table["photo"]), ("table", "Le train de nuit pour Chiang Mai", ["Départ de Bangkok"], "thailande-train-nuit"))
        self.assertEqual(table["detail"], "*938 bahts* la couchette haute climatisée de 2e classe du train 9")
        self.assertIn("938 bahts la couchette haute climatisée de 2e classe du train 9", [fact["excerpt"] for fact in table["facts"]])
        self.assertEqual(lines[0], "🚆 938 bahts : la couchette haute climatisée de 2e classe du train 9 (≈ 25 €, tarif SRT de novembre 2026)")
        # The caption says what the four times are: departures from Bangkok of the trains for Chiang Mai.
        self.assertEqual(lines[1:3], ["📅 Le train de nuit pour Chiang Mai · Départ de Bangkok — N° 7 (autorail de jour) : 7 h 30", "📅 N° 9 (couchettes récentes) : 18 h 40"])
        # A section whose title names nothing the photo shows ("Arriver", "En bref", "Le parcours") leaves the place above the table.
        for title in ("Arriver", "En bref", "Le parcours"):
            scenes, lines = reel_formats.build("tableau", {**article, "sections": [{**trains, "title": title}]}, figures(pairs), photos, [], "Phrase d’ouverture.", "Thaïlande", "Thaïlande",
                                               "Guide Thaïlande · sources du 12/11/2026", ["La Thaïlande", "en 2 semaines"], read)
            self.assertEqual((scenes[1]["kicker"], scenes[1]["photo"]), ("Thaïlande", "thailande-train-nuit"), title)
            self.assertIn("📅 Départ de Bangkok — N° 7 (autorail de jour) : 7 h 30", lines)
        self.assertEqual([scene["headline"][0].strip("*").replace(reel_formats.NBSP, " ") for scene in scenes[2:-1]], ["500 bahts", "330 bahts"])  # not said twice
        # A price the table already gives in a row is not written under it again.
        rows = dict(trains, table={"headers": ["Train", "2e classe"], "rows": [["N° 7 (autorail de jour)", "558 bahts"], ["N° 9 (couchettes récentes)", "938 bahts"], ["N° 13 (couchettes)", "768 bahts"]]})
        priced = p.normalized("2e classe " + " ".join(row[0] + " " + row[1] for row in rows["table"]["rows"]))
        scenes, _ = reel_formats.build("tableau", {**article, "sections": [rows]}, figures(pairs), photos, [], "Phrase d’ouverture.", "Thaïlande", "Thaïlande",
                                       "Guide Thaïlande · sources du 12/11/2026", ["La Thaïlande", "en 2 semaines"], priced)
        self.assertNotIn("detail", scenes[1])
        # A price that another photo shows as well is not the table's own: it stays a plan of its own.
        twin = photos[:2] + [("thailande-gare", {"commonsTitle": "File:Station.jpg"}, "Un train en gare de Bangkok.")] + photos[2:]
        scenes, _ = reel_formats.build("tableau", article, figures(pairs), twin, [], "Phrase d’ouverture.", "Thaïlande", "Thaïlande",
                                       "Guide Thaïlande · sources du 12/11/2026", ["La Thaïlande", "en 2 semaines"], read)
        self.assertNotIn("detail", scenes[1])

    def test_a_table_whose_first_column_repeats_names_its_rows_with_the_next_one(self):
        # Review of 12/11/2026: "Alfa Pendular : Turística", "Alfa Pendular : Conforto" gave a table with no fare in it.
        fares = {"title": "Alfa Pendular ou Intercidades : 7,65 € d’écart", "image": "train-oriente",
                 "table": {"headers": ["Train", "Classe", "Aller simple 2026", "Durée type"],
                           "rows": [["Alfa Pendular", "Turística", "35,70 €", "≈ 2 h 58"], ["Alfa Pendular", "Conforto", "49,90 €", "≈ 2 h 58"], ["Intercidades", "2e classe", "28,05 €", "≈ 3 h 23"]]}}
        photos = [("train-alfa-pendular", {"commonsTitle": "File:Alfa.jpg", "emblematic": True}, "Un train Alfa Pendular de CP à quai."),
                  ("train-oriente", {"commonsTitle": "File:Oriente.jpg"}, "Un Alfa Pendular sous les arbres de béton de la gare d’Oriente."),
                  ("train-interieur", {"commonsTitle": "File:Alfa Pendular interior.jpg"}, "L’intérieur d’une voiture Alfa Pendular."),
                  ("train-nord", {"commonsTitle": "File:Linha do Norte.jpg"}, "La ligne du Nord et ses caténaires."),
                  ("train-campanha", {"commonsTitle": "File:Campanha.jpg", "emblematic": True}, "La façade de la gare de Porto-Campanhã.")]
        pairs = [("35,70 €", "Alfa Pendular Lisbonne → Porto-Campanhã en Turística (49,90 € en Conforto)"), ("28,05 €", "Intercidades en 2e classe, pour environ 25 minutes de plus"),
                 ("≈ 3 h", "de trajet en Alfa Pendular entre Santa Apolónia et Campanhã"), ("38,3 %", "des Alfa Pendular à l’heure sur la ligne du Nord en 2025")]
        article = guide(slug="lisbonne-porto-train", country="portugal", cover="train-alfa-pendular", destination="Portugal", shortTitle="Lisbonne–Porto en train", sections=[fares])
        table = fares["table"]
        read = p.normalized(" ".join(table["headers"]) + " " + " ".join(" ".join(row) for row in table["rows"]))
        self.assertEqual(reel_formats.table_of(article, read)["rows"], [["Alfa Pendular Turística", "35,70 €"], ["Alfa Pendular Conforto", "49,90 €"], ["Intercidades 2e classe", "28,05 €"]])
        scenes, lines = reel_formats.build("tableau", article, figures(pairs), photos, [], "Phrase d’ouverture.", "Portugal", "Portugal",
                                           "Guide Portugal · sources du 24/10/2026", ["Lisbonne–Porto", "en train"], read)
        plan = scenes[1]
        self.assertEqual((plan["headline"], plan["rows"][2]), (["Aller simple 2026"], ["Intercidades 2e classe", "28,05 €"]))
        # The year in the heading is a number on screen: the plan quotes the heading, and it is not one more thing said.
        self.assertIn("Aller simple 2026", [fact["excerpt"] for fact in plan["facts"]])
        self.assertEqual(len(reel_formats.said_by(scenes[0], scenes[1:-1], "Phrase d’ouverture.")), 5)
        # The fares the table gives get no plan of their own; the caption gives the table, then what the reel shows next.
        self.assertEqual([scene["headline"][0].strip("*").replace(reel_formats.NBSP, " ") for scene in scenes[2:-1]], ["≈ 3 h", "38,3 %"])
        self.assertEqual(lines[0], "📅 Alfa Pendular ou Intercidades · Aller simple 2026 — Alfa Pendular Turística : 35,70 €")
        self.assertEqual(lines[3], "⏱️ ≈ 3 h de trajet en Alfa Pendular entre Santa Apolónia et Campanhã")
        # The table is never laid over a photo that shows numbers of its own, even when it is the first one free.
        display = ("train-afficheur", {"commonsTitle": "File:Display.jpg", "figures": True}, "L’afficheur d’une voiture : 220 km/h.")
        scenes, _ = reel_formats.build("tableau", article, figures(pairs), [photos[0], display] + photos[1:], [], "Phrase d’ouverture.", "Portugal", "Portugal",
                                       "Guide Portugal · sources du 24/10/2026", ["Lisbonne–Porto", "en train"], read)
        self.assertNotEqual(scenes[1]["photo"], "train-afficheur")
        self.assertEqual(scenes[1]["layout"], "table")
        # A table that no leading columns can tell apart, or with nothing after them, is left alone.
        twins = {**fares, "table": {"headers": ["Train", "Classe"], "rows": [["Alfa Pendular", "Turística"], ["Alfa Pendular", "Turística"], ["Intercidades", "2e classe"]]}}
        self.assertIsNone(reel_formats.table_of({**article, "sections": [twins]}, read))

    def test_the_first_caption_line_of_a_table_is_headed_only_by_a_heading_that_names_something(self):
        rows = [["1 jour", "22 €"], ["2 jours", "34 €"]]
        for header, first in (("Départ de Bangkok", "📅 Départ de Bangkok — 1 jour : 22 €"), ("Aller simple 2026", "📅 Aller simple 2026 — 1 jour : 22 €"),
                              ("Jour A", "📅 1 jour : 22 €"), ("Étape", "📅 1 jour : 22 €"), ("Notre choix", "📅 1 jour : 22 €"), ("Prix", "📅 1 jour : 22 €")):
            self.assertEqual(reel_formats.table_lines(header, rows), [first, "📅 2 jours : 34 €"], header)
        # The name of the section, when the plan carries it, is part of what the heading names.
        self.assertEqual(reel_formats.table_lines("Le train de nuit pour Chiang Mai · Prix", rows)[0], "📅 Le train de nuit pour Chiang Mai · Prix — 1 jour : 22 €")

    def test_a_name_with_a_year_is_not_written_over_a_figure_of_another_year(self):
        # Verification of 12/11/2026: "La ligne du Nord en 2026" stood over "38,3 % des Alfa Pendular à l'heure en 2025".
        north = {"title": "La ligne du Nord en 2026 : prévoir de la marge"}
        late = {"value": "38,3 %", "label": "des Alfa Pendular à l’heure (à 5 minutes près) en 2025", "short": "des Alfa Pendular à l’heure (à 5 minutes près) en 2025",
                "shortExcerpt": "38,3 % des Alfa Pendular à l’heure (à 5 minutes près) en 2025", "excerpt": "38,3 % des Alfa Pendular à l’heure (à 5 minutes près) en 2025", "section": north}
        media = lambda: reel_formats.Media([("train-interieur", {"commonsTitle": "File:Alfa Pendular interior.jpg"}, "L’intérieur d’une voiture Alfa Pendular."),
                                            ("train-campanha", {"commonsTitle": "File:Campanha.jpg", "emblematic": True}, "La gare de Porto-Campanhã.")], [])
        tag = "Guide Portugal · sources du 24/10/2026"
        self.assertEqual(reel_formats.fact_plan(late, media(), "Portugal", tag)["kicker"], "Portugal")
        # The same year, or no year on one side: the name of the section stays.
        works = {**late, "label": "des Alfa Pendular à l’heure en 2026, travaux compris"}
        self.assertEqual(reel_formats.fact_plan(works, media(), "Portugal", tag)["kicker"], "La ligne du Nord en 2026")
        undated = {**late, "label": "des Alfa Pendular à l’heure, à 5 minutes près"}
        self.assertEqual(reel_formats.fact_plan(undated, media(), "Portugal", tag)["kicker"], "La ligne du Nord en 2026")

    def test_a_fact_that_names_a_place_never_goes_over_a_photo_of_another_one(self):
        # Review of 13/11/2026, two photo posts of the night: "la réouverture des îles Similan" over Ko Phi Phi (the two
        # shared "îles"), "le pavillon d'Or du Kinkaku-ji" over the sign of Shin-Fuji station.
        names = reel_formats.place_names
        thai = [("thailande-railay", {"commonsTitle": "File:Railay Beach 5.jpg", "emblematic": True}, "La plage de Railay et ses falaises calcaires, près de Krabi."),
                ("thailande-phi-phi", {"commonsTitle": "File:Isla Ko Phi Phi Don, Tailandia.JPG"}, "Les falaises et l’eau turquoise des îles Phi Phi."),
                ("thailande-koh-samui", {"commonsTitle": "File:Koh Samui, Beach, Thailand.jpg"}, "Une plage de sable blanc à Koh Samui."),
                ("thailande-wat-arun", {"commonsTitle": "File:Wat Arun.jpg", "emblematic": True}, "Le pavillon d’entrée du Wat Arun, à Bangkok.")]
        sea = {"title": "La mer d’Andaman : Phuket, Krabi, Koh Phi Phi", "image": "thailande-phi-phi"}
        similan = "la réouverture des îles Similan en 2026 ; la saison dure jusqu’à la mi-mai 2027"
        media = lambda: reel_formats.Media(list(thai), [], reserve=2, cover="thailande-railay", emblematic=reel_formats.emblematic(thai), everywhere="Thaïlande Thaïlande")
        self.assertIsNone(media().named(similan, sea))          # not the guide's own photo of that section: it names Phi Phi
        self.assertEqual(media().left_for(similan), [])         # nor any other photo: each names another place
        self.assertEqual(media().named("Maya Bay, à Phi Phi, ferme du 1er août au 30 septembre", sea)[0], "thailande-phi-phi")
        self.assertEqual(media().named("de pluie à Koh Samui en novembre : le golfe est trempé", None)[0], "thailande-koh-samui")
        facts = figures([("15 octobre", similan), ("445 mm", "de pluie à Koh Samui en novembre")], {"15 octobre": sea})
        self.assertEqual(list(reel_formats.placed(facts, media(), 2, 2)), [1])   # the plan about the Similan islands is left out
        japan = [("japon-fuji-chureito", {"commonsTitle": "File:Chureito.jpg", "emblematic": True}, "La pagode de Chureito et le mont Fuji."),
                 ("japon-shinkansen", {"commonsTitle": "File:Shin-Fuji Station Shinkansen platform view of Mt.Fuji.jpg"}, "Le mont Fuji vu depuis le quai de la gare shinkansen de Shin-Fuji."),
                 ("japon-kyoto-kiyomizu", {"commonsTitle": "File:Kiyomizu.jpg"}, "Des promeneuses en yukata devant la porte nord du Kiyomizu-dera, à Kyoto."),
                 ("japon-nara-cerfs", {"commonsTitle": "File:Nara deer.jpg"}, "Des cerfs en liberté dans le parc de Nara."),
                 ("japon-tokyo-shibuya", {"commonsTitle": "File:Shibuya.jpg", "emblematic": True}, "Le carrefour de Shibuya, à Tokyo.")]
        rail, kyoto = {"title": "Le parcours en train", "image": "japon-shinkansen"}, {"title": "Jours 5 à 8 — Kyoto et Nara", "image": "japon-kyoto-kiyomizu"}
        trip = reel_formats.Media(list(japan), [], reserve=2, cover="japon-fuji-chureito", emblematic=reel_formats.emblematic(japan), everywhere="Japon Japon")
        # A journey goes over the train of the guide, not over a town it names; a temple goes over no other temple.
        # The guide's train photo is the sign of Shin-Fuji station: a place that is none of the two ends of the journey.
        self.assertIn(trip.named("Tokyo → Kyoto en Nozomi, 13 960 ¥ (≈ 80 €), un train toutes les 15 à 30 minutes", rail)[0], ("japon-tokyo-shibuya", "japon-kyoto-kiyomizu"))
        self.assertIsNone(trip.named("le pavillon d’Or du Kinkaku-ji, ouvert tous les jours de 9 h à 17 h", kyoto))
        self.assertEqual(trip.left_for("le pavillon d’Or du Kinkaku-ji, ouvert tous les jours de 9 h à 17 h"), [])
        # The first place a fact names is the one it is about: Nara, not Kyoto "à 45 minutes".
        self.assertEqual(trip.named("le Grand Bouddha du Tōdai-ji, à Nara, à 45 minutes de Kyoto par le train JR", kyoto)[0], "japon-nara-cerfs")
        # Independent review of 13/11/2026: a journey only goes over a ride of its own kind, a word like "ticket" ties
        # no photo to a place, and the first word of a caption is no place.
        stock = [("japon-quai", {"commonsTitle": "File:Platform.jpg"}, "Le quai shinkansen de Shin-Fuji, au pied du mont."),
                 ("japon-ticket", {"commonsTitle": "File:Machine.jpg"}, "Un distributeur de tickets à Shin-Fuji."),
                 ("japon-jardin", {"commonsTitle": "File:Garden.jpg"}, "Visiteurs dans un jardin zen."),
                 ("japon-fin", {"commonsTitle": "File:Fuji.jpg", "emblematic": True}, "Le mont Fuji.")]
        some = lambda: reel_formats.Media(list(stock), [], everywhere="Japon Japon")
        self.assertIsNone(some().named("Le bus 205 pour le Kinkaku-ji, 230 ¥", None))
        self.assertIsNone(some().named("Kinkaku-ji : 500 ¥ le ticket d’entrée", {"image": "japon-ticket"}))
        # Since the review of 13/11/2026 a fact that names a place takes no photo that does not name it, were it a
        # photo that names nothing ("350 mm de pluie à Phuket" went over the inside of a sleeping car): the plan is
        # left out. A fact that names no place may still take any free photo.
        self.assertEqual(some().left_for("Ryoan-ji : 500 ¥ le jardin de pierres"), [])
        self.assertEqual(some().left_for("de pluie en septembre au sud"), [])
        self.assertTrue(some().left_for("le budget confort pour deux semaines"))
        with self.assertRaises(reel_formats.Held):
            some().photo("350 mm de pluie à Phuket en septembre")
        self.assertEqual(some().moving("le budget confort pour deux semaines")[0], "photo")
        clips = lambda: reel_formats.Media(list(stock), [("japon-clip", {})], everywhere="Japon Japon")
        self.assertEqual(clips().moving("le budget confort pour deux semaines")[0], "clip")
        with self.assertRaises(reel_formats.Held):   # a clip shows the destination, nobody knows which place of it
            clips().moving("350 mm de pluie à Phuket en septembre")
        self.assertEqual(names.proper("Visiteurs dans un jardin zen.", sentence=True), set())
        self.assertEqual(names.proper("Bus 500 jusqu’à la mer, billet CP en ligne"), set())
        # What a precise place is: a proper noun, not a kind of place, an acronym or the name of a carrier.
        self.assertEqual(names.named("le ticket bus SITA COSTIERASITA, illimité pendant 24 h"), [])
        self.assertEqual(names.named("de car pour Essaouira : dès 100 dh chez Supratours, dès 105 dh chez CTM"), ["essaouira"])
        self.assertEqual(names.named("Tokyo → Kyoto en Nozomi"), ["tokyo", "kyoto"])
        self.assertEqual(names.named("le Grand Palais de Bangkok et le Wat Phra Kaew", {"bangkok"}), ["phra", "kaew"])
        # The pictogram of a caption line follows what the line opens on.
        self.assertEqual(reel_formats.caption_emoji("800 ¥", "le Grand Bouddha du Tōdai-ji, à Nara, à 45 minutes de Kyoto par le train JR"), "📍")
        self.assertEqual(reel_formats.caption_emoji("44 620 ¥", "Tokyo–Kyoto–Hiroshima–Tokyo en billets à l’unité"), "🚆")
        self.assertEqual(reel_formats.caption_emoji("697 pesos", "l’entrée de Chichén Itzá pour un étranger"), "🎟️")
        self.assertEqual(reel_formats.caption_emoji("12 €", "le ferry Travelmar Salerne → Amalfi, 35 minutes"), "💶")

    def test_the_guard_refuses_a_plan_over_a_photo_of_another_place(self):
        photos = {"thailande-phi-phi": {"commonsTitle": "File:Isla Ko Phi Phi Don, Tailandia, 2013-08-19, DD 02.JPG", "categories": "Beaches of Ko Phi Phi Don"},
                  "japon-shinkansen": {"commonsTitle": "File:Shin-Fuji Station Shinkansen platform view of Mt.Fuji.jpg", "categories": "Shin-Fuji Station (Shizuoka)"},
                  "thailande-koh-samui": {"commonsTitle": "File:Koh Samui, Beach, Thailand.jpg"}}
        plan = lambda photo, headline, detail, alt: {"photo": photo, "kicker": "x", "headline": [headline], "detail": detail, "alt": alt}
        edge = {"photo": "thailande-koh-samui", "kicker": "Thaïlande", "headline": ["Titre"]}
        post = lambda *plans: {"destination": "Thaïlande", "scenes": [edge, *plans, edge]}
        similan = plan("thailande-phi-phi", "*15 octobre*", "la réouverture des îles Similan en 2026", "Les falaises et l’eau turquoise des îles Phi Phi.")
        kinkaku = plan("japon-shinkansen", "*500 ¥*", "le pavillon d’Or du Kinkaku-ji, ouvert tous les jours de 9 h à 17 h", "Le mont Fuji vu depuis le quai de la gare shinkansen de Shin-Fuji.")
        self.assertEqual(p.photos_of_another_place(post(similan, kinkaku), photos),
                         ["plan 2 names similan over thailande-phi-phi (phi)", "plan 3 names kinkaku over japon-shinkansen (fuji)"])
        # Review of the pull request: the place a fact is about is not one it only situates itself by (a photo of Kyoto
        # for "le Tōdai-ji, à Nara, à 45 minutes de Kyoto"), a kind of place shared without its name proves nothing
        # (two pavilions), and a title names what is seen, not where from ("View of … from Rockefeller Center").
        photos = {**photos, "japon-kyoto-kiyomizu": {"commonsTitle": "File:North Gate of Kiyomizu-dera temple Kyoto Japan.jpg"},
                  "thailande-wat-arun": {"commonsTitle": "File:Wat Arun.jpg"},
                  "new-york-268e3ad7": {"commonsTitle": "File:View of Empire State Building from Rockefeller Center New York City.jpg", "categories": "Empire State Building|Views from Rockefeller Center"}}
        wrong = [plan("japon-kyoto-kiyomizu", "*800 ¥*", "le Grand Bouddha du Tōdai-ji, à Nara, à 45 minutes de Kyoto par le train JR", "Des promeneuses en yukata devant la porte nord du Kiyomizu-dera, à Kyoto."),
                 plan("thailande-wat-arun", "*500 ¥*", "le pavillon d’Or du Kinkaku-ji, ouvert tous les jours", "Le pavillon d’entrée de la salle d’ordination du Wat Arun, à Bangkok."),
                 {"photo": "new-york-268e3ad7", "kicker": "x", "headline": ["*2 déc. 2026*"], "detail": "l’allumage du sapin du Rockefeller Center, arrivé le 7 novembre"}]
        self.assertEqual([line.split(" names ")[0] for line in p.photos_of_another_place(post(*wrong), photos)], ["plan 2", "plan 3", "plan 4"])
        self.assertEqual(reel_formats.place_names.subjects("le Grand Bouddha du Tōdai-ji, à Nara, à 45 minutes de Kyoto par le train JR"), ["todai", "nara"])
        self.assertEqual(reel_formats.place_names.subjects("la fenêtre où Bangkok, Chiang Mai et la mer d’Andaman sont tous au sec"), ["bangkok", "mai", "andaman"])
        photos = {**photos, "japon-n700": {"commonsTitle": "File:N700 Series Shinkansen.jpg"}, "thailande-train-nuit": {"commonsTitle": "File:THAI RAILWAYS NIGHT SLEEPER TRAIN.jpg"},
                  "vietnam-train-hanoi": {"commonsTitle": "File:Hanoi train street with coffee.jpg"}, "tenerife-garachico": {"commonsTitle": "File:Vista de Garachico.jpg"},
                  "tenerife-adeje": {"commonsTitle": "File:Tenerife Playa El Duque R01.jpg"}}
        fine = [plan("thailande-phi-phi", "*1er août*", "Maya Bay, à Phi Phi, ferme jusqu’au 30 septembre", "Les falaises et l’eau turquoise des îles Phi Phi."),
                plan("japon-n700", "*2 h 18*", "Tokyo → Kyoto en Nozomi, 13 960 ¥", "Un shinkansen N700 en pleine voie."),
                plan("thailande-train-nuit", "*12 h 35*", "Bangkok → Chiang Mai par le train de nuit n° 9", "L’intérieur d’une voiture-couchettes de deuxième classe."),
                plan("thailande-koh-samui", "*445 mm*", "de pluie à Koh Samui en novembre", "Une plage de sable blanc à Koh Samui."),
                plan("tenerife-adeje", "*222 h*", "de soleil en janvier au sud (aéroport Tenerife Sud), contre 150 h dans le nord", "La plage du Duque à Costa Adeje, dans le sud de l’île."),
                plan("thailande-koh-samui", "*1 367 €*", "le budget confort en business hôtel à deux", "Une plage de sable blanc à Koh Samui.")]
        self.assertEqual(p.photos_of_another_place(post(*fine), photos), [])
        # Review of 13/11/2026, cases replayed with the generator of that morning, all accepted by the first guard:
        # a journey over a ride at another place, a place the record does not name at all, a part of the destination
        # over a precise place of another part, a ticket taken for a journey, two hours taken for the ends of a journey.
        astray = [plan("japon-shinkansen", "*2 h 18*", "Tokyo → Kyoto en Nozomi, 13 960 ¥", "Le mont Fuji vu depuis le quai de la gare shinkansen de Shin-Fuji."),
                  plan("vietnam-train-hanoi", "*2 h 32*", "de Hué à Đà Nẵng en train de jour (SE1, 9 h 40 → 12 h 12), porte d’entrée de Hội An à 35 km", "Une rue de Hanoï longée par la voie ferrée."),
                  plan("thailande-train-nuit", "*350 mm*", "de pluie à Phuket en septembre", "L’intérieur d’une voiture-couchettes de deuxième classe."),
                  plan("vietnam-train-hanoi", "*120 000 ₫*", "le billet de la vieille ville de Hội An, cinq sites au choix", "Une rue de Hanoï longée par la voie ferrée."),
                  plan("thailande-phi-phi", "*15 octobre*", "la réouverture des îles Similan", "Les îles Phi Phi, plus au sud que les Similan.")]
        self.assertEqual([line.split(" names ")[0] for line in p.photos_of_another_place(post(*astray), photos)], [f"plan {n}" for n in range(2, 7)])
        sun = "de soleil en janvier au sud (aéroport Tenerife Sud), contre 150 h dans le nord"
        island = lambda photo, alt, kicker="Tenerife": {"destination": "Tenerife", "scenes": [edge, {**plan(photo, "*222 h*", sun, alt), "kicker": kicker}, edge]}
        self.assertEqual(p.photos_of_another_place(island("tenerife-garachico", "Le village de Garachico et sa côte de lave."), photos),
                         ["plan 2 names the sud over tenerife-garachico (garachico)"])
        self.assertEqual(p.photos_of_another_place(island("tenerife-adeje", "La plage du Duque à Costa Adeje, dans le sud de l’île."), photos), [])
        # The name of its own section above a photo says which part of the island it is of.
        self.assertEqual(p.photos_of_another_place(island("tenerife-adeje", "La plage du Duque, à Costa Adeje.", "Le sud"), photos), [])
        self.assertEqual(len(p.photos_of_another_place(island("tenerife-adeje", "La plage du Duque, à Costa Adeje."), photos)), 1)
        names = reel_formats.place_names
        self.assertEqual((names.linked("9 h 40 → 12 h 12"), names.linked("Tokyo → Kyoto"), names.journey("le billet de la vieille ville de Hội An")), (False, True, False))

    def test_places_are_read_as_the_review_of_13_november_asked(self):
        names = reel_formats.place_names
        # A ticket, a card, an operator, a brand, a people are no places; nor is what follows "chez".
        for text in ("l’Andante Tour 3 : métro, bus et trains urbains pendant 72 h", "le ticket Carris/Metro sur carte Navegante",
                     "de séjour sans visa pour les Français", "une balade en traîneau au village du Père Noël", "Intercidades en 2e classe"):
            self.assertEqual(names.named(text), [], text)
        self.assertEqual(names.named("le bus MEPE Puerto Viejo – San José, environ 4 h 30"), ["viejo", "jose"])
        self.assertEqual(names.subjects("un petit casier City Lockers pour 24 h à Porto-Trindade (7,50 € à Lisbonne), jusqu’à 7 jours"), ["porto", "trindade"])
        self.assertEqual(names.named("le billet de train Rossio–Sintra (tarif CP 4 zones 2026)"), ["rossio", "sintra"])
        # Capitals of any alphabet, and letters no accent rule folds.
        self.assertEqual(names.named("de Hué à Đà Nẵng puis Đà Lạt, Šibenik et Łódź"), ["hue", "nang", "lat", "sibenik", "lodz"])
        # Two names that begin alike are two places; a month is part of a name after another one.
        self.assertEqual((names.named("la nuit à Chiang Rai"), names.named("le temple de Chiang Mai"), names.named("de mai à octobre, en Mai")), (["rai"], ["mai"], []))
        # The first word of a caption is its place when the photo's identifier or title says so.
        for caption, known, place in (("Vernazza et son port au coucher du soleil.", {"cinque", "vernazza"}, "vernazza"),
                                      ("Amalfi vue de la mer, sous les falaises.", {"amalfi", "ville"}, "amalfi"),
                                      ("L’Alhambra et la Sierra Nevada enneigée vus depuis l’Albaicín.", {"grenade", "alhambra"}, "alhambra"),
                                      ("Porto et le pont Luís I illuminés à la tombée de la nuit.", {"porto", "luis", "nuit"}, "porto"),
                                      ("Guimarães et son château vus du téléphérique.", {"guimaraes", "chateau"}, "guimaraes")):
            self.assertEqual(names.named(caption, sentence=True, known=known)[0], place)
        self.assertEqual(names.named("Visiteurs dans un jardin zen.", sentence=True, known={"japon", "jardin"}), [])
        # What a record shows: not where the view is from, not a place it only compares with, not a homonym.
        self.assertNotIn("bryant", names.pictured("new-york-esb", "", "File:Empire State Building behind Bryant Park trees.jpg"))
        self.assertNotIn("similan", names.pictured("thailande-phi-phi", "Les îles Phi Phi, plus au sud que les Similan."))
        self.assertNotIn("porto", names.pictured("alentejo-plage", "La plage de Porto Covo, en Alentejo."))
        self.assertIn("alentejo", names.recorded("alentejo-plage", "La plage de Porto Covo, en Alentejo."))
        # Another spelling, another name, a quarter of the town.
        self.assertLessEqual({"kinkaku", "minh", "sa", "pa", "nang", "lisbonne", "tokyo"},
                             names.widened({"kinkakuji", "saigon", "sapa", "danang", "belem", "shibuya"}))
        # A photo of the old catalogue has no caption of its own: its Commons title says what it names.
        self.assertEqual(names.recorded("sintra-mouros-remparts", "Sintra (Portugal).", "File:Castelo dos Mouros in Sintra, Portugal.jpg", {"sintra", "portugal"}, "sintra"), {"mouros"})
        # A part of the destination: the first one a fact says, not the whole ("nord-sud"), not the name of a line.
        self.assertEqual([names.region(text) for text in ("de soleil en janvier au sud (aéroport Tenerife Sud), contre 150 h dans le nord",
                                                         "la meilleure fenêtre pour un voyage nord-sud", "La ligne du Nord en 2026", "sur la côte est de l’île")],
                         [{"sud"}, set(), set(), {"est"}])
        # A place one only comes from is not what the fact is about.
        self.assertEqual(names.subjects("depuis Kyoto pour voir le Grand Bouddha du Tōdai-ji, à Nara"), ["todai", "nara"])

    def test_a_figure_only_the_summary_gives_stays_in_the_summary_and_a_label_never_names_another_part(self):
        brief = {"title": "En bref", "paragraphs": ["Comptez 872 € pour le budget serré de 14 jours, 500 ¥ l’entrée d’un temple."]}
        sleep = {"title": "Où dormir", "paragraphs": ["Un budget serré dort en capsule ou en dortoir pendant 14 jours."]}
        temple = {"title": "Jour 1 — Kiyomizu-dera", "paragraphs": ["L’entrée du temple coûte 500 ¥."]}
        sections = [brief, sleep, temple]
        self.assertIs(a.section_of("872 €", "le budget serré pour 14 jours et 13 nuits", sections), brief)
        self.assertIs(a.section_of("500 ¥", "l’entrée du temple", sections), temple)
        photos = [("vietnam-trang-an", {"commonsTitle": "File:Trang An.jpg"}, "Des barques dans les rizières de Tràng An, près de Ninh Bình."),
                  ("vietnam-mekong", {"commonsTitle": "File:Mekong.jpg"}, "Un marché flottant du delta du Mékong, dans le sud du pays."),
                  ("vietnam-halong", {"commonsTitle": "File:Halong.jpg", "emblematic": True}, "Une jonque dans la baie d’Along.")]
        media = reel_formats.Media(photos, [], everywhere="Vietnam Vietnam")
        south, budget = {"title": "Le Sud : Saïgon et le delta du Mékong"}, {"title": "Budget : ce que ça coûte"}
        self.assertEqual(media.above(south, "vietnam-trang-an", "Vietnam"), "Vietnam")   # "LE SUD" was written over Tràng An, in the north
        self.assertEqual(media.above(south, "vietnam-mekong", "Vietnam"), reel_formats.kicker_of(south, "Vietnam"))
        self.assertEqual(media.above(budget, "vietnam-trang-an", "Vietnam"), reel_formats.kicker_of(budget, "Vietnam"))
        self.assertEqual(media.above({**south, "image": "vietnam-mekong"}, "vietnam-halong", "Vietnam"), "Vietnam")
        # A fact about one part of the country takes the photo that says that part, never a precise place of another part.
        rain = "de pluie en octobre dans le sud, la fin de la mousson"
        self.assertEqual(media.named(rain, None)[0], "vietnam-mekong")
        self.assertIsNone(reel_formats.Media(photos[:1] + photos[2:], [], everywhere="Vietnam Vietnam").named(rain, None))

    def test_a_photo_post_whose_figures_all_belong_to_a_day_reads_day_after_day(self):
        days = {number: {"title": f"Jour {number} — {name}"} for number, name in ((1, "La médina"), (2, "Le jardin Majorelle"), (3, "Sortir de la ville"))}
        pairs = [("170 dh", "le jardin Majorelle en plein tarif", 2), ("100 dh", "l’entrée de la Bahia, des tombeaux saadiens ou d’El Badi", 1),
                 ("3 h", "de car pour Essaouira : dès 100 dh chez Supratours", 3), ("150 km", "jusqu’aux cascades d’Ouzoud, soit 2 h 30 à 3 h de route", 3)]
        photos = [self.MARRAKECH[0], self.MARRAKECH[1], self.MARRAKECH[2],
                  ("marrakech-essaouira-port", {"commonsTitle": "File:Skala.jpg"}, "Des barques bleues au pied de la Skala du port, à Essaouira."),
                  ("marrakech-ouzoud-cascades", {"commonsTitle": "File:Ouzoud.jpg"}, "Les cascades d’Ouzoud, dans le Moyen Atlas."),
                  ("marrakech-koutoubia-bassin", {"commonsTitle": "File:Koutoubia.jpg", "emblematic": True}, "Le minaret de la Koutoubia, à Marrakech.")]
        article = guide(slug="marrakech-3-jours", country="maroc", destination="Marrakech", shortTitle="Marrakech en 3 jours", sourcesCheckedOn="2026-11-12", sections=list(days.values()))
        made = lambda chosen: a.scenes_for(article, a.Post("facebook", "carousel"), [{"value": value, "label": label, "excerpt": value + " " + label, "section": days.get(day)}
                                                                                   for value, label, day in chosen], list(photos), "Phrase d’ouverture.", "Marrakech", "Maroc")
        scenes = made(pairs)
        self.assertEqual([(scene["kicker"], scene["headline"][0].strip("*"), scene["photo"]) for scene in scenes[1:-1]],
                         [("Jour 1", "100 dh", "marrakech-bahia"), ("Jour 2", "170 dh", "marrakech-majorelle"),
                          ("Jour 3", "3 h", "marrakech-essaouira-port"), ("Jour 3", "150 km", "marrakech-ouzoud-cascades")])
        # One figure outside the days of the guide: the post keeps the order of the guide's figures.
        loose = made(pairs[:3] + [("150 km", "jusqu’aux cascades d’Ouzoud, soit 2 h 30 à 3 h de route", None)])
        self.assertEqual([scene["headline"][0].strip("*") for scene in loose[1:-1]], ["170 dh", "100 dh", "3 h", "150 km"])

    def test_a_file_found_by_the_search_never_opens_a_post(self):
        media = reel_formats.Media(list(self.MARRAKECH), [], reserve=2, cover="marrakech-place-jemaa-el-fna",
                                   emblematic=reel_formats.emblematic(self.MARRAKECH), everywhere="Maroc · Marrakech")
        # The post leans on found files: its cover is kept for the opening, and the fare that names it stays in the guide.
        bus = "le bus 19 de l’aéroport à Jemaa el-Fna (50 dh l’aller-retour)"
        self.assertIsNone(media.named(bus, None))
        self.assertEqual(media.left_for(bus), [])
        self.assertEqual(media.photo("le jardin Majorelle selon les relevés 2023-2024")[1], "marrakech-majorelle")
        self.assertEqual(media.opening(media.cover)[1], "marrakech-place-jemaa-el-fna")
        self.assertEqual(media.closing()[1], "marrakech-bahia")
        # No cover and nothing a person looked at but the photo kept for the end: the post waits.
        found = [photo for photo in self.MARRAKECH if photo[1].get("automatic")] + [self.MARRAKECH[1]]
        alone = reel_formats.Media(found, [], reserve=2, emblematic=reel_formats.emblematic(found))
        with self.assertRaisesRegex(reel_formats.Held, "no_reviewed_photo_to_open_with"):
            alone.opening(None)
        # A photo post may close on any photo a person looked at, never on a found file.
        mixed = [self.MARRAKECH[0], ("marrakech-souk", {"commonsTitle": "File:Souk.jpg"}, "Une allée du souk.")] + [ph for ph in self.MARRAKECH if ph[1].get("automatic")]
        post = reel_formats.Media(mixed, [], reserve=2, cover=mixed[0][0], emblematic=reel_formats.emblematic(mixed))
        self.assertEqual((post.opening(post.cover)[1], post.closing(required=False)[1]), ("marrakech-place-jemaa-el-fna", "marrakech-souk"))
        with self.assertRaisesRegex(reel_formats.Held, "no_emblematic_photo_for_the_call"):
            post.closing(required=False)
        # Even named as the cover (a guide whose own photos were all refused), a found file does not open the post.
        only = [photo for photo in self.MARRAKECH if photo[1].get("automatic")]
        with self.assertRaisesRegex(reel_formats.Held, "no_reviewed_photo_to_open_with"):
            reel_formats.Media(only, [], reserve=2, cover=only[0][0]).opening(only[0][0])
        with self.assertRaisesRegex(reel_formats.Held, "no_reviewed_photo_to_open_with|not_enough"):
            reel_formats.build("liste", guide(cover="absente"), figures([(f["value"], f["label"]) for f in FACTS]), only * 3, [],
                               "Phrase d’ouverture.", "Marrakech", "Maroc · Marrakech", "Guide Marrakech · sources du 05/11/2026", ["Marrakech"], "")

    SEALED = ("ig-yucatan-itineraire-10-jours-2026-11-20-2", "ig-laponie-budget-rovaniemi-2026-11-27-2")

    def sealed(self, name):
        """A reel sealed before the neutral button: its scenario, its plans as production draws them today, its fonts."""
        scenario = json.loads((HERE / "scenarios" / f"{name}.json").read_text())
        info = {"photos": p.load_photos(scenario, HERE), "clips": {}}
        return scenario, info, p.prepared_scenes(scenario, HERE, info, None, False), p.motion_fonts(scenario, HERE)

    def test_a_reel_sealed_before_the_neutral_button_keeps_the_button_it_was_given(self):
        # Drawn twice on the same machine: nothing here depends on how this machine draws text.
        for name in self.SEALED:
            scenario, info, plans, fonts = self.sealed(name)
            last, count = scenario["scenes"][-1], len(scenario["scenes"])
            self.assertNotIn("button", last)
            media = [(str(HERE / info["photos"][last["photo"]]["file"]), False)]
            drawn = lambda plan: motion_render.still(plan, count - 1, count, fonts).tobytes()
            before, neutral = (motion_render.prepare([last], media, fonts, button)[0] for button in (p.MOTION_BUTTON_BEFORE, p.MOTION_BUTTON))
            self.assertEqual(drawn(plans[-1]), drawn(before))
            self.assertNotEqual(drawn(plans[-1]), drawn(neutral))
            # A scenario made today carries the neutral button and is drawn with it.
            today = {**scenario, "scenes": scenario["scenes"][:-1] + [{**last, "button": p.MOTION_BUTTON}]}
            self.assertEqual(drawn(p.prepared_scenes(today, HERE, info, None, False)[-1]), drawn(neutral))

    def test_on_the_machine_that_rendered_it_a_sealed_reel_is_redrawn_to_the_byte(self):
        # The stills in output/ were drawn by one machine; another one (another text engine) draws the same plans a few
        # pixels apart. A reel is compared only where every plan before the last already comes out identical.
        compared = 0
        for name in self.SEALED:
            scenario, _, plans, fonts = self.sealed(name)

            def redrawn(index):
                saved = io.BytesIO()
                motion_render.still(plans[index], index, len(plans), fonts).save(saved, "JPEG", quality=90)
                return saved.getvalue()

            stored = lambda index: (HERE / "output" / name / f"scene-{index + 1:02}.jpg").read_bytes()
            if any(redrawn(index) != stored(index) for index in range(len(plans) - 1)):
                continue
            compared += 1
            with self.subTest(name):
                self.assertEqual(redrawn(len(plans) - 1), stored(len(plans) - 1))
        if not compared:
            self.skipTest("this machine does not draw text as the one that rendered these reels")

    def test_the_frame_never_slides_off_the_subject_of_a_panorama(self):
        # Review of 12/11/2026: on the panorama of Tulum (2880 × 1328) the frame is a quarter of the photo wide, and a
        # slide of 7 % of the photo carried the temple (0.59 to 0.70 of the width) out of it at the end of the plan.
        size, focus = (2880, 1328), media_library.SITE_FOCUS["yucatan-tulum"]
        closest = 1.0 + motion_render.ZOOM_RANGE + motion_render.PUNCH
        for index in range(3):
            for progress in (0.0, 0.25, 0.5, 0.75, 1.0):
                slide = motion_render.drift_of(size, progress, index)
                left, _, right, _ = motion_render.base.cover_box(size, motion_render.SIZE, closest, (focus[0] + slide, focus[1]))
                self.assertTrue(left <= 0.59 * size[0] and 0.70 * size[0] <= right, (index, progress, left, right))
            # An ordinary photo slides as it always did, and every plan still moves.
            self.assertAlmostEqual(abs(motion_render.drift_of((3000, 2000), 1.0, index)), motion_render.DRIFT)
            self.assertAlmostEqual(motion_render.drift_of(size, 0.0, index), -motion_render.drift_of(size, 1.0, index))
            self.assertGreater(abs(motion_render.drift_of(size, 1.0, index)), 0.03)

    def test_a_panorama_as_high_as_the_frame_at_zoom_one_is_framed_inside_the_photo(self):
        # 2880 × 854: the rounding of the division put the top of the box a hair above the photo and stopped the render.
        for size in ((2880, 854), (2880, 803), (2880, 1600), (1021, 2880)):
            for zoom in (1.0, 1.0 + motion_render.ZOOM_RANGE, 1.0 + motion_render.ZOOM_RANGE + motion_render.PUNCH):
                for center in ((0.43, 0.5), (0.5, 0.5), (0.57, 0.5)):
                    left, top, right, bottom = motion_render.base.cover_box(size, motion_render.SIZE, zoom, center)
                    self.assertTrue(0 <= left < right <= size[0] and 0 <= top < bottom <= size[1], (size, zoom, center))
        picture = Image.new("RGB", (2880, 854), (40, 90, 140))
        with tempfile.TemporaryDirectory() as folder:
            picture.save(Path(folder) / "panorama.jpg")
            for index in (0, 1):
                for moment in (0.0, 1.0):
                    self.assertEqual(motion_render.photo_frame(str(Path(folder) / "panorama.jpg"), (0.5, 0.5), moment, index, False).size, motion_render.SIZE)


if __name__ == "__main__":
    unittest.main()
