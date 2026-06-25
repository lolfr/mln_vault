#!/usr/bin/env python3
"""categorize_tags.py — classe chaque tag dans 1 des N catégories via Ollama.
Approche par INDEX (tableau ordonné, zéro matching de clé) + garde-fou d'alignement
(re-découpe récursive si la longueur ne correspond pas). Idempotent (WHERE category IS NULL).
Catégories pilotées par vault.toml (tags.categories). stdlib only."""
import json, os, sqlite3, sys, urllib.request
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import vault_config  # noqa: E402

_CFG = vault_config.load_config()

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
ROOT = os.environ.get("ARCHIVE_ROOT", _REPO_ROOT)
DB = ROOT + "/metadata/catalog.sqlite"
OLLAMA = "http://127.0.0.1:11434/api/generate"
MODEL = os.environ.get("CAT_MODEL", "qwen2.5:14b")
BATCH = 25

CATEGORIES = _CFG.tag_categories
_LUT = {c.lower(): c for c in CATEGORIES}

FEWSHOT = ("Examples: 'logo' -> Products ; 'child' -> People ; 'green' -> Colors ; "
           "'dog' -> Animals ; 'mountain' -> Places & Landscapes ; "
           "'icon' -> Interface & Software ; 'creativity' -> Concepts & Themes .")

def coerce_category(raw):
    return _LUT.get((raw or "").strip().lower(), CATEGORIES[-1] if CATEGORIES else "Other")

def _ask(batch):
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(batch))
    prompt = (
        f"You classify tags from {_CFG.collection_description} into categories.\n"
        "Allowed categories (use EXACTLY these labels):\n- "
        + "\n- ".join(CATEGORIES) + "\n\n" + FEWSHOT + "\n\n"
        f"Here are {len(batch)} numbered tags:\n{numbered}\n\n"
        'Reply ONLY with a JSON {"categories": [...]} containing EXACTLY '
        f"{len(batch)} categories, in the SAME ORDER as the tags. "
        "One category per tag, taken from the list."
    )
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                       "format": "json", "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())["response"]

def parse_batch(resp, batch):
    """Maps by INDEX. Returns dict tag->category (None if length mismatch)."""
    try:
        cats = json.loads(resp).get("categories", [])
    except Exception:
        cats = []
    if len(cats) != len(batch):
        return None  # signal de désalignement
    return {batch[i]: coerce_category(cats[i]) for i in range(len(batch))}

def categorize(batch):
    """Guard: if length doesn't match, split in two (down to 1 = always aligned)."""
    out = parse_batch(_ask(batch), batch)
    if out is not None:
        return out
    if len(batch) == 1:
        return {batch[0]: CATEGORIES[-1] if CATEGORIES else "Other"}
    mid = len(batch) // 2
    res = {}
    res.update(categorize(batch[:mid]))
    res.update(categorize(batch[mid:]))
    return res

def main():
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT id, label FROM tags WHERE category IS NULL").fetchall()
    print(f"à classer : {len(rows)} (modèle {MODEL}, batch {BATCH})", flush=True)
    done = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i+BATCH]
        labels = [r[1] for r in chunk]
        try:
            mapping = categorize(labels)
        except Exception as e:
            print("  batch KO:", e, flush=True); continue
        for tid, label in chunk:
            con.execute("UPDATE tags SET category=? WHERE id=?", (mapping[label], tid))
        con.commit(); done += len(chunk)
        print(f"  {done}/{len(rows)}", flush=True)
    by_cat = con.execute("SELECT category, COUNT(*) FROM tags GROUP BY category ORDER BY 2 DESC").fetchall()
    print("récap :", dict(by_cat), flush=True)
    con.close()

if __name__ == "__main__":
    sys.exit(main())
