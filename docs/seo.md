# Référencement : ce qui est en place, comment le suivre

État mesuré le 11 novembre 2026 (session « trafic SEO »). Une page pour savoir ce que le site fait
tout seul pour être trouvé sur Google, où lire les chiffres, et quoi faire quand une alerte tombe.

## Le constat de départ

Search Console (propriété `https://voyagesansdetour.fr/`), lu le 11/11/2026 :

- **38 pages indexées, 15 non indexées** (relevé Google du 06/11). Les guides sont indexés : 14 pages
  « Détectée, actuellement non indexée » sur 15 étaient des pages listes (pays à un seul guide,
  `/guides/` et ses rubriques, crédits, confidentialité, `/liens/`), plus un seul guide
  (`lisbonne-ou-porto`).
- **6 clics pour 771 impressions en 28 jours**, position moyenne 19. Deux guides étaient déjà en
  première page sans être cliqués : New York à Noël (353 impressions, position 8,4, 1 clic) et
  Londres (141 impressions, position 7,6, 0 clic).
- **0 lien externe** connu de Google.

Ce que ça dit : Google explore et indexe les guides, mais (1) les titres de 90 à 121 caractères
étaient coupés dans les résultats, donc personne ne cliquait ; (2) les pages listes étaient trop
minces pour mériter une place (120 à 190 mots) ; (3) le site n'a aucune autorité, donc Google
n'explore que lentement ce qui n'est pas un guide.

## Ce que le site fait désormais tout seul

Tout est tenu par `site-src/generate.py` et vérifié par `site-src/test_site.py` : une régression
fait échouer le build avant la mise en ligne.

| Règle | Où |
| --- | --- |
| Balise `<title>` de 60 caractères au plus, description de 70 à 160, uniques, un seul `<h1>` | `title_tag`, `guide_title`, `meta_description` |
| Titre court, description et questions cherchées par guide | `site-src/seo.json` |
| Un guide sans entrée dans `seo.json` garde un titre court : son titre, sinon la partie avant « : », sinon son titre de carte ; une description trop longue est coupée à un mot entier | `guide_title`, `meta_description` |
| Page pays lisible seule : réponse courte et trois chiffres datés de chaque guide | `country_brief` |
| Page continent : un paragraphe et les guides de chaque pays | `continent_page` |
| Chaque guide renvoie vers son pays, sa rubrique, trois guides liés et jusqu'à douze voisins | `more_guides`, `main_rubrique` |
| Rubriques liées depuis le pied de toutes les pages ; « Quand partir » se déduit du titre, « Que faire » existe | `RUBRIQUES`, `theme_links` |
| `/liens/` (page de liens des profils sociaux) hors des résultats et du sitemap | `noindex=True` |
| Date de mise à jour visible et dans le schéma `Article` ; `FAQPage`, `BreadcrumbList`, `ItemList` | rendu d'article |
| Polices en WOFF2, images avec dimensions, `loading=lazy` sauf la première | `page`, `img` |
| Copies de 400 et 1 200 px de chaque photo, créées au déploiement et jamais commitées : un téléphone ne télécharge plus le fichier de 1 600 px, une vignette plus celui de 800 px | `photo_variants.py`, étape de `build-pages.yml` |
| Sitemap daté par page (`lastmod` = dernière mise à jour du guide ou du plus récent guide de la liste) | fin de `generate.py` |

### Pourquoi `seo.json` et pas `articles.json`

L'empreinte d'un guide dans `articles.json` lie ses épingles, ses reels et son reçu de
publication : y ajouter un champ aurait périmé tous les brouillons en cours. `seo.json` ne touche à
rien. La page garde son titre complet dans le `<h1>` (la chaîne des posts refuse un guide dont le
titre a disparu de la page).

Format, vérifié par le générateur (une entrée invalide arrête le build) :

```json
{"schemaVersion": 1, "guides": {"new-york-noel": {
  "title": "Sapin du Rockefeller Center 2026 : dates de Noël à New York",
  "description": "facultative, 160 caractères au plus",
  "faq": [{"question": "Quand arrive le sapin de Noël à New York en 2026 ?", "answer": "…"}]}}}
```

Règles de rédaction : le titre commence par les mots que les gens tapent (lus dans Search Console),
tient en 60 caractères et porte un chiffre ou une année quand le guide en donne ; une question
ajoutée reprend **un fait déjà sourcé dans le guide**, jamais une information nouvelle ; pas de
répétition de mots-clés.

## Prévenir les moteurs

- **Google** lit `sitemap.xml` (déclaré dans `robots.txt` et dans Search Console, relu le 10/11) et
  ses dates `lastmod`. Il n'existe plus de « ping » Google : la date exacte suffit.
- **Bing, Yandex, Seznam, Naver** : `site-src/indexnow.py` envoie, après chaque déploiement
  (`build-pages.yml`, étape non bloquante), les pages dont la date de sitemap est d'aujourd'hui ou
  d'hier. La clé IndexNow est un fichier public à la racine du site (`<clé>.txt`), pas un secret.
  Après un changement de gabarit qui touche toutes les pages, lancer une fois :

```bash
python3 site-src/indexnow.py --all
```

## Suivre les chiffres

Le panneau privé (`vsd-admin`) détient le seul accès Google, en lecture seule. Il relève :

- clics et impressions sur 28 jours et sur les 28 jours précédents, les 10 premières requêtes et
  les **requêtes en hausse** (gain d'impressions d'une période à l'autre) ;
- l'**indexation page par page** : 8 pages du sitemap sont inspectées chaque heure par l'API
  d'inspection d'URL de la Search Console (le rapport « Indexation des pages » n'a pas d'API). Tout
  le site est relu en moins d'une journée ; un historique de 90 jours est gardé.

Où lire :

- le **panneau**, bloc « Indexation Google » : pages indexées, pages en attente avec leur état,
  requêtes en hausse ;
- le **rapport hebdomadaire** (issue `rapport-hebdo` du lundi), section « Référencement Google ».
  `seo-status.mjs` lit le résumé du panneau par un appel signé en lecture seule ; si le panneau ne
  répond pas, le rapport le dit et continue.

### Les alertes (issue `alerte-file`, vérifiée chaque jour)

| Alerte | Déclenchement | Quoi faire |
| --- | --- | --- |
| Indexation en recul | 2 pages et 10 % de pages indexées en moins qu'il y a 7 jours, sur des tournées complètes | Ouvrir le panneau : lire l'état des pages sorties. « Exclue par la balise noindex » ou « Introuvable (404) » sur un guide : bug du site, relancer `test_site.py` et le dernier déploiement. « Explorée, non indexée » en série : contenu jugé faible, revoir les guides concernés (longueur, faits datés, doublons) avant d'en publier d'autres. |
| Impressions divisées par deux | Moins de la moitié des impressions des 28 jours précédents, à partir de 300 | Vérifier d'abord la saison (les guides de Noël retombent en janvier), puis l'indexation, puis Search Console > Sécurité et actions manuelles. |

## Autorité : ce qui est fait, ce qui attend, ce qui est écarté

- **Fait** : profils Pinterest et Instagram déclarés (`sameAs`, liens `rel="me"`), flux RSS,
  IndexNow, sitemap exact.
- **Attend Mathis** (`attente-mathis.json`) : importer le site dans Bing Webmaster Tools depuis
  Search Console (2 minutes) ; coller les bios avec le lien du site.
- **Écarté après recherche le 11/11** : les annuaires de blogs voyage francophones ouverts
  n'existent plus sous une forme utile ; les classements (Globe-Trotting, Tourdumondiste) rangent
  les blogs par audience et n'ont rien à faire d'un site à trois visites, à revoir au-delà de
  quelques milliers de visites par mois. Poster des liens sur des forums depuis un compte
  automatique serait du spam : non. Achat de liens, échanges, pages satellites : jamais.
- **Ce qui construit vraiment l'autorité ici** : des guides qui donnent un chiffre daté que les
  autres n'ont pas (les deux guides de Noël sont arrivés en première page en trois semaines sans
  aucun lien), publiés deux à trois mois avant leur saison, et repris par les épingles.

## Consignes pour les routines de rédaction

Texte à ajouter aux consignes des routines (appliqué par la session de pilotage) :

> **Référencement.** Avant d'écrire, lis `docs/seo.md`. Pour chaque nouveau guide, ajoute son entrée
> dans `site-src/seo.json` : un `title` de 60 caractères au plus qui commence par la requête visée
> (« Quand partir à… », « … en 3 jours », « Budget … 2 semaines ») et porte un chiffre ou l'année
> quand le guide en donne ; une `description` de 120 à 155 caractères avec deux ou trois chiffres
> du guide ; et une ou deux questions `faq` formulées comme on les tape dans Google, dont la
> réponse reprend mot pour mot un fait déjà sourcé dans le guide. Le champ `title` d'`articles.json`
> reste le titre long affiché sur la page ; ne le raccourcis pas. Dans `related`, mets d'abord un
> guide du même pays, puis un guide du même type. N'écris jamais deux guides sur la même requête :
> si un guide existe déjà sur le sujet, propose une mise à jour. Lance `python3 -m unittest -q
> test_site` : il refuse un titre de plus de 60 caractères, une description hors 70 à 160 et un
> titre en double.

Chaque trimestre, ou quand le rapport montre des requêtes en hausse sans clic : relire dans
Search Console les requêtes des guides en positions 5 à 20 et ajuster leur `title` dans `seo.json`.

## Mesures du 11/11/2026

Build de `main` (avant) et de cette branche (après), 57 puis 59 pages :

| | Avant | Après |
| --- | ---: | ---: |
| Titres de plus de 60 caractères | 41 | 0 |
| Descriptions hors 70 à 160 caractères | 11 | 0 |
| Pages pays : mots (médiane) | 151 | 318 |
| Guides : liens entrants depuis le contenu des autres pages (minimum / médiane) | 7 / 10 | 12 / 18 |
| Rubriques : pages qui y mènent depuis leur contenu (pied de page non compté) | 0 à 1 | 8 à 22 |
| Polices : poids transféré des 7 fichiers | 288 Ko | 213 Ko |
| Photo d'en-tête d'un guide sur un téléphone récent (médiane) | 361 Ko | 185 Ko |
| Photo d'en-tête des guides de Lisbonne (`lisbonne.jpg`) sur téléphone | 575 Ko | 79 à 163 Ko |

Lighthouse mobile (version en ligne de commande, connexion 4G lente simulée), sur les deux builds
servis en local. Une seule mesure par page, sauf l'accueil d'avant mesuré deux fois ; la machine
était chargée, d'où l'écart entre ces deux mesures : à lire comme un ordre de grandeur.

| Page | Performance avant | Performance après | Poids avant | Poids après | Plus grand élément affiché, avant puis après |
| --- | ---: | ---: | ---: | ---: | --- |
| Accueil | 42 et 76 | 90 | 1 663 Ko | 560 Ko | 7,3 à 7,5 s puis 3,5 s |
| Guide (Japon en 2 semaines) | 94 | 100 | 633 Ko | 399 Ko | 0,9 s puis 0,9 s |
| Page pays (Japon) | 81 | 90 | 639 Ko | 453 Ko | 4,1 s puis 3,5 s |

Accessibilité, bonnes pratiques et SEO : 100 sur les trois pages après (la page pays était à 98 en
accessibilité). Sur le site en ligne, avant, la même commande donnait 54 (accueil), 68 (guide) et
63 (`/guides/`), avec un temps de blocage gonflé par la charge de la machine. Les poids locaux
d'avant comptent les polices sans compression ; en ligne elles pesaient 263 Ko par page, 193 Ko
désormais. Le plus grand élément des pages listes reste la photo d'en-tête de 800 px (85 à 160 Ko) :
3,5 s en 4G lente simulée, au-dessus du seuil « bon » de 2,5 s.

## Limites connues

- GitHub Pages impose un cache de 10 minutes sur tous les fichiers : l'audit « cache » de Lighthouse
  ne peut pas passer sans changer d'hébergeur ou placer un CDN devant.
- Les photos restent en JPEG (400, 800, 1 200 et 1 600 px). Les copies de 400 et 1 200 px sont créées par le
  déploiement (Pillow, étape non bloquante) : si l'étape échoue, le site sort avec 800 et 1 600 px
  comme avant. Un format WebP ou AVIF demanderait de toucher à la chaîne des photos.
- Lighthouse émule un téléphone à 1,75 pixel par point, qui prenait déjà le fichier de 800 px : le
  gain des copies de 1 200 px ne se voit que sur les vrais téléphones (2 à 3 pixels par point).
- L'inspection d'URL donne l'état connu de Google, pas une promesse d'indexation ; une page neuve
  met de quelques jours à quelques semaines à entrer dans l'index d'un site jeune.
- Le suivi dépend du panneau privé : tant que sa version avec l'appel `seo` n'est pas déployée, le
  rapport écrit « relevé indisponible ».
