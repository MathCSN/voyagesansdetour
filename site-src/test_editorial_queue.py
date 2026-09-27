import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import editorial_queue as release

ROOT = Path(__file__).resolve().parent
NOW = release.instant('2026-10-15T10:00:00Z')


class EditorialQueueTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vsd-editorial-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.articles = json.loads((ROOT / 'articles.json').read_text())
        self.queue = {'schemaVersion': 1, 'drafts': [], 'promotions': []}
        self.save()

    def save(self):
        for name, value in [('articles.json', self.articles), ('editorial-queue.json', self.queue)]:
            (self.root / name).write_text(json.dumps(value, ensure_ascii=False))

    def draft(self, slug='fixture-new-guide', release_at='2026-10-15T10:00:00Z', valid_until='2026-10-27T23:59:59Z'):
        article = {k: copy.deepcopy(v) for k, v in self.articles[0].items() if k in release.ARTICLE_KEYS}
        article.update(slug=slug, sourcesCheckedOn='2026-09-14')
        draft = {'id': slug, 'article': article, 'releaseAt': release_at, 'validUntil': valid_until,
                 'approval': {'approvedAt': '2026-09-20T10:00:00Z'}}
        draft['approval']['sha256'] = release.approval_hash(draft)
        self.queue['drafts'].append(draft); self.save()
        return draft

    def build_manifest(self):
        data = b'<html>Reviewed fixture; no real publication</html>'
        path = self.root / 'public/portugal/fixture-new-guide/index.html'
        path.parent.mkdir(parents=True); path.write_bytes(data)
        return release.manifest(self.root, self.root / 'public', NOW), data

    def test_future_hidden_then_due_promoted_once_and_persisted(self):
        self.draft()
        before = NOW - dt.timedelta(seconds=1)
        self.assertFalse(release.promote(self.root, before))
        self.assertEqual(release.published_articles(self.root, before), self.articles)
        self.assertTrue(release.promote(self.root, NOW))
        articles, queue = release.load(self.root, NOW)
        self.assertEqual(articles[:-1], self.articles)
        self.assertEqual(articles[-1]['publishedOn'], '2026-10-15')
        self.assertEqual(queue['drafts'], [])
        self.assertIsNone(queue['promotions'][0]['receipt'])
        self.assertFalse(release.promote(self.root, NOW + dt.timedelta(hours=1)))
        self.assertEqual(len(release.published_articles(self.root, NOW)), len(self.articles) + 1)

    def test_content_and_window_tamper_refused_without_writes(self):
        for field in ('article', 'releaseAt', 'validUntil', 'approvedAt'):
            with self.subTest(field=field):
                self.queue['drafts'] = []; draft = self.draft()
                if field == 'article': draft['article']['title'] += ' edited'
                elif field == 'approvedAt': draft['approval'][field] = '2026-09-28T10:00:00Z'
                else: draft[field] = '2026-10-16T10:00:00Z'
                self.save(); before = (self.root / 'articles.json').read_bytes()
                with self.assertRaises(ValueError): release.promote(self.root, NOW)
                self.assertEqual((self.root / 'articles.json').read_bytes(), before)

    def test_expired_before_first_release_and_failed_deployment_stop_without_removal(self):
        self.draft(valid_until='2026-10-15T09:59:59Z', release_at='2026-10-14T10:00:00Z')
        with self.assertRaisesRegex(ValueError, 'expiré'): release.promote(self.root, NOW)
        self.assertEqual(json.loads((self.root / 'articles.json').read_text()), self.articles)
        self.queue['drafts'] = []; self.draft(); release.promote(self.root, NOW)
        persisted = (self.root / 'articles.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'expiré'):
            release.published_articles(self.root, release.instant('2026-11-01T00:00:00Z'))
        self.assertEqual((self.root / 'articles.json').read_bytes(), persisted)

    def test_confirmed_guide_survives_expiry_and_cannot_be_removed_by_stale_copy(self):
        self.draft(); release.promote(self.root, NOW)
        expected, data = self.build_manifest()
        self.assertTrue(release.confirm(self.root, expected, NOW, fetcher=lambda url: data))
        later = release.instant('2027-02-01T00:00:00Z')
        self.assertEqual(len(release.published_articles(self.root, later)), len(self.articles) + 1)
        articles, queue = release.load(self.root, later)
        articles.pop()
        with self.assertRaisesRegex(ValueError, 'retiré'): release.validate(articles, queue, later)

    def test_stale_local_publisher_cannot_erase_remote_promotion_or_receipt(self):
        self.draft()
        remote = self.root / 'remote'; remote.mkdir()
        for name in ('articles.json', 'editorial-queue.json'):
            shutil.copyfile(self.root / name, remote / name)
        release.promote(remote, NOW)
        with self.assertRaisesRegex(ValueError, 'Promotions cloud absentes'):
            release.preserve_remote(self.root, remote, NOW)
        for name in ('articles.json', 'editorial-queue.json'):
            shutil.copyfile(remote / name, self.root / name)
        release.preserve_remote(self.root, remote, NOW)
        expected, data = self.build_manifest()
        release.confirm(remote, expected, NOW, fetcher=lambda url: data)
        with self.assertRaisesRegex(ValueError, 'Promotions cloud absentes'):
            release.preserve_remote(self.root, remote, NOW)

    def test_unconfirmed_release_cannot_drift_to_a_false_publication_day(self):
        self.draft(); release.promote(self.root, NOW)
        with self.assertRaisesRegex(ValueError, 'autre jour'):
            release.published_articles(self.root, NOW + dt.timedelta(days=1))

    def test_build_manifest_binds_content_queue_and_exact_http_bytes(self):
        self.draft(); release.promote(self.root, NOW)
        expected, data = self.build_manifest()
        self.assertEqual(expected['entries'][0]['htmlSha256'], hashlib.sha256(data).hexdigest())
        with self.assertRaisesRegex(ValueError, 'HTML public différent'):
            release.confirm(self.root, expected, NOW, fetcher=lambda url: b'old page')
        self.assertIsNone(release.load(self.root, NOW)[1]['promotions'][0]['receipt'])
        edited = copy.deepcopy(expected); edited['queueSha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'sources de sortie différents'):
            release.check_manifest(self.root, edited, NOW)
        self.assertEqual(release.load(self.root, NOW)[1]['promotions'][0]['receipt'], None)
        articles, queue = release.load(self.root, NOW)
        articles[-1]['summary'] += ' altered after build'
        (self.root / 'articles.json').write_text(json.dumps(articles))
        with self.assertRaisesRegex(ValueError, 'modifié avant confirmation'):
            release.check_manifest(self.root, expected, NOW)

    def test_cadence_and_explicit_window_hold_back_backlog(self):
        self.draft(); self.draft(slug='fixture-second-guide')
        self.assertTrue(release.promote(self.root, NOW))
        expected, data = self.build_manifest(); release.confirm(self.root, expected, NOW, fetcher=lambda url: data)
        self.assertFalse(release.promote(self.root, NOW + dt.timedelta(days=1)))
        self.assertEqual(len(release.load(self.root, NOW)[1]['drafts']), 1)

    def test_missing_approval_unknown_fields_and_published_slug_fail_closed(self):
        draft = self.draft()
        for mutate in (lambda d: d.update(extra=True), lambda d: d['approval'].pop('sha256'),
                       lambda d: d['article'].update(slug=self.articles[0]['slug'])):
            candidate = copy.deepcopy(self.queue); mutate(candidate['drafts'][0])
            with self.assertRaises(ValueError): release.validate(self.articles, candidate, NOW)

    def test_live_generator_excludes_future_and_keeps_existing_pages_identical(self):
        # Copy only source and permitted assets, never the existing generated site.
        self.draft(release_at='2099-10-15T10:00:00Z', valid_until='2099-10-27T23:59:59Z')
        for name in ('generate.py', 'public_media.py', 'public-media.json', 'editorial_queue.py', 'stay22.py', 'stay22.json', 'mentions.json',
                     'analytics.json', 'pinterest-rss.json', 'image-sources.json'):
            shutil.copyfile(ROOT / name, self.root / name)
        (self.root / 'dist').mkdir()
        for name in ('style.css', 'site.js', 'analytics.mjs'):
            shutil.copyfile(ROOT / 'dist' / name, self.root / 'dist' / name)
        shutil.copytree(ROOT / 'dist/assets', self.root / 'dist/assets', ignore=shutil.ignore_patterns('reel-*'))
        shutil.copytree(ROOT / 'social-media', self.root / 'social-media')
        env = dict(os.environ, LJA_PUBLIC='1', SITE_ORIGIN=release.ORIGIN)
        for key in ('SITE_OUT', 'SITE_MENTIONS', 'SITE_ANALYTICS', 'SITE_STAY22'): env.pop(key, None)
        result = subprocess.run([sys.executable, 'generate.py'], cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = self.root / 'public'
        self.assertFalse((out / 'portugal/fixture-new-guide').exists())
        before = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
        self.queue['drafts'] = []; self.save()
        result = subprocess.run([sys.executable, 'generate.py'], cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
