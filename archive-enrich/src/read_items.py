#!/usr/bin/env python3
# version: 0.2.0
"""
archive-enrich/src/read_items.py

Lit catalog.sqlite et sélectionne les items éligibles à l'enrichissement LLM.
Produit un manifest JSON consommé par enrich.py.

Critères d'éligibilité (par défaut) :
  - publication_level = 'private'
  - file_path_preview NOT NULL (sinon le VLM n'a rien à voir)
  - au moins un des champs suivants est NULL ou manquant :
      description, product, campaign, OU pas de tags du tout

Usage :
    python read_items.py --limit 30
    python read_items.py --section videos --limit 50
    python read_items.py --years 1984-1990
    python read_items.py --item-id 2019-vid-000087   # ciblage exact
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("read_items")


# Section déduite de l'item_id ('2019-vid-000087' -> 'vid' -> 'videos')
SECTION_FROM_PREFIX = {
    "pho": "photos", "cor": "corporate", "har": "hardware",
    "ret": "retail", "sof": "software", "vid": "videos", "oth": "other",
}


def deduce_section(item_id: str) -> str:
    parts = item_id.split("-")
    if len(parts) >= 2:
        return SECTION_FROM_PREFIX.get(parts[1], "other")
    return "other"


def build_query(args) -> tuple[str, list]:
    where = ["i.publication_level = 'private'"]
    params: list = []

    # Si --all-fields, on ne filtre pas sur les champs manquants
    if not args.all_fields:
        where.append("""
        (i.description IS NULL OR i.description = ''
         OR i.product IS NULL
         OR i.campaign IS NULL
         OR NOT EXISTS (SELECT 1 FROM item_tags it WHERE it.item_id = i.id))
        """)

    # Filtre preview obligatoire (sauf override)
    if not args.allow_no_preview:
        where.append("i.file_path_preview IS NOT NULL")

    if args.section:
        # On filtre par préfixe d'id (plus fiable que parser un chemin)
        section_prefix = args.section[:3]
        where.append("substr(i.id, 6, 3) = ?")
        params.append(section_prefix)

    if args.item_type:
        where.append("i.item_type = ?")
        params.append(args.item_type)

    if args.years:
        try:
            y1, y2 = (int(x) for x in args.years.split("-"))
            where.append("i.year BETWEEN ? AND ?")
            params += [y1, y2]
        except ValueError:
            log.warning(f"--years format attendu : '1984-1990', reçu : {args.years!r}")

    if args.item_id:
        where.append("i.id = ?")
        params.append(args.item_id)

    # Stratégie d'ordre : items avec année connue d'abord (datables = plus de signal)
    order = "i.year IS NULL, i.year DESC, i.id"

    sql = f"""
    SELECT i.id, i.title, i.description, i.item_type, i.product, i.campaign,
           i.year, i.circa_start, i.circa_end, i.language, i.country,
           i.file_path_master, i.file_path_preview, i.file_path_thumb,
           i.width_px, i.height_px, i.duration_seconds, i.digital_format,
           i.notes_internal,
           (SELECT COUNT(*) FROM item_tags it WHERE it.item_id = i.id) AS tag_count,
           (SELECT 1 FROM transcripts t WHERE t.item_id = i.id) AS has_transcript
      FROM items i
     WHERE {' AND '.join(where)}
     ORDER BY {order}
     LIMIT ?
    """
    params.append(args.limit)
    return sql, params


def run(args):
    if not config.CATALOG_DB.exists():
        log.error(f"DB introuvable : {config.CATALOG_DB}")
        log.error("Vérifie ARCHIVE_ROOT ou monte /Volumes/Vault")
        sys.exit(1)

    con = sqlite3.connect(str(config.CATALOG_DB))
    con.row_factory = sqlite3.Row

    # Sanity check : on doit avoir migration 001 si on demande l'info has_transcript
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "transcripts" not in tables:
        log.warning("table 'transcripts' absente — lance d'abord :")
        log.warning(f"  sqlite3 {config.CATALOG_DB} < migrations/001_add_transcripts.sql")
        log.warning("(on continue sans, has_transcript sera toujours None)")

    sql, params = build_query(args)
    log.debug(f"SQL: {sql}\nparams: {params}")
    rows = con.execute(sql, params).fetchall() if "transcripts" in tables else con.execute(
        sql.replace(
            "(SELECT 1 FROM transcripts t WHERE t.item_id = i.id)",
            "NULL"
        ),
        params,
    ).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        d["section"] = deduce_section(d["id"])
        # Chemins absolus pour les outils suivants
        if d["file_path_preview"]:
            d["preview_abs"] = str(config.ARCHIVE_ROOT / d["file_path_preview"])
        if d["file_path_master"]:
            d["master_abs"] = str(config.ARCHIVE_ROOT / d["file_path_master"])
        items.append(d)

    out_path = config.DATA_DIR / "manifest.json"
    out_path.write_text(json.dumps({
        "selected": len(items),
        "criteria": vars(args),
        "items": items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(f"sélectionnés : {len(items)} items → {out_path}")
    # Petit résumé visuel
    by_type = {}
    n_videos_no_transcript = 0
    for it in items:
        by_type[it["item_type"]] = by_type.get(it["item_type"], 0) + 1
        if it["item_type"] == "video" and not it.get("has_transcript"):
            n_videos_no_transcript += 1
    log.info(f"  par type : {by_type}")
    if n_videos_no_transcript:
        log.info(f"  → {n_videos_no_transcript} vidéos sans transcription (lance transcribe.py)")

    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30, help="nombre max d'items (pilote : 30)")
    ap.add_argument("--section", choices=list(SECTION_FROM_PREFIX.values()))
    ap.add_argument("--item-type", help="ad, brochure, visual, scan, video, press, other")
    ap.add_argument("--years", help="plage '1984-1990'")
    ap.add_argument("--item-id", help="cible un item précis")
    ap.add_argument("--all-fields", action="store_true",
                    help="ignore le filtre 'champs manquants' (re-traiter du déjà-enrichi)")
    ap.add_argument("--allow-no-preview", action="store_true",
                    help="autorise items sans preview (rare, casse l'enrichissement vision)")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
