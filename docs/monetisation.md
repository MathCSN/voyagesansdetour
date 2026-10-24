# Monétisation : les liens partenaires des guides

Mis à jour le 24 octobre 2026. Code : `site-src/affiliates.py` (choix et placement),
`site-src/stay22.py` (liens Stay22), réglages `site-src/affiliates.json` et `site-src/stay22.json`.

## Ce qui se passe à chaque génération du site

Chaque guide, existant ou futur, de n'importe quel pays, reçoit ses liens au moment où
`generate.py` construit le site. La chaîne de rédaction n'a rien à faire de plus.

1. **Le lieu** vient du guide : champ `destination` et pays (`country`, nom lu dans
   `destinations.json` s'il existe). Pour un guide à l'échelle d'un pays (« Lisbonne ou Porto »,
   « Lisbonne–Porto en train »), les villes citées dans le titre qui sont aussi la destination
   d'un autre guide servent de lieux (jusqu'à deux). Si un guide porte un jour un champ `geo`
   (`{"lat": …, "lng": …}`), les coordonnées sont utilisées à la place de l'adresse.
   Aucune liste de villes n'est écrite dans le code.
2. **Les besoins** se lisent dans le texte : un hébergement pour tout guide ; des billets et
   visites quand le guide parle de musées, palais, visites, excursions (pas pour les guides
   « Transports » et « Préparer ») ; un trajet quand il parle de trains, gares, bus, ferries ;
   une assurance pour les guides hors d'Europe ou de préparation.
3. **Le placement** : le bloc hébergement suit la section « où dormir », « quartiers » ou
   « arrivée » (après le comparatif dans un guide « où dormir ») ; le bloc activités suit la
   section qui parle de visites ; à défaut, juste avant les questions.
4. **Au plus 3 liens par guide** (`max_links_per_guide`), un vrai texte d'appel, et sous
   chaque bloc la mention « Lien partenaire : nous touchons une commission, sans surcoût pour
   vous. » Les liens portent `rel="sponsored nofollow noopener"` et s'ouvrent dans un nouvel
   onglet. Aucun script, iframe ni pixel de partenaire n'est chargé.
5. **Une campagne par guide** : `vsd_<slug>` (tirets remplacés par `_`, comme le demande
   Stay22), pour suivre les clics et réservations guide par guide dans le tableau de bord.
6. Les liens n'apparaissent que dans la version publique de `https://voyagesansdetour.fr`.
   Une génération locale n'en contient aucun. Aperçu local avec liens désactivés :
   `SITE_OUT=previews/stay22/site SITE_ORIGIN=http://127.0.0.1:8770 python3 generate.py --preview-stay22`.

Les pages `/transparence/` et `/confidentialite/` changent toutes seules selon les
partenaires actifs.

## Partenaires actifs

- **GetYourGuide** (identifiant `HKEWKYM`, activé le 24/10/2026) : lien simple vers la
  recherche `https://www.getyourguide.com/fr-fr/s/?q=<lieu>&partner_id=HKEWKYM&cmp=vsd_<guide>`,
  le format que construit la barre de recherche du site lui-même. Pas de widget ni de script
  « Integration Analyzer » : ils chargeraient un script tiers soumis au consentement RGPD et
  ralentiraient les pages. Le bloc apparaît dans les guides qui parlent de visites, musées,
  monuments ou excursions (8 guides sur 14 au 24/10). À vérifier une fois dans un navigateur
  ordinaire : dans le navigateur intégré de Claude, la recherche GetYourGuide renvoyait des
  résultats sans rapport, y compris depuis sa propre barre de recherche.

## Stay22 : pourquoi c'est inactif et comment l'activer

Stay22 (« Allez ») transforme un lien en réservation suivie : `https://www.stay22.com/allez/roam`
choisit le meilleur site (Booking.com, Expedia…) et `…/allez/getyourguide` mène aux activités
GetYourGuide, payées via le même identifiant (`aid`). Le 24/10/2026, un lien
`allez/roam?aid=voyagesansdetourfr&address=Lisbonne, Portugal` ouvert dans un navigateur
redirige bien vers Booking.com avec le marquage affilié Stay22, et le lien GetYourGuide
redirige avec `partner_id` Stay22 et la campagne. Les liens sont donc techniquement prêts
(`links_verified: true`).

`stay22.json` garde deux verrous :

- `hosting_verified` : le compte Stay22 de Mathis a été vérifié, l'identifiant
  `voyagesansdetourfr` est bien le sien et le site `voyagesansdetour.fr` y est déclaré, avec
  les coordonnées de paiement. Personne d'autre que Mathis ne peut le constater : la
  documentation publique de Stay22 ne décrit pas cette étape et le tableau de bord exige sa
  connexion. Sans cela, des clics pourraient être comptés sur un identifiant qui ne paie pas.
- `enabled` : l'interrupteur. Il est refusé tant que `hosting_verified` et `links_verified`
  ne sont pas vrais.

L'action à faire par Mathis est notée dans `.github/vsd-control/attente-mathis.json`.
Une fois confirmée, une session passe `hosting_verified` et `enabled` à `true` dans
`site-src/stay22.json`, et le prochain déploiement place les liens dans tous les guides.

## Ajouter l'identifiant d'un partenaire

1. S'inscrire au programme (liens ci-dessous) et attendre l'acceptation.
2. Dans `site-src/affiliates.json`, sur l'entrée du partenaire :
   - `id` : l'identifiant affilié (lettres, chiffres, `.`, `_`, `~`, `-`). Ce n'est pas un
     secret, il apparaît dans les liens. **Jamais** de mot de passe ni de clé d'API ici : le
     dépôt est public.
   - `template` : le gabarit de lien, déjà rempli pour Civitatis et Trainline.
     Pour Omio, Heymondo et Chapka, copier le lien de suivi fourni par l'espace partenaire et
     remplacer l'identifiant par `{id}`. Repères possibles : `{campaign}` (campagne du guide),
     `{query}` (nom du lieu, encodé), `{place_slug}` (nom du lieu en minuscules avec tirets).
     Le domaine du lien doit figurer dans `domains`, sinon la génération s'arrête.
   - `enabled` : `true`.
3. Lancer `python3 -m unittest -q test_affiliates test_stay22` dans `site-src`, puis pousser.

Un partenaire sans `id`, sans gabarit ou avec `enabled: false` reste inactif sans rien casser.
Dans une catégorie, le premier partenaire actif de la liste gagne : GetYourGuide en direct
passe devant Civitatis, qui passe devant GetYourGuide via Stay22 (le repli déjà prêt).

## Les programmes qui valent le coup pour un blog voyage français

Commissions relevées le 24/10/2026 sur les pages des programmes ou des réseaux ; elles varient
selon le compte et le réseau, à confirmer dans l'espace partenaire.

| Partenaire | Catégorie | Commission typique | Inscription | Intérêt |
|---|---|---|---|---|
| Stay22 | Hôtels (+ activités GetYourGuide) | Part de la commission du site de réservation, « à partir de 30 % » (FAQ Stay22) | https://hub.stay22.com/en/auth/signup | Un seul identifiant pour Booking.com, Expedia, Hotels.com, Vrbo et GetYourGuide, liens par adresse ou coordonnées : idéal pour un blog monde entier. Priorité 1. |
| GetYourGuide | Activités | Environ 8 % (5 à 8 % selon les sources), cookie 30 jours | https://partner.getyourguide.com/ | Billets coupe-file, visites guidées : très bon taux de clic sur les guides de ville. Priorité 2. |
| Civitatis | Activités | Jusqu'à 10 %, 1 € par participant de plus de 12 ans sur les free tours | https://www.civitatis.com/fr/affilies/ | Catalogue en français, fort en Espagne, Portugal, Italie et Amérique latine. Exige un site fonctionnel, pas seulement des réseaux sociaux. |
| Trainline | Transport | Variable, fixée dans Partnerize, cookie 30 jours | https://www.thetrainline.com/about-us/partnerships/affiliates | Trains en Europe (SNCF, Renfe, Trenitalia) : utile pour les guides « sans voiture ». |
| Omio | Transport | 2 à 8 % selon les réseaux, cookie 30 jours | https://www.omio.co.uk/affiliate | Trains, bus et ferries, plus large hors de France. Alternative à Trainline. |
| Heymondo | Assurance | Non publiée, attribution 30 jours après le dernier clic | https://heymondo.fr/programme-affiliation/ | Assurance voyage en ligne, réduction pour les lecteurs ; panier élevé. |
| Chapka | Assurance | Non publiée | https://www.chapkadirect.fr/ (demander l'affiliation au service partenaires) | Assureur français (groupe Aon), connu des voyageurs au long cours. |

Sources : documentation Stay22 Allez (https://dev.stay22.com/docs/allez/parameters,
https://dev.stay22.com/docs/allez), FAQ Stay22 (https://stay22.com/faq), page affiliés
Civitatis, page partenariats Trainline, page affiliés Omio, page affiliés Heymondo,
revues de programmes (petraontheway.com, Awin, Tradedoubler) pour GetYourGuide,
presse-citron.net pour Chapka.
