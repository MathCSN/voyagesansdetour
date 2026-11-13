"""Which precise places a text names, and whether a photo is a photo of them.

A figure goes over a photo of the place it names, never over another one. On 13/11/2026 two photo posts went out of
the generator with "la réouverture des îles Similan" over Ko Phi Phi (the two only shared the word "îles") and "le
pavillon d'Or du Kinkaku-ji" over the sign of Shin-Fuji station. This module says what a precise place is (a proper
noun: Similan, Kinkaku-ji, Uxmal, Campanhã), which words never tie a figure to a photo (kinds of places: île, plage,
temple, gare, train…), and what a journey is ("Tokyo → Kyoto en Nozomi" goes over a train first).

Used by reel_formats.py (to choose the photo) and by production.py (to refuse a scenario that got it wrong).
"""
from __future__ import annotations

import re

import destinations

# Kinds of places, of things and of sizes: shared alone, such a word names nothing ("les îles Similan" and "les îles
# Phi Phi"), and written with a capital it is still no proper noun ("le Grand Palais", "Wat Arun" and "Wat Pho").
GENERIC = frozenset("""
    ile iles archipel baie baies lac lacs mont monts montagne montagnes vue vues mer cote cotes plage plages temple temples
    gare gares train trains pont ponts marche marches riviere fleuve cascade cascades colline collines foret grotte grottes
    volcan canal rue rues route quai quais station port ports tour tours villa villas ville villes village villages medina
    place places palais jardin jardins musee musees eglise eglises cathedrale chateau parc parcs quartier quartiers centre
    monument monuments pagode sanctuaire statue porte pavillon bouddha cite vallee desert
    koh wat doi dera saint sainte san santa sao grand grande grands petit petite vieux vieille nouveau nouvelle
    chiang khao los las isla islas playa playas puerto costa vila monte cabo punta rio
    nord sud est ouest haut haute bas basse jour jours pass
    janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre
    lundi mardi mercredi jeudi vendredi samedi dimanche noel paques
    park center centre square street bridge tower beach island islands lake mount river market museum garden gardens
    palace church house hall city bay view station railway castle cathedral temple old town
    ponte praia praca rua igreja torre castelo palacio estacao mosteiro cais largo miradouro jardim catedral plaza puente""".split())
# What a journey is made by, as a fact says it; and what a photo of it shows.
WAYS = {"rail": frozenset("train trains shinkansen tgv couchette couchettes rame railway sleeper locomotive wagon".split()),
        "urban": frozenset("metro tram tramway".split()), "road": frozenset(["bus"]),
        "water": frozenset("ferry ferries bateau bateaux".split())}
RIDES = frozenset().union(*WAYS.values())   # never a station alone: it is a place
TRANSPORT = RIDES | frozenset("billet billets".split())
# "chez Supratours", "ligne Yamanote". Not "en" ("en Alentejo") nor "train" or "bus" ("le train Rossio–Sintra"): a
# carrier read as a place leaves a plan out, a place read as a carrier would let its fact go over any photo.
CARRIED_BY = frozenset("chez ligne compagnie".split())
# Names written with a capital that are no places: tickets, cards, operators, trains, brands, peoples. Reviewed by
# hand, like GENERIC: "16,55 € l'Andante Tour 3" names no place, nor does "un casier City Lockers", "pour les Français"
# or "le Père Noël" (13/11/2026: three posts were refused, and a locker of Porto went over a tram of Lisbon).
NOT_PLACES = frozenset("""
    andante navegante viva viagem zapping carris metro cp alfa pendular alfapendular intercidades interregional regional promo urbano
    renfe ave avlo ouigo iryo trenitalia italo frecciarossa sita mepe interbus ado tren maya nozomi hikari kodama sakura
    turistica conforto classe azul phantip supratours ctm travelmar alilauro flixbus alsa rede expressos
    jr japan rail pass suica pasmo icoca oyster tfl contactless grab bolt uber city lockers locker bounce nannybag luggage
    pere noel claus santa inah unesco covid wifi
    francais francaise francaises europeen europeens europeenne portugais portugaise espagnol espagnole italien italienne
    japonais japonaise thailandais thailandaise vietnamien vietnamienne mexicain mexicaine marocain marocaine finlandais
    finlandaise britannique britanniques anglais anglaise americain americaine americains suisse suisses belge belges
    """.split())
# Two spellings or two names of one place, and a quarter inside its town: a record that says the first says the others.
# Reviewed by hand: "Kinkakuji" is the Kinkaku-ji, Saigon is Hô-Chi-Minh-Ville, Belém and Alfama are in Lisbon.
IMPLIES = {"kinkakuji": ("kinkaku",), "kinkaku": ("kinkakuji",), "saigon": ("ho", "chi", "minh"), "minh": ("saigon",),
           "sapa": ("sa", "pa"), "pa": ("sapa",), "danang": ("da", "nang"), "nang": ("danang",), "hanoi": ("ha", "noi"),
           "belem": ("lisbonne",), "alfama": ("lisbonne",), "shibuya": ("tokyo",)}
MONTHS = frozenset("janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre".split())
# Letters that no accent rule folds to ASCII: "Đà Lạt" was read "à Lạt".
PLAIN = str.maketrans({"Đ": "D", "đ": "d", "Ł": "L", "ł": "l", "Ø": "O", "ø": "o", "İ": "I", "ı": "i", "ß": "ss", "œ": "oe", "Œ": "Oe", "æ": "ae", "Æ": "Ae"})
SHORT = frozenset("el or st mt da do di al ii iii iv ji ko".split())   # two letters with a capital that name no place alone ("Sa Pa" does)
LEADING = frozenset("le la les un une des du de ce cette ces au aux".split())
WORD = re.compile(r"[^\W\d_][\w’'-]*")
# "Mérida–Tulum", "Tokyo → Kyoto", "Tokyo–Kyoto–Hiroshima–Tokyo": two names joined by an arrow or a dash are the two
# ends of a journey. Not two hours ("9 h 40 → 12 h 12"), nor a clause set off by a long dash.
LINKED = re.compile(r"([^\W\d_][\w’']{0,40})\s?[→–]\s?([^\W\d_])")
# What opens a fact about a journey: "de trajet en Alfa Pendular entre Santa Apolónia et Campanhã". A ticket alone
# does not ("le billet de la vieille ville de Hội An" went over a train): it opens a journey with its means of transport.
OPENERS = RIDES | frozenset("trajet trajets minibus navette".split())


class _Capitalised:
    """Words that begin with a capital, in any alphabet Python knows ("Đà", "Šibenik", "Ōsaka", "Łódź"); the capital
    may follow an elision ("d’Andaman" gives "Andaman", "L’Alhambra" is one word)."""

    @staticmethod
    def finditer(text: str):
        position = 0
        while position < len(text):
            if text[position].isupper():
                match = WORD.match(text, position)
                yield match
                position = match.end()
            else:
                position += 1

    @staticmethod
    def match(text: str):
        return WORD.match(text) if text[:1].isupper() else None

    @staticmethod
    def fullmatch(text: str):
        return WORD.fullmatch(text) if text[:1].isupper() else None


CAPITALISED = _Capitalised
# Words of four letters and more that two texts share without being about the same thing.
HOLLOW = frozenset("pour entre dans avec sans sous vers chez depuis selon plus moins tout tous toute toutes cette leur leurs dont comme "
                   "aussi tres deux trois quatre nuit nuits prix tarif euros pesos entree ouvert ouverte jours".split())
OPENING_WORDS = 5   # a fact is about a journey when it says so at once: "le train direct…", not "…, à 45 minutes par le train"


def folded(text: str) -> list[str]:
    """The words of a text, lower case and without accents, in their order."""
    return re.findall(r"[a-z0-9]+", destinations.ascii_fold(re.sub(r"[’'‘]", " ", text.translate(PLAIN))).lower())


def words(text: str) -> set[str]:
    return set(folded(text))


def spans(text: str, everywhere: frozenset | set = frozenset(), sentence: bool = False, known: frozenset | set = frozenset()) -> list[tuple[str, int, int]]:
    """The precise places a text names, in the order it names them: its words written with a capital, two letters
    and more, that are neither a kind of place, nor an article opening the sentence, nor the name of the destination
    of the whole post (`everywhere`: every photo of a guide of Thailand is "in Thailand"). An acronym ("SITA", "JR"),
    a ticket, a card, an operator, a train, a brand or a people (NOT_PLACES) and what follows "chez", "bus", "ligne"
    ("chez Supratours", "bus Phantip") are no places. A month is part of a name after another one ("Chiang Mai").
    `sentence`: the text is a caption; its first word has a capital by grammar ("Visiteurs dans un jardin zen."),
    unless a name follows it at once or `known` (the words of the photo's identifier and title) says it is the place
    ("Vernazza et son port", "L'Alhambra et la Sierra Nevada" for "grenade-alhambra")."""
    found, carrier, end = [], False, -1
    for match in CAPITALISED.finditer(text):
        first = sentence and not text[:match.start()].strip("«“\" ")
        adjacent = end >= 0 and text[end:match.start()] == " "
        end = match.end()
        if first and not CAPITALISED.match(text[match.end():].lstrip(" ")) and not set(folded(match[0])) & set(known):
            continue
        before = folded(text[:match.start()])[-1:]
        carrier = (carrier and adjacent) or bool(before and before[0] in CARRIED_BY and text[match.start() - 1:match.start()] == " ")
        if len(match[0]) > 1 and match[0].isupper():
            carrier = False   # the acronym is the carrier's whole name: "le bus MEPE Puerto Viejo – San José"
        elif not carrier:
            found += [(piece, match.start(), match.end()) for piece in folded(match[0]) if names_a_place(piece, everywhere, adjacent and not first)]
    return found


UNNAMED = GENERIC | LEADING | OPENERS | TRANSPORT | SHORT | NOT_PLACES


def names_a_place(piece: str, everywhere: frozenset | set, after_a_name: bool) -> bool:
    """One word of a capitalised name: two letters and more, no kind of place, no article, no means of transport, no
    name that is not a place, not the destination itself; a month only right after another capitalised word."""
    if len(piece) < 2 or piece in everywhere:
        return False
    return piece not in UNNAMED or (piece in MONTHS and after_a_name)


def named(text: str, everywhere: frozenset | set = frozenset(), sentence: bool = False, known: frozenset | set = frozenset()) -> list[str]:
    """The precise places a text names, in the order it names them (see `spans`)."""
    return list(dict.fromkeys(piece for piece, _, _ in spans(text, everywhere, sentence, known)))


SUBJECT_GAP = 4   # words at most between two places a fact is about: "Bahia, des tombeaux saadiens ou d'El Badi"


def subjects(text: str, everywhere: frozenset | set = frozenset(), sentence: bool = False, known: frozenset | set = frozenset()) -> list[str]:
    """The places a fact is about, among those it names: the first one, and those it lists with it ("Mérida et Uxmal",
    "de Surat Thani à Krabi", "Bangkok, Chiang Mai et la mer d'Andaman"). A place named further on, after a figure or
    a long stretch of words, only situates the fact: "le Grand Bouddha du Tōdai-ji, à Nara, à 45 minutes de Kyoto"
    is about the Tōdai-ji and Nara, not about Kyoto. A place one only comes from is no subject either: "depuis Kyoto
    pour voir le Grand Bouddha du Tōdai-ji, à Nara"."""
    about, end = [], None
    for piece, start, stop in spans(text, everywhere, sentence, known):
        gap = text[end:start] if end is not None and start >= end else ""
        if end is not None and (re.search(r"\d", gap) or len(folded(gap)) > SUBJECT_GAP):
            break
        if folded(text[:start])[-1:] in (["depuis"], ["from"]):
            continue
        about, end = about + [piece], stop
    return list(dict.fromkeys(about))


def first_name(text: str, everywhere: frozenset | set = frozenset()) -> list[str]:
    """The words of the first place a fact names: "le Real Alcázar de Séville" is first about the Real Alcázar, "un
    casier à Porto-Trindade" about Porto-Trindade, "de Surat Thani à Krabi" about Surat Thani."""
    name, end = [], None
    for piece, start, stop in spans(text, everywhere):
        if end is not None and start >= end and text[end:start] != " ":
            break
        name, end = name + [piece], stop
    return list(dict.fromkeys(name))


def proper(text: str, everywhere: frozenset | set = frozenset(), sentence: bool = False) -> set[str]:
    return set(named(text, everywhere, sentence))


def named_after(text: str, kind: str) -> set[str]:
    """The names a text gives to a kind of place: {"similan"} for "îles" in "la réouverture des îles Similan"; nothing
    for "pont" in "Le pont en métro"."""
    pieces, found = re.findall(r"[\w’'-]+", text), set()
    for index, piece in enumerate(pieces):
        if folded(piece)[-1:] == [kind]:
            after = [word for word in pieces[index + 1:index + 4] if folded(word) and folded(word)[0] not in LEADING and word not in ("d", "l")]
            if after and CAPITALISED.fullmatch(after[0]):
                found |= {part for part in folded(after[0]) if len(part) >= 3}
    return found - GENERIC


def linked(text: str) -> bool:
    """Two names joined by an arrow or a dash: "Tokyo → Kyoto", "Mérida–Tulum"; not "9 h 40 → 12 h 12"."""
    return any(match[1][0].isupper() and match[2].isupper() for match in LINKED.finditer(text))


def journey(text: str) -> bool:
    """A fact about a journey: an arrow or a dash between two names, or a means of transport in its first words."""
    return linked(text) or bool(OPENERS & set(folded(text)[:OPENING_WORDS]))


CARDINAL = frozenset("nord sud ouest".split())
EAST_AFTER = frozenset("cote rive versant facade".split())
NAMED_AFTER_CARDINAL = frozenset("ligne gare station autoroute route".split())


def region(text: str) -> set[str]:
    """The part of the destination a fact is about when it names no place: "au sud (aéroport Tenerife Sud)", "dans le
    nord", "sur la côte est". Nothing for the whole of it ("un voyage nord-sud")."""
    said = folded(text)
    east = lambda index: said[index] == "est" and index and (said[index - 1] in EAST_AFTER or (said[index - 1] == "l" and index > 1 and said[index - 2] in ("a", "de", "dans", "vers")))
    # "la ligne du Nord", "la gare du Nord" are names of a line and of a station, not a part of the destination.
    named = lambda index: bool(NAMED_AFTER_CARDINAL & set(said[max(0, index - 2):index]))
    found = [index for index, word in enumerate(said) if (word in CARDINAL or east(index)) and not named(index)]
    # The first one is what the fact is about ("222 h au sud, contre 150 h dans le nord"); two side by side are the
    # whole of the place ("un voyage nord-sud").
    if not found or (len(found) > 1 and found[1] == found[0] + 1):
        return set()
    return {said[found[0]]}


def widened(said: set[str]) -> set[str]:
    """These words and what they imply (IMPLIES): another spelling, another name, the town a quarter is in."""
    return said | {other for word in said for other in IMPLIES.get(word, ())}


def pictured(identifier: str, caption: str, title: str = "", everywhere: frozenset | set = frozenset()) -> set[str]:
    """The words that say what a photo shows: its identifier, its caption and its Commons title. Not where it is
    taken from ("View of Empire State Building from Rockefeller Center", "… behind Bryant Park trees"), not a place
    its caption only compares with ("Les îles Phi Phi, plus au sud que les Similan."), and not a town whose name is
    part of the name the record gives (Porto for "Porto Covo": destinations.HOMONYMS)."""
    own = words(identifier.replace("-", " "))
    title = title.removeprefix("File:").rsplit(".", 1)[0] if title else ""
    told = subject(caption) + " " + subject(title)
    known = own | words(title)
    aside = set(named(caption, everywhere, sentence=True, known=known)) - set(subjects(caption, everywhere, sentence=True, known=known))
    shown = widened((own | words(told)) - aside)
    flat = " " + " ".join(folded(caption + " " + title)) + " "
    for place, others in destinations.HOMONYMS.items():
        if place in shown and any(" " + " ".join(folded(other)) + " " in flat for other in others):
            shown = shown - {place}
    return shown


def recorded(identifier: str, caption: str, title: str = "", everywhere: frozenset | set = frozenset(), family: str | None = None) -> set[str]:
    """The precise places the record of a photo names: those of its caption; when the caption only says the
    destination (a photo of the old catalogue has none of its own: "Sintra (Portugal)."), those of its Commons title
    ("Castelo dos Mouros in Sintra" for "sintra-mouros-remparts"). Its identifier is in lower case: it cannot tell a
    place ("mouros") from a thing ("interieur", "viaduc")."""
    prefix, _, rest = identifier.partition("-")
    own = words((rest if prefix == family else identifier).replace("-", " "))
    title = title.removeprefix("File:").rsplit(".", 1)[0] if title else ""
    places = set(named(subject(caption), everywhere, sentence=True, known=own | words(title)))
    if places or not words(caption) <= set(everywhere) | GENERIC:
        return places
    return set(named(subject(title), everywhere))


VIEWPOINT = re.compile(r"\b(?:from|depuis|behind|derrière|vue?s? (?:de|du|des|d’|d'))\b", re.IGNORECASE)


def subject(text: str) -> str:
    """What a title or a caption says the photo shows, without where it was taken from: "View of Empire State
    Building from Rockefeller Center" is a photo of the Empire State Building, not of the Rockefeller Center."""
    return VIEWPOINT.split(text, 1)[0]


def shows(said: str, shown: set[str], places: set[str] | list[str] = ()) -> bool:
    """The record of a photo says something of what a text says. When the text names no precise place: a word of
    four letters and more that names something. A kind of place counts only with its name: "le pavillon d'Or du
    Kinkaku-ji" and another pavilion share "pavillon" and nothing else; "les îles Similan" are not "les îles Phi
    Phi"."""
    shared = {word for word in words(said) & shown if len(word) >= 4 and word not in HOLLOW}
    if not places:
        return any(word not in GENERIC or named_after(said, word) <= shown for word in shared)
    return any(word in GENERIC and named_after(said, word) and named_after(said, word) <= shown for word in shared)


def ways(words_said: set[str] | list[str]) -> set[str]:
    """By what one travels in these words: "rail", "urban", "road", "water"."""
    return {way for way, names in WAYS.items() if names & set(words_said)}


def ride(described: set[str], text: str = "") -> bool:
    """A photo of a means of transport, by the words of its caption, title and identifier; of the one the text opens
    on when it names one ("Le bus 205 pour…" does not go over a shinkansen)."""
    wanted = ways(folded(text)[:OPENING_WORDS])
    return bool(ways(described) & wanted) if wanted else bool(RIDES & described)


def on_the_way(recorded: set[str], places: set[str] | list[str]) -> bool:
    """The record of a ride names one of the places of a journey, or names no place: it does not stand elsewhere."""
    return not recorded or any(widened({named}) & set(places) for named in recorded)


def elsewhere(caption: str, places: set[str], everywhere: frozenset | set = frozenset()) -> set[str]:
    """The precise places a photo's caption names that are none of those the fact names: over such a photo, the fact
    would be read as a fact about that other place."""
    return proper(caption, everywhere, sentence=True) - places
