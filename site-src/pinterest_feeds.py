"""Additional reviewed RSS feeds; never move or rewrite the existing Lisbon feed."""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from public_media import approved_files

def build(root,out,origin):
    root,out=Path(root),Path(out)
    config=json.loads((root/'pinterest-additions.json').read_text())
    if config.get('schemaVersion')!=1:raise ValueError('Invalid Pinterest feed schema')
    approved=set(approved_files(root));seen=set();links=set();feeds=set()
    for feed in config['feeds']:
        filename=feed['file']
        if not re.fullmatch(r'[a-z0-9-]+\.xml',filename) or filename=='lisbonne.xml' or filename in feeds:raise ValueError('Invalid or existing feed')
        feeds.add(filename);rss=ET.Element('rss',{'version':'2.0'});channel=ET.SubElement(rss,'channel')
        for tag,text in [('title',feed['title']),('link',origin+'/'),('description',feed['title']),('language','fr')]:ET.SubElement(channel,tag).text=text
        for pin in feed['items']:
            identity=pin['id'];route=pin['linkPath'];media='production/'+pin['mediaId']+'/pin.jpg'
            # A guide may have several Pins, each with its own picture: a variant links with its own campaign tag, so no two items share a link.
            query=pin.get('linkQuery');link=route+('?'+query if query else '')
            if query is not None and query!='utm_source=pinterest&utm_medium=social&utm_content='+identity:raise ValueError('Invalid Pin campaign tag')
            if not re.fullmatch(r'pin-[a-z0-9-]+',identity) or identity in seen or link in links:raise ValueError('Duplicate or invalid Pin')
            seen.add(identity);links.add(link)
            if not re.fullmatch(r'/[a-z]+(?:-[a-z]+)*/[a-z0-9-]+/',route) or not (out/route.strip('/')/'index.html').is_file():raise ValueError('Pin target missing')
            if media not in approved or not (out/'social-media'/media).is_file():raise ValueError('Unapproved Pin media')
            if not 1<=len(pin['title'])<=100 or not 1<=len(pin['description'])<=500:raise ValueError('Pin text length')
            if (pin['width'],pin['height'])!=(1000,1500):raise ValueError('Unqualified Pin dimensions')
            item=ET.SubElement(channel,'item')
            for tag,text in [('title',pin['title']),('description',pin['description']),('link',origin+link)]:ET.SubElement(item,tag).text=text
            ET.SubElement(item,'guid',{'isPermaLink':'false'}).text='urn:vsd:pinterest:'+identity
            url=origin+'/social-media/'+media
            ET.SubElement(item,'enclosure',{'url':url,'length':str((out/'social-media'/media).stat().st_size),'type':'image/jpeg'})
            ET.SubElement(item,'{http://search.yahoo.com/mrss/}content',{'url':url,'type':'image/jpeg','medium':'image','width':'1000','height':'1500'})
        target=out/'pinterest'/filename;target.parent.mkdir(exist_ok=True,parents=True);ET.indent(rss);ET.ElementTree(rss).write(target,encoding='utf-8',xml_declaration=True)
