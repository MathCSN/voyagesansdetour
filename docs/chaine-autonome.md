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
- **Changer un créneau** (`cadence.json`) : le plafond du panneau compte sur 7 jours exacts, en heure
  de Paris, et le même créneau de la semaine précédente en sort tout juste. La grille remplit ce
  plafond (Instagram 4 créneaux pour 4, Facebook 2 pour 2) : **avancer un créneau, même d'une heure,
  fait donc retenir le premier post de la nouvelle grille**, placé moins de 7 jours après l'ancien
  créneau. Sauter cette première occurrence, ou garder sept jours pleins entre le dernier post de
  l'ancien créneau et le premier du nouveau. Reculer un créneau d'une heure ne retient rien (rejeu
  du 12/11/2026 sur le moteur du panneau). Un post retenu de cette façon sort dans l'alerte
  « Posts bloqués ».
- **Retirer un lot** : l'ajouter à `retirements` de `index.json`. Au passage `stock` suivant, ses posts
  pas encore envoyés passent « en attente » dans le registre et ne partent plus. Un post déjà programmé
  dans Buffer se supprime dans Buffer. Le panneau ne lit que `batchId` ; l'entrée garde aussi les
  empreintes du lot, la date, le motif (`photos_of_another_place`, `too_little_content`,
  `duplicate_media_on_channel`, `figure_no_longer_in_guide`) et, s'il est refait, `replacedBy`. Retirer aussi la copie TikTok
  (`…-tiktok-v1`). Le générateur rend alors le créneau et le guide : le post refait prend
  l'identité suivie de `-2`. Les anciens garde-fous endormis du dépôt ne connaissent que le motif
  `duplicate_media_on_channel` : leurs jeux d'essai écartent les autres.
- **Un guide corrigé retire ses posts en file** (depuis le 12/11/2026) : `vsd-render-content.yml`
  lance `stale_lots.py --retire` avant de planifier. Chaque lot à venir est relu contre la page de son
  guide publiée ce jour-là ; celui qui cite un chiffre que la page ne donne plus est retiré tout seul,
  avec ses copies, et le générateur rend son créneau dans le même passage. Le résumé du passage liste
  les lots retirés, ceux qui restent à traiter à la main (créneau à moins de 84 heures : le post est
  peut-être déjà dans Buffer, où il faut le supprimer ; avertissement « Post en file périmé non
  retiré ») et les citations seulement reformulées. Le 12/11/2026 la relecture a retiré quatre lots
  (Yucatán et sa copie TikTok, Marrakech, Thaïlande) après la revérification de cinq guides.
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

**Les nouveaux guides viennent des routines cloud** (rédaction le lundi et le jeudi à 9 h, veille le
lundi ; règles dans `bureau/blog/regles.md` de la holding). Le rédacteur GitHub décrit ci-dessous est
**en sommeil depuis le 12/11/2026** : en 51 passages planifiés il n'a jamais fait passer un guide à sa
propre relecture. Il se lance encore à la main.

`vsd-writing-guide.yml` (à la main seulement depuis le 12/11/2026) choisit le sujet le mieux classé du plan
(`guide-topics.json`, voir `docs/strategie-sujets.md`), trouve ses photos libres sur Wikimedia Commons,
lit ses sources, rédige, relit bloc par bloc et met le guide en file avec ses photos et ses preuves,
au plus un guide tous les deux jours. `vsd-writing-discovery.yml` (chaque jour) cherche des mises à
jour sourcées des guides publiés. Les guides et mises à jour programmés vivent dans
`site-src/editorial-queue.json` et `site-src/editorial-candidates/` ; `build-pages.yml`
(chaque jour 07:41 UTC) publie ceux dont l'heure est venue.

**État réel au 12/11/2026.** Ce rédacteur automatique n'a encore admis aucun guide : 51 passages
depuis le 12/10, tous retenus à la relecture. Les guides en ligne viennent des routines et des
sessions, qui écrivent dans `articles.json`. Le rapport le dit (alerte « rédacteur automatique sans
résultat »). Un jeton Workers AI refusé (HTTP 401 ou 403) fait désormais échouer le passage au lieu
de le laisser vert. La découverte laisse de côté un guide de plus de 18 000 octets, trop long pour
tenir dans une requête avec ses sources (statut `held_guide_too_large` s'il est demandé par son
nom) : au 12/11, seul le guide du Costa Rica est dans ce cas.

**Reprise d'un déploiement doublé.** Si un commit arrive sur `main` pendant une construction, le
déploiement ne publie rien (le site ne revient jamais en arrière) et relance lui-même
`build-pages.yml` sur le nouveau `main` (entrée `republish`). Avant, il échouait, et un commit hors
de `site-src`, qui ne déclenche aucune construction, laissait le guide hors ligne.

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
| `vsd-weekly-report.yml` | toutes les 6 heures (01:07, 07:07, 13:07, 19:07 ; rapport dès le dimanche midi) | Rapport hebdomadaire et issue d'alerte |

`vsd-writing-guide` ne tourne plus seul depuis le 12/11/2026 (voir « Le trajet d'un guide »).
Lancés à la main seulement, pour qualifier un modèle : `vsd-writing-draft`, `-entailment`,
`-evaluation`, `-guide-review`, `-guide-revision`, `-probe`. Ils ne tournent jamais seuls.
`vsd-voice-pilot.yml` (qualification ponctuelle des voix, terminée le 12/10) a été supprimé.

Secrets : `VSD_ADMIN_TICK_KEY` (appels signés du panneau privé), `CLOUDFLARE_WORKERS_AI_TOKEN`
(rédaction). Variables : `VSD_FREE_PROMOTION_SCHEDULE` et `VSD_FREE_RENDER_SCHEDULE` à `true`.

## Surveillance

- **Rapport hebdomadaire** : une issue `rapport-hebdo` par semaine, ouverte au premier passage
  après le dimanche midi (UTC), pour exister avant les routines du lundi matin qui la lisent
  (publié cette semaine, publication, référencement, sources des guides, file à venir, échecs de
  workflows, alertes, ce qui attend Mathis). La précédente est fermée automatiquement. Si GitHub
  saute un passage, le suivant ouvre le rapport de la semaine.
- **Alerte** : toutes les six heures, une issue `alerte-file` s'ouvre ou se met à jour si
  Instagram ou Facebook n'a plus de post programmé à 14 jours, si un workflow échoue deux fois dans
  la semaine, ou à 60 jours de la date d'arrêt ; s'y ajoutent les alertes de publication, de
  référencement et de guides décrites plus bas. Elle se ferme seule quand tout est revenu dans l'ordre.
  - Son **titre** dit ce qui se passe (« ⚠️ Instagram coupé de Buffer et 2 autres alertes »).
  - GitHub ne prévient personne quand le texte d'une issue change : chaque alerte **nouvelle** depuis
    le passage précédent est donc annoncée par un **commentaire** qui la nomme et mentionne le
    propriétaire du dépôt. Une alerte déjà ouverte qui **s'aggrave** est annoncée de la même façon :
    un post retenu de plus, un post menacé de plus, un guide périmé de plus. Un nombre qui baisse ne
    prévient pas. Les codes et les nombres des alertes en cours sont gardés dans le texte de l'issue
    (`issue-plan.mjs`). Limite : si un post sort de la liste pendant qu'un autre y entre entre deux
    passages, le nombre ne bouge pas et rien n'est annoncé.
  - Une alerte que le passage **n'a pas pu relire** reste telle qu'elle était connue : elle n'est ni
    levée, ni annoncée de nouveau, et l'issue ne se ferme pas. C'est le cas des alertes de
    publication et de référencement quand le panneau ne répond pas, et de l'alerte sur le rédacteur
    quand la recherche GitHub échoue. L'issue les range alors sous « Non relues à ce passage ». Pour
    repartir de zéro, fermer l'issue à la main : le passage suivant en ouvre une neuve.
  - Le libellé de chaque alerte est gardé avec son code dans le texte de l'issue (deux commentaires
    HTML invisibles, en fin de texte). Retoucher le texte visible à la main ne change donc rien : il
    est récrit à chaque passage, et une alerte non relue garde son libellé d'origine. Supprimer ces
    commentaires fait repartir de zéro : le passage suivant annonce toutes les alertes en cours.
- **Guides** (`guide-health.mjs`) :
  - section « Sources des guides » du rapport : les guides dont `sourcesCheckedOn` aura plus de
    45 jours dans les 10 jours, groupés par date. Au-delà de 45 jours, `auto_social.py` ne tire plus
    de posts du guide ; l'alerte se lève quand un guide a dépassé la limite ;
  - alerte si aucun guide n'a été publié depuis plus de 10 jours (`publishedOn` du catalogue). La
    file `editorial-queue.json` n'est plus surveillée : les routines écrivent dans `articles.json` ;
  - alerte si le rédacteur automatique (`vsd-writing-guide.yml`) tourne sans avoir admis de guide
    depuis 14 jours. Elle tombe quand il admet un guide, ou quand il est mis en sommeil (aucun
    passage dans la semaine).
- **Référencement** (`docs/seo.md`) : le rapport de la semaine donne les clics et impressions Google sur
  28 jours, les requêtes en hausse et les pages indexées, lus dans le panneau privé par un appel
  signé en lecture seule. L'alerte se lève aussi si l'indexation recule sur 7 jours ou si les
  impressions sont divisées par deux. Après chaque déploiement, `indexnow.py` prévient Bing et
  Yandex des pages changées.
- **Publication** : le même appel signé rapporte l'état du moteur du panneau (section
  « Publication » du rapport : état de chaque canal Buffer et date de leur dernière relecture par
  le panneau, dernier passage, posts par état, posts
  retenus ou en échec, posts prêts dont le canal ne reçoit rien). L'alerte se lève aussi dans les
  cas ci-dessous et retombe d'elle-même quand la cause disparaît. Si le panneau ne répond pas ou
  n'envoie pas ce bloc, le rapport le dit ; au deuxième passage de suite sans lecture (plus de
  4 heures), l'alerte « état du moteur illisible » se lève, car les autres alertes de publication
  sont alors aveugles. La date de la première lecture manquée est gardée d'un passage à l'autre
  dans le cache du workflow, enregistré juste après l'écriture du rapport, même si une étape
  suivante échoue. Une mémoire perdue, ou vieille de plus de 9 heures (passage sauté, cache non
  enregistré), ne compte pas : le délai repart, ce qui ne fait que retarder cette alerte d'un passage.

  | Alerte | Déclenchement | Quoi faire |
  | --- | --- | --- |
  | Canal coupé | Instagram, Facebook ou TikTok déconnecté, verrouillé ou en pause dans Buffer (Instagram ou Facebook absent compte aussi ; TikTok absent non, il est facultatif) | Buffer, publish.buffer.com > Channels : reconnecter le canal, le déverrouiller ou relancer sa file. Le moteur relit les canaux à chaque passage : rien d'autre à faire. |
  | Moteur silencieux | Aucun passage du moteur depuis plus de 6 heures (il passe à :37 et :52 de chaque heure), ou moteur désactivé | Page Publication du panneau, puis logs du Worker. Causes habituelles : clé Buffer refusée (la recoller page Connexions), Buffer injoignable, tâche planifiée arrêtée. |
  | Accès Buffer absent | Aucune clé Buffer enregistrée dans le panneau | Page Connexions du panneau. |
  | Canaux plus relus | La dernière relecture réussie des canaux Buffer par le panneau a plus de 24 heures (il les relit à chaque collecte et à chaque passage du moteur, et récrit cette date au plus toutes les 6 heures) | Page Connexions du panneau : vérifier la clé Buffer, la recoller si elle est refusée ; sinon logs du Worker (`buffer_channels_unreadable`). Tant que l'alerte tient, l'état des canaux donné par le rapport est celui de cette date : une coupure plus récente n'est pas vue. |
  | Posts bloqués | Un post retenu ou en échec depuis moins de 7 jours (un lot retiré du stock exprès ne compte pas) | Page Publication du panneau : lire le motif. Échéance dépassée : le post est perdu, corriger la cause (canal, clé) pour les suivants. L'alerte tombe 7 jours après le blocage. |
  | Posts menacés | Un post prêt à moins de 24 h de son échéance sur un canal qui ne reçoit rien | Rétablir le canal avant l'échéance, sinon le post sera retenu. |
  | État du moteur illisible | Le panneau ne répond plus au rapport, ou répond sans le bloc « publication », depuis plus de 4 heures | Vérifier que le panneau est en ligne, puis que la version déployée est à jour (`npm run deploy` par Mathis). |

  Les posts TikTok ne lèvent aucune alerte tant que TikTok est absent de Buffer (réseau facultatif) :
  ils restent listés dans la section « Publication ». Non couvert : un post resté « à vérifier »
  (envoi au résultat incertain), qui se lit dans les compteurs du registre ; des canaux dont le
  panneau ne donne aucune date de relecture (clé tout juste enregistrée, jamais relue depuis), ce
  que la section « Publication » écrit sans lever d'alerte.
- Limite : le rapport ne sait pas si le panneau a importé un lot. Un lot refusé à l'import n'entre
  pas au registre et reste invisible ici ; chaque post de la « file à venir » sort donc avec
  « état cloud inconnu ». Il faudrait que le bloc « publication » du panneau donne le résultat de
  son dernier import (date, lots importés, lots refusés avec leur code, lots reportés) et les
  identifiants de lots présents au registre.
- Limite : la preuve de publication Instagram/Facebook n'est pas lisible depuis GitHub
  (pas d'API publique). Le rapport liste les posts dont l'échéance est passée ; la preuve
  est dans le panneau privé et sur les profils.
- La liste « ce qui attend Mathis » se tient à jour dans `.github/vsd-control/attente-mathis.json`.

## Date d'arrêt

Toute la chaîne s'arrête d'elle-même le **14 septembre 2027** (constante `STOP` ou `END`
dans `invoke-admin.mjs`, `stock-control.mjs`, `pin_intake.py` et plusieurs workflows).
Le rapport alerte 60 jours avant ; il faudra alors repousser ces dates.
