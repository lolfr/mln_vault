#!/usr/bin/env python3
"""Idempotent CSV/JSON metadata import.

CSV header (tab or comma separated, UTF-8):
  id, title, description, item_type, product, campaign, year, date_exact,
  language, country, rights_status, publication_level, tags, notes_internal

- Rows without `id` are skipped with a warning.
- `tags` is a pipe-separated list: "retro|print|poster".
- Missing fields leave existing values untouched.

Usage:
  python import_csv.py path/to/file.csv
  python import_csv.py path/to/file.json   # expects a list of objects
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

UPDATABLE = {
    "title", "description", "item_type", "product", "campaign", "year",
    "date_exact", "language", "country", "rights_status", "publication_level",
    "notes_internal",
}


def _upsert_tag(con: sqlite3.Connection, label: str) -> int:
    slug = common.slugify(label)
    con.execute(
        "INSERT OR IGNORE INTO tags (slug, label, kind) VALUES (?, ?, 'free')",
        (slug, label),
    )
    row = con.execute("SELECT id FROM tags WHERE slug = ?", (slug,)).fetchone()
    return row[0]


def _apply(con: sqlite3.Connection, row: dict) -> str:
    item_id = row.get("id", "").strip()
    if not item_id:
        return "skip_no_id"
    existing = con.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone()
    if not existing:
        return f"skip_missing:{item_id}"

    fields = {k: v for k, v in row.items() if k in UPDATABLE and v not in (None, "")}
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        con.execute(
            f"UPDATE items SET {sets} WHERE id = ?", (*fields.values(), item_id)
        )

    tags = row.get("tags", "")
    if tags:
        labels = [t.strip() for t in tags.split("|") if t.strip()]
        for label in labels:
            tag_id = _upsert_tag(con, label)
            con.execute(
                "INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)",
                (item_id, tag_id),
            )

    con.execute(
        "INSERT INTO audit_log (item_id, action, actor, payload) VALUES (?, ?, ?, ?)",
        (item_id, "edit", "import_csv", json.dumps(fields)),
    )
    con.commit()
    return f"ok:{item_id}"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: import_csv.py <file.csv|file.json>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    con = sqlite3.connect(common.DB_PATH)

    if src.suffix.lower() == ".json":
        rows = json.loads(src.read_text(encoding="utf-8"))
    else:
        with src.open(encoding="utf-8", newline="") as fp:
            dialect = csv.Sniffer().sniff(fp.read(2048))
            fp.seek(0)
            rows = list(csv.DictReader(fp, dialect=dialect))

    stats = {"ok": 0, "skip": 0}
    for row in rows:
        res = _apply(con, row)
        if res.startswith("ok"):
            stats["ok"] += 1
        else:
            stats["skip"] += 1
            print(res, file=sys.stderr)
    print(f"imported: {stats}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
