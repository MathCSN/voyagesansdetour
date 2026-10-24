import json,html,pathlib,datetime,os,shutil,sys
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from urllib.parse import urlparse
import stay22
import editorial_queue
from public_media import approved_files
ROOT=pathlib.Path(__file__).parent
STATIC=ROOT/'dist'
PUBLIC=os.environ.get('LJA_PUBLIC')=='1'
OUT=pathlib.Path(os.environ.get('SITE_OUT') or ROOT/('public' if PUBLIC else 'dist'))
ORIGIN=os.environ.get('SITE_ORIGIN','https://voyagesansdetour.fr').rstrip('/')
AFFILIATE_PREVIEW=sys.argv[1:]==['--preview-stay22']
if sys.argv[1:] and not AFFILIATE_PREVIEW:sys.exit('Argument de génération inconnu.')
try:
    if AFFILIATE_PREVIEW:stay22.validate_preview(ROOT,OUT,public=PUBLIC,origin=ORIGIN)
    AFFILIATE=stay22.load_config(os.environ.get('SITE_STAY22') or ROOT/'stay22.json')
    AFFILIATE_ACTIVE=stay22.is_active(AFFILIATE,public=PUBLIC,origin=ORIGIN)
except (OSError,ValueError,TypeError,KeyError) as error:sys.exit(str(error))
MENTIONS_FILE=pathlib.Path(os.environ.get('SITE_MENTIONS') or ROOT/'mentions.json')
BRAND='Voyage Sans Détour'
CONTACT='contact@voyagesansdetour.fr'
PINTEREST_URL='https://fr.pinterest.com/voyagesansdetour/'
ANALYTICS=json.loads(pathlib.Path(os.environ.get('SITE_ANALYTICS') or ROOT/'analytics.json').read_text())
ANALYTICS_ACTIVE=(PUBLIC and ORIGIN=='https://voyagesansdetour.fr' and
    ANALYTICS.get('enabled') is True and ANALYTICS.get('provider_settings_verified') is True and
    isinstance(ANALYTICS.get('provider_settings_verified_at'),str) and
    bool(ANALYTICS['provider_settings_verified_at']))
# Seul ce lot final validé est diffusé ; les brouillons et fichiers de production restent locaux.
SOCIAL_FILES=tuple('lancement-2026-09/'+name for name in (
    'pin-01-lisbonne-3-jours.jpg','pin-02-porto-3-jours.jpg',
    'pin-03-ou-dormir-lisbonne.jpg','pin-04-lisbonne-ou-porto.jpg',
    'reel-01-lisbonne-ou-porto.mp4','reel-02-lisbonne-3-jours.mp4','credits.txt'))

CAROUSEL_FILES=tuple('carrousels-2026-09/'+city+'-'+name+'.jpg'
    for city in ('lisbonne','porto') for name in
    ('01-couverture','02-jour-1','03-jour-2','04-jour-3','05-bons-reflexes','06-guide-complet'))+tuple(
    'carrousels-2026-09/'+name for name in ('credits.txt','dmsans-OFL.txt','playfairdisplay-OFL.txt'))
SOCIAL_FILES+=CAROUSEL_FILES
SOCIAL_FILES+=approved_files(ROOT)
# Les reels de démonstration portent l'ancien nom et une voix sans droits commerciaux : jamais publiés.
SHOW_SHORTS=not PUBLIC and not AFFILIATE_PREVIEW
REQUIRED_MENTIONS={'editeur':('nom','adresse','telephone','email','directeur_publication'),'hebergeur':('nom','adresse','telephone','site','confidentialite')}
def mention(data,group,name):
    section=data.get(group)
    return str(section.get(name,'')).strip() if isinstance(section,dict) else ''
def load_mentions():
    if not MENTIONS_FILE.exists():return None,['fichier absent']
    try:data=json.loads(MENTIONS_FILE.read_text())
    except json.JSONDecodeError as err:sys.exit(f'{MENTIONS_FILE.name} illisible : {err}')
    if not isinstance(data,dict):sys.exit(f'{MENTIONS_FILE.name} doit contenir un objet JSON.')
    missing=[f'{group}.{name}' for group,names in REQUIRED_MENTIONS.items() for name in names if not mention(data,group,name)]
    placeholders=[f'{group}.{name}' for group,section in data.items() if isinstance(section,dict) for name in section if 'COMPLÉTER' in mention(data,group,name)]
    return data,missing+[p for p in placeholders if p not in missing]
mentions,missing_mentions=load_mentions()
if PUBLIC and missing_mentions:sys.exit(f'Version publique refusée : mentions légales incomplètes dans {MENTIONS_FILE.name} ({", ".join(missing_mentions)}).')
def prepare_public_dir():
    social=ROOT/'social-media'
    for name in SOCIAL_FILES:
        source=social/name
        if not source.is_file() or source.is_symlink() or any(p.is_symlink() for p in (social,source.parent)):
            sys.exit(f'Média public manquant ou lien symbolique interdit : social-media/{name}')
    if OUT.exists() and any(OUT.iterdir()) and not (OUT/'.nojekyll').exists():sys.exit(f'{OUT} existe et ne provient pas de ce générateur : suppression refusée.')
    if OUT.exists():shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for name in ('style.css','site.js','analytics.mjs'):shutil.copy2(STATIC/name,OUT/name)
    shutil.copytree(STATIC/'assets',OUT/'assets',ignore=shutil.ignore_patterns('reel-*','.DS_Store'))
    for name in SOCIAL_FILES:
        target=OUT/'social-media'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(social/name,target)
    if PUBLIC:
        (OUT/'CNAME').write_text(urlparse(ORIGIN).hostname+'\n')
        # Déclaration du compte éditeur vérifié ; aucun script ou espace publicitaire n'est activé ici.
        if ORIGIN=='https://voyagesansdetour.fr':
            (OUT/'ads.txt').write_text('google.com, pub-7879144993741676, DIRECT, f08c47fec0942fa0\n')
    (OUT/'.nojekyll').write_text('')
try:articles=editorial_queue.published_articles(ROOT)
except (OSError,ValueError,TypeError,KeyError) as error:sys.exit(str(error))
if PUBLIC or AFFILIATE_PREVIEW:prepare_public_dir()
LEGACY_DATE='2026-09-14'
MONTHS_FR=('janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre')
def article_date(article,key):
    value=article.get(key,LEGACY_DATE)
    try:
        parsed=datetime.date.fromisoformat(value)
        if parsed.isoformat()!=value:raise ValueError()
    except (TypeError,ValueError):sys.exit(f'Date éditoriale invalide : {article.get("slug")} / {key}')
    return value
def french_date(value):
    date=datetime.date.fromisoformat(value)
    return f'{date.day} {MONTHS_FR[date.month-1]} {date.year}'
for article in articles:
    for key in ('publishedOn','updatedOn','sourcesCheckedOn'):article_date(article,key)
    if article_date(article,'updatedOn')<article_date(article,'publishedOn'):
        sys.exit(f'Date de mise à jour antérieure à la publication : {article["slug"]}')
credits=json.loads((ROOT/'image-sources.json').read_text())
e=editorial_queue.html_text
by_slug={a['slug']:a for a in articles}
photos={a['id']:a for a in credits['photos']}
SHARE_IMAGES={
    'brand':('brand-voyagesansdetour.png',1080,1080,'image/png'),
    'lisbonne':('lisbonne.jpg',1600,1066,'image/jpeg'),
    'porto':('porto.jpg',2200,652,'image/jpeg'),
    'sintra':('sintra.jpg',1800,818,'image/jpeg'),
    'guimaraes':('guimaraes-cover.png',1600,900,'image/png'),
}
# Photos libres du dossier photos/ : fichier 1600 px et variante 800 px pour les cartes et le mobile.
for key,p in photos.items():
    if 'file' in p:SHARE_IMAGES[key]=(p['file'],p['width'],p['height'],'image/jpeg')
DESTINATION_IMAGES={'Lisbonne':'lisbonne','Porto':'porto','Sintra':'sintra','Guimarães':'guimaraes-chateau',
    'Portugal':'lisbonne-tram-28','Algarve':'algarve-ponta-piedade','Douro':'douro-vallee',
    'Andalousie':'grenade-alhambra','Côte amalfitaine':'amalfi-positano','Cinque Terre':'cinque-manarola'}
COUNTRIES={'portugal':'Portugal','espagne':'Espagne','italie':'Italie'}
COUNTRY_PAGES={
    'portugal':('Le Portugal sans voiture','Lisbonne, Porto, Sintra, l’Algarve et le Douro : des trains qui longent l’océan et le fleuve, des trams qui grimpent, et des prix relevés pour préparer chaque trajet.','lisbonne-tram-28'),
    'espagne':('L’Espagne en train','Séville, Cordoue et Grenade reliées par des trains rapides : l’Andalousie se parcourt sans volant, d’un patio à l’autre.','seville-plaza-espana'),
    'italie':('L’Italie sans voiture','Côte amalfitaine en ferry, Cinque Terre en train : les plus beaux rivages d’Italie sont aussi ceux où la voiture est la pire idée.','cinque-manarola'),
}
ILLUSTRATIONS={}
def image_data(key):
    filename,width,height,mime_type=SHARE_IMAGES[key]
    url=ORIGIN+'/assets/'+filename
    data={'@type':'ImageObject','@id':url+'#image','url':url,'contentUrl':url,'width':width,'height':height,'encodingFormat':mime_type}
    if key in photos:
        p=photos[key]
        creator={'@type':'Person','name':p['author']}
        if p.get('author_url'):creator['url']=p['author_url']
        data.update({'caption':p['alt_fr'],'creditText':p['credit_fr'],'license':p['license_url'],'creator':creator})
    elif key in ILLUSTRATIONS:
        data.update(ILLUSTRATIONS[key])
        data['creator']={'@type':'Organization','name':BRAND}
    else:data.update({'caption':'Identité visuelle de '+BRAND,'creditText':BRAND})
    return data
def country(a):
    value=a.get('country','portugal')
    if value not in COUNTRIES:sys.exit(f'Pays inconnu pour {a["slug"]} : {value}')
    return value
def photo(a):
    if a.get('cover') in SHARE_IMAGES:return a['cover']
    return DESTINATION_IMAGES.get(a['destination'],'brand')
def uri(a):return '/'+country(a)+'/'+a['slug']+'/'
def img(key,cls='',lazy=True,sizes='(max-width:700px) 100vw, 50vw'):
    filename,width,height,_=SHARE_IMAGES[key]
    image=image_data(key)
    srcset=''
    if key in photos and 'file' in photos[key]:
        small=filename.removesuffix('.jpg')+'-800.jpg'
        srcset=f' srcset="/assets/{small} 800w, /assets/{filename} {width}w" sizes="{sizes}"'
    return f'<img class="{cls}" src="/assets/{filename}"{srcset} alt="{e(image["caption"])}" width="{width}" height="{height}" {"loading=lazy" if lazy else "fetchpriority=high"} decoding="async">'
def credit(key):
    if key in ILLUSTRATIONS:
        return f'<p class="photo-credit">{e(ILLUSTRATIONS[key]["caption"])} · {e(ILLUSTRATIONS[key]["creditText"])}</p>'
    if key not in photos:
        return f'<p class="photo-credit">Identité visuelle de {e(BRAND)}</p>'
    p=photos[key]
    return f'<p class="photo-credit">Photo : <a href="{p["source_page"]}">{e(p["author"])} / Wikimedia Commons</a> · <a href="{p["license_url"]}">{p["license"]}</a> · redimensionnée, recadrée à l’affichage.</p>'
def figure(key):
    if key not in photos:sys.exit(f'Photo inconnue : {key}')
    return f'<figure class="inline-photo">{img(key,sizes="(max-width:700px) 100vw, 800px")}<figcaption>{e(photos[key]["alt_fr"])}</figcaption>{credit(key)}</figure>'
header='''<a class="skip" href="#contenu">Aller au contenu</a><div class="topline">EN TRAIN, EN FERRY, EN TRAM ET À PIED · DES PRIX RELEVÉS, DES TRAJETS QUI MARCHENT</div><div class="wrap"><header class="header"><a class="brand" href="/" aria-label="Voyage Sans Détour, accueil"><small>VOYAGE</small><span>sans détour.</span></a><nav class="nav" aria-label="Navigation principale"><a href="/portugal/">Portugal</a><a href="/espagne/">Espagne</a><a href="/italie/">Italie</a><a href="/#destinations">Destinations</a></nav></header>'''
if AFFILIATE_PREVIEW:header+='<p class="stay22-preview-banner">Aperçu local de l’encart : affiliation inactive, liens désactivés, aucune admission ni redirection vérifiée par cet aperçu.</p>'
shorts_link='<a href="/formats-courts/">Formats courts</a>' if SHOW_SHORTS else ''
audience_settings='<button type="button" class="audience-settings" data-audience-settings hidden>Gérer la mesure d’audience</button>' if ANALYTICS_ACTIVE else ''
audience_panel='''<section id="audience-choice" class="audience-choice" aria-labelledby="audience-title" hidden><h2 id="audience-title">La mesure d’audience, à votre choix</h2><p>Avec votre accord, Google Analytics utilise des cookies pour compter les visites et comprendre les pages consultées. Aucune publicité personnalisée. Refuser ne change pas votre accès au blog.</p><p id="audience-status" role="status">Aucune mesure d’audience sans votre accord.</p><div class="audience-actions"><button type="button" data-audience-refuse>Tout refuser</button><button type="button" data-audience-accept>Accepter la mesure d’audience</button></div><p><a href="/confidentialite/">Données, destinataires et durées</a> · Choix conservé 180 jours. Retrait possible dans « Gérer la mesure d’audience » en bas de chaque page.</p></section>''' if ANALYTICS_ACTIVE else ''
footer=f'''<footer class="footer"><div class="footer-top"><a class="brand" href="/"><small>VOYAGE</small><span>sans détour.</span></a><div class="footer-links"><a href="/carnet/">Mon carnet de départ</a><a href="/methode/">Notre méthode</a><a href="/transparence/">Transparence</a>{shorts_link}<a href="/credits/">Crédits photos</a><a href="{PINTEREST_URL}" rel="me">Pinterest</a></div></div><small>© 2026 {BRAND} · Guides préparés avec l’aide de l’IA, à partir de sources identifiées. <a href="mailto:{CONTACT}">Contact</a> · <a href="/confidentialite/">Confidentialité</a> · <a href="/mentions-legales/">Mentions légales</a> {audience_settings}</small></footer></div>'''
favicon="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='13' fill='%23214fe6'/%3E%3Ctext x='32' y='46' text-anchor='middle' font-family='Georgia' font-size='47' fill='%23f8de55'%3Ev%3C/text%3E%3C/svg%3E"
pages=[]
def page(path,title,description,content,schema=None,noindex=False,share_image='brand'):
    dest=OUT/path.strip('/')/'index.html' if path!='/' else OUT/'index.html'
    if path=='/404.html':dest=OUT/'404.html'
    dest.parent.mkdir(parents=True,exist_ok=True)
    full=ORIGIN+path
    sharing=image_data(share_image)
    data=[{'@context':'https://schema.org','@type':'Organization','@id':ORIGIN+'/#organization','name':BRAND,'email':CONTACT,'url':ORIGIN+'/','sameAs':[PINTEREST_URL],'logo':image_data('brand'),'image':image_data('brand')},{'@context':'https://schema.org','@type':'WebSite','name':BRAND,'url':ORIGIN+'/','inLanguage':'fr'},dict(sharing,**{'@context':'https://schema.org'})]
    if schema:data+=schema
    robots='index,follow,max-image-preview:large' if PUBLIC and not noindex else 'noindex,follow'
    ld=json.dumps(data,ensure_ascii=False).replace('<','\\u003c')
    analytics_tag=(f'<script type="module" src="/analytics.mjs" data-vsd-analytics data-enabled="true" data-measurement-id="{e(ANALYTICS["measurement_id"])}"></script>' if ANALYTICS_ACTIVE and path!='/404.html' else '')
    site_verifications='<meta name="p:domain_verify" content="c3f99d14884f31bf28b008c476ddfea3"/><meta name="google-site-verification" content="4AJ36ZanxjOuwRQIDsjdF0XBXaho8-Zd_5r7VBjY0P0" /><meta name="google-adsense-account" content="ca-pub-7879144993741676">' if PUBLIC and path=='/' else ''
    affiliate_style=stay22.CSS if AFFILIATE_PREVIEW or 'class="stay22-box"' in content else ''
    dest.write_text(f'''<!doctype html><html lang="fr"><head>{site_verifications}<meta charset="utf-8"><meta name="referrer" content="strict-origin-when-cross-origin"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title><meta name="description" content="{e(description)}"><meta name="robots" content="{robots}"><meta name="theme-color" content="#214fe6"><link rel="canonical" href="{full}"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(description)}"><meta property="og:url" content="{full}"><meta property="og:locale" content="fr_FR"><meta property="og:site_name" content="{BRAND}"><meta property="og:type" content="{'article' if path in {uri(a) for a in articles} else 'website'}"><meta property="og:image" content="{e(sharing['url'])}"><meta property="og:image:secure_url" content="{e(sharing['url'])}"><meta property="og:image:type" content="{sharing['encodingFormat']}"><meta property="og:image:width" content="{sharing['width']}"><meta property="og:image:height" content="{sharing['height']}"><meta property="og:image:alt" content="{e(sharing['caption'])}"><meta name="twitter:card" content="{'summary' if share_image=='brand' else 'summary_large_image'}"><meta name="twitter:image" content="{e(sharing['url'])}"><meta name="twitter:image:alt" content="{e(sharing['caption'])}"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(description)}"><link rel="icon" href="{favicon}"><link rel="stylesheet" href="/style.css"><link rel="alternate" type="application/rss+xml" title="{BRAND}" href="/feed.xml"><script type="application/ld+json">{ld}</script><script src="/site.js" defer></script>{analytics_tag}{affiliate_style}</head><body>{header}<main id="contenu">{content}</main>{footer}{audience_panel if path!="/404.html" else ""}</body></html>''')
    if not noindex:pages.append(path)
def card(a,lead=False):
    return f'''<a class="card{' card-lead' if lead else ''}" href="{uri(a)}" data-destination="{e(a['destination'])}" data-search="{e(a['title']+' '+a['description']+' '+a['category']+' '+a['destination'])}"><div class="card-image">{img(photo(a),sizes='(max-width:700px) 100vw, 33vw')}<span class="tag">{e(a['destination'])}</span></div><span class="meta">{e(a['category'].upper())} · {a['readMinutes']} MIN DE LECTURE</span><h3>{e(a['shortTitle'])}</h3><p>{e(a['description'])}</p></a>'''
def breadcrumb(a):
    slug=country(a)
    return f'<nav class="breadcrumb" aria-label="Fil d’Ariane"><a href="/">Accueil</a> / <a href="/{slug}/">{COUNTRIES[slug]}</a> / {e(a["shortTitle"])}</nav>'
def basic(path,title,description,body):page(path,title+' | '+BRAND,description,f'<div class="page-heading"><span class="eyebrow">{e(BRAND)}</span><h1>{e(title)}</h1><p>{e(description)}</p></div><div class="prose">{body}</div>')
def key_facts(a):
    facts=a.get('keyFacts',[])
    if not facts:return ''
    items=''.join(f'<li><strong>{e(f["value"])}</strong><span>{e(f["label"])}</span></li>' for f in facts)
    return f'<ul class="key-facts">{items}</ul>'
def published(a):return article_date(a,'publishedOn')
latest=sorted(articles,key=lambda a:(published(a),articles.index(a)),reverse=True)
destinations=[]
for a in articles:
    if a['destination'] in DESTINATION_IMAGES and a['destination']!='Portugal' and a['destination'] not in [d[0] for d in destinations]:
        destinations.append((a['destination'],a))
def destination_tile(name,lead):
    count=sum(1 for x in articles if x['destination']==name)
    label=f'{count} guides' if count>1 else '1 guide'
    return f'''<a class="destination" href="{uri(lead)}"><div class="destination-image">{img(DESTINATION_IMAGES[name],sizes='(max-width:700px) 50vw, 25vw')}</div><span class="destination-country">{COUNTRIES[country(lead)]} · {label}</span><strong>{e(name)}</strong></a>'''
FACTS_ON_HOME=8
fact_guides=[]
for a in latest:
    if a.get('keyFacts') and a['destination'] not in [x['destination'] for x in fact_guides]:fact_guides.append(a)
facts_strip=''.join(f'<a class="fact" href="{uri(a)}"><strong>{e(a["keyFacts"][0]["value"])}</strong><span>{e(a["keyFacts"][0]["label"])}</span><em>{e(a["destination"])} ↗</em></a>' for a in fact_guides[:FACTS_ON_HOME])
hero_key='lisbonne-alfama-toits'
page('/',BRAND+' — Voyager sans voiture, en train et à pied','Lisbonne, Porto, l’Algarve, le Douro, l’Andalousie, la côte amalfitaine et les Cinque Terre sans voiture : trajets, prix relevés et itinéraires qui donnent envie de partir.',f'''<section class="hero-full">{img(hero_key,'hero-photo',lazy=False,sizes='100vw')}<div class="hero-copy"><span class="eyebrow">Le voyage sans voiture, en vrai</span><h1>Prenez le train.<br>Gardez <em>la vue.</em></h1><p>Le tram 28 qui grimpe dans Alfama, le train du Douro au ras du fleuve, le ferry qui longe Positano. Des itinéraires précis, des prix relevés, et l’envie de partir.</p><div class="hero-actions"><a class="button" href="#destinations">Choisir ma destination <span aria-hidden="true">↓</span></a><a class="button light" href="{uri(latest[0])}">Le dernier guide <span aria-hidden="true">↗</span></a></div></div><div class="stamp">{len(destinations)}<b>destinations</b>0 VOITURE</div><span class="hero-caption">{e(photos[hero_key]['alt_fr'])} Photo : {e(photos[hero_key]['author'])} / Wikimedia Commons, {photos[hero_key]['license']}.</span></section><div class="manifesto"><span>Des prix et des durées, datés</span><span>Des photos des vrais lieux</span><span>Des trajets vérifiés chez les opérateurs</span></div><section class="section" id="destinations"><div class="section-head"><div><span class="eyebrow">Où partir</span><h2>Des envies d’ailleurs.<br>Zéro volant.</h2></div></div><div class="destinations">{''.join(destination_tile(name,lead) for name,lead in destinations)}</div></section><section class="facts-band"><span class="eyebrow">Le concret qui change le voyage</span><div class="facts">{facts_strip}</div></section><section class="section"><div class="section-head"><div><span class="eyebrow">Tout juste publiés</span><h2>Les derniers guides.</h2></div><a class="text-link" href="/portugal/#guides">Tous les guides ↗</a></div><div class="grid">{''.join(card(a) for a in latest[:6])}</div></section><section class="blue-panel"><div><span class="eyebrow">Les questions qu’on se pose avant de réserver</span><h2>Choisir vite.<br>Partir mieux.</h2><p>Une ville ou deux, quel quartier, quel train : les réponses courtes, avec les chiffres qui permettent de trancher.</p></div><ul class="quicklinks"><li><a href="/portugal/lisbonne-ou-porto/">Lisbonne ou Porto : laquelle choisir ? <span>↗</span></a></li><li><a href="/portugal/ou-dormir-lisbonne-quartiers/">Dans quel quartier dormir à Lisbonne ? <span>↗</span></a></li><li><a href="/portugal/lisbonne-porto-train/">Lisbonne–Porto en train : prix et durées <span>↗</span></a></li></ul></section><section class="intro-note"><div><span class="eyebrow">L’esprit de {BRAND}</span><h2>Le volant en moins,<br>le paysage en plus.</h2></div><div><p>Sans voiture, on regarde par la fenêtre du train, on traverse le fleuve en ferry, on monte à pied jusqu’au belvédère. Nos guides donnent les lignes, les prix, les durées et les petites astuces qui rendent tout ça simple.</p><p>Chaque chiffre est relevé sur le site de l’opérateur ou du monument, avec sa date. Les sources sont en bas de chaque guide.</p><a class="text-link" href="/methode/">Comment nous vérifions ↗</a></div></section><section class="blue-panel" style="margin-bottom:55px"><div><span class="eyebrow">À garder sous la main</span><h2>Votre départ,<br>sur une seule page.</h2><p>Une fiche de préparation à cocher et à imprimer. Pas d’adresse e-mail à laisser, juste l’essentiel à emporter.</p></div><div><a class="button light" href="/carnet/">Ouvrir mon carnet de départ ↗</a></div></section>''',share_image=hero_key)
def country_page(slug):
    title,intro,cover=COUNTRY_PAGES[slug]
    selected=[a for a in articles if country(a)==slug]
    if not selected:return
    names=list(dict.fromkeys(a['destination'] for a in selected))
    buttons=''.join(f'<button class="filter" aria-pressed="false" data-filter="{e(n)}">{e(n)}</button>' for n in names) if len(names)>1 else ''
    schema=[{'@context':'https://schema.org','@type':'ItemList','name':title,'itemListElement':[{'@type':'ListItem','position':i+1,'url':ORIGIN+uri(a),'name':a['title']} for i,a in enumerate(selected)]}]
    count=f'{len(selected)} guides pour préparer votre séjour' if len(selected)>1 else '1 guide pour préparer votre séjour'
    page(f'/{slug}/',f'{title} : itinéraires, trains et prix | {BRAND}',intro,f'''<section class="country-hero">{img(cover,'hero-photo',lazy=False,sizes='100vw')}<div class="country-copy"><span class="eyebrow">Dossier · {COUNTRIES[slug]}</span><h1>{e(title)}.</h1><p>{e(intro)}</p></div></section>{credit(cover)}<section class="section" id="guides" style="padding-top:30px"><div class="filters" aria-label="Rechercher un guide"><label class="sr-only" for="search">Rechercher un guide</label><input type="search" id="search" placeholder="Une ville, un quartier, un trajet…"><button class="filter" aria-pressed="true" data-filter="Tous">Tous</button>{buttons}</div><p class="result-count" id="result-count" aria-live="polite">{count}</p><div class="grid" id="guide-grid">{''.join(card(a) for a in selected)}</div><p class="empty" id="empty" hidden>Aucun guide ne correspond. Essayez « train », « quartier » ou une autre ville.</p></section>''',schema,share_image=cover)
for slug in COUNTRIES:country_page(slug)
def section_html(s):
    out=f'<section id="{e(s["id"])}"><h2>{e(s["title"])}</h2>'
    if s.get('image'):out+=figure(s['image'])
    out+=''.join(f'<p>{e(p)}</p>' for p in s['paragraphs'])
    if s.get('bullets'):out+='<ul>'+''.join(f'<li>{e(x)}</li>' for x in s['bullets'])+'</ul>'
    if s.get('table'):
        t=s['table'];out+='<div class="table-scroll"><table><thead><tr>'+''.join(f'<th scope="col">{e(x)}</th>' for x in t['headers'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{e(str(x))}</td>' for x in row)+'</tr>' for row in t['rows'])+'</tbody></table></div>'
    if s.get('tip'):out+=f'<aside class="tip"><strong>L’astuce</strong><p>{e(s["tip"])}</p></aside>'
    return out+'</section>'
def related_for(a):
    chosen=[by_slug[x] for x in a['related'] if x in by_slug]
    if len(chosen)<3:
        same=[x for x in articles if x is not a and x not in chosen and country(x)==country(a)]
        others=[x for x in latest if x is not a and x not in chosen and x not in same]
        chosen+=(same+others)[:3-len(chosen)]
    return chosen[:3]
for a in articles:
    body=''.join(section_html(s) for s in a['sections'])
    affiliate_box=stay22.guide_box(AFFILIATE,a['slug'],active=AFFILIATE_ACTIVE,preview=AFFILIATE_PREVIEW)
    affiliate_note=('Un lien affilié est signalé dans ce guide.' if affiliate_box else 'Aucun lien de réservation rémunéré n’est activé dans ce guide.') if AFFILIATE_ACTIVE or AFFILIATE_PREVIEW else 'Aucun lien de réservation rémunéré n’est activé dans cette édition.'
    faq=''.join(f'<details><summary>{e(q["question"])}</summary><p>{e(q["answer"])}</p></details>' for q in a['faq'])
    sources=''.join(f'<li><a href="{e(s["url"])}">{e(s["label"])}</a></li>' for s in a['sources'])
    related=related_for(a)
    toc=''.join(f'<li><a href="#{e(s["id"])}">{e(s["title"])}</a></li>' for s in a['sections'])
    checked=french_date(article_date(a,'sourcesCheckedOn'))
    images=[image_data(photo(a))]+[image_data(s['image']) for s in a['sections'] if s.get('image')]
    schema=[{'@context':'https://schema.org','@type':'Article','headline':a['title'],'description':a['description'],'image':images[0] if len(images)==1 else images,'datePublished':article_date(a,'publishedOn'),'dateModified':article_date(a,'updatedOn'),'inLanguage':'fr','author':{'@type':'Organization','name':BRAND,'url':ORIGIN+'/methode/'},'publisher':{'@id':ORIGIN+'/#organization'},'mainEntityOfPage':ORIGIN+uri(a),'citation':[s['url'] for s in a['sources']]},{'@context':'https://schema.org','@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':1,'name':'Accueil','item':ORIGIN+'/'},{'@type':'ListItem','position':2,'name':COUNTRIES[country(a)],'item':ORIGIN+'/'+country(a)+'/'},{'@type':'ListItem','position':3,'name':a['shortTitle'],'item':ORIGIN+uri(a)}]}]
    if a['faq']:schema.append({'@context':'https://schema.org','@type':'FAQPage','mainEntity':[{'@type':'Question','name':q['question'],'acceptedAnswer':{'@type':'Answer','text':q['answer']}} for q in a['faq']]})
    facts=key_facts(a)
    facts_block=f'<section class="essentials" aria-labelledby="essentiel"><h2 id="essentiel">L’essentiel en chiffres</h2>{facts}<p class="facts-date">Relevés le {checked} ; chaque chiffre vient d’une source citée en bas de page.</p></section>' if facts else ''
    page(uri(a),a['title']+' | '+BRAND,a['description'],f'''{breadcrumb(a)}<header class="article-title"><span class="eyebrow">{e(a['destination'])} · {e(a['category'])}</span><h1>{e(a['title'])}</h1><p>{e(a['description'])}</p><div class="byline">{e(BRAND)} · Publié le {french_date(article_date(a,'publishedOn'))} · {a['readMinutes']} min de lecture<br>Sources consultées le {checked} · <a href="/methode/">Méthode éditoriale</a></div></header>{img(photo(a),'article-cover',False,sizes='100vw')}{credit(photo(a))}<div class="article-layout"><article class="article-body"><div class="answer"><strong>La réponse en bref</strong><p>{e(a['summary'])}</p></div>{facts_block}{body}{affiliate_box}<section id="questions"><h2>Les questions avant le départ</h2>{faq}</section><section id="sources"><h2>Sources et date de vérification</h2><p>Prix, horaires et conditions relevés le {checked} sur ces pages. Ils peuvent changer : un coup d’œil avant de réserver suffit.</p><ul class="source-list">{sources}</ul><p class="photo-credit">{affiliate_note} <a href="/transparence/">En savoir plus</a>. Guide préparé avec l’aide de l’IA à partir de ces sources.</p></section></article><aside class="toc" aria-label="Sommaire"><strong>Dans ce guide</strong><ol>{'<li><a href="#essentiel">L’essentiel en chiffres</a></li>' if facts else ''}{toc}<li><a href="#questions">Vos questions</a></li><li><a href="#sources">Sources</a></li></ol><button type="button" class="button" data-print>Imprimer le guide</button></aside></div><section class="section"><div class="section-head"><h2>Pour la suite du voyage.</h2></div><div class="grid">{''.join(card(x) for x in related)}</div></section>''',schema,share_image=photo(a))
basic('/a-propos/','Un peu plus d’ailleurs.','Un média de voyage pour faire des choix simples et préparer des journées qui vous ressemblent.',f'''<h2>Le voyage, avant le voyage</h2><p>{BRAND} rassemble des guides pratiques pour les voyageurs francophones. Nos dossiers couvrent le Portugal, l’Espagne et l’Italie sans voiture : Lisbonne, Porto, Sintra, l’Algarve, le Douro, l’Andalousie, la côte amalfitaine et les Cinque Terre, avec les trains, ferries et bus qui les relient.</p><p>Nous préférons un programme faisable à une liste interminable de lieux, et des chiffres à des généralités : le prix du billet, la durée du trajet, le numéro de la ligne, le jour de fermeture.</p><div class="profile"><img src="/assets/alma.jpg" alt="Alma, personnage virtuel créé par intelligence artificielle" width="563" height="1000" loading="lazy"><div><span class="eyebrow">Le visage de nos formats courts</span><h2>Voici Alma.</h2><p>Alma est une présentatrice virtuelle originale, créée par intelligence artificielle. Elle incarne nos formats courts et explique les idées de voyage du média.</p><p>Son image ne représente pas une voyageuse réelle. Elle ne signe pas de témoignages de séjour et ne prétend pas avoir testé des hôtels.</p></div></div><h2>Des repères, et leurs sources</h2><p>Les contenus de cette première édition ont été préparés avec l’aide de l’IA, à partir de pages d’offices de tourisme, d’opérateurs de transport et de monuments. Une vérification des sources ne remplace pas une visite sur place.</p><p><a href="/methode/">Lire notre méthode éditoriale</a> · <a href="/transparence/">Comprendre la monétisation</a></p>''')
basic('/methode/','Comment nous préparons les guides.','Les sources, les choix éditoriaux et les limites de cette première édition.',f'''<h2>Une question précise par guide</h2><p>Un article doit aider à prendre une décision : choisir une ville, un quartier, un trajet ou un programme. Les itinéraires sont des propositions éditoriales à adapter, pas des séjours présentés comme vécus.</p><h2>Des sources identifiées</h2><p>Les informations pratiques sont recherchées sur les sites des opérateurs, monuments et organismes touristiques. Les liens figurent au bas des articles. La date indiquée correspond à la consultation des sources, pas à un voyage sur place.</p><h2>Le rôle de l’intelligence artificielle</h2><p>Cette première édition a été recherchée, structurée et rédigée avec l’aide de l’IA. Les contenus n’ont pas encore bénéficié d’une relecture indépendante par une personne ayant testé les itinéraires. L’IA peut commettre des erreurs : utilisez les sources officielles pour toute réservation.</p><h2>Prix, horaires et recommandations</h2><p>Nos guides donnent les prix, durées, lignes et horaires relevés sur les sites des opérateurs, des monuments et des offices de tourisme, avec la date du relevé en tête de guide. Quand une information ne vient que de la presse ou d’un guide tiers, la source est citée comme telle. Une idée d’itinéraire exprime un choix éditorial ; un avis d’hôtel ou un retour d’expérience ne peut être attribué qu’à son auteur réel.</p><h2>Images et corrections</h2><p>Chaque guide est illustré par des photos réelles des lieux, sous licence libre (Creative Commons ou domaine public, vérifiée sur Wikimedia Commons), avec auteurs et licences sur la page crédits. Alma est une image générée d’un personnage fictif.</p><h2>Signaler une erreur</h2><p>Une information inexacte ou périmée ? Écrivez à <a href="mailto:{CONTACT}">{CONTACT}</a> en indiquant la page concernée.</p>''')
transparency_body='<h2>Dans cette édition</h2><p>Aucun programme d’affiliation ni publicité n’est activé. Les liens vers les transports, monuments et organismes touristiques sont des liens informatifs ordinaires. Aucune commission n’est annoncée ou perçue par le site grâce à ces liens.</p><h2>Si l’affiliation est activée</h2><p>Certains liens pourront devenir rémunérés après admission aux programmes. Une mention claire sera placée près des liens concernés. Une commission peut alors être versée à l’éditeur selon les conditions du partenaire ; les conditions de réservation et le prix restent à vérifier chez le vendeur.</p><p>Les relations commerciales, produits offerts et placements seront identifiés. La présence d’une rémunération ne sera pas présentée comme une preuve qu’une offre convient à tous les voyageurs.</p><h2>Une présentatrice virtuelle clairement annoncée</h2><p>Alma est un personnage créé par intelligence artificielle. Les visuels et formats courts qui la représentent sont signalés. Ils ne constituent pas la preuve d’un voyage ou d’un test de prestation.</p>'
if AFFILIATE_ACTIVE or AFFILIATE_PREVIEW:transparency_body=stay22.TRANSPARENCY+'<h2>Une présentatrice virtuelle clairement annoncée</h2><p>Alma est un personnage créé par intelligence artificielle. Les visuels et formats courts qui la représentent sont signalés. Ils ne constituent pas la preuve d’un voyage ou d’un test de prestation.</p>'
basic('/transparence/','La confiance fait partie du voyage.','Comment sont présentés les liens commerciaux et les contenus virtuels.',transparency_body)
def privacy_body():
    if missing_mentions:hosting='<p>L’hébergement et le contrôle d’accès de la préversion peuvent traiter les données techniques nécessaires au service.</p>'
    else:
        host=mentions['hebergeur']
        hosting=f'<p>Le site est hébergé par {e(host["nom"])}. Comme tout serveur web, l’hébergeur peut enregistrer des données techniques de connexion (adresse IP, date, navigateur) pour assurer la sécurité et le fonctionnement du service, selon <a href="{e(host["confidentialite"])}">sa politique de confidentialité</a>.</p>'
    analytics_notice = ('<h2>Mesure d’audience facultative</h2><p>Uniquement après votre accord, Google Analytics 4 mesure les visites et les pages consultées pour améliorer nos guides. Le traitement repose sur votre consentement. Google reçoit notamment un identifiant de cookie, la page canonique consultée, des informations techniques sur le navigateur et les événements nécessaires aux sessions. Notre balise exclut les paramètres et fragments d’URL, le site précédent, les recherches saisies et les clics de contact. Nous ne transmettons ni nom, ni adresse e-mail, ni identifiant de compte visiteur ; nous ne mettons en place ni empreinte numérique, ni publicité personnalisée.</p><p>Google peut traiter des données hors de l’Union européenne, selon ses <a href="https://policies.google.com/privacy">règles de confidentialité</a> et ses <a href="https://business.safety.google/adsprocessorterms/">conditions de traitement</a>. Cette mesure ne s’applique qu’aux visiteurs qui l’acceptent : elle ne représente donc pas toute l’audience.</p><h2>Cookies, choix et retrait</h2><p>Votre accord ou votre refus est mémorisé dans le stockage local de votre navigateur pendant 180 jours, sans identifiant individuel. Si ce stockage ne peut pas enregistrer un refus, un cookie strictement nécessaire nommé vsd_audience_refused sert de secours, pour la même durée maximale. Les cookies de mesure _ga et _ga_9EB7Q36YYM ont une durée maximale liée à cette période, sans prolongation automatique. Vous pouvez refuser ou retirer votre accord à tout moment avec le bouton ci-dessous ou en bas de chaque page. Le retrait arrête les mesures futures et supprime ces cookies accessibles sur notre domaine ; il ne supprime pas rétroactivement les statistiques déjà collectées.</p><button type="button" class="audience-settings" data-audience-settings hidden>Gérer la mesure d’audience</button><p>Si le stockage de votre navigateur est indisponible, la mesure reste désactivée. Sans JavaScript, aucune balise Analytics n’est chargée. Google Analytics est réglé sur une conservation de deux mois pour les données détaillées des utilisateurs et des événements, sans réinitialisation lors d’une nouvelle activité. Les rapports agrégés standards ne sont pas soumis à ce délai et peuvent être conservés plus longtemps, selon les <a href="https://support.google.com/analytics/answer/7667196?hl=fr">règles de conservation de Google</a>. Pour exercer vos droits, vous pouvez contacter le responsable ci-dessous.</p>') if ANALYTICS_ACTIVE else '<h2>Mesure d’audience</h2><p>Aucune balise de mesure d’audience n’est actuellement chargée par le site.</p>'
    affiliate_privacy=stay22.PRIVACY if AFFILIATE_ACTIVE or AFFILIATE_PREVIEW else ''
    return f'''<h2>Ce que le blog collecte</h2><p>Le site ne propose ni formulaire, ni compte, ni newsletter. Les cases du carnet de départ ne sont ni enregistrées ni envoyées à un serveur.</p>{analytics_notice}<h2>Responsable et contact</h2><p>Le responsable du site est identifié dans les <a href="/mentions-legales/">mentions légales</a>. Pour toute question sur vos données ou pour exercer vos droits, écrivez à <a href="mailto:{CONTACT}">{CONTACT}</a>.</p><h2>Hébergement</h2>{hosting}<h2>Liens externes</h2><p>Les pages officielles ouvertes depuis les guides appliquent leurs propres politiques de confidentialité.</p>{affiliate_privacy}<h2>Vos droits</h2><p>Vous pouvez demander l’accès à vos données, leur rectification ou leur effacement, et retirer votre consentement. Vous pouvez aussi adresser une réclamation à la <a href="https://www.cnil.fr/">CNIL</a>.</p>'''
def mentions_body():
    ownership='<h2>Propriété des contenus</h2><p>Les textes, la charte graphique et le personnage d’Alma appartiennent à l’éditeur, sauf mention contraire. Les photos de lieux restent soumises à leurs licences et attributions respectives : <a href="/credits/">voir les auteurs et les licences</a>.</p>'
    if missing_mentions:return '<h2>Statut de cette édition</h2><p>Cette préversion est préparée avant le lancement public. L’identité de l’éditeur, le directeur de la publication et l’hébergeur seront indiqués avant l’ouverture au public.</p>'+ownership
    editor,host=mentions['editeur'],mentions['hebergeur']
    legal=''.join(f'<br>{e(line)}' for line in (mention(mentions,'editeur','statut'),mention(mentions,'editeur','immatriculation')) if line)
    return f'''<h2>Éditeur du site</h2><p>{e(editor["nom"])}{legal}<br>{e(editor["adresse"])}<br>Téléphone : {e(editor["telephone"])}<br>E-mail : <a href="mailto:{e(editor["email"])}">{e(editor["email"])}</a></p><h2>Directeur de la publication</h2><p>{e(editor["directeur_publication"])}</p><h2>Hébergement</h2><p>{e(host["nom"])}<br>{e(host["adresse"])}<br>Téléphone : {e(host["telephone"])}<br><a href="{e(host["site"])}">{e(host["site"])}</a></p><h2>Contenus et intelligence artificielle</h2><p>Les guides sont recherchés, structurés et rédigés avec l’aide de l’IA à partir de sources identifiées, puis publiés sous la responsabilité de l’éditeur. Alma est un personnage virtuel créé par IA : elle ne représente aucune personne réelle. <a href="/methode/">Lire notre méthode</a>.</p>{ownership}<h2>Signaler une erreur</h2><p>Une information inexacte ou périmée ? Écrivez à <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>'''
basic('/confidentialite/','Confidentialité.','Ce que le site collecte, et surtout ce qu’il ne collecte pas.',privacy_body())
basic('/mentions-legales/','Mentions légales.',f'Éditeur, hébergement et propriété des contenus de {BRAND}.',mentions_body())
creditbody=f'<p>Les photographies représentent les lieux décrits. Elles ne sont pas présentées comme prises par {BRAND}. Elles sont redimensionnées et leur cadrage varie selon l’écran ; les adaptations des images sous licence CC BY-SA sont mises à disposition sous la même licence.</p>'
creditbody+='<div class="credit-grid">'+''.join(f'<figure>{img(key,sizes="(max-width:700px) 100vw, 260px")}<figcaption>{e(p["alt_fr"])}</figcaption>{credit(key)}</figure>' for key,p in photos.items())+'</div>'
creditbody+='<h2>Alma</h2><p>Portrait original généré avec l’outil image_gen le 14 septembre 2026. Personnage adulte entièrement fictif, sans référence à une personne réelle.</p>'
basic('/credits/','Les images, et leurs auteurs.','Sources et licences des images utilisées sur '+BRAND+'.',creditbody)
checklist=['Choisir mes dates et compter les journées complètes sur place','Vérifier les horaires de transport sur le site de l’opérateur','Choisir le quartier du logement et vérifier l’accès avec les bagages','Confirmer les conditions et le prix total avant réservation','Réserver les visites à créneau et noter l’heure à l’entrée concernée','Garder les billets et l’adresse du logement accessibles hors connexion','Prévoir chaussures adaptées, eau et pauses','Laisser une demi-journée libre et une solution en cas de pluie']
basic('/carnet/','Mon carnet de départ.','Huit repères à cocher, une place pour vos notes et les guides utiles à garder sous la main.',f'''<div class="print-sheet"><span class="eyebrow">Sans voiture · La fiche à emporter</span><h2>Prêt pour quelques jours ailleurs ?</h2><ul class="checklist">{''.join(f'<li><label><input type="checkbox">{e(x)}</label></li>' for x in checklist)}</ul><h3>Mes repères</h3><p>Destination : ____________________ · Dates : ____________________</p><p>Logement et accès : __________________________________________</p><p>Réservation à ne pas manquer : ________________________________</p><p>Une journée libre pour : ______________________________________</p></div><button class="button" data-print>Imprimer ou enregistrer en PDF</button><p style="margin-top:20px"><a href="/carnet-de-depart.txt" download>Télécharger la checklist en texte</a></p><h2>Vos guides</h2><ul>{''.join(f'<li><a href="{uri(a)}">{e(a["shortTitle"])}</a></li>' for a in articles)}</ul>''')
basic('/liens/','On part où ?',BRAND+' · Voyager sans voiture, en train et à pied.',f'''<p>Guides de voyage francophones sans voiture : Portugal, Espagne, Italie.</p><ul>{''.join(f'<li><a href="{uri(a)}">{e(a["shortTitle"])}</a></li>' for a in articles)}</ul><p><a href="/carnet/">La checklist de départ gratuite</a></p><p><a href="/a-propos/">Alma, notre présentatrice virtuelle</a></p>''')
if SHOW_SHORTS:basic('/formats-courts/','Une idée, en quelques secondes.','Alma, notre présentatrice virtuelle, explique les repères du dossier Portugal.','''<p>Deux premiers formats avec un personnage virtuel créé par IA. Il s’agit de montages de photos et de titres, accompagnés d’une voix synthétique de démonstration.</p><div class="reel-grid"><section><h2>Le Portugal sans voiture</h2><video controls playsinline preload="metadata" aria-label="Le Portugal sans voiture, avec Alma"><source src="/assets/reel-01.mp4" type="video/mp4"><track kind="captions" src="/assets/reel-01.vtt" srclang="fr" label="Français">Votre navigateur ne peut pas afficher cette vidéo.</video><p><a href="/portugal/">Ouvrir le dossier Portugal</a></p></section><section><h2>Le détail à connaître à Pena</h2><video controls playsinline preload="metadata" aria-label="Comprendre le créneau au palais de Pena"><source src="/assets/reel-02.mp4" type="video/mp4"><track kind="captions" src="/assets/reel-02.vtt" srclang="fr" label="Français">Votre navigateur ne peut pas afficher cette vidéo.</video><p><a href="/portugal/sintra-depuis-lisbonne/">Lire le guide de Sintra et ses sources</a></p></section></div><p>Alma est fictive ; ces vidéos ne sont pas des tournages sur place. Les photos et leurs adaptations sont créditées dans les <a href="/credits/">crédits images</a>. Les narrations de démonstration doivent être remplacées par une voix disposant des droits nécessaires avant diffusion commerciale.</p><p><a href="/liens/">Tous les liens utiles du blog</a></p>''')
page('/404.html','Page introuvable | '+BRAND,'Retrouvez les guides pour préparer votre voyage sans voiture.','<section class="page-heading"><span class="eyebrow">Ce chemin s’arrête ici · 404</span><h1>Un petit détour ?</h1><p>Cette page n’existe pas. Retrouvez votre route dans nos guides.</p><a class="button" href="/#destinations">Voir les destinations</a></section>',noindex=True)
(OUT/'carnet-de-depart.txt').write_text(BRAND.upper()+' — MON CARNET DE DÉPART\nVoyager sans voiture\n\n'+'\n'.join('[ ] '+x for x in checklist)+'\n\nGuides : '+ORIGIN+'/portugal/\n')
page_dates={uri(a):article_date(a,'updatedOn') for a in articles}
for catalog in ('/','/carnet/','/liens/'):page_dates[catalog]=max(page_dates.values(),default=LEGACY_DATE)
for slug in COUNTRIES:page_dates[f'/{slug}/']=max((article_date(a,'updatedOn') for a in articles if country(a)==slug),default=LEGACY_DATE)
def article_rss_date(article):
    if 'publishedOn' not in article:return 'Mon, 14 Sep 2026 12:00:00 +0200'
    return format_datetime(datetime.datetime.fromisoformat(article_date(article,'publishedOn')).replace(tzinfo=datetime.timezone.utc))
(OUT/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{ORIGIN+p}</loc><lastmod>{page_dates.get(p,LEGACY_DATE)}</lastmod></url>' for p in pages)+'</urlset>')
(OUT/'robots.txt').write_text(('User-agent: *\nAllow: /\n\nUser-agent: OAI-SearchBot\nAllow: /\n\n' if PUBLIC else '# Preversion privee : indexation desactivee avant lancement public.\nUser-agent: *\nDisallow: /\n\n')+'Sitemap: '+ORIGIN+'/sitemap.xml\n')
(OUT/'feed.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>'+e(BRAND)+'</title><link>'+ORIGIN+'</link><description>Voyager sans voiture : Portugal, Espagne, Italie</description><language>fr</language>'+''.join(f'<item><title>{e(a["title"])}</title><link>{ORIGIN+uri(a)}</link><guid>{ORIGIN+uri(a)}</guid><description>{e(a["description"])}</description><pubDate>{article_rss_date(a)}</pubDate></item>' for a in latest)+'</channel></rss>')
if PUBLIC:
    # Flux distinct du flux éditorial : Pins revus vers le même tableau Lisbonne et excursions, sans date inventée.
    config=json.loads((ROOT/'pinterest-rss.json').read_text())
    pins=config['items']
    allowed_pins={
        'pin-01-lisbonne-3-jours':('/portugal/lisbonne-3-jours-sans-voiture/',
                                    '/social-media/lancement-2026-09/pin-01-lisbonne-3-jours.jpg'),
        'pin-05-sintra-trois-temps':('/portugal/sintra-depuis-lisbonne/',
                                    '/social-media/production/sintra-facebook-2026-10/scene-01.jpg'),
        'pin-03-ou-dormir-lisbonne':('/portugal/ou-dormir-lisbonne-quartiers/',
                                    '/social-media/lancement-2026-09/pin-03-ou-dormir-lisbonne.jpg'),
    }
    if config.get('schema_version')!=1 or not isinstance(pins,list) or [p.get('id') for p in pins]!=['pin-01-lisbonne-3-jours','pin-03-ou-dormir-lisbonne','pin-05-sintra-trois-temps']:
        sys.exit('Flux Pinterest refusé : les éléments revus sont requis dans leur ordre exact.')
    media_ns='http://search.yahoo.com/mrss/'
    ET.register_namespace('media',media_ns)
    rss=ET.Element('rss',{'version':'2.0'})
    channel=ET.SubElement(rss,'channel')
    for tag,text in (('title',BRAND+' — Lisbonne'),('link',ORIGIN+'/'),('description','Guides de Lisbonne sans voiture à enregistrer.'),('language','fr')):
        ET.SubElement(channel,tag).text=text
    for pin in pins:
        if pin.get('enabled') is not True or (pin.get('link_path'),pin.get('image_path'))!=allowed_pins[pin['id']]:
            sys.exit('Flux Pinterest pilote refusé : identifiant, destination ou image non validé.')
        if not 1<=len(pin['title'])<=100 or not 1<=len(pin['description'])<=500:
            sys.exit('Flux Pinterest pilote refusé : longueur du titre ou de la description.')
        image_file=OUT/pin['image_path'].lstrip('/')
        if not image_file.is_file() or not (OUT/pin['link_path'].strip('/')/'index.html').is_file():
            sys.exit('Flux Pinterest pilote refusé : média ou guide absent du site public.')
        item=ET.SubElement(channel,'item')
        ET.SubElement(item,'title').text=pin['title']
        ET.SubElement(item,'description').text=pin['description']
        ET.SubElement(item,'link').text=ORIGIN+pin['link_path']
        ET.SubElement(item,'guid',{'isPermaLink':'false'}).text='urn:vsd:pinterest:'+pin['id']
        image_url=ORIGIN+pin['image_path']
        ET.SubElement(item,'enclosure',{'url':image_url,'length':str(image_file.stat().st_size),'type':'image/jpeg'})
        ET.SubElement(item,'{'+media_ns+'}content',{'url':image_url,'type':'image/jpeg','medium':'image','width':('1080' if pin['id']=='pin-05-sintra-trois-temps' else '1000'),'height':('1920' if pin['id']=='pin-05-sintra-trois-temps' else '1500')})
    target=OUT/'pinterest/lisbonne.xml'
    target.parent.mkdir(parents=True,exist_ok=True)
    ET.indent(rss)
    ET.ElementTree(rss).write(target,encoding='utf-8',xml_declaration=True)
if PUBLIC and (ROOT/'pinterest-additions.json').exists():
    import pinterest_feeds
    pinterest_feeds.build(ROOT,OUT,ORIGIN)
print(f'Generated {len(pages)+1} pages, {len(articles)} articles; public={PUBLIC}; out={OUT}')
