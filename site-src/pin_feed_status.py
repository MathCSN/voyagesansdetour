"""Compare committed Pin feed items with public RSS, without sending any Pin."""
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
ORIGIN='https://voyagesansdetour.fr'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('feed_redirect')

def fetch(url):
    try:
        with urllib.request.build_opener(NoRedirect()).open(url,timeout=15) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError('feed_too_large')
            return raw
    except urllib.error.HTTPError as error:
        if error.code==404:return None
        raise

def compare(root,fetcher=fetch):
    path=Path(root)/'pinterest-additions.json'
    if not path.exists():return {'status':'not_configured','needsDeployment':False}
    config=json.loads(path.read_text());missing=[]
    try:
        for feed in config['feeds']:
            filename=feed['file']
            if not re.fullmatch(r'[a-z0-9-]+\.xml',filename):raise ValueError('invalid_filename')
            raw=fetcher(ORIGIN+'/pinterest/'+filename)
            if raw is None:missing.append(filename);continue
            tree=ET.fromstring(raw)
            if tree.tag!='rss' or tree.find('channel') is None:raise ValueError('invalid_rss')
            items=tree.findall('channel/item');indexed={i.findtext('guid'):i for i in items}
            if len(indexed)!=len(items) or None in indexed:raise ValueError('duplicate_or_missing_guid')
            for pin in feed['items']:
                guid='urn:vsd:pinterest:'+pin['id'];item=indexed.get(guid)
                if item is None:missing.append(guid);continue
                enclosure=item.find('enclosure')
                if (item.findtext('title')!=pin['title'] or item.findtext('description')!=pin['description'] or item.findtext('link')!=ORIGIN+pin['linkPath'] or enclosure is None or enclosure.get('url')!=ORIGIN+'/social-media/production/'+pin['mediaId']+'/pin.jpg'):
                    return {'status':'conflict','needsDeployment':False,'id':pin['id']}
        return {'status':'missing' if missing else 'current','needsDeployment':bool(missing),'missing':missing}
    except (OSError,ValueError,ET.ParseError,KeyError,TypeError) as error:
        return {'status':'unavailable','needsDeployment':False,'errorType':type(error).__name__}

if __name__=='__main__':print(json.dumps(compare(Path(__file__).parent)))
