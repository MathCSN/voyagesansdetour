"""Which guide to write next: research priority plus a seasonal boost, never a fixed order.

Each topic carries a priority (French search demand and competition, see
docs/strategie-sujets.md) and the months its readers travel. A guide is worth most
2 to 3 months before that season: it has time to be indexed before the searches peak.
"""
import urllib.parse
from source_draft import require
import editorial_queue as q

TYPES={'itineraire':'Itinéraires','quand-partir':'Quand partir','budget':'Budget','ou-dormir':'Où dormir',
       'road-trip':'Road trips','que-faire':'Que faire','transport':'Transports','visite':'Visites','excursion':'Excursions'}
TOPIC_KEYS={'slug','destination','country','continent','type','question','travelMonths','priority','sources','photos'}
OPTIONAL_KEYS={'category','cover','demand','keywords'}
# Months between today and the next travel month -> boost. Ideal: 2 to 3 months ahead.
SEASON_BOOST={0:5,1:20,2:30,3:30,4:10}
# The best few topics share the calendar, so one held topic never blocks the others.
WINDOW=3


def validate_topic(topic):
    require(isinstance(topic,dict) and TOPIC_KEYS<=set(topic)<=TOPIC_KEYS|OPTIONAL_KEYS,'guide_topic_schema')
    require(q.SLUG.fullmatch(topic['slug']) and 2<=len(topic['sources'])<=3,'guide_topic_schema')
    require(isinstance(topic['country'],str) and q.SLUG.fullmatch(topic['country']),'guide_topic_country')
    require(isinstance(topic['continent'],str) and q.SLUG.fullmatch(topic['continent']),'guide_topic_continent')
    require(topic['type'] in TYPES,'guide_topic_type')
    require(isinstance(topic['destination'],str) and 2<=len(topic['destination'])<=60,'guide_topic_destination')
    require(isinstance(topic['question'],str) and 20<=len(topic['question'])<=600,'guide_topic_question')
    months=topic['travelMonths']
    require(isinstance(months,list) and months and len(set(months))==len(months) and all(type(m) is int and 1<=m<=12 for m in months),'guide_topic_months')
    require(type(topic['priority']) is int and 0<=topic['priority']<=100,'guide_topic_priority')
    require(isinstance(topic['photos'],list) and 3<=len(topic['photos'])<=6,'guide_topic_photos')
    keywords=topic.get('keywords',[])
    require(isinstance(keywords,list) and len(keywords)<=12 and all(isinstance(w,str) and 1<=len(w)<=40 for w in keywords),'guide_topic_keywords')
    for source in topic['sources']:
        require(isinstance(source,dict) and set(source)=={'label','url'} and isinstance(source['label'],str) and source['label'],'guide_topic_source')
        url=urllib.parse.urlsplit(source['url'])
        # Hosts are reviewed with the topic file itself; page contents never add a host.
        require(url.scheme=='https' and url.hostname and not url.username and not url.password and not url.query and not url.fragment,'guide_source_outside_scope')
    require(len({s['url'] for s in topic['sources']})==len(topic['sources']),'guide_topic_source')
    return topic


def months_ahead(month,travel):
    return min((m-month)%12 for m in travel)


def score(topic,now):
    month=now.astimezone(q.PARIS).month
    return topic['priority']+SEASON_BOOST.get(months_ahead(month,topic['travelMonths']),0)


def ranked(topics,known,now):
    slugs={a['slug'] for a in known}
    for topic in topics:validate_topic(topic)
    require(len({t['slug'] for t in topics})==len(topics),'guide_topic_duplicate')
    remaining=[t for t in topics if t['slug'] not in slugs]
    return sorted(remaining,key=lambda t:(-score(t,now),t['slug']))


def select(topics,known,now):
    """Top topics rotate twice a day: a morning hold is not retried the same afternoon."""
    order=ranked(topics,known,now)
    if not order:return None
    window=order[:WINDOW]
    turn=now.date().toordinal()*2+(now.astimezone(q.UTC).hour>=12)
    return window[turn%len(window)]
