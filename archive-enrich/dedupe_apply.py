#!/usr/bin/env python3
"""dedupe_apply.py — fusionne les métadonnées vers le survivant puis blocklist les copies.
Idempotent, réversible (DELETE FROM blocklist WHERE reason LIKE 'dedupe:%'). À lancer APRÈS
validation du rapport (data/dedupe_report.csv)."""
import csv, os, re, sqlite3, sys
from dedupe_report import norm_title, has_suffix, DB, OUT

def merge_metadata(con, survivor, removed):
    con.execute("INSERT OR IGNORE INTO item_tags(item_id,tag_id) "
                "SELECT ?, tag_id FROM item_tags WHERE item_id=?", (survivor, removed))
    con.execute("INSERT OR IGNORE INTO transcripts(item_id,lang,text,segments_json,model,duration_s,word_count) "
                "SELECT ?,lang,text,segments_json,model,duration_s,word_count FROM transcripts WHERE item_id=?",
                (survivor, removed))
    con.execute("INSERT INTO enrichments(item_id,model,prompt_version,raw_json,confidence,applied,applied_at,created_at) "
                "SELECT ?,model,prompt_version,raw_json,confidence,applied,applied_at,created_at FROM enrichments e "
                "WHERE e.item_id=? AND NOT EXISTS (SELECT 1 FROM enrichments s WHERE s.item_id=? AND s.model=e.model)",
                (survivor, removed, survivor))

def apply_group(con, survivor, removed_ids, *, blocklist=True):
    for rid in removed_ids:
        merge_metadata(con, survivor, rid)
        if blocklist:
            con.execute("INSERT INTO blocklist(item_id,reason) SELECT ?,? "
                        "WHERE NOT EXISTS (SELECT 1 FROM blocklist WHERE item_id=?)",
                        (rid, f"dedupe: kept {survivor}", rid))
    row = con.execute("SELECT title FROM items WHERE id=?", (survivor,)).fetchone()
    if row and has_suffix(row[0]):
        clean = re.sub(r"\s+(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{10,11}$", "",
                       re.sub(r"\.f\d{2,4}$", "", (row[0] or "").strip())).strip()
        con.execute("UPDATE items SET title=? WHERE id=?", (clean, survivor))
    con.commit()

def main():
    con = sqlite3.connect(DB)
    groups = {}
    with open(OUT) as f:
        for r in csv.DictReader(f):
            groups.setdefault(r["group"], {"keep": None, "remove": []})
            if r["role"] == "KEEP": groups[r["group"]]["keep"] = r["id"]
            else: groups[r["group"]]["remove"].append(r["id"])
    n = 0
    for g in groups.values():
        if g["keep"] and g["remove"]:
            apply_group(con, g["keep"], g["remove"]); n += len(g["remove"])
    print(f"applique : {n} copies blocklistees+fusionnees", flush=True)
    con.close()

if __name__ == "__main__":
    sys.exit(main())
