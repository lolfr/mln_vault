#!/usr/bin/env python3
# status_json.py — état JSON de l'enrichissement Vault, pour le widget Übersicht
# (mln-homelab). Lecture seule de la DB pour ne pas gêner le run en cours.
# Calcule aussi vitesse (items/min, wall-clock), temps moyen/item et ETA.
# 2026-06-22 : ajout transcription vidéos (Whisper hub) + tags FR.
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime

DB = os.environ.get("ARCHIVE_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + "/metadata/catalog.sqlite"
TOTAL = 5745
LOG = "/tmp/enrich_hub.log"

# "2026-06-20 22:09:10,558 [INFO] 2017-vid-000015 ok 13.6s [conf=0.7, tags=6]"
OK_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[.,]\d+\s+\[INFO\]\s+\S+\s+ok\s+(\d+(?:\.\d+)?)s"
)


def _proc_running(pattern):
    return subprocess.call(
        ["pgrep", "-f", pattern],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ) == 0


def _done():
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=3)
        n = con.execute(
            "SELECT count(*) FROM enrichments WHERE model LIKE 'hub:%lite'"
        ).fetchone()[0]
        con.close()
        return int(n)
    except Exception:
        return None


def _transcribe_tags():
    """Transcription vidéos (Whisper hub) + tags FR — lecture seule."""
    out = {"transcribe": None, "tags": None}
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=3)
        vtot = con.execute("SELECT count(*) FROM items WHERE item_type='video'").fetchone()[0]
        vdone = con.execute("SELECT count(*) FROM transcripts").fetchone()[0]
        tcount = con.execute("SELECT count(*) FROM tags").fetchone()[0]
        titems = con.execute("SELECT count(DISTINCT item_id) FROM item_tags").fetchone()[0]
        tlinks = con.execute("SELECT count(*) FROM item_tags").fetchone()[0]
        con.close()
        out["transcribe"] = {
            "done": vdone, "total": vtot, "remaining": max(0, vtot - vdone),
            "pct": round(vdone / vtot * 100, 1) if vtot else 0,
            "running": _proc_running("hub_transcribe.py"),
        }
        out["tags"] = {
            "count": tcount, "items_tagged": titems, "links": tlinks,
            "running": _proc_running("translate_tags.py"),
        }
    except Exception:
        pass
    return out


def _read_log():
    """Renvoie (lines, start) où start = index du dernier démarrage de run
    ('manifest :'), car le log est cumulatif (`>>` sur plusieurs runs)."""
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return [], 0
    start = 0
    for i in range(len(lines) - 1, -1, -1):
        if "manifest :" in lines[i]:
            start = i
            break
    return lines, start


def _errors_and_last(lines, start):
    errors = sum(1 for ln in lines[start:] if "KO :" in ln and "403" not in ln)
    last = ""
    for ln in reversed(lines):
        s = ln.strip()
        if s:
            last = s
            break
    return errors, last


def _telemetry(run_lines, remaining):
    pts = []
    for ln in run_lines:
        m = OK_RE.match(ln)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        pts.append((ts, float(m.group(2))))

    if not pts:
        return {"speed_per_min": None, "avg_sec": None, "eta_seconds": None}
    if len(pts) < 2:
        return {"speed_per_min": None, "avg_sec": round(pts[0][1], 1), "eta_seconds": None}

    recent = pts[-40:]
    span = (recent[-1][0] - recent[0][0]).total_seconds()
    speed = ((len(recent) - 1) / span * 60) if span > 0 else None
    avg_sec = sum(d for _, d in recent) / len(recent)
    eta = (remaining / speed * 60) if (speed and remaining is not None) else None
    return {
        "speed_per_min": round(speed, 2) if speed else None,
        "avg_sec": round(avg_sec, 1),
        "eta_seconds": int(eta) if eta else None,
    }


def main():
    done = _done()
    lines, start = _read_log()
    errors, last = _errors_and_last(lines, start)
    remaining = (TOTAL - done) if done is not None else None
    tele = _telemetry(lines[start:], remaining)
    tt = _transcribe_tags()
    print(json.dumps({
        "done": done,
        "total": TOTAL,
        "remaining": remaining,
        "pct": round(done / TOTAL * 100, 1) if done is not None else None,
        "errors": errors,
        "running": _proc_running("enrich_hub.py"),
        "last": last[:180],
        "speed_per_min": tele["speed_per_min"],
        "avg_sec": tele["avg_sec"],
        "eta_seconds": tele["eta_seconds"],
        "transcribe": tt["transcribe"],
        "tags": tt["tags"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
