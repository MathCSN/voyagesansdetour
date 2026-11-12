"""Offline tests for stale_lots.py: the stock, the scenarios and the guide pages are made up."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import stale_lots

NOW = dt.datetime(2026, 11, 12, 20, 0, tzinfo=dt.timezone.utc)
GUIDE = "https://voyagesansdetour.fr/mexique/yucatan/"
FARE = "977,50 pesos le billet Mérida–Cancún aéroport en tarif touriste international"
ENTRY = "697 pesos l’entrée de Chichén Itzá pour un étranger"
OPENING = "Dix jours suffisent pour boucler le Yucatán."


def page(*sentences):
    return "<html><body><h1>Yucatán</h1>" + "".join(f"<p>{sentence}</p>" for sentence in sentences) + "<script>var x = 977.50;</script></body></html>"


class Stock:
    """A stock of batches in a temporary folder; each post quotes one page of the site, and sometimes another site."""

    def __init__(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        (self.root / "reviewed-social").mkdir()
        (self.root / "scenarios").mkdir()
        self.index = {"schemaVersion": 1, "items": [], "retirements": []}
        self.pages = {}

    def post(self, name, quotes, due=NOW + dt.timedelta(days=8), url=GUIDE, copies=("",), other=()):
        sources = {"guide": {"url": url}, "rail": {"url": "https://www.example.org/fares"}}
        (self.root / "auto" / name).mkdir(parents=True)
        (self.root / "auto" / name / "sources.json").write_text(json.dumps({"schemaVersion": 1, "sources": sources}))
        facts = [{"source": "guide", "excerpt": quote} for quote in quotes] + [{"source": "rail", "excerpt": quote} for quote in other]
        scenario = {"id": name, "sources": {"file": f"auto/{name}/sources.json"}, "scenes": [{"facts": [fact]} for fact in facts] + [{"headline": ["Fin"]}]}
        (self.root / "scenarios" / f"{name}.json").write_text(json.dumps(scenario))
        for number, copy in enumerate(copies):
            batch = name + copy + "-v1"
            item = {"dueAt": (due + dt.timedelta(hours=number)).strftime("%Y-%m-%dT%H:%M:%SZ"), "payload": {"channel": copy.strip("-") or "instagram"}}
            (self.root / "reviewed-social" / f"{batch}.json").write_text(json.dumps({"schemaVersion": 1, "batchId": batch, "items": [item]}))
            self.index["items"].append({"path": f".github/vsd-production/reviewed-social/{batch}.json", "fileSha256": "f" * 64, "batchId": batch,
                                        "batchSha256": "b" * 64, "itemIds": [f"vsd-production:{name}{copy}"]})
        self.save()

    def save(self):
        (self.root / "reviewed-social" / "index.json").write_text(json.dumps(self.index, ensure_ascii=False, indent=2) + "\n")

    def fetch(self, url):
        if url not in self.pages:
            raise OSError("unreachable")
        return self.pages[url]

    def run(self, withdraw=True, now=NOW):
        return stale_lots.run(self.root, now, fetcher=self.fetch, withdraw=withdraw)

    def retirements(self):
        return json.loads((self.root / "reviewed-social" / "index.json").read_text())["retirements"]


class StaleLotsTests(unittest.TestCase):
    def stock(self):
        stock = Stock()
        self.addCleanup(stock.folder.cleanup)
        return stock

    def test_a_batch_whose_figure_left_the_guide_is_withdrawn_with_its_copy_and_nothing_else_is_touched(self):
        stock = self.stock()
        stock.post("ig-yucatan", [OPENING, FARE, ENTRY], copies=("", "-tiktok"))
        stock.post("fb-yucatan", [ENTRY])
        stock.post("ig-kyoto", ["500 ¥ l’entrée du temple"], url="https://voyagesansdetour.fr/japon/kyoto/")
        stock.pages = {GUIDE: page(OPENING, "1 041,50 pesos le billet Mérida–Cancún aéroport en tarif touriste international", ENTRY),
                       "https://voyagesansdetour.fr/japon/kyoto/": page("500 ¥ l’entrée du temple")}
        before = {path: path.read_bytes() for path in stock.root.rglob("*") if path.is_file() and path.name != "index.json"}
        result = stock.run()
        self.assertEqual((result["status"], result["checked"], result["reported"], result["unread"]), ("stale", 4, [], []))
        self.assertEqual(result["retired"], ["ig-yucatan-v1", "ig-yucatan-tiktok-v1"])
        entries = stock.retirements()
        self.assertEqual([entry["batchId"] for entry in entries], ["ig-yucatan-v1", "ig-yucatan-tiktok-v1"])
        self.assertEqual({(entry["reason"], entry["retiredAt"], entry["batchSha256"], entry["fileSha256"]) for entry in entries},
                         {("figure_no_longer_in_guide", "2026-11-12T20:00:00Z", "b" * 64, "f" * 64)})
        self.assertEqual(entries[0]["itemIds"], ["vsd-production:ig-yucatan"])
        self.assertIn("« " + FARE + " » (ne se lit plus : 977,50)", entries[0]["evidence"])
        self.assertIn("Relecture du 12/11/2026 : " + GUIDE + " ne donne plus 1 des 3 citations", entries[0]["evidence"])
        self.assertEqual({path: path.read_bytes() for path in before}, before)  # no scenario, source or batch file is rewritten
        # The day after: the withdrawn batches are no longer read, and nothing more is withdrawn.
        again = stock.run(now=NOW + dt.timedelta(days=1))
        self.assertEqual((again["status"], again["checked"], again["retired"]), ("current", 2, []))
        self.assertEqual(len(stock.retirements()), 2)

    def test_without_the_flag_a_stale_batch_is_reported_and_the_stock_is_left_as_it_is(self):
        stock = self.stock()
        stock.post("ig-yucatan", [FARE, ENTRY])
        stock.post("fb-yucatan", [ENTRY])
        stock.pages = {GUIDE: page(ENTRY)}
        result = stock.run(withdraw=False)
        self.assertEqual((result["status"], result["retired"], result["reported"]), ("stale", [], ["ig-yucatan-v1"]))
        self.assertEqual(stock.retirements(), [])

    def test_a_sentence_worded_again_with_the_same_numbers_keeps_its_batch(self):
        stock = self.stock()
        stock.post("ig-new-york", ["0 $ la patinoire de Bryant Park", "6,9 °C la maximale moyenne de décembre, 1,1 °C la nuit", "Le sapin s’illumine le 2 décembre 2026."],
                   url="https://voyagesansdetour.fr/etats-unis/new-york-noel/")
        stock.pages = {"https://voyagesansdetour.fr/etats-unis/new-york-noel/":
                       page("0 $ l’entrée de la patinoire de Bryant Park", "En moyenne 44,4 °F l’après-midi (6,9 °C) et 33,9 °F la nuit (1,1 °C).", "Allumage le mercredi 2 décembre 2026.")}
        result = stock.run()
        row = result["batches"][0]
        self.assertEqual((result["status"], row["status"], row["found"], row["quotes"], row["missing"]), ("current", "current", 0, 3, []))
        self.assertEqual(len(row["reworded"]), 3)
        self.assertEqual(stock.retirements(), [])

    def test_a_number_is_read_whole(self):
        gone = stale_lots.numbers_gone
        self.assertEqual(gone("30 dh le bus 19, toutes les 30 minutes", "30 000 visiteurs, 1,30 € le ticket, le bus 190 et 19,5 km"), ["30", "19"])
        self.assertEqual(gone("30 dh le bus 19", "le bus 19 coûte 30 dh"), [])
        self.assertEqual(gone("1 041,50 pesos le billet", "le billet coûte 1 041,50 pesos"), [])
        self.assertEqual(gone("1 041,50 pesos le billet", "le billet coûte 1 041 pesos ou 41,50 pesos"), ["1041,50"])
        self.assertEqual(gone("20 000 azulejos", "ses 20 000 azulejos"), [])
        self.assertEqual(gone("20 000 azulejos", "20 azulejos, puis 000"), ["20000"])
        self.assertEqual(gone("Placez Belém un autre jour.", "rien"), [])
        self.assertEqual(gone("938 ฿ la couchette haute climatisée", "938 bahts la couchette haute climatisée de 2e classe"), [])
        # Two numbers side by side are thousands only inside one sentence of one element of the page.
        facts = "12 h 35 Bangkok → Chiang Mai, arrivée 7 h 15\n938 bahts la couchette haute (tarif de novembre 2026)\n500 bahts le Grand Palais de Bangkok"
        self.assertEqual(gone("938 ฿ la couchette haute", facts), [])
        self.assertEqual(gone("500 ฿ le Grand Palais de Bangkok", facts.replace("\n", " ")), [])

    def test_a_number_found_elsewhere_on_the_page_does_not_keep_a_figure_that_changed(self):
        gone = stale_lots.numbers_gone
        far = " Un long paragraphe sur les souks, les riads et les terrasses de la médina. " * 12
        # The bus fare changed; "30" is still on the page, far away, in a sentence about something else.
        page = "4 dh le bus L19 de l’aéroport à Jemaa el-Fna." + far + "Le car part toutes les 30 minutes pour Essaouira."
        self.assertEqual(gone("30 dh le bus 19 de l’aéroport à Jemaa el-Fna", page), ["30"])
        # The same numbers in a passage about something else: the guide no longer says what the post says.
        fixed = "Le trajet de l’aéroport au centre était fixé à 70 dh ; un chauffeur en a réclamé 400, et 46 chauffeurs ont perdu leur licence."
        self.assertEqual(gone("70 dh le prix attendu d’un petit taxi de l’aéroport à la médina ; une course à 400 dh a coûté leur licence à 46 chauffeurs", fixed), ["70", "400", "46"])
        # Worded again in the same passage, even in another order: the figure is still given.
        tree = "Le sapin du Rockefeller Center, un épicéa de 23 m, est arrivé le 7 novembre et s’illumine le mercredi 2 décembre 2026."
        self.assertEqual(gone("2 déc. 2026 l’allumage du sapin du Rockefeller Center, arrivé le 7 novembre", tree + far), [])
        self.assertEqual(gone("6,9 °C la maximale moyenne de décembre à Central Park, 1,1 °C la nuit",
                              far + "Central Park affiche en moyenne 44,4 °F l’après-midi (6,9 °C) et 33,9 °F la nuit (1,1 °C)."), [])

    def test_a_batch_that_may_already_be_in_buffer_is_reported_not_withdrawn(self):
        stock = self.stock()
        stock.post("ig-yucatan", [FARE, ENTRY], due=NOW + dt.timedelta(hours=80), copies=("", "-tiktok"))
        stock.post("ig-late", [FARE, ENTRY], due=NOW + dt.timedelta(hours=85))
        stock.post("fb-a", [ENTRY]); stock.post("fb-b", [ENTRY]); stock.post("fb-c", [ENTRY]); stock.post("fb-d", [ENTRY])
        stock.pages = {GUIDE: page(ENTRY)}
        result = stock.run()
        self.assertEqual((result["retired"], result["reported"]), (["ig-late-v1"], ["ig-yucatan-v1", "ig-yucatan-tiktok-v1"]))
        self.assertEqual({row["why"] for row in result["batches"] if row["action"] == "report"}, {"may_already_be_in_buffer"})
        self.assertEqual([entry["batchId"] for entry in stock.retirements()], ["ig-late-v1"])

    def test_a_reel_and_its_copy_are_one_post_decided_by_the_slot_that_comes_first(self):
        # The reel is due in 83 h 30 and its copy in 84 h 30: withdrawing the copy alone would leave the reel in the
        # queue with its slot taken, and nothing made again.
        stock = self.stock()
        stock.post("ig-yucatan", [FARE, ENTRY], due=NOW + dt.timedelta(hours=83, minutes=30), copies=("", "-tiktok"))
        stock.post("ig-next", [FARE, ENTRY], due=NOW + dt.timedelta(hours=84, minutes=30), copies=("", "-tiktok"))
        for name in ("fb-a", "fb-b", "fb-c", "fb-d", "fb-e"):
            stock.post(name, [ENTRY])
        stock.pages = {GUIDE: page(ENTRY)}
        result = stock.run()
        self.assertEqual(result["reported"], ["ig-yucatan-v1", "ig-yucatan-tiktok-v1"])
        self.assertEqual(result["retired"], ["ig-next-v1", "ig-next-tiktok-v1"])

    def test_an_ordinal_an_order_number_or_a_date_written_otherwise_is_reported_not_withdrawn(self):
        gone, wording = stale_lots.numbers_gone, stale_lots.only_wording
        # An ordinal is not a figure: "2e classe" may become "seconde classe", "1er dimanche" "premier dimanche".
        self.assertEqual(gone("938 bahts la couchette haute de 2e classe du train 9", "938 bahts la couchette haute de seconde classe du train 9"), [])
        self.assertEqual(gone("gratuit le 1er dimanche du mois", "gratuit le premier dimanche du mois"), [])
        # A number under ten without a unit, or a piece of a date: lost, but only wording.
        for quote, today in (("dès 100 dh chez Supratours, 7 départs par jour", "dès 100 dh chez Supratours, sept départs par jour"),
                             ("les prix relevés le 12/11/2026 au guichet", "les prix relevés le 12 novembre 2026 au guichet"),
                             ("le sapin s’illumine le 2 décembre 2026", "le sapin s’illumine début décembre")):
            lost = gone(quote, today)
            self.assertTrue(lost and wording(lost, quote), (quote, lost))
        # A price, a duration, a distance or a larger number is a figure, whatever its size and however its unit is written.
        for quote, today in (("2 € la traversée du Tage en ferry", "3 € la traversée du Tage en ferry"), ("3 h de car pour Essaouira", "trois heures de car pour Essaouira"),
                             ("le bus 19 de l’aéroport", "le bus L99 de l’aéroport"), ("0 $ la patinoire de Bryant Park", "la patinoire de Bryant Park est payante"),
                             ("3 heures de train depuis Séville", "4 heures de train depuis Séville"), ("5 minutes à pied de la gare", "8 minutes à pied de la gare"),
                             ("7 kilomètres de sentier côtier", "9 kilomètres de sentier côtier"), ("2 semaines suffisent pour la boucle", "trois semaines suffisent pour la boucle"),
                             ("la chambre pour 3 personnes", "la chambre pour 4 personnes"), ("le billet à € 5 en ligne", "le billet à € 6 en ligne"),
                             ("4 trains directs seulement", "6 trains directs seulement")):
            lost = gone(quote, today)
            self.assertTrue(lost and not wording(lost, quote), (quote, lost))
        stock = self.stock()
        stock.post("ig-marrakech", ["3 h de car pour Essaouira : dès 100 dh chez Supratours (7 départs par jour)", ENTRY])
        for name in ("fb-a", "fb-b"):
            stock.post(name, [ENTRY])
        stock.pages = {GUIDE: page("3 h de car pour Essaouira : dès 100 dh chez Supratours (sept départs par jour)", ENTRY)}
        result = stock.run()
        self.assertEqual((result["retired"], result["reported"]), ([], ["ig-marrakech-v1"]))
        self.assertEqual(result["batches"][0]["why"], "only_an_order_number_or_a_date_changed")
        self.assertEqual(stock.retirements(), [])

    def test_two_cells_of_a_table_joined_in_one_quote_are_not_a_number_in_the_thousands(self):
        gone = stale_lots.numbers_gone
        cells = "<table><tr><td>Ligne 15 (express)</td><td>200 ¥</td></tr></table>"
        # A row worded again whose two cells are still side by side: perhaps the same numbers, perhaps a price in the
        # thousands that changed. The batch is not withdrawn, and it is not passed in silence either.
        lost = gone("Ligne 15 200 ¥", stale_lots.a.page_text(cells))
        self.assertEqual((lost, stale_lots.only_wording(lost, "Ligne 15 200 ¥")), (["15|200"], True))
        self.assertEqual(gone("Ligne 15 200 ¥", stale_lots.a.page_text(cells.replace("200 ¥", "230 ¥"))), ["15200"])
        self.assertEqual(gone("15 200 ¥ le billet", "le billet coûte 15 200 ¥"), [])      # a real number in the thousands
        # A real number in the thousands that changed is not read in pieces: "1" and "500" are on the page, not side by side in a table.
        self.assertEqual(gone("1 500 € la semaine en chambre double", "500 € la semaine en chambre double, pour 1 nuit offerte"), ["1500"])

    def test_two_numbers_that_punctuation_parts_are_not_a_number_in_the_thousands(self):
        gone = stale_lots.numbers_gone
        # Worded again with the same numbers: nothing is lost, whatever stands between the two numbers in the quote.
        for quote, today in (("768 / 838 ฿ la couchette du train N° 13", "N° 13 : 768 ou 838 bahts la couchette du train"),
                             ("arrivée 13 h 16. 265 pesos les ruines de Tulum", "265 pesos les ruines de Tulum ; arrivée à 13 h 16"),
                             ("300 ¥ (500 ¥ avec le musée) l’entrée du temple", "l’entrée du temple : 300 ¥, ou 500 ¥ avec le musée"),
                             ("3 × 100 dh le trajet en taxi", "trois fois 100 dh le trajet en taxi, soit 3 billets"),
                             ("150–300 bahts la course en tuk-tuk", "de 150 à 300 bahts la course en tuk-tuk"),
                             ("N° 9 : 938 ฿ la couchette", "938 bahts la couchette du train N° 9"), ("18 h 40 · 938 ฿ le départ du train", "le départ du train à 18 h 40, 938 bahts"),
                             ("le bus 19 (100 dh) depuis l’aéroport", "le bus 19 depuis l’aéroport coûte 100 dh"), ("100/200 dh le hammam", "le hammam : 100 ou 200 dh")):
            self.assertEqual(gone(quote, today), [], quote)
        self.assertEqual(sorted(stale_lots.readings("768 / 838 ฿, bus 19 (100 dh), 13 h 16. 265 pesos")[0]), ["100", "13", "16", "19", "265", "768", "838"])

    def test_a_price_in_the_thousands_that_changed_is_never_read_as_two_cells(self):
        gone = stale_lots.numbers_gone
        # "1" and "500" follow each other elsewhere on the page, in two neighbouring elements: the figure still changed.
        self.assertEqual(gone("1 500 bahts la nuit en bungalow", "1 800 bahts la nuit en bungalow\n1\n500 m de plage"), ["1500"])
        self.assertEqual(gone("2 500 dh la nuit en riad", "3 000 dh la nuit en riad, à 2\n500 m de la place"), ["2500"])
        self.assertEqual(gone("la nuit à 1 500 bahts en bungalow", "la nuit à 1 800 bahts en bungalow"), ["1500"])
        # Independent review of 12/11/2026: a word before the number does not make a row, and "1", "500" anywhere near
        # do not make two cells.
        self.assertEqual(gone("Chambre à 1 500 € la nuit", "Chambre à 1 800 € la nuit, 1 lit, à 500 m de la plage"), ["1500"])
        self.assertEqual(gone("Entrée 2 500 ¥", "Entrée 3 500 ¥ pour 2 adultes, à 500 m de la gare"), ["2500"])
        # Even where the page puts "2" and "500" in two neighbouring cells, the batch is reported.
        self.assertEqual(gone("Entrée 2 500 ¥", "Entrée 3 500 ¥ pour 2\n500 m plus loin"), ["2|500"])
        self.assertEqual(stale_lots.readings("1 500 bahts la nuit")[1], {})                       # the figure that opens a quote is one number
        self.assertEqual(stale_lots.readings("Chambre à 1 500 € la nuit")[1], {})                 # words after the number: not a row
        self.assertEqual(stale_lots.readings("Ligne 15 200 ¥")[1], {"15200": ("15", "200")})     # a row: a label, then its cell and its unit

    def test_an_ordinal_that_changed_is_reported_and_one_written_in_full_is_not(self):
        gone, wording = stale_lots.numbers_gone, stale_lots.only_wording
        for quote, today, lost in (("gratuit le 1er dimanche du mois", "gratuit le 2e dimanche du mois", ["1er"]), ("ouvert dès le 1er décembre", "ouvert dès le 3 décembre", ["1er"]),
                                   ("la couchette de 2e classe du train 9", "la couchette de 1re classe du train 9", ["2e"]),
                                   ("le tram 15E dessert Belém", "le tram 18E dessert Belém", ["15e"]), ("le 100e anniversaire du parc", "le 110e anniversaire du parc", ["100e"])):
            self.assertEqual(gone(quote, today), lost, quote)
            self.assertTrue(wording(lost, quote), quote)      # reported, never withdrawn on an ordinal alone
        # "secondes" is a unit of time, not the rank of a class.
        self.assertEqual(gone("2e classe sans réservation", "sans réservation, attendre 5 secondes au portillon"), ["2e"])
        for quote, today in (("gratuit le 1er dimanche du mois", "gratuit le premier dimanche du mois"), ("la couchette de 2e classe du train 9", "la couchette de seconde classe du train 9"),
                             ("la 3e station après la gare", "la troisième station après la gare"), ("le tram 15E dessert Belém", "Belém est desservi par le tram 15E")):
            self.assertEqual(gone(quote, today), [], quote)
        stock = self.stock()
        stock.post("fb-lisbonne", ["Le tram 15E dessert Belém et le monastère.", ENTRY])
        for name in ("fb-a", "fb-b"):
            stock.post(name, [ENTRY])
        stock.pages = {GUIDE: page("Le tram 18E dessert Belém et le monastère.", ENTRY)}
        result = stock.run()
        self.assertEqual((result["status"], result["retired"], result["reported"]), ("stale", [], ["fb-lisbonne-v1"]))
        self.assertEqual((result["batches"][0]["why"], result["batches"][0]["missing"][0]["numbers"]), ("only_an_order_number_or_a_date_changed", ["15e"]))

    def test_a_lost_number_is_wording_only_if_every_place_it_stands_in_is(self):
        gone, wording = stale_lots.numbers_gone, stale_lots.only_wording
        quote = "2 € la traversée, 2 départs par heure"
        lost = gone(quote, "3 € la traversée, 4 départs par heure")
        self.assertEqual((lost, wording(lost, quote)), (["2"], False))       # the same "2" is also a price
        # A number the quote gives twice must be read twice: one of the two changed, the other does not hide it.
        lost = gone(quote, "2 € la traversée, 4 départs par heure")
        self.assertEqual((lost, wording(lost, quote)), (["2"], False))
        self.assertEqual(gone(quote, "2 départs par heure, 2 € la traversée"), [])
        for quote, today in (("5 kg de bagage en cabine", "8 kg de bagage en cabine"), ("le trajet coûte 9 EUR", "le trajet coûte 12 EUR"), ("5 MAD le thé", "8 MAD le thé"),
                             ("8 THB le ferry", "9 THB le ferry"), ("7 USD la navette", "9 USD la navette"), ("5 mn de marche", "8 mn de marche"), ("3 k€ le séjour", "4 k€ le séjour")):
            lost = gone(quote, today)
            self.assertTrue(lost and not wording(lost, quote), quote)

    def test_a_quote_found_inside_a_longer_number_is_not_found(self):
        # Verification of 12/11/2026: the quote was looked for as a plain piece of text, and "5 € l'entrée" was "found
        # word for word" in "15 € l'entrée": the batch stayed current, without even a line in the summary.
        cases = (("0 $ la patinoire de Bryant Park", "10 $ la patinoire de Bryant Park"),
                 ("5 € l’entrée du monastère des Hiéronymites", "15 € l’entrée du monastère des Hiéronymites"),
                 ("500 bahts l’entrée du Grand Palais", "1 500 bahts l’entrée du Grand Palais"),
                 ("370 € la semaine de logement", "1 370 € la semaine de logement"),
                 ("5 € le ticket du funiculaire", "7,5 € le ticket du funiculaire"),
                 ("30 min de marche jusqu’au belvédère", "1 h 30 min de marche jusqu’au belvédère"),
                 ("50 pesos le colectivo pour Tulum", "150 pesos le colectivo pour Tulum"),
                 ("depuis l’aéroport par le bus 19", "depuis l’aéroport par le bus 190"),
                 ("le billet du matin coûte dès 9", "le billet du matin coûte dès 9,50 €"),
                 ("pour une nuit en bungalow comptez 1", "pour une nuit en bungalow comptez 1 500 bahts"))
        for quote, today in cases:
            stock = self.stock()
            stock.post("ig-cas", [OPENING, quote], copies=("", "-tiktok"))
            stock.post("fb-temoin", [ENTRY])
            stock.post("fb-autre", [OPENING])
            stock.pages = {GUIDE: page(OPENING, ENTRY, today)}
            result = stock.run()
            said = result["retired"] + result["reported"]
            self.assertEqual((result["status"], sorted(said)), ("stale", ["ig-cas-tiktok-v1", "ig-cas-v1"]), quote)
            self.assertFalse(stale_lots.quoted(quote, today)[0], quote)
        # A quote that ends on the number of a line, or on the unit of a duration, and that the page goes on with.
        for quote, today in (("Prenez le tram 28", "Prenez le tram 28E"), ("depuis la gare par le bus 19", "depuis la gare par le bus 19A"),
                             ("30 min de marche", "2 heures 30 min de marche"), ("30 min de marche", "1 heure et 30 min de marche"),
                             ("le trajet dure 2 h", "le trajet dure 2 h 30"), ("départ à 7 h", "départ à 7 h 15"), ("comptez 20 min", "comptez 20 min 30")):
            self.assertFalse(stale_lots.quoted(quote, today)[0], quote)
            stale = stale_lots.reread([(GUIDE, quote)], {GUIDE: today})
            self.assertEqual((stale["status"], all(entry["wording"] for entry in stale["missing"])), ("stale", True), quote)   # reported
        self.assertEqual(stale_lots.reread([(GUIDE, "Prenez le tram 28")], {GUIDE: "Prenez le tram 28E"})["missing"][0]["numbers"], ["28e"])
        self.assertEqual(stale_lots.quoted("le trajet dure 2 h", "Ici le trajet dure 2 h. 15 € le billet."), (True, None))
        # A price that changed is withdrawn; a quote that only became longer is reported with what the page says.
        self.assertEqual(stale_lots.reread([(GUIDE, cases[1][0])], {GUIDE: cases[1][1]})["missing"][0], {"quote": cases[1][0], "numbers": ["5"], "wording": False})
        longer = stale_lots.reread([(GUIDE, cases[5][0])], {GUIDE: cases[5][1]})["missing"][0]
        self.assertEqual((longer["numbers"], longer["wording"]), (["→ 1 h 30 min de marche jusqu’au belvédère"], True))
        # The same words with whole numbers are found: after a year, after another element, before a full stop.
        for quote, today in (("500 bahts l’entrée du Grand Palais", "Tarif de novembre 2026 : 500 bahts l’entrée du Grand Palais."),
                             ("200 ¥ le trajet", "Ligne 15\n200 ¥ le trajet"), ("le bus 19", "Prenez le bus 19. 30 minutes plus tard, la médina."),
                             ("30 min de marche", "Comptez 30 min de marche."), ("938 bahts la couchette", "N° 9, 18 h 40\n938 bahts la couchette")):
            self.assertEqual(stale_lots.quoted(quote, today), (True, None), quote)

    def test_a_figure_put_right_everywhere_is_not_read_in_another_fact_a_few_elements_away(self):
        gone = stale_lots.numbers_gone
        # The entrance of the palaces went from 100 to 120 dh; the taxi fare "100 à 160 dh" stands three tiles below.
        palaces = "l’entrée de la Bahia, des tombeaux saadiens ou d’El Badi pour un adulte étranger"
        marrakech = "\n".join(["120 dh", palaces + ", de 9 h à 17 h", "170 dh", "le jardin Majorelle en plein tarif", "100 à 160 dh",
                               "le prix d’un petit taxi de l’aéroport à la médina"])
        self.assertEqual(gone("100 dh " + palaces, marrakech), ["100"])
        # Santa Claus went from free to 25 €; a photo credit seven lines above says "CC BY-SA 2 0".
        lapland = "\n".join(["Photo : Visit Rovaniemi, CC BY-SA 2 0"] + [f"Ligne {n} du guide, sans rapport" for n in "abcdef"] + ["25 €", "rencontrer le Père Noël au village"])
        self.assertEqual(gone("0 € rencontrer le Père Noël au village", lapland), ["0"])
        # Winter Wonderland went from 1 £ to 5 £; "zones 1-2" stands in the transport tile, further down.
        london = "\n".join(["5 £", "l’entrée de Winter Wonderland en semaine", "8,90 £", "le plafond quotidien", "Transports", "le plafond des zones 1-2 du métro"])
        self.assertEqual(gone("1 £ l’entrée de Winter Wonderland en semaine", london), ["1"])
        # Rain in February went from 4 to 14 mm in the three lines that give it.
        vietnam = "\n".join(["Février", "14 mm de pluie à Hô-Chi-Minh-Ville", "Mars", "9 mm de pluie à Hô-Chi-Minh-Ville"])
        stale = stale_lots.reread([(GUIDE, "4 mm de pluie à Hô-Chi-Minh-Ville")], {GUIDE: vietnam})
        self.assertEqual((stale["status"], stale["missing"][0]["numbers"]), ("stale", ["4"]))
        # Worded again in the same element or the next one, the figure is still read.
        self.assertEqual(gone("100 dh " + palaces, "\n".join(["Les palais", "L’entrée coûte 100 dh pour un adulte étranger : Bahia, tombeaux saadiens, El Badi."])), [])
        self.assertEqual(gone("100 dh " + palaces, "\n".join(["100 dh", "pour un adulte étranger, l’entrée de la Bahia, des tombeaux saadiens ou d’El Badi"])), [])
        # The limit that is left, written in the code: the old number given for something else in the very same paragraph.
        self.assertEqual(gone("1 £ l’entrée de Winter Wonderland en semaine", "Winter Wonderland : une entrée à 5 £ en semaine, dans les zones 1-2 du métro."), [])

    def test_the_same_figure_written_otherwise_withdraws_nothing(self):
        gone, wording = stale_lots.numbers_gone, stale_lots.only_wording
        # The line is now written with its letter: reported, to be read by eye, never withdrawn alone.
        quote = "le tram 28 traverse l’Alfama et Graça"
        lost = gone(quote, "Le tram 28E traverse l’Alfama puis Graça.")
        self.assertEqual((lost, wording(lost, quote)), (["28e"], True))
        # …but a price is not a line: "2 €" is not read in "2e classe".
        quote = "2 € le ticket acheté à bord"
        lost = gone(quote, "3 € le ticket acheté à bord, en 2e classe")
        self.assertEqual((lost, wording(lost, quote)), (["2"], False))
        # A decimal point is a decimal comma.
        self.assertEqual(gone("2,10 € le ticket Carris acheté à bord", "2.10 € le ticket Carris, acheté à bord"), [])
        self.assertEqual(gone("2,10 € le ticket Carris acheté à bord", "2.40 € le ticket Carris, acheté à bord"), ["2,10"])
        self.assertEqual(gone("1 500 bahts la nuit en bungalow", "la nuit en bungalow : 1.500 bahts"), ["1500"])   # a point for the thousands is not read
        # A year is not the head of a number in the millions: the price that follows it is read alone.
        self.assertEqual(gone("500 bahts l’entrée du Grand Palais de Bangkok", "Tarif de novembre 2026 500 bahts pour entrer au Grand Palais de Bangkok"), [])
        self.assertEqual(stale_lots.plain("En 2026 500 bahts, 12 500 000 dongs et 1 041,50 pesos"), "en 2026 500 bahts, 12500000 dongs et 1041,50 pesos")

    def test_a_post_is_never_half_withdrawn_and_a_missing_file_is_counted(self):
        stock = self.stock()
        stock.post("ig-yucatan", [FARE, ENTRY], copies=("", "-tiktok"))
        stock.post("fb-yucatan", [ENTRY])
        stock.post("fb-kyoto", [OPENING])
        stock.post("fb-nara", [OPENING])
        stock.pages = {GUIDE: page(OPENING, ENTRY)}
        # The file of the reel is broken: its copy is stale, and would have gone out of the stock alone.
        (stock.root / "reviewed-social" / "ig-yucatan-v1.json").write_text("{")
        result = stock.run()
        self.assertEqual((result["retired"], result["reported"], result["unread"]), ([], ["ig-yucatan-tiktok-v1"], ["ig-yucatan-v1"]))
        self.assertEqual(next(row["why"] for row in result["batches"] if row["batchId"] == "ig-yucatan-tiktok-v1"), "another_batch_of_the_post_is_unread")
        self.assertEqual(stock.retirements(), [])
        # A batch of the index whose file is gone is counted among the unread, not passed over.
        (stock.root / "reviewed-social" / "fb-kyoto-v1.json").unlink()
        result = stock.run()
        self.assertEqual((result["checked"], sorted(result["unread"])), (3, ["fb-kyoto-v1", "ig-yucatan-v1"]))
        self.assertEqual(next(row["why"] for row in result["batches"] if row["batchId"] == "fb-kyoto-v1"), "no_batch_file")

    def test_nothing_is_written_through_an_index_that_is_a_link(self):
        stock = self.stock()
        stock.post("ig-yucatan", [FARE, ENTRY])
        stock.post("fb-yucatan", [ENTRY])
        stock.post("fb-kyoto", [OPENING])
        stock.pages = {GUIDE: page(OPENING, ENTRY)}
        index = stock.root / "reviewed-social" / "index.json"
        outside = stock.root.parent / "outside-index.json"
        outside.write_text(index.read_text())
        self.addCleanup(outside.unlink)
        index.unlink()
        index.symlink_to(outside)
        before = outside.read_bytes()
        result = stock.run()
        # Nothing is withdrawn; the stale batch is still told, as it is without the flag.
        self.assertEqual((result["status"], result["retired"], result["reported"]), ("stale", [], ["ig-yucatan-v1"]))
        self.assertEqual(outside.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "is a link"):
            stale_lots.retire(stock.root, result["batches"], NOW)
        self.assertEqual(outside.read_bytes(), before)

    def test_figures_taken_from_another_site_are_listed_with_the_day_they_were_read(self):
        stock = self.stock()
        stock.post("ig-train", [ENTRY], other=["dès 10,50 € le billet promotionnel", "Une phrase sans chiffre."])
        registry = stock.root / "auto" / "ig-train" / "sources.json"
        sources = json.loads(registry.read_text())
        sources["sources"]["rail"]["retrievedAt"] = "2026-10-24T08:00:00Z"
        registry.write_text(json.dumps(sources))
        stock.post("fb-guide", [ENTRY])
        stock.pages = {GUIDE: page(ENTRY)}
        result = stock.run()
        self.assertEqual((result["status"], result["external"], result["retired"], result["reported"]), ("current", ["ig-train-v1"], [], []))
        self.assertEqual(result["batches"][0]["external"], [{"url": "https://www.example.org/fares", "retrievedAt": "2026-10-24T08:00:00Z", "quotes": 1}])
        self.assertNotIn("external", result["batches"][1])

    def test_nothing_read_in_a_file_is_opened_as_a_path(self):
        stock = self.stock()
        stock.post("ig-yucatan", [ENTRY])
        secret = stock.root.parent / "outside.json"
        stock.index["items"].append({"path": "x", "fileSha256": "f" * 64, "batchId": "../outside", "batchSha256": "b" * 64, "itemIds": ["x"]})
        stock.save()
        stock.post("ig-escape", [FARE])
        scenario = stock.root / "scenarios" / "ig-escape.json"
        scenario.write_text(json.dumps({**json.loads(scenario.read_text()), "sources": {"file": "../../../etc/hosts"}}))
        stock.pages = {GUIDE: page(ENTRY)}
        result = stock.run()
        self.assertEqual([(row["batchId"], row["status"], row.get("why")) for row in result["batches"]],
                         [("ig-yucatan-v1", "current", None), ("../outside", "unread", "unreadable_batch"), ("ig-escape-v1", "unread", "unreadable_batch")])
        self.assertFalse(secret.exists())
        scenarios = stale_lots.shelf(stock.root, "scenarios")
        self.assertEqual(sorted(scenarios), ["ig-escape", "ig-yucatan"])
        for name in ("../../x", "a/b", "A", "x.json", "", None):
            with self.assertRaises(ValueError):
                stale_lots.stored(scenarios, name)
        self.assertIsNone(stale_lots.stored(scenarios, "ig-absent"))
        # A registry is looked up among the files of the production folder, never opened from what a scenario says.
        self.assertEqual(sorted(stale_lots.registries(stock.root)), ["auto/ig-escape/sources.json", "auto/ig-yucatan/sources.json"])
        with self.assertRaises(KeyError):
            stale_lots.quotes_of({"sources": {"file": "/etc/hosts"}, "scenes": []}, stale_lots.registries(stock.root))
        # A link is not a file of the folder, wherever it leads.
        outside = stock.root.parent / "outside-scenario.json"
        outside.write_text("{}")
        self.addCleanup(outside.unlink)
        (stock.root / "scenarios" / "ig-link.json").symlink_to(outside)
        (stock.root / "auto" / "ig-link").mkdir()
        (stock.root / "auto" / "ig-link" / "sources.json").symlink_to(outside)
        self.assertNotIn("ig-link", stale_lots.shelf(stock.root, "scenarios"))
        self.assertNotIn("auto/ig-link/sources.json", stale_lots.registries(stock.root))

    def test_a_scenario_oddly_made_never_keeps_the_others_from_being_read(self):
        stock = self.stock()
        stock.post("ig-yucatan", [ENTRY])
        for name, scenario in (("ig-list", ["not", "a", "scenario"]), ("ig-scenes", {"sources": {"file": "auto/ig-scenes/sources.json"}, "scenes": [None, "x"]}),
                               ("ig-sources", {"sources": "auto/ig-sources/sources.json", "scenes": []})):
            stock.post(name, [FARE])
            (stock.root / "scenarios" / f"{name}.json").write_text(json.dumps(scenario))
        stock.pages = {GUIDE: page(ENTRY)}
        result = stock.run()
        self.assertEqual([(row["batchId"], row["status"]) for row in result["batches"]],
                         [("ig-yucatan-v1", "current"), ("ig-list-v1", "unread"), ("ig-scenes-v1", "unread"), ("ig-sources-v1", "unread")])
        self.assertEqual(result["retired"], [])

    def test_a_page_that_cannot_be_read_or_that_changed_altogether_withdraws_nothing(self):
        stock = self.stock()
        stock.post("ig-yucatan", [FARE, ENTRY])
        stock.post("fb-yucatan", [ENTRY])
        self.assertEqual((stock.run()["unread"], stock.retirements()), (["ig-yucatan-v1", "fb-yucatan-v1"], []))  # the site is down
        stock.post("ig-kyoto", ["500 ¥ l’entrée du temple"], url="https://voyagesansdetour.fr/japon/kyoto/")
        stock.post("fb-kyoto", ["500 ¥ l’entrée du temple"], url="https://voyagesansdetour.fr/japon/kyoto/")
        stock.pages = {GUIDE: page("Une page d’erreur, ou un guide récrit de bout en bout : 12 conseils."), "https://voyagesansdetour.fr/japon/kyoto/": page("500 ¥ l’entrée du temple")}
        result = stock.run()
        self.assertEqual((result["retired"], result["reported"]), ([], ["ig-yucatan-v1", "fb-yucatan-v1"]))
        self.assertEqual({row.get("why") for row in result["batches"] if row["action"] == "report"}, {"no_quote_left_on_the_page"})
        self.assertEqual(stock.retirements(), [])

    def test_more_than_half_of_the_stock_stale_is_a_change_of_the_site_and_withdraws_nothing(self):
        stock = self.stock()
        for name in ("ig-a", "ig-b", "fb-c"):
            stock.post(name, [FARE, ENTRY])
        stock.post("fb-d", [ENTRY])
        stock.pages = {GUIDE: page(ENTRY)}
        result = stock.run()
        self.assertEqual((result["retired"], len(result["reported"])), ([], 3))
        self.assertEqual({row.get("why") for row in result["batches"] if row["action"] == "report"}, {"more_than_half_of_the_batches_are_stale"})

    def test_only_quotes_of_the_site_and_batches_still_to_come_are_read(self):
        stock = self.stock()
        stock.post("ig-yucatan", [ENTRY], other=["12 € le billet relevé chez le transporteur"])   # another site: not this guard's business
        stock.post("ig-past", [FARE], due=NOW - dt.timedelta(hours=1))                             # already out
        stock.post("ig-orphan", [FARE])
        (stock.root / "scenarios" / "ig-orphan.json").unlink()                                     # an older batch without a scenario
        stock.post("ig-broken", [FARE])
        (stock.root / "auto" / "ig-broken" / "sources.json").unlink()                              # its source registry is gone
        stock.post("ig-empty", [FARE])
        (stock.root / "reviewed-social" / "ig-empty-v1.json").write_text('{"items": []}')          # an oddly made batch
        stock.pages = {GUIDE: page(ENTRY)}
        result = stock.run()
        self.assertEqual([(row["batchId"], row["status"], row.get("why")) for row in result["batches"]],
                         [("ig-yucatan-v1", "current", None), ("ig-orphan-v1", "unread", "no_scenario"),
                          ("ig-broken-v1", "unread", "unreadable_batch"), ("ig-empty-v1", "unread", "unreadable_batch")])
        self.assertEqual(result["unread"], ["ig-orphan-v1", "ig-broken-v1", "ig-empty-v1"])
        self.assertEqual((result["batches"][0]["quotes"], result["retired"]), (1, []))
        self.assertEqual(stale_lots.scenario_id("ig-kyoto-2026-11-20-2-tiktok-v1"), "ig-kyoto-2026-11-20-2")
        self.assertEqual(stale_lots.scenario_id("fb-kyoto-2026-11-20-v1"), "fb-kyoto-2026-11-20")


if __name__ == "__main__":
    unittest.main()
