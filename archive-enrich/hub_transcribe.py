#!/usr/bin/env python3
"""hub_transcribe.py — transcription bulk via le hub mlx (whisper-large-v3), reprenable/idempotent.
Saute les vidéos qui ont déjà un transcript. Token lu depuis api_keys.yaml (jamais hardcodé).
Usage: python hub_transcribe.py [LIMIT]   (LIMIT=0 → tout)
"""
import yaml, sqlite3, os, sys, json
import httpx
ROOT=os.environ.get("ARCHIVE_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); DB=ROOT+"/metadata/catalog.sqlite"
HUB="http://127.0.0.1:8765/transcribe"
KEYF="/Users/mini/mln-homelab/mln-inference-hub/config/api_keys.yaml"
limit=int(sys.argv[1]) if len(sys.argv)>1 else 0
tok=next(c["token"] for c in yaml.safe_load(open(KEYF))["clients"] if "transcribe" in c.get("allowed_endpoints",[]))
con=sqlite3.connect(DB, timeout=120); con.row_factory=sqlite3.Row
rows=con.execute("""SELECT id, file_path_master FROM items
  WHERE item_type='video' AND file_path_master IS NOT NULL AND file_path_master<>''
  AND id NOT IN (SELECT item_id FROM transcripts) ORDER BY id""").fetchall()
if limit: rows=rows[:limit]
print(f"à transcrire: {len(rows)}",flush=True)
ok=err=0
for i,r in enumerate(rows,1):
    vid=os.path.join(ROOT, r["file_path_master"])
    if not os.path.exists(vid): print("  manquant:",r["id"],flush=True); err+=1; continue
    try:
        with open(vid,"rb") as f:
            resp=httpx.post(HUB, headers={"X-API-Key":tok}, files={"audio":(os.path.basename(vid),f)}, data={"cache":"false"}, timeout=1800)
        if resp.status_code!=200: print("  HTTP",resp.status_code,r["id"],resp.text[:120],flush=True); err+=1; continue
        d=resp.json(); text=d.get("text") or ""; segs=d.get("segments")
        con.execute("""INSERT OR REPLACE INTO transcripts(item_id,lang,text,segments_json,model,word_count,created_at,updated_at)
            VALUES(?,?,?,?,?,?,datetime('now'),datetime('now'))""",
            (r["id"], d.get("lang"), text, json.dumps(segs,ensure_ascii=False) if segs else None,
             "hub:whisper-large-v3-mlx", len(text.split())))
        con.commit(); ok+=1
        if i%25==0 or limit: print(f"  …{i}/{len(rows)} ok={ok} err={err} (last {r['id']} {d.get('lang')} {len(text.split())}w {d.get('processing_seconds')}s)",flush=True)
    except Exception as e:
        print("  EXC",r["id"],str(e)[:140],flush=True); err+=1
print(f"DONE ok={ok} err={err} · transcripts total={con.execute('SELECT COUNT(*) FROM transcripts').fetchone()[0]}",flush=True)
