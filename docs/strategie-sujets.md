# Stratégie des sujets : ce que le blog écrit, et pourquoi

Mesuré le 24 octobre 2026 (session « contenus monde »). Ce document explique comment les
77 sujets de `.github/vsd-writing/guide-topics.json` ont été choisis et classés, comment la
chaîne choisit le prochain guide, et ce que coûte le rythme de publication.

## En bref

- Le blog écrit sur **ce que les Français cherchent vraiment** : itinéraires de 10 à 15 jours,
  « quand partir », budgets, quartiers où dormir, road trips, avec des requêtes précises
  (« Kyoto en 3 jours », « budget Laponie ») plutôt que des requêtes de tête (« Japon »).
- **77 sujets** : 31 en Europe, 11 en Afrique, 2 au Moyen-Orient, 16 en Asie, 7 en Amérique du Nord,
  5 en Amérique centrale et Caraïbes, 2 en Amérique du Sud, 3 en Océanie ; 9 types de guides
  (26 itinéraires, 12 « quand partir », 12 visites, 9 « que faire », 8 road trips, 4 budgets…).
- La chaîne écrit d’abord les sujets les mieux notés **2 à 3 mois avant leur saison**.
- **Un guide tous les deux jours** (3 à 4 par semaine), dans le quota gratuit de Workers AI.
- Les six premiers guides monde (Japon, Thaïlande, New York à Noël, Londres en décembre,
  Laponie, Costa Rica) ont été écrits à la main le 24/10 ; ce sont les six sujets les mieux
  classés ce jour-là, hors Portugal, Espagne et Italie.

## La méthode de recherche

Trois mesures, toutes faites en France et en français le 24 octobre 2026. Les données brutes
(environ 800 requêtes) ont servi au calcul et ne sont pas versionnées : seuls les scores
qui en découlent figurent dans le champ `demand` de chaque sujet.

1. **Suggestions Google** (le menu déroulant de la recherche, `hl=fr`, `gl=fr`) pour 27 tournures
   de voyage (« quand partir au », « itinéraire 10 jours », « budget voyage », « où dormir à »,
   « road trip », « que faire à », « 3 jours à », « combien coûte un voyage »…), chacune suivie
   des 26 lettres de l’alphabet : 729 requêtes. Chaque suggestion rapporte 10 points en
   première position, 1 point en dixième. Le score d’une destination pour un type de guide
   additionne ses points sur toutes les tournures de ce type.
2. **Google Tendances**, France, sur 5 ans, pour « voyage + destination », comparé à
   « voyage japon » (étalon = 1,0), sur 100 destinations. On en tire l’intérêt relatif et le
   **mois de pic des recherches**.
3. **Suggestions Pinterest** (France) pour 60 amorces (« voyage japon », « itinéraire »,
   « quand partir »…), afin de repérer les angles qui plaisent sur le canal du site.

### Ce que disent les données

- **Janvier est le mois de préparation** des voyages lointains : Thaïlande, Bali, Mexique,
  Vietnam, Islande, Cap-Vert, Maurice, Réunion et Égypte culminent en janvier. Publier en
  novembre et décembre laisse le temps d’être indexé avant ce pic.
- Les **saisons de Noël** cherchent tôt : Laponie (pic en décembre, dès août), Londres et
  Prague (novembre), Vienne (décembre), New York (novembre-décembre).
- Les tournures les plus fortes : « quand partir » (Vietnam, Japon, Sri Lanka, Cap-Vert,
  Mexique, Thaïlande, Égypte, Bali, Réunion, Maurice), « itinéraire 10 ou 15 jours »
  (Thaïlande, Sri Lanka, Vietnam, Costa Rica, Japon, Philippines), « budget » (Japon,
  Laponie, Polynésie, Thaïlande, Vietnam), « où dormir » (Tokyo, Londres, Rome, Bangkok).
- La Grèce, le Maroc et Dubaï ont l’intérêt Trends le plus fort, mais des requêtes très
  concurrentielles : le plan les aborde par des angles précis (Crète, Cyclades en ferry,
  Marrakech en 3 jours, Dubaï en 4 jours).
- Pinterest pousse les angles « aesthetic », « famille », « couple », « hiver » et « Noël » :
  les photos libres et les guides de saison servent ce canal.

## La note de chaque sujet

`priorité = 0,5 × demande + 0,3 × intérêt + 0,2 × portée`, chaque terme sur 100 :

- **demande** : score des suggestions Google pour la destination et le type de guide
  (100 à partir de 120 points ; pour les guides de ville, les tournures « 3 jours à » et
  « week-end à » comptent pour moitié) ;
- **intérêt** : Google Tendances relatif au Japon (100 à partir de 1,0) ;
- **portée** : chance d’un site jeune d’apparaître : 85 pour une longue traîne précise
  (ville ou région + intention), 60 à 70 pour un pays + intention précise, 35 pour une
  requête de tête (« quand partir au Vietnam »).

Les trois composantes sont gardées dans le champ `demand` de chaque sujet.

### Le choix du prochain guide

`topic_plan.py` ajoute un **bonus de saison** selon le nombre de mois avant le premier mois de
voyage du sujet (`travelMonths`) : +30 à 2 ou 3 mois, +20 à 1 mois, +10 à 4 mois, +5 en
pleine saison. Les trois meilleurs sujets du jour tournent matin et après-midi : un sujet bloqué
(source fermée, faits insuffisants) ne bloque jamais le calendrier. Un sujet déjà publié,
en file ou en candidat n’est jamais réécrit.

## Les sources d’un sujet

Chaque sujet a 2 ou 3 sources, toutes lues le 24/10/2026 avec le lecteur de la chaîne
(178 adresses, toutes accessibles) :

1. une page **officielle** quand elle répond (opérateur de transport, monument, office du
   tourisme, service météo) : c’est elle qui donne les prix ;
2. **Seat61** pour les trains, ferries et durées (pages datées, mises à jour en 2026) ;
3. **Wikivoyage** ou **Wikipédia** pour le climat, la géographie, les quartiers et les durées.

Règle tenue dans le code (`REFERENCE_HOSTS` dans `guide_draft.py`) : **aucun prix n’est tiré
d’un wiki**. Une phrase de Wikivoyage ou de Wikipédia qui contient un prix n’entre jamais dans
le catalogue de citations : un prix de wiki n’a pas de date fiable, et le site promet des prix
relevés à une date donnée. Les mots-clés du sujet (`keywords`) font passer en premier les
phrases qui parlent de lui avec un chiffre (prix, durée, température, numéro de ligne).

Beaucoup de sites officiels bloquent les robots (Office du tourisme de Thaïlande, Dubaï, Maroc,
Nouvelle-Zélande, Tahiti, MTA de New York, Rockefeller Center) : ils ne figurent pas dans le
plan. Pour le Costa Rica, le site des parcs (SINAC) ne répond pas ; le guide écrit à la main
cite deux sources datées de 2026 qui concordent (Earthtrekkers, The Rio Times).

## Les photos

Chaque sujet liste 3 ou 4 photos voulues : un identifiant, des mots de recherche, des mots
obligatoires dans le titre ou la description du fichier, et un texte alternatif. La chaîne
(`guide_photos.py`) interroge Wikimedia Commons, garde un fichier JPEG paysage d’au moins
1 600 px sous licence **CC BY, CC BY-SA ou CC0**, avec un auteur (« Attribution » puis
« Artist »), télécharge les versions 1 600 et 800 px, les recompresse en JPEG progressif
qualité 72 comme les photos existantes, et inscrit auteur, licence, lien de licence et page
source dans `site-src/image-sources.json`. Moins de 3 photos : le guide attend, sans
dépenser d’inférence. Les 234 photos du plan ont été testées le 24/10 : toutes trouvables.

Les textes alternatifs décrivent **le sujet** (« Le temple Kiyomizu-dera, à Kyoto »), jamais
une scène (« au lever du soleil », « un train passe ») : le contrôle visuel des 20 premières
photos a montré qu’une scène écrite d’avance ne correspond pas toujours au fichier trouvé.

## Le rythme et ce qu’il coûte

### Le calendrier

- `RELEASE_INTERVAL` = **2 jours** (`site-src/editorial_queue.py`) : un guide au plus tous les
  deux jours, compté en jours de Paris, soit 3 à 4 guides par semaine.
- Un guide peut être écrit **jusqu’à 30 heures avant** son créneau (`GUIDE_LOOKAHEAD`) : la
  veille d’un créneau, la chaîne prépare le guide suivant ; si elle échoue, elle a encore
  le lendemain matin.
- `vsd-writing-guide.yml` tourne **à 6 h 23 et 15 h 23 UTC chaque jour**. Quand le calendrier
  est plein, le passage s’arrête avant toute photo, source ou inférence (`calendar_full`).
- `build-pages.yml` publie le guide à son heure, après avoir relu ses sources.

### Le quota Workers AI (vérifié le 24/10/2026)

- Offre gratuite : **10 000 neurones par jour**, remis à zéro chaque jour à 0 h UTC ; au-delà,
  les appels échouent, rien n’est facturé.
- Llama 3.3 70B (le rédacteur et le relecteur) : 26 668 neurones par million de jetons en
  entrée, **204 805 en sortie**. Qwen3 30B, autorisé pour la rédaction : 4 625 et 30 475.
- Un guide accepté coûte environ **3 400 neurones** : extraction des faits (≈ 350), contrôle
  des citations (≈ 400), rédaction (≈ 750), relecture globale (≈ 400) et relecture bloc par
  bloc (≈ 1 500 pour 45 blocs). Une révision automatique ajoute jusqu’à 1 500 neurones.
- Plafond codé : **4 800 neurones par passage** (`NEURON_BUDGET`), 40 appels au plus. Deux
  passages et la découverte quotidienne des mises à jour (≈ 1 500 au plus) tiennent dans les
  10 000 gratuits.
- Au rythme d’un guide tous les deux jours, la rédaction consomme environ 1 700 neurones par
  jour en moyenne : le quota gratuit suffit, avec de la marge pour les échecs.

### Ce que coûterait un rythme plus élevé

| Rythme | Neurones par jour | Offre | Coût estimé |
| --- | --- | --- | --- |
| 1 guide tous les 2 jours (actuel) | ≈ 1 700 en moyenne | gratuite | 0 € |
| 1 guide par jour | 3 400 à 4 800 | gratuite, sans marge les jours de révision | 0 € |
| 2 guides par jour | 7 000 à 9 600 + découverte | Workers Paid recommandé | 5 $ par mois |
| 3 guides par jour | 10 000 à 14 500 | Workers Paid | 5 $ + ≈ 1,50 $ par mois de dépassement |

Calcul : Workers Paid coûte 5 $ par mois minimum ; Workers AI y est facturé 0,011 $ les 1 000
neurones au-delà des 10 000 quotidiens. Un guide supplémentaire coûte donc environ 0,04 $.
Pour accélérer, il suffit de baisser `RELEASE_INTERVAL` et d’ajouter des créneaux au
workflow ; le vrai frein n’est pas le prix, c’est la qualité : chaque guide doit passer la
relecture bloc par bloc, et un site qui publie trop vite des pages faibles en souffre.

## Le plan au 24 octobre 2026

Classé par continent, puis par score du jour (priorité + bonus de saison). Les six guides
marqués « publié » ont été écrits à la main le 24/10 ; la chaîne passe au suivant.

### Europe (31 sujets)

| Sujet | Type | Pays | Voyage en | Priorité | Score au 24/10 |
| --- | --- | --- | --- | ---: | ---: |
| `londres-noel-marches` (publié) | Que faire | royaume-uni | nov., déc. | 68 | 88 |
| `laponie-budget-rovaniemi` (publié) | Budget | finlande | jan., fév., mars, déc. | 55 | 85 |
| `amsterdam-3-jours` | Itinéraires | pays-bas | avr., mai, sept., déc. | 35 | 65 |
| `vienne-marches-de-noel` | Que faire | autriche | nov., déc. | 44 | 64 |
| `crete-itineraire-10-jours` | Itinéraires | grece | mai, juin, sept., oct. | 58 | 63 |
| `istanbul-3-jours` | Itinéraires | turquie | avr., mai, sept., oct., nov. | 48 | 53 |
| `norvege-fjords-train` | Itinéraires | norvege | juin, juil., août | 52 | 52 |
| `cyclades-ferry-itineraire` | Transports | grece | mai, juin, juil., août, sept., oct. | 44 | 49 |
| `cappadoce-montgolfiere` | Que faire | turquie | avr., mai, juin, sept., oct. | 41 | 46 |
| `croatie-itineraire-10-jours` | Itinéraires | croatie | mai, juin, sept., oct. | 40 | 45 |
| `islande-aurores-boreales` | Quand partir | islande | jan., fév., mars, sept., oct., nov., déc. | 40 | 45 |
| `lisbonne-miradouros` | Que faire | portugal | toute l’année | 39 | 44 |
| `malte-que-faire` | Que faire | malte | avr., mai, juin, sept., oct. | 38 | 43 |
| `porto-belvederes-gratuits` | Que faire | portugal | toute l’année | 36 | 41 |
| `albanie-road-trip` | Road trips | albanie | mai, juin, sept., oct. | 32 | 37 |
| `prague-3-jours` | Itinéraires | republique-tcheque | avr., mai, sept., oct., déc. | 31 | 36 |
| `budapest-3-jours` | Itinéraires | hongrie | avr., mai, sept., oct., déc. | 30 | 35 |
| `porto-caves-gaia-telepherique` | Visites | portugal | toute l’année | 27 | 32 |
| `porto-clerigos-lello` | Visites | portugal | toute l’année | 27 | 32 |
| `ecosse-road-trip-highlands` | Road trips | royaume-uni | mai, juin, juil., août, sept. | 31 | 31 |
| `belem-jeronimos-tram-15` | Visites | portugal | toute l’année | 26 | 31 |
| `lisbonne-chateau-sao-jorge` | Visites | portugal | toute l’année | 26 | 31 |
| `lisbonne-ferry-cacilhas` | Transports | portugal | toute l’année | 26 | 31 |
| `sintra-quinta-da-regaleira` | Visites | portugal | toute l’année | 26 | 31 |
| `irlande-road-trip-10-jours` | Road trips | irlande | mai, juin, juil., août, sept. | 30 | 30 |
| `islande-road-trip-10-jours` | Road trips | islande | juin, juil., août, sept. | 29 | 29 |
| `porto-foz-tram-1` | Excursions | portugal | avr., mai, juin, juil., août, sept. | 27 | 27 |
| `alhambra-reserver-billets` | Visites | espagne | mars, avr., mai, oct., nov. | 22 | 27 |
| `cordoue-mezquita-visite` | Visites | espagne | mars, avr., mai, oct., nov. | 22 | 27 |
| `seville-alcazar-cathedrale` | Visites | espagne | mars, avr., mai, oct., nov. | 22 | 27 |
| `aveiro-musee-art-nouveau` | Visites | portugal | avr., mai, juin, sept., oct. | 17 | 22 |

### Afrique (11 sujets)

| Sujet | Type | Pays | Voyage en | Priorité | Score au 24/10 |
| --- | --- | --- | --- | ---: | ---: |
| `marrakech-3-jours` | Itinéraires | maroc | mars, avr., mai, oct., nov., déc. | 64 | 69 |
| `reunion-itineraire-10-jours` | Itinéraires | reunion | mai, juin, juil., août, sept., oct., nov. | 60 | 65 |
| `egypte-croisiere-nil-louxor` | Itinéraires | egypte | jan., fév., mars, avr., oct., nov., déc. | 58 | 63 |
| `maroc-itineraire-10-jours` | Itinéraires | maroc | mars, avr., mai, oct., nov. | 58 | 63 |
| `zanzibar-quand-partir` | Quand partir | tanzanie | jan., fév., juin, juil., août, sept., oct., déc. | 50 | 55 |
| `seychelles-quand-partir` | Quand partir | seychelles | avr., mai, oct., nov. | 43 | 48 |
| `cap-vert-quand-partir` | Quand partir | cap-vert | toute l’année | 42 | 47 |
| `ile-maurice-quand-partir` | Quand partir | maurice | avr., mai, sept., oct., nov., déc. | 42 | 47 |
| `afrique-du-sud-itineraire-2-semaines` | Itinéraires | afrique-du-sud | jan., fév., mars, avr., oct., nov., déc. | 39 | 44 |
| `kenya-safari-budget` | Budget | kenya | jan., fév., juil., août, sept., oct. | 32 | 37 |
| `namibie-road-trip` | Road trips | namibie | mai, juin, juil., août, sept., oct. | 23 | 28 |

### Moyen-Orient (2 sujets)

| Sujet | Type | Pays | Voyage en | Priorité | Score au 24/10 |
| --- | --- | --- | --- | ---: | ---: |
| `dubai-que-faire-4-jours` | Que faire | emirats-arabes-unis | jan., fév., mars, nov., déc. | 44 | 64 |
| `petra-visite-jordan-pass` | Visites | jordanie | mars, avr., mai, oct., nov. | 25 | 30 |

### Asie (16 sujets)

| Sujet | Type | Pays | Voyage en | Priorité | Score au 24/10 |
| --- | --- | --- | --- | ---: | ---: |
| `thailande-itineraire-2-semaines` (publié) | Itinéraires | thailande | jan., fév., mars, nov., déc. | 89 | 109 |
| `japon-itineraire-2-semaines` (publié) | Itinéraires | japon | mars, avr., mai, oct., nov. | 92 | 97 |
| `sri-lanka-itineraire-2-semaines` | Itinéraires | sri-lanka | jan., fév., mars, avr., déc. | 58 | 88 |
| `vietnam-itineraire-15-jours` | Itinéraires | vietnam | fév., mars, avr., oct., nov., déc. | 76 | 81 |
| `thailande-quand-partir` | Quand partir | thailande | jan., fév., mars, nov., déc. | 60 | 80 |
| `vietnam-quand-partir` | Quand partir | vietnam | fév., mars, avr., oct., nov., déc. | 69 | 74 |
| `bangkok-ou-dormir-quartiers` | Où dormir | thailande | jan., fév., mars, nov., déc. | 54 | 74 |
| `malaisie-itineraire-2-semaines` | Itinéraires | malaisie | jan., fév., mars, avr., mai, juin, juil., août, déc. | 41 | 71 |
| `philippines-quand-partir` | Quand partir | philippines | jan., fév., mars, avr., mai, déc. | 38 | 68 |
| `japon-budget-2-semaines` | Budget | japon | toute l’année | 62 | 67 |
| `tokyo-ou-dormir-quartiers` | Où dormir | japon | mars, avr., mai, oct., nov. | 59 | 64 |
| `bali-quand-partir` | Quand partir | indonesie | avr., mai, juin, juil., août, sept., oct. | 54 | 59 |
| `kyoto-3-jours` | Itinéraires | japon | mars, avr., oct., nov. | 53 | 58 |
| `coree-du-sud-itineraire-10-jours` | Itinéraires | coree-du-sud | avr., mai, sept., oct., nov. | 46 | 51 |
| `angkor-visite-temples` | Visites | cambodge | jan., fév., mars, nov., déc. | 22 | 42 |
| `rajasthan-itineraire-10-jours` | Itinéraires | inde | jan., fév., mars, oct., nov., déc. | 24 | 29 |

### Amérique du Nord (7 sujets)

| Sujet | Type | Pays | Voyage en | Priorité | Score au 24/10 |
| --- | --- | --- | --- | ---: | ---: |
| `new-york-noel` (publié) | Que faire | etats-unis | nov., déc. | 78 | 98 |
| `yucatan-itineraire-10-jours` | Itinéraires | mexique | jan., fév., mars, avr., nov., déc. | 61 | 81 |
| `quebec-hiver` | Que faire | canada | jan., fév., déc. | 47 | 77 |
| `mexique-quand-partir` | Quand partir | mexique | jan., fév., mars, avr., nov., déc. | 50 | 70 |
| `new-york-ou-dormir` | Où dormir | etats-unis | toute l’année | 58 | 63 |
| `rocheuses-canadiennes-road-trip` | Road trips | canada | juin, juil., août, sept. | 45 | 45 |
| `ouest-americain-road-trip` | Road trips | etats-unis | avr., mai, juin, sept., oct. | 27 | 32 |

### Amérique centrale et Caraïbes (5 sujets)

| Sujet | Type | Pays | Voyage en | Priorité | Score au 24/10 |
| --- | --- | --- | --- | ---: | ---: |
| `costa-rica-itineraire-2-semaines` (publié) | Itinéraires | costa-rica | jan., fév., mars, avr., déc. | 72 | 102 |
| `guadeloupe-itineraire-10-jours` | Itinéraires | guadeloupe | jan., fév., mars, avr., mai, déc. | 55 | 85 |
| `martinique-quand-partir` | Quand partir | martinique | jan., fév., mars, avr., mai, déc. | 44 | 74 |
| `republique-dominicaine-quand-partir` | Quand partir | republique-dominicaine | jan., fév., mars, avr., déc. | 33 | 63 |
| `cuba-itineraire-2-semaines` | Itinéraires | cuba | jan., fév., mars, avr., nov., déc. | 25 | 45 |

### Amérique du Sud (2 sujets)

| Sujet | Type | Pays | Voyage en | Priorité | Score au 24/10 |
| --- | --- | --- | --- | ---: | ---: |
| `colombie-itineraire-2-semaines` | Itinéraires | colombie | jan., fév., mars, juil., août, déc. | 37 | 67 |
| `machu-picchu-billets-train` | Visites | perou | avr., mai, juin, juil., août, sept., oct. | 22 | 27 |

### Océanie (3 sujets)

| Sujet | Type | Pays | Voyage en | Priorité | Score au 24/10 |
| --- | --- | --- | --- | ---: | ---: |
| `nouvelle-zelande-road-trip-3-semaines` | Road trips | nouvelle-zelande | jan., fév., mars, déc. | 19 | 49 |
| `polynesie-budget` | Budget | polynesie-francaise | mai, juin, juil., août, sept., oct. | 34 | 39 |
| `australie-itineraire-3-semaines` | Itinéraires | australie | mars, avr., mai, sept., oct., nov. | 21 | 26 |

## Tenir le plan à jour

- **Ajouter un sujet** : une entrée dans `guide-topics.json` (schéma vérifié par
  `topic_plan.validate_topic` et `test_topic_plan.py`), avec le pays et le continent de
  `site-src/destinations.json`, 2 ou 3 sources lues par la chaîne et 3 photos au moins.
- **Remesurer la demande** chaque trimestre : refaire les trois mesures, recalculer les
  priorités. Les sujets suivent les saisons sans intervention grâce au bonus.
- Le catalogue s’épuise vers mars 2027 au rythme actuel ; le rapport hebdomadaire alerte quand
  aucun guide n’est prévu à 28 jours.

## Limites

- Les mesures donnent un **classement relatif**, pas des volumes de recherche : aucun outil
  payant (Ahrefs, Semrush) n’a servi.
- La portée est une estimation à la main, pas une analyse des pages concurrentes.
- Les sources peuvent changer entre la rédaction et la publication : la publication relit
  leur empreinte ; si le texte a bougé (Wikivoyage est souvent modifié) ou si la relecture a
  plus de 48 heures, le guide est retiré de la file sans être publié, le build continue, et
  la chaîne peut réécrire le sujet à partir des sources du jour.
