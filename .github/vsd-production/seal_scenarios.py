#!/usr/bin/env python3
"""Fill in the file fingerprints of photo scenarios and rebuild catalogue.json.

Write a scenario with empty "sha256" fields, run this, then `production.py
--validate`. Sealing never checks facts: validation does.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = 2


def fingerprint(relative: str) -> str:
    return hashlib.sha256((HERE / relative).read_bytes()).hexdigest()


def sealed(entry: dict) -> dict:
    """Return a copy of a {"file", "sha256", ...} reference with its hashes refreshed, nested ones included."""
    result = {key: (sealed(value) if isinstance(value, dict) and "file" in value else value) for key, value in entry.items()}
    return {**result, "sha256": fingerprint(entry["file"])}


def seal(scenario: dict) -> dict:
    assets = {name: sealed(asset) for name, asset in scenario["assets"].items()}
    return {**scenario, "sources": sealed(scenario["sources"]), "photos": sealed(scenario["photos"]), "assets": assets}


def main() -> None:
    items = []
    for path in sorted((HERE / "scenarios").glob("*.json")):
        scenario = json.loads(path.read_text())
        if scenario.get("schemaVersion") != SCHEMA:
            continue
        path.write_text(json.dumps(seal(scenario), ensure_ascii=False, indent=2) + "\n")
        items.append({"contentId": scenario["id"], "notBefore": scenario["review"]["checkedAt"],
                      "file": str(path.relative_to(HERE)), "sha256": fingerprint(str(path.relative_to(HERE)))})
    catalogue = {"schemaVersion": SCHEMA, "items": sorted(items, key=lambda item: (item["notBefore"], item["contentId"]))}
    (HERE / "catalogue.json").write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"sealed": len(items)}))


if __name__ == "__main__":
    main()
