#!/usr/bin/env python3
# version: 0.3.0-hub-lite
"""enrich_hub.py — enrichissement 100% LOCAL via le hub (Qwen2.5-VL, GPU mini).
Appelle UNIQUEMENT http://127.0.0.1:8765/vision. AUCUN Claude/router. Budget = 0.
Prompt LITE (schéma compact) : le VLM 7B produit du JSON fiable (le prompt complet 15-champs le faisait dériver).
Usage : HUB_TOKEN=... /opt/homebrew/bin/python3 src/enrich_hub.py --manifest data/manifest.json [--limit N] [--force]
"""
from __future__ import annotations
import argparse, json, logging, os, re, sqlite3, sys, time, uuid, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config  # noqa: E402
import vault_config as _vc; _CFG = _vc.load_config()  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("enrich_hub")

HUB_URL = os.environ.get("HUB_URL", "http://127.0.0.1:8765").rstrip("/")
HUB_TOKEN = os.environ.get("HUB_TOKEN", "")
HUB_MODEL = os.environ.get("HUB_MODEL", "hub:Qwen2.5-VL-7B-4bit-lite")
ATTEMPTS = int(os.environ.get("HUB_ATTEMPTS", "3"))

# ── Garde-fou anti-décrochage du volume Vault (images ET catalog.sqlite y vivent).
# Si le disque APFS externe saute en plein run (Errno 6 "Device not configured"),
# on NE compte PAS les items en no-img/err : on attend le remontage, on rouvre la
# DB, et on re-traite le même item. Évite qu'un blip USB ne sabote des milliers d'items.
VAULT_ROOT = os.environ.get("ARCHIVE_ROOT", str(Path(_vc.__file__).resolve().parent))
VAULT_RETRY_S = int(os.environ.get("VAULT_RETRY_S", "10"))      # intervalle de re-check
VAULT_MAX_WAIT_S = int(os.environ.get("VAULT_MAX_WAIT_S", "1800"))  # 0 = infini


class _VaultGone(Exception):
    """Le volume Vault a décroché — signal interne pour attendre + retry l'item."""

SYSTEM_LITE = (
    f"Tu es archiviste de {_CFG.collection_description}. Tu analyses l'image fournie (preview d'un item "
    "d'archive) et, si présente, sa transcription audio. Tu enrichis sans contredire le contexte connu. "
    "RÈGLE DE SORTIE ABSOLUE : réponds par UN SEUL objet JSON valide, commençant par { et finissant par }. "
    "JAMAIS de tableau au premier niveau, JAMAIS de texte avant/après, JAMAIS de balises markdown. "
    "Si une info n'est pas déterminable : null. Ne jamais inventer."
)


def build_lite(item: dict, transcript: str | None) -> str:
    return (
        f"Item: {item.get('id')} | type: {item.get('item_type')} | "
        f"année connue: {item.get('year') or 'inconnue'} | produit connu: {item.get('product') or 'inconnu'} | "
        f"campagne connue: {item.get('campaign') or 'inconnue'}\n"
        f"Titre actuel: {item.get('title') or '(aucun)'}\n"
        f"Transcription audio: {(transcript or '(aucune)')[:1500]}\n\n"
        "Produis MAINTENANT cet objet JSON (remplis ce que tu peux, null sinon), et RIEN d'autre :\n"
        '{"description": "2-3 phrases factuelles, non promotionnelles", '
        '"tags": ["entre 5 et 10 tags pertinents"], '
        '"year_estimate": entier ou null, '
        '"product": "ligne de produit ou null", '
        '"campaign": "nom de campagne connu ou null", '
        '"format_type": "tv_spot|print|keynote|web|photo|other ou null", '
        '"overall_confidence": nombre entre 0.0 et 1.0}'
    )


def _parse_obj(raw: str):
    t = (raw or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    s, e = t.find("{"), t.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        d = json.loads(t[s:e + 1])
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def _call_raw(preview_path: Path, system: str, user: str) -> str:
    b = "----hub" + uuid.uuid4().hex
    fields = {"user_prompt": user, "system_prompt": system,
              "expect_json": "false", "cache": "false", "priority": "6"}
    body = b""
    for k, v in fields.items():
        body += ("--" + b + "\r\nContent-Disposition: form-data; name=\"" + k + "\"\r\n\r\n" + v + "\r\n").encode("utf-8")
    body += ("--" + b + "\r\nContent-Disposition: form-data; name=\"image\"; filename=\"" + preview_path.name
             + "\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode("utf-8")
    body += preview_path.read_bytes() + b"\r\n" + ("--" + b + "--\r\n").encode("utf-8")
    req = urllib.request.Request(HUB_URL + "/vision/describe", data=body, method="POST",
                                 headers={"Content-Type": "multipart/form-data; boundary=" + b,
                                          "X-API-Key": HUB_TOKEN})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read()).get("raw", "")


def post_vision(preview_path: Path, system: str, user: str) -> dict:
    for _ in range(ATTEMPTS):
        d = _parse_obj(_call_raw(preview_path, system, user))
        if d is not None:
            return d
    raise ValueError("pas d'objet JSON apres %d essais" % ATTEMPTS)


def get_transcript(con, item_id):
    row = con.execute("SELECT text, lang FROM transcripts WHERE item_id=?", (item_id,)).fetchone()
    return (row[0], row[1]) if row else (None, None)


def already(con, item_id, pv, model):
    return con.execute("SELECT 1 FROM enrichments WHERE item_id=? AND prompt_version=? AND model=? AND applied=0",
                       (item_id, pv, model)).fetchone() is not None


def _vault_healthy() -> bool:
    """Vrai si Vault est monté ET réellement lisible (détecte un montage zombie)."""
    try:
        return os.path.ismount(VAULT_ROOT) and bool(os.listdir(VAULT_ROOT) is not None)
    except OSError:
        return False


def _wait_for_vault() -> bool:
    """Bloque tant que Vault n'est pas revenu. Retourne True si une attente a eu
    lieu (→ le caller doit rouvrir la DB, l'ancien handle sqlite est périmé)."""
    if _vault_healthy():
        return False
    waited = 0
    log.warning("⏸️  Vault (%s) indisponible — pause, attente du remontage…", VAULT_ROOT)
    while not _vault_healthy():
        time.sleep(VAULT_RETRY_S)
        waited += VAULT_RETRY_S
        if VAULT_MAX_WAIT_S and waited >= VAULT_MAX_WAIT_S:
            log.error("Vault absent après %ds — abandon (progression sauvée en DB, relançable)", waited)
            raise SystemExit(2)
        if waited % 60 == 0:
            log.warning("Vault toujours absent (%ds)…", waited)
    log.info("▶️  Vault revenu après %ds — reprise", waited)
    return True


def _open_db():
    con = sqlite3.connect(str(config.CATALOG_DB))
    con.row_factory = sqlite3.Row
    return con


def run(args):
    if not HUB_TOKEN:
        log.error("HUB_TOKEN non defini"); sys.exit(1)
    pv = config.PROMPT_VERSION + "-lite"
    items = json.loads(Path(args.manifest).read_text(encoding="utf-8"))["items"]
    if args.limit:
        items = items[:args.limit]
    log.info("manifest : %d items (modele=%s, LOCAL %s)", len(items), HUB_MODEL, HUB_URL)
    _wait_for_vault()  # ne démarre pas tant que Vault n'est pas là
    con = _open_db()
    # Erreurs symptomatiques d'un décrochage disque (lecture image OU catalog.sqlite).
    DISK_ERRORS = (OSError, sqlite3.OperationalError, sqlite3.DatabaseError)
    n_ok = n_skip = n_err = n_noimg = 0
    i = 0
    while i < len(items):
        it = items[i]
        iid = it["id"]
        try:
            if already(con, iid, pv, HUB_MODEL) and not args.force:
                n_skip += 1; i += 1; continue
            preview = Path(it["preview_abs"]) if it.get("preview_abs") else None
            if not preview or not preview.exists():
                # Distinguer une image réellement absente d'un Vault décroché :
                # sinon un blip USB compterait des milliers d'items en faux no-img.
                if not _vault_healthy():
                    raise _VaultGone()
                n_noimg += 1; i += 1; continue
            t_text, _ = get_transcript(con, iid)
            user_msg = build_lite(it, t_text)
            t0 = time.time()
            data = post_vision(preview, SYSTEM_LITE, user_msg)
            con.execute("INSERT INTO enrichments (item_id, model, prompt_version, raw_json, confidence, applied) "
                        "VALUES (?,?,?,?,?,0)",
                        (iid, HUB_MODEL, pv, json.dumps(data, ensure_ascii=False),
                         data.get("overall_confidence")))
            con.commit()
            log.info("%s ok %.1fs [conf=%s, tags=%d]", iid, time.time() - t0,
                     data.get("overall_confidence"), len(data.get("tags") or []))
            n_ok += 1; i += 1
        except _VaultGone:
            if _wait_for_vault():
                con = _open_db()
            continue  # re-traite le MÊME item
        except DISK_ERRORS as e:
            # I/O disque : si Vault a sauté → attente + réouverture DB + retry item.
            # Sinon (volume sain) c'est une vraie erreur → on compte et on avance.
            if not _vault_healthy():
                log.warning("%s I/O disque (%s) — Vault décroché, attente+retry", iid, str(e)[:80])
                if _wait_for_vault():
                    con = _open_db()
                continue
            log.error("%s KO : %s", iid, str(e)[:150]); n_err += 1; i += 1
        except Exception as e:
            log.error("%s KO : %s", iid, str(e)[:150]); n_err += 1; i += 1
    con.close()
    log.info("fini. ok=%d skip=%d no-img=%d err=%d", n_ok, n_skip, n_noimg, n_err)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=config.DATA_DIR / "manifest.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
