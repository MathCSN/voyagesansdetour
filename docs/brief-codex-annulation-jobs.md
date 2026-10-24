# Brief Codex : annuler trois jobs de l'ancien format dans le registre du panneau privé

À exécuter dans le projet ChatGPT « BLOG » (`~/.codex/.chatgpt-projects/g-p-6aa80b285c0081919bf16079e50bfb9e/`),
panneau ChatGPT Sites `voyage-sans-detour-admin.cousinmathis31.chatgpt.site`. Rédigé le 24/10/2026.
**Échéance : avant le 25/10/2026 à 15:30 UTC** (envoi Facebook prévu à 16:00 UTC).
Alternative si c'est impossible à temps : remettre les médias en ligne (PR #8 du dépôt).

## Pourquoi

Le 24/10, les médias de ces trois lots ont été retirés du site (PR #1). Or ils sont déjà dans le registre D1.
Un échec d'envoi Buffer (`publishPrepared` → `uncertain`) ou un post Buffer en `error` met le job à l'état `unknown`.
Ensuite, `scheduler.cadenceUsageAt` renvoie `Number.MAX_SAFE_INTEGER` pour tout le canal dès qu'un job est
`reserved`, `submitting`, `unknown` ou `submitted_import_pending`, ou `accepted` avec une échéance passée :
plus rien ne part sur Instagram ni sur Facebook. Rien dans le transport ne produit seul la preuve d'absence
exhaustive qui permettrait d'en sortir : le blocage serait indéfini.

## Les trois jobs (job.id = contentId = deduplicationKey)

| Job | Canal | dueAt | État attendu aujourd'hui | État cible |
| --- | --- | --- | --- | --- |
| `vsd-production:facebook:sintra-trois-temps-2026-10:photos-v1` | facebook | 2026-10-25T16:00:00Z | `accepted` (post déjà créé dans Buffer, programmé) | `failed`, opération `not_created` |
| `vsd-production:instagram:portugal-sans-voiture-bagages:voice-v1` | instagram | 2026-10-25T17:00:00Z | `ready` (retenu par la cadence jusqu'au 25/10 ≈ 20:38 UTC) | `paused`, `currentOperationId: null` |
| `vsd-production:instagram:porto-3-jours-sans-voiture:voice-v1` | instagram | 2026-11-01T17:00:00Z | `ready` | `paused`, `currentOperationId: null` |

Lire l'état réel avant toute écriture : si un job n'est pas dans l'état attendu, voir « Si c'est trop tard ».

## Ce qu'il faut écrire

Une maintenance ponctuelle sur le modèle exact de `src/exploitation/cloud-publications/archival-rejection.mjs`
et `archival-maintenance.mjs` (déjà raccordée au tick par l'action `reconcile_windsor_refusal`) :
mêmes clôtures des écrivains (bail du runtime), proposition calculée hors ligne, `validateState`, puis un seul CAS
sur l'état complet. Un contrat figé liste les trois identifiants ; tout autre job reste intact.

1. **Instagram (2 jobs `ready`)** : il n'existe pas d'événement de pause dans `transition`. Copier l'état, mettre
   `status: 'paused'`, `reason: 'retired_old_format_2026-10-24'`, `nextAttemptAt: null`, laisser
   `currentOperationId: null`, puis `validateState(nextState)` (la ligne 147 du scheduler accepte `paused` sans
   opération) et commit CAS avec `expectedRevision = state.revision`.
2. **Facebook (job `accepted`)**, dans cet ordre :
   1. Supprimer le post programmé dans Buffer. Mathis : publish.buffer.com > Queue > post « 🏰 Sintra sans voiture »
      prévu le 25/10 à 17:00 (heure de Paris) > More actions > Delete. Ou via l'API, avec le `providerPostId`
      de l'opération courante.
   2. Vérifier l'absence : `post(input:{id})` ne renvoie plus le post, et `posts(...)` sur le canal Facebook
      `6ab88a42ea19ca0bdefe4aac` ne contient aucun post avec ce texte ou ces médias, ni en file ni en envoi.
   3. Seulement après cette vérification, appliquer
      `transition(state, {type:'reconcile', operationId, evidence, retryable:false}, {now, policy})` avec
      `evidence = {id, responseSha256, provider:'buffer', channelId:<opération>, contentId:<job.id>, operationId,
      payloadRevision:<opération>, source:'provider_lookup', observedAt:now, outcome:'not_created', definitive:true,
      terminal:true, exhaustive:true, noPendingWork:true}` (`responseSha256` = SHA-256 de la réponse de vérification).
      Le scheduler (l. 384-388) n'accepte cette absence qu'avec `provider_lookup` + `exhaustive` + `noPendingWork`.
      `retryOrFail` met alors le job en `failed` sans nouvel essai. Fixer `reason: 'retired_old_format_2026-10-24'`.

Si un tick rapproche le post entre la suppression et le commit, le job passe en `unknown` : ce n'est pas grave,
le même événement `reconcile` est accepté depuis `unknown` (l. 365).

## Garantie à vérifier avant de déployer

Test hors ligne sur une copie de l'état réel :
- `cadenceUsageAt(nextState, 'instagram', {now, dueAt: '2026-10-28T17:00:00Z'})` vaut au plus 1 (le reel publié
  le 18/10 sort de la fenêtre le 25/10) et `cadenceUsageAt(nextState, 'facebook', …)` ne renvoie plus `MAX_SAFE_INTEGER` ;
- `planTick` ne réserve aucun des trois jobs ;
- les autres jobs et opérations sont identiques octet pour octet.

## Si c'est trop tard

- **Facebook publié** (post `sent`, une seule image en ligne) : le job passe en `published`, le canal n'est pas bloqué.
  Supprimer le post depuis Meta Business Suite si on n'en veut pas ; ne rien changer dans D1.
- **Job en `unknown`** (Facebook en erreur, ou reel bagages après un createPost refusé) : supprimer le post Buffer
  s'il existe (statut `error`), vérifier l'absence comme ci-dessus, puis appliquer le même `reconcile`. Le job passe
  en `failed` et le canal se débloque au tick suivant.
- **Délai** : le panneau n'a aucune interface pour annuler un job ou forcer une réconciliation (seulement
  les connexions Buffer et Google, et `extend_planning`, `prepare_planning`, `prepare_facebook`). Compter le temps
  d'écrire, tester et déployer la maintenance (≈ 1 à 2 h pour Codex), puis le prochain tick de publication.
  Il est planifié toutes les 30 min, mais GitHub ne l'exécute en pratique que toutes les 3 à 5 h.
  On peut le lancer tout de suite : Actions > « Voyage Sans Detour cloud control » > Run workflow > `publications`.
  Sans cette maintenance, le canal reste bloqué indéfiniment (16 rapprochements automatiques sur ≈ 12 jours, sans issue).

## Ce qu'il ne faut pas faire

- Pas de mise à jour SQL directe du JSON sans CAS ni `validateState`.
- Pas d'événement `not_created` sans avoir constaté l'absence dans Buffer.
- Ne pas remettre les jobs en `ready` ni les réimporter.
