import json,os,pathlib,re,shutil,subprocess,sys,tempfile,unittest
import xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).parent
ORIGIN='https://voyagesansdetour.fr'
# Sensible à la casse : « quelques jours ailleurs » reste une expression courante, pas l'ancien nom.
OLD_NAMES=re.compile(r'Jours Ailleurs|JOURS AILLEURS|lesjoursailleurs|les-jours-ailleurs|chatgpt\.site')
TEXT_SUFFIXES={'.html','.xml','.txt','.css','.js','.vtt'}
LINK=re.compile(r'(?:href|src)="(/[^"#?]*)')
MENTIONS={
    'editeur':{'nom':'Camille Exemple & Fils','statut':'SAS au capital de 1 000 €','immatriculation':'RCS Toulouse 123 456 789','adresse':'1 rue de l’Exemple, 31000 Toulouse','telephone':'05 00 00 00 00','email':'contact@voyagesansdetour.fr','directeur_publication':'Camille Exemple'},
    'hebergeur':{'nom':'GitHub, Inc.','adresse':'88 Colin P. Kelly Jr. Street, San Francisco, CA 94107, États-Unis','telephone':'+1 000 000 0000','site':'https://github.com','confidentialite':'https://docs.github.com/fr/site-policy/privacy-policies/github-general-privacy-statement'},
}

def build(workdir,public,mentions,out=None):
    mentions_file=workdir/'mentions.json'
    if mentions is not None:mentions_file.write_text(json.dumps(mentions,ensure_ascii=False))
    out=out or workdir/('public' if public else 'dist')
    if not public and not out.exists():shutil.copytree(ROOT/'dist',out)
    env=dict(os.environ,SITE_OUT=str(out),SITE_ORIGIN=ORIGIN,SITE_MENTIONS=str(mentions_file),LJA_PUBLIC='1' if public else '0')
    result=subprocess.run([sys.executable,str(ROOT/'generate.py')],env=env,capture_output=True,text=True)
    return result,out

def text_files(out):
    return [p for p in out.rglob('*') if p.is_file() and p.suffix in TEXT_SUFFIXES]

def read(out,route):
    return (out/route.strip('/')/'index.html').read_text() if route!='/' else (out/'index.html').read_text()

class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.workdir=pathlib.Path(tempfile.mkdtemp(prefix='vsd-test-'))
        self.addCleanup(shutil.rmtree,self.workdir,True)

class PublicBuildSafetyTest(TempDirTest):
    def test_refuses_public_build_without_mentions_file(self):
        result,out=build(self.workdir,True,None)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('mentions légales incomplètes',result.stderr)
        self.assertFalse(out.exists())

    def test_refuses_public_build_with_placeholder_values(self):
        incomplete=json.loads(json.dumps(MENTIONS))
        incomplete['editeur']['adresse']='À COMPLÉTER'
        incomplete['editeur']['statut']='SAS au capital de À COMPLÉTER €'
        incomplete['hebergeur']['telephone']=''
        result,_=build(self.workdir,True,incomplete)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('editeur.adresse',result.stderr)
        self.assertIn('editeur.statut',result.stderr)
        self.assertIn('hebergeur.telephone',result.stderr)

    def test_refuses_to_delete_a_folder_it_did_not_create(self):
        foreign=self.workdir/'autre-dossier'
        foreign.mkdir()
        (foreign/'important.txt').write_text('à garder')
        result,_=build(self.workdir,True,MENTIONS,out=foreign)
        self.assertNotEqual(result.returncode,0)
        self.assertTrue((foreign/'important.txt').exists())

    def test_rebuild_replaces_previous_public_output(self):
        first,out=build(self.workdir,True,MENTIONS)
        self.assertEqual(first.returncode,0,first.stderr)
        (out/'ancien-fichier.html').write_text('stale')
        second,_=build(self.workdir,True,MENTIONS)
        self.assertEqual(second.returncode,0,second.stderr)
        self.assertFalse((out/'ancien-fichier.html').exists())

class PublicBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workdir=pathlib.Path(tempfile.mkdtemp(prefix='vsd-public-'))
        cls.result,cls.out=build(cls.workdir,True,MENTIONS)
        if cls.result.returncode!=0:
            shutil.rmtree(cls.workdir,True)
            raise AssertionError('La génération publique a échoué : '+cls.result.stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir,True)

    def test_publishes_no_old_brand_or_preview_url(self):
        offenders=[str(p.relative_to(self.out)) for p in text_files(self.out) if OLD_NAMES.search(p.read_text())]
        self.assertEqual(offenders,[])

    def test_demo_reels_are_not_published(self):
        self.assertEqual(list((self.out/'assets').glob('reel-*')),[])
        self.assertFalse((self.out/'formats-courts').exists())
        linked=[str(p.relative_to(self.out)) for p in self.out.rglob('*.html') if '/formats-courts/' in p.read_text() or 'reel-0' in p.read_text()]
        self.assertEqual(linked,[])

    def test_only_approved_social_files_are_copied_unchanged(self):
        expected={'pin-01-lisbonne-3-jours.jpg','pin-02-porto-3-jours.jpg',
                  'pin-03-ou-dormir-lisbonne.jpg','pin-04-lisbonne-ou-porto.jpg',
                  'reel-01-lisbonne-ou-porto.mp4','reel-02-lisbonne-3-jours.mp4','credits.txt'}
        folder=self.out/'social-media'/'lancement-2026-09'
        self.assertEqual({p.name for p in folder.iterdir()},expected)
        for name in expected:
            self.assertEqual((folder/name).read_bytes(),(ROOT/'social-media'/'lancement-2026-09'/name).read_bytes())

    def test_pinterest_rss_has_only_the_approved_lisbon_pin(self):
        rss=ET.parse(self.out/'pinterest/lisbonne.xml').getroot()
        self.assertEqual(rss.tag,'rss')
        self.assertEqual(rss.get('version'),'2.0')
        items=rss.findall('channel/item')
        self.assertEqual(len(items),1)
        item=items[0]
        self.assertEqual(item.findtext('title'),'Lisbonne en 3 jours sans voiture : un quartier par jour')
        self.assertEqual(item.findtext('link'),ORIGIN+'/portugal/lisbonne-3-jours-sans-voiture/')
        self.assertEqual(item.findtext('guid'),'urn:vsd:pinterest:pin-01-lisbonne-3-jours')
        self.assertEqual(item.find('guid').get('isPermaLink'),'false')
        self.assertIsNone(item.find('pubDate'))
        self.assertIsNone(rss.find('channel/lastBuildDate'))
        description=item.findtext('description')
        self.assertLessEqual(len(description),500)
        for credit in ('SIryn / Wikimedia Commons','Recadrage et composition','CC BY-SA 4.0',
                       'https://creativecommons.org/licenses/by-sa/4.0/',ORIGIN+'/credits/'):
            self.assertIn(credit,description)
        image_path='/social-media/lancement-2026-09/pin-01-lisbonne-3-jours.jpg'
        enclosure=item.find('enclosure')
        media=item.find('{http://search.yahoo.com/mrss/}content')
        for node in (enclosure,media):
            self.assertEqual(node.get('url'),ORIGIN+image_path)
            self.assertEqual(node.get('type'),'image/jpeg')
        self.assertEqual(int(enclosure.get('length')),(self.out/image_path.lstrip('/')).stat().st_size)
        self.assertEqual((media.get('width'),media.get('height')),('1000','1500'))
        self.assertEqual(len(ET.parse(self.out/'feed.xml').findall('channel/item')),6)

    def test_every_internal_link_resolves(self):
        broken=set()
        for page in self.out.rglob('*.html'):
            for url in LINK.findall(page.read_text()):
                if url.startswith('//'):continue
                target=self.out/url.lstrip('/')
                if url.endswith('/'):target=target/'index.html'
                if not target.is_file():broken.add(f'{page.relative_to(self.out)} -> {url}')
        self.assertEqual(sorted(broken),[])

    def test_pages_are_indexable_except_404(self):
        blocked=[str(p.relative_to(self.out)) for p in self.out.rglob('*.html') if 'noindex' in p.read_text() and p.name!='404.html']
        self.assertEqual(blocked,[])
        self.assertIn('noindex',(self.out/'404.html').read_text())

    def test_canonical_urls_sitemap_and_robots_use_the_domain(self):
        for page in self.out.rglob('index.html'):
            canonical=re.search(r'<link rel="canonical" href="([^"]+)"',page.read_text()).group(1)
            self.assertTrue(canonical.startswith(ORIGIN+'/'),canonical)
        locations=re.findall(r'<loc>([^<]+)</loc>',(self.out/'sitemap.xml').read_text())
        self.assertTrue(locations)
        self.assertTrue(all(loc.startswith(ORIGIN+'/') for loc in locations))
        robots=(self.out/'robots.txt').read_text()
        self.assertNotIn('Disallow: /',robots)
        self.assertIn(f'Sitemap: {ORIGIN}/sitemap.xml',robots)

    def test_github_pages_files_are_present(self):
        self.assertEqual((self.out/'CNAME').read_text().strip(),'voyagesansdetour.fr')
        self.assertTrue((self.out/'.nojekyll').exists())
        self.assertTrue((self.out/'style.css').is_file())
        self.assertTrue((self.out/'assets'/'lisbonne.jpg').is_file())

    def test_legal_notice_shows_escaped_editor_and_host(self):
        page=read(self.out,'/mentions-legales/')
        self.assertIn('Camille Exemple &amp; Fils',page)
        self.assertIn('SAS au capital de 1 000 €<br>RCS Toulouse 123 456 789',page)
        self.assertIn('Directeur de la publication',page)
        self.assertIn('GitHub, Inc.',page)
        self.assertIn('+1 000 000 0000',page)
        self.assertNotIn('préversion',page.lower())

    def test_privacy_page_names_the_host_and_contact(self):
        page=read(self.out,'/confidentialite/')
        self.assertIn('hébergé par GitHub, Inc.',page)
        self.assertIn('mailto:contact@voyagesansdetour.fr',page)

class PreviewBuildTest(TempDirTest):
    def test_preview_is_not_indexable_and_keeps_demo_page(self):
        result,out=build(self.workdir,False,None)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Disallow: /',(out/'robots.txt').read_text())
        self.assertIn('noindex',read(out,'/'))
        self.assertTrue((out/'formats-courts'/'index.html').is_file())

    def test_preview_without_mentions_shows_prelaunch_notice(self):
        result,out=build(self.workdir,False,None)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('avant le lancement public',read(out,'/mentions-legales/'))

if __name__=='__main__':
    unittest.main()
