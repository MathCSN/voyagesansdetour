"""Offline tests for auto_social.py: guide pages, Commons and downloads are faked."""
import datetime as dt
import hashlib
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
TABLE = {"title": "En bref", "table": {"headers": ["Votre envie", "Les meilleurs mois", "À savoir"],
                                        "rows": [["Cerisiers en fleurs", "Fin mars à début avril", "Réservez tôt"],
                                                 ["Érables rouges", "Mi-novembre", "Temples illuminés le soir"],
                                                 ["Moins de monde", "Janvier et février", "Froid sec"]]}}


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

    def test_too_few_photos_holds_the_photo_post_but_not_the_reel(self):
        f = self.fixture(photos=5)
        result = f.run(limit=30)
        self.assertEqual({c["channel"] for c in result["created"]}, {"instagram"})
        self.assertIn({"slug": "kyoto-train", "channel": "facebook", "kind": "carousel", "reason": "not_enough_photos_or_figures"}, result["held"])

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
        self.assertEqual((first["format"], second[0]["format"]), ("liste", "express"))

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
        reel = self.reel(self.fixture([guide(category="Itinéraires", sections=DAYS)]))
        stages = reel["scenes"][1:-1]
        self.assertEqual((reel["format"], reel["scenes"][0]["headline"][-1]), ("itineraire", "*jour par jour*"))
        self.assertEqual([(s["kicker"], s["headline"], s["photo"]) for s in stages],
                         [("Jour 1", ["Kiyomizu-dera"], "kyoto-3"), ("Jour 2", ["Fushimi Inari", "et ses torii"], "kyoto-4"), ("Jour 3", ["Arashiyama"], "kyoto-5")])
        self.assertEqual(stages[0]["facts"][0]["excerpt"], "Jour 1 — Kiyomizu-dera, le temple sur pilotis")
        self.assertEqual(stages[0]["detail"], "*500 ¥* l’entrée du temple Kiyomizu-dera")
        self.assertIn("📍 Jour 2 : Fushimi Inari et ses torii", reel["caption"]["lines"])
        self.assertNotIn("Osaka", json.dumps(reel["scenes"], ensure_ascii=False))  # no photo of Osaka in this guide

    def test_a_when_to_go_guide_becomes_a_table_to_pause(self):
        article = guide(category="Choisir", shortTitle="Quand partir à Kyoto", sections=[TABLE] + SECTIONS)
        reel = self.reel(self.fixture([article]))
        table = reel["scenes"][1]
        self.assertEqual((reel["format"], table["layout"], table["headline"]), ("tableau", "table", ["Les meilleurs mois"]))
        self.assertEqual(table["rows"][0], ["Cerisiers en fleurs", "Fin mars à début avril"])
        self.assertEqual(table["note"], "Faites pause pour tout lire")
        self.assertEqual([fact["excerpt"] for fact in table["facts"]][1], "Érables rouges Mi-novembre")
        self.assertEqual(reel["caption"]["lines"][0], "📅 Cerisiers en fleurs : Fin mars à début avril")

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

    def test_the_hook_announces_only_the_plans_that_follow(self):
        self.refused("not quoted from this plan", lambda s: s["scenes"][0].update(headline=["Kyoto en train", "*9 chiffres à connaître*"]))

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
