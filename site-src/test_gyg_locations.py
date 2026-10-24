import json
from pathlib import Path
import tempfile
import unittest

import affiliates
import editorial_queue
import gyg_locations

ROOT = Path(__file__).resolve().parent


def widget(*paths):
    """Réponse minimale du widget officiel : des liens d'activités sous leur page de lieu."""
    return ''.join(f'<a href="https://www.getyourguide.com/{p}/activite-t{i}/">x</a>' for i, p in enumerate(paths))


def guide(slug, destination, country='portugal', title=None):
    return {'slug': slug, 'destination': destination, 'country': country, 'title': title or destination, 'sections': []}


class Fetcher:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, query):
        self.calls.append(query)
        answer = self.answers.get(query)
        if isinstance(answer, Exception):
            raise answer
        return answer or ''


class LocationFromWidgetTest(unittest.TestCase):
    def test_keeps_the_most_frequent_page_whose_name_matches_the_place(self):
        html = widget('santarem-portugal-l1441', 'lisbonne-l42', 'lisbonne-l42', 'lisbonne-l42')
        self.assertEqual(gyg_locations.location_from_html(html, 'Lisbonne'), 'lisbonne-l42')
        self.assertEqual(gyg_locations.location_from_html(widget('guimaraes-l4960'), 'Guimarães'), 'guimaraes-l4960')
        self.assertEqual(gyg_locations.location_from_html(widget('santarem-portugal-l1441'), 'Santarém', 'Portugal'), 'santarem-portugal-l1441')

    def test_refuses_a_neighbouring_city_rather_than_linking_the_wrong_place(self):
        self.assertIsNone(gyg_locations.location_from_html(widget('malaga-l402', 'seville-l48'), 'Andalousie'))
        self.assertIsNone(gyg_locations.location_from_html(widget('naples-l162', 'sorrente-l391'), 'Côte amalfitaine'))
        self.assertIsNone(gyg_locations.location_from_html(widget('porto-l151'), 'Douro'))
        self.assertIsNone(gyg_locations.location_from_html('', 'Sintra'))
        self.assertIsNone(gyg_locations.location_from_html(widget('porto-vecchio-l1'), 'Porto'), 'préfixe ambigu')


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'getyourguide-locations.json'
        self.articles = [guide('sintra', 'Sintra'), guide('andalousie', 'Andalousie', 'espagne'),
                         guide('kyoto', 'Kyoto', 'japon'), guide('lisbonne-ou-porto', 'Portugal', title='Lisbonne ou Porto'),
                         guide('lisbonne', 'Lisbonne'), guide('porto', 'Porto')]

    def test_resolves_every_place_once_and_records_failures_without_search_links(self):
        fetch = Fetcher({'Sintra': widget('sintra-l99'), 'Andalousie': widget('malaga-l402'), 'Kyoto': widget('kyoto-l96826'),
                         'Lisbonne': widget('lisbonne-l42'), 'Porto': widget('porto-l151')})
        cache = gyg_locations.update(gyg_locations.empty(), self.articles, {}, fetch=fetch, today='2026-10-24')
        locations = cache['locations']
        self.assertEqual(locations['sintra|portugal']['path'], 'sintra-l99')
        self.assertEqual(locations['kyoto|japon']['path'], 'kyoto-l96826')
        self.assertIsNone(locations['andalousie|espagne']['path'])
        self.assertEqual(locations['andalousie|espagne']['checkedOn'], '2026-10-24')
        self.assertEqual(sorted(fetch.calls), ['Andalousie', 'Kyoto', 'Lisbonne', 'Porto', 'Sintra'])
        region = guide('andalousie-train', 'Andalousie', 'espagne', 'L’Andalousie en train : Séville, Cordoue')
        self.assertTrue({'seville|espagne', 'cordoue|espagne'} <= gyg_locations.needed_keys([region], {}))
        again = Fetcher({})
        self.assertEqual(gyg_locations.update(cache, self.articles, {}, fetch=again, today='2026-11-01'), cache)
        self.assertEqual(again.calls, [])

    def test_retries_old_failures_and_survives_network_errors(self):
        cache = gyg_locations.empty()
        cache['locations']['andalousie|espagne'] = {'place': 'Andalousie', 'country': 'Espagne', 'path': None, 'checkedOn': '2026-08-01'}
        fetch = Fetcher({'Andalousie': widget('andalousie-l9'), 'Sintra': OSError('réseau coupé')})
        updated = gyg_locations.update(cache, self.articles[:2], {}, fetch=fetch, today='2026-10-24')
        self.assertEqual(updated['locations']['andalousie|espagne']['path'], 'andalousie-l9')
        self.assertNotIn('sintra|portugal', updated['locations'])
        self.assertIsNone(cache['locations']['andalousie|espagne']['path'], 'le cache d’origine n’est pas modifié')

    def test_save_and_load_round_trip_and_reject_unsafe_paths(self):
        cache = gyg_locations.empty()
        cache['locations']['sintra|portugal'] = {'place': 'Sintra', 'country': 'Portugal', 'path': 'sintra-l99', 'checkedOn': '2026-10-24'}
        gyg_locations.save(self.path, cache)
        self.assertEqual(gyg_locations.load(self.path), cache)
        self.assertEqual(gyg_locations.paths(self.path), {'sintra|portugal': 'sintra-l99'})
        for bad in ('../evil-l1', 'sintra', 'https://evil.test/x-l1', 'Sintra-L99'):
            cache['locations']['sintra|portugal']['path'] = bad
            self.path.write_text(json.dumps(cache))
            with self.subTest(path=bad), self.assertRaises(ValueError):
                gyg_locations.load(self.path)
        self.assertEqual(gyg_locations.paths(Path(self.tmp.name) / 'absent.json'), {})

    def test_widget_query_uses_the_official_partner_widget(self):
        url = gyg_locations.widget_url('Côte amalfitaine')
        self.assertTrue(url.startswith('https://widget.getyourguide.com/default/activities.frame?'))
        self.assertIn('partner_id=HKEWKYM', url)
        self.assertIn('q=C%C3%B4te%20amalfitaine', url)


class RealCacheTest(unittest.TestCase):
    def test_committed_cache_covers_every_published_guide_place_with_matching_names(self):
        cache = gyg_locations.load(ROOT / 'getyourguide-locations.json')
        articles = editorial_queue.published_articles(ROOT)
        countries = affiliates.load_countries(ROOT / 'destinations.json')
        for key in gyg_locations.needed_keys(articles, countries):
            self.assertIn(key, cache['locations'])
        for key, entry in cache['locations'].items():
            if entry['path']:
                self.assertTrue(gyg_locations.matches(entry['path'], entry['place'], entry['country']), key)


if __name__ == '__main__':
    unittest.main()
