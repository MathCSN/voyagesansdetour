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
    nord sud est ouest haut haute bas basse jour jours pass""".split())
# What a journey is made by, as a fact says it; and what a photo of it shows.
TRANSPORT = frozenset("train trains shinkansen tgv couchette couchettes ferry ferries bateau bateaux bus tram tramway metro rame billet billets".split())
RIDES = TRANSPORT | frozenset("gare gares quai quais railway sleeper locomotive wagon".split())
CARRIED_BY = frozenset("en chez bus ferry train trains ligne compagnie avec".split())   # "en Nozomi", "chez Supratours"
LEADING = frozenset("le la les un une des du de ce cette ces au aux".split())
CAPITALISED = re.compile(r"[A-ZÀ-ÖØ-Þ][\w’'-]*")
# "Mérida–Tulum", "Tokyo–Kyoto–Hiroshima–Tokyo": two names joined by a dash are the two ends of a journey.
LINKED = re.compile(r"[A-ZÀ-ÖØ-Þ][\w’']*\s?[–—]\s?[A-ZÀ-ÖØ-Þ]")
OPENERS = TRANSPORT | frozenset("trajet trajets".split())   # "de trajet en Alfa Pendular entre Santa Apolónia et Campanhã"
# Words of four letters and more that two texts share without being about the same thing.
HOLLOW = frozenset("pour entre dans avec sans sous vers chez depuis selon plus moins tout tous toute toutes cette leur leurs dont comme "
                   "aussi tres deux trois quatre nuit nuits prix tarif euros pesos entree ouvert ouverte jours".split())
OPENING_WORDS = 5   # a fact is about a journey when it says so at once: "le train direct…", not "…, à 45 minutes par le train"


def folded(text: str) -> list[str]:
    """The words of a text, lower case and without accents, in their order."""
    return re.findall(r"[a-z0-9]+", destinations.ascii_fold(re.sub(r"[’'‘]", " ", text.replace("œ", "oe"))).lower())


def words(text: str) -> set[str]:
    return set(folded(text))


def named(text: str, everywhere: frozenset | set = frozenset()) -> list[str]:
    """The precise places a text names, in the order it names them: its words written with a capital, three letters
    and more, that are neither a kind of place, nor an article opening the sentence, nor the name of the destination
    of the whole post (`everywhere`: every photo of a guide of Thailand is "in Thailand"). An acronym ("SITA", "JR")
    and the name of a carrier or of a train ("en Nozomi", "chez Supratours", "bus SITA", "Alfa Pendular" after "en")
    are no places."""
    found, carrier, end = [], False, -1
    for match in CAPITALISED.finditer(text):
        before = folded(text[:match.start()])[-1:]
        carrier = (carrier and text[end:match.start()] == " ") or bool(before and before[0] in CARRIED_BY and text[match.start() - 1:match.start()] == " ")
        end = match.end()
        if carrier or (len(match[0]) > 1 and match[0].isupper()):
            continue
        found += [piece for piece in folded(match[0]) if len(piece) >= 3 and piece not in GENERIC and piece not in LEADING and piece not in everywhere]
    return list(dict.fromkeys(found))


def proper(text: str, everywhere: frozenset | set = frozenset()) -> set[str]:
    return set(named(text, everywhere))


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


def shows(said: str, shown: set[str]) -> bool:
    """The record of a photo says something of what a text says: a word of four letters and more that names
    something, or a kind of place of which the text names no other one ("Le pont en métro" and a bridge; never "les
    îles Similan" and "les îles Phi Phi")."""
    shared = {word for word in words(said) & shown if len(word) >= 4 and word not in HOLLOW}
    return any(word not in GENERIC or named_after(said, word) <= shown for word in shared)


def ride(described: set[str]) -> bool:
    """A photo of a means of transport, by the words of its caption, title and identifier."""
    return bool(RIDES & described)


def elsewhere(caption: str, places: set[str], everywhere: frozenset | set = frozenset()) -> set[str]:
    """The precise places a photo's caption names that are none of those the fact names: over such a photo, the fact
    would be read as a fact about that other place."""
    return proper(caption, everywhere) - places
