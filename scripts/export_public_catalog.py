#!/usr/bin/env python3
"""Export a static public catalog (JSON feed + CSV dump + minimal HTML index).

Only items with publication_level='public' are exported.
Masters are NEVER referenced by URL in the public catalog.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402


PUBLIC_FIELDS = [
    "id", "slug", "title", "description", "item_type", "product", "campaign",
    "brand", "year", "circa_start", "circa_end", "language", "country",
    "digital_format", "file_path_preview", "file_path_thumb",
    "width_px", "height_px", "duration_seconds",
]


def main() -> int:
    out_dir = common.ARCHIVE_ROOT / "exports" / "public"
    out_dir.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(common.DB_PATH)
    con.row_factory = sqlite3.Row

    cols = ", ".join(PUBLIC_FIELDS)
    rows = [dict(r) for r in con.execute(
        f"SELECT {cols} FROM items WHERE publication_level = 'public' "
        f"AND id NOT IN (SELECT item_id FROM blocklist WHERE item_id IS NOT NULL)"
    )]

    # JSON feed
    (out_dir / "catalog.json").write_text(
        json.dumps({"items": rows, "count": len(rows)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # CSV dump
    with (out_dir / "catalog.csv").open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=PUBLIC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    # Minimal HTML index (so a static host can serve it)
    html = [
        '<!doctype html><meta charset="utf-8"><title>Archive — public catalog</title>',
        '<link rel="stylesheet" href="../../app/static/style.css">',
        '<body><h1>Archive — public catalog</h1>',
        f'<p>{len(rows)} items.</p><ul class="grid">',
    ]
    for r in rows:
        thumb = r.get("file_path_thumb") or ""
        html.append(
            f'<li><a href="item-{r["slug"]}.html">'
            f'<img src="../../{thumb}" alt=""><span>{r["title"]}</span></a></li>'
        )
    html.append("</ul></body>")
    (out_dir / "index.html").write_text("\n".join(html), encoding="utf-8")

    con.close()
    print(f"exported {len(rows)} public items → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
