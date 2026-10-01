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
e=html.escape
by_slug={a['slug']:a for a in articles}
photos={a['id']:a for a in credits['photos']}
SHARE_IMAGES={
    'brand':('brand-voyagesansdetour.png',1080,1080,'image/png'),
    'lisbonne':('lisbonne.jpg',1600,1066,'image/jpeg'),
    'porto':('porto.jpg',2200,652,'image/jpeg'),
    'sintra':('sintra.jpg',1800,818,'image/jpeg'),
    'guimaraes':('guimaraes-cover.png',1600,900,'image/png'),
}
DESTINATION_IMAGES={'Lisbonne':'lisbonne','Porto':'porto','Sintra':'sintra','Guimarães':'guimaraes'}
ILLUSTRATIONS={'guimaraes':{
    'caption':'Guimarães sans voiture — illustration typographique',
    'creditText':'Illustration typographique originale — Voyage Sans Détour',
}}
def image_data(key):
    filename,width,height,mime_type=SHARE_IMAGES[key]
    url=ORIGIN+'/assets/'+filename
    data={'@type':'ImageObject','@id':url+'#image','url':url,'contentUrl':url,'width':width,'height':height,'encodingFormat':mime_type}
    if key in photos:
        p=photos[key]
        data.update({'caption':p['alt_fr'],'creditText':p['credit_fr'],'license':p['license_url'],'creator':{'@type':'Person','name':p['author'],'url':p['author_url']}})
    elif key in ILLUSTRATIONS:
        data.update(ILLUSTRATIONS[key])
        data['creator']={'@type':'Organization','name':BRAND}
    else:data.update({'caption':'Identité visuelle de '+BRAND,'creditText':BRAND})
    return data
def photo(a):return DESTINATION_IMAGES.get(a['destination'],'brand')
def uri(a):return '/portugal/'+a['slug']+'/'
def img(key,cls='',lazy=True):
    filename,width,height,_=SHARE_IMAGES[key]
    image=image_data(key)
    return f'<img class="{cls}" src="/assets/{filename}" alt="{e(image["caption"])}" width="{width}" height="{height}" {"loading=lazy" if lazy else "fetchpriority=high"} decoding="async">'
def credit(key):
    if key in ILLUSTRATIONS:
        return f'<p class="photo-credit">{e(ILLUSTRATIONS[key]["caption"])} · {e(ILLUSTRATIONS[key]["creditText"])}</p>'
    if key not in photos:
        return f'<p class="photo-credit">Identité visuelle de {e(BRAND)}</p>'
    p=photos[key]
    return f'<p class="photo-credit">Photo : <a href="{p["source_page"]}">{e(p["author"])} / Wikimedia Commons</a> · <a href="{p["license_url"]}">{p["license"]}</a> · redimensionnée, recadrée à l’affichage.</p>'
header='''<a class="skip" href="#contenu">Aller au contenu</a><div class="topline">LE PORTUGAL, À VOTRE RYTHME — LE PREMIER DOSSIER DE VOYAGE SANS DÉTOUR</div><div class="wrap"><header class="header"><a class="brand" href="/" aria-label="Voyage Sans Détour, accueil"><small>VOYAGE</small><span>sans détour.</span></a><nav class="nav" aria-label="Navigation principale"><a href="/portugal/">Le Portugal</a><a href="/portugal/#guides">Tous les guides</a><a href="/a-propos/">L’esprit du blog</a></nav></header>'''
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
    dest.write_text(f'''<!doctype html><html lang="fr"><head>{site_verifications}<meta charset="utf-8"><meta name="referrer" content="strict-origin-when-cross-origin"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title><meta name="description" content="{e(description)}"><meta name="robots" content="{robots}"><meta name="theme-color" content="#214fe6"><link rel="canonical" href="{full}"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(description)}"><meta property="og:url" content="{full}"><meta property="og:locale" content="fr_FR"><meta property="og:site_name" content="{BRAND}"><meta property="og:type" content="{'article' if '/portugal/' in path and path!='/portugal/' else 'website'}"><meta property="og:image" content="{e(sharing['url'])}"><meta property="og:image:secure_url" content="{e(sharing['url'])}"><meta property="og:image:type" content="{sharing['encodingFormat']}"><meta property="og:image:width" content="{sharing['width']}"><meta property="og:image:height" content="{sharing['height']}"><meta property="og:image:alt" content="{e(sharing['caption'])}"><meta name="twitter:card" content="{'summary' if share_image=='brand' else 'summary_large_image'}"><meta name="twitter:image" content="{e(sharing['url'])}"><meta name="twitter:image:alt" content="{e(sharing['caption'])}"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(description)}"><link rel="icon" href="{favicon}"><link rel="stylesheet" href="/style.css"><link rel="alternate" type="application/rss+xml" title="{BRAND}" href="/feed.xml"><script type="application/ld+json">{ld}</script><script src="/site.js" defer></script>{analytics_tag}{affiliate_style}</head><body>{header}<main id="contenu">{content}</main>{footer}{audience_panel if path!="/404.html" else ""}</body></html>''')
    if not noindex:pages.append(path)
def card(a):
    return f'''<a class="card" href="{uri(a)}" data-destination="{e(a['destination'])}" data-search="{e(a['title']+' '+a['description']+' '+a['category'])}"><div class="card-image">{img(photo(a))}<span class="tag">{e(a['destination'])}</span></div><span class="meta">{e(a['category'].upper())} · {a['readMinutes']} MIN DE LECTURE</span><h3>{e(a['shortTitle'])}</h3><p>{e(a['description'])}</p></a>'''
def breadcrumb(label):return f'<nav class="breadcrumb" aria-label="Fil d’Ariane"><a href="/">Accueil</a> / <a href="/portugal/">Portugal</a> / {e(label)}</nav>'
def basic(path,title,description,body):page(path,title+' | '+BRAND,description,f'<div class="page-heading"><span class="eyebrow">{e(BRAND)}</span><h1>{e(title)}</h1><p>{e(description)}</p></div><div class="prose">{body}</div>')
first=articles[:3]
page('/',BRAND+' — Le Portugal sans voiture','Lisbonne, Porto, Sintra : des itinéraires à votre rythme, des quartiers expliqués et des transports faciles à préparer. Le Portugal sans voiture.',f'''<section class="hero"><div><span class="eyebrow">Le voyage commence bien avant le départ</span><h1>Moins d’onglets.<br>Plus <em>d’ailleurs.</em></h1><p>Une ville à explorer. Un itinéraire qui respire. Et les bonnes infos pour prendre le large, sans voiture.</p><a class="button" href="/portugal/">Trouver mon prochain départ <span aria-hidden="true">↗</span></a></div><div class="hero-visual">{img('lisbonne',lazy=False)}<div class="stamp">CAP SUR LE<b>Portugal</b>SANS VOITURE</div><span class="caption">01 / LISBONNE · Une autre idée du rythme</span></div></section><div class="manifesto"><span>Des itinéraires à votre rythme</span><span>Des sources officielles à portée de clic</span><span>Des choix expliqués, simplement</span></div><section class="section"><div class="section-head"><div><span class="eyebrow">Premier arrêt · Portugal</span><h2>Quelques jours. Déjà ailleurs.</h2></div><a class="text-link" href="/portugal/">Explorer les guides ↗</a></div><div class="grid">{''.join(card(a) for a in first)}</div></section><section class="blue-panel"><div><span class="eyebrow">Le détail qui change le départ</span><h2>Bien préparer.<br>Puis lâcher prise.</h2><p>Le bon quartier, un trajet compris, un choix de ville. Tout ce qui libère de la place pour le voyage.</p></div><ul class="quicklinks"><li><a href="/portugal/lisbonne-ou-porto/">Lisbonne ou Porto : laquelle choisir ? <span>↗</span></a></li><li><a href="/portugal/ou-dormir-lisbonne-quartiers/">Dans quel quartier dormir à Lisbonne ? <span>↗</span></a></li><li><a href="/portugal/lisbonne-porto-train/">Relier Lisbonne et Porto en train <span>↗</span></a></li></ul></section><section class="intro-note"><div><span class="eyebrow">L’esprit de {BRAND}</span><h2>La curiosité,<br>bien accompagnée.</h2></div><div><p>Un voyage commence souvent avec trente onglets ouverts. Ici, nous rassemblons les informations qui aident vraiment à choisir : un parcours raisonnable, les bons transports et les réservations à anticiper.</p><p>Nos guides sont des propositions éditoriales documentées. Les sources, les limites et la façon dont nous travaillons sont accessibles à chacun.</p><a class="text-link" href="/methode/">Découvrir notre méthode ↗</a></div></section><section class="blue-panel" style="margin-bottom:55px"><div><span class="eyebrow">À garder sous la main</span><h2>Votre départ,<br>sur une seule page.</h2><p>Une fiche de préparation à cocher et à imprimer. Pas d’adresse e-mail à laisser, juste l’essentiel à emporter.</p></div><div><a class="button light" href="/carnet/">Ouvrir mon carnet de départ ↗</a></div></section>''',share_image='lisbonne')
page('/portugal/','Portugal sans voiture : Lisbonne, Porto et Sintra | '+BRAND,'Tous nos guides pour préparer un séjour au Portugal sans voiture : itinéraires, trains, excursions et quartiers où dormir.',f'''<section class="page-heading"><span class="eyebrow">Dossier 01 · Portugal</span><h1>Le Portugal,<br>à votre rythme.</h1><p>Des villes à parcourir, des trains à prendre, des journées qui respirent. Choisissez le guide qui fera avancer votre prochain départ.</p></section><section class="section" id="guides" style="padding-top:20px"><div class="filters" aria-label="Rechercher un guide"><label class="sr-only" for="search">Rechercher un guide</label><input type="search" id="search" placeholder="Une ville, un quartier, un trajet…"><button class="filter" aria-pressed="true" data-filter="Tous">Tous</button><button class="filter" aria-pressed="false" data-filter="Lisbonne">Lisbonne</button><button class="filter" aria-pressed="false" data-filter="Porto">Porto</button><button class="filter" aria-pressed="false" data-filter="Sintra">Sintra</button></div><p class="result-count" id="result-count" aria-live="polite">{len(articles)} guides pour préparer votre séjour</p><div class="grid" id="guide-grid">{''.join(card(a) for a in articles)}</div><p class="empty" id="empty" hidden>Aucun guide ne correspond. Essayez « train », « quartier » ou une autre ville.</p></section>''',share_image='lisbonne')
for a in articles:
    body=''
    for s in a['sections']:
        body+=f'<section id="{e(s["id"])}"><h2>{e(s["title"])}</h2>'+''.join(f'<p>{e(p)}</p>' for p in s['paragraphs'])
        if s.get('bullets'):body+='<ul>'+''.join(f'<li>{e(x)}</li>' for x in s['bullets'])+'</ul>'
        if s.get('table'):
            t=s['table'];body+='<div class="table-scroll"><table><thead><tr>'+''.join(f'<th scope="col">{e(x)}</th>' for x in t['headers'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{e(str(x))}</td>' for x in row)+'</tr>' for row in t['rows'])+'</tbody></table></div>'
        body+='</section>'
    affiliate_box=stay22.guide_box(AFFILIATE,a['slug'],active=AFFILIATE_ACTIVE,preview=AFFILIATE_PREVIEW)
    affiliate_note=('Un lien affilié est signalé dans ce guide.' if affiliate_box else 'Aucun lien de réservation rémunéré n’est activé dans ce guide.') if AFFILIATE_ACTIVE or AFFILIATE_PREVIEW else 'Aucun lien de réservation rémunéré n’est activé dans cette édition.'
    faq=''.join(f'<details><summary>{e(q["question"])}</summary><p>{e(q["answer"])}</p></details>' for q in a['faq'])
    sources=''.join(f'<li><a href="{e(s["url"])}">{e(s["label"])}</a></li>' for s in a['sources'])
    related=[by_slug[x] for x in a['related'] if x in by_slug]
    toc=''.join(f'<li><a href="#{e(s["id"])}">{e(s["title"])}</a></li>' for s in a['sections'])
    schema=[{'@context':'https://schema.org','@type':'Article','headline':a['title'],'description':a['description'],'image':image_data(photo(a)),'datePublished':article_date(a,'publishedOn'),'dateModified':article_date(a,'updatedOn'),'inLanguage':'fr','author':{'@type':'Organization','name':BRAND,'url':ORIGIN+'/methode/'},'publisher':{'@id':ORIGIN+'/#organization'},'mainEntityOfPage':ORIGIN+uri(a),'citation':[s['url'] for s in a['sources']]},{'@context':'https://schema.org','@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':1,'name':'Accueil','item':ORIGIN+'/'},{'@type':'ListItem','position':2,'name':'Portugal','item':ORIGIN+'/portugal/'},{'@type':'ListItem','position':3,'name':a['shortTitle'],'item':ORIGIN+uri(a)}]}]
    page(uri(a),a['title']+' | '+BRAND,a['description'],f'''{breadcrumb(a['shortTitle'])}<header class="article-title"><span class="eyebrow">{e(a['destination'])} · {e(a['category'])}</span><h1>{e(a['title'])}</h1><p>{e(a['description'])}</p><div class="byline">{e(BRAND)} · Publié le {french_date(article_date(a,'publishedOn'))} · {a['readMinutes']} min de lecture<br>Sources consultées le {french_date(article_date(a,'sourcesCheckedOn'))} · <a href="/methode/">Méthode éditoriale</a></div></header>{img(photo(a),'article-cover',False)}{credit(photo(a))}<div class="article-layout"><article class="article-body"><div class="answer"><strong>La réponse en bref</strong><p>{e(a['summary'])}</p></div>{body}{affiliate_box}<section id="questions"><h2>Les questions avant le départ</h2>{faq}</section><section id="sources"><h2>Les sources pour préparer votre séjour</h2><p>Consultez ces pages officielles pour confirmer horaires, tarifs et conditions à vos dates. Les programmes proposés ici ne sont pas des comptes rendus de voyage.</p><ul class="source-list">{sources}</ul><p class="photo-credit">{affiliate_note} <a href="/transparence/">En savoir plus</a>.</p></section></article><aside class="toc" aria-label="Sommaire"><strong>Dans ce guide</strong><ol>{toc}<li><a href="#questions">Vos questions</a></li><li><a href="#sources">Sources officielles</a></li></ol><button type="button" class="button" data-print>Imprimer le guide</button></aside></div><section class="section"><div class="section-head"><h2>Pour la suite du voyage.</h2></div><div class="grid">{''.join(card(x) for x in related)}</div></section>''',schema,share_image=photo(a))
basic('/a-propos/','Un peu plus d’ailleurs.','Un média de voyage pour faire des choix simples et préparer des journées qui vous ressemblent.',f'''<h2>Le voyage, avant le voyage</h2><p>{BRAND} rassemble des guides pratiques pour les voyageurs francophones. Notre premier dossier explore le Portugal sans voiture : Lisbonne, Porto, Sintra et les trajets qui les relient.</p><p>Nous préférons un programme faisable à une liste interminable de lieux. Chaque guide précise à qui il peut convenir, les arbitrages à faire et les informations à confirmer avant de réserver.</p><div class="profile"><img src="/assets/alma.jpg" alt="Alma, personnage virtuel créé par intelligence artificielle" width="563" height="1000" loading="lazy"><div><span class="eyebrow">Le visage de nos formats courts</span><h2>Voici Alma.</h2><p>Alma est une présentatrice virtuelle originale, créée par intelligence artificielle. Elle incarne nos formats courts et explique les idées de voyage du média.</p><p>Son image ne représente pas une voyageuse réelle. Elle ne signe pas de témoignages de séjour et ne prétend pas avoir testé des hôtels.</p></div></div><h2>Des repères, et leurs sources</h2><p>Les contenus de cette première édition ont été préparés avec l’aide de l’IA, à partir de pages d’offices de tourisme, d’opérateurs de transport et de monuments. Une vérification des sources ne remplace pas une visite sur place.</p><p><a href="/methode/">Lire notre méthode éditoriale</a> · <a href="/transparence/">Comprendre la monétisation</a></p>''')
basic('/methode/','Comment nous préparons les guides.','Les sources, les choix éditoriaux et les limites de cette première édition.',f'''<h2>Une question précise par guide</h2><p>Un article doit aider à prendre une décision : choisir une ville, un quartier, un trajet ou un programme. Les itinéraires sont des propositions éditoriales à adapter, pas des séjours présentés comme vécus.</p><h2>Des sources identifiées</h2><p>Les informations pratiques sont recherchées sur les sites des opérateurs, monuments et organismes touristiques. Les liens figurent au bas des articles. La date indiquée correspond à la consultation des sources, pas à un voyage sur place.</p><h2>Le rôle de l’intelligence artificielle</h2><p>Cette première édition a été recherchée, structurée et rédigée avec l’aide de l’IA. Les contenus n’ont pas encore bénéficié d’une relecture indépendante par une personne ayant testé les itinéraires. L’IA peut commettre des erreurs : utilisez les sources officielles pour toute réservation.</p><h2>Prix, horaires et recommandations</h2><p>Les prix non confirmés sont omis. Les conditions peuvent changer après consultation. Une idée d’itinéraire exprime un choix éditorial ; un avis d’hôtel ou un retour d’expérience ne peut être attribué qu’à son auteur réel.</p><h2>Images et corrections</h2><p>Les photos des destinations sont des images réelles sous licence, avec auteurs et liens dans les crédits. Alma est une image générée d’un personnage fictif.</p><h2>Signaler une erreur</h2><p>Une information inexacte ou périmée ? Écrivez à <a href="mailto:{CONTACT}">{CONTACT}</a> en indiquant la page concernée.</p>''')
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
creditbody=f'<p>Les photographies représentent les lieux décrits. Elles ne sont pas présentées comme prises par {BRAND}. Elles sont redimensionnées et leur cadrage varie selon l’écran ; les adaptations des images sous CC BY-SA 4.0 sont mises à disposition sous cette même licence.</p>'
for key,p in photos.items():creditbody+=f'<h2>{key.title()}</h2>{img(key)}{credit(key)}'
for key in ILLUSTRATIONS:creditbody+=f'<h2>Guimarães : illustration originale</h2>{img(key)}{credit(key)}'
creditbody+='<h2>Alma</h2><p>Portrait original généré avec l’outil image_gen le 14 septembre 2026. Personnage adulte entièrement fictif, sans référence à une personne réelle.</p>'
basic('/credits/','Les images, et leurs auteurs.','Sources et licences des images utilisées sur '+BRAND+'.',creditbody)
checklist=['Choisir mes dates et compter les journées complètes sur place','Vérifier les horaires de transport sur le site de l’opérateur','Choisir le quartier du logement et vérifier l’accès avec les bagages','Confirmer les conditions et le prix total avant réservation','Réserver les visites à créneau et noter l’heure à l’entrée concernée','Garder les billets et l’adresse du logement accessibles hors connexion','Prévoir chaussures adaptées, eau et pauses','Laisser une demi-journée libre et une solution en cas de pluie']
basic('/carnet/','Mon carnet de départ.','Huit repères à cocher, une place pour vos notes et les guides utiles à garder sous la main.',f'''<div class="print-sheet"><span class="eyebrow">Portugal · La fiche à emporter</span><h2>Prêt pour quelques jours ailleurs ?</h2><ul class="checklist">{''.join(f'<li><label><input type="checkbox">{e(x)}</label></li>' for x in checklist)}</ul><h3>Mes repères</h3><p>Destination : ____________________ · Dates : ____________________</p><p>Logement et accès : __________________________________________</p><p>Réservation à ne pas manquer : ________________________________</p><p>Une journée libre pour : ______________________________________</p></div><button class="button" data-print>Imprimer ou enregistrer en PDF</button><p style="margin-top:20px"><a href="/carnet-de-depart.txt" download>Télécharger la checklist en texte</a></p><h2>Vos guides</h2><ul>{''.join(f'<li><a href="{uri(a)}">{e(a["shortTitle"])}</a></li>' for a in articles)}</ul>''')
basic('/liens/','On part où ?',BRAND+' · Moins d’onglets. Plus d’ailleurs.',f'''<p>Guides de voyage francophones. Premier dossier : le Portugal sans voiture.</p><ul>{''.join(f'<li><a href="{uri(a)}">{e(a["shortTitle"])}</a></li>' for a in articles)}</ul><p><a href="/carnet/">La checklist de départ gratuite</a></p><p><a href="/a-propos/">Alma, notre présentatrice virtuelle</a></p>''')
if SHOW_SHORTS:basic('/formats-courts/','Une idée, en quelques secondes.','Alma, notre présentatrice virtuelle, explique les repères du dossier Portugal.','''<p>Deux premiers formats avec un personnage virtuel créé par IA. Il s’agit de montages de photos et de titres, accompagnés d’une voix synthétique de démonstration.</p><div class="reel-grid"><section><h2>Le Portugal sans voiture</h2><video controls playsinline preload="metadata" aria-label="Le Portugal sans voiture, avec Alma"><source src="/assets/reel-01.mp4" type="video/mp4"><track kind="captions" src="/assets/reel-01.vtt" srclang="fr" label="Français">Votre navigateur ne peut pas afficher cette vidéo.</video><p><a href="/portugal/">Ouvrir le dossier Portugal</a></p></section><section><h2>Le détail à connaître à Pena</h2><video controls playsinline preload="metadata" aria-label="Comprendre le créneau au palais de Pena"><source src="/assets/reel-02.mp4" type="video/mp4"><track kind="captions" src="/assets/reel-02.vtt" srclang="fr" label="Français">Votre navigateur ne peut pas afficher cette vidéo.</video><p><a href="/portugal/sintra-depuis-lisbonne/">Lire le guide de Sintra et ses sources</a></p></section></div><p>Alma est fictive ; ces vidéos ne sont pas des tournages sur place. Les photos et leurs adaptations sont créditées dans les <a href="/credits/">crédits images</a>. Les narrations de démonstration doivent être remplacées par une voix disposant des droits nécessaires avant diffusion commerciale.</p><p><a href="/liens/">Tous les liens utiles du blog</a></p>''')
page('/404.html','Page introuvable | '+BRAND,'Retrouvez les guides pour préparer votre voyage au Portugal.','<section class="page-heading"><span class="eyebrow">Ce chemin s’arrête ici · 404</span><h1>Un petit détour ?</h1><p>Cette page n’existe pas. Retrouvez votre route dans nos guides.</p><a class="button" href="/portugal/">Explorer le Portugal</a></section>',noindex=True)
(OUT/'carnet-de-depart.txt').write_text(BRAND.upper()+' — MON CARNET DE DÉPART\nPortugal sans voiture\n\n'+'\n'.join('[ ] '+x for x in checklist)+'\n\nGuides : '+ORIGIN+'/portugal/\n')
page_dates={uri(a):article_date(a,'updatedOn') for a in articles}
for catalog in ('/portugal/','/carnet/','/liens/'):
    page_dates[catalog]=max(page_dates.values(),default=LEGACY_DATE)
def article_rss_date(article):
    if 'publishedOn' not in article:return 'Mon, 14 Sep 2026 12:00:00 +0200'
    return format_datetime(datetime.datetime.fromisoformat(article_date(article,'publishedOn')).replace(tzinfo=datetime.timezone.utc))
(OUT/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{ORIGIN+p}</loc><lastmod>{page_dates.get(p,LEGACY_DATE)}</lastmod></url>' for p in pages)+'</urlset>')
(OUT/'robots.txt').write_text(('User-agent: *\nAllow: /\n\nUser-agent: OAI-SearchBot\nAllow: /\n\n' if PUBLIC else '# Preversion privee : indexation desactivee avant lancement public.\nUser-agent: *\nDisallow: /\n\n')+'Sitemap: '+ORIGIN+'/sitemap.xml\n')
(OUT/'feed.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>'+e(BRAND)+'</title><link>'+ORIGIN+'</link><description>Le Portugal sans voiture</description><language>fr</language>'+''.join(f'<item><title>{e(a["title"])}</title><link>{ORIGIN+uri(a)}</link><guid>{ORIGIN+uri(a)}</guid><description>{e(a["description"])}</description><pubDate>{article_rss_date(a)}</pubDate></item>' for a in articles)+'</channel></rss>')
if PUBLIC:
    # Flux distinct du flux éditorial : deux Pins revus vers le même tableau Lisbonne, sans date inventée.
    config=json.loads((ROOT/'pinterest-rss.json').read_text())
    pins=config['items']
    allowed_pins={
        'pin-01-lisbonne-3-jours':('/portugal/lisbonne-3-jours-sans-voiture/',
                                    '/social-media/lancement-2026-09/pin-01-lisbonne-3-jours.jpg'),
        'pin-03-ou-dormir-lisbonne':('/portugal/ou-dormir-lisbonne-quartiers/',
                                    '/social-media/lancement-2026-09/pin-03-ou-dormir-lisbonne.jpg'),
    }
    if config.get('schema_version')!=1 or not isinstance(pins,list) or [p.get('id') for p in pins]!=list(allowed_pins):
        sys.exit('Flux Pinterest refusé : les deux éléments revus sont requis dans leur ordre exact.')
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
        ET.SubElement(item,'{'+media_ns+'}content',{'url':image_url,'type':'image/jpeg','medium':'image','width':'1000','height':'1500'})
    target=OUT/'pinterest/lisbonne.xml'
    target.parent.mkdir(parents=True,exist_ok=True)
    ET.indent(rss)
    ET.ElementTree(rss).write(target,encoding='utf-8',xml_declaration=True)
print(f'Generated {len(pages)+1} pages, {len(articles)} articles; public={PUBLIC}; out={OUT}')
