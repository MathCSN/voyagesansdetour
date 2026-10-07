#!/usr/bin/env python3
"""Create one conservative editorial candidate from an existing guide.

This is a no-cost, deterministic fallback for the cloud editorial queue.  It
does not invent a destination, a hotel, a price or a lived experience.  It
reuses a published guide's already reviewed source set, fetches each source
once to bind the current visible-text hash, and writes a clearly labelled
verification update.  The normal intake still revalidates the source bytes
near the release date before any article can be published.

The generator is intentionally bounded: one candidate per scheduled run,
eight unadmitted candidates maximum, and no paid API or language-model call.
If a source is unavailable, it fails closed and leaves the queue untouched.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path

import autonomous_editorial as intake
import editorial_queue as queue

ROOT = Path(__file__).resolve().parent
UTC = dt.timezone.utc
HARD_STOP = dt.datetime(2027, 9, 14, 21, 59, 59, tzinfo=UTC)
MAX_PENDING = 8
CADENCE = dt.timedelta(days=14)
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now_utc(value=None):
    value = value or dt.datetime.now(UTC)
    require(value.tzinfo is not None, "Clock must include timezone")
    return value.astimezone(UTC).replace(microsecond=0)


def read_json(path: Path):
    require(path.is_file() and not path.is_symlink(), f"Missing JSON: {path.name}")
    require(path.stat().st_size <= 2 * 1024 * 1024, "JSON input too large")
    return json.loads(path.read_text(encoding="utf-8"))


def iso(value: dt.datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def next_release(now: dt.datetime, articles, state, candidates=()) -> dt.datetime:
    dates = [now]
    for article in articles:
        for key in ("publishedOn", "updatedOn"):
            value = article.get(key)
            if value:
                try:
                    dates.append(dt.datetime.fromisoformat(value).replace(tzinfo=dt.timezone.utc))
                except ValueError:
                    pass
    for entry in state.get("drafts", []) + state.get("promotions", []):
        dates.append(queue.instant(entry["releaseAt"]))
    for candidate in candidates:
        value = candidate.get("releaseAt")
        if value:
            dates.append(queue.instant(value))
    candidate = max(dates) + CADENCE
    # Keep the queue predictable: 08:00 UTC is 10:00 Paris in summer and
    # 09:00 Paris in winter, without guessing a local DST offset in JSON.
    candidate = candidate.replace(hour=8, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate = (now + CADENCE).replace(hour=8, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += dt.timedelta(days=1)
    return candidate


def anchor(text: str) -> str:
    words = re.findall(r"[\wÀ-ÿ][\wÀ-ÿ'’-]{2,}", text)
    require(len(words) >= 2, "Source visible text is too short")
    return " ".join(words[:3])[:120]


def source_manifest(article):
    manifest = []
    for source in article["sources"]:
        observed = intake.source_fingerprint(source["url"])
        manifest.append({"url": source["url"], "sha256": observed["sha256"],
                         "requiredText": [anchor(observed["text"])]})
    return manifest


def make_article(base, release_date, checked_on):
    base_title = base["shortTitle"]
    slug = f"mise-a-jour-{base['slug']}-{release_date}"
    require(SLUG.fullmatch(slug), "Generated slug invalid")
    title = f"Mise à jour : {base_title}, les vérifications avant le départ"
    summary = (f"Une fiche de contrôle pour relire « {base_title} », retrouver les sources "
               "officielles et vérifier les informations variables avant de réserver.")
    source_lines = [
        f"Cette mise à jour reprend le guide « {base['title']} » et sa liste de sources. "
        "Elle ne raconte pas un séjour vécu et ne présente aucun hébergement comme testé.",
        f"Le contenu de référence a été relu le {checked_on}. Les horaires, accès, tarifs et "
        "conditions peuvent évoluer : ouvrez les pages officielles le jour de votre décision.",
    ]
    sections = [
        {"id": "point-de-depart", "title": "Relire le guide avant de choisir",
         "paragraphs": source_lines},
        {"id": "controles", "title": "Les contrôles à refaire pour vos dates",
         "paragraphs": [
             "Commencez par l’adresse exacte, la gare ou l’arrêt réellement utilisé et le trajet final avec les bagages. Une distance courte sur une carte ne décrit ni les pentes, ni les escaliers, ni l’entrée d’un bâtiment.",
             "Contrôlez ensuite les horaires, les réservations, les conditions d’accès et le prix complet auprès de l’exploitant concerné. Si une information n’est pas confirmée pour vos dates, gardez-la comme inconnue et adaptez le programme.",
         ],
         "bullets": [
             "Date et heure du déplacement, avec la dernière correspondance utile.",
             "Accès réel depuis la rue jusqu’à l’entrée du lieu ou du logement.",
             "Conditions et montant affichés par l’opérateur au moment de réserver.",
             "Plan B si un service, une visite ou un accès change.",
         ]},
        {"id": "sources-officielles", "title": "Utiliser les sources plutôt qu’une promesse",
         "paragraphs": [
             "Les liens ci-dessous servent à vérifier les faits qui changent. Ils ne constituent pas une recommandation commerciale et ne remplacent pas les conditions publiées par l’opérateur.",
             "Le guide reste une proposition éditoriale documentée. Adaptez le parcours à vos dates, à votre budget et à vos besoins d’accès ; aucune expérience personnelle n’est revendiquée.",
         ]},
    ]
    faq = [
        {"question": "Cette mise à jour raconte-t-elle un voyage réalisé par l’équipe ?",
         "answer": "Non. Il s’agit d’une fiche éditoriale documentée et aucune adresse n’est présentée comme testée personnellement."},
        {"question": "Pourquoi vérifier les sources le jour du départ ?",
         "answer": "Les horaires, accès, réservations, prix et conditions peuvent changer après la rédaction ; les pages officielles restent la référence pour vos dates."},
        {"question": "Que faire si une information n’est plus confirmée ?",
         "answer": "La laisser comme inconnue, choisir une solution vérifiable ou reporter la décision plutôt que d’inventer un détail."},
    ]
    return {
        "slug": slug, "title": title, "shortTitle": f"Mise à jour {base_title}",
        "destination": base["destination"], "category": "Mises à jour",
        "description": f"Fiche de contrôle liée à {base_title} : sources officielles, accès, horaires et vérifications avant de réserver.",
        "readMinutes": 3, "summary": summary, "sections": sections, "faq": faq,
        "sources": base["sources"], "related": [base["slug"]],
        "sourcesCheckedOn": checked_on,
    }


def generate(root=ROOT, now=None):
    now = now_utc(now)
    require(now <= HARD_STOP, "Authorised period ended")
    articles = read_json(root / "articles.json")
    state = read_json(root / "editorial-queue.json")
    candidates_dir = root / "editorial-candidates"
    candidates_dir.mkdir(exist_ok=True)
    candidates = [read_json(path) for path in sorted(candidates_dir.glob("*.json"))]
    known_ids = {item.get("id") for item in state.get("drafts", []) + state.get("promotions", [])}
    pending = len(state.get("drafts", [])) + sum(
        1 for item in candidates
        if item.get("review", {}).get("publicationApproved") is False
        and item.get("id") not in known_ids
    )
    if pending >= MAX_PENDING:
        return {"status": "capacity", "changed": False, "pending": pending}
    known_slugs = {item.get("article", {}).get("slug") for item in candidates}
    known_slugs |= {item.get("slug") for item in articles}
    base = articles[len(candidates) % len(articles)]
    release = next_release(now, articles, state, candidates)
    release_date = release.date().isoformat()
    article = make_article(base, release_date, now.astimezone(dt.timezone.utc).date().isoformat())
    if article["slug"] in known_slugs:
        return {"status": "already_present", "changed": False, "id": f"auto-{article['slug']}"}
    sources = source_manifest(article)
    candidate = {
        "schemaVersion": 1, "id": f"auto-{article['slug']}",
        "releaseAt": iso(release), "validUntil": iso(release + dt.timedelta(days=30)),
        "article": article, "sources": sources,
        "review": {"publicationApproved": False, "fabricatedExperience": False, "commercialClaims": False,
                    "method": "deterministic-source-recheck-v1"},
    }
    # Validate locally before writing. Intake repeats the same checks and binds
    # fresh source fingerprints at the release window.
    intake.validate_candidate(candidate, {item["slug"] for item in articles})
    path = candidates_dir / f"{candidate['id']}.json"
    require(not path.exists() and not path.is_symlink(), "Candidate identity already exists")
    path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "generated", "changed": True, "id": candidate["id"], "releaseAt": candidate["releaseAt"], "sourceCount": len(sources)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        result = generate(args.root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"status": "blocked", "changed": False, "reason": type(error).__name__}
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"changed={str(result.get('changed', False)).lower()}\n")
            if result.get("id"):
                handle.write(f"candidate_id={result['id']}\n")


if __name__ == "__main__":
    main()
