"""The two-day guide calendar: an empty queue opens it, a fresh release or a reserved guide fills it."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import admit_update as a
import guide_draft as g
import editorial_queue as q

LEDGER={'schemaVersion':1,'updates':[]}


def published(day):
    return {'slug':'guide-'+day,'publishedOn':day}


def queue(drafts=(),promotions=()):
    return {'schemaVersion':1,'drafts':list(drafts),'promotions':list(promotions)}


class GuideCalendarTests(unittest.TestCase):
    def test_empty_queue_after_a_due_slot_opens_the_calendar_now(self):
        now=dt.datetime(2026,11,6,14,25,tzinfo=q.UTC)
        self.assertEqual(a.guide_release_at([published('2026-11-01')],queue(),LEDGER,now),now)
    def test_the_evening_before_a_slot_reserves_it(self):
        # Marrakech went out on 05/11: the next guide may be written on 06/11 for 07/11 00:00 Paris.
        now=dt.datetime(2026,11,6,14,25,tzinfo=q.UTC)
        self.assertEqual(a.guide_release_at([published('2026-11-05')],queue(),LEDGER,now),dt.datetime(2026,11,6,23,tzinfo=q.UTC))
    def test_publication_day_waits_for_the_two_day_slot(self):
        now=dt.datetime(2026,11,5,14,47,tzinfo=q.UTC)
        self.assertIsNone(a.guide_release_at([published('2026-11-05')],queue(),LEDGER,now))
    def test_a_reserved_guide_or_an_unconfirmed_release_fills_the_calendar(self):
        now=dt.datetime(2026,11,6,14,25,tzinfo=q.UTC)
        self.assertIsNone(a.guide_release_at([published('2026-11-01')],queue(drafts=[{'releaseAt':'2026-11-08T07:00:00Z'}]),LEDGER,now))
        self.assertIsNone(a.guide_release_at([published('2026-11-01')],queue(promotions=[{'promotedAt':'2026-11-02T07:00:00Z','receipt':None}]),LEDGER,now))
    def test_a_confirmed_promotion_counts_as_a_release(self):
        now=dt.datetime(2026,11,6,14,25,tzinfo=q.UTC)
        done={'promotedAt':'2026-11-06T07:00:00Z','receipt':{'deployed':True}}
        self.assertIsNone(a.guide_release_at([published('2026-11-01')],queue(promotions=[done]),LEDGER,now))


class GuideRunCalendarTests(unittest.TestCase):
    def test_an_empty_queue_goes_on_to_photos_instead_of_calendar_full(self):
        now=dt.datetime.now(q.UTC)
        articles=[published((now.astimezone(q.PARIS).date()-dt.timedelta(days=5)).isoformat())]
        read=q.read_json
        with tempfile.TemporaryDirectory() as tmp, patch.dict(g.os.environ,{'REPORT_DIR':tmp,'CLOUDFLARE_WORKERS_AI_TOKEN':'x'},clear=True), \
             patch.object(g,'quota_hold',return_value=None), patch.object(g,'known_articles',return_value=(articles,queue(),articles)), \
             patch.object(g.q,'read_json',side_effect=lambda path:LEDGER if Path(path).name=='editorial-updates.json' else read(path)), \
             patch.object(g.guide_photos,'prepare',side_effect=ValueError('guide_photos_insufficient')) as photos, \
             patch.object(g,'call',side_effect=AssertionError('inference')):
            self.assertEqual(g.main(),0)
            report=json.loads((Path(tmp)/'guide-report.json').read_text())
        photos.assert_called_once()
        self.assertNotEqual(report['status'],'calendar_full')
        self.assertEqual((report['reason'],report['callsAttempted']),('guide_photos_insufficient',0))
        self.assertIn('releaseAt',report)
