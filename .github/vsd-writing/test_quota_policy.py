import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import quota_policy as quota
import source_draft as source
import discover_facts as discovery

NOW=dt.datetime(2026,10,12,6,tzinfo=dt.timezone.utc)

class FrozenDateTime(dt.datetime):
    @classmethod
    def now(cls,tz=None):return NOW

class QuotaTests(unittest.TestCase):
    def test_hold_expires_at_next_utc_midnight(self):
        self.assertEqual(quota.hold(NOW,source.ACCOUNT)['status'],'free_quota_hold')
        self.assertIsNone(quota.hold(dt.datetime(2026,10,13,tzinfo=dt.timezone.utc),source.ACCOUNT))
        self.assertIsNone(quota.hold(NOW,'unrelated-account'))

    def test_unbounded_hold_rejected(self):
        data=json.loads(quota.OBSERVATIONS.read_text());data['holds'][0]['resumeAt']='2027-01-01T00:00:00Z'
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'quota.json';p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'daily_reset'):quota.hold(NOW,source.ACCOUNT,p)

    def test_shared_call_stops_before_inference(self):
        with patch.object(source.dt,'datetime',FrozenDateTime), \
                patch.object(source,'quota_hold',return_value={'status':'free_quota_hold'}), \
                patch.object(source.urllib.request,'build_opener',side_effect=AssertionError('network')):
            with self.assertRaisesRegex(ValueError,'free_quota_hold'):source.call([],10,'dummy-token')

    def test_scheduled_discovery_skips_sources_and_secret(self):
        budget=quota.hold(NOW,source.ACCOUNT)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'REPORT_DIR':folder,'CLOUDFLARE_WORKERS_AI_TOKEN':''}), \
                patch.object(discovery.dt,'datetime',FrozenDateTime), \
                patch.object(discovery,'quota_hold',return_value=budget), \
                patch.object(discovery,'source_fingerprint',side_effect=AssertionError('source fetch')), \
                patch.object(discovery,'call',side_effect=AssertionError('inference')):
            self.assertEqual(discovery.main(),0)
            report=json.loads((Path(folder)/'discovery-report.json').read_text())
            self.assertEqual(report['callsAttempted'],0)
            self.assertEqual(report['sourceFetches'],0)
            self.assertEqual(report['observedAt'],NOW.isoformat(timespec='seconds'))
            self.assertEqual(report['quotaObservedAt'],budget['quotaObservedAt'])
            self.assertFalse(report['publicationAttempted'])

if __name__=='__main__':unittest.main()
