import copy
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
import affiliates
import editorial_queue
import stay22

ROOT = Path(__file__).resolve().parent


class Tags(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.tags = []; self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class Stay22Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='vsd-stay22-tests-')
        cls.work = Path(cls.tmp.name)
        # Validate production configuration as it stands, then isolate fixtures.
        # A verified account or an authorized activation must not invalidate CI.
        cls.real_config = stay22.load_config(ROOT / 'stay22.json')
        cls.config = copy.deepcopy(cls.real_config)
        cls.config.update(enabled=False, hosting_verified=False, links_verified=False)
        # Ces contrôles portent sur Stay22 seul : les partenaires à gabarit sont éteints.
        partners = affiliates.load_config(ROOT / 'affiliates.json')
        for partner in partners['partners']:
            if partner['engine'] == 'template':
                partner['enabled'] = False
        cls.stay22_only = cls.work / 'affiliates-stay22-only.json'
        cls.stay22_only.write_text(json.dumps(partners))
        cls.inactive = cls.render(cls.config, 'inactive')
        cls.active_config = {**cls.config, 'enabled': True, 'hosting_verified': True, 'links_verified': True}
        cls.active = cls.render(cls.active_config, 'active')
        cls.guides = {a['slug']: a for a in editorial_queue.published_articles(ROOT)}
        cls.real_partners = cls.render(cls.config, 'real-partners', extra_env={'SITE_AFFILIATES': str(ROOT / 'affiliates.json')})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def render(cls, config, name, *, extra_env=None, args=()):
        config_path = cls.work / (name + '.json')
        config_path.write_text(json.dumps(config))
        out = cls.work / name
        env = dict(os.environ, LJA_PUBLIC='1', SITE_ORIGIN=stay22.ORIGIN, SITE_OUT=str(out), SITE_STAY22=str(config_path))
        env.pop('SITE_MENTIONS', None); env.pop('SITE_ANALYTICS', None)
        env['SITE_AFFILIATES'] = str(cls.stay22_only)
        env.update(extra_env or {})
        result = subprocess.run([sys.executable, str(ROOT / 'generate.py'), *args], env=env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return out

    def guide_pages(self, out):
        for slug, article in self.guides.items():
            yield slug, (out / article.get('country', 'portugal') / slug / 'index.html').read_text()

    def test_inactive_fixture_with_unverified_gates_has_no_affiliate_markup(self):
        self.assertEqual(stay22.validate_config(self.real_config), self.real_config)
        for path in self.inactive.rglob('*.html'):
            source = path.read_text()
            self.assertNotIn('stay22', source.lower())
            self.assertNotIn('partner-box', source)
        for slug, source in self.guide_pages(self.inactive):
            self.assertNotIn(affiliates.DISCLOSURE, source, slug)

    def test_allez_url_uses_aid_campaign_and_place_from_the_guide(self):
        url = stay22.allez_url(self.config, 'roam', campaign='vsd_test', address='Hanoï, Vietnam')
        parsed = urlparse(url)
        self.assertEqual(parsed.scheme + '://' + parsed.netloc + parsed.path, stay22.ENDPOINT + 'roam')
        self.assertEqual(parse_qs(parsed.query), {'aid': ['voyagesansdetourfr'], 'address': ['Hanoï, Vietnam'],
                                                 'campaign': ['vsd_test'], 'lang': ['fr'], 'currency': ['EUR']})
        geo = parse_qs(urlparse(stay22.allez_url(self.config, 'getyourguide', campaign='c', lat=-8.5, lng=115.26)).query)
        self.assertEqual((geo['lat'], geo['lng']), (['-8.5'], ['115.26']))
        self.assertEqual(stay22.campaign_for(self.config, 'ou-dormir-à-Lisbonne--quartiers'), 'vsd_ou_dormir_lisbonne_quartiers')
        self.assertLessEqual(len(stay22.campaign_for(self.config, 'x' * 200)), stay22.CAMPAIGN_MAX)
        with self.assertRaises(ValueError): stay22.allez_url(self.config, 'evil', campaign='c', address='Paris')
        with self.assertRaises(ValueError): stay22.allez_url(self.config, 'roam', campaign='c', address=' ')

    def test_config_rejects_foreign_values(self):
        for patch in ({'aid': 'Other-Project'}, {'aid': ''}, {'endpoint': 'https://evil.test/'}, {'lang': 'en'},
                      {'currency': 'USD'}, {'script': 'https://example.test/x.js'}, {'enabled': 'false'},
                      {'hosting_verified': 1}, {'schema_version': True}, {'campaign_prefix': 'a b'}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                stay22.validate_config({**self.config, **patch})

    def test_activation_requires_both_gates_and_only_runs_on_the_public_domain(self):
        for hosting, links in [(False, False), (True, False), (False, True)]:
            config = {**self.config, 'enabled': True, 'hosting_verified': hosting, 'links_verified': links}
            with self.assertRaises(ValueError): stay22.validate_config(config)
        self.assertTrue(stay22.is_active(self.active_config, public=True, origin=stay22.ORIGIN))
        for public, origin in [(False, stay22.ORIGIN), (True, 'https://other.test')]:
            self.assertFalse(stay22.is_active(self.active_config, public=public, origin=origin))

    def test_every_published_guide_gets_one_to_three_disclosed_links_inside_the_article(self):
        for slug, source in self.guide_pages(self.active):
            with self.subTest(slug=slug):
                links = [a for t, a in Tags(source).tags if t == 'a' and 'partner-cta' in a.get('class', '')]
                self.assertTrue(1 <= len(links) <= 3, len(links))
                for attrs in links:
                    query = parse_qs(urlparse(attrs['href']).query)
                    self.assertTrue(attrs['href'].startswith(stay22.ENDPOINT))
                    self.assertEqual(query['aid'], ['voyagesansdetourfr'])
                    self.assertEqual(query['campaign'], [stay22.campaign_for(self.config, slug)])
                    self.assertEqual(set(attrs['rel'].split()), {'sponsored', 'nofollow', 'noopener'})
                    self.assertEqual(attrs['target'], '_blank')
                self.assertEqual(source.count(affiliates.DISCLOSURE), source.count('class="partner-box'))
                article = source[source.index('<article class="article-body">'):source.index('id="questions"')]
                self.assertEqual(article.count('class="partner-box'), source.count('class="partner-box'))
                self.assertIn('Les liens partenaires de ce guide sont signalés', source)

    def test_real_partner_config_without_stay22_links_activities_to_getyourguide(self):
        boxes = 0
        for slug, source in self.guide_pages(self.real_partners):
            with self.subTest(slug=slug):
                self.assertNotIn('stay22.com', source)
                links = [a for t, a in Tags(source).tags if t == 'a' and 'partner-cta' in a.get('class', '')]
                self.assertLessEqual(len(links), 3)
                for attrs in links:
                    query = parse_qs(urlparse(attrs['href']).query)
                    self.assertTrue(attrs['href'].startswith('https://www.getyourguide.com/fr-fr/s/?'))
                    self.assertEqual((query['partner_id'], query['cmp']), (['HKEWKYM'], [stay22.campaign_for(self.config, slug)]))
                    self.assertEqual(set(attrs['rel'].split()), {'sponsored', 'nofollow', 'noopener'})
                self.assertEqual(source.count(affiliates.DISCLOSURE), source.count('class="partner-box'))
                boxes += source.count('class="partner-box')
        self.assertGreater(boxes, 0)
        self.assertIn('GetYourGuide', (self.real_partners / 'transparence/index.html').read_text())

    def test_where_to_sleep_guide_puts_the_hotel_box_in_its_neighbourhood_sections(self):
        source = dict(self.guide_pages(self.active))['ou-dormir-lisbonne-quartiers']
        first_section = source.index('<section id=', source.index('<article class="article-body">'))
        hotel = source.index('partner-hotels')
        self.assertLess(first_section, hotel)
        self.assertIn('address=Lisbonne%2C%20Portugal', source)

    def test_affiliation_adds_no_script_iframe_or_automatic_resource_request(self):
        for path in self.active.rglob('*.html'):
            source = path.read_text()
            original = (self.inactive / path.relative_to(self.active)).read_text()
            self.assertEqual([a for t, a in Tags(source).tags if t == 'script'], [a for t, a in Tags(original).tags if t == 'script'])
            for tag, attrs in Tags(source).tags:
                self.assertNotEqual(tag, 'iframe')
                if tag != 'a':
                    self.assertFalse(any('stay22.com' in str(value) for value in attrs.values()))
                self.assertNotIn(attrs.get('rel'), ('preconnect', 'prefetch', 'dns-prefetch'))

    def test_transparency_and_privacy_follow_activation_without_admission_claim(self):
        for route in ('transparence', 'confidentialite'):
            active = (self.active / route / 'index.html').read_text()
            inactive = (self.inactive / route / 'index.html').read_text()
            self.assertIn('Stay22', active); self.assertNotIn('Stay22', inactive)
            self.assertNotIn('admission confirmée', active)
            self.assertNotIn('admis au programme', active)
        transparency = (self.active / 'transparence/index.html').read_text()
        self.assertIn(affiliates.DISCLOSURE, transparency)
        self.assertIn('Aucune publicité d’affichage n’est activée', transparency)
        self.assertIn('Aucun programme d’affiliation ni publicité n’est activé', (self.inactive / 'transparence/index.html').read_text())

    def test_preview_cannot_target_public_or_enable_a_public_build(self):
        with self.assertRaises(ValueError): stay22.validate_preview(ROOT, ROOT / 'public', public=False, origin=stay22.PREVIEW_ORIGIN)
        with self.assertRaises(ValueError): stay22.validate_preview(ROOT, ROOT / 'previews/stay22/site', public=True, origin=stay22.PREVIEW_ORIGIN)
        with self.assertRaises(ValueError): stay22.validate_preview(ROOT, ROOT / 'previews/stay22/site', public=False, origin=stay22.ORIGIN)
        with self.assertRaisesRegex(RuntimeError, 'aperçu réservé'): self.render(self.config, 'rejected-preview', args=('--preview-stay22',))
        self.assertFalse((self.work / 'rejected-preview').exists())
        spoof = self.render(self.config, 'spoof-env', extra_env={'SITE_STAY22_PREVIEW': '1'})
        self.assertNotIn('partner-box', (spoof / 'portugal/lisbonne-3-jours-sans-voiture/index.html').read_text())

    def test_public_carousel_inventory_is_twelve_unmodified_jpegs_plus_attribution(self):
        folder = self.inactive / 'social-media/carrousels-2026-09'
        expected = {city + '-' + name + '.jpg' for city in ('lisbonne', 'porto') for name in
                    ('01-couverture', '02-jour-1', '03-jour-2', '04-jour-3', '05-bons-reflexes', '06-guide-complet')}
        expected.update(('credits.txt', 'dmsans-OFL.txt', 'playfairdisplay-OFL.txt'))
        self.assertEqual({p.name for p in folder.iterdir()}, expected)
        for name in expected:
            self.assertEqual((folder / name).read_bytes(), (ROOT / 'social-media/carrousels-2026-09' / name).read_bytes())
        self.assertIn('ne prouve aucune programmation ni publication sociale', (folder / 'credits.txt').read_text())


if __name__ == '__main__':
    unittest.main()
