#!/usr/bin/env python3
"""translate_tags.py — EN→FR des tags enrichments → tags/item_tags (direct, réversible). Idempotent/reprenable."""
import sqlite3, json, re, urllib.request, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vault_config as _vc; _CFG = _vc.load_config()  # noqa: E402
_ARCHIVE_ROOT = os.environ.get("ARCHIVE_ROOT", str(Path(_vc.__file__).resolve().parent))
DB=_ARCHIVE_ROOT+"/metadata/catalog.sqlite"
OLLAMA="http://127.0.0.1:11434/api/generate"; MODEL="qwen2.5:7b"
def slugify(s): return re.sub(r"[^a-z0-9]+","-",s.lower().strip()).strip("-")[:80] or "tag"
def ollama(prompt):
    body=json.dumps({"model":MODEL,"prompt":prompt,"stream":False,"format":"json","options":{"temperature":0}}).encode()
    req=urllib.request.Request(OLLAMA,data=body,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as r: return json.loads(r.read())["response"]
def tr(tags):
    p=('Traduis ces tags EN->FR pour une archive de médias. Keep brand and product names as-is. '
       'Traduis seulement les termes communs. '
       'Reponds JSON {"t":["fr1",...]} MEME ordre, MEME longueur.\nTags:\n'+json.dumps(tags,ensure_ascii=False))
    try:
        d=json.loads(ollama(p)); fr=d.get("t") or d.get("tags") or []
        if len(fr)==len(tags): return [str(x).strip() or e for x,e in zip(fr,tags)]
    except Exception as e: print("  batch KO:",e,file=sys.stderr,flush=True)
    return None
con=sqlite3.connect(DB, timeout=120); con.row_factory=sqlite3.Row
item_tags={}; uniq={}
for r in con.execute("SELECT item_id, raw_json FROM enrichments"):
    try: tags=json.loads(r["raw_json"]).get("tags") or []
    except Exception: continue
    clean=[t.strip() for t in tags if isinstance(t,str) and t.strip()]
    if not clean: continue
    item_tags.setdefault(r["item_id"],set()).update(clean)
    for t in clean: uniq.setdefault(t, slugify(t))
print(f"items avec tags: {len(item_tags)} · uniques: {len(uniq)}",flush=True)
have={row["slug"] for row in con.execute("SELECT slug FROM tags")}
todo=[(en,sl) for en,sl in uniq.items() if sl not in have]
print(f"a traduire: {len(todo)}",flush=True)
B=60; done=0
for i in range(0,len(todo),B):
    batch=todo[i:i+B]; fr=tr([en for en,_ in batch]) or [en for en,_ in batch]
    for (en,sl),f in zip(batch,fr):
        con.execute("INSERT OR IGNORE INTO tags(slug,label,kind) VALUES(?,?, 'free')",(sl,f or en))
    con.commit(); done+=len(batch)
    if done % 600 < B: print(f"  ...{done}/{len(todo)}",flush=True)
sid={row["slug"]:row["id"] for row in con.execute("SELECT id,slug FROM tags")}
for item,tags in item_tags.items():
    for en in tags:
        tid=sid.get(uniq[en])
        if tid: con.execute("INSERT OR IGNORE INTO item_tags(item_id,tag_id) VALUES(?,?)",(item,tid))
con.commit()
print(f"DONE tags={con.execute('SELECT COUNT(*) FROM tags').fetchone()[0]} item_tags={con.execute('SELECT COUNT(*) FROM item_tags').fetchone()[0]}",flush=True)
