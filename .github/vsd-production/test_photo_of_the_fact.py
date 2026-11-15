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
        boats = names.vehicle(*self.BOATS[0:1], self.BOATS[2], self.BOATS[1]["commonsTitle"])
        self.assertEqual(boats, {"water"})
        self.assertTrue(names.other_ride(boats, self.NIGHT))
        self.assertFalse(names.other_ride(names.vehicle("vietnam-train", self.TRAIN[2], "File:SE3 train.jpg"), self.NIGHT))
        self.assertFalse(names.other_ride(names.vehicle("vietnam-hue", "La porte de la cité impériale de Hué.", "File:Hue.jpg"), self.DAY))
        # Boats in the foreground of a view are not what the photo is of.
        self.assertEqual(names.vehicle("porto", "Les façades de Ribeira au bord du Douro à Porto, avec des bateaux rabelos au premier plan.",
                                       "File:Porto-Panorama de Ribeira-Rabelos.jpg"), set())
        media = reel_formats.Media([self.BOATS], [], everywhere=VIETNAM)
        self.assertIsNone(media.named(self.NIGHT, None))
        self.assertEqual(media.left_for(self.NIGHT), [])
        self.assertEqual(reel_formats.Media([self.BOATS, self.TRAIN], [], everywhere=VIETNAM).named(self.NIGHT, None)[0], "vietnam-train")

    def test_a_journey_with_its_two_ends_and_its_means_goes_over_that_means_or_stays_in_the_guide(self):
        gate = photo("vietnam-hue", "File:Hue citadel gate.jpg", "La porte de la cité impériale de Hué.")
        self.assertTrue(names.strict_journey(self.DAY))
        self.assertTrue(names.strict_journey("Séville → Cordoue en AVE ; Ouigo dès 9 €"))
        self.assertFalse(names.strict_journey("le ticket bus SITA COSTIERASITA, illimité pendant 24 h"))
        self.assertFalse(names.strict_journey("le plafond quotidien du métro en zones 1-2 en sans contact"))
        self.assertIsNone(reel_formats.Media([gate], [], everywhere=VIETNAM).named(self.DAY, None))
        self.assertEqual(reel_formats.Media([gate], [], everywhere=VIETNAM).left_for(self.DAY), [])
        self.assertEqual(reel_formats.Media([gate, self.TRAIN], [], everywhere=VIETNAM).named(self.DAY, None)[0], "vietnam-train")
        scene = {"photo": "vietnam-hue", "headline": ["*2 h 32*"], "detail": self.DAY, "alt": gate[2]}
        self.assertIn("no ride", p.another_place(scene, {"vietnam-hue": gate[1]}, names.words(VIETNAM)))

    def test_the_figure_tells_the_means_too(self):
        mezquita = photo("cordoue-mezquita", "File:Mezquita.jpg", "Les arcs de la Mezquita de Cordoue.")
        fact = {"value": "10 trains", "label": "directs par jour entre Cordoue et Grenade, 1 h 37 à 1 h 56", "section": None}
        media = reel_formats.Media([mezquita], [], everywhere="Espagne Andalousie")
        self.assertTrue(names.strict_journey(media.about(fact)))
        self.assertIsNone(media.named(media.about(fact), None))
        scene = {"photo": "cordoue-mezquita", "headline": ["*10 trains*"], "detail": fact["label"], "alt": mezquita[2]}
        self.assertIn("no ride", p.another_place(scene, {"cordoue-mezquita": mezquita[1]}, names.words("Espagne Andalousie")))

    def test_a_train_named_in_its_own_language_is_a_train(self):
        self.assertTrue(names.strict_journey("de l’aéroport de Cancún à Valladolid en Tren Maya, 6 départs par jour"))
        self.assertEqual(names.wanted_ways("en Tren Maya de Mérida à Cancún"), {"rail"})

    def test_a_taxi_never_goes_over_a_tram(self):
        taxi = "le taxi à prix fixe depuis l’aéroport de Lisbonne selon la zone et l’heure, bagages compris"
        tram = names.vehicle("lisbonne-tram28-rue", "Un tram jaune de la ligne 28 dans une rue pavée et pentue de Lisbonne.", "File:Tram 28.jpg")
        self.assertEqual(names.wanted_ways(taxi), {"other"})
        self.assertTrue(names.other_ride(tram, taxi))
        self.assertFalse(names.other_ride(names.vehicle("lisbonne", "Les toits de Lisbonne.", "File:Lisboa.jpg"), taxi))

    def test_the_guard_refuses_a_journey_over_another_means(self):
        scene = {"photo": "vietnam-trang-an", "headline": ["*10 h 24*"], "detail": self.NIGHT, "alt": self.BOATS[2]}
        photos = {"vietnam-trang-an": self.BOATS[1]}
        self.assertIn("another means of transport", p.another_place(scene, photos, names.words(VIETNAM)))


class TheFinish(unittest.TestCase):
    """BAS 9: the opening read by the guard, a line never cut after an article, no colon before a preposition, a
    price in any currency, and no train named by a table's label over another train."""

    HALONG = photo("vietnam-halong", "File:Ha Long Bay.jpg", "Des jonques dans la baie d'Ha Long.")
    OPENING = "Le Vietnam a trois climats : un même mois peut être parfait à Saïgon et inondé à Hội An."

    def test_the_guard_reads_the_opening(self):
        scenario = {"destination": "Vietnam", "title": "Quand partir au Vietnam : 4 repères",
                    "scenes": [{"photo": "vietnam-halong", "kicker": "Vietnam", "headline": ["Quand partir au Vietnam", "*4 repères* à connaître"],
                                "detail": self.OPENING, "alt": self.HALONG[2]},
                               {"photo": "vietnam-halong", "kicker": "Le guide complet", "headline": ["Quand partir au Vietnam"], "cta": True}]}
        photos = {"vietnam-halong": self.HALONG[1]}
        self.assertEqual(len(p.photos_of_another_place(scenario, photos)), 1)
        scenario["scenes"][0]["detail"] = "Le bon mois pour chaque région, de la baie d'Ha Long au delta du Mékong."
        self.assertEqual(p.photos_of_another_place(scenario, photos), [])
        del scenario["scenes"][0]["detail"]
        self.assertEqual(p.photos_of_another_place(scenario, photos), [])

    def test_the_generator_leaves_out_an_opening_its_photo_does_not_show(self):
        media = reel_formats.Media([self.HALONG], [], everywhere=VIETNAM)
        self.assertFalse(media.opens_on(self.OPENING, "vietnam-halong", "Quand partir au Vietnam"))
        self.assertTrue(media.opens_on("Le Vietnam a trois climats.", "vietnam-halong", "Quand partir au Vietnam"))

    def test_a_line_never_ends_on_an_article(self):
        lines = reel_formats.lines_of("Le bon mois pour Bangkok, le Nord, l’Andaman et Koh Samui", 34)
        self.assertFalse(any(reel_formats.dangling(line) for line in lines[:-1]), lines)

    def test_no_colon_before_a_preposition(self):
        self.assertEqual(reel_formats.caption_line({"value": "64 mm", "label": "à Koh Samui en novembre"}), "📍 64 mm à Koh Samui en novembre")
        self.assertIn("59 € : la cabine", reel_formats.caption_line({"value": "59 €", "label": "la cabine du train de nuit"}))

    def test_a_price_in_yen_or_dong_is_a_price(self):
        for value in ("176,77 ¥", "150 000 ₫", "938 bahts", "45 £"):
            self.assertEqual(reel_formats.caption_emoji(value, "le billet d'entrée"), "💶", value)

    def test_a_table_that_would_run_over_its_columns_is_never_chosen(self):
        vietnam = [["Nord (Hanoï, Ninh Bình, Sa Pa)", "Octobre-novembre et avril à juin (21 à 28 °C)"],
                   ["Centre (Hué, Hội An, Đà Nẵng)", "Février à mai"], ["Sud (Saïgon, delta du Mékong)", "Décembre à avril"]]
        self.assertFalse(p.motion.table_fits(vietnam, reel_formats.TABLE_FONTS))
        self.assertFalse(p.motion.table_fits([["Golfe", "Llanfairpwllgwyngyll"]] * 3, reel_formats.TABLE_FONTS))   # one word too wide
        # A word too wide with dashes is cut after them, each piece keeping its dash.
        self.assertTrue(p.motion.table_fits([["Golfe", "Octobre-novembre"]] * 3, reel_formats.TABLE_FONTS))
        self.assertTrue(p.motion.table_fits([["Alfa Pendular Turística", "35,70 €"], ["Intercidades 2e classe", "28,05 €"],
                                             ["Alfa Pendular Conforto", "49,90 €"]], reel_formats.TABLE_FONTS))

    def test_a_table_at_the_edge_of_its_column_is_drawn_but_never_chosen(self):
        # "Randonnées au nord" measures 440 px here and a hair more on the Linux runner: the plan rendered on 15/11 still
        # lays out (slack), and the generator chooses no table that close to its columns (margin).
        from PIL import Image, ImageDraw
        rows = [["Randonnées au nord (Masca, Anaga)", "Avril-mai, octobre"], ["Nager dans une mer tiède", "Septembre à novembre"],
                ["Teide et ciel étoilé", "Avril à octobre"]]
        self.assertGreater(p.motion.table(ImageDraw.Draw(Image.new("RGBA", (8, 8))), False, 0, rows, reel_formats.TABLE_FONTS), 0)
        self.assertFalse(p.motion.table_fits(rows, reel_formats.TABLE_FONTS))

    def test_a_word_too_wide_is_cut_after_its_dashes_and_a_lone_dash_keeps_its_spaces(self):
        from PIL import Image, ImageDraw
        draw, fonts, size = ImageDraw.Draw(Image.new("RGBA", (8, 8))), reel_formats.TABLE_FONTS, p.motion.ROW_SIZE
        self.assertEqual(p.motion.wrap(draw, "Boucle Salerne–Positano–Amalfi–Salerne", fonts.bold, size, fonts, 440),
                         ["Boucle Salerne–", "Positano–Amalfi–", "Salerne"])
        # Three lines: that table is not chosen (it ran over its column in the reel of 04/12 generated before this rule).
        self.assertFalse(p.motion.table_fits([["Boucle Salerne–Positano–Amalfi–Salerne", "39 €"]] * 3, fonts))
        self.assertEqual(p.motion.wrap(draw, "Lisbonne – Porto en train", fonts.bold, size, fonts, 366), ["Lisbonne – Porto", "en train"])

    def test_a_table_label_never_names_another_train(self):
        alfa = names.words("L’intérieur d’une voiture Alfa Pendular. Alfa Pendular interior")
        self.assertTrue(names.label_clash("Alfa Pendular ou Intercidades", alfa))
        self.assertFalse(names.label_clash("Le train Alfa Pendular", alfa))
        table = {"photo": "train-interieur", "layout": "table", "kicker": "Alfa Pendular ou Intercidades", "headline": ["Lisbonne → Porto"],
                 "alt": "L’intérieur d’une voiture Alfa Pendular."}
        photos = {"train-interieur": {"commonsTitle": "File:Alfa Pendular interior.jpg"}}
        self.assertIn("another train", p.another_place(table, photos, names.words("Portugal")))
        self.assertIsNone(p.another_place({**table, "kicker": "Lisbonne → Porto"}, photos, names.words("Portugal")))


class RetouchedPhotos(unittest.TestCase):
    """Review of the Pins (15/11/2026): a file whose history says "slight cloning" is no photograph as taken."""

    def answer(self, comments, description="View of the bridge at night"):
        def fetch(params):
            if params.get("iiprop") == "comment":
                return {"query": {"pages": {"1": {"imageinfo": [{"comment": text} for text in comments]}}}}
            return {"query": {"pages": {"1": {"imageinfo": [{"mime": "image/jpeg", "width": 4000, "height": 3000, "extmetadata": {
                "ImageDescription": {"value": description}, "Categories": {"value": "Luiz I bridge"},
                "Model": {"value": "Canon EOS 5DS R"}}}]}}}}
        return fetch

    def test_a_history_that_admits_cloning_refuses_the_file(self):
        import photo_intake
        from unittest import mock
        title = "File:Some bridge at night.jpg"
        with mock.patch.object(photo_intake, "fetch_json", self.answer(["Curves", "Highlights, slight cloning", "HDR artifacts"])):
            with self.assertRaises(photo_intake.Refused):
                photo_intake.commons_info(title)
        with mock.patch.object(photo_intake, "fetch_json", self.answer(["Curves"], "A tourist removed from the square")):
            with self.assertRaises(photo_intake.Refused):
                photo_intake.commons_info(title)
        with mock.patch.object(photo_intake, "fetch_json", self.answer(["Curves", "Perspective correction"])):
            self.assertEqual(photo_intake.commons_info(title)["width"], 4000)

    def test_the_whole_history_is_read_page_after_page(self):
        import photo_intake
        from unittest import mock
        def fetch(params):
            if params.get("iiprop") != "comment":
                return self.answer([])(params)
            if "iistart" not in params:
                return {"continue": {"iistart": "2019-06-02T10:00:00Z", "continue": "||"},
                        "query": {"pages": {"1": {"imageinfo": [{"comment": "Curves"}] * 50}}}}
            return {"query": {"pages": {"1": {"imageinfo": [{"comment": "Highlights, slight cloning"}]}}}}
        with mock.patch.object(photo_intake, "fetch_json", fetch):
            self.assertEqual(len(photo_intake.history_comments("File:X.jpg")), 51)
            with self.assertRaises(photo_intake.Refused):
                photo_intake.commons_info("File:X.jpg")

    def test_the_retouched_bridge_of_porto_is_named(self):
        import photo_intake
        self.assertIn("File:Puente de Don Luis I, Oporto, Portugal, 2019-06-02, DD 29-31 HDR.jpg", photo_intake.NOT_A_PHOTOGRAPH_AS_TAKEN)
        self.assertTrue(photo_intake.derived_record({"commonsTitle": "File:Puente de Don Luis I, Oporto, Portugal, 2019-06-02, DD 29-31 HDR.jpg"}))


class ReviewOfPullRequest54(unittest.TestCase):
    """Review of PR 54 (15/11/2026): one test per point."""

    def test_a_table_of_prices_in_several_columns_is_not_chosen(self):
        cinque = {"title": "La Cinque Terre Card : laquelle acheter", "table": {"headers": ["Treno Card adulte 2026", "Jour A", "Jour B", "Jour C"],
                  "rows": [["1 jour", "22 €", "29,50 €", "35 €"], ["2 jours", "36,50 €", "51 €", "61 €"], ["3 jours", "49 €", "68 €", "81 €"]]}}
        page = p.normalized("Jour A 1 jour 22 € 2 jours 36,50 € 3 jours 49 €")
        self.assertIsNone(reel_formats.table_of({"sections": [cinque]}, page))
        algarve = {"title": "Une ligne", "table": {"headers": ["Trajet", "Prix régional", "Durée"],
                   "rows": [["Faro → Olhão", "1,60 €", "quelques minutes"], ["Faro → Tavira", "3,60 €", "33 min"], ["Faro → Lagos", "8,30 €", "1 h 35"]]}}
        page = p.normalized("Prix régional Faro → Olhão 1,60 € Faro → Tavira 3,60 € Faro → Lagos 8,30 €")
        table = reel_formats.table_of({"sections": [algarve]}, page)
        self.assertEqual(table["header"], "Prix régional")
        self.assertTrue(all(line.startswith("💶") for line in reel_formats.table_lines("Prix régional", table["rows"])))

    def test_a_journey_through_a_name_with_a_kind_of_place_or_by_a_named_train_is_strict(self):
        belem = "8 min de train entre Cais do Sodré et Belém"
        self.assertTrue(names.strict_journey(belem))
        jeronimos = photo("lisbonne-jeronimos", "File:Jeronimos.jpg", "La façade sculptée du monastère des Jerónimos, à Belém.")
        self.assertIsNone(reel_formats.Media([jeronimos], [], everywhere="Portugal Portugal").named(belem, None))
        scene = {"photo": "lisbonne-jeronimos", "headline": ["*8 min*"], "detail": "de train entre Cais do Sodré et Belém", "alt": jeronimos[2]}
        self.assertIn("no ride", p.another_place(scene, {"lisbonne-jeronimos": jeronimos[1]}, names.words("Portugal Lisbonne")))
        self.assertTrue(names.strict_journey("de Tokyo à Kyoto en Nozomi"))
        shibuya = photo("japon-tokyo-shibuya", "File:Shibuya.jpg", "Le carrefour de Shibuya, à Tokyo.")
        self.assertIsNone(reel_formats.Media([shibuya], [], everywhere=JAPON).named("de Tokyo à Kyoto en Nozomi, 13 960 ¥", None))

    def test_the_coach_is_a_means_of_transport_not_the_conjunction(self):
        self.assertEqual(names.wanted_ways("3 h de car pour Essaouira : dès 100 dh chez Supratours"), {"road"})
        self.assertTrue(names.journey("3 h de car pour Essaouira"))
        self.assertEqual(names.wanted_ways("une ville à voir, car il y fait doux en hiver"), set())
        boats = names.vehicle("marrakech-essaouira-port", "Des barques bleues au pied de la Skala du port, à Essaouira.", "File:Skala.jpg")
        self.assertTrue(names.other_ride(boats, "3 h de car pour Essaouira"))

    def test_a_title_line_never_ends_on_a_number_nor_cuts_a_name(self):
        self.assertEqual(reel_formats.lines_of("Le Japon en 2 semaines", 16), ["Le Japon", "en 2 semaines"])
        self.assertNotEqual(reel_formats.lines_of("Les Cinque Terre en train", 16), ["Les Cinque", "Terre en train"])
        self.assertEqual(reel_formats.lines_of("du 28 octobre 2026 au 3 janvier 2027", 22), ["du 28 octobre 2026", "au 3 janvier 2027"])

    def test_a_section_name_stands_over_a_figure_only_when_the_figure_speaks_of_it(self):
        halong = photo("vietnam-halong", "File:Ha Long Bay.jpg", "Une jonque dans la baie d'Ha Long.")
        media = reel_formats.Media([halong], [], everywhere=VIETNAM)
        when = {"title": "Quand partir", "image": "vietnam-halong"}
        self.assertEqual(media.above(when, "vietnam-halong", "Vietnam", "de séjour sans visa pour les Français"), "Vietnam")
        self.assertEqual(media.above(when, "vietnam-halong", "Vietnam", "la meilleure période pour partir au nord"), "Quand partir")
        days = {"title": "Jours 3 à 5 — Ninh Bình", "image": "vietnam-halong"}
        self.assertEqual(media.above(days, "vietnam-halong", "Vietnam", "la balade en barque"), "Jours 3 à 5")
        garden = photo("londres-covent-garden", "File:Covent Garden.jpg", "La halle de Covent Garden.")
        calendar = {"title": "Le calendrier de l’hiver 2026", "image": "londres-covent-garden"}
        london = reel_formats.Media([garden], [], everywhere="Royaume-Uni Londres")
        self.assertEqual(london.above(calendar, "londres-covent-garden", "Londres", "le plafond quotidien du métro en zones 1-2, 2026"), "Londres")


class FollowUpOfPullRequest54(unittest.TestCase):
    """The follow-up of the review of PR 54 (15/11/2026): one test per point."""

    def test_a_journey_never_goes_over_a_ride_of_another_means_even_when_it_shows_the_place(self):
        # Media.misleads: the ferry to Cacilhas is no train of Cacilhas, though both name the place.
        train = photo("lisbonne-cacilhas-train", "File:Cacilhas.jpg", "Un train de banlieue en gare de Cacilhas.")
        media = reel_formats.Media([train], [], everywhere="Portugal Portugal")
        self.assertIsNone(media.named("le ferry pour Cacilhas, 10 minutes face à la ville", None))
        self.assertEqual(media.left_for("la traversée en ferry, 10 minutes"), [])

    def test_the_same_guide_never_twice_on_one_network_within_two_weeks(self):
        import datetime as dt
        import auto_social as a
        slot = dt.datetime(2026, 11, 26, 8, tzinfo=dt.timezone.utc)
        guide = {"slug": "vietnam-quand-partir", "country": "vietnam", "publishedOn": "2026-11-01"}
        other = {"slug": "laponie-budget-rovaniemi", "country": "finlande", "publishedOn": "2026-10-01"}
        url = a.guide_url(guide)
        rows = [{"channel": "instagram", "kind": "reel", "url": url, "dueAt": slot - dt.timedelta(days=5)}]
        order = a.guide_order([guide, other], a.Post("instagram", "carousel"), rows, slot)
        self.assertEqual([article["slug"] for article in order], ["laponie-budget-rovaniemi"])
        later = a.guide_order([guide, other], a.Post("instagram", "carousel"), rows, slot + dt.timedelta(days=10))
        self.assertIn("vietnam-quand-partir", [article["slug"] for article in later])
        facebook = a.guide_order([guide, other], a.Post("facebook", "carousel"), rows, slot)
        self.assertIn("vietnam-quand-partir", [article["slug"] for article in facebook])

    def test_a_titled_stretch_takes_its_brackets_whole(self):
        self.assertEqual(names.titled("La mer d’Andaman (Phuket, Krabi) : décembre à mars", names.words("Thaïlande")), "Andaman (Phuket, Krabi)")
        for title in ("Le golfe de Thaïlande (Koh Samui)", "La mer d’Andaman (Phuket, Krabi)", "Jours 6 et 7 — Hué"):
            stretch = names.titled(title, names.words("Thaïlande Vietnam"))
            self.assertEqual(stretch.count("("), stretch.count(")"), title)

    def test_a_card_is_no_place(self):
        self.assertEqual(names.names("La Cinque Terre Card : laquelle acheter", sentence=True)[0][0], ("cinque", "terre"))
        self.assertEqual(names.titled("La Cinque Terre Card : laquelle acheter", names.words("Italie Cinque Terre")), "")

    def test_a_table_of_journeys_goes_over_a_ride_of_its_means(self):
        rows = [["Séville → Cordoue (AVE, Avant)", "40 à 48 min"], ["Cordoue → Grenade (AVE, Avant)", "1 h 37 à 1 h 56"],
                ["Séville → Grenade (Avant)", "2 h 37 à 2 h 52"]]
        self.assertEqual(names.journeys_table(rows, "Durée en direct"), {"rail"})
        self.assertEqual(names.journeys_table([["Plage", "Novembre"], ["Teide", "Avril"], ["Masca", "Mai"]]), set())
        table = {"photo": "cordoue-mezquita", "layout": "table", "kicker": "Andalousie", "headline": ["Durée en direct"], "rows": rows,
                 "alt": "Les arcs de la Mezquita de Cordoue."}
        everywhere = names.words("Espagne Andalousie")
        self.assertIn("no ride", p.another_place(table, {"cordoue-mezquita": {"commonsTitle": "File:Mezquita.jpg"}}, everywhere))
        ave = {**table, "photo": "andalousie-ave", "alt": "Un train AVE en gare de Cordoue."}
        self.assertIsNone(p.another_place(ave, {"andalousie-ave": {"commonsTitle": "File:AVE Cordoba.jpg"}}, everywhere))
        mezquita = photo("cordoue-mezquita", "File:Mezquita.jpg", "Les arcs de la Mezquita de Cordoue.")
        brief_table = {"rows": rows, "header": "Durée en direct", "section": {"title": "Les trains : la boucle Séville, Cordoue, Grenade"}}
        media, ride = reel_formats.Media([mezquita], [], everywhere="Espagne Andalousie"), reel_formats.table_ride(brief_table)
        with self.assertRaises(reel_formats.Held):
            media.photo(ride, brief_table["section"], strict=True)

    def test_the_section_a_figure_comes_from_goes_from_the_generator_to_the_guard(self):
        import auto_social as a
        hue = {"title": "Jours 6 et 7 — Hué", "image": "vietnam-hue"}
        def fact(value, label, section, heading):
            return {"value": value, "label": label, "excerpt": value + " " + label, "section": section, "short": label,
                    "shortExcerpt": value + " " + label, "heading": heading}
        facts = [fact("150 000 ₫", "les tombeaux coûtent chacun", hue, "Jours 6 et 7 — Hué"),
                 fact("1 200 000 ₫", "la croisière dans la baie d’Ha Long", {"title": "Jours 3 à 5 — Ha Long"}, "Jours 3 à 5 — Ha Long"),
                 fact("120 000 ₫", "le billet de la vieille ville de Hội An", {"title": "Jours 8 à 10 — Hội An"}, "Jours 8 à 10 — Hội An"),
                 fact("4 mm", "de pluie à Hô-Chi-Minh-Ville en février", {"title": "Jours 13 à 15 — Hô-Chi-Minh-Ville"}, "Jours 13 à 15 — Hô-Chi-Minh-Ville")]
        photos = [photo("vietnam-train-hanoi", "File:Train street.jpg", "La rue du train de Hanoï.", emblematic=True),
                  photo("vietnam-hue", "File:Hue citadel gate.jpg", "La porte de la cité impériale de Hué."),
                  photo("vietnam-halong", "File:Ha Long Bay.jpg", "Une jonque dans la baie d’Ha Long."),
                  photo("vietnam-hoi-an", "File:Hoi An.jpg", "Une maison aux lanternes de la vieille ville de Hội An."),
                  photo("vietnam-saigon", "File:Saigon.jpg", "La poste centrale de Hô-Chi-Minh-Ville."),
                  photo("vietnam-sapa", "File:Sapa.jpg", "Les rizières de Sa Pa.", emblematic=True)]
        article = {"slug": "vietnam-itineraire-15-jours", "country": "vietnam", "destination": "Vietnam", "title": "Le Vietnam en 15 jours",
                   "shortTitle": "Le Vietnam en 15 jours", "sourcesCheckedOn": "2026-10-24", "sections": [hue], "cover": "vietnam-train-hanoi"}
        scenes = a.scenes_for(article, a.Post("instagram", "carousel"), facts, list(photos), "Phrase d’ouverture.", "Vietnam", "Vietnam")
        tombs = next(scene for scene in scenes if "tombeaux" in (scene.get("detail") or ""))
        self.assertEqual((tombs["photo"], tombs.get("where")), ("vietnam-hue", "Jours 6 et 7 — Hué"))
        self.assertEqual(tombs["facts"][0]["excerpt"], "Jours 6 et 7 — Hué")
        records = {identifier: record for identifier, record, _ in photos}
        self.assertIsNone(p.another_place({**tombs, "alt": photos[1][2]}, records, names.words("Vietnam")))
        self.assertIsNotNone(p.another_place({**tombs, "photo": "vietnam-halong", "alt": photos[2][2]}, records, names.words("Vietnam")))

    def test_a_figure_that_points_back_to_another_sentence_is_left_in_the_guide(self):
        import auto_social as a
        for label in ("le même trajet en tram si vous payez à bord", "la même entrée le dimanche", "ce billet pour deux jours",
                      "celui-ci en haute saison"):
            self.assertTrue(a.REPRISE.match(label), label)
        self.assertFalse(a.REPRISE.match("le trajet en tram de la Baixa à Belém"))
        self.assertFalse(a.REPRISE.match("certains jours, l’entrée est gratuite"))
        article = {"keyFacts": [{"value": "3,30 €", "label": "le même trajet en tram si vous payez à bord"},
                                {"value": "1,90 €", "label": "le ticket Carris sur carte Navegante"}]}
        page = "3,30 € le même trajet en tram si vous payez à bord. 1,90 € le ticket Carris sur carte Navegante."
        self.assertEqual([fact["value"] for fact in a.usable_facts(article, page)], ["1,90 €"])

    def test_the_facade_of_a_station_is_no_train(self):
        self.assertEqual(names.vehicle("train-campanha", "La façade de la gare de Porto-Campanhã.", "File:Campanha.jpg"), set())
        # Review of PR 56: nor for a ride, at the choice and at the guard.
        facade = photo("train-campanha", "File:Campanha.jpg", "La façade de la gare de Porto-Campanhã.")
        alfa = "Alfa Pendular Lisbonne → Porto-Campanhã en Turística"
        self.assertIsNone(reel_formats.Media([facade], [], everywhere="Portugal Portugal").named(alfa, None))
        scene = {"photo": "train-campanha", "headline": ["*35,70 €*"], "detail": alfa, "alt": facade[2]}
        self.assertIsNotNone(p.another_place(scene, {"train-campanha": facade[1]}, names.words("Portugal")))
        rows = [["Lisbonne → Porto (Alfa Pendular)", "2 h 58"], ["Lisbonne → Coimbra (Alfa Pendular)", "1 h 40"], ["Porto → Braga (Urbano)", "1 h"]]
        table = {"photo": "train-campanha", "layout": "table", "kicker": "Portugal", "headline": ["Durée en train"], "rows": rows, "alt": facade[2]}
        self.assertIn("no ride", p.another_place(table, {"train-campanha": facade[1]}, names.words("Portugal")))
        self.assertEqual(names.vehicle("vietnam-trang-an", "Des barques sur la rivière de Tràng An.", "File:Trang An boats.jpg"), {"water"})


class OpeningAndSubject(unittest.TestCase):
    """Review of PR 56, points 6 and 7."""

    def test_a_post_opens_on_its_destination_not_on_an_outing(self):
        port = photo("marrakech-essaouira-port", "File:Skala.jpg", "Des barques bleues au pied de la Skala du port, à Essaouira.")
        majorelle = photo("marrakech-majorelle", "File:Majorelle.jpg", "La villa bleue du jardin Majorelle.")
        koutoubia = photo("marrakech-koutoubia", "File:Koutoubia.jpg", "Le minaret de la Koutoubia, à Marrakech.", emblematic=True)
        media = reel_formats.Media([port, majorelle, koutoubia], [], cover="marrakech-place-jemaa-el-fna",
                                   emblematic=("marrakech-koutoubia",), everywhere="Maroc Marrakech", local=True)
        self.assertTrue(media.excursion(port))
        self.assertFalse(media.excursion(koutoubia))
        self.assertEqual(media.opening("marrakech-place-jemaa-el-fna")[1], "marrakech-majorelle")
        # Only an outing left to open with (the Koutoubia kept for the call to action): the post waits.
        alone = reel_formats.Media([port, koutoubia], [], emblematic=("marrakech-koutoubia",), everywhere="Maroc Marrakech", local=True)
        with self.assertRaises(reel_formats.Held):
            alone.opening(None)
        # A guide of a country has its stages in many towns: "…, à Kyoto" is no outing there.
        kyoto = photo("japon-kyoto", "File:Kiyomizu.jpg", "Le temple Kiyomizu-dera, à Kyoto.")
        japan = reel_formats.Media([kyoto], [], everywhere="Japon Japon", local=False)
        self.assertFalse(japan.excursion(kyoto))
        # A quarter of the town is the town: "…, à Belém" in a guide of Lisbon.
        belem = photo("lisbonne-jeronimos", "File:Jeronimos.jpg", "La façade sculptée du monastère des Jerónimos, à Belém.")
        self.assertFalse(reel_formats.Media([belem], [], everywhere="Portugal Lisbonne", local=True).excursion(belem))

    def test_never_the_same_subject_twice_in_a_post(self):
        north = photo("yucatan-el-castillo", "File:Kukulcan, Chichen Itza.jpg", "La pyramide d’El Castillo, à Chichén Itzá, sous un ciel sans nuage.")
        south = photo("yucatan-chichen-itza", "File:Templo el Castillo - Chichen Itza-Yucatan-Mexico0222.jpg", "La pyramide d’El Castillo, à Chichén Itzá.")
        cenote = photo("yucatan-cenote", "File:Cenote Ik Kil.jpg", "Un cenote entouré de lianes.")
        media = reel_formats.Media([north, south, cenote], [], cover="yucatan-el-castillo", everywhere="Mexique Yucatán")
        self.assertEqual(media.subject(north), media.subject(south))
        self.assertEqual(media.opening("yucatan-el-castillo")[1], "yucatan-el-castillo")
        self.assertNotIn("yucatan-chichen-itza", [ph[0] for ph in media.free()])
        self.assertIsNone(media.named("697 pesos l’entrée de Chichén Itzá pour un étranger", None))
        # Two photos of one town are not one subject: the village and the office of Santa Claus, both at Rovaniemi.
        village = photo("lap-village", "File:Village.jpg", "Le village sous la neige en décembre, à Rovaniemi.")
        office = photo("lap-bureau", "File:Office.jpg", "Le bureau du Père Noël illuminé, à Rovaniemi.")
        lapland = reel_formats.Media([village, office], [], everywhere="Finlande Laponie")
        lapland.photos.remove(village)
        self.assertIn("lap-bureau", [ph[0] for ph in lapland.free()])


class RideToAnotherPlace(unittest.TestCase):
    """Review of PR 56, point 4, the narrow rule: a fact that names its means of transport and another place than the
    photo's goes over a photo of that means; a fare taken in the town stays over a photo of the town."""

    ALFAMA = photo("lisbonne-alfama", "File:Alfama.jpg", "Les toits et l’église de São Vicente, dans l’Alfama, à Lisbonne.")
    FERRY = photo("lisbonne-cacilhas-ferry", "File:Cacilhas ferry.jpg", "Un ferry de la Transtejo sur le Tage, vers Cacilhas.")
    EVERYWHERE = "Portugal Lisbonne"

    def shown(self, record: tuple) -> set[str]:
        return reel_formats.Media([record], [], everywhere=self.EVERYWHERE).described(record)

    def test_a_ride_to_another_place_needs_its_means(self):
        alfama, everywhere = self.shown(self.ALFAMA), names.words(self.EVERYWHERE)
        for text in ("2 € la traversée du Tage en ferry vers Cacilhas", "35,70 € l’Alfa Pendular entre les deux villes",
                     "4,50 € le bus pour Sintra depuis Lisbonne"):
            self.assertTrue(names.ride_needed(text, alfama, everywhere), text)

    def test_a_fare_inside_the_town_stays_over_the_town(self):
        alfama, everywhere = self.shown(self.ALFAMA), names.words(self.EVERYWHERE)
        for text in ("16 à 23 € le taxi depuis l’aéroport de Lisbonne", "8,90 € le plafond quotidien du métro",
                     "16,55 € l’Andante Tour 3 : métro, bus et trains urbains pendant 72 h", "10 € la tour de Belém"):
            self.assertFalse(names.ride_needed(text, alfama, everywhere), text)

    def test_the_generator_puts_the_ride_over_its_means_or_leaves_it_in_the_guide(self):
        ferry = "2 € la traversée du Tage en ferry vers Cacilhas"
        media = reel_formats.Media([self.ALFAMA, self.FERRY], [], everywhere=self.EVERYWHERE)
        self.assertTrue(media.misleads(ferry, self.ALFAMA))
        self.assertFalse(media.misleads(ferry, self.FERRY))
        self.assertEqual(media.photo(ferry)[1], "lisbonne-cacilhas-ferry")
        alone = reel_formats.Media([self.ALFAMA], [], everywhere=self.EVERYWHERE)
        self.assertEqual(alone.takeable(ferry), [])

    def test_the_guard_refuses_it_only_in_posts_made_after_the_rule(self):
        # "Entre les deux villes" names no place: only the rule on rides refuses it over a church of Alfama.
        scene = {"photo": "lisbonne-alfama", "headline": ["*35,70 €*"], "detail": "l’Alfa Pendular entre les deux villes",
                 "alt": self.ALFAMA[2]}
        records, everywhere = {"lisbonne-alfama": self.ALFAMA[1]}, names.words(self.EVERYWHERE)
        self.assertIn("ride to another place", p.another_place(scene, records, everywhere))
        # A post sealed before 17/11/2026 stays valid in the queue: the guard reads it as it was made.
        self.assertIsNone(p.another_place(scene, records, everywhere, rides=False))
        self.assertGreater(p.instant(p.RIDES_FROM), p.instant(p.PLACES_FROM))

    def test_a_station_is_no_train(self):
        # "Estación de tren São Bento": the hall of azulejos took "l'Alfa Pendular entre les deux villes".
        hall = photo("porto-sao-bento", "File:Estación de tren São Bento, Oporto, Portugal, 2012-05-09, DD 07.JPG",
                     "Les panneaux d’azulejos bleus du hall de la gare de São Bento.")
        self.assertEqual(names.vehicle(hall[0], hall[2], hall[1]["commonsTitle"]), set())
        self.assertEqual(names.vehicle("porto-metro", "La station de métro Aeroporto, à Porto.", "File:Porto airport metro station.jpg"), set())
        self.assertEqual(names.vehicle("lap-train", "Un train de nuit en gare de Rovaniemi.", "File:Rovaniemi railway station.jpg"), {"rail"})
        media = reel_formats.Media([hall], [], everywhere="Portugal Porto")
        self.assertTrue(media.misleads("35,70 € l’Alfa Pendular entre les deux villes", hall))


class OpeningAndEndingReservedFirst(unittest.TestCase):
    """Review of PR 56: the opening and the ending are reserved before the figures. "100 à 160 dh le taxi au départ de
    l'aéroport" took Jemaa el-Fna, and the posts of Marrakech had only Essaouira left to open on."""

    JEMAA = photo("marrakech-place-jemaa-el-fna", "File:Jamaa El Fna.jpg", "La place Jemaa el-Fna en fin de journée.", emblematic=True)
    KOUTOUBIA = photo("marrakech-koutoubia", "File:Koutoubia.jpg", "Le minaret de la Koutoubia, à Marrakech.", emblematic=True)
    PORT = photo("marrakech-essaouira-port", "File:Skala.jpg", "Des barques bleues au pied de la Skala du port, à Essaouira.")
    TAXI = "le taxi au départ de l’aéroport selon la zone"   # the label of "100 à 160 dh", as Media.about reads it

    def media(self, *more: tuple) -> reel_formats.Media:
        photos = [self.JEMAA, self.KOUTOUBIA, self.PORT, *more]
        return reel_formats.Media(photos, [], reserve=2, cover=self.JEMAA[0], emblematic=reel_formats.emblematic(photos),
                                  everywhere="Maroc Marrakech", local=True)

    def test_a_figure_of_no_place_never_takes_the_cover_nor_the_ending(self):
        media = self.media()
        self.assertEqual(media.kept(), {self.JEMAA[0], self.KOUTOUBIA[0]})
        # Only the boats of Essaouira are left: no photo for a taxi, the figure stays in the guide.
        with self.assertRaises(reel_formats.Held):
            media.photo(self.TAXI)
        self.assertEqual(media.opening(self.JEMAA[0])[1], self.JEMAA[0])

    def test_a_fare_of_the_town_takes_a_photo_of_the_town_left_free(self):
        souk = photo("marrakech-souk", "File:Souk.jpg", "Une ruelle des souks de la médina, à Marrakech.")
        media = self.media(souk)
        self.assertEqual(media.photo(self.TAXI)[1], "marrakech-souk")
        self.assertEqual(media.opening(self.JEMAA[0])[1], self.JEMAA[0])
        self.assertEqual(media.closing()[1], self.KOUTOUBIA[0])

    def test_a_photo_added_for_the_posts_is_offered_before_the_old_catalogue(self):
        # The metro on the bridge Luís I came after seventeen photos of the old catalogue and was never offered.
        import datetime as dt
        import json
        import tempfile
        from pathlib import Path
        import media_library
        with tempfile.TemporaryDirectory() as folder:
            photos = Path(folder) / "assets" / "photos"
            photos.mkdir(parents=True)
            old = {f"porto-old-{n:02}": {"commonsTitle": f"File:Old {n}.jpg"} for n in range(17)}
            (photos / "catalogue.json").write_text(json.dumps({"schemaVersion": 1, "photos": old}))
            (photos / "reviewed.json").write_text(json.dumps({"schemaVersion": 1, "photos": {"porto-metro-luis-tablier": {"commonsTitle": "File:Metro.jpg"}}}))
            shared = media_library.Photos(Path(folder), dt.datetime(2026, 11, 16, tzinfo=dt.timezone.utc)).shared
        self.assertEqual(next(iter(shared)), "porto-metro-luis-tablier")
        self.assertEqual(len(shared), 18)

    def test_a_town_stays_a_town_when_its_kicker_is_shortened(self):
        # Review of PR 57 (Codex): "Maroc · Marrakech" read the town from its separator; a kicker longer than 32 letters
        # is cut to the place alone, and the reel of a town could open on an outing again.
        import datetime as dt
        from pathlib import Path
        from unittest import mock
        import auto_social as a
        import destinations

        class Seen(Exception):
            pass

        def media(*args, **kwargs):
            raise Seen(kwargs["local"])

        with mock.patch.object(reel_formats, "Media", side_effect=media):
            for kicker, local, expected in (("Maroc · Marrakech", None, True), ("Marrakech", None, False), ("Marrakech", True, True)):
                with self.assertRaises(Seen) as seen:
                    reel_formats.build("liste", {}, [], [self.JEMAA], [], "", "Marrakech", kicker, "", [], "", local=local)
                self.assertIs(seen.exception.args[0], expected, kicker)
        # build_reel says it whatever the length of the kicker.
        table = destinations.load(Path(a.__file__).resolve().parents[2] / "site-src")
        article = {"slug": "x", "country": "republique-dominicaine", "destination": "Punta Cana et Bávaro", "sourcesCheckedOn": "2026-11-01",
                   "title": "Punta Cana et Bávaro en 5 jours", "shortTitle": "Punta Cana en 5 jours"}
        with mock.patch.object(reel_formats, "build", side_effect=lambda *args, **kwargs: (_ for _ in ()).throw(Seen(kwargs.get("local")))), \
                mock.patch.object(destinations, "name", return_value="République dominicaine"), \
                mock.patch.object(a, "opening_sentence", return_value="Phrase d’ouverture."):
            with self.assertRaises(Seen) as seen:
                now = dt.datetime(2026, 11, 16, tzinfo=dt.timezone.utc)
                a.build_reel(Path(a.__file__).parent, article, now, now, "", [], [], "liste", 0, 0, table, 34)
        self.assertIs(seen.exception.args[0], True)


if __name__ == "__main__":
    unittest.main()
