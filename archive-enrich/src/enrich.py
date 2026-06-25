#!/usr/bin/env python3
# version: 0.2.0
"""
archive-enrich/src/enrich.py

Pour chaque item du manifest, appelle Claude Haiku avec :
  - la preview (file_path_preview, déjà générée par ton generate_derivatives.py)
  - la transcription (table `transcripts`, si présente)
  - le contexte connu (year/product/campaign s'ils existent)

Le LLM produit un JSON conforme au schéma de enrich prompt.
Le JSON brut est stocké dans la table `enrichments` (applied=0, en attente review).

Usage :
    export ANTHROPIC_API_KEY=sk-ant-...
    python enrich.py --manifest data/manifest.json
    python enrich.py --manifest data/manifest.json --dry-run
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "prompts"))

import config  # noqa: E402
from enrich_prompt import SYSTEM_ENRICH, build_user_message  # noqa: E402

try:
    from anthropic import Anthropic
except ImportError:
    print("ERREUR : pip install anthropic", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("enrich")


def parse_json_response(text: str) -> dict:
    """Parse JSON robuste : fences markdown tolérés, premier {…} extrait."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError(f"pas de JSON : {text[:200]}")
    return json.loads(text[s:e + 1])


def get_transcript(con: sqlite3.Connection, item_id: str) -> tuple[Optional[str], Optional[str]]:
    row = con.execute("SELECT text, lang FROM transcripts WHERE item_id = ?", (item_id,)).fetchone()
    return (row[0], row[1]) if row else (None, None)


def already_enriched(con: sqlite3.Connection, item_id: str, prompt_version: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM enrichments WHERE item_id=? AND prompt_version=? AND applied=0",
        (item_id, prompt_version),
    ).fetchone()
    return row is not None


def call_llm(client: Anthropic, model: str, system: str, user: str,
             preview_path: Optional[Path]) -> dict:
    content = []
    if preview_path and preview_path.exists():
        img_b64 = base64.standard_b64encode(preview_path.read_bytes()).decode("ascii")
        # On déduit le media_type de l'extension
        ext = preview_path.suffix.lower()
        media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": media_type, "data": img_b64
        }})
    content.append({"type": "text", "text": user})

    resp = client.messages.create(
        model=model,
        max_tokens=config.MAX_TOKENS_ENRICH,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    return parse_json_response(resp.content[0].text)


def run(args):
    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        log.error("ANTHROPIC_API_KEY non définie")
        sys.exit(1)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    items = manifest["items"]
    log.info(f"manifest : {len(items)} items à enrichir")

    con = sqlite3.connect(str(config.CATALOG_DB))
    con.row_factory = sqlite3.Row
    # Sanity
    if "enrichments" not in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        log.error("table 'enrichments' absente — lance migration 001 d'abord")
        sys.exit(1)

    client = None if args.dry_run else Anthropic()

    n_ok = n_skip = n_err = 0
    for it in items:
        item_id = it["id"]
        if already_enriched(con, item_id, config.PROMPT_VERSION) and not args.force:
            log.info(f"{item_id} : déjà enrichi (en attente review) — skip")
            n_skip += 1
            continue

        # Récupération transcript
        t_text, t_lang = get_transcript(con, item_id)

        title_is_raw = config.is_raw_filename_title(it.get("title"))

        user_msg = build_user_message(
            item=it,
            transcript_text=t_text,
            transcript_lang=t_lang,
            allowed_products=config.ALLOWED_PRODUCT_LINES,
            allowed_campaigns=config.ALLOWED_CAMPAIGNS,
            allowed_formats=config.ALLOWED_FORMATS,
            title_is_raw=title_is_raw,
        )

        if args.dry_run:
            log.info(f"{item_id} : DRY (titre brut={title_is_raw}, transcript={'oui' if t_text else 'non'})")
            n_skip += 1
            continue

        preview_abs = Path(it["preview_abs"]) if it.get("preview_abs") else None
        t0 = time.time()
        try:
            data = call_llm(client, args.model, SYSTEM_ENRICH, user_msg, preview_abs)
            con.execute("""
                INSERT INTO enrichments (item_id, model, prompt_version, raw_json, confidence, applied)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (item_id, args.model, config.PROMPT_VERSION,
                  json.dumps(data, ensure_ascii=False),
                  data.get("overall_confidence")))
            con.commit()
            log.info(f"{item_id} ok en {time.time()-t0:.1f}s "
                     f"[conf={data.get('overall_confidence')}, "
                     f"title_replace={data.get('should_replace_title')}]")
            n_ok += 1
        except Exception as e:
            log.error(f"{item_id} KO : {e}")
            n_err += 1

    con.close()
    log.info(f"fini. ok={n_ok} skip={n_skip} err={n_err}")
    if n_ok:
        log.info(f"→ next : make review (génère data/enrich_review.html)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=config.DATA_DIR / "manifest.json")
    ap.add_argument("--model", default=config.ANTHROPIC_MODEL)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-enrichit même si déjà fait")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
