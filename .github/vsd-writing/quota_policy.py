"""Respect observed free-quota holds; expiry is the next UTC daily reset.

This is a bounded observation, not a live meter or permission to upgrade.
Cloudflare Workers Free remains the provider-side spending boundary.
"""
import datetime as dt
import json
from pathlib import Path

OBSERVATIONS = Path(__file__).with_name('quota-observations.json')


def hold(now, account, path=OBSERVATIONS):
    if now.tzinfo is None:
        raise ValueError('quota_clock_timezone')
    data = json.loads(path.read_text())
    if data.get('schemaVersion') != 1 or not isinstance(data.get('holds'), list):
        raise ValueError('quota_observation_schema')
    active=[]
    for item in data['holds']:
        if item['accountId'] != account:
            continue
        observed=dt.datetime.fromisoformat(item['observedAt'].replace('Z','+00:00'))
        resume=dt.datetime.fromisoformat(item['resumeAt'].replace('Z','+00:00'))
        if observed.tzinfo is None or resume.tzinfo is None:
            raise ValueError('quota_observation_timezone')
        next_reset=dt.datetime.combine(observed.astimezone(dt.timezone.utc).date()+dt.timedelta(days=1),dt.time(),dt.timezone.utc)
        if resume != next_reset:
            raise ValueError('quota_hold_exceeds_daily_reset')
        if observed <= now < resume:
            active.append(item)
    if not active:
        return None
    latest=max(active,key=lambda item:item['observedAt'])
    return {'status':'free_quota_hold','resumeAt':latest['resumeAt'],
            'observedAt':latest['observedAt'],'usageDisplay':latest['usageDisplay'],
            'reason':'preserve_free_quota_until_daily_reset','liveQuotaMeter':False}
