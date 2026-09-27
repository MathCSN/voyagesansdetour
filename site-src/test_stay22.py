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
        # A verified link or an authorized activation must not invalidate CI.
        cls.real_config = stay22.load_config(ROOT / 'stay22.json')
        cls.config = copy.deepcopy(cls.real_config)
        cls.config.update(enabled=False, hosting_verified=False, links_verified=False)
        cls.inactive = cls.render(cls.config, 'inactive')
        active = copy.deepcopy(cls.config)
        active.update(enabled=True, hosting_verified=True, links_verified=True)
        cls.active = cls.render(active, 'active')

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
        env.update(extra_env or {})
        result = subprocess.run([sys.executable, str(ROOT / 'generate.py'), *args], env=env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return out

    def test_inactive_fixture_with_unverified_gates_has_no_affiliate_markup(self):
        self.assertEqual(stay22.validate_config(self.real_config), self.real_config)
        self.assertFalse(self.config['enabled'])
        self.assertFalse(self.config['hosting_verified'])
        self.assertFalse(self.config['links_verified'])
        for path in self.inactive.rglob('*.html'):
            source = path.read_text()
            self.assertNotIn('stay22', source.lower())
            self.assertNotIn('booking.com', source)

    def test_aid_destinations_campaigns_and_all_parameters_are_bounded(self):
        for destination, expected in stay22.DESTINATIONS.items():
            url = stay22.booking_url(self.config, destination)
            parsed = urlparse(url)
            self.assertEqual(parsed.scheme + '://' + parsed.netloc + parsed.path, stay22.ENDPOINT)
            self.assertEqual(parse_qs(parsed.query), {'aid': [stay22.AID], 'link': [expected['url']],
                'campaign': [expected['campaign']], 'lang': ['fr'], 'currency': ['EUR'], 'roam': ['false']})
            self.assertIn('link=https%3A%2F%2Fwww.booking.com%2F', url)
        for patch in ({'aid': 'other-project'}, {'aid': ''}, {'endpoint': 'https://evil.test/'}, {'roam': True},
                      {'lang': 'en'}, {'currency': 'USD'}, {'script': 'https://example.test/x.js'}, {'enabled': 'false'},
                      {'hosting_verified': 1}, {'schema_version': True}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                stay22.validate_config({**self.config, **patch})
        for url in ['http://www.booking.com/city/pt/lisbon.fr.html', 'https://www.booking.com@evil.test/',
                    'https://www.booking.com/city/pt/porto.fr.html', 'https://www.booking.com/city/pt/lisbon.fr.html?aid=other']:
            config = copy.deepcopy(self.config); config['destinations']['lisbonne']['url'] = url
            with self.assertRaises(ValueError): stay22.validate_config(config)

    def test_activation_requires_both_explicit_gates_and_expected_public_origin(self):
        for hosting, links in [(False, False), (True, False), (False, True)]:
            config = {**self.config, 'enabled': True, 'hosting_verified': hosting, 'links_verified': links}
            with self.assertRaises(ValueError): stay22.is_active(config, public=True, origin=stay22.ORIGIN)
        config = {**self.config, 'enabled': True, 'hosting_verified': True, 'links_verified': True}
        for public, origin in [(False, stay22.ORIGIN), (True, 'https://other.test')]:
            with self.assertRaises(ValueError): stay22.is_active(config, public=public, origin=origin)

    def test_only_three_guides_have_one_disclosed_link_before_faq(self):
        found = []
        for path in self.active.rglob('*.html'):
            source = path.read_text()
            links = [attrs for tag, attrs in Tags(source).tags if tag == 'a' and attrs.get('href', '').startswith(stay22.ENDPOINT)]
            if not links: continue
            slug = path.parent.name; found.append(slug)
            self.assertEqual(len(links), 1)
            self.assertLess(source.index('id="hebergement"'), source.index('id="questions"'))
            self.assertGreater(source.index('id="hebergement"'), source.index('<article class="article-body">'))
            self.assertEqual(set(links[0]['rel'].split()), {'sponsored', 'nofollow', 'noopener', 'noreferrer'})
            self.assertEqual(links[0]['target'], '_blank')
            self.assertEqual(parse_qs(urlparse(links[0]['href']).query)['link'], [stay22.DESTINATIONS[stay22.GUIDES[slug]]['url']])
            box = source[source.index('id="hebergement"'):source.index('id="questions"')]
            self.assertIn('Nous n’avons pas testé', box)
            self.assertIn('Lien affilié via Stay22', box)
            self.assertIn('commission', box)
        self.assertEqual(set(found), set(stay22.GUIDES))

    def test_affiliation_adds_no_script_iframe_or_automatic_resource_request(self):
        for path in self.active.rglob('*.html'):
            source = path.read_text()
            original = (self.inactive / path.relative_to(self.active)).read_text()
            self.assertEqual([a for t, a in Tags(source).tags if t == 'script'], [a for t, a in Tags(original).tags if t == 'script'])
            for tag, attrs in Tags(source).tags:
                self.assertNotEqual(tag, 'iframe')
                if tag != 'a':
                    self.assertFalse(any('stay22.com' in str(value) or 'booking.com' in str(value) for value in attrs.values()))
                self.assertNotIn(attrs.get('rel'), ('preconnect', 'prefetch', 'dns-prefetch'))

    def test_transparency_and_privacy_follow_activation_without_admission_claim(self):
        for route in ('transparence', 'confidentialite'):
            active = (self.active / route / 'index.html').read_text()
            inactive = (self.inactive / route / 'index.html').read_text()
            self.assertIn('Stay22', active); self.assertNotIn('Stay22', inactive)
            self.assertNotIn('admission confirmée', active)
            self.assertNotIn('admis au programme', active)
        self.assertIn('Aucun programme d’affiliation ni publicité n’est activé', (self.inactive / 'transparence/index.html').read_text())
        self.assertIn('Aucune publicité d’affichage n’est activée', (self.active / 'transparence/index.html').read_text())

    def test_preview_cannot_target_public_or_enable_a_public_build(self):
        with self.assertRaises(ValueError): stay22.validate_preview(ROOT, ROOT / 'public', public=False, origin=stay22.PREVIEW_ORIGIN)
        with self.assertRaises(ValueError): stay22.validate_preview(ROOT, ROOT / 'previews/stay22/site', public=True, origin=stay22.PREVIEW_ORIGIN)
        with self.assertRaises(ValueError): stay22.validate_preview(ROOT, ROOT / 'previews/stay22/site', public=False, origin=stay22.ORIGIN)
        with self.assertRaisesRegex(RuntimeError, 'aperçu réservé'): self.render(self.config, 'rejected-preview', args=('--preview-stay22',))
        self.assertFalse((self.work / 'rejected-preview').exists())
        spoof = self.render(self.config, 'spoof-env', extra_env={'SITE_STAY22_PREVIEW': '1'})
        self.assertNotIn('stay22-box', (spoof / 'portugal/lisbonne-3-jours-sans-voiture/index.html').read_text())

    def test_preview_box_disables_clicks_and_does_not_mutate_config(self):
        original = copy.deepcopy(self.config)
        box = stay22.guide_box(self.config, 'lisbonne-3-jours-sans-voiture', preview=True)
        self.assertIn('aria-disabled="true"', box)
        self.assertNotIn('href=', box)
        self.assertIn('Aperçu local', box)
        self.assertEqual(self.config, original)

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
