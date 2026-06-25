#!/usr/bin/env python3
"""Ingest a source tree → catalog.

Pipeline per file:
  1. hash (SHA-256)
  2. skip if checksum already in DB  (idempotent)
  3. classify from path (section, item_type, year, product, campaign)
  4. generate item_id + slug
  5. copy to masters/<section>/<rel-tree>/<id>__<slug><ext>
  6. generate thumbnail + preview
  7. insert into DB
  8. audit log

Usage:
  python ingest.py                    # ingest everything
  python ingest.py --limit 20         # first 20 files (useful for a dry run)
  python ingest.py --section hardware # only one top category
  python ingest.py --skip-videos      # defer heavy video processing
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import common  # noqa: E402
import generate_derivatives as gd  # noqa: E402


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(common.DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _next_sequence(con: sqlite3.Connection, section: str, year: int | None) -> int:
    yr = str(year) if year else "0000"
    prefix = f"{yr}-{section[:3]}-"
    row = con.execute(
        "SELECT id FROM items WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    if not row:
        return 1
    return int(row["id"].split("-")[-1]) + 1


def _iter_sources(root: Path, section_filter: str | None = None):
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if common.should_skip(path):
            continue
        rel = path.relative_to(root)
        if section_filter:
            top = rel.parts[0] if rel.parts else ""
            section_code = common._CFG.ingest_sections.get(top, ("other", "other"))[0]
            if section_code != section_filter:
                continue
        yield path, rel


def _existing_by_checksum(con: sqlite3.Connection, checksum: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT id, slug FROM items WHERE checksum_sha256 = ?", (checksum,)
    ).fetchone()


def _format_title(rel: Path) -> str:
    stem = rel.stem
    stem = stem.replace("_", " ").replace("-", " ").strip()
    return stem or rel.name


def ingest_one(con: sqlite3.Connection, src: Path, rel: Path, *, skip_videos: bool) -> str:
    ext = src.suffix.lower()
    if skip_videos and ext in common.VIDEO_EXTS:
        return "skipped_video"
    # Only ingest files we have a media handler for.
    if ext not in (common.IMAGE_EXTS | common.VECTOR_EXTS | common.VIDEO_EXTS):
        return "skipped_nonmedia"

    checksum = common.sha256_file(src)
    existing = _existing_by_checksum(con, checksum)
    if existing:
        return f"dup:{existing['id']}"

    meta = common.classify_path(rel)
    section = meta["section"]
    seq = _next_sequence(con, section, meta["year"])
    item_id = common.make_item_id(section, meta["year"], seq)
    title = _format_title(rel)
    slug_base = common.slugify(f"{meta['year'] or ''} {title}".strip())
    slug = f"{slug_base}-{common.short_id(checksum)}"

    # Copy to masters preserving the source structure under masters/<section>/
    dest_rel = Path(section) / rel
    dest_rel = dest_rel.with_name(f"{item_id}__{common.slugify(src.stem)}{src.suffix.lower()}")
    dest = common.MASTERS_ROOT / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(src, dest)

    # Derivatives
    deriv = {}
    try:
        deriv = gd.derive(dest, item_id)
    except Exception as exc:  # noqa: BLE001
        deriv = {"error": str(exc)}

    size = dest.stat().st_size
    con.execute(
        """INSERT INTO items (
             id, slug, title, item_type, product, campaign, year, circa_start, circa_end,
             source_type, publication_level, rights_status,
             digital_format, file_path_master, file_path_preview, file_path_thumb,
             file_size_bytes, width_px, height_px, duration_seconds, checksum_sha256,
             notes_internal
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            item_id, slug, title, meta["item_type"], meta["product"], meta["campaign"],
            meta["year"], meta["circa_start"], meta["circa_end"],
            "personal_archive", "private", "likely_copyrighted",
            common.guess_digital_format(src),
            str(dest.relative_to(common.ARCHIVE_ROOT)),
            deriv.get("preview"),
            deriv.get("thumb"),
            size,
            deriv.get("width_px"),
            deriv.get("height_px"),
            deriv.get("duration_seconds"),
            checksum,
            json.dumps({"source_rel": str(rel)}),
        ),
    )
    con.execute(
        "INSERT INTO sources (item_id, kind, reference) VALUES (?, ?, ?)",
        (item_id, "personal_archive", f"{common.SOURCE_LABEL}:{rel}"),
    )
    con.execute(
        "INSERT INTO audit_log (item_id, action, actor, payload) VALUES (?, ?, ?, ?)",
        (item_id, "ingest", "ingest.py", json.dumps({"src": str(rel), "checksum": checksum})),
    )
    con.commit()
    return f"new:{item_id}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--section", choices=list(set(v[0] for v in common._CFG.ingest_sections.values())))
    ap.add_argument("--skip-videos", action="store_true")
    ap.add_argument("--progress-every", type=int, default=25)
    args = ap.parse_args()

    if not common.SOURCE_ROOT.exists():
        print(f"FATAL: {common.SOURCE_ROOT} not mounted", file=sys.stderr)
        return 2

    t0 = time.time()
    con = _connect()
    counts = {"new": 0, "dup": 0, "err": 0, "skip": 0}
    seen = 0
    for src, rel in _iter_sources(common.SOURCE_ROOT, args.section):
        seen += 1
        try:
            res = ingest_one(con, src, rel, skip_videos=args.skip_videos)
            if res.startswith("new"):
                counts["new"] += 1
            elif res.startswith("dup"):
                counts["dup"] += 1
            elif res.startswith("skipped"):
                counts["skip"] += 1
        except Exception as exc:  # noqa: BLE001
            counts["err"] += 1
            print(f"ERR {rel}: {exc}", file=sys.stderr)

        if seen % args.progress_every == 0:
            dt = time.time() - t0
            rate = seen / dt if dt else 0
            print(f"[{seen:5d}] new={counts['new']} dup={counts['dup']} "
                  f"skip={counts['skip']} err={counts['err']} ({rate:.1f}/s)",
                  flush=True)

        if args.limit and seen >= args.limit:
            break

    con.close()
    print(f"done in {time.time()-t0:.0f}s — {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
