# Production des médias Voyage Sans Détour

Ce paquet fabrique un **nouveau MP4 à partir d’un scénario contrôlé**. Il fonctionne avec des fichiers portables, Pillow et FFmpeg, sans compte de génération, API, navigateur ou clé. Il ne recherche pas de nouvelles informations et ne publie rien sur les réseaux.

Premier scénario : **Porto — trois réflexes avant de quitter l’aéroport**. Six scènes originales, 28 secondes, 1080 × 1920, 30 images/s, H.264 et AAC 48 kHz. Musique instrumentale, schémas animés, aucune voix ni Alma. Ce scénario est distinct des deux Reels Lisbonne déjà préparés.

## Exécuter

Depuis le dossier du paquet :

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest -q test_production
python3 production.py --validate
python3 production.py
```

Python 3.12 est choisi pour le cloud ; le moteur fonctionne aussi avec Python 3.9 local. Pillow est fixé à 11.3.0. FFmpeg et FFprobe doivent être disponibles dans le PATH, avec libx264 et AAC. Le workflow utilise les binaires du runner Ubuntu 24.04 et consigne leur version réelle ; il ne prétend pas figer l’image GitHub. Le rendu local de qualification conserve ses versions propres dans `receipt.json`.

Le résultat est écrit dans `output/<identifiant>/` : `reel.mp4`, six scènes JPEG, affiche, planche, légende complète, licences et reçu. Une relance identique vérifie les empreintes puis reste inactive. Le remplacement d’un scénario sous un identifiant déjà produit ou l’altération d’un rendu provoque un arrêt. Le dossier temporaire est déplacé seulement après encodage et décodage complet réussis. Les résultats terminés ne sont jamais écrasés.

## Les scénarios et leurs sources

`catalogue.json` référence des scénarios par identité stable, date minimale et SHA-256. Chaque scénario porte les textes, scènes, durée, thème, URL cible, sources, extraits justificatifs, date de contrôle, échéance, fichiers de police et musique avec empreintes/licences. Le code ne contient aucun scénario Lisbonne ni appel de voix. Les formats actuels sont musique/texte et texte muet ; la génération ou la rotation de voix n’est pas installée dans ce moteur.

Le premier scénario reprend le **guide Porto publié et contrôlé le 27 septembre 2026**, dont l’instantané et la preuve historique de publication sont inclus. La dérivation a été relue à partir de cet instantané ; le rendu n’effectue pas de nouvelle recherche. Les extraits de preuve doivent correspondre exactement au guide. Une réponse HTTP ancienne n’est pas présentée comme un contrôle actuel. La date limite est le **27 octobre 2026 à 00:00 UTC** ; le travail s’arrête après expiration. Aucun horaire, prix, accessibilité individuelle ou durée de transfert n’est garanti.

La musique **Almost Bliss — Kevin MacLeod** provient du téléchargement officiel déjà vérifié sous CC BY 4.0. Le fichier source et sa preuve sont inclus. La légende générée garde le titre, l’auteur, les liens de source et de licence, ainsi que l’extrait, les fondus, l’ajustement du niveau et la synchronisation. DM Sans et Playfair Display sont accompagnées des avis SIL OFL 1.1. Les diagrammes sont des compositions originales de préparation, pas des plans d’opérateur.

## Qualification GitHub Actions

`cloud/vsd-render-content.yml` est un workflow prêt à installer, **pas la preuve d’une exécution distante**. Le paquet public place le moteur dans `.github/vsd-production/` et ce YAML dans `.github/workflows/`. Aucun rendu local n’est inclus dans le paquet d’installation : un premier lancement manuel doit réellement encoder la vidéo dans le cloud.

Le workflow n’accepte que `MathCSN/voyagesansdetour`, la branche `main`, un dépôt public et le runner standard `ubuntu-24.04`. Il a un plafond de dix minutes, deux threads d’encodage, au plus un clip par lancement et aucun secret/provider externe. Les sorties terminées sont ajoutées dans `.github/vsd-production/output/` avec leur reçu, conservé entre les exécutions et protégé des exports du blog ; un refus de push reste un échec visible. Il ne remplace pas le pipeline du blog ni le registre D1.

La cadence future est le lundi à 05:17 UTC mais reste inactive tant que la variable de dépôt `VSD_FREE_RENDER_SCHEDULE` n’est pas exactement `true`. L’activation vient après lecture du vrai premier reçu distant. Tous les déclenchements restent bornés au 14 septembre 2027. Un dépôt privé n’est pas utilisé comme repli payant. Les retards et limites GitHub restent applicables.

## Ce qui reste à raccorder

- Rechercher, rédiger et recontrôler régulièrement de nouveaux scénarios ; un scénario préparé ne remplit pas une année de stock.
- Constater un premier succès réel GitHub puis qualifier la cadence et les ressources.
- Héberger les MP4 à une URL admissible, contrôler le résultat et la légende, puis créer le lot signé pour le registre de publication. Le reçu est expressément `rendered_not_published`, avec `readyForAutomaticImport: false`.
- Relier ce stock au moteur social sans renvoyer d’anciens contenus, avec les validations de chaque réseau et les plafonds gratuits existants.

La sélection et les scènes sont déterministes. Des versions différentes de FFmpeg ou Pillow peuvent encoder des octets différents : chaque résultat possède donc sa propre empreinte et le logiciel réellement utilisé, sans promesse trompeuse de MP4 identique sur tous les systèmes.
