# Production des posts Voyage Sans Détour

Ce dossier fabrique les **reels Instagram** (MP4 1080 × 1920) et les **carrousels photo** (6 images 1080 × 1350, publiés sur Facebook) à partir de scénarios relus. Il ne publie rien : la file passe par `reviewed-social/` et le contrôleur de stock du cloud.

Depuis le 24/10/2026, le moteur ne produit plus qu’un seul format, celui de la charte de `CLAUDE.md` :

- **une vraie photo du lieu en plein cadre à chaque scène**, sous licence libre (CC BY, CC BY-SA, CC0, domaine public), auteur et licence consignés ;
- **une accroche** dès la première scène, visible dès la première image (vignette) ;
- **une info concrète et différente par scène** (prix, durée, ligne, horaire), citée **mot pour mot** depuis un instantané daté d’une page officielle ou d’un guide publié ;
- du texte lisible sur la photo (dégradé, voile sombre, chiffres en jaune), une musique entraînante sous CC BY 4.0, **aucune voix** ;
- une légende courte : accroche, 3 à 5 lignes utiles, appel à l’action, **une seule ligne de crédits** qui renvoie au `credits.txt` complet du post.

Le moteur refuse l’ancien format (aplats, schéma « 1-2-3 », voix de synthèse), une photo ou un titre répété dans un même post, une scène sans fait sourcé, un extrait absent de son instantané, une licence non libre et les formules creuses de l’ancienne ligne (« sans récit vécu », « si possible »…).

## Posts automatiques

Chaque guide publié, de n'importe quel pays, produit seul ses posts. Chaque jour, `vsd-render-content.yml` lance `auto_social.py`, qui remplit **tous les créneaux libres des trois prochaines semaines**. La stratégie, les exemples étudiés et les raisons de chaque choix sont dans `docs/strategie-videos.md`.

- **Créneaux** : `cadence.json`, en heure de Paris. Instagram : reels le mardi à 19 h et le dimanche à 21 h ; Facebook : lots photos le jeudi et le dimanche à 18 h. `weeklyLimit` suit le plafond du panneau `vsd-admin` (2 posts par réseau sur 7 jours) ; les créneaux marqués `"enabled": false` sont la cadence cible (carrousel Instagram le jeudi, troisième reel le vendredi), à activer une fois ce plafond relevé. Un créneau libre entre deux posts déjà en file est comblé ; aucun post à moins de 40 h d'un autre sur Instagram.
- **Reels rapides (schéma 3)** : `reel_formats.py` choisit le format selon le guide : `prix` (budget : le prix dans l'accroche), `itineraire` (une étape datée par plan, seulement sur une photo de ce lieu), `tableau` (un tableau court du guide, entier, à mettre en pause), `liste` (cinq chiffres numérotés). Un reel dit au moins quatre choses différentes (il lui faut six photos ou plans) ; un chiffre qui répète le titre est écarté ; le prix n'ouvre le reel que s'il est le budget du voyage. Le format `express` (deux chiffres) n'est plus produit depuis le 12/11/2026. Un guide revient au bout de six semaines dans un format qu'il n'a pas encore eu. `motion_render.py` dessine : accroche encadrée dès la première image, plans de 2,4 à 4 s, chiffre seul puis explication, texte lisible sans le son, 9 à 25 s au total.
- **Choix du guide** : d'abord les guides jamais publiés sur aucun réseau (le plus récent d'abord), puis ceux jamais publiés sous cette forme sur ce réseau, puis la reprise au bout de 6 semaines. Un guide dont les sources ont plus de 45 jours attend sa mise à jour.
- **Faits** : la page publiée du guide est relevée (`auto/<id>/guide.txt`, première ligne = URL). Chiffres du bloc « L'essentiel en chiffres », titres de sections datées et lignes de tableau sont cités mot pour mot ; un libellé long est coupé à sa première pause naturelle, jamais réécrit. Le moteur refuse tout texte surligné qui n'est pas dans l'extrait du plan.
- **Photos** : celles du guide (`site-src/image-sources.json`), puis les autres photos du site pour le même lieu, puis celles ajoutées et regardées à la main (`photo_intake.py <identifiant> "File:…"` les range dans `assets/photos/reviewed.json` ; même préfixe que les photos du guide : `laponie-…` ; l'ancien `catalogue.json`, scellé par les scénarios écrits à la main, ne se modifie plus), puis au besoin des « Featured pictures » de Wikimedia Commons (`media_library.py`). La recherche ne prend que le nom du lieu et ses noms relus à la main (`destinations.EXONYMS`), exigés en mot entier dans le titre du fichier ; le pays seulement pour un guide de tout le pays ; jamais un mot tiré du titre d'une autre photo. Licences libres seulement, **jamais d'image générée par IA**, et seulement des photographies : illustration, affiche, publicité, œuvre reproduite ou antérieure à 1950 refusées, appareil photo exigé dans les données d'une image trouvée par la recherche. La photo de couverture du guide ouvre le reel (ou sa première photo quand la couverture est trop petite).
- **Retirer un post en file** : ajouter son lot (et sa copie TikTok) à `retirements` de `reviewed-social/index.json`. Le panneau ne l'enverra plus, et le générateur rend son créneau et son guide : le nouveau post prend l'identité suivie de `-2`. Rien n'est récrit.
- **Vrais plans vidéo** : `clip_intake.py` (Pexels si le secret `PEXELS_API_KEY` existe ; Wikimedia Commons éteint par défaut ; Pixabay écarté). Licence, auteur et page source consignés dans `auto/<id>/clips.json`, toute marque d'IA refusée, jamais en accroche ni en dernière image.
- **Texte** : aucune case vide à l'écran : ce que DM Sans ne sait pas dessiner (₫, lettres vietnamiennes) passe en Noto Sans ; un caractère inconnu des deux polices écarte le chiffre. Légende : titre du guide, 3 à 5 lignes utiles, « Enregistrez… lien dans la bio », une ligne de crédits, 5 hashtags au plus.
- **Garde-fous** : le scénario est figé avec ses propres entrées (`auto/<id>/`), puis passé aux contrôles de `production.py` (sources, licences, empreintes, mise en page) **avant** d'entrer au catalogue. Un refus est noté dans le résumé du workflow, le format ou le guide suivant est essayé. Rien d'existant n'est réécrit.

Le même workflow rend ensuite jusqu'à six posts, les met en file (`social_stock.py`) et relance le site. Un lot Instagram de six photos part en `carousel`, un lot Facebook en `photos`. Chaque reel rapide Instagram peut partir aussi sur TikTok : un second lot `<id>-tiktok-v1`, la même vidéo une heure plus tard, la même légende sauf l'appel à l'action (le site est nommé, sans « lien dans la bio »), 2 200 signes et 5 hashtags au plus. Un réseau allumé après coup reçoit aussi les reels déjà en file dont le créneau est à plus de 24 heures. Éteint (`"crossposts"` dans `cadence.json`) jusqu'au déploiement du panneau qui accepte TikTok : voir `docs/strategie-videos.md`, « TikTok : ce qui est branché ». YouTube Shorts et les Reels Facebook restent éteints : le panneau ne les accepte pas.

**Pinterest** : `pin_intake.py` dessine jusqu'à quatre brouillons par passage, trois épingles par guide (`pin_draft.py` : couverture et premier chiffre ; autre photo et trois chiffres ; troisième photo et titre de recherche). `pin_promotion.py` en admet une par jour au plus, une par tableau tous les trois jours, deux épingles d'un même guide à 14 jours d'écart, avec un titre de 100 caractères au plus et une description tirée de la présentation du guide. Les tableaux sont déclarés dans `site-src/pinterest-additions.json` (`countries`) ; un pays sans tableau part dans `inspirations-voyage.xml`.

## Fichiers

| Fichier | Rôle |
|---|---|
| `production.py` | Valide un scénario (schéma 2), rend le reel ou le carrousel, écrit le reçu. Au plus un rendu par exécution. |
| `social_render.py` | Dessin des carrousels et des reels historiques (schéma 2) : photo plein cadre, dégradé, texte. |
| `motion_render.py` | Dessin des reels rapides (schéma 3) : accroche encadrée, plans courts, tableau, clips, police de repli. |
| `reel_formats.py` | Choix du format d'un reel selon le guide et construction de ses plans. |
| `media_library.py` | Photos et clips d'un lieu, téléchargés une fois et réutilisés. |
| `clip_intake.py` | Plans vidéo libres (Pexels, Wikimedia Commons) : licence, auteur, extrait de 4 s, IA refusée. |
| `cadence.json` | Créneaux par réseau en heure de Paris, limite hebdomadaire, sources de clips, cross-posts. |
| `auto_social.py` | Fabrique les scénarios des prochains créneaux libres à partir des guides publiés, les fige et les valide avant de les mettre au catalogue. |
| `destinations.py` | Noms, prépositions et hashtags des pays, lus dans `site-src/destinations.json` avec un repli. |
| `photo_intake.py` | Ajoute une photo Wikimedia Commons au catalogue `assets/photos/catalogue.json` (licence vérifiée, auteur, empreinte). |
| `seal_scenarios.py` | Remplit les empreintes d’un scénario et reconstruit `catalogue.json`. |
| `social_stock.py` | Publie les fichiers rendus dans `site-src/social-media/production/`, les déclare dans `site-src/public-media.json`, écrit le lot relu et son entrée d’index. `--verify-public` contrôle les octets en ligne après déploiement. |
| `sources/<date>/` | Instantanés texte des pages officielles (1re ligne = URL) et registre `sources.json` daté. |

## Ajouter un post

1. Relever les pages officielles utiles dans un nouveau dossier `sources/social-AAAA-MM-JJ/` (texte visible, URL en première ligne) et son `sources.json`. Une source vaut 30 jours.
2. Ajouter les photos : `python3 photo_intake.py <id> "File:Titre sur Commons.jpg"`. Vérifier l’auteur (le champ Commons « Artist » nomme parfois l’architecte du monument).
3. Écrire `scenarios/<id>.json` (schéma 2 : `kind` reel ou carousel, `publishAt`, `caption`, `scenes` avec `photo`, `headline` — les chiffres entre `*astérisques*` passent en jaune —, `detail`, `tag`, `facts` [{`source`, `excerpt`}]). Laisser les `sha256` vides.
4. `python3 seal_scenarios.py`, puis `python3 production.py --validate`, puis `python3 production.py` (une fois par post).
5. Regarder `output/<id>/apercu.jpg` (planche contact) : chaque image doit donner envie.
6. `python3 social_stock.py` : médias publics, lot relu et index. Après fusion et déploiement : `python3 social_stock.py --verify-public`.

Le workflow `vsd-render-content.yml` enchaîne les étapes 4 et 6 dans GitHub Actions et relance la construction du site quand de nouveaux médias sont en file.

## Rythme et limites

- Le panneau `vsd-admin` importe chaque jour (08:53 UTC, `vsd-cloud-control`) les lots encore programmables et les envoie à Buffer trois jours avant leur échéance.
- Le panneau `vsd-admin` limite chaque réseau à 2 posts sur 7 jours glissants ; `cadence.json` s’y tient.
- Le panneau accepte les reels et carrousels Instagram et les lots photos Facebook (2 à 10 images).
- L’inventaire du site publie exactement 6 images par carrousel (`site-src/public_media.py`).
- Prix Andante (Porto) : la page officielle affiche encore les tarifs 2023 alors que la presse annonce une hausse en 2026 ; aucun prix Andante n’est cité tant qu’une source officielle à jour manque.

## Exécuter

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest -q test_production test_auto_social test_pin_draft test_pin_intake test_pin_promotion test_reel_intake
python3 production.py --validate
python3 production.py
```

FFmpeg et FFprobe (libx264, AAC) doivent être dans le PATH. Les anciens rendus de `output/` (porto-aeroport, lisbonne-quartiers, sintra-pena) sont conservés comme historique et ne sont plus au catalogue.
