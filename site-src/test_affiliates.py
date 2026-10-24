import copy
from html.parser import HTMLParser
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

import affiliates
import stay22

ROOT = Path(__file__).resolve().parent


class Tags(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.tags = []; self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def links(source):
    return [attrs for tag, attrs in Tags(source).tags if tag == 'a' and 'partner-cta' in attrs.get('class', '')]


def section(title, *paragraphs):
    return {'id': title.lower().replace(' ', '-')[:20], 'title': title, 'paragraphs': list(paragraphs)}


def article(slug, destination, sections, *, country='portugal', category='Itinéraires', title=None, **extra):
    return {'slug': slug, 'title': title or destination + ' en 3 jours', 'destination': destination,
            'country': country, 'category': category, 'sections': sections, **extra}


CITY = article('lisbonne-3-jours', 'Lisbonne', [
    section('Avant tout la carte', 'Le métro et le tram coûtent 1,85 €.'),
    section('Jour 1 le château', 'Billets du château à réserver, entrée 15 €, visite guidée possible.',
            'Le musée et le monastère : billets en ligne, réservation conseillée.'),
    section('Où dormir', 'Baixa ou Alfama : les quartiers les plus pratiques.'),
    section('Le budget', 'Comptez 60 € de visites.'),
])
TRAIN = article('lisbonne-porto-train', 'Portugal', [
    section('Alfa Pendular ou Intercidades', 'Le train met 2 h 49, billet 25 €.'),
    section('Les bonnes gares', 'La gare de Campanhã, la gare de São Bento, le train régional.'),
    section('Bagages à bord', 'Le train accepte deux valises.'),
], title='Lisbonne–Porto en train : prix et durées', category='Transports')
CATALOGUE = [CITY, TRAIN, article('porto-3-jours', 'Porto', []), article('seville', 'Séville', [], country='espagne')]


def stay22_config(**gates):
    config = stay22.load_config(ROOT / 'stay22.json')
    return {**config, 'enabled': True, 'hosting_verified': True, 'links_verified': True, **gates}


def active_site(config=None, **gates):
    return affiliates.Site(config or affiliates.load_config(ROOT / 'affiliates.json'), stay22_config(**gates),
                           public=True, origin=stay22.ORIGIN)


def stay22_only():
    config = affiliates.load_config(ROOT / 'affiliates.json')
    for partner in config['partners']:
        if partner['engine'] == 'template':
            partner['enabled'] = False
    return affiliates.validate_config(config)


def woven(site, art, catalogue=CATALOGUE):
    return site.weave(art, ['<section id="s%d">x</section>' % i for i in range(len(art['sections']))], catalogue)


def with_template_partners(config, **values):
    config = copy.deepcopy(config)
    for partner in config['partners']:
        if partner['engine'] == 'template':
            partner.update({'enabled': True, 'id': 'ID123',
                            'template': partner['template'] or 'https://' + partner['domains'][0] + '/?a={id}', **values})
    return affiliates.validate_config(config)


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.config = affiliates.load_config(ROOT / 'affiliates.json')

    def test_real_config_prepares_required_partners_and_categories(self):
        keys = {p['key'] for p in self.config['partners']}
        self.assertTrue({'stay22_hotels', 'getyourguide', 'civitatis', 'trainline', 'omio', 'heymondo', 'chapka'} <= keys)
        self.assertEqual({p['category'] for p in self.config['partners']}, set(affiliates.CATEGORIES))
        self.assertLessEqual(self.config['max_links_per_guide'], 3)
        for partner in self.config['partners']:
            self.assertTrue(partner['signup'].startswith('https://'), partner['key'])
            if partner['engine'] == 'template' and partner['id']:
                self.assertRegex(partner['id'], affiliates.ID_PATTERN)
        gyg = next(p for p in self.config['partners'] if p['key'] == 'getyourguide')
        self.assertEqual((gyg['enabled'], gyg['id']), (True, 'HKEWKYM'))

    def test_partner_without_id_stays_inactive_and_breaks_nothing(self):
        site = active_site(with_template_partners(self.config, id=''))
        self.assertEqual({p['key'] for p in site.active_partners()} & {'getyourguide', 'trainline', 'heymondo'}, set())
        self.assertIn('partner-cta', woven(site, CITY))

    def test_getyourguide_link_carries_partner_id_and_guide_campaign(self):
        site = active_site(enabled=False, hosting_verified=False)
        found = links(woven(site, CITY))
        self.assertEqual(len(found), 1)
        url = urlparse(found[0]['href'])
        self.assertEqual(url.netloc + url.path, 'www.getyourguide.com/fr-fr/s/')
        self.assertEqual(parse_qs(url.query), {'q': ['Lisbonne'], 'partner_id': ['HKEWKYM'], 'cmp': ['vsd_lisbonne_3_jours']})
        self.assertNotIn('partner-hotels', woven(site, CITY))

    def test_partner_with_id_but_disabled_flag_stays_inactive(self):
        config = copy.deepcopy(self.config)
        next(p for p in config['partners'] if p['key'] == 'getyourguide').update(enabled=False, id='ABC123')
        self.assertNotIn('getyourguide', {p['key'] for p in active_site(affiliates.validate_config(config)).active_partners()})

    def test_rejects_unsafe_or_incomplete_partner_entries(self):
        gyg = next(i for i, p in enumerate(self.config['partners']) if p['key'] == 'getyourguide')
        patches = [{'category': 'casino'}, {'engine': 'script'}, {'id': 'a"><script>'}, {'id': 'x y'},
                   {'template': 'http://www.getyourguide.fr/?partner_id={id}'}, {'template': 'https://evil.test/?p={id}'},
                   {'template': 'https://www.getyourguide.fr/?p={secret}'}, {'enabled': 'yes'}, {'domains': []},
                   {'unknown': 1}]
        for patch in patches:
            config = copy.deepcopy(self.config)
            config['partners'][gyg].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                affiliates.validate_config(config)
        for patch in ({'max_links_per_guide': 4}, {'max_links_per_guide': 0}, {'schema_version': 2}, {'extra': True}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                affiliates.validate_config({**self.config, **patch})
        duplicate = copy.deepcopy(self.config)
        duplicate['partners'].append(copy.deepcopy(duplicate['partners'][0]))
        with self.assertRaises(ValueError):
            affiliates.validate_config(duplicate)


class SelectionTest(unittest.TestCase):
    def test_city_guide_gets_disclosed_hotel_and_activity_links_with_guide_campaign(self):
        html = woven(active_site(stay22_only()), CITY)
        found = links(html)
        self.assertTrue(1 <= len(found) <= 3)
        urls = [urlparse(a['href']) for a in found]
        hotel = next(u for u in urls if u.path == '/allez/roam')
        self.assertEqual(hotel.scheme + '://' + hotel.netloc, 'https://www.stay22.com')
        query = parse_qs(hotel.query)
        self.assertEqual(query['aid'], ['voyagesansdetourfr'])
        self.assertEqual(query['address'], ['Lisbonne, Portugal'])
        self.assertEqual(query['campaign'], ['vsd_lisbonne_3_jours'])
        self.assertIn('/allez/getyourguide', [u.path for u in urls])
        for attrs in found:
            self.assertEqual(set(attrs['rel'].split()), {'sponsored', 'nofollow', 'noopener'})
            self.assertEqual(attrs['target'], '_blank')
        self.assertEqual(html.count(affiliates.DISCLOSURE), html.count('class="partner-box'))

    def test_hotel_box_sits_after_the_where_to_sleep_section(self):
        html = woven(active_site(), CITY)
        self.assertLess(html.index('<section id="s2">'), html.index('partner-hotels'))
        self.assertLess(html.index('partner-hotels'), html.index('<section id="s3">'))

    def test_activity_box_follows_the_section_about_tickets(self):
        html = woven(active_site(), CITY)
        self.assertLess(html.index('<section id="s1">'), html.index('partner-activites'))
        self.assertLess(html.index('partner-activites'), html.index('<section id="s2">'))

    def test_transport_guide_gets_no_activity_box_even_when_it_mentions_tickets(self):
        tickets = {**TRAIN, 'sections': TRAIN['sections'] + [section('Visites', 'Musée, palais, château, visite guidée.')]}
        self.assertNotIn('partner-activites', woven(active_site(), tickets))

    def test_where_to_sleep_guide_places_hotel_link_after_its_comparison(self):
        sleep = article('ou-dormir-x', 'Lisbonne', [section('Baixa', 'Calme la nuit.'), section('Le comparatif', 'Tableau.'),
                                                    section('Avant de payer', 'Taxe.')], category='Quartiers')
        html = woven(active_site(), sleep)
        self.assertLess(html.index('<section id="s1">'), html.index('partner-hotels'))
        self.assertLess(html.index('partner-hotels'), html.index('<section id="s2">'))

    def test_country_level_guide_uses_cities_named_in_title_without_city_list(self):
        found = links(woven(active_site(), TRAIN))
        addresses = [parse_qs(urlparse(a['href']).query).get('address') for a in found]
        self.assertIn(['Lisbonne, Portugal'], addresses)
        self.assertIn(['Porto, Portugal'], addresses)

    def test_new_country_and_coordinates_need_no_code_change(self):
        tokyo = article('tokyo-5-jours', 'Tokyo', [section('Où dormir à Tokyo', 'Shinjuku ou Asakusa.')],
                        country='japon', geo={'lat': 35.6895, 'lng': 139.6917})
        query = parse_qs(urlparse(links(woven(active_site(), tokyo, [tokyo]))[0]['href']).query)
        self.assertEqual((query['lat'], query['lng']), (['35.6895'], ['139.6917']))
        self.assertNotIn('address', query)
        kyoto = article('kyoto', 'Kyoto', [section('Le temple', 'Rien.')], country='japon')
        query = parse_qs(urlparse(links(woven(active_site(), kyoto, [kyoto]))[0]['href']).query)
        self.assertEqual(query['address'], ['Kyoto, Japon'])

    def test_never_more_than_three_links_even_with_every_partner_active(self):
        site = active_site(with_template_partners(affiliates.load_config(ROOT / 'affiliates.json')))
        for art in (CITY, TRAIN, {**CITY, 'country': 'japon', 'continent': 'asie'}):
            with self.subTest(slug=art['slug']):
                html = woven(site, art)
                self.assertTrue(1 <= len(links(html)) <= 3)
                self.assertEqual(html.count(affiliates.DISCLOSURE), html.count('class="partner-box'))

    def test_transport_partner_is_chosen_for_train_guide_when_active(self):
        config = affiliates.load_config(ROOT / 'affiliates.json')
        next(p for p in config['partners'] if p['key'] == 'trainline').update(enabled=True, id='1100l12345')
        found = links(woven(active_site(affiliates.validate_config(config)), TRAIN))
        trainline_url = next(a['href'] for a in found if urlparse(a['href']).netloc == 'prf.hn')
        self.assertIn('camref:1100l12345', trainline_url)
        self.assertIn('pubref:vsd_lisbonne_porto_train', trainline_url)

    def test_no_link_and_no_disclosure_when_everything_is_inactive(self):
        html = woven(active_site(stay22_only(), enabled=False, hosting_verified=False), CITY)
        self.assertEqual(links(html), [])
        self.assertNotIn(affiliates.DISCLOSURE, html)
        self.assertEqual(html, ''.join('<section id="s%d">x</section>' % i for i in range(4)))

    def test_local_or_foreign_origin_build_never_emits_live_links(self):
        for public, origin in ((False, stay22.ORIGIN), (True, 'https://other.test')):
            site = affiliates.Site(affiliates.load_config(ROOT / 'affiliates.json'), stay22_config(), public=public, origin=origin)
            self.assertEqual(links(woven(site, CITY)), [])

    def test_preview_shows_disabled_boxes_with_disclosure(self):
        site = affiliates.Site(affiliates.load_config(ROOT / 'affiliates.json'), stay22_config(enabled=False),
                               public=False, origin=stay22.PREVIEW_ORIGIN, preview=True)
        html = woven(site, CITY)
        self.assertNotIn('href=', html)
        self.assertIn('aria-disabled="true"', html)
        self.assertIn(affiliates.DISCLOSURE, html)

    def test_escapes_place_names_in_markup(self):
        evil = article('x', '<img src=x onerror=1>', [section('Où dormir', 'a')])
        self.assertNotIn('<img', woven(active_site(), evil, [evil]))

    def test_transparency_lists_active_partners_and_the_exact_disclosure(self):
        text = active_site().transparency()
        self.assertIn(affiliates.DISCLOSURE, text)
        self.assertIn('Stay22', text)
        self.assertIn('sponsored', text)
        self.assertIn('Aucun programme d’affiliation ni publicité n’est activé', active_site(stay22_only(), enabled=False).transparency())


if __name__ == '__main__':
    unittest.main()
