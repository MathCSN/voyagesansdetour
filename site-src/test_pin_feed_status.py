import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pin_feed_status import compare
import pinterest_feeds

class FeedStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        config={'feeds':[{'file':'preparation.xml','items':[{'id':'pin-guide','title':'Guide','description':'Description','linkPath':'/portugal/guide/','mediaId':'pin-guide'}]}]}
        (self.root/'pinterest-additions.json').write_text(json.dumps(config))
        self.xml=b'<rss><channel><item><guid>urn:vsd:pinterest:pin-guide</guid><title>Guide</title><description>Description</description><link>https://voyagesansdetour.fr/portugal/guide/</link><enclosure url="https://voyagesansdetour.fr/social-media/production/pin-guide/pin.jpg"/></item></channel></rss>'
    def test_published_feed_does_not_redeploy(self):self.assertEqual(compare(self.root,lambda u:self.xml)['status'],'current')
    def test_missing_item_requests_deployment_without_recreating_item(self):self.assertTrue(compare(self.root,lambda u:b'<rss><channel/></rss>')['needsDeployment'])
    def test_http404_requests_deployment(self):self.assertTrue(compare(self.root,lambda u:None)['needsDeployment'])
    def test_transient_error_never_means_missing(self):
        def unavailable(url):raise TimeoutError()
        self.assertEqual(compare(self.root,unavailable),{'status':'unavailable','needsDeployment':False,'errorType':'TimeoutError'})
    def test_conflicting_existing_guid_is_held(self):self.assertEqual(compare(self.root,lambda u:self.xml.replace(b'<title>Guide',b'<title>Wrong'))['status'],'conflict')
    def test_invalid_rss_is_not_missing(self):self.assertFalse(compare(self.root,lambda u:b'<html/>')['needsDeployment'])
    def test_a_variant_pin_is_current_only_with_its_campaign_tag(self):
        tag='utm_source=pinterest&utm_medium=social&utm_content=pin-guide-b'
        config={'feeds':[{'file':'preparation.xml','items':[{'id':'pin-guide-b','title':'Guide','description':'Description','linkPath':'/portugal/guide/','linkQuery':tag,'mediaId':'pin-guide-b'}]}]}
        (self.root/'pinterest-additions.json').write_text(json.dumps(config))
        xml=self.xml.replace(b'pin-guide',b'pin-guide-b')
        self.assertEqual(compare(self.root,lambda u:xml)['status'],'conflict')
        tagged=xml.replace(b'/portugal/guide/</link>',b'/portugal/guide/?'+tag.replace('&','&amp;').encode()+b'</link>')
        self.assertEqual(compare(self.root,lambda u:tagged)['status'],'current')

class FeedBuildTests(unittest.TestCase):
    ORIGIN='https://voyagesansdetour.fr'
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'site';self.out=Path(self.temp.name)/'out';self.root.mkdir()
        (self.out/'portugal/guide').mkdir(parents=True);(self.out/'portugal/guide/index.html').write_text('<html/>')
        self.media=[];self.pins=[]
    def pin(self,identity,**extra):
        files=[]
        for name in ('pin.jpg','credits.txt','dmsans-OFL.txt','playfairdisplay-OFL.txt'):
            data=(identity+name).encode()
            for base in (self.root,self.out):
                (base/'social-media/production'/identity).mkdir(parents=True,exist_ok=True);(base/'social-media/production'/identity/name).write_bytes(data)
            files.append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        self.media.append({'contentId':identity,'kind':'pin','approved':True,'files':files})
        self.pins.append({'id':identity,'title':'Titre '+identity,'description':'Description','linkPath':'/portugal/guide/','mediaId':identity,'width':1000,'height':1500,**extra})
    def build(self):
        (self.root/'public-media.json').write_text(json.dumps({'schemaVersion':1,'items':self.media}))
        (self.root/'pinterest-additions.json').write_text(json.dumps({'schemaVersion':1,'feeds':[{'file':'preparer-portugal.xml','title':'Portugal','items':self.pins}]}))
        pinterest_feeds.build(self.root,self.out,self.ORIGIN)
        return [item.findtext('link') for item in ET.parse(self.out/'pinterest/preparer-portugal.xml').getroot().iter('item')]
    def test_several_pins_of_one_guide_are_published_each_with_its_own_link(self):
        tag='utm_source=pinterest&utm_medium=social&utm_content=pin-guide-b'
        self.pin('pin-guide');self.pin('pin-guide-b',linkQuery=tag)
        self.assertEqual(self.build(),[self.ORIGIN+'/portugal/guide/',self.ORIGIN+'/portugal/guide/?'+tag])
    def test_two_pins_with_the_same_link_are_refused(self):
        self.pin('pin-guide');self.pin('pin-guide-b')
        with self.assertRaisesRegex(ValueError,'Duplicate or invalid Pin'):self.build()
    def test_a_campaign_tag_cannot_carry_anything_else(self):
        self.pin('pin-guide-b',linkQuery='utm_source=pinterest&utm_medium=social&utm_content=pin-guide-b&next=https://example.org')
        with self.assertRaisesRegex(ValueError,'Invalid Pin campaign tag'):self.build()
