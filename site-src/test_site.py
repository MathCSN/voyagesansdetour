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

    def test_preparation_feed_contains_reviewed_baggage_pin(self):
        rss=ET.parse(self.out/'pinterest/preparer-portugal.xml').getroot()
        # New Pins join this feed every week: the reviewed baggage Pin must stay, not stay alone.
        items={item.findtext('guid'):item for item in rss.findall('channel/item')}
        pin=items['urn:vsd:pinterest:pin-portugal-sans-voiture-bagages']
        self.assertEqual(pin.findtext('link'),ORIGIN+'/portugal/portugal-sans-voiture-bagages/')
        self.assertIn('assistée par IA',pin.findtext('description'))
        media=pin.find('{http://search.yahoo.com/mrss/}content')
        self.assertEqual((media.get('width'),media.get('height')),('1000','1500'))
        self.assertTrue((self.out/media.get('url').removeprefix(ORIGIN+'/')).is_file())

    def test_pinterest_rss_preserves_published_pins_and_adds_reviewed_sintra(self):
        rss=ET.parse(self.out/'pinterest/lisbonne.xml').getroot()
        self.assertEqual(rss.tag,'rss')
        self.assertEqual(rss.get('version'),'2.0')
        items=rss.findall('channel/item')
        self.assertEqual(len(items),3)
        self.assertIsNone(rss.find('channel/lastBuildDate'))
        expected=(
            ('pin-01-lisbonne-3-jours','Lisbonne en 3 jours sans voiture : un quartier par jour',
             '/portugal/lisbonne-3-jours-sans-voiture/',
             '/social-media/lancement-2026-09/pin-01-lisbonne-3-jours.jpg'),
            ('pin-03-ou-dormir-lisbonne','Où dormir à Lisbonne sans voiture ? Bien choisir son quartier',
             '/portugal/ou-dormir-lisbonne-quartiers/',
             '/social-media/lancement-2026-09/pin-03-ou-dormir-lisbonne.jpg'),
        )
        expected += (('pin-05-sintra-trois-temps','Sintra depuis Lisbonne sans voiture : préparer la visite de Pena','/portugal/sintra-depuis-lisbonne/','/social-media/production/sintra-facebook-2026-10/scene-01.jpg'),)
        for item,(id,title,link,image_path) in zip(items,expected):
            self.assertEqual(item.findtext('title'),title)
            self.assertEqual(item.findtext('link'),ORIGIN+link)
            self.assertEqual(item.findtext('guid'),'urn:vsd:pinterest:'+id)
            self.assertEqual(item.find('guid').get('isPermaLink'),'false')
            self.assertIsNone(item.find('pubDate'))
            description=item.findtext('description')
            self.assertLessEqual(len(description),500)
            for credit in (() if id=='pin-05-sintra-trois-temps' else ('SIryn / Wikimedia Commons','Recadrage et composition','CC BY-SA 4.0',
                           'https://creativecommons.org/licenses/by-sa/4.0/',ORIGIN+'/credits/')):
                self.assertIn(credit,description)
            if id=='pin-03-ou-dormir-lisbonne':
                self.assertIn('Baixa, Chiado, Alfama ou Cais do Sodré ?',description)
            enclosure=item.find('enclosure')
            media=item.find('{http://search.yahoo.com/mrss/}content')
            for node in (enclosure,media):
                self.assertEqual(node.get('url'),ORIGIN+image_path)
                self.assertEqual(node.get('type'),'image/jpeg')
            self.assertEqual(int(enclosure.get('length')),(self.out/image_path.lstrip('/')).stat().st_size)
            self.assertEqual((media.get('width'),media.get('height')),('1080','1920') if id=='pin-05-sintra-trois-temps' else ('1000','1500'))
            if id=='pin-05-sintra-trois-temps':
                self.assertIn('Composition typographique originale',description)
                self.assertIn('/sintra-facebook-2026-10/credits.txt',description)
        self.assertEqual(len(ET.parse(self.out/'feed.xml').findall('channel/item')),len(json.loads((ROOT/'articles.json').read_text())))

    def test_guides_keep_their_publication_date_and_show_their_review_date(self):
        route='/portugal/aeroport-porto-centre-ville/'
        catalogue=json.loads((ROOT/'articles.json').read_text())
        guide=next(a for a in catalogue if a['slug']=='aeroport-porto-centre-ville')
        article=read(self.out,route)
        # The original publication date survives an enrichment; the review date follows it.
        self.assertIn('Publié le 27 septembre 2026',article)
        self.assertEqual(guide['publishedOn'],'2026-09-27')
        schemas=json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',article).group(1))
        schema=next(item for item in schemas if item.get('@type')=='Article')
        self.assertEqual(schema['datePublished'],'2026-09-27')
        self.assertEqual(schema['dateModified'],guide['updatedOn'])
        sitemap=ET.parse(self.out/'sitemap.xml')
        ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
        dates={node.findtext('s:loc',namespaces=ns):node.findtext('s:lastmod',namespaces=ns) for node in sitemap.findall('s:url',ns)}
        for item in catalogue:
            path='/'+item.get('country','portugal')+'/'+item['slug']+'/'
            self.assertEqual(dates[ORIGIN+path],item.get('updatedOn','2026-09-14'))
        for country in {item.get('country','portugal') for item in catalogue}:
            latest=max(a.get('updatedOn','2026-09-14') for a in catalogue if a.get('country','portugal')==country)
            self.assertEqual(dates[ORIGIN+'/'+country+'/'],latest)
        items=ET.parse(self.out/'feed.xml').findall('channel/item')
        rss={node.findtext('link'):node.findtext('pubDate') for node in items}
        self.assertEqual(rss[ORIGIN+route],'Sun, 27 Sep 2026 00:00:00 +0000')
        self.assertEqual(rss[ORIGIN+'/portugal/porto-3-jours-sans-voiture/'],'Mon, 14 Sep 2026 12:00:00 +0200')

    def test_new_destinations_get_country_hubs_breadcrumbs_and_faq_schema(self):
        page=read(self.out,'/italie/cinque-terre-sans-voiture/')
        self.assertIn('<a href="/italie/">Italie</a>',page)
        schemas=json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',page).group(1))
        types={item.get('@type') for item in schemas}
        self.assertTrue({'Article','BreadcrumbList','FAQPage'}<=types)
        crumbs=next(item for item in schemas if item.get('@type')=='BreadcrumbList')['itemListElement']
        self.assertEqual([c['item'] for c in crumbs[:3]],[ORIGIN+'/',ORIGIN+'/europe/',ORIGIN+'/italie/'])
        for hub in ('/portugal/','/espagne/','/italie/'):
            self.assertIn('class="grid" id="guide-grid"',read(self.out,hub))
        self.assertIn('class="key-facts"',page)
        self.assertIn('class="inline-photo"',page)

    def test_home_shows_destinations_latest_guides_and_dated_figures(self):
        home=read(self.out,'/')
        self.assertIn('id="destinations"',home)
        for name in ('Algarve','Douro','Andalousie','Côte amalfitaine','Cinque Terre'):
            self.assertIn('<strong>'+name+'</strong>',home)
        self.assertIn('class="facts"',home)
        self.assertNotIn('Le Portugal, à votre rythme',home)

    def test_home_and_menu_speak_to_a_world_travel_blog(self):
        home=read(self.out,'/')
        nav=re.search(r'<nav class="nav".*?</nav>',home).group(0)
        self.assertIn('<a href="/europe/">Europe</a>',nav)
        self.assertIn('<a href="/destinations/">Destinations</a>',nav)
        self.assertNotIn('/portugal/',nav)
        for retired in ('Prenez le train','Zéro volant','0 VOITURE','EN TRAIN, EN FERRY'):
            self.assertNotIn(retired,home)
        self.assertIn('Destinations à la une.',home)
        self.assertIn('id="rubriques"',home)
        self.assertIn('href="/guides/itineraires/"',home)
        self.assertIn('class="chip" href="/portugal/"',home)
        about=read(self.out,'/a-propos/')
        self.assertIn('partout dans le monde',about)
        self.assertNotIn('Nos dossiers couvrent le Portugal',about)
        self.assertNotIn('sans voiture',(self.out/'feed.xml').read_text().split('<item>',1)[0])

    def test_hubs_exist_for_countries_continents_rubriques_and_all_guides(self):
        catalogue=json.loads((ROOT/'articles.json').read_text())
        for route in ('/destinations/','/guides/','/europe/','/guides/itineraires/','/guides/ou-dormir/'):
            with self.subTest(route=route):
                self.assertIn('<nav class="breadcrumb"',read(self.out,route))
        self.assertEqual(read(self.out,'/guides/').count('<a class="card"'),len(catalogue))
        europe=read(self.out,'/europe/')
        for country in ('/portugal/','/espagne/','/italie/'):
            self.assertIn(f'class="destination" href="{country}"',europe)
        portugal=read(self.out,'/portugal/')
        self.assertIn('<h1>Voyager au Portugal.</h1>',portugal)
        self.assertIn('<a href="/europe/">Europe</a> / Portugal</nav>',portugal)
        locations=set(re.findall(r'<loc>([^<]+)</loc>',(self.out/'sitemap.xml').read_text()))
        for route in ('/destinations/','/guides/','/europe/','/guides/itineraires/'):
            self.assertIn(ORIGIN+route,locations)

    def test_no_ai_generated_image_is_published(self):
        # Règle de Mathis : uniquement de vraies photos (catalogue sous licence libre) et le logo.
        self.assertFalse((self.out/'assets'/'alma.jpg').exists())
        allowed={'/assets/'+p['file'] for p in json.loads((ROOT/'image-sources.json').read_text())['photos'] if 'file' in p}
        allowed|={'/assets/'+p['file'].replace('.jpg','-800.jpg') for p in json.loads((ROOT/'image-sources.json').read_text())['photos'] if 'file' in p}
        allowed|={'/assets/lisbonne.jpg','/assets/porto.jpg','/assets/sintra.jpg','/assets/brand-voyagesansdetour.png'}
        for page in self.out.rglob('*.html'):
            body=page.read_text()
            self.assertNotIn('image_gen',body)
            self.assertNotIn('Alma',body)
            for src in re.findall(r'<img [^>]*src="(/assets/[^"]+)"',body):
                self.assertIn(src,allowed,f'{page.relative_to(self.out)} : {src}')

    def test_existing_guide_urls_are_unchanged(self):
        for item in json.loads((ROOT/'articles.json').read_text()):
            route='/'+item.get('country','portugal')+'/'+item['slug']+'/'
            with self.subTest(route=route):
                self.assertTrue((self.out/route.strip('/')/'index.html').is_file())

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
        self.assertIn('SAS au capital de 1 000\u00a0€<br>RCS Toulouse 123 456 789',page)
        self.assertIn('Directeur de la publication',page)
        self.assertIn('GitHub, Inc.',page)
        self.assertIn('+1 000 000 0000',page)
        self.assertNotIn('préversion',page.lower())

    def test_privacy_page_names_the_host_and_contact(self):
        page=read(self.out,'/confidentialite/')
        self.assertIn('hébergé par GitHub, Inc.',page)
        self.assertIn('mailto:contact@voyagesansdetour.fr',page)

def synthetic_guide(slug,destination,**fields):
    return dict({'slug':slug,'title':'Guide de '+destination,'shortTitle':destination,
                 'destination':destination,'category':'Test','description':'Vérification de la couverture.',
                 'readMinutes':1,'summary':'Article temporaire de contrôle.',
                 'sections':[{'id':'controle','title':'Contrôle','paragraphs':['Texte de test.']}],
                 'faq':[],'sources':[{'label':'Source de contrôle','url':'https://www.visitportugal.com/'}],
                 'related':['lisbonne-3-jours-sans-voiture']},**fields)

def source_copy(workdir,extra_articles):
    # Only disposable copies receive synthetic articles; the live catalogue and
    # its reviewed release queue are never edited by these regression tests.
    source=workdir/'source'
    source.mkdir()
    for name in ('generate.py','public_media.py','public-media.json','editorial_queue.py','destinations.py','destinations.json','articles.json','image-sources.json',
                 'stay22.py','stay22.json','affiliates.py','affiliates.json','pinterest-rss.json','analytics.json'):
        shutil.copyfile(ROOT/name,source/name)
    shutil.copytree(ROOT/'dist',source/'dist')
    shutil.copytree(ROOT/'social-media',source/'social-media')
    (source/'editorial-queue.json').write_text(json.dumps({'schemaVersion':1,'drafts':[],'promotions':[]}))
    articles=json.loads((source/'articles.json').read_text())+extra_articles
    (source/'articles.json').write_text(json.dumps(articles,ensure_ascii=False))
    return source

class DestinationImageBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workdir=pathlib.Path(tempfile.mkdtemp(prefix='vsd-destination-images-'))
        cls.addClassCleanup(shutil.rmtree,cls.workdir,True)
        articles=[]
        cls.destinations={'lisbonne':'Lisbonne','porto':'Porto','sintra':'Sintra',
                          'guimaraes':'Guimarães','inconnue':'Destination inconnue'}
        for key,destination in cls.destinations.items():
            articles.append(synthetic_guide('test-image-'+key,destination))
        result,cls.out=build(cls.workdir,True,MENTIONS,source_root=source_copy(cls.workdir,articles))
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

    def test_guimaraes_uses_a_real_licensed_photo_for_cover_cards_and_social_metadata(self):
        # Charte 2026-10 : plus d'aplat typographique, une vraie photo du lieu sous licence libre.
        page,head,cover,image=self.article_parts('guimaraes')
        self.assertIn('src="/assets/photos/guimaraes-chateau.jpg"',cover)
        self.assertIn('srcset="/assets/photos/guimaraes-chateau-800.jpg 800w',cover)
        self.assertIn('Photo :',cover)
        self.assertIn('Wikimedia Commons',cover)
        self.assertEqual(image['url'],ORIGIN+'/assets/photos/guimaraes-chateau.jpg')
        self.assertEqual(image['encodingFormat'],'image/jpeg')
        self.assertTrue(image['license'].startswith('https://creativecommons.org/'))
        self.assertEqual(image['creator']['@type'],'Person')
        self.assertIn('property="og:image:type" content="image/jpeg"',head)
        self.assertIn('name="twitter:card" content="summary_large_image"',head)
        for prefix in ('property="og:image"','name="twitter:image"'):
            self.assertIn(prefix+' content="'+image['url']+'"',head)
        card=re.search(r'<a class="card" href="/portugal/test-image-guimaraes/".*?</a>',read(self.out,'/portugal/')).group(0)
        self.assertIn('src="/assets/photos/guimaraes-chateau.jpg"',card)
        self.assertIn(image['caption'],read(self.out,'/credits/'))
        self.assertTrue((self.out/'assets/photos/guimaraes-chateau-800.jpg').is_file())

    def test_every_cover_and_section_photo_id_exists_in_the_catalogue(self):
        ids={p['id'] for p in json.loads((ROOT/'image-sources.json').read_text())['photos']}
        topics=json.loads((ROOT.parent/'.github/vsd-writing/guide-topics.json').read_text())
        for item in json.loads((ROOT/'articles.json').read_text())+topics:
            refs=[item.get('cover')]+[s.get('image') for s in item.get('sections',[])]
            for ref in filter(None,refs):
                with self.subTest(guide=item['slug'],photo=ref):
                    self.assertIn(ref,ids)

    def test_every_photo_in_the_catalogue_has_a_verified_free_licence_and_both_sizes(self):
        sources=json.loads((ROOT/'image-sources.json').read_text())['photos']
        free=re.compile(r'^(CC BY(-SA)? [0-9.]+|CC0)$')
        for photo in sources:
            with self.subTest(photo=photo['id']):
                self.assertRegex(photo['license'],free)
                self.assertTrue(photo['source_page'].startswith('https://commons.wikimedia.org/wiki/File:'))
                self.assertTrue(photo['author'] and photo['alt_fr'])
                if 'file' in photo:
                    self.assertTrue((self.out/'assets'/photo['file']).is_file())
                    self.assertTrue((self.out/'assets'/photo['file'].replace('.jpg','-800.jpg')).is_file())

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

    def test_no_photo_is_attributed_to_an_unknown_destination(self):
        for key in ('inconnue',):
            with self.subTest(destination=key):
                page,head,cover,image=self.article_parts(key)
                for section in (head,cover,json.dumps(image)):
                    self.assertNotIn('/assets/lisbonne.jpg',section)
                    self.assertNotIn('Photo :',section)
                    self.assertNotIn('Wikimedia',section)
                # A separately labelled related Lisbon guide may retain its photo.
                self.assertIn('src="/assets/lisbonne.jpg"',page.split('Pour la suite du voyage.',1)[1])

class DestinationCatalogueTest(unittest.TestCase):
    def test_catalogue_covers_the_most_visited_countries_with_prepositions_and_flags(self):
        import destinations
        catalogue=destinations.load()
        countries=catalogue['countries']
        self.assertGreaterEqual(len(countries),80)
        for slug in ('france','portugal','espagne','italie','japon','etats-unis','thailande','maroc','grece'):
            self.assertIn(slug,countries)
        self.assertEqual(countries['japon']['preposition'],'au Japon')
        self.assertEqual(countries['etats-unis']['preposition'],'aux États-Unis')
        self.assertEqual(countries['italie']['preposition'],'en Italie')
        self.assertEqual(countries['japon']['flag'],'🇯🇵')
        self.assertTrue(set(countries).isdisjoint(destinations.reserved(catalogue)))

    def test_unknown_country_gets_a_readable_fallback_and_reserved_paths_are_refused(self):
        import destinations
        catalogue=destinations.load()
        info=destinations.country_info('sri-lanka-du-sud',catalogue,'asie')
        self.assertEqual((info['name'],info['preposition'],info['continent'],info['known']),('Sri Lanka du Sud','en Sri Lanka du Sud','asie',False))
        self.assertIsNone(destinations.country_info('atlantide',catalogue,'continent-perdu')['continent'])
        # The catalogue's continent wins over a guide's own value.
        self.assertEqual(destinations.country_info('japon',catalogue,'europe')['continent'],'asie')
        for value in ('guides','europe','Japon','',None,'../x'):
            self.assertFalse(destinations.valid_country(value,catalogue),value)

class WorldBuildTest(unittest.TestCase):
    """A fake, unpublished Japan guide and countries absent from the catalogue get their pages."""
    @classmethod
    def setUpClass(cls):
        cls.workdir=pathlib.Path(tempfile.mkdtemp(prefix='vsd-world-'))
        cls.addClassCleanup(shutil.rmtree,cls.workdir,True)
        guides=[synthetic_guide('test-kyoto-automne','Kyoto',country='japon',category='Quand partir',publishedOn='2026-10-25',updatedOn='2026-10-26',
                                keyFacts=[{'value':'15 nov.','label':'pic des érables à Kyoto'}]),
                synthetic_guide('test-atlantide','Atlantide',country='atlantide',category='Budget'),
                synthetic_guide('test-zanzibar','Stone Town',country='zanzibar',continent='afrique')]
        result,cls.out=build(cls.workdir,True,MENTIONS,source_root=source_copy(cls.workdir,guides))
        if result.returncode!=0:raise AssertionError(result.stderr)

    def test_new_country_gets_country_and_continent_pages_and_menu_entry(self):
        japan=read(self.out,'/japon/')
        self.assertIn('<h1>Voyager au Japon.</h1>',japan)
        self.assertIn('<a href="/">Accueil</a> / <a href="/asie/">Asie</a> / Japon</nav>',japan)
        self.assertIn('href="/japon/test-kyoto-automne/"',japan)
        asia=read(self.out,'/asie/')
        self.assertIn('<h1>Voyager en Asie.</h1>',asia)
        self.assertIn('class="destination" href="/japon/"',asia)
        home=read(self.out,'/')
        self.assertIn('<a href="/asie/">Asie</a>',re.search(r'<nav class="nav".*?</nav>',home).group(0))
        self.assertIn('class="chip" href="/japon/"',home)
        self.assertIn('href="/guides/quand-partir/"',home)
        self.assertIn('href="/japon/test-kyoto-automne/"',read(self.out,'/guides/quand-partir/'))

    def test_new_guide_breadcrumb_schema_sitemap_and_feed(self):
        page=read(self.out,'/japon/test-kyoto-automne/')
        self.assertIn('<a href="/asie/">Asie</a> / <a href="/japon/">Japon</a> / Kyoto</nav>',page)
        schemas=json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',page).group(1))
        crumbs=next(item for item in schemas if item.get('@type')=='BreadcrumbList')['itemListElement']
        self.assertEqual([c['name'] for c in crumbs],['Accueil','Asie','Japon','Kyoto'])
        article=next(item for item in schemas if item.get('@type')=='Article')
        self.assertEqual(article['contentLocation']['containedInPlace']['name'],'Japon')
        ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
        dates={n.findtext('s:loc',namespaces=ns):n.findtext('s:lastmod',namespaces=ns) for n in ET.parse(self.out/'sitemap.xml').findall('s:url',ns)}
        for route in ('/japon/test-kyoto-automne/','/japon/','/asie/','/guides/quand-partir/'):
            self.assertEqual(dates[ORIGIN+route],'2026-10-26',route)
        self.assertIn(ORIGIN+'/japon/test-kyoto-automne/',[n.findtext('link') for n in ET.parse(self.out/'feed.xml').findall('channel/item')])

    def test_country_missing_from_the_catalogue_never_breaks_the_build(self):
        page=read(self.out,'/atlantide/test-atlantide/')
        self.assertIn('<a href="/">Accueil</a> / <a href="/atlantide/">Atlantide</a> / Atlantide</nav>',page)
        hub=read(self.out,'/atlantide/')
        self.assertIn('<h1>Voyager en Atlantide.</h1>',hub)
        self.assertIn('country-hero no-photo',hub)
        destinations=read(self.out,'/destinations/')
        self.assertIn('Autres destinations',destinations)
        self.assertIn('class="destination" href="/atlantide/"',destinations)
        # A guide's own continent places a country the catalogue does not know yet.
        self.assertIn('class="destination" href="/zanzibar/"',read(self.out,'/afrique/'))
        self.assertIn('<a href="/afrique/">Afrique</a> / Zanzibar</nav>',read(self.out,'/zanzibar/'))

    def test_every_internal_link_resolves_with_new_countries(self):
        broken=set()
        for page in self.out.rglob('*.html'):
            for url in LINK.findall(page.read_text()):
                target=self.out/url.lstrip('/')
                if url.endswith('/'):target=target/'index.html'
                if not url.startswith('//') and not target.is_file():broken.add(f'{page.relative_to(self.out)} -> {url}')
        self.assertEqual(sorted(broken),[])

class ReservedCountryTest(TempDirTest):
    def test_a_country_cannot_take_a_fixed_page_or_continent_path(self):
        for slug in ('guides','asie'):
            with self.subTest(country=slug):
                workdir=self.workdir/slug
                workdir.mkdir()
                result,_=build(workdir,True,MENTIONS,source_root=source_copy(workdir,[synthetic_guide('test-collision','Collision',country=slug)]))
                self.assertNotEqual(result.returncode,0)
                self.assertIn('réservé',result.stderr)

    def test_generator_no_longer_hardcodes_the_former_three_countries(self):
        source=(ROOT/'generate.py').read_text()
        self.assertNotRegex(source,r"['\"](espagne|italie)['\"]")
        self.assertNotIn('COUNTRY_PAGES',source)
        self.assertNotIn('DESTINATION_IMAGES',source)

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
