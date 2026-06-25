#!/usr/bin/env python3
# version: 0.2.0
"""
archive-enrich/src/build_review.py

Génère data/enrich_review.html — page statique de validation des enrichissements
en attente (applied=0). Permet à Laurent de voir côte à côte :
  - la preview existante
  - le titre actuel vs le titre proposé
  - les valeurs proposées vs les valeurs actuelles
  - la transcription si présente
  - le JSON brut LLM (audit)

Charte alignée sur l'interface archive (sable / bleu nuit / orange / turquoise).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


CSS = """
:root {
  --bg: #f4ede0;        /* sable Archive */
  --ink: #142136;       /* bleu nuit */
  --accent: #c8662c;    /* orange */
  --accent2: #2e8a7a;   /* turquoise */
  --gold:   #c9a13b;
  --muted:  #6a6655;
  --card:   #fffaf0;
  --line:   #d8cfb8;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  background: var(--bg); color: var(--ink); margin: 0;
  padding: 32px 40px; line-height: 1.5;
}
h1 { font-weight: 800; letter-spacing: -0.5px; margin: 0 0 4px; font-size: 28px; }
.subtitle { color: var(--muted); margin-bottom: 28px; font-size: 14px; }

.stats { display: flex; gap: 12px; margin-bottom: 32px; flex-wrap: wrap; }
.stat {
  background: var(--card); border: 1.5px solid var(--ink);
  padding: 10px 18px; border-radius: 2px; min-width: 120px;
}
.stat .n { font-size: 24px; font-weight: 800; }
.stat .l { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: var(--muted); margin-top: 2px; }

.item {
  background: var(--card); border: 1.5px solid var(--ink);
  border-radius: 2px; padding: 24px; margin-bottom: 24px;
  position: relative;
}
.item::before {
  content: ""; position: absolute; top: -1px; left: -1px;
  width: 60px; height: 4px; background: var(--accent);
}

.item-head {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 16px; margin-bottom: 12px;
}
.item-id {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 12px; color: var(--muted); letter-spacing: 0.5px;
}
.item h2 { margin: 0; font-size: 18px; font-weight: 800; }

.grid {
  display: grid; grid-template-columns: 320px 1fr; gap: 24px;
  margin-top: 12px;
}
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }

.preview {
  border: 1.5px solid var(--ink); padding: 8px; background: white;
}
.preview img { width: 100%; height: auto; display: block; }
.preview .meta {
  font-size: 11px; color: var(--muted); margin-top: 6px;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
}

.diff dl { display: grid; grid-template-columns: 130px 1fr; gap: 6px 14px; margin: 0; font-size: 13px; }
.diff dt {
  color: var(--muted); text-transform: uppercase;
  font-size: 10px; letter-spacing: 1.5px; font-weight: 700;
  align-self: center;
}
.diff dd { margin: 0; }
.diff .new   { background: rgba(46,138,122,0.12); padding: 2px 6px; border-left: 3px solid var(--accent2); }
.diff .keep  { color: var(--muted); }
.diff .replace { background: rgba(200,102,44,0.12); padding: 2px 6px; border-left: 3px solid var(--accent); }
.diff .replace .old { color: var(--muted); text-decoration: line-through; font-size: 11px; display: block; }

.tag {
  display: inline-block; background: var(--accent2); color: white;
  padding: 2px 8px; border-radius: 2px; font-size: 11px;
  margin: 2px 2px 2px 0; font-weight: 500;
}

.conf {
  display: inline-block; padding: 2px 10px; border-radius: 2px;
  font-size: 11px; font-weight: 700; color: white; letter-spacing: 0.5px;
}
.conf.high { background: var(--accent2); }
.conf.med  { background: var(--gold); }
.conf.low  { background: var(--accent); }

details { margin-top: 12px; }
details summary { cursor: pointer; color: var(--muted); font-size: 12px;
                   font-weight: 600; letter-spacing: 0.5px; }
.transcript {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 12px; background: #faf6ec; padding: 14px;
  border-left: 3px solid var(--gold); margin-top: 8px;
  max-height: 240px; overflow-y: auto;
}
pre.raw {
  background: var(--ink); color: #e8ddc7; padding: 14px;
  border-radius: 2px; font-size: 11px; overflow-x: auto;
  margin-top: 8px;
}

.footer {
  margin-top: 40px; padding-top: 16px; border-top: 1.5px solid var(--ink);
  font-size: 12px; color: var(--muted); display: flex; justify-content: space-between;
}
"""


def conf_class(c):
    if c is None: return "low"
    if c >= 0.75: return "high"
    if c >= 0.50: return "med"
    return "low"


def render_field(label, current, proposed, replace_flag=None):
    """Affiche un champ avec sa valeur actuelle et la proposition."""
    current = current or "—"
    proposed = proposed or "—"
    if proposed == "—" or proposed == current:
        cls, content = "keep", escape(str(current))
    elif current == "—" or current is None:
        cls, content = "new", escape(str(proposed))
    elif replace_flag is False:
        cls, content = "keep", escape(str(current))
    else:
        cls = "replace"
        content = f'<span class="old">{escape(str(current))}</span>{escape(str(proposed))}'
    return f'<dt>{escape(label)}</dt><dd class="{cls}">{content}</dd>'


def render_item(item: sqlite3.Row, enrich: dict, transcript: sqlite3.Row | None) -> str:
    title_replace = enrich.get("should_replace_title") and enrich.get("title_inferred")
    fields = []
    fields.append(render_field(
        "Titre",
        item["title"],
        enrich.get("title_inferred"),
        replace_flag=bool(title_replace),
    ))
    fields.append(render_field("Description", item["description"], enrich.get("description")))
    fields.append(render_field("Produit", item["product"], enrich.get("product")))
    fields.append(render_field("Campagne", item["campaign"], enrich.get("campaign")))
    fields.append(render_field("Année", item["year"], enrich.get("year_estimate")))
    fields.append(render_field("Pays", item["country"], enrich.get("country")))
    fields.append(render_field("Langue", item["language"], enrich.get("language")))

    cast = enrich.get("cast") or []
    if cast:
        fields.append(f'<dt>Casting</dt><dd class="new">{escape(", ".join(cast))}</dd>')

    if enrich.get("on_screen_text"):
        fields.append(f'<dt>Texte écran</dt><dd class="new"><em>{escape(enrich["on_screen_text"])}</em></dd>')

    tags = enrich.get("tags") or []
    if tags:
        tag_html = "".join(f'<span class="tag">{escape(t)}</span>' for t in tags)
        fields.append(f'<dt>Tags</dt><dd>{tag_html}</dd>')

    fields.append(f'<dt>Confiance</dt><dd>'
                  f'<span class="conf {conf_class(enrich.get("overall_confidence"))}">'
                  f'{enrich.get("overall_confidence") if enrich.get("overall_confidence") is not None else "?"}'
                  f'</span></dd>')

    if enrich.get("year_evidence"):
        fields.append(f'<dt>Évidence</dt><dd class="keep"><em>{escape(enrich["year_evidence"])}</em></dd>')

    preview_html = ""
    if item["file_path_preview"]:
        preview_abs = config.ARCHIVE_ROOT / item["file_path_preview"]
        preview_html = (
            f'<div class="preview">'
            f'<img src="file://{escape(str(preview_abs))}" loading="lazy">'
            f'<div class="meta">{escape(item["file_path_preview"])}<br>'
            f'{item["width_px"] or "?"}×{item["height_px"] or "?"} · '
            f'{item["duration_seconds"] or "—"}s · {escape(item["digital_format"] or "?")}'
            f'</div></div>'
        )

    transcript_html = ""
    if transcript and transcript["text"]:
        transcript_html = f'''
        <details>
          <summary>Transcription ({escape(transcript["lang"] or "?")} · {len(transcript["text"])} chars)</summary>
          <div class="transcript">{escape(transcript["text"])}</div>
        </details>
        '''

    raw_html = f'''
    <details>
      <summary>JSON brut LLM (audit)</summary>
      <pre class="raw">{escape(json.dumps(enrich, indent=2, ensure_ascii=False))}</pre>
    </details>
    '''

    return f'''
    <div class="item">
      <div class="item-head">
        <h2>{escape(enrich.get("title_inferred") or item["title"] or "(sans titre)")}</h2>
        <span class="item-id">{escape(item["id"])}</span>
      </div>
      <div class="grid">
        {preview_html}
        <div class="diff"><dl>{''.join(fields)}</dl></div>
      </div>
      {transcript_html}
      {raw_html}
    </div>
    '''


def run(args):
    con = sqlite3.connect(str(config.CATALOG_DB))
    con.row_factory = sqlite3.Row

    # On prend les enrichissements en attente, jointure sur items
    enrichments = con.execute("""
        SELECT e.id AS enr_id, e.raw_json, e.confidence, e.model, e.created_at,
               i.*
          FROM enrichments e
          JOIN items i ON i.id = e.item_id
         WHERE e.applied = 0
         ORDER BY e.created_at DESC
         LIMIT ?
    """, (args.limit,)).fetchall()

    parts = [
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">',
        '<title>archive-enrich — review</title>',
        f'<style>{CSS}</style></head><body>',
        '<h1>archive-enrich — review</h1>',
        '<p class="subtitle">Enrichissements en attente d\'application sur l\'archive.</p>',
    ]

    n_total = len(enrichments)
    avg_conf = sum((e["confidence"] or 0) for e in enrichments) / n_total if n_total else 0
    n_high = sum(1 for e in enrichments if (e["confidence"] or 0) >= 0.75)
    parts.append(f'''
    <div class="stats">
      <div class="stat"><div class="n">{n_total}</div><div class="l">en attente</div></div>
      <div class="stat"><div class="n">{n_high}</div><div class="l">haute confiance</div></div>
      <div class="stat"><div class="n">{avg_conf:.2f}</div><div class="l">confiance moy.</div></div>
    </div>
    ''')

    for e in enrichments:
        enrich = json.loads(e["raw_json"])
        transcript = con.execute(
            "SELECT * FROM transcripts WHERE item_id = ?", (e["id"],)
        ).fetchone()
        parts.append(render_item(e, enrich, transcript))

    parts.append(f'''
    <div class="footer">
      <span>archive-enrich v0.2.0</span>
      <span>Archive : {escape(str(config.ARCHIVE_ROOT))}</span>
    </div>
    </body></html>''')

    out = Path(args.out)
    out.write_text("".join(parts), encoding="utf-8")
    print(f"écrit : {out} ({n_total} enrichissements)")
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=config.DATA_DIR / "enrich_review.html")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
