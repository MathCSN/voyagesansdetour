# La chaîne autonome de Voyage Sans Détour

État constaté le 24 octobre 2026. Une page pour savoir ce qui publie quoi, où, et quand.

## Les comptes réels

| Réseau | Compte | Comment les posts y arrivent |
| --- | --- | --- |
| Instagram | **@voyagesansdetour.fr** (pas @voyagesansdetour, qui est un autre compte, vide) | Buffer, envoyé par le panneau privé |
| Facebook | Page « Voyagesansdetour » | Buffer, envoyé par le panneau privé |
| Pinterest | fr.pinterest.com/voyagesansdetour | Import RSS natif de Pinterest depuis `voyagesansdetour.fr/pinterest/*.xml` |
| Site | voyagesansdetour.fr | GitHub Pages, construit depuis `site-src/` |

Publié à ce jour : 4 reels Instagram (27/09, 04/10, 11/10, 18/10, un par dimanche),
2 carrousels Facebook (27/09, 12/10), 5 épingles (29/09, 01/10, 12/10 en double, 18/10), 8 guides.

Les trois posts ancien format déjà importés (Facebook Sintra 25/10, reel bagages 25/10,
reel Porto 01/11) ne partiront pas : leurs médias ont été retirés du site le 24/10, donc Buffer
ne peut plus les récupérer. **Après eux, la file sociale est vide** jusqu'aux premiers lots du nouveau format.

## Le trajet d'un post

```
guide publié ──► rendu (production.py, reel_intake.py)
              ──► lot relu dans .github/vsd-production/reviewed-social/ + index.json
              ──► import chaque heure par le panneau privé vsd-admin (sa tâche planifiée, à :22)
              ──► registre D1 du panneau ──► Buffer 3 jours avant l'échéance ──► Instagram / Facebook / TikTok
```

- **Panneau privé** `vsd-admin` (https://vsd-admin.kartier.workers.dev, accès par clé d'accès) :
  Cloudflare Worker + base D1, code dans le dépôt privé `MathCSN/vsd-admin`, modifié et déployé par Claude
  seul. Il tient le registre, la clé Buffer (chiffrée) et les règles : programmation dans Buffer 3 jours
  avant l'échéance, **plafond par réseau sur 7 jours (Instagram 4, Facebook 2, TikTok 4)**, contrôle
  anti-doublon sur ce que Buffer a déjà, formats `instagram/reel`, `instagram/carousel`, `facebook/photos`
  et `tiktok/reel` (depuis le 11/11/2026). Les canaux Buffer sont relus à chaque passage : un canal
  déconnecté, verrouillé ou en pause fait attendre ses seuls posts. Bascule depuis l'ancien
  serveur ChatGPT Sites le 11/11/2026 (`docs/migration-panneau.md`) ; l'ancien n'est plus appelé.
- **Retirer un lot** : l'ajouter à `retirements` de `index.json`. Au passage `stock` suivant, ses posts
  pas encore envoyés passent « en attente » dans le registre et ne partent plus. Un post déjà programmé
  dans Buffer se supprime dans Buffer. Les anciens garde-fous du dépôt n'admettent qu'un motif de
  retrait, `duplicate_media_on_channel`.
- **Qui déclenche le moteur** (depuis le 11/11/2026) : le panneau lui-même, par la tâche planifiée du
  Worker (vsd-admin PR 4). À :22 il importe les lots relus encore programmables ; à :37 et :52 il
  programme les posts dus dans Buffer ; à :07 il relève les statistiques. Les passages planifiés de GitHub sont trop rares
  pour porter la publication (une demi-douzaine par jour au lieu de 48, et le passage `stock` de 08:53
  presque jamais) : `vsd-cloud-control.yml` reste un déclencheur de secours, et le verrou du moteur
  empêche deux passages simultanés.
- **Import économe** : un Worker gratuit plafonne à 50 sous-requêtes par passage. L'import ne relit pas un
  lot dont tous les posts sont au registre, ni un lot échu déjà connu du relevé ; il lit au plus 10
  fichiers par passage, les plus récents d'abord, et reporte le reste au suivant.
- **Lot refusé** : un lot que le panneau refuse et qui pourrait encore partir fait répondre « attention »
  au passage `stock` (le workflow sort alors en erreur). Un lot refusé dont l'échéance est passée est
  ignoré : c'est le cas du lot Facebook Porto du 12/10/2026, publié par l'ancien moteur avec une
  relecture incomplète.
- Format d'un lot : un item `{contentId, deduplicationKey, title, dueAt, payload, review}` ;
  `payload` = `{schemaVersion, channel, kind, text, aiGenerated, assets[{url, sha256, mimeType}]}` ;
  la relecture doit couvrir l'échéance (`review.validUntil > dueAt`).

## Le trajet d'une épingle

`vsd-render-content.yml` (lundi 05:17 UTC) : `pin_intake.py` dessine un brouillon par guide,
`pin_promotion.py` en admet **un par semaine** dans `site-src/pinterest-additions.json`,
puis le site est redéployé et Pinterest importe le flux RSS tout seul.
Un brouillon devenu périmé (guide mis à jour ou gabarit changé) est redessiné, il ne bloque plus la chaîne.
Le lien de l'épingle suit le pays du guide (`/portugal/`, `/espagne/`, `/italie/`). Seul le tableau
« Préparer son voyage au Portugal » a un flux branché (`COUNTRY_FEEDS` dans `pin_promotion.py`) :
les épingles Espagne et Italie attendent leur tableau. Un guide dont la page est indisponible ou
qui ne se dessine pas est mis en attente (`held`) sans bloquer les suivants.

## Le trajet d'un guide

`vsd-writing-guide.yml` (chaque jour à 06:23 et 15:23 UTC) choisit le sujet le mieux classé du plan
(`guide-topics.json`, voir `docs/strategie-sujets.md`), trouve ses photos libres sur Wikimedia Commons,
lit ses sources, rédige, relit bloc par bloc et met le guide en file avec ses photos et ses preuves,
au plus un guide tous les deux jours. `vsd-writing-discovery.yml` (chaque jour) cherche des mises à
jour sourcées des guides publiés. Les guides et mises à jour programmés vivent dans
`site-src/editorial-queue.json` et `site-src/editorial-candidates/` ; `build-pages.yml`
(chaque jour 07:41 UTC) publie ceux dont l'heure est venue.

**Calendrier.** Un nouveau guide sort au plus tôt deux jours (calendrier de Paris) après la
dernière publication, quelle qu'en soit l'origine (chaîne, routine cloud ou promotion). Il peut
être rédigé la veille de son créneau. `calendar_full` est donc normal le jour d'une
publication et le lendemain matin ; il ne signifie jamais que la file est pleine. La chaîne
dépense alors zéro photo, zéro source et zéro neurone. Un guide déjà réservé dans la file ou une
promotion sans reçu de déploiement bloque aussi le calendrier.

**Métadonnées.** Le rédacteur mettait un paragraphe entier dans `summary` (800 à 1 000
caractères pour 360). Du 24/10 au 06/11, 22 passages sur 26 ont été jetés pour cette seule
raison, après 700 à 1 000 neurones dépensés. Désormais, le JSON demandé commence par les
sections et finit par les métadonnées, écrites comme un résumé du guide déjà rédigé ; la consigne
demande un résumé de deux phrases (200 à 320 caractères) et 2 à 4 paragraphes par section. Puis,
avant tout contrôle, un champ trop long garde ses premières phrases entières (un titre garde sa
partie avant « : »), sans un mot réécrit ni ajouté. S'il reste trop long (une seule phrase), un
appel court le condense (environ 50 neurones, une seule fois) ; si cette réécriture manque sa
limite, la phrase du rédacteur est coupée à une virgule ou à un mot et finit par « … ». La
reprise unique du rédacteur (corps trop court ou trop long, ou section qui ne cite aucun fait
nouveau) reçoit le brouillon brut, avec son long résumé à reporter dans les sections ; le
résultat repasse tous les contrôles et les relectures. Un fait
que le guide ne cite nulle part sort du dossier de preuves au lieu de faire jeter le guide,
pourvu qu'il en reste au moins 5. Les relectures lisent toujours le texte final.

**Sujets.** Un sujet dont toutes les sources sont des wikis (Wikivoyage, Wikipédia) passe
après ceux qui ont une page officielle ou d'opérateur : un wiki ne fournit jamais de prix, et
ces sujets donnaient des guides trop courts ou complétés de détails inventés, que la relecture
refusait (essais du 06/11 sur la Guadeloupe). Ajouter une source officielle à un tel sujet le
remet à son rang. Le rédacteur Qwen (`writer=qwen`) n'est pas une issue : à l'essai, il
inventait lignes de bus, prix et quartiers absents des faits.

**Photos.** Jamais d'image générée par IA. Chaque photo est un fichier de Wikimedia Commons,
vérifié sur Commons même : licence CC BY, CC BY-SA ou CC0, auteur, page `File:`, données EXIF
d'un appareil photo (marque ou modèle), et aucune marque IA dans le titre, la description, le
crédit, l'auteur ou les catégories (« AI-generated », Midjourney, DALL·E, Stable Diffusion…).
La chaîne cherche d'abord dans les images de qualité de Commons, puis dans tout Commons, puis
avec **Openverse** (`api.openverse.org`, sans clé, licences `by`, `by-sa` et `cc0`, source
`wikimedia`). Openverse remplace seulement le moteur de recherche de Commons, le plus
rationné, et trouve d'autres fichiers ; chaque fichier qu'il propose repasse ensuite par les
mêmes contrôles sur Commons. Openverse sert aussi des photos Flickr, mais elles restent
écartées : leurs fichiers n'ont pas d'EXIF, et le site attribue chaque crédit à « Wikimedia
Commons » (`generate.py`, `test_site.py`). Quand Commons ou Openverse répond 429 (ou 503),
la requête attend le délai `Retry-After` (300 s au plus), sinon 10, 30 puis 90 s, dans un
budget de 10 minutes d'attente par passage. Le détail de chaque recherche (origine, erreur,
fichier retenu, secondes d'attente) est écrit dans `guide-photo-search.json`, dans l'artefact du
passage.

**Cadence et quota.** Workers AI gratuit : 10 000 neurones par jour (remise à zéro à minuit
UTC). Un guide coûte environ 2 000 à 4 000 neurones (extraction, vérification des citations,
rédaction, relecture globale, relecture bloc par bloc, réécriture éventuelle), et un passage est
plafonné à 4 800. Deux passages par jour plus la découverte des mises à jour tiennent dans le
gratuit, ce qui permet un guide tous les deux jours (3 à 4 par semaine avec les routines du lundi
et du jeudi). Un rythme plus élevé demande d'abord de réduire `RELEASE_INTERVAL`
(`site-src/editorial_queue.py`) et un troisième passage quotidien ; au-delà du gratuit, Workers
Paid (5 $ par mois) facture 0,011 $ les 1 000 neurones, soit environ 0,04 $ par guide.

**Essai sur une branche.** `gh workflow run vsd-writing-guide.yml --ref <branche>` fait tout le
trajet, admission comprise, dans le seul runner, sans rien pousser. La file obtenue et la liste
des fichiers changés sont dans l'artefact `new-guide-proposal`.

## Les workflows

| Workflow | Quand | Rôle |
| --- | --- | --- |
| `build-pages.yml` | push sur main, chaque jour 07:41 | Construit et déploie le site, publie les guides dus |
| `vsd-cloud-control.yml` | toutes les 30 min ; stock 08:53 chaque jour (GitHub n'en lance qu'une partie) | Déclencheur de secours du panneau `vsd-admin`, qui importe et programme de lui-même depuis le 11/11/2026 : appels signés `publications` et `stock` |
| `vsd-render-content.yml` | lundi 05:17 | Rend les reels, brouillons et admission d'épingles |
| `vsd-reel-intake.yml` | après chaque déploiement | Prépare un storyboard de reel depuis un nouveau guide |
| `vsd-voice-production.yml` → `vsd-voice-adopt.yml` → `vsd-voice-review.yml` → `vsd-voice-promote.yml` | à la main seulement | Chaîne des reels voix de synthèse, en sommeil depuis le 24/10 (ancien format retiré) |
| `vsd-promote-media.yml` | à la main seulement | Ancienne promotion des rendus relus, en sommeil depuis le 06/11 : les nouveaux posts passent par `vsd-render-content` et l'import quotidien de `vsd-cloud-control` |
| `vsd-writing-discovery.yml` | chaque jour 09:37 | Mises à jour sourcées des guides ; une source injoignable est ignorée et notée, le passage continue |
| `vsd-weekly-report.yml` | chaque jour 09:07 (rapport le lundi) | Rapport hebdomadaire et alerte de file vide |

`vsd-writing-guide` tourne seul deux fois par jour (rédaction des nouveaux guides).
Lancés à la main seulement, pour qualifier un modèle : `vsd-writing-draft`, `-entailment`,
`-evaluation`, `-guide-review`, `-guide-revision`, `-probe`. Ils ne tournent jamais seuls.
`vsd-voice-pilot.yml` (qualification ponctuelle des voix, terminée le 12/10) a été supprimé.

Secrets : `VSD_ADMIN_TICK_KEY` (appels signés du panneau privé), `CLOUDFLARE_WORKERS_AI_TOKEN`
(rédaction). Variables : `VSD_FREE_PROMOTION_SCHEDULE` et `VSD_FREE_RENDER_SCHEDULE` à `true`.

## Surveillance

- **Rapport hebdomadaire** : chaque lundi, une issue `rapport-hebdo` dans le dépôt
  (publié cette semaine, file à venir, échecs de workflows, alertes, ce qui attend Mathis).
  La précédente est fermée automatiquement.
- **Alerte** : chaque jour, une issue `alerte-file` s'ouvre (ou se met à jour) si
  Instagram ou Facebook n'a plus de post programmé à 14 jours, si aucun nouveau guide n'est prévu
  à 28 jours, si un workflow échoue deux fois dans la semaine, ou à 60 jours de la date d'arrêt.
  Elle se ferme seule quand tout est revenu dans l'ordre.
- **Référencement** (`docs/seo.md`) : le rapport du lundi donne les clics et impressions Google sur
  28 jours, les requêtes en hausse et les pages indexées, lus dans le panneau privé par un appel
  signé en lecture seule. L'alerte se lève aussi si l'indexation recule sur 7 jours ou si les
  impressions sont divisées par deux. Après chaque déploiement, `indexnow.py` prévient Bing et
  Yandex des pages changées.
- Limite : la preuve de publication Instagram/Facebook n'est pas lisible depuis GitHub
  (pas d'API publique). Le rapport liste les posts dont l'échéance est passée ; la preuve
  est dans le panneau privé et sur les profils.
- La liste « ce qui attend Mathis » se tient à jour dans `.github/vsd-control/attente-mathis.json`.

## Date d'arrêt

Toute la chaîne s'arrête d'elle-même le **14 septembre 2027** (constante `STOP` ou `END`
dans `invoke-admin.mjs`, `stock-control.mjs`, `pin_intake.py` et plusieurs workflows).
Le rapport alerte 60 jours avant ; il faudra alors repousser ces dates.
