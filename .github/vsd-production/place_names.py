"""Which precise places a text names, and whether a photo is a photo of them.

A figure goes over a photo of the place it names, never over another one. On 13/11/2026 two photo posts went out of
the generator with "la réouverture des îles Similan" over Ko Phi Phi (the two only shared the word "îles") and "le
pavillon d'Or du Kinkaku-ji" over the sign of Shin-Fuji station. This module says what a precise place is (a proper
noun: Similan, Kinkaku-ji, Uxmal, Campanhã), which words never tie a figure to a photo (kinds of places: île, plage,
temple, gare, train…), and what a journey is ("Tokyo → Kyoto en Nozomi" goes over a train first).

Used by reel_formats.py (to choose the photo), by pin_draft.py (the figures of a Pin) and by production.py (to
refuse a scenario that got it wrong): one reading for the three.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    palace church house hall city bay view station railway railways castle cathedral temple old town night day
    ponte praia praca rua igreja torre castelo palacio estacao mosteiro cais largo miradouro jardim catedral plaza puente
    real via""".split())
# What a journey is made by, as a fact says it; and what a photo of it shows.
WAYS = {"rail": frozenset("train trains shinkansen tgv couchette couchettes rame railway sleeper locomotive wagon "
                          "tren trenes comboio comboios treno treni".split()),
        "metro": frozenset("metro metros".split()), "tram": frozenset("tram trams tramway eletrico".split()),
        "road": frozenset("bus minibus navette autocar".split()),
        "water": frozenset("ferry ferries bateau bateaux barque barques sampan sampans boat boats".split())}
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
    jr japan rail pass card cards suica pasmo icoca oyster tfl contactless grab bolt uber city lockers locker bounce nannybag luggage
    pere noel claus santa inah unesco covid wifi
    francais francaise francaises europeen europeens europeenne portugais portugaise espagnol espagnole italien italienne
    japonais japonaise thailandais thailandaise vietnamien vietnamienne mexicain mexicaine marocain marocaine finlandais
    finlandaise britannique britanniques anglais anglaise americain americaine americains suisse suisses belge belges thai
    """.split())
# Words of NOT_PLACES that also make up names of places ("Maya Bay", "Santa Claus Village", "City Hall"): alone they
# name no place, in a name with a kind of place (KINDS) they do. The others never make a place (HARD).
SHARED_WITH_PLACES = frozenset("maya santa claus city japan regional metro viva bolt".split())
HARD = NOT_PLACES - SHARED_WITH_PLACES
# Kinds of places that make a name of words that are otherwise no place: "Maya Bay", "Santa Claus Village", "Tower
# Bridge", "Grand Palace" (review of 13/11/2026: "Maya Bay : 400 bahts" took any free photo). Not "tour" (l'Andante Tour).
KINDS = frozenset("bay baie village palace palais bridge park parc square tower market garden gardens beach island islands "
                  "lake castle cathedral church hall museum cove lagoon falls canal plaza".split())
# Small English words of a Commons title written in capitals ("… TRAIN BUTTERWORTH TO BANGKOK"): never a place.
SMALL = frozenset("to of the and in at on by for with from near".split())
# Two spellings or two names of one place: a record that gives one gives the other. Whole names, never a part of one
# ("Minh Mang" is not Hô-Chi-Minh-Ville, "Pa Sak" is not Sapa). Reviewed by hand.
ALIASES = {("kinkakuji",): (("kinkaku",),), ("kinkaku",): (("kinkakuji",),), ("saigon",): (("ho", "chi", "minh"),),
           ("ho", "chi", "minh"): (("saigon",),), ("sapa",): (("sa", "pa"),), ("sa", "pa"): (("sapa",),),
           ("danang",): (("da", "nang"),), ("da", "nang"): (("danang",),), ("hanoi",): (("ha", "noi"),), ("ha", "noi"): (("hanoi",),),
           ("santa", "claus", "village"): (("village", "pere", "noel"),)}
# A quarter and the town it is in: a photo of Belém is a photo of Lisbon for a fact that is first about Lisbon, never
# for a fact about another place of Lisbon ("le château São Jorge" went over the tower of Belém). Reviewed by hand.
INSIDE = {"belem": "lisbonne", "alfama": "lisbonne", "baixa": "lisbonne", "chiado": "lisbonne", "graca": "lisbonne",
          "ribeira": "porto", "shibuya": "tokyo", "shinjuku": "tokyo", "asakusa": "tokyo", "gion": "kyoto", "arashiyama": "kyoto"}
# Trains a fact may name: a fact about one is never shown over another ("28,05 € Intercidades" over an Alfa Pendular).
BRANDS = {"alfa pendular": {"alfa", "pendular", "alfapendular"}, "intercidades": {"intercidades"}, "nozomi": {"nozomi"},
          "hikari": {"hikari"}, "kodama": {"kodama"}, "ave": {"ave"}, "ouigo": {"ouigo"}, "avlo": {"avlo"}, "iryo": {"iryo"},
          "frecciarossa": {"frecciarossa"}, "italo": {"italo"}}
MONTHS = frozenset("janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre".split())
# Letters that no accent rule folds to ASCII: "Đà Lạt" was read "à Lạt".
PLAIN = str.maketrans({"Đ": "D", "đ": "d", "Ł": "L", "ł": "l", "Ø": "O", "ø": "o", "İ": "I", "ı": "i", "ß": "ss", "œ": "oe", "Œ": "Oe", "æ": "ae", "Æ": "Ae"})
SHORT = frozenset("el or st mt da do di al ii iii iv ji ko".split())   # two letters with a capital that name no place alone ("Sa Pa" does)
LEADING = frozenset("le la les un une des du de ce cette ces au aux dell della dello degli delle".split())
WORD = re.compile(r"[^\W\d_][\w’'-]*")
# "Mérida–Tulum", "Tokyo → Kyoto", "Tokyo–Kyoto–Hiroshima–Tokyo": two names joined by an arrow or a dash are the two
# ends of a journey. Not two hours ("9 h 40 → 12 h 12"), nor a clause set off by a long dash.
LINKED = re.compile(r"([^\W\d_][\w’']{0,40})\s?[→–]\s?([^\W\d_])")
# What opens a fact about a journey: "de trajet en Alfa Pendular entre Santa Apolónia et Campanhã". A ticket alone
# does not ("le billet de la vieille ville de Hội An" went over a train): it opens a journey with its means of transport.
OPENERS = RIDES | frozenset("trajet trajets traversee minibus navette".split())


class _Capitalised:
    """Words that begin with a capital, in any alphabet Python knows ("Đà", "Šibenik", "Ōsaka", "Łódź"); the capital
    may follow an elision ("d’Andaman" gives "Andaman", "L’Alhambra" is one word)."""

    @staticmethod
    def finditer(text: str):
        position = 0
        while position < len(text):
            match = WORD.match(text, position) if text[position].isupper() else None
            if match:
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
OPENING_WORDS = 5   # a fact is about a journey when it says so at once: "le train direct…", not "…, à 45 minutes par le train"


def folded(text: str) -> list[str]:
    """The words of a text, lower case and without accents, in their order."""
    return re.findall(r"[a-z0-9]+", destinations.ascii_fold(re.sub(r"[’'‘]", " ", text.translate(PLAIN))).lower())


def words(text: str) -> set[str]:
    return set(folded(text))


Name = tuple   # the place-words of one name, in order: ("trang", "an"), ("ho", "chi", "minh"), ("maya", "bay")


def names(text: str, everywhere: frozenset | set = frozenset(), sentence: bool = False,
          known: frozenset | set = frozenset()) -> list[tuple[Name, int, int]]:
    """The precise places a text names, whole, in the order it names them, with where each stands in the text. A name
    is a run of words written with a capital and separated by a space ("Tràng An", "Ninh Bình", "Porto-Trindade");
    its place-words are those that are neither a kind of place, nor an article, nor the destination of the whole post
    (`everywhere`), nor a ticket, a card, an operator, a train, a brand or a people (NOT_PLACES). An acronym ("SITA",
    "MEPE") and what follows "chez", "ligne" ("chez Supratours") name no place. A month is part of a name after
    another word ("Chiang Mai"). A run of words that are otherwise no place is a name when it holds a kind of place
    and no ticket ("Maya Bay", "Santa Claus Village", "Grand Palace"). `sentence`: the text is a caption; its first
    word has a capital by grammar ("Visiteurs dans un jardin zen."), unless a name follows it at once or `known` (the
    words of the photo's identifier and title) says it is the place ("Vernazza et son port")."""
    text = ordinary(text)
    found, run, carrier, end = [], None, False, -1
    for match in CAPITALISED.finditer(text):
        first = sentence and not text[:match.start()].strip("«“\" ")
        adjacent = end >= 0 and joined(run, text[end:match.start()])
        end = match.end()
        if not adjacent:
            found, run = found + closed(run), None
        role, carrier = role_of(text, match, carrier, adjacent, first, known)
        if role == "break":
            found, run = found + closed(run), None
        elif role != "skip":
            run = extended(run, match, folded(match[0]) if role == "word" else [], everywhere, adjacent and not first)
    return found + closed(run)


def role_of(text: str, match: re.Match, carrier: bool, adjacent: bool, first: bool, known: frozenset | set) -> tuple[str, bool]:
    """What one capitalised word does to the name being read ("skip", "break", "acronym" or "word"), and whether the
    name of a carrier runs on after it."""
    if first and grammar_capital(text, match, known):
        return "skip", carrier
    if set(folded(match[0])) <= SMALL:
        return "break", carrier   # "Malaysia To Bangkok": two names
    # The acronym is the carrier's whole name: "le bus MEPE Puerto Viejo – San José".
    acronym = len(match[0]) > 1 and match[0].isupper()
    carrier = not acronym and ((carrier and adjacent) or after_carrier(text, match))
    if carrier:
        return "break", carrier
    return ("acronym" if acronym else "word"), carrier


def grammar_capital(text: str, match: re.Match, known: frozenset | set) -> bool:
    """The first word of a caption, written with a capital by grammar: no name follows it, and it is not the place."""
    return not CAPITALISED.match(text[match.end():].lstrip(" ")) and not set(folded(match[0])) & set(known)


def after_carrier(text: str, match: re.Match) -> bool:
    """A capitalised word right after "chez", "ligne"…: the name of a carrier, not of a place."""
    before = folded(text[:match.start()])[-1:]
    return bool(before and before[0] in CARRIED_BY and text[match.start() - 1:match.start()] == " ")


def ordinary(text: str) -> str:
    """A text written mostly in capitals, in ordinary case ("LISBONNE", "HÔ-CHI-MINH-VILLE"): each word then reads as a
    name, as in a Commons title (readable). The same length, so what is found stands at the same place."""
    letters = sum(c.isalpha() for c in text)
    titled_text = text.title()
    if sum(c.isupper() for c in text) > 0.6 * max(1, letters) and len(titled_text) == len(text):
        return titled_text
    return text


# Between two capitalised words, what keeps them one name: a space of any kind, a line break ("Ninh Bình" with a
# non-breaking space); and after a word that begins a name, its particles ("Puerto de la Cruz", "Vila do Conde").
SPACES = frozenset("   \n")
PARTICLES = re.compile(r"[  ](?:de la|del|de|do|da|dos|das|di)[  ]")
# Words that name no place alone but are part of a longer name: "Santa Cruz" is not "Puerto de la Cruz", "Đà Nẵng" is
# not Ao Nang, "Mai Châu" is not Châu Đốc. Not the kinds of places that change with the language of the record ("Tour
# Eiffel", "Eiffel Tower"; "mont Fuji", "Mount Fuji"): those stay out of the name.
# Not "real" either: "le Real Alcázar" and a photo titled "Alcázar of Seville" are one place.
IN_NAMES = frozenset("saint sainte san santa sao los las puerto costa vila monte cabo punta rio chiang khao da do di el".split()) | MONTHS


def joined(run: list | None, gap: str) -> bool:
    if gap and set(gap) <= SPACES:
        return True
    starts_a_name = bool(run) and not run[0] and len(run[1]) == 1 and run[1][0] in IN_NAMES
    return starts_a_name and bool(PARTICLES.fullmatch(gap))


def closed(run: list | None) -> list[tuple[Name, int, int]]:
    """The name a run of capitalised words makes: its place-words and those of its words that belong to a longer name
    (IN_NAMES: "Santa Cruz", "Đà Nẵng"); or, when it has no place-word, its words when they hold a kind of place or
    are all generic and one of them begins a name, and no ticket ("Maya Bay", "Vila Real"); nothing otherwise."""
    if not run:
        return []
    if run[0]:
        whole = [word for word in run[1] if word in run[0] or word in IN_NAMES]
        return [(tuple(dict.fromkeys(whole or run[0])), run[2], run[3])]
    # All generic, one of them the beginning of a name: "Vila Real". Not "Grand Bouddha", "Old Town".
    all_generic = set(run[1]) <= GENERIC and bool(set(run[1]) & IN_NAMES)
    if len(run[1]) >= 2 and (set(run[1]) & KINDS or all_generic) and not set(run[1]) & HARD:
        return [(tuple(dict.fromkeys(run[1])), run[2], run[3])]
    return []


def extended(run: list | None, match: re.Match, pieces: list[str], everywhere: frozenset | set, after_a_name: bool) -> list:
    """The run of capitalised words with one more: [place-words, words, start, end]."""
    placed = [piece for piece in pieces if names_a_place(piece, everywhere, after_a_name)]
    # "Chiang Mai", "Chiang Rai", "Khao Sok": the head of the name is kept, or "mai" alone would be any May.
    if placed and run and not run[0] and run[1][-1:] and run[1][-1] in NAME_HEADS:
        placed = run[1][-1:] + placed
    raw = [piece for piece in pieces if piece not in LEADING and piece not in everywhere]
    start = run[2] if run else match.start()
    return [(run[0] if run else []) + placed, (run[1] if run else []) + raw, start, match.end()]


NAME_HEADS = frozenset("chiang khao".split())
UNNAMED = GENERIC | LEADING | OPENERS | TRANSPORT | SHORT | NOT_PLACES | SMALL


def names_a_place(piece: str, everywhere: frozenset | set, after_a_name: bool) -> bool:
    """One word of a capitalised name: two letters and more, no kind of place, no article, no means of transport, no
    name that is not a place, not the destination itself; a month only right after another capitalised word."""
    if len(piece) < 2 or piece in everywhere:
        return False
    return piece not in UNNAMED or (piece in MONTHS and after_a_name)


def named(text: str, everywhere: frozenset | set = frozenset(), sentence: bool = False, known: frozenset | set = frozenset()) -> list[str]:
    """The words of the precise places a text names, in the order it names them (see `names`)."""
    return list(dict.fromkeys(piece for name, _, _ in names(text, everywhere, sentence, known) for piece in name))


def proper(text: str, everywhere: frozenset | set = frozenset(), sentence: bool = False) -> set[str]:
    return set(named(text, everywhere, sentence))


SUBJECT_GAP = 4   # words at most between two places a fact is about: "Bangkok, Chiang Mai et la mer d'Andaman"
# What sets a place off as where the first one stands, not as another place the fact is about: "le Grand Bouddha du
# Tōdai-ji, à Nara", "Maya Bay, à Phi Phi", "le Real Alcázar de Séville", "le château São Jorge à Lisbonne".
SITUATING = frozenset(["à", "a", "au", "aux", "en", "dans", "sur", "de", "du", "des", "d’", "d'",
                       "près d", "près de", "près du", "près d’", "près d'", "pres d"])


def situates(gap: str, journeying: bool) -> bool:
    """The words between two places set the second off as where the first one stands: after a comma, always ("…, à
    Nara"); right after it ("le Real Alcázar de Séville"), only when the fact is no journey ("de Hanoï à Hué")."""
    if SITUATING_AFTER_COMMA.match(gap):
        return True
    word = gap.strip()
    if word[:1] in (",", "("):
        word = word[1:].strip()
    return not journeying and word.lower() in SITUATING
SITUATING_AFTER_COMMA = re.compile(r"^\s*[,(]\s*(?:à|a|au|aux|en|dans|sur|près d|pres d)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Reading:
    """What a fact says of places: the one it is first about, the others it lists with it, those it only situates
    the first one in, and every name it says."""
    first: Name | None
    listed: tuple
    situating: tuple
    all: tuple
    said: frozenset


def word_before(text: str, start: int) -> str:
    return "".join(folded(text[:start])[-1:])


def beyond_subject(gap: str) -> bool:
    """A figure or a long stretch of words between two places: the second only situates the fact."""
    return bool(re.search(r"\d", gap)) or len(folded(gap)) > SUBJECT_GAP


def read(text: str, everywhere: frozenset | set = frozenset()) -> Reading:
    """The places a fact is about: the first one it names, and those it lists with it ("Mérida et Uxmal", "de Surat
    Thani à Krabi", "Bangkok, Chiang Mai et la mer d'Andaman"); the places it situates the first one in ("…, à Nara");
    a place named further on, after a figure or a long stretch of words, only situates the fact and is none of these
    ("…, à 45 minutes de Kyoto"); nor is a place one only comes from ("depuis Kyoto pour voir…")."""
    found = names(text, everywhere)
    first, listed, situating, end, origins = None, [], [], None, []
    journeying = journey(text)
    for name, start, stop in found:
        if word_before(text, start) in ("depuis", "from"):
            origins.append(name)
            continue
        if first is None:
            first, end = name, stop
            journeying = journeying or word_before(text, start) in ("de", "d", "entre")
            continue
        gap = text[end:start] if start >= end else ""
        if beyond_subject(gap):
            break
        (situating if situates(gap, journeying) else listed).append(name)
        end = stop
    if first is None and origins:
        # "la traversée du fleuve en ferry depuis Bangkok": no other place, the fact is about where it starts.
        first, listed = origins[0], origins[1:]
    return Reading(first, tuple(listed), tuple(situating), tuple(name for name, _, _ in found), frozenset(words(text)))


def titled(title: str, everywhere: frozenset | set = frozenset()) -> str:
    """The stretch of a title that names its places ("Jours 6 et 7 — Hué" → "Hué", "Jours 5 à 8 — Kyoto et Nara" →
    "Kyoto et Nara"), the destination aside; "" when it names none. Read the same by the generator and the guard."""
    found = names(title, everywhere, sentence=True)
    if not found:
        return ""
    stretch = title[found[0][1]:found[-1][2]]
    # "Mer d'Andaman (Phuket, Krabi)": the stretch ends inside the brackets; it takes them whole, or none of them.
    if stretch.count("(") > stretch.count(")"):
        closing = title.find(")", found[-1][2])
        stretch = title[found[0][1]:closing + 1] if closing >= 0 else stretch.replace("(", "")
    return stretch.strip()


def beyond(text: str, title: str, everywhere: frozenset | set = frozenset()) -> list[Name]:
    """The places a text names that a title does not name."""
    told = [name for name, _, _ in names(title, everywhere, sentence=True)]
    return [name for name, _, _ in names(text, everywhere, sentence=True) if not any(same(name, other) for other in told)]


def opening_fits(text: str, title: str, shown: set[str], everywhere: frozenset | set = frozenset()) -> bool:
    """The opening of a post over its first photo: what it names beyond the guide's title, the photo shows one of
    ("un même mois peut être parfait à Saïgon et inondé à Hội An" went over the bay of Ha Long). A promise that
    lists the guide's places ("pour Bangkok, le Nord, l'Andaman et Koh Samui") holds with a photo of one of them."""
    named = [name for line in re.split(r"\n|(?<=[.!?:])\s+", text) for name in beyond(line, title, everywhere)]
    return not named or any(shows(name, widened(shown)) for name in named)


def subjects(text: str, everywhere: frozenset | set = frozenset()) -> list[str]:
    """The words of the places a fact is about: its first place and those it lists with it (see `read`)."""
    reading = read(text, everywhere)
    return list(dict.fromkeys(piece for name in ((reading.first,) if reading.first else ()) + reading.listed for piece in name))


def variants(name: Name) -> tuple:
    return (name,) + ALIASES.get(tuple(name), ())


def shows(name: Name, shown: set[str]) -> bool:
    """The words of a record hold this whole name, or another name of the same place: "Tràng An" is not shown by a
    record that says "Quảng Ninh" for "Ninh Bình"."""
    return any(set(variant) <= shown for variant in variants(name))


def same(one: Name, other: Name) -> bool:
    return any(set(a) == set(b) for a in variants(one) for b in variants(other))


def linked(text: str) -> bool:
    """Two names joined by an arrow or a dash: "Tokyo → Kyoto", "Mérida–Tulum"; not "9 h 40 → 12 h 12", nor two
    months ("Novembre–Avril")."""
    return any(match[1][0].isupper() and match[2].isupper() and not (folded(match[1])[-1:] and folded(match[1])[-1] in MONTHS
                                                                      and set(folded(text[match.end(2) - 1:])[:1]) & MONTHS)
               for match in LINKED.finditer(text))


def journey(text: str) -> bool:
    """A fact about a journey: an arrow or a dash between two names, or a means of transport in its first words."""
    opening = folded(text)[:OPENING_WORDS]
    return linked(text) or bool(OPENERS & set(opening)) or bool(CAR.search(" ".join(opening))) or travelled(text)


# "SE3", "SE1": the trains of the Reunification line, named by their number.
TRAIN_NUMBER = re.compile(r"\bSE\d{1,2}\b")
FROM_TO = re.compile(r"\b(?:de|d[’']|entre|depuis)\s*$", re.IGNORECASE)
AND_TO = re.compile(r"(?:^|\s)(?:à|a|et|jusqu[’']à)\s*$", re.IGNORECASE)
HOURS = re.compile(r"\d\s?h\b")


# "le car pour Essaouira", "3 h de car": the coach, never the conjunction ("car il pleut").
CAR = re.compile(r"\b(?:de|en|le|du|un|au|par)\s+car\b", re.IGNORECASE)
PARTICLE_WORDS = frozenset("do da dos das del della di du".split())


def travelled(text: str) -> bool:
    """A journey that says its means further on: from one place to another ("de Hué à Đà Nẵng en train de jour", "entre
    Ninh Bình (SE3, 21 h 35) et Hué", "entre Cais do Sodré et Belém"), with a means of transport, a train by its brand
    or its number ("de Tokyo à Kyoto en Nozomi"), the coach, or an hour."""
    found = names(text)
    ends = any(starts_from(text[:one[1]]) and AND_TO.search(text[one[2]:other[1]]) for one, other in zip(found, found[1:]))
    said = set(folded(text))
    return ends and bool(RIDES & said or brands(said) or CAR.search(text) or TRAIN_NUMBER.search(text) or HOURS.search(text))


def starts_from(before: str) -> bool:
    """The words before a name open a journey ("de", "entre", "depuis"), past the kinds of places and the particles of
    that name ("entre Cais do Sodré": "Cais" and "do" are part of it)."""
    words = before.rstrip().split(" ")
    while words:
        if FROM_TO.search(" ".join(words) + " "):
            return True
        last = folded(words[-1])
        if not last or not set(last) <= GENERIC | PARTICLE_WORDS:
            return False
        words.pop()
    return False


def wanted_ways(text: str) -> set[str]:
    """The means of transport a journey is made by: the one it opens on, else the one it names further on; a train
    when it names one by its brand or its number ("Nozomi", "SE3")."""
    said = folded(text)
    found = ways(said[:OPENING_WORDS]) or ways(said)
    if found:
        return found
    if CAR.search(text):
        return {"road"}
    if brands(set(said)) or TRAIN_NUMBER.search(text):
        return {"rail"}
    # "le taxi à prix fixe depuis l'aéroport": a means no photo of a train, a tram or a bus shows.
    return {"other"} if OTHER_MEANS & set(said[:OPENING_WORDS]) else set()


def strict_journey(text: str) -> bool:
    """A journey that names its two ends and its means ("de Hué à Đà Nẵng en train de jour", "Séville → Cordoue en
    AVE"): it goes over a photo of that means of transport, or stays in the guide. Over the gate of the imperial city
    of Hué, the photo said nothing of the train (review of PR 53). A ticket or a fare that names one place at most ("le
    ticket bus SITA", "le plafond quotidien du métro") is no such journey."""
    return journey(text) and (linked(text) or travelled(text)) and bool(wanted_ways(text))


def vehicle(identifier: str, caption: str, title: str) -> set[str]:
    """The means of transport a photo is of: the one its caption opens on, or its title names ("Des barques sur la
    rivière de Tràng An", "Trang An boats"); not boats "au premier plan" of a view of the Ribeira, nor the identifier it
    is filed under ("train-campanha" is the façade of a station, no train). `identifier` is kept for the callers."""
    return ways(folded(caption)[:OPENING_WORDS]) | ways(folded(readable(title)))


def journeys_table(rows: list[list[str]], said: str = "") -> set[str]:
    """The means of transport of a table that lists journeys ("Séville → Cordoue (AVE, Avant) | 40 à 48 min"): most of
    its rows join two places, and it says by what; nothing otherwise."""
    linked_rows = sum(1 for row in rows if linked(str(row[0])))
    if not rows or 2 * linked_rows < len(rows):
        return set()
    return wanted_ways(" ".join(" ".join(map(str, row)) for row in rows) + " " + said)


def other_ride(shown_ways: set[str], text: str) -> bool:
    """A journey over a photo of another means of transport than its own (`shown_ways`, see `vehicle`): "de nuit entre
    Ninh Bình (SE3…) et Hué" went over the boats of Tràng An. A photo of no means at all is not concerned."""
    wanted = wanted_ways(text)
    concerned = journey(text) or "other" in wanted   # "16 à 23 € le taxi…" went over a tram of Lisbon
    return bool(concerned and shown_ways and wanted and not shown_ways & wanted)


CARDINAL = frozenset("nord sud ouest centre".split())
EAST_AFTER = frozenset("cote rive versant facade".split())
NAMED_AFTER_CARDINAL = frozenset("ligne gare station autoroute route".split())
# "Corée du Sud", "Afrique du Sud", "la mer du Nord", "le cap Nord", "le pôle Sud": names, not parts of the destination.
NAME_BEFORE_CARDINAL = frozenset("coree afrique amerique soudan irlande ossetie caroline dakota mer cap pole asie".split())
OPPOSITE = ({"nord", "sud"}, {"est", "ouest"})


def region(text: str) -> set[str]:
    """The part of the destination a fact is about when it names no place: "au sud (aéroport Tenerife Sud)", "dans le
    nord", "sur la côte est", "le Centre", "le sud-ouest". Nothing for the whole of it ("un voyage nord-sud"), for a
    name ("Corée du Sud", "le cap Nord", "l'Asie du Sud-Est"), nor for the verb ("la côte est magnifique"). Written
    with a capital after a name ("Tenerife Sud"), it is part of that name; "centre" only with its capital ("le Centre",
    not "le centre historique")."""
    compound = compound_part(text)
    if compound:
        return compound
    raw = [match[0] for match in re.finditer(r"[^\W\d_]+", text.translate(PLAIN))]
    said = [destinations.ascii_fold(word).lower() for word in raw]
    found = [index for index in range(len(said)) if is_part(raw, said, index)]
    if not found:
        return set()
    if len(found) > 1 and whole(said, found[0], found[1]):
        return set()
    return {said[found[0]]}


def compound_part(text: str) -> set[str]:
    """"le sud-ouest", "Le Nord-Est": one part, both words; "l'Asie du Sud-Est", "le Sud-Est asiatique": a name."""
    compound = re.search(r"\b(nord|sud)-(est|ouest)\b(?!\s+(?:asiatique|americain|europeen|africain))", destinations.ascii_fold(text), re.IGNORECASE)
    if compound and not NAME_BEFORE_CARDINAL & set(folded(text[:compound.start()])[-2:]):
        return {compound[1].lower(), compound[2].lower()}
    return set()


def is_part(raw: list[str], said: list[str], index: int) -> bool:
    """One word of a fact names a part of the destination: a cardinal point, "est" only as one, "centre" only with its
    capital; not inside a name ("Tenerife Sud", "la ligne Nord", "Corée du Sud", "Sud-Est asiatique")."""
    word, before = said[index], said[max(0, index - 2):index]
    if word == "centre" and not raw[index][0].isupper():
        return False
    if word == "est" and not east(said, before, index):
        return False
    if word != "est" and word not in CARDINAL:
        return False
    if NAMED_AFTER_CARDINAL & set(before) or NAME_BEFORE_CARDINAL & set(before):
        return False
    if raw[index][0].isupper() and index and raw[index - 1][0].isupper() and said[index - 1] not in LEADING:
        return False   # "Tenerife Sud", "Sud-Est"
    return not adjective_after(said, index)


def east(said: list[str], before: list[str], index: int) -> bool:
    """"est" as the east, not the verb: "Le Sud est plus chaud", "la côte est magnifique"."""
    after = said[index + 1:index + 2]
    if not (before[-1:] and before[-1] in EAST_AFTER or before[-2:] in (["a", "l"], ["de", "l"], ["dans", "l"], ["vers", "l"])):
        return False
    return not (after and after[0] not in ("de", "du", "des", "d", "l", "et"))


def adjective_after(said: list[str], index: int) -> bool:
    """"Sud asiatique", "Sud-Est asiatique": the name of a region of the world."""
    after, then = said[index + 1:index + 2], said[index + 2:index + 3]
    return after in (["asiatique"], ["americain"], ["europeen"], ["africain"]) or \
        (after in (["est"], ["ouest"]) and then in (["asiatique"], ["americain"], ["europeen"]))


def whole(said: list[str], one: int, other: int) -> bool:
    """"nord-sud", "du nord au sud", "le Nord et le Sud": the whole of the place. Not a comparison of two parts:
    "222 h au sud, contre 150 h dans le nord" is about the south."""
    if {said[one], said[other]} not in OPPOSITE:
        return False
    return not set(said[one + 1:other]) & {"contre", "que", "plutot", "mais", "alors"}


def widened(said: set[str]) -> set[str]:
    """These words and the towns of the quarters they name (INSIDE): Belém is in Lisbon."""
    return said | {INSIDE[word] for word in said if word in INSIDE}


VIEWPOINT = re.compile(r"\b(?:from|depuis|behind|derrière|vue?s? (?:de|du|des|d’|d'))\b", re.IGNORECASE)
# What sets a place off as a neighbour or a comparison, not as what the photo shows: "Pise, près de Florence", "Kyoto,
# plus au sud que Tokyo", "Les îles Phi Phi, plus au sud que les Similan".
COMPARED = re.compile(r"\b(?:près d[eu’']?|pres d[eu]?|à côté d[eu’']?|a cote d[eu]?|non loin d[eu’']?|loin d[eu’']?|near|next to|"
                      r"close to|au (?:nord|sud|large|pied)(?:-(?:est|ouest))? d[eu’']?|à l[’'](?:est|ouest) d[eu’']?|en face d[eu’']?|"
                      r"face à|que|than|comme|like|vers|towards?|to(?=\s)|à destination d[eu’']?|à \d[\d\s,]* ?km d[eu’']?)", re.IGNORECASE)


def subject(text: str) -> str:
    """What a title or a caption says the photo shows, without where it was taken from: "View of Empire State
    Building from Rockefeller Center" is a photo of the Empire State Building, not of the Rockefeller Center."""
    return VIEWPOINT.split(text, 1)[0]


def readable(title: str) -> str:
    """A Commons title without its prefix and extension, in ordinary case when it is written in capitals."""
    return ordinary(title.removeprefix("File:").rsplit(".", 1)[0] if title else "")


def compared(text: str, everywhere: frozenset | set = frozenset(), known: frozenset | set = frozenset()) -> list[Name]:
    """The names a caption only compares the photo's place with, or sets it beside."""
    zones = []
    for match in COMPARED.finditer(text):
        stop = re.search(r"[,.;()]", text[match.end():])
        zones.append((match.end(), match.end() + stop.start() if stop else len(text)))
    return [name for name, start, _ in names(text, everywhere, sentence=True, known=known) if any(a <= start < b for a, b in zones)]


def pictured(identifier: str, caption: str, title: str = "", everywhere: frozenset | set = frozenset()) -> set[str]:
    """The words that say what a photo shows: its identifier, its caption and its Commons title. Not where it is
    taken from ("View of Empire State Building from Rockefeller Center", "… behind Bryant Park trees"), not a place
    its caption only compares with or sets it beside ("Les îles Phi Phi, plus au sud que les Similan.", "Pise, près
    de Florence"), and not a town whose name is part of the name the record gives (Porto for "Porto Covo")."""
    own = words(identifier.replace("-", " "))
    title = readable(title)
    told = subject(caption) + " " + subject(title)
    aside = {piece for name in compared(caption, everywhere, own | words(title)) for piece in name}
    shown = (own | words(told)) - aside
    flat = " " + " ".join(folded(caption + " " + title)) + " "
    for place, others in destinations.HOMONYMS.items():
        if place in shown and any(" " + " ".join(folded(other)) + " " in flat for other in others):
            shown = shown - {place}
    return shown


def record(identifier: str, caption: str, title: str = "", everywhere: frozenset | set = frozenset(), family: str | None = None) -> list[Name]:
    """The precise places the record of a photo names, whole: those of its caption, neighbours included;
    when the caption only says the destination (a photo of the old catalogue has none of its own: "Sintra
    (Portugal)."), those of its Commons title ("Castelo dos Mouros in Sintra" for "sintra-mouros-remparts"). Its
    identifier is in lower case: it cannot tell a place ("mouros") from a thing ("interieur", "viaduc")."""
    prefix, _, rest = identifier.partition("-")
    own = words((rest if prefix == family else identifier).replace("-", " "))
    title = readable(title)
    known = own | words(title)
    # A neighbour the caption names is kept here: a photo "de Porto près de la station des Guindais" stands at the
    # Guindais, and a place too many only ever refuses a photo (what it shows, `pictured`, leaves neighbours out).
    found = [name for name, _, _ in names(subject(caption), everywhere, sentence=True, known=known)]
    if found or not words(caption) <= set(everywhere) | GENERIC:
        return list(dict.fromkeys(found))
    return list(dict.fromkeys(name for name, _, _ in names(subject(title), everywhere)))


def brands(said: set[str]) -> set[str]:
    """The trains these words name, by any word of their name ("alfa" in "train-alfa-220")."""
    return {brand for brand, pieces in BRANDS.items() if pieces & said}


def brand_clash(text: str, shown: set[str]) -> bool:
    """The fact names a train the photo does not show, while the photo shows another one ("Intercidades" over an Alfa
    Pendular)."""
    wanted, seen = brands(words(text)), brands(shown)
    return bool(wanted and seen and not wanted & seen)


def label_clash(label: str, shown: set[str]) -> bool:
    """A label names a train the photo is not, while the photo shows a train: "Alfa Pendular ou Intercidades" over the
    inside of an Alfa Pendular says the photo could be either."""
    wanted, seen = brands(words(label)), brands(shown)
    return bool(seen and wanted - seen)


def fits(reading: Reading, shown: set[str], told: set[str], recorded_names: list[Name]) -> int:
    """How well a photo is a photo of what a fact is about, 0 when it is not. 3: it shows the first place the fact
    names, wherever the record says so (its identifier included; a quarter shows its town when the fact lists no
    other place: Belém is no photo of "de l'aéroport de Lisbonne à Baixa-Chiado"). 2: its caption or title
    shows another place the fact lists. 1: it shows a place the fact only situates the first one in, and its record
    names no other place ("le Grand Bouddha du Tōdai-ji, à Nara" over deer of Nara, never over the tower of Belém for
    "le château São Jorge, à Lisbonne"); or the fact says, without a capital, the very place the record names ("les
    tombeaux saadiens")."""
    # A quarter shows its town only when the record names no other town ("l'église de Graça, à Faro" is no photo of Lisbon).
    quarters = set(INSIDE) | set(INSIDE.values())
    inside = not reading.listed and all(set(name) <= quarters for name in recorded_names)
    if reading.first and shows(reading.first, widened(shown) if inside else shown):
        return 3
    if any(shows(name, told) for name in reading.listed):
        return 2
    # A place the fact only situates itself in: the photo's own record must name it, and nothing else (a record that
    # names nothing is no proof: "…TO BANGKOK" in a title is where a train goes, not where the photo is).
    alone = bool(recorded_names) and all(any(same(name, other) for other in reading.all) for name in recorded_names)
    if alone and any(shows(name, shown) for name in reading.situating):
        return 1
    # A word of four letters and more that the fact says without a capital, and that a name of the record holds:
    # "les tombeaux saadiens" over "Maroc Marrakech Saadiens Luc Viatour" (a name of the record may carry its author).
    capitalised = {piece for name in reading.all for piece in name}
    # Only a word that names a place: "Grand" or "Palais" said by the fact is no echo of the record's "Grand Palais".
    if any(len(piece) >= 4 and piece in reading.said and piece not in capitalised and piece not in UNNAMED
           for name in recorded_names for piece in name):
        return 1
    return 0


def ways(words_said: set[str] | list[str]) -> set[str]:
    """By what one travels in these words: "rail", "metro", "tram", "road", "water"."""
    return {way for way, names_ in WAYS.items() if names_ & set(words_said)}


def ride(described: set[str], text: str = "") -> bool:
    """A photo of a means of transport, by the words of its caption, title and identifier; of the one the text opens
    on when it names one ("Le bus 205 pour…" does not go over a shinkansen)."""
    # The means a line opens on; else the one it names further on ("la traversée du Tage en ferry": a ferry, not a tram).
    wanted = wanted_ways(text)
    if not wanted and OTHER_MEANS & set(folded(text)):
        return False   # "Hanoï → Hô-Chi-Minh-Ville en avion": no photo of a train
    return bool(ways(described) & wanted) if wanted else bool(RIDES & described)


OTHER_MEANS = frozenset("avion avions vol vols taxi taxis voiture voitures velo pied".split())


def on_the_way(recorded_names: list[Name], reading: Reading) -> bool:
    """The record of a ride names one of the places of a journey, whole, or names no place: it does not stand elsewhere."""
    return not recorded_names or any(within(name, other) for name in recorded_names for other in reading.all)


def within(name: Name, other: Name) -> bool:
    """`name` is `other`, or a place of it whose name holds it whole ("Mérida Teya", the station of Mérida)."""
    return any(set(b) <= set(a) for a in variants(name) for b in variants(other))
