"""Étape 4 (16/11/2026): the cases of the review of PR 53, one test each. Which photo a figure goes over, and what the
guard on places (production.another_place) reads."""
import unittest

import place_names as names
import production as p
import reel_formats

VIETNAM = "Vietnam Vietnam"
JAPON = "Japon Japon"


def photo(identifier: str, title: str, caption: str, **extra) -> tuple:
    return (identifier, {"commonsTitle": title, **extra}, caption)


class NumbersAreNoWords(unittest.TestCase):
    """MOYEN 1: a year shared with a Commons title ties no figure to that photo."""

    JAPAN = [photo("japon-nara-cerfs", "File:Nara deer park November 2026.jpg", "Des cerfs en liberté dans le parc de Nara."),
             photo("japon-fuji-chureito", "File:Chureito Pagoda 2023.jpg", "La pagode Chureito devant le mont Fuji."),
             photo("japon-tokyo-shibuya", "File:Shibuya.jpg", "Le carrefour de Shibuya, à Tokyo.", emblematic=True)]

    def test_a_year_is_not_a_word_two_texts_share(self):
        self.assertNotIn("2026", reel_formats.words_of("176,77 ¥ pour 1 € (BCE, 6 novembre 2026)"))
        self.assertIn("n700s", reel_formats.words_of("le N700S"))

    def test_a_rate_dated_2026_does_not_go_over_a_photo_titled_2026(self):
        for fact in ("176,77 ¥ pour 1 € (BCE, 6 novembre 2026)", "le budget moyen d'un voyageur en 2023"):
            media = reel_formats.Media(list(self.JAPAN), [], everywhere=JAPON)
            self.assertIsNone(media.named(fact, None), fact)
            self.assertEqual(media.photo(fact)[1], "japon-tokyo-shibuya", fact)


class TheSectionSaysWhere(unittest.TestCase):
    """MOYEN 2: a figure that names no place, in a section about one town, goes over that town or stays in the guide."""

    HUE = {"title": "Jours 6 et 7 — Hué", "image": "vietnam-hue"}
    TOMBS = {"value": "150 000 ₫", "label": "les tombeaux coûtent 150 000 ₫ chacun", "section": HUE, "heading": "Jours 6 et 7 — Hué"}
    HALONG = photo("vietnam-halong", "File:Ha Long Bay.jpg", "La baie d'Ha Long.")
    HUE_GATE = photo("vietnam-hue", "File:Hue citadel gate.jpg", "La porte de la cité impériale de Hué.")

    def test_the_title_of_the_section_names_the_place(self):
        self.assertEqual(names.titled("Jours 6 et 7 — Hué"), "Hué")
        self.assertEqual(names.titled("Jours 5 à 8 — Kyoto et Nara"), "Kyoto et Nara")
        self.assertEqual(names.titled("Budget"), "")
        self.assertEqual(reel_formats.section_place({"title": "En bref : Hanoï, Hué, Saïgon"}, set()), "")

    def test_the_figure_goes_over_the_town_of_its_section(self):
        media = reel_formats.Media([self.HALONG, self.HUE_GATE], [], everywhere=VIETNAM)
        self.assertEqual(media.about(self.TOMBS), "les tombeaux coûtent 150 000 ₫ chacun (Hué)")
        self.assertEqual(media.named(media.about(self.TOMBS), self.HUE)[0], "vietnam-hue")

    def test_once_the_town_is_taken_the_figure_stays_in_the_guide(self):
        media = reel_formats.Media([self.HALONG], [], everywhere=VIETNAM)
        self.assertIsNone(media.named(media.about(self.TOMBS), self.HUE))
        self.assertEqual(media.left_for(media.about(self.TOMBS)), [])
        self.assertEqual(list(reel_formats.placed([self.TOMBS], media, 1, 1)), [])

    def test_a_figure_that_names_its_own_place_keeps_it(self):
        media = reel_formats.Media([self.HALONG], [], everywhere=VIETNAM)
        fact = {**self.TOMBS, "label": "la croisière dans la baie d'Ha Long, 1 200 000 ₫"}
        self.assertEqual(media.where(fact), "")

    def test_the_plan_quotes_its_section_and_the_guard_reads_it(self):
        media = reel_formats.Media([self.HALONG, self.HUE_GATE], [], everywhere=VIETNAM)
        where, quotes = reel_formats.located_by_section(self.TOMBS, media, "150 000 ₫ les tombeaux coûtent 150 000 ₫ chacun")
        self.assertEqual(where, "Jours 6 et 7 — Hué")
        self.assertEqual(quotes[0], {"source": "guide", "excerpt": "Jours 6 et 7 — Hué"})
        scene = {"photo": "vietnam-halong", "headline": ["*150 000 ₫*"], "detail": "les tombeaux coûtent 150 000 ₫ chacun",
                 "alt": "La baie d'Ha Long.", "where": where}
        photos = {"vietnam-halong": {"commonsTitle": "File:Ha Long Bay.jpg"}, "vietnam-hue": {"commonsTitle": "File:Hue citadel gate.jpg"}}
        everywhere = names.words(VIETNAM)
        self.assertIn("hue", p.another_place(scene, photos, everywhere))
        self.assertIsNone(p.another_place({**scene, "photo": "vietnam-hue", "alt": "La porte de la cité impériale de Hué."}, photos, everywhere))
        self.assertIsNone(p.another_place({key: value for key, value in scene.items() if key != "where"}, photos, everywhere))

    def test_the_section_a_plan_says_it_is_about_must_be_quoted(self):
        snapshots = {"guide": ("guide", p.normalized("Jours 6 et 7 — Hué. 150 000 ₫ les tombeaux coûtent 150 000 ₫ chacun"))}
        scene = {"facts": [{"source": "guide", "excerpt": "150 000 ₫ les tombeaux coûtent 150 000 ₫ chacun"}], "tag": "Guide",
                 "where": "Jours 6 et 7 — Hué"}
        with self.assertRaises(p.Invalid):
            p.quoted_excerpts(scene, snapshots, False)
        quoted = {**scene, "facts": [{"source": "guide", "excerpt": "Jours 6 et 7 — Hué"}] + scene["facts"]}
        self.assertEqual(p.quoted_excerpts(quoted, snapshots, False)[0], {"guide"})


class WholeNames(unittest.TestCase):
    """MOYEN 3 and BAS 4 to 6: a name keeps the words that begin it, and is read whatever its spaces and its case."""

    def test_a_name_keeps_the_word_that_begins_it(self):
        self.assertEqual(names.names("Santa Cruz")[0][0], ("santa", "cruz"))
        self.assertEqual(names.names("Puerto de la Cruz")[0][0], ("puerto", "cruz"))
        self.assertFalse(names.same(("santa", "cruz"), ("puerto", "cruz")))
        self.assertEqual(names.names("Mai Châu")[0][0], ("mai", "chau"))
        self.assertFalse(names.shows(("mai", "chau"), names.words("Le marché flottant de Châu Đốc")))
        self.assertEqual(names.names("Đà Nẵng")[0][0], ("da", "nang"))
        self.assertFalse(names.shows(("da", "nang"), names.words("La plage d'Ao Nang")))
        self.assertTrue(names.shows(("da", "nang"), {"danang", "beach"}))   # the alias serves at last

    def test_a_kind_of_place_stays_out_of_the_name(self):
        # "Real Alcázar" and "Alcázar of Seville", "Grand Bouddha" and the Tōdai-ji: one place, the kind is not the name.
        self.assertEqual(names.names("le Real Alcázar de Séville")[0][0], ("alcazar",))
        self.assertEqual(names.read("le Grand Bouddha du Tōdai-ji, à Nara").first, ("todai",))

    def test_a_name_of_generic_words_only_is_a_name(self):
        self.assertEqual(names.named("de Porto à Vila Real en bus"), ["porto", "vila", "real"])
        self.assertEqual(names.names("Vila Real")[0][0], ("vila", "real"))

    def test_a_non_breaking_space_or_a_line_break_does_not_cut_a_name(self):
        plain = [name for name, _, _ in names.names("Tràng An à Ninh Bình")]
        for space in (" ", " ", "\n"):
            self.assertEqual([name for name, _, _ in names.names(f"Tràng{space}An à Ninh{space}Bình")], plain, repr(space))
        self.assertEqual(plain, [("trang", "an"), ("ninh", "binh")])

    def test_a_place_written_in_capitals_is_read(self):
        self.assertEqual(names.named("LISBONNE"), ["lisbonne"])
        self.assertEqual(names.named("HÔ-CHI-MINH-VILLE"), ["ho", "chi", "minh"])
        self.assertEqual(names.ordinary("Lisbonne et Porto"), "Lisbonne et Porto")


class APlainFact(unittest.TestCase):
    """BAS 7: a fact that names no place never goes over a station before a photo of the place, vehicle or not."""

    def test_a_station_without_a_vehicle_comes_after_the_place(self):
        stock = [photo("porto-campanha", "File:Estação de Campanhã.jpg", "La façade de la gare de Porto-Campanhã."),
                 photo("porto-ribeira", "File:Ribeira.jpg", "Les maisons colorées de la Ribeira, à Porto.")]
        media = reel_formats.Media(list(stock), [], everywhere="Portugal Portugal")
        self.assertEqual(media.photo("le budget confort pour deux semaines")[1], "porto-ribeira")


class JourneysSaidFurtherOn(unittest.TestCase):
    """BAS 8: a journey whose means comes after its first words is a journey, and never goes over another means."""

    NIGHT = "de nuit entre Ninh Bình (SE3, 21 h 35) et Hué (arrivée 7 h 59)"
    DAY = "de Hué à Đà Nẵng en train de jour (SE1, 9 h 40 → 12 h 12), porte d’entrée de Hội An à 35 km"
    BOATS = photo("vietnam-trang-an", "File:Trang An boats.jpg", "Des barques sur la rivière de Tràng An, près de Ninh Bình.")
    TRAIN = photo("vietnam-train", "File:SE3 train.jpg", "Le train de la Réunification en gare de Hué.")

    def test_the_two_journeys_are_read(self):
        self.assertTrue(names.journey(self.NIGHT))
        self.assertTrue(names.journey(self.DAY))
        self.assertEqual(names.wanted_ways(self.NIGHT), {"rail"})
        self.assertEqual(names.wanted_ways(self.DAY), {"rail"})
        self.assertFalse(names.journey("les hôtels entre Lisbonne et Porto coûtent plus cher en août"))

    def test_a_journey_by_train_never_goes_over_boats(self):
        boats = names.words("Des barques sur la rivière de Tràng An, près de Ninh Bình. Trang An boats")
        self.assertTrue(names.other_ride(boats, self.NIGHT))
        self.assertFalse(names.other_ride(names.words("Le train de la Réunification"), self.NIGHT))
        self.assertFalse(names.other_ride(names.words("La porte de la cité impériale de Hué"), self.DAY))
        media = reel_formats.Media([self.BOATS], [], everywhere=VIETNAM)
        self.assertIsNone(media.named(self.NIGHT, None))
        self.assertEqual(media.left_for(self.NIGHT), [])
        self.assertEqual(reel_formats.Media([self.BOATS, self.TRAIN], [], everywhere=VIETNAM).named(self.NIGHT, None)[0], "vietnam-train")

    def test_the_guard_refuses_a_journey_over_another_means(self):
        scene = {"photo": "vietnam-trang-an", "headline": ["*10 h 24*"], "detail": self.NIGHT, "alt": self.BOATS[2]}
        photos = {"vietnam-trang-an": self.BOATS[1]}
        self.assertIn("another means of transport", p.another_place(scene, photos, names.words(VIETNAM)))


if __name__ == "__main__":
    unittest.main()
