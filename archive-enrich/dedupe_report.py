#!/usr/bin/env python3
"""dedupe_report.py — détecte les vidéos en double (titre normalisé + durée), LECTURE SEULE.
Écrit data/dedupe_report.csv. N'écrit RIEN dans le catalog."""
import csv, os, re, sqlite3, sys
ROOT = os.environ.get("ARCHIVE_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = ROOT + "/metadata/catalog.sqlite"
OUT = os.path.join(os.path.dirname(__file__), "data", "dedupe_report.csv")

_FMT = re.compile(r"\.f\d{2,4}$")
_YT = re.compile(r"\s+(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{10,11}$")

def norm_title(title):
    t = (title or "").strip()
    t = _FMT.sub("", t)
    t = _YT.sub("", t)
    return t.strip().lower()

def has_suffix(title):
    return norm_title(title) != (title or "").strip().lower()

def pick_survivor(items):
    return sorted(items, key=lambda r: (-(r["file_size_bytes"] or 0), has_suffix(r["title"]), r["id"]))[0]

def group_videos(rows):
    buckets = {}
    for r in rows:
        if r.get("item_type") != "video" or r.get("duration_seconds") is None:
            continue
        key = (norm_title(r["title"]), round(r["duration_seconds"], 1))
        buckets.setdefault(key, []).append(r)
    return [g for g in buckets.values() if len(g) > 1]

def main():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT id, title, item_type, duration_seconds, file_size_bytes FROM items WHERE item_type='video'")]
    groups = group_videos(rows)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n_remove = 0
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "role", "id", "title", "duration_s", "size_bytes"])
        for gi, g in enumerate(groups):
            surv = pick_survivor(g)
            for r in g:
                role = "KEEP" if r["id"] == surv["id"] else "REMOVE"
                if role == "REMOVE": n_remove += 1
                w.writerow([gi, role, r["id"], r["title"], r["duration_seconds"], r["file_size_bytes"]])
    print(f"groupes doublons : {len(groups)} | copies a blocklister : {n_remove} | rapport : {OUT}", flush=True)
    con.close()

if __name__ == "__main__":
    sys.exit(main())
