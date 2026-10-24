"""Liens partenaires des guides : choix selon le contenu, placement, mention légale.

Tout est calculé à la génération à partir des données du guide (destination, pays, texte),
sans liste de villes. Un partenaire sans identifiant reste inactif. Aucun script ni pixel.
"""
from __future__ import annotations

from dataclasses import dataclass
import html
import json
from pathlib import Path
import re
from string import Formatter
import unicodedata
from urllib.parse import quote, urlparse

import stay22

DISCLOSURE = 'Lien partenaire : nous touchons une commission, sans surcoût pour vous.'
CATEGORIES = ('hotels', 'activites', 'transport', 'assurance')
ENGINES = ('stay22', 'template')
REL = 'sponsored nofollow noopener'
MAX_LINKS = 3
MAX_HOTEL_PLACES = 2
PLACEHOLDERS = {'id', 'campaign', 'query', 'place_slug', 'location_path'}
# Page de lieu GetYourGuide (« lisbonne-l42 ») lue dans getyourguide-locations.json.
LOCATION_PATTERN = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*-l[0-9]+')
ID_PATTERN = re.compile(r'[A-Za-z0-9._~-]{1,80}')
PARTNER_KEYS = {'key', 'name', 'category', 'engine', 'enabled', 'id', 'template', 'domains', 'signup', 'commission'}
CONFIG_KEYS = {'schema_version', 'max_links_per_guide', 'partners'}

# Expressions cherchées dans le texte normalisé du guide (minuscules, sans accents).
# « billet » et « réserver » servent aussi aux trains et aux trams : ils ne signalent pas une visite.
ACTIVITY_WORDS = (r'\b(entrees?|visites?|excursions?|croisieres?|musees?|palais|chateaux?|monuments?|cathedrales?|'
                  r'basiliques?|monasteres?|coupe-file|degustations?)\b')
TRANSPORT_WORDS = r'\b(trains?|gares?|tgv|intercites|ferrys?|ferries|bus|autocars?|trajets?)\b'
SIGNALS = {'activites': (ACTIVITY_WORDS, 3), 'transport': (TRANSPORT_WORDS, 4)}
HOTEL_ANCHORS = (r'\b(dormir|heberg\w*|logements?|quartiers?|hotels?)\b', r'\barriv\w*')
SLEEP_GUIDE_ANCHOR = r'\b(compar\w*|en bref|resume)\b'
SLEEP_CATEGORIES = {'quartiers', 'ou dormir', 'hebergement'}
NO_ACTIVITY_CATEGORIES = {'transports', 'preparer'}
INSURANCE_CATEGORIES = {'preparer', 'pratique', 'conseils', 'budget'}

COPY = {
    'hotels': ('Où dormir', 'Votre point de chute : {places}',
               'Hôtels, appartements et maisons d’hôtes libres à vos dates, avec le prix total affiché avant de réserver.',
               'Voir les hébergements · {place}'),
    'activites': ('Billets et visites', 'Réservez les visites à l’avance',
                  'Les créneaux des sites les plus demandés partent vite : billets d’entrée, visites guidées et excursions.',
                  'Voir les billets et visites · {place}'),
    'transport': ('Le trajet', 'Réservez le trajet',
                  'Horaires et prix des trains et des bus côte à côte, puis billet électronique sur le téléphone.',
                  'Comparer les trains et les bus'),
    'assurance': ('Avant de partir', 'L’assurance voyage',
                  'Frais médicaux, annulation, bagages : comparez les garanties avant le départ.',
                  'Comparer les assurances voyage'),
}

CSS = '''<style id="partner-style">.partner-box{margin:30px 0;padding:22px 26px;border:1px solid #ccd6e9;border-radius:12px;background:#f4f6fc}.partner-box .partner-kicker{font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:#214fe6}.partner-box .partner-title{font-size:21px;font-weight:700;line-height:1.3;margin:8px 0 8px}.partner-box p{line-height:1.65;margin:0 0 10px}.partner-box .partner-links{display:flex;flex-wrap:wrap;gap:8px 22px}.partner-box .partner-cta{display:inline-block;font-size:15px;font-weight:700;line-height:1.5;color:#214fe6;text-decoration:underline;text-underline-offset:4px}.partner-box .partner-disclosure{font-size:12px;color:#596575;margin:10px 0 0}.partner-cta[aria-disabled]{cursor:default}.partner-preview-banner{padding:14px 18px;border:1px solid #214fe6;border-radius:8px;background:#eef2ff;color:#183580;font-size:13px;margin:16px 0}@media(max-width:600px){.partner-box{padding:19px 18px}.partner-box .partner-title{font-size:19px}}</style>'''


@dataclass(frozen=True)
class Place:
    name: str
    address: str
    lat: float | None = None
    lng: float | None = None
    key: str = ''


@dataclass(frozen=True)
class Link:
    url: str
    label: str


@dataclass(frozen=True)
class Box:
    category: str
    anchor: int
    places: tuple
    links: tuple


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize('NFKD', str(text))
    plain = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^\x00-\x7f]', ' ', plain.lower())).strip()


def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', normalize(text)).strip('-')


# --- configuration -----------------------------------------------------------------------

def template_fields(template: str) -> set:
    return {field for _, field, _, _ in Formatter().parse(template) if field is not None}


def validate_partner(partner: dict) -> None:
    key = partner.get('key') if isinstance(partner, dict) else None
    extra = {'provider'} if isinstance(partner, dict) and partner.get('engine') == 'stay22' else set()
    if not isinstance(partner, dict) or set(partner) != PARTNER_KEYS | extra:
        raise ValueError(f'Partenaire {key} : champs incomplets ou non autorisés.')
    if partner['category'] not in CATEGORIES or partner['engine'] not in ENGINES or type(partner['enabled']) is not bool:
        raise ValueError(f'Partenaire {key} : catégorie, moteur ou activation invalide.')
    if not all(isinstance(partner[name], str) for name in ('key', 'name', 'id', 'template', 'signup', 'commission')):
        raise ValueError(f'Partenaire {key} : texte attendu.')
    if not re.fullmatch(r'[a-z0-9_]{2,40}', partner['key']) or not partner['signup'].startswith('https://'):
        raise ValueError(f'Partenaire {key} : clé ou lien d’inscription invalide.')
    domains = partner['domains']
    if not isinstance(domains, list) or not domains or not all(isinstance(d, str) and re.fullmatch(r'[a-z0-9.-]+\.[a-z]{2,}', d) for d in domains):
        raise ValueError(f'Partenaire {key} : domaines autorisés manquants.')
    if partner['id'] and not ID_PATTERN.fullmatch(partner['id']):
        raise ValueError(f'Partenaire {key} : identifiant invalide (lettres, chiffres, . _ ~ - uniquement).')
    if partner['engine'] == 'stay22':
        if partner['provider'] not in stay22.PROVIDERS or partner['template'] or partner['id']:
            raise ValueError(f'Partenaire {key} : Stay22 se règle dans stay22.json.')
    elif partner['template']:
        validate_template(partner)


def validate_template(partner: dict) -> None:
    fields = template_fields(partner['template'])
    if 'id' not in fields or not fields <= PLACEHOLDERS:
        raise ValueError(f'Partenaire {partner["key"]} : le gabarit doit contenir {{id}} et seulement {sorted(PLACEHOLDERS)}.')
    sample = partner['template'].format(id='x', campaign='x', query='x', place_slug='x', location_path='x-l1')
    parsed = urlparse(sample)
    if parsed.scheme != 'https' or parsed.netloc not in partner['domains']:
        raise ValueError(f'Partenaire {partner["key"]} : gabarit hors https ou hors domaines autorisés.')


def validate_config(config: dict) -> dict:
    if not isinstance(config, dict) or set(config) != CONFIG_KEYS or config['schema_version'] != 1:
        raise ValueError('Partenaires : configuration incomplète ou version invalide.')
    limit = config['max_links_per_guide']
    if type(limit) is not int or not 1 <= limit <= MAX_LINKS:
        raise ValueError(f'Partenaires : 1 à {MAX_LINKS} liens par guide.')
    partners = config['partners']
    if not isinstance(partners, list) or not partners:
        raise ValueError('Partenaires : liste vide.')
    for partner in partners:
        validate_partner(partner)
    if len({p['key'] for p in partners}) != len(partners):
        raise ValueError('Partenaires : clé en double.')
    return config


def load_config(path) -> dict:
    return validate_config(json.loads(Path(path).read_text(encoding='utf-8')))


def load_countries(path) -> dict:
    """Référentiel facultatif des pays (destinations.json) : nom et continent."""
    path = Path(path)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    return {c['id']: c for c in data.get('countries', []) if isinstance(c, dict) and 'id' in c}


# --- lecture du guide --------------------------------------------------------------------

def section_text(section: dict) -> str:
    parts = [section.get('title', ''), *section.get('paragraphs', []), *section.get('bullets', []), section.get('tip', '')]
    return normalize(' '.join(str(p) for p in parts))


def count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text))


def country_of(article: dict, countries: dict) -> tuple:
    slug = article.get('country', 'portugal')
    entry = countries.get(slug, {})
    name = entry.get('name') or ' '.join(w.capitalize() for w in slug.split('-'))
    return name, article.get('continent') or entry.get('continent')


def place_key(name: str, article: dict) -> str:
    return slugify(name) + '|' + article.get('country', 'portugal')


def places_for(article: dict, catalogue: list, country_name: str) -> tuple:
    destination = str(article['destination'])
    names = [destination]
    if normalize(destination) == normalize(country_name):
        title = normalize(article.get('title', ''))
        same = {str(o['destination']) for o in catalogue if o.get('country', 'portugal') == article.get('country', 'portugal')}
        found = sorted((title.find(normalize(d)), d) for d in same
                       if normalize(d) != normalize(country_name) and re.search(r'\b' + re.escape(normalize(d)) + r'\b', title))
        names = [d for _, d in found][:MAX_HOTEL_PLACES] or names
    geo = article.get('geo') if isinstance(article.get('geo'), dict) else {}
    return tuple(Place(name, name if normalize(name) == normalize(country_name) else f'{name}, {country_name}',
                       geo.get('lat') if name == destination else None, geo.get('lng') if name == destination else None,
                       place_key(name, article))
                 for name in names)


# Noms propres d'un titre (« Séville », « Pinhão ») : premier mot, sigles et noms élidés exclus.
TITLE_NAME = re.compile(r"(?<![\w’'])([A-ZÀ-Ý][a-zà-ÿ]{2,}(?:[- ][A-ZÀ-Ý][a-zà-ÿ]+)*)")
MAX_TITLE_PLACES = 3


def title_places(article: dict, country_name: str) -> tuple:
    """Villes citées dans le titre, en repli quand la destination (une région) n'a pas de page fiable."""
    taken = {normalize(article['destination']), normalize(country_name)}
    names = [m.group(1) for m in TITLE_NAME.finditer(article.get('title', '')) if m.start() > 0]
    names = [n for n in dict.fromkeys(names) if normalize(n) not in taken][:MAX_TITLE_PLACES]
    return tuple(Place(n, f'{n}, {country_name}', key=place_key(n, article)) for n in names)


def wants(category: str, article: dict, texts: list, continent: str | None) -> bool:
    if category == 'hotels':
        return True
    if category == 'assurance':
        return (continent not in (None, 'europe')) or normalize(article.get('category', '')) in INSURANCE_CATEGORIES
    if category == 'activites' and normalize(article.get('category', '')) in NO_ACTIVITY_CATEGORIES:
        return False
    pattern, minimum = SIGNALS[category]
    return count(pattern, ' '.join(texts)) >= minimum


def anchor_for(category: str, sections: list, texts: list, guide_category: str = '') -> int:
    last = max(len(sections) - 1, 0)
    if category == 'assurance' or not sections:
        return last
    titles = [normalize(s.get('title', '')) for s in sections]
    if category == 'hotels':
        # Un guide « où dormir » parle d'hébergement partout : le lien vient après le comparatif.
        patterns = (SLEEP_GUIDE_ANCHOR,) if normalize(guide_category) in SLEEP_CATEGORIES else HOTEL_ANCHORS
        for pattern in patterns:
            hit = next((i for i, title in enumerate(titles) if re.search(pattern, title)), None)
            if hit is not None:
                return hit
        return last
    pattern = SIGNALS[category][0]
    hit = next((i for i, title in enumerate(titles) if re.search(pattern, title)), None)
    if hit is not None:
        return hit
    scores = [count(pattern, text) for text in texts]
    return scores.index(max(scores)) if max(scores) else last


# --- le site -----------------------------------------------------------------------------

class Site:
    def __init__(self, config: dict, stay22_config: dict, *, public: bool, origin: str, preview: bool = False,
                 countries: dict | None = None, locations: dict | None = None):
        self.config = validate_config(config)
        self.stay22 = stay22.validate_config(stay22_config)
        if preview and public:
            raise ValueError('Partenaires : un aperçu ne peut pas être public.')
        self.preview = preview
        self.live = public and origin == stay22.ORIGIN
        self.countries = countries or {}
        self.locations = locations or {}

    @classmethod
    def load(cls, root, *, public: bool, origin: str, preview: bool = False, stay22_path=None, path=None) -> 'Site':
        import gyg_locations  # le résolveur importe ce module : import local pour éviter la boucle
        root = Path(root)
        return cls(load_config(path or root / 'affiliates.json'), stay22.load_config(stay22_path or root / 'stay22.json'),
                   public=public, origin=origin, preview=preview, countries=load_countries(root / 'destinations.json'),
                   locations=gyg_locations.paths(root / gyg_locations.CACHE_NAME))

    def is_partner_active(self, partner: dict) -> bool:
        ready = partner['engine'] == 'stay22' or bool(partner['id'] and partner['template'])
        if self.preview:
            return partner['enabled'] and ready
        if not (self.live and partner['enabled'] and ready):
            return False
        return partner['engine'] != 'stay22' or stay22.is_active(self.stay22, public=True, origin=stay22.ORIGIN)

    def active_partners(self) -> tuple:
        return tuple(p for p in self.config['partners'] if self.is_partner_active(p))

    def partners_for(self, category: str) -> tuple:
        return tuple(p for p in self.active_partners() if p['category'] == category)

    def url(self, partner: dict, place: Place, campaign: str) -> str | None:
        """Lien du partenaire pour ce lieu, ou None s'il n'a pas de page fiable pour ce lieu."""
        if partner['engine'] == 'stay22':
            return stay22.allez_url(self.stay22, partner['provider'], campaign=campaign, address=place.address,
                                    lat=place.lat, lng=place.lng)
        location = ''
        if 'location_path' in template_fields(partner['template']):
            location = self.locations.get(place.key) or ''
            if not LOCATION_PATTERN.fullmatch(location):
                return None
        url = partner['template'].format(id=quote(partner['id'], safe=''), campaign=quote(campaign, safe=''),
                                         query=quote(place.name, safe=''), place_slug=slugify(place.name),
                                         location_path=location)
        if urlparse(url).netloc not in partner['domains']:
            raise ValueError(f'Partenaire {partner["key"]} : lien hors domaines autorisés.')
        return url

    def plan(self, article: dict, catalogue: list) -> tuple:
        sections = article.get('sections', [])
        texts = [section_text(s) for s in sections]
        country_name, continent = country_of(article, self.countries)
        places = places_for(article, catalogue, country_name)
        fallback = title_places(article, country_name)
        campaign = stay22.campaign_for(self.stay22, article['slug'])
        budget, boxes = self.config['max_links_per_guide'], []
        for category in CATEGORIES:
            if not budget or not wants(category, article, texts, continent):
                continue
            candidates = places + fallback if category == 'activites' else places
            box = self.box_for(category, candidates, campaign, budget, anchor_for(category, sections, texts, article.get('category', '')))
            if box:
                boxes.append(box)
                budget -= len(box.links)
        return tuple(boxes)

    def box_for(self, category: str, places: tuple, campaign: str, budget: int, anchor: int) -> Box | None:
        """Premier partenaire actif de la catégorie qui a un lien fiable pour au moins un lieu."""
        limit = min(budget, MAX_HOTEL_PLACES) if category == 'hotels' else 1
        for partner in self.partners_for(category):
            pairs = [(p, self.url(partner, p, campaign)) for p in places]
            pairs = [(p, url) for p, url in pairs if url][:limit]
            if pairs:
                label = COPY[category][3]
                return Box(category, anchor, tuple(p for p, _ in pairs),
                           tuple(Link(url, label.format(place=p.name)) for p, url in pairs))
        return None

    def render(self, box: Box) -> str:
        kicker, title, text, _ = COPY[box.category]
        title = title.format(places=' ou '.join(p.name for p in box.places))
        if self.preview:
            ctas = ''.join(f'<span class="partner-cta" role="link" aria-disabled="true">{html.escape(link.label)} →</span>'
                           for link in box.links)
        else:
            ctas = ''.join(f'<a class="partner-cta" href="{html.escape(link.url, quote=True)}" target="_blank" '
                           f'rel="{REL}">{html.escape(link.label)} →</a>' for link in box.links)
        return (f'<aside class="partner-box partner-{box.category}" aria-label="{html.escape(kicker)} : lien partenaire">'
                f'<span class="partner-kicker">{html.escape(kicker)}</span><p class="partner-title">{html.escape(title)}</p>'
                f'<p>{html.escape(text)}</p><div class="partner-links">{ctas}</div>'
                f'<p class="partner-disclosure">{DISCLOSURE}</p></aside>')

    def weave(self, article: dict, sections_html: list, catalogue: list) -> str:
        """Insère chaque bloc partenaire juste après la section où il sert."""
        after = {}
        for box in self.plan(article, catalogue):
            after.setdefault(box.anchor, []).append(self.render(box))
        return ''.join(chunk + ''.join(after.get(i, ())) for i, chunk in enumerate(sections_html))

    def note(self, body: str) -> str:
        if 'class="partner-box' in body:
            return 'Les liens partenaires de ce guide sont signalés près de chaque lien.'
        if self.active_partners():
            return 'Aucun lien partenaire dans ce guide.'
        return 'Aucun lien de réservation rémunéré n’est activé dans cette édition.'

    def css(self, content: str) -> str:
        return CSS if self.preview or 'class="partner-box' in content else ''

    @property
    def preview_banner(self) -> str:
        return ('<p class="partner-preview-banner">Aperçu local des liens partenaires : liens désactivés, '
                'aucune admission ni redirection vérifiée par cet aperçu.</p>') if self.preview else ''

    def transparency(self) -> str:
        active = self.active_partners()
        if not active:
            return ('<h2>Dans cette édition</h2><p>Aucun programme d’affiliation ni publicité n’est activé. Les liens vers les '
                    'transports, monuments et organismes touristiques sont des liens informatifs ordinaires. Aucune commission '
                    'n’est annoncée ou perçue par le site grâce à ces liens.</p><h2>Si l’affiliation est activée</h2><p>Chaque '
                    f'bloc de liens rémunérés portera la mention « {DISCLOSURE} » et les liens l’attribut rel="sponsored". '
                    'Le prix et les conditions restent à vérifier chez le vendeur.</p><p>Les relations commerciales, produits '
                    'offerts et placements seront identifiés. La présence d’une rémunération ne sera pas présentée comme une '
                    'preuve qu’une offre convient à tous les voyageurs.</p>')
        names = ', '.join(html.escape(p['name']) for p in active)
        return ('<h2>Les liens partenaires</h2><p>Certains guides contiennent jusqu’à trois liens partenaires, placés là où ils '
                'servent : où dormir, billets et visites, trajet ou assurance. Chaque bloc porte la mention '
                f'« {DISCLOSURE} » Les liens portent l’attribut rel="sponsored nofollow".</p><p>Partenaires actifs : {names}.'
                '</p><p>Nous n’avons pas testé les établissements ni les prestations listés : un lien rémunéré ne vaut pas '
                'recommandation personnelle. Tarifs, disponibilités et conditions restent à vérifier chez le vendeur. Aucun '
                'revenu n’est garanti.</p><h2>Publicité et indépendance</h2><p>Aucune publicité d’affichage n’est activée. '
                'Les liens vers les transports, monuments et organismes touristiques cités en sources restent des liens '
                'informatifs ordinaires. Le choix des sujets et des conseils ne dépend pas des partenaires.</p>')

    def privacy(self) -> str:
        if not (self.preview or self.active_partners()):
            return ''
        return ('<h2>Liens partenaires</h2><p>Les liens signalés « Lien partenaire » sont des liens HTML ordinaires. Aucun '
                'script, iframe ou pixel de partenaire n’est chargé à l’ouverture d’une page.</p><p>Si vous ouvrez un de ces '
                'liens, votre navigateur contacte le partenaire (par exemple Stay22, puis le site de réservation). Ces services '
                'peuvent recevoir des données techniques comme votre adresse IP et votre navigateur, et poser leurs propres '
                'cookies pour attribuer une éventuelle réservation, selon leurs politiques de confidentialité. Accepter la '
                'mesure d’audience du blog n’active aucun script d’affiliation.</p>')
