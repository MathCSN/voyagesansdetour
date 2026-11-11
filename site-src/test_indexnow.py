import datetime as dt
import io
import json
import unittest
import urllib.error

import indexnow

SITEMAP = ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           '<url><loc>https://voyagesansdetour.fr/</loc><lastmod>2026-11-11</lastmod></url>'
           '<url><loc>https://voyagesansdetour.fr/japon/</loc><lastmod>2026-11-10</lastmod></url>'
           '<url><loc>https://voyagesansdetour.fr/methode/</loc><lastmod>2026-09-14</lastmod></url>'
           '<url><loc>https://example.org/ailleurs/</loc><lastmod>2026-11-11</lastmod></url>'
           '</urlset>')
TODAY = dt.date(2026, 11, 11)


class Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body.encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeWeb:
    """Stands for the site and the IndexNow endpoint; records what was sent."""

    def __init__(self, sitemap=SITEMAP, key=indexnow.KEY, status=200):
        self.sitemap, self.key, self.status, self.posted = sitemap, key, status, []

    def open(self, request, timeout=None):
        url = request.full_url
        if url.startswith(indexnow.ENDPOINT):
            self.posted.append(json.loads(request.data))
            if self.status >= 400:
                raise urllib.error.HTTPError(url, self.status, 'refused', None, None)
            return Response('', self.status)
        if '/sitemap.xml' in url:
            return Response(self.sitemap)
        if url.startswith(indexnow.KEY_LOCATION):
            return Response(self.key + '\n')
        raise AssertionError('Appel inattendu : ' + url)


class ChangedUrlsTest(unittest.TestCase):
    def test_only_recent_pages_of_the_site_are_selected(self):
        self.assertEqual(indexnow.changed_urls(SITEMAP, TODAY, since_days=1),
                         ['https://voyagesansdetour.fr/', 'https://voyagesansdetour.fr/japon/'])
        self.assertEqual(indexnow.changed_urls(SITEMAP, TODAY, since_days=0), ['https://voyagesansdetour.fr/'])

    def test_all_pages_can_be_sent_after_a_template_change(self):
        self.assertEqual(len(indexnow.changed_urls(SITEMAP, TODAY, since_days=None)), 3)

    def test_a_page_without_a_valid_date_is_never_selected_by_date(self):
        broken = SITEMAP.replace('<lastmod>2026-11-11</lastmod>', '<lastmod>hier</lastmod>', 1)
        self.assertEqual(indexnow.changed_urls(broken, TODAY, since_days=1), ['https://voyagesansdetour.fr/japon/'])


class SubmitTest(unittest.TestCase):
    def test_changed_pages_are_sent_with_the_public_key_and_its_location(self):
        web = FakeWeb()
        report = indexnow.run(TODAY, opener=web)
        self.assertEqual(report['status'], 'submitted')
        self.assertEqual(web.posted, [{'host': 'voyagesansdetour.fr', 'key': indexnow.KEY,
                                       'keyLocation': indexnow.KEY_LOCATION,
                                       'urlList': ['https://voyagesansdetour.fr/', 'https://voyagesansdetour.fr/japon/']}])

    def test_nothing_is_sent_when_no_page_changed(self):
        web = FakeWeb(sitemap=SITEMAP.replace('2026-11-11', '2026-10-01').replace('2026-11-10', '2026-10-01'))
        self.assertEqual(indexnow.run(TODAY, opener=web)['status'], 'nothing_changed')
        self.assertEqual(web.posted, [])

    def test_nothing_is_sent_before_the_key_file_is_online(self):
        web = FakeWeb(key='autre-chose')
        self.assertEqual(indexnow.run(TODAY, opener=web)['status'], 'key_not_published')
        self.assertEqual(web.posted, [])

    def test_a_refusal_is_reported_without_raising(self):
        report = indexnow.run(TODAY, opener=FakeWeb(status=403))
        self.assertEqual((report['status'], report['reason']), ('refused', 'http_403'))

    def test_a_broken_connection_is_reported_without_raising(self):
        import http.client

        class Broken:
            def open(self, request, timeout=None):
                raise http.client.IncompleteRead(b'')

        self.assertEqual(indexnow.run(TODAY, opener=Broken()), {'status': 'unreachable', 'reason': 'IncompleteRead'})

    def test_the_key_is_a_valid_indexnow_key(self):
        self.assertRegex(indexnow.KEY, r'^[0-9a-f]{32}$')
        self.assertEqual(indexnow.KEY_LOCATION, f'https://voyagesansdetour.fr/{indexnow.KEY}.txt')

    def test_the_generator_publishes_the_same_key_file(self):
        import pathlib
        source = (pathlib.Path(__file__).parent / 'generate.py').read_text()
        self.assertIn(f"INDEXNOW_KEY='{indexnow.KEY}'", source)
        self.assertIn("(OUT/(INDEXNOW_KEY+'.txt')).write_text(INDEXNOW_KEY+'\\n')", source)


if __name__ == '__main__':
    unittest.main()
