import datetime as dt
import unittest
import social_draft as draft

class DraftTests(unittest.TestCase):
    def test_slots_respect_weekly_spacing_and_expiry(self):
        now=dt.datetime(2026,10,12,8,tzinfo=dt.timezone.utc);expiry=dt.datetime(2026,11,11,tzinfo=dt.timezone.utc)
        occupied=['2026-10-18T16:00:00Z','2026-10-25T17:00:00Z','2026-11-01T17:00:00Z']
        self.assertEqual(draft.due_date(now,occupied,expiry),'2026-11-08T17:00:00Z')
        self.assertIsNone(draft.due_date(now,occupied,dt.datetime(2026,11,8,16,tzinfo=dt.timezone.utc)))
    def test_no_same_day_or_overdue_slot(self):
        now=dt.datetime(2026,10,18,15,tzinfo=dt.timezone.utc)
        self.assertEqual(draft.due_date(now,[],dt.datetime(2026,11,1,tzinfo=dt.timezone.utc)),'2026-10-25T17:00:00Z')
    def test_capability_expiry_before_files_or_network(self):
        self.assertEqual(draft.build('/absent','/absent',draft.CAPABILITY_UNTIL,[])['status'],'capability_or_authorization_expired')
if __name__=='__main__':unittest.main()
