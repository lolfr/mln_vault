#!/usr/bin/env python3
# version: 0.2.0
"""
archive-enrich/src/build_csv.py

Convertit les enrichissements en attente (applied=0) en CSV conforme à ton
`import_csv.py` existant.

Règles d'application :
  - Le champ `description` est toujours appliqué (c'est la vraie valeur ajoutée).
  - Le champ `title` est appliqué UNIQUEMENT si :
      should_replace_title=true ET le titre actuel est jugé "raw" (config.is_raw_filename_title)
  - Les champs product/campaign/year/country/language sont appliqués
    UNIQUEMENT si la valeur actuelle est NULL (on n'écrase pas).
  - Les tags sont fusionnés via le format pipe-separated de ton importer.
  - L'année LLM n'est jamais appliquée si elle a une `year_confidence='unknown'`.

Usage :
    python build_csv.py --out data/enrichments.csv
    python build_csv.py --min-confidence 0.6 --out data/enrichments.csv
    python build_csv.py --mark-applied   # marque applied=1 après export (option)

L'application réelle se fait ensuite par :
    cd /chemin/vers/ton/projet
    python import_csv.py /chemin/vers/data/enrichments.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("build_csv")

# Colonnes acceptées par ton import_csv.py
CSV_FIELDS = [
    "id", "title", "description", "item_type", "product", "campaign",
    "year", "date_exact", "language", "country",
    "rights_status", "publication_level", "tags", "notes_internal",
]


def safe(v):
    """Convertit None/'' en chaîne vide, tout le reste en str."""
    return "" if v is None else str(v).strip()


def build_row(item: sqlite3.Row, enrich: dict, min_confidence: float) -> dict | None:
    """Retourne une ligne CSV ou None si rien à appliquer.

    Politique :
      - Champs NULL en base : on remplit avec ce que dit le LLM.
      - Champs non NULL : on ne touche PAS, sauf cas spécifique du titre.
      - description : on remplit toujours si vide, on REMPLACE jamais si plein
                      (l'enrichissement initial peut être relancé plus tard).
    """
    conf = enrich.get("overall_confidence") or 0
    if conf < min_confidence:
        return None

    row = {"id": item["id"]}
    changes = []

    # ─── Titre ───
    new_title = enrich.get("title_inferred")
    if (enrich.get("should_replace_title")
            and new_title
            and config.is_raw_filename_title(item["title"])):
        row["title"] = new_title
        changes.append(f"title={new_title!r}")

    # ─── Description : toujours appliquée si vide ET proposée ───
    if not item["description"] and enrich.get("description"):
        row["description"] = enrich["description"]
        changes.append("description")

    # ─── Product (uniquement si null) ───
    if not item["product"] and enrich.get("product"):
        row["product"] = enrich["product"]
        changes.append(f"product={enrich['product']}")

    # ─── Campaign (uniquement si null) ───
    if not item["campaign"] and enrich.get("campaign") and enrich["campaign"] != "other":
        row["campaign"] = enrich["campaign"]
        changes.append(f"campaign={enrich['campaign']}")

    # ─── Year (uniquement si null ET LLM confiant sur l'année) ───
    if (not item["year"]
            and enrich.get("year_estimate")
            and enrich.get("year_confidence") in ("exact", "narrow")):
        row["year"] = enrich["year_estimate"]
        changes.append(f"year={enrich['year_estimate']}")

    # ─── Country (uniquement si null) ───
    if not item["country"] and enrich.get("country"):
        row["country"] = enrich["country"]
        changes.append(f"country={enrich['country']}")

    # ─── Language (uniquement si null) ───
    if not item["language"] and enrich.get("language"):
        row["language"] = enrich["language"]
        changes.append(f"language={enrich['language']}")

    # ─── Tags (toujours en mode ajout, ton importer fait INSERT OR IGNORE) ───
    tags = enrich.get("tags") or []
    # On filtre les tags vides ou trop génériques (sécurité)
    BANNED = {"publicite", "publicity", "advertising", "ad", "advert", "pub"}
    clean_tags = [t.strip().lower() for t in tags if t and t.strip().lower() not in BANNED]
    if clean_tags:
        row["tags"] = "|".join(clean_tags)
        changes.append(f"tags×{len(clean_tags)}")

    # ─── notes_internal : on ajoute un bloc enrichment_meta SANS écraser ───
    # On laisse vide ici (ton importer remplacerait notes_internal en entier).
    # L'audit_log côté DB suffit à tracer.

    if not changes:
        return None

    log.info(f"  {item['id']} : {', '.join(changes)}")
    return row


def run(args):
    con = sqlite3.connect(str(config.CATALOG_DB))
    con.row_factory = sqlite3.Row

    enrichments = con.execute("""
        SELECT e.id AS enr_id, e.raw_json, e.confidence, i.*
          FROM enrichments e
          JOIN items i ON i.id = e.item_id
         WHERE e.applied = 0
         ORDER BY e.created_at
    """).fetchall()
    log.info(f"{len(enrichments)} enrichissements en attente")

    rows = []
    enr_ids_applied = []
    for e in enrichments:
        enrich = json.loads(e["raw_json"])
        row = build_row(e, enrich, args.min_confidence)
        if row:
            rows.append(row)
            enr_ids_applied.append(e["enr_id"])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    log.info(f"écrit : {out} ({len(rows)} lignes, sur {len(enrichments)} enrichissements)")
    log.info(f"→ applique ensuite avec :  python /chemin/vers/import_csv.py {out}")

    if args.mark_applied:
        for enr_id in enr_ids_applied:
            con.execute("UPDATE enrichments SET applied=1, applied_at=datetime('now') WHERE id=?",
                        (enr_id,))
        con.commit()
        log.info(f"applied=1 sur {len(enr_ids_applied)} enrichissements")

    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=config.DATA_DIR / "enrichments.csv")
    ap.add_argument("--min-confidence", type=float, default=0.5,
                    help="seuil minimum (default 0.5)")
    ap.add_argument("--mark-applied", action="store_true",
                    help="marquer applied=1 dans enrichments (à faire APRÈS l'import effectif)")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
