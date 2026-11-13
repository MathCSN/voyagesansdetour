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
    nord sud est ouest haut haute bas basse jour jours pass
    janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre
    lundi mardi mercredi jeudi vendredi samedi dimanche noel paques
    park center centre square street bridge tower beach island islands lake mount river market museum garden gardens
    palace church house hall city bay view""".split())
# What a journey is made by, as a fact says it; and what a photo of it shows.
WAYS = {"rail": frozenset("train trains shinkansen tgv couchette couchettes rame railway sleeper locomotive wagon".split()),
        "urban": frozenset("metro tram tramway".split()), "road": frozenset(["bus"]),
        "water": frozenset("ferry ferries bateau bateaux".split())}
RIDES = frozenset().union(*WAYS.values())   # never a station alone: it is a place
TRANSPORT = RIDES | frozenset("billet billets".split())
CARRIED_BY = frozenset("en chez bus ferry train trains ligne compagnie avec".split())   # "en Nozomi", "chez Supratours"
SHORT = frozenset("el or st mt da do di al ii iii iv ji ko".split())   # two letters with a capital that name no place alone ("Sa Pa" does)
LEADING = frozenset("le la les un une des du de ce cette ces au aux".split())
CAPITALISED = re.compile(r"[A-ZÀ-ÖØ-Þ][\w’'-]*")
# "Mérida–Tulum", "Tokyo–Kyoto–Hiroshima–Tokyo": two names joined by a dash are the two ends of a journey.
LINKED = re.compile(r"[A-ZÀ-ÖØ-Þ][\w’']{0,40}\s?[–—]\s?[A-ZÀ-ÖØ-Þ]")
OPENERS = TRANSPORT | frozenset("trajet trajets minibus navette".split())   # "de trajet en Alfa Pendular entre Santa Apolónia et Campanhã"
# Words of four letters and more that two texts share without being about the same thing.
HOLLOW = frozenset("pour entre dans avec sans sous vers chez depuis selon plus moins tout tous toute toutes cette leur leurs dont comme "
                   "aussi tres deux trois quatre nuit nuits prix tarif euros pesos entree ouvert ouverte jours".split())
OPENING_WORDS = 5   # a fact is about a journey when it says so at once: "le train direct…", not "…, à 45 minutes par le train"


def folded(text: str) -> list[str]:
    """The words of a text, lower case and without accents, in their order."""
    return re.findall(r"[a-z0-9]+", destinations.ascii_fold(re.sub(r"[’'‘]", " ", text.replace("œ", "oe"))).lower())


def words(text: str) -> set[str]:
    return set(folded(text))


def named(text: str, everywhere: frozenset | set = frozenset(), sentence: bool = False) -> list[str]:
    """The precise places a text names, in the order it names them: its words written with a capital, three letters
    and more, that are neither a kind of place, nor an article opening the sentence, nor the name of the destination
    of the whole post (`everywhere`: every photo of a guide of Thailand is "in Thailand"). An acronym ("SITA", "JR")
    and the name of a carrier or of a train ("en Nozomi", "chez Supratours", "bus SITA", "Alfa Pendular" after "en")
    are no places; nor is a means of transport ("Bus 500", "Billet CP"). `sentence`: the text is a sentence, a caption:
    its first word has a capital by grammar ("Visiteurs dans un jardin zen."), unless a name follows it at once."""
    found, carrier, end = [], False, -1
    for match in CAPITALISED.finditer(text):
        if sentence and not text[:match.start()].strip("«“\" ") and not CAPITALISED.match(text[match.end():].lstrip(" ")):
            end = match.end()
            continue
        before = folded(text[:match.start()])[-1:]
        carrier = (carrier and text[end:match.start()] == " ") or bool(before and before[0] in CARRIED_BY and text[match.start() - 1:match.start()] == " ")
        end = match.end()
        if carrier or (len(match[0]) > 1 and match[0].isupper()):
            continue
        found += [piece for piece in folded(match[0])
                  if len(piece) >= 2 and piece not in GENERIC and piece not in LEADING and piece not in OPENERS and piece not in SHORT
                  and piece not in everywhere]
    return list(dict.fromkeys(found))


SUBJECT_GAP = 4   # words at most between two places a fact is about: "Bahia, des tombeaux saadiens ou d'El Badi"


def subjects(text: str, everywhere: frozenset | set = frozenset()) -> list[str]:
    """The places a fact is about, among those it names: the first one, and those it lists with it ("Mérida et Uxmal",
    "de Surat Thani à Krabi", "Bangkok, Chiang Mai et la mer d'Andaman"). A place named further on, after a figure or
    a long stretch of words, only situates the fact: "le Grand Bouddha du Tōdai-ji, à Nara, à 45 minutes de Kyoto"
    is about the Tōdai-ji and Nara, not about Kyoto."""
    about, end = [], None
    for match in CAPITALISED.finditer(text):
        pieces = [piece for piece in named(match[0], everywhere) if piece in named(text, everywhere)]
        if not pieces:
            end = match.end() if end is not None else None   # a word of the name itself ("Chiang Mai", "El Badi")
            continue
        gap = text[end:match.start()] if end is not None else ""
        if end is not None and (re.search(r"\d", gap) or len(folded(gap)) > SUBJECT_GAP):
            break
        about, end = about + pieces, match.end()
    return list(dict.fromkeys(about))


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


def journey(text: str) -> bool:
    """A fact about a journey: an arrow or a dash between two names, or a means of transport in its first words."""
    return "→" in text or bool(LINKED.search(text)) or bool(OPENERS & set(folded(text)[:OPENING_WORDS]))


VIEWPOINT = re.compile(r"\b(?:from|depuis|vue?s? (?:de|du|des|d’|d'))\b", re.IGNORECASE)


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


def elsewhere(caption: str, places: set[str], everywhere: frozenset | set = frozenset()) -> set[str]:
    """The precise places a photo's caption names that are none of those the fact names: over such a photo, the fact
    would be read as a fact about that other place."""
    return proper(caption, everywhere, sentence=True) - places
