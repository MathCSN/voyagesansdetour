import json
from pathlib import Path
import tempfile
import unittest
from pin_feed_status import compare

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
