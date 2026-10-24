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
              ──► import quotidien vers le panneau privé (cloud control, 08:53 UTC)
              ──► registre D1 du panneau privé ──► Buffer à l'échéance ──► Instagram / Facebook
```

- **Panneau privé** : application ChatGPT Sites
  `voyage-sans-detour-admin.cousinmathis31.chatgpt.site`. Son code vit hors de ce dépôt,
  dans le projet Codex local `~/.codex/.chatgpt-projects/g-p-6aa80b285c0081919bf16079e50bfb9e/`
  (`panneau-prive/` et `exploitation/cloud-publications/`). Il tient le registre D1, la clé Buffer
  et la cadence : **Instagram 1 post par semaine**, Facebook selon sa politique serveur.
- **Un lot importé ne peut plus être annulé depuis ce dépôt** : le retirer de `index.json`
  ne le retire pas du registre cloud. Seule parade sans redéployer le serveur :
  mettre en pause la file du canal dans Buffer jusqu'à l'expiration de la relecture du lot (`validUntil`).
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

## Les workflows

| Workflow | Quand | Rôle |
| --- | --- | --- |
| `build-pages.yml` | push sur main, chaque jour 07:41 | Construit et déploie le site, publie les guides dus |
| `vsd-cloud-control.yml` | toutes les 30 min ; métriques 06–08 h ; stock 08:53 chaque jour | Déclenche l'envoi des posts dus ; importe un lot relu par jour |
| `vsd-render-content.yml` | lundi 05:17 | Rend les reels, brouillons et admission d'épingles |
| `vsd-reel-intake.yml` | après chaque déploiement | Prépare un storyboard de reel depuis un nouveau guide |
| `vsd-voice-production.yml` → `vsd-voice-adopt.yml` → `vsd-voice-review.yml` → `vsd-voice-promote.yml` | à la main seulement | Chaîne des reels voix de synthèse, en sommeil depuis le 24/10 (ancien format retiré) |
| `vsd-promote-media.yml` | lundi, mercredi, vendredi 06:23 | Promeut un rendu relu en lot social |
| `vsd-writing-discovery.yml` | chaque jour 09:37 | Mises à jour sourcées des guides |
| `vsd-weekly-report.yml` | chaque jour 09:07 (rapport le lundi) | Rapport hebdomadaire et alerte de file vide |

`vsd-writing-guide` tourne seul deux fois par jour (rédaction des nouveaux guides).
Lancés à la main seulement, pour qualifier un modèle : `vsd-writing-draft`, `-entailment`,
`-evaluation`, `-guide-review`, `-guide-revision`, `-probe`. Ils ne tournent jamais seuls.
`vsd-voice-pilot.yml` (qualification ponctuelle des voix, terminée le 12/10) a été supprimé.

Secrets : `VSD_CLOUD_KEY`, `VSD_SITES_DISPATCH_TOKEN` (panneau privé), `CLOUDFLARE_WORKERS_AI_TOKEN`
(rédaction). Variables : `VSD_FREE_PROMOTION_SCHEDULE` et `VSD_FREE_RENDER_SCHEDULE` à `true`.

## Surveillance

- **Rapport hebdomadaire** : chaque lundi, une issue `rapport-hebdo` dans le dépôt
  (publié cette semaine, file à venir, échecs de workflows, alertes, ce qui attend Mathis).
  La précédente est fermée automatiquement.
- **Alerte** : chaque jour, une issue `alerte-file` s'ouvre (ou se met à jour) si
  Instagram ou Facebook n'a plus de post programmé à 14 jours, si aucun nouveau guide n'est prévu
  à 28 jours, si un workflow échoue deux fois dans la semaine, ou à 60 jours de la date d'arrêt.
  Elle se ferme seule quand tout est revenu dans l'ordre.
- Limite : la preuve de publication Instagram/Facebook n'est pas lisible depuis GitHub
  (pas d'API publique). Le rapport liste les posts dont l'échéance est passée ; la preuve
  est dans le panneau privé et sur les profils.
- La liste « ce qui attend Mathis » se tient à jour dans `.github/vsd-control/attente-mathis.json`.

## Date d'arrêt

Toute la chaîne s'arrête d'elle-même le **14 septembre 2027** (constante `STOP` ou `END`
dans `invoke.mjs`, `stock-control.mjs`, `pin_intake.py` et plusieurs workflows).
Le rapport alerte 60 jours avant ; il faudra alors repousser ces dates.
