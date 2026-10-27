# Brief Codex : remettre le panneau privé à 100 %

À exécuter dans le projet ChatGPT « BLOG », sur le panneau privé
`voyage-sans-detour-admin.cousinmathis31.chatgpt.site` (code dans `panneau-prive/`).
Rédigé le 27/10/2026 par la session de pilotage. Demande de Mathis : « que tout soit nickel à 100 % ».

Lire d'abord le `CLAUDE.md` du dépôt `MathCSN/voyagesansdetour` (branche main), puis
`docs/chaine-autonome.md` et `docs/monetisation.md`. Depuis le 24/10, le blog est **généraliste,
monde entier** : 22 guides dans 10 pays, rédaction automatique et routines cloud, posts et
épingles générés seuls.

## 1. Réparer la collecte des statistiques (prioritaire)

Symptôme : depuis le 26/10, le workflow « Voyage Sans Detour cloud control » échoue sur les passages
`metrics` (`Cloud task not confirmed: task_attention_required`). `worker/metrics-collection.mjs`
renvoie `partial`. Le panneau montre **Google Search Console** et **Stay22 · reporting** figés au
25/10 (« collecte à rétablir »), alors que GA4 est à jour (27/10).

À faire : lire le journal persistant du serveur et l'état D1 pour trouver quelle source échoue et
pourquoi. Pistes : jeton Google expiré ou révoqué pour la portée Search Console, propriété Search
Console (la propriété utilisée est le préfixe d'URL `https://voyagesansdetour.fr/`, pas le domaine),
clé de l'API Stay22 Reporting, format de réponse changé, quota. Corriger la cause, pas le symptôme.

- Si une reconnexion par Mathis est indispensable (OAuth Google, clé Stay22), afficher dans le
  panneau un bouton clair, en un clic. Si le client OAuth Google est encore en mode « test »
  (jetons valables 7 jours), le noter et donner à Mathis la marche à suivre pour le passer en
  production.
- Une source isolée en panne ne doit plus faire échouer tout le passage `metrics` en boucle : elle
  doit apparaître « à rétablir » dans le panneau, sans rendre le workflow rouge chaque jour.
  Garder l'alerte visible dans le panneau.

Vérification : relancer Actions > « Voyage Sans Detour cloud control » > Run workflow > `metrics`.
Il doit passer au vert, et Search Console et Stay22 doivent afficher un relevé du jour.

## 2. Mettre à jour les cartes figées au 27/09

Plusieurs cartes de « Connexions » et de « Vue d'ensemble » sont du texte de configuration du 27/09,
désormais faux. Les remplacer par l'état réel, idéalement lu automatiquement (dépôt GitHub public,
flux en ligne) plutôt que figé :

| Carte | Aujourd'hui (faux) | Réalité au 27/10 |
| --- | --- | --- |
| Production de contenus | « pas encore créés automatiquement, à activer » | Automatique : chaîne `vsd-writing` (un guide tous les 2 jours) + routines cloud de la holding (guide lundi et jeudi, veille, sujets, partenariats) ; posts et épingles générés par `vsd-render-content` |
| Publication du site depuis le cloud | « rédaction non automatisée », relevé du 27/09 | Rédaction automatisée, 22 guides publiés |
| Pinterest | « 3 tableaux observés, import en attente » | 6 tableaux, 5 flux RSS branchés : `lisbonne.xml`, `preparer-portugal.xml`, `preparer-espagne.xml`, `preparer-italie.xml`, `inspirations-voyage.xml` ; épingles importées le 24/10 |
| Pinterest · import RSS | « premier Pin en attente » | Épingles importées (Japon, Porto, Andalousie, Cinque Terre…) |
| Stay22 · intégration | « inactive, validation de l'hébergement attendue » | Active depuis le 24/10 sur tous les guides (aid `voyagesansdetourfr`, domaine déclaré, commission 30 %) |
| Partenaires de monétisation | « AdSense seul, non connecté » | Stay22 et GetYourGuide (partner_id `HKEWKYM`) actifs ; AdSense en réexamen (demande prévue le 7/11) |
| Hébergement des médias | « 6 médias », relevé du 27/09 | Relever le compte réel depuis `site-src/public-media.json` |
| Make | « compte gratuit observé » | Inutilisé : retirer la carte |
| Contrôle du serveur | « Indisponible » | Doit refléter le dernier passage réussi une fois le point 1 réglé |

## 3. Audiences des réseaux (« Non connecté »)

- **Instagram et Facebook** : relier l'audience (abonnés, vues) via ce qui est déjà en place, les
  statistiques Buffer (`BUFFER_INSIGHTS_ENABLED`) ou l'audience Meta (`META_AUDIENCE_ENABLED`), sans
  service payant. Si l'essai Windsor a expiré, ne pas en dépendre.
- **Pinterest** : relier les statistiques si une voie gratuite existe (API Pinterest avec le compte
  du blog) ; sinon afficher « suivi par le rapport du lundi » plutôt que « Non connecté ».
- **TikTok et YouTube** : le blog ne les utilise pas. Afficher « non utilisé » (ou masquer), pas
  « Non connecté ».

## Règles

- Ne pas toucher aux lots `reviewed-social` déjà importés, ni aux jobs de publication, ni à la
  politique de cadence.
- Aucun secret dans un dépôt ; aucun service payant sans accord de Mathis.
- Tests du panneau verts, build et validation réussis avant le déploiement privé (procédure Sites
  officielle).
- À la fin : relais `agent-relay` destiné à `all`, avec ce qui a été corrigé et ce qui demande
  encore une action de Mathis (en une ligne chacune, avec le lien exact).
