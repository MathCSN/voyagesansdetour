import json,os,pathlib,re,shutil,subprocess,sys,tempfile,unittest
import xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).parent
ORIGIN='https://voyagesansdetour.fr'
# Sensible à la casse : « quelques jours ailleurs » reste une expression courante, pas l'ancien nom.
OLD_NAMES=re.compile(r'Jours Ailleurs|JOURS AILLEURS|lesjoursailleurs|les-jours-ailleurs|chatgpt\.site')
TEXT_SUFFIXES={'.html','.xml','.txt','.css','.js','.mjs','.vtt'}
LINK=re.compile(r'(?:href|src)="(/[^"#?]*)')
MENTIONS={
    'editeur':{'nom':'Camille Exemple & Fils','statut':'SAS au capital de 1 000 €','immatriculation':'RCS Toulouse 123 456 789','adresse':'1 rue de l’Exemple, 31000 Toulouse','telephone':'05 00 00 00 00','email':'contact@voyagesansdetour.fr','directeur_publication':'Camille Exemple'},
    'hebergeur':{'nom':'GitHub, Inc.','adresse':'88 Colin P. Kelly Jr. Street, San Francisco, CA 94107, États-Unis','telephone':'+1 000 000 0000','site':'https://github.com','confidentialite':'https://docs.github.com/fr/site-policy/privacy-policies/github-general-privacy-statement'},
}

def build(workdir,public,mentions,out=None,analytics=None,source_root=ROOT):
    mentions_file=workdir/'mentions.json'
    if mentions is not None:mentions_file.write_text(json.dumps(mentions,ensure_ascii=False))
    out=out or workdir/('public' if public else 'dist')
    if not public and not out.exists():shutil.copytree(source_root/'dist',out)
    env=dict(os.environ,SITE_OUT=str(out),SITE_ORIGIN=ORIGIN,SITE_MENTIONS=str(mentions_file),LJA_PUBLIC='1' if public else '0')
    env.pop('SITE_ANALYTICS',None)
    if analytics is not None:
        analytics_file=workdir/'analytics-test.json'
        analytics_file.write_text(json.dumps(analytics))
        env['SITE_ANALYTICS']=str(analytics_file)
    result=subprocess.run([sys.executable,str(source_root/'generate.py')],env=env,capture_output=True,text=True)
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
        self.assertEqual(len(ET.parse(self.out/'feed.xml').findall('channel/item')),len(json.loads((ROOT/'articles.json').read_text())))

    def test_new_guide_uses_its_review_and_publication_dates(self):
        route='/portugal/aeroport-porto-centre-ville/'
        article=read(self.out,route)
        self.assertIn('Publié le 27 septembre 2026',article)
        self.assertIn('Sources consultées le 27 septembre 2026',article)
        schemas=json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',article).group(1))
        schema=next(item for item in schemas if item.get('@type')=='Article')
        self.assertEqual(schema['datePublished'],'2026-09-27')
        self.assertEqual(schema['dateModified'],'2026-09-27')
        sitemap=ET.parse(self.out/'sitemap.xml')
        ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
        dates={node.findtext('s:loc',namespaces=ns):node.findtext('s:lastmod',namespaces=ns) for node in sitemap.findall('s:url',ns)}
        self.assertEqual(dates[ORIGIN+route],'2026-09-27')
        self.assertEqual(dates[ORIGIN+'/portugal/'],'2026-09-27')
        self.assertEqual(dates[ORIGIN+'/portugal/porto-3-jours-sans-voiture/'],'2026-09-14')
        items=ET.parse(self.out/'feed.xml').findall('channel/item')
        rss={node.findtext('link'):node.findtext('pubDate') for node in items}
        self.assertEqual(rss[ORIGIN+route],'Sun, 27 Sep 2026 00:00:00 +0000')
        self.assertEqual(rss[ORIGIN+'/portugal/porto-3-jours-sans-voiture/'],'Mon, 14 Sep 2026 12:00:00 +0200')

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

class DestinationImageBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workdir=pathlib.Path(tempfile.mkdtemp(prefix='vsd-destination-images-'))
        cls.addClassCleanup(shutil.rmtree,cls.workdir,True)
        source=cls.workdir/'source'
        source.mkdir()
        for name in ('generate.py','public_media.py','public-media.json','editorial_queue.py','articles.json','image-sources.json',
                     'stay22.py','stay22.json','pinterest-rss.json','analytics.json'):
            shutil.copyfile(ROOT/name,source/name)
        # Only disposable copies receive synthetic articles; the live catalogue and
        # its reviewed release queue are never edited by these regression tests.
        shutil.copytree(ROOT/'dist',source/'dist')
        shutil.copytree(ROOT/'social-media',source/'social-media')
        (source/'editorial-queue.json').write_text(json.dumps({'schemaVersion':1,'drafts':[],'promotions':[]}))
        articles=json.loads((source/'articles.json').read_text())
        cls.destinations={'lisbonne':'Lisbonne','porto':'Porto','sintra':'Sintra',
                          'guimaraes':'Guimarães','inconnue':'Destination inconnue'}
        for key,destination in cls.destinations.items():
            articles.append({
                'slug':'test-image-'+key,'title':'Guide de '+destination,'shortTitle':destination,
                'destination':destination,'category':'Test','description':'Vérification de la couverture.',
                'readMinutes':1,'summary':'Article temporaire de contrôle.',
                'sections':[{'id':'controle','title':'Contrôle','paragraphs':['Texte de test.']}],
                'faq':[],'sources':[{'label':'Source de contrôle','url':'https://www.visitportugal.com/'}],
                'related':['lisbonne-3-jours-sans-voiture'],
            })
        (source/'articles.json').write_text(json.dumps(articles,ensure_ascii=False))
        result,cls.out=build(cls.workdir,True,MENTIONS,source_root=source)
        if result.returncode!=0:raise AssertionError(result.stderr)

    def article_parts(self,key):
        page=read(self.out,'/portugal/test-image-'+key+'/')
        head=page.split('</head>',1)[0]
        cover=re.search(r'<img class="article-cover".*?<p class="photo-credit">.*?</p>',page).group(0)
        schema=json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',page).group(1))
        image=next(item for item in schema if item.get('@type')=='Article')['image']
        return page,head,cover,image

    def test_known_destinations_keep_their_exact_photos_and_credits(self):
        for key in ('lisbonne','porto','sintra'):
            with self.subTest(destination=key):
                _,head,cover,image=self.article_parts(key)
                self.assertIn('src="/assets/'+key+'.jpg"',cover)
                self.assertIn('Photo :',cover)
                self.assertIn('Wikimedia Commons',cover)
                self.assertEqual(image['url'],ORIGIN+'/assets/'+key+'.jpg')
                self.assertEqual(image['encodingFormat'],'image/jpeg')
                self.assertIn('property="og:image:type" content="image/jpeg"',head)

    def test_guimaraes_uses_original_png_for_cover_cards_and_social_metadata(self):
        page,head,cover,image=self.article_parts('guimaraes')
        caption='Guimarães sans voiture — illustration typographique'
        credit='Illustration typographique originale — Voyage Sans Détour'
        self.assertIn('src="/assets/guimaraes-cover.png"',cover)
        self.assertIn('width="1600" height="900"',cover)
        self.assertIn(caption,cover)
        self.assertIn(credit,cover)
        self.assertEqual((image['width'],image['height']),(1600,900))
        self.assertEqual(image['url'],ORIGIN+'/assets/guimaraes-cover.png')
        self.assertEqual(image['encodingFormat'],'image/png')
        self.assertEqual(image['caption'],caption)
        self.assertEqual(image['creditText'],credit)
        self.assertEqual(image['creator'],{'@type':'Organization','name':'Voyage Sans Détour'})
        self.assertNotIn('license',image)
        self.assertIn('property="og:image:type" content="image/png"',head)
        self.assertIn('name="twitter:card" content="summary_large_image"',head)
        for prefix in ('property="og:image"','name="twitter:image"'):
            self.assertIn(prefix+' content="'+image['url']+'"',head)
        card=re.search(r'<a class="card" href="/portugal/test-image-guimaraes/".*?</a>',read(self.out,'/portugal/')).group(0)
        self.assertIn('src="/assets/guimaraes-cover.png"',card)
        self.assertIn(caption,card)
        self.assertIn(credit,read(self.out,'/credits/'))
        self.assertEqual((self.out/'assets/guimaraes-cover.png').read_bytes(),(ROOT/'dist/assets/guimaraes-cover.png').read_bytes())

    def test_unknown_destination_uses_brand_instead_of_a_lisbon_photo(self):
        _,head,cover,image=self.article_parts('inconnue')
        self.assertIn('src="/assets/brand-voyagesansdetour.png"',cover)
        self.assertEqual(image['url'],ORIGIN+'/assets/brand-voyagesansdetour.png')
        self.assertEqual(image['encodingFormat'],'image/png')
        self.assertEqual(image['caption'],'Identité visuelle de Voyage Sans Détour')
        self.assertNotIn('license',image)
        self.assertIn('property="og:image:type" content="image/png"',head)
        self.assertIn('name="twitter:card" content="summary"',head)
        self.assertIn('name="twitter:image" content="'+image['url']+'"',head)
        card=re.search(r'<a class="card" href="/portugal/test-image-inconnue/".*?</a>',read(self.out,'/portugal/')).group(0)
        self.assertIn('src="/assets/brand-voyagesansdetour.png"',card)

    def test_no_photo_is_attributed_to_guimaraes_or_unknown_destination(self):
        for key in ('guimaraes','inconnue'):
            with self.subTest(destination=key):
                page,head,cover,image=self.article_parts(key)
                for section in (head,cover,json.dumps(image)):
                    self.assertNotIn('/assets/lisbonne.jpg',section)
                    self.assertNotIn('Photo :',section)
                    self.assertNotIn('Wikimedia',section)
                # A separately labelled related Lisbon guide may retain its photo.
                self.assertIn('src="/assets/lisbonne.jpg"',page.split('Pour la suite du voyage.',1)[1])

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

class AnalyticsBuildTest(TempDirTest):
    def settings(self,verified):
        return {'measurement_id':'G-9EB7Q36YYM','enabled':True,
                'provider_settings_verified':verified,'provider_settings_verified_at':'2026-09-27' if verified else None}

    def test_provider_settings_are_required_and_preview_stays_untracked(self):
        for public,verified in ((True,False),(False,True)):
            result,out=build(self.workdir,public,MENTIONS,analytics=self.settings(verified))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('data-vsd-analytics',read(out,'/'))

    def test_active_public_pages_only_load_local_consent_code(self):
        result,out=build(self.workdir,True,MENTIONS,analytics=self.settings(True))
        self.assertEqual(result.returncode,0,result.stderr)
        for page in out.rglob('index.html'):
            body=page.read_text()
            self.assertIn('src="/analytics.mjs" data-vsd-analytics data-enabled="true"',body)
            self.assertIn('data-audience-refuse>Tout refuser</button>',body)
            self.assertIn('data-audience-accept>Accepter la mesure d’audience</button>',body)
            self.assertIn('data-audience-settings',body)
            self.assertNotRegex(body,r'<(?:script|link)[^>]+(?:src|href)="https://(?:www\.)?(?:google|googletagmanager)')
            self.assertNotRegex(body,r'rel="(?:preconnect|dns-prefetch|prefetch)"')
        self.assertNotIn('data-vsd-analytics',(out/'404.html').read_text())
        self.assertTrue((out/'analytics.mjs').is_file())
        privacy=read(out,'/confidentialite/')
        self.assertIn('180 jours',privacy)
        self.assertIn('retirer votre accord',privacy)
        self.assertNotIn('n’utilise aucun cookie',privacy)

if __name__=='__main__':
    unittest.main()
