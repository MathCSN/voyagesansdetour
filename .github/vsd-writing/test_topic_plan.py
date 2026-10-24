import datetime as dt
import json
import unittest
from pathlib import Path
import guide_photos
import topic_plan as t
import editorial_queue as q
from test_guide_draft import topic

TOPICS=Path(__file__).with_name('guide-topics.json')
DESTINATIONS=Path(__file__).resolve().parents[2]/'site-src'/'destinations.json'


class SeasonTests(unittest.TestCase):
    def test_two_or_three_months_before_the_season_wins(self):
        winter=dict(topic(),slug='laponie',travelMonths=[12,1,2,3],priority=60)
        spring=dict(topic(),slug='kyoto',travelMonths=[3,4],priority=60)
        october=dt.datetime(2026,10,10,tzinfo=q.UTC)
        self.assertEqual([x['slug'] for x in t.ranked([spring,winter],[],october)],['laponie','kyoto'])
        january=dt.datetime(2027,1,10,tzinfo=q.UTC)
        self.assertEqual([x['slug'] for x in t.ranked([spring,winter],[],january)],['kyoto','laponie'])
    def test_priority_still_counts_out_of_season(self):
        low=dict(topic(),slug='bas',travelMonths=[7],priority=10)
        high=dict(topic(),slug='haut',travelMonths=[7],priority=90)
        self.assertEqual(t.ranked([low,high],[],dt.datetime(2026,10,10,tzinfo=q.UTC))[0]['slug'],'haut')
    def test_morning_and_afternoon_runs_try_different_topics(self):
        topics=[dict(topic(),slug='s'+str(i),priority=50) for i in range(4)]
        morning=dt.datetime(2026,10,10,6,23,tzinfo=q.UTC)
        picks={t.select(topics,[],morning)['slug'],t.select(topics,[],morning.replace(hour=15))['slug']}
        self.assertEqual(len(picks),2)
        week={t.select(topics,[],morning+dt.timedelta(hours=12*n))['slug'] for n in range(6)}
        self.assertEqual(week,{'s0','s1','s2'})


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.topics=json.loads(TOPICS.read_text())
    def test_plan_is_large_worldwide_and_valid(self):
        self.assertGreaterEqual(len(self.topics),60)
        for item in self.topics:
            with self.subTest(topic=item['slug']):
                t.validate_topic(item)
                for spec in item['photos']:guide_photos.validate_spec(spec)
        continents={item['continent'] for item in self.topics}
        self.assertTrue({'europe','asie','afrique','oceanie'}<=continents)
        self.assertTrue(continents & {'amerique-du-nord','amerique-centrale-caraibes','amerique-du-sud'})
        self.assertGreaterEqual(len({item['type'] for item in self.topics}),6)
    def test_every_country_and_continent_is_in_the_destination_catalogue(self):
        if not DESTINATIONS.exists():self.skipTest('destinations.json arrives with the site-monde branch')
        places=json.loads(DESTINATIONS.read_text())
        countries={c['id']:c['continent'] for c in places['countries']}
        for item in self.topics:
            with self.subTest(topic=item['slug']):
                self.assertEqual(countries.get(item['country']),item['continent'])
    def test_photo_ids_are_not_shared_between_topics(self):
        ids=[s['id'] for item in self.topics for s in item['photos'] if 'query' in s]
        self.assertEqual(len(ids),len(set(ids)))
    def test_a_topic_is_ready_today(self):
        self.assertIsNotNone(t.select(self.topics,[],dt.datetime(2026,10,26,6,23,tzinfo=q.UTC)))
