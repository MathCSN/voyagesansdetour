# Production des posts Voyage Sans Détour

Ce dossier fabrique les **reels Instagram** (MP4 1080 × 1920) et les **carrousels photo** (6 images 1080 × 1350, publiés sur Facebook) à partir de scénarios relus. Il ne publie rien : la file passe par `reviewed-social/` et le contrôleur de stock du cloud.

Depuis le 24/10/2026, le moteur ne produit plus qu’un seul format, celui de la charte de `CLAUDE.md` :

- **une vraie photo du lieu en plein cadre à chaque scène**, sous licence libre (CC BY, CC BY-SA, CC0, domaine public), auteur et licence consignés ;
- **une accroche** dès la première scène, visible dès la première image (vignette) ;
- **une info concrète et différente par scène** (prix, durée, ligne, horaire), citée **mot pour mot** depuis un instantané daté d’une page officielle ou d’un guide publié ;
- du texte lisible sur la photo (dégradé, voile sombre, chiffres en jaune), une musique entraînante sous CC BY 4.0, **aucune voix** ;
- une légende courte : accroche, 3 à 5 lignes utiles, appel à l’action, **une seule ligne de crédits** qui renvoie au `credits.txt` complet du post.

Le moteur refuse l’ancien format (aplats, schéma « 1-2-3 », voix de synthèse), une photo ou un titre répété dans un même post, une scène sans fait sourcé, un extrait absent de son instantané, une licence non libre et les formules creuses de l’ancienne ligne (« sans récit vécu », « si possible »…).

## Fichiers

| Fichier | Rôle |
|---|---|
| `production.py` | Valide un scénario (schéma 2), rend le reel ou le carrousel, écrit le reçu. Au plus un rendu par exécution. |
| `social_render.py` | Dessin : photo plein cadre avec lent mouvement de caméra, dégradé, texte, fondus. |
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

- Le contrôleur importe **un lot par passage** (lundi via `vsd-cloud-control`, lundi, mercredi et vendredi via `vsd-promote-media`), par ordre d’échéance.
- Le serveur limite par défaut Instagram à 1 post par 168 h ; les reels sont donc espacés d’une semaine.
- Le stock n’accepte aujourd’hui que les reels Instagram et les lots photos Facebook (2 à 10 images). Les carrousels Instagram demandent une extension de `stock-control.mjs` / `promotion-control.mjs`.
- L’inventaire du site publie exactement 6 images par carrousel (`site-src/public_media.py`).
- Prix Andante (Porto) : la page officielle affiche encore les tarifs 2023 alors que la presse annonce une hausse en 2026 ; aucun prix Andante n’est cité tant qu’une source officielle à jour manque.

## Exécuter

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest -q test_production
python3 production.py --validate
python3 production.py
```

FFmpeg et FFprobe (libx264, AAC) doivent être dans le PATH. Les anciens rendus de `output/` (porto-aeroport, lisbonne-quartiers, sintra-pena) sont conservés comme historique et ne sont plus au catalogue.
