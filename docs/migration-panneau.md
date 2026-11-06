# Migration du panneau admin hors de ChatGPT Sites

Rédigé le 6 novembre 2026. But fixé par Mathis : **tout passe par Claude**.

**État au 6 novembre 2026, 18 h** : le nouveau panneau est en ligne sur
**https://vsd-admin.kartier.workers.dev** (dépôt privé `MathCSN/vsd-admin`), affichage vérifié dans le
navigateur intégré ; le nouveau moteur de publication est prêt et testé mais **désactivé**. L'ancien serveur
Sites publie toujours, rien n'a été basculé. Procédure exacte : `BASCULE.md` du dépôt privé. Le panneau privé
actuel (`voyage-sans-detour-admin.cousinmathis31.chatgpt.site`) ne peut être déployé que par
Codex ; on le remplace par un panneau que Claude modifie et déploie seul, sans jamais casser la
publication en cours.

## 1. Ce que fait le panneau actuel

Code : `~/.codex/.chatgpt-projects/g-p-6aa80b285c0081919bf16079e50bfb9e/panneau-prive/`
(Worker ChatGPT Sites + base D1, dépôt git local sans remote). Deux choses distinctes y cohabitent.

### L'affichage

| Bloc | Source | État au 06/11 |
| --- | --- | --- |
| Visites, utilisateurs | GA4 (OAuth Google, propriété `556076363`) | collecté, mais affiche « 0 » vérifié sur 30 jours |
| Clics, impressions Google | Search Console (`https://voyagesansdetour.fr/`) | 6 clics, 594 impressions (05/10–03/11) |
| Commissions | Stay22 Reporting API (`X-API-KEY`) | aucune transaction |
| Activité des posts | Buffer `aggregatedPostMetrics` | IG 4 posts / 247 de portée ; FB 3 posts |
| Audiences | Windsor (essai expiré), Meta non autorisé | figées au 27/09 ou « Non connecté » |
| Cartes « lancement », Pinterest, Make, partenaires | texte de configuration | figées au 27/09, fausses |
| Stock de posts | registre D1 | 25 contenus, lisible en lecture seule (`#publications`) |

La collecte est déclenchée par `vsd-cloud-control.yml` (passages `metrics` 06–08 h UTC).

### Le moteur de publication

- **Registre D1** : jobs de publication (un par contenu relu), payloads relus, reçus,
  budget Buffer, verrous (`vsd_publication_*`, `vsd_reviewed_payloads`, `vsd_buffer_budget`).
- **Import du stock** : chaque jour à 08:53 UTC, `stock-control.mjs` (dépôt public) envoie au
  panneau **un** lot relu de `.github/vsd-production/reviewed-social/` (`import_stock`).
- **Envoi** : toutes les 30 min (`:13`, `:43`), le workflow appelle `POST /internal/tick`
  (`kind: publications`). Le moteur crée le post dans Buffer (`createPost`,
  `mode: customScheduled`) **quelques jours avant l'échéance** ; Buffer publie à l'heure.
  Exemple : le post Facebook Porto du 06/11 18:00 a été programmé le 03/11.
- **Sécurité de l'appel** : bearer natif Sites (`VSD_SITES_DISPATCH_TOKEN`) + signature
  HMAC-SHA256 (`VSD_CLOUD_KEY`) sur site, origine, chemin, date, nonce, empreinte du corps.
- Le Worker n'a **aucun ordonnanceur propre** : sans appel du workflow, il ne fait rien.
  Geler l'ancien moteur revient donc à ne plus l'appeler.

Registre relevé le 06/11 (lecture seule) : 10 publiés, 1 programmé dans Buffer
(FB Porto, 06/11 18:00), 9 prêts (IG 11/11, FB 12/11, FB 15/11, IG 18/11, FB 20/11, IG 25/11…),
2 échecs anciens, 2 en pause (ancien format), 1 import Pinterest historique.

## 2. Hébergement retenu : Cloudflare Workers + D1

| Option | Pour | Contre |
| --- | --- | --- |
| **Cloudflare Workers + D1** | Même environnement que l'ancien Worker (même SQL, même API Web) ; Wrangler est déjà connecté sur ce Mac avec les droits Workers et D1 ; gratuit (100 000 requêtes/jour, 5 Go D1, tâche planifiée incluse) ; déploiement en une commande par Claude | Le compte connecté est celui de Mathis ouvert avec `mathis.cousin@go-dansmaville.fr` (pas celui de Workers AI du blog) |
| Vercel | Outils MCP disponibles | Seule équipe accessible : KOPRO ; la protection d'accès native ne couvre pas la production sur le forfait gratuit ; il faudrait une base externe |
| Supabase | Base Postgres, Auth intégrée | Seule organisation : KOPRO, déjà 2 projets (limite gratuite) ; pas d'hébergement de pages HTML |

**Décision** : Worker `vsd-admin` + base D1 `vsd-admin` sur le compte Cloudflare déjà connecté
(sous-domaine `kartier.workers.dev`).
Aucun service payant. Le Worker est déplaçable plus tard vers un autre compte Cloudflare
(même code, `wrangler deploy` + export/import D1) si Mathis le souhaite.

Le code vit dans le **dépôt privé `MathCSN/vsd-admin`** ; jamais dans ce dépôt public.
Les secrets (clé du coffre, clé de signature) sont des secrets Wrangler, jamais dans un fichier.

## 3. Accès réservé à Mathis

Pas de mot de passe, pas de compte tiers : **une clé d'accès (passkey)** sur le Mac de Mathis
(Touch ID, synchronisée par le trousseau iCloud sur son iPhone).

- Inscription : un **lien à usage unique** (valable 7 jours, empreinte seule stockée en base)
  ouvre « Créer ma clé d'accès ». Un clic, Touch ID, c'est fini. Aucune inscription libre.
- Connexion : « Se connecter » → Touch ID. Session de 30 jours (cookie `HttpOnly`, `Secure`,
  `SameSite=Strict`, signé), révocable.
- Perte de la clé : Claude génère un nouveau lien d'inscription depuis le Mac
  (`npm run lien-inscription`), sans intervention de Mathis sur un site tiers.
- Toutes les pages : `noindex`, `no-store`, CSP stricte, aucun script tiers.
- L'URL `*.workers.dev` n'est annoncée nulle part ; même trouvée, elle ne montre qu'un écran de
  connexion.

## 4. Ce que le nouveau panneau affiche, et d'où

Tout est relu en direct ou par la tâche planifiée du Worker (cron horaire gratuit) ; chaque
chiffre porte sa source et sa date. Aucun texte de configuration figé.

| Bloc | Source | Accès |
| --- | --- | --- |
| Visites, pages vues, pages les plus lues | GA4 Data API | Google OAuth (Mathis, une fois) |
| Clics, impressions, requêtes | Search Console API | même connexion Google |
| Revenus Stay22 | Stay22 Reporting API | clé API Stay22 (Mathis, une fois) |
| Revenus GetYourGuide | pas d'API de rapport pour les affiliés : lien direct vers l'espace partenaire et relevé daté saisi depuis le panneau | aucun |
| Posts publiés et programmés | Buffer API (posts envoyés et en file) | clé API Buffer (Mathis, une fois) |
| Posts à venir | `reviewed-social/index.json` et lots du dépôt public | aucun (fichiers publics) |
| Activité des posts (portée, vues) | Buffer `aggregatedPostMetrics` | même clé Buffer |
| Guides publiés et à venir | `site-src/articles.json`, file éditoriale du dépôt | aucun |
| Épingles et tableaux Pinterest | flux RSS publics des 6 tableaux (dernière épingle de chacun) et épingles proposées par le site (`pinterest-additions.json`) ; le nombre d'abonnés et d'impressions demande l'API Pinterest, affiché « non relevé » | aucun |
| Audiences Instagram / Facebook | statistiques Buffer ; le total d'abonnés exige une app Meta revue : affiché « non relevé » plutôt que zéro | — |
| État des workflows GitHub | API GitHub publique du dépôt (lecture, mise en cache) | aucun |
| Ce qui attend Mathis | `.github/vsd-control/attente-mathis.json` | aucun |

TikTok et YouTube n'apparaissent pas : le blog ne les utilise pas.

## 5. Les accès que Mathis doit donner

Le minimum, chacun depuis la page « Connexions » du nouveau panneau, avec le lien exact :

1. **Créer sa clé d'accès** : ouvrir le lien d'inscription, Touch ID.
2. **Buffer** : coller la clé API (publish.buffer.com → Settings → API). Elle sert à
   l'affichage tout de suite et au moteur après la bascule. Le panneau vérifie le compte
   `contact@voyagesansdetour.fr` et les deux canaux avant de l'enregistrer (chiffrée AES-GCM).
3. **Google** (GA4 + Search Console) : dans la console Google Cloud, sur le client OAuth Web
   existant, ajouter l'URI de redirection affichée par le panneau et créer un secret ; coller
   l'identifiant et le secret dans le panneau ; cliquer « Connecter Google » et accepter
   (lecture seule : `analytics.readonly`, `webmasters.readonly`).
4. **Stay22** : coller la clé de l'API Reporting (hub.stay22.com).

Rien à faire pour Pinterest, GitHub, le site, GetYourGuide (lien direct) ni pour la bascule.

## 6. Le nouveau moteur de publication

Écrit dans le même dépôt privé, **désactivé par défaut** (`PUBLICATION_ENABLED` absent).
Il reprend le contrat de lot actuel (`schemaVersion`, `contentId`, `deduplicationKey`, `dueAt`,
`payload`, `review`) et ses garde-fous :

- relecture approuvée, valide à l'échéance (`review.validUntil > dueAt`), empreinte SHA-256 du
  payload canonique égale à `review.payloadRevision`, médias uniquement sur
  `https://voyagesansdetour.fr`, formats `instagram/reel` et `facebook/photos` ;
- cadence plafond par canal (2 posts / 7 jours), file Buffer gratuite (10 posts par canal) ;
- programmation dans Buffer au plus tôt 3 jours avant l'échéance, comme l'ancien moteur ;
- **anti-doublon côté Buffer** : avant chaque `createPost`, lecture des posts programmés et
  envoyés du canal ; un post au même texte et aux mêmes médias est adopté, jamais recréé ;
- un envoi au résultat incertain (délai, réponse illisible) n'est jamais retenté à l'aveugle :
  le job passe « à vérifier » et se résout par la lecture Buffer suivante ;
- import des lots directement depuis le dépôt public (plus besoin que GitHub pousse le stock) ;
- appel `POST /internal/tick` signé HMAC (clé dédiée `VSD_ADMIN_TICK_KEY`), même enveloppe que
  `invoke.mjs` sans le bearer Sites, nonce à usage unique ;
- page « Publication » : registre, journal et **plan à blanc** (ce que le moteur ferait, sans rien envoyer).

Tests (`npm test`, 44 au 06/11, après revue de sécurité) : contrat vérifié sur de vrais lots relus (l'empreinte
`payloadRevision` est recalculée à l'identique sur les 22 posts relus du dépôt), adoption d'un post
déjà dans Buffer sans doublon, envoi incertain, refus Buffer, média absent, verrou, rejeu d'appel signé,
import du stock (retraits, échéances passées), comparaison des registres.

## 7. Procédure de bascule

La procédure exacte, commande par commande, est tenue dans le dépôt privé
(`vsd-admin/BASCULE.md`). Elle est exécutée par une session Claude, après accord du pilotage.

Pré-requis : nouveau panneau en ligne, clé Buffer connectée, `npm test` vert, page
« Moteur » du panneau montrant un plan à blanc cohérent (ce que le moteur ferait, sans rien
envoyer).

1. **Choisir le créneau** : juste après un passage `:13` ou `:43`, à au moins 6 h de la
   prochaine échéance d'un post, et hors de 08:40–09:10 UTC (import du stock).
2. **Export du registre** (lecture seule) : relever `GET /api/overview` de l'ancien panneau dans
   le navigateur intégré et l'enregistrer dans le dépôt privé ; lancer `stock_status` sur
   l'ancien et garder le journal.
3. **Reprise à l'identique** dans le nouveau, toujours désactivé : import de tous les lots déjà
   importés par l'ancien, puis réconciliation avec Buffer. Chaque job devient publié (post
   envoyé trouvé), programmé (post en file trouvé, identifiant Buffer conservé) ou prêt. Un job
   dont l'échéance est passée sans post trouvé est mis « à vérifier », jamais envoyé en retard.
4. **Comparer** l'export de l'ancien et l'état reconstruit. Toute différence arrête la bascule.
5. **Gel de l'ancien et bascule en un seul commit** sur `main` du dépôt public :
   `vsd-cloud-control.yml` pointe vers le nouveau (origine, clé `VSD_ADMIN_TICK_KEY` créée juste avant,
   même valeur dans Cloudflare et dans les secrets GitHub), et l'étape de lecture de l'ancien stock
   disparaît du rapport hebdomadaire ; plus aucun appel planifié vers `chatgpt.site`. À partir de ce commit, l'ancien ne reçoit plus rien : il est
   gelé, ses données restent intactes.
6. **Activer le nouveau** juste après le commit, avant le passage suivant.
7. **Vérifier** au passage suivant : reçu `publications` en succès dans le workflow, aucun post
   en double dans Buffer, prochain post visible « programmé » dans le nouveau panneau.

**Retour arrière** (si l'étape 7 échoue) : désactiver le nouveau moteur, `git revert` du
commit de bascule. L'ancien reprend là où il en était avec ses propres reçus ; le nouveau n'a
rien créé en double grâce au contrôle anti-doublon.

Après une semaine sans incident : retirer les secrets `VSD_CLOUD_KEY` et
`VSD_SITES_DISPATCH_TOKEN` du dépôt public, mettre à jour `docs/chaine-autonome.md` et
`attente-mathis.json`. Le projet ChatGPT Sites peut alors être archivé par Mathis.

## 8. Ce qui ne change pas d'ici la bascule

L'ancien panneau reste en service, seul à publier. Le nouveau le lit (Buffer, fichiers publics)
sans jamais écrire chez Buffer ni chez l'ancien. Aucune modification du serveur Sites ni de ses
données.
