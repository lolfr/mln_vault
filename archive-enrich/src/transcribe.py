#!/usr/bin/env python3
# version: 0.2.0
"""
archive-enrich/src/transcribe.py

Transcrit les vidéos du manifest qui n'ont pas encore de transcription.
Écrit dans catalog.sqlite, table `transcripts` (migration 001 requise).

Deux backends auto-détectés :
  1. whisper.cpp (préféré sur Mac Apple Silicon)
  2. openai-whisper Python (fallback)

Usage :
    python transcribe.py --manifest data/manifest.json --model medium
    python transcribe.py --manifest data/manifest.json --binary $(which whisper-cli) \\
                          --model-path ~/models/ggml-medium.bin
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("transcribe")


def extract_audio(video_path: Path, out_wav: Path):
    """Pipe audio en WAV 16kHz mono — format universel Whisper."""
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(video_path),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
         str(out_wav)],
        check=True, timeout=600,
    )


def transcribe_with_whisper_cpp(wav: Path, binary: str, model_path: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpd:
        prefix = Path(tmpd) / "out"
        subprocess.run(
            [binary, "-m", model_path, "-f", str(wav),
             "-of", str(prefix), "-oj", "-l", "auto"],
            check=True, capture_output=True, text=True, timeout=1800,
        )
        with open(f"{prefix}.json") as f:
            data = json.load(f)
        segments, full = [], []
        for seg in data.get("transcription", []):
            text = seg.get("text", "").strip()
            full.append(text)
            segments.append({
                "from": seg.get("timestamps", {}).get("from"),
                "to":   seg.get("timestamps", {}).get("to"),
                "text": text,
            })
        return {
            "lang": data.get("result", {}).get("language"),
            "text": " ".join(full).strip(),
            "segments": segments,
        }


def transcribe_with_openai_whisper(wav: Path, model: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpd:
        subprocess.run(
            ["whisper", str(wav), "--model", model, "--output_format", "json",
             "--output_dir", tmpd, "--verbose", "False"],
            check=True, capture_output=True, text=True, timeout=1800,
        )
        out_json = next(Path(tmpd).glob("*.json"))
        with open(out_json) as f:
            data = json.load(f)
        return {
            "lang": data.get("language"),
            "text": data.get("text", "").strip(),
            "segments": [
                {"from": s.get("start"), "to": s.get("end"), "text": s.get("text", "")}
                for s in data.get("segments", [])
            ],
        }


def has_transcript(con: sqlite3.Connection, item_id: str) -> bool:
    row = con.execute("SELECT 1 FROM transcripts WHERE item_id = ?", (item_id,)).fetchone()
    return row is not None


def insert_transcript(con: sqlite3.Connection, item_id: str, result: dict,
                      model_label: str, duration_proc: float):
    con.execute("""
        INSERT OR REPLACE INTO transcripts
            (item_id, lang, text, segments_json, model, duration_s, word_count, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        item_id, result.get("lang"), result["text"],
        json.dumps(result["segments"], ensure_ascii=False),
        model_label, duration_proc,
        len(result["text"].split()),
    ))
    con.commit()


def run(args):
    if shutil.which("ffmpeg") is None:
        log.error("ffmpeg requis dans le PATH")
        sys.exit(1)

    if args.binary and args.model_path:
        if not Path(args.binary).exists():
            log.error(f"binaire whisper.cpp introuvable : {args.binary}")
            sys.exit(1)
        backend, model_label = "cpp", f"whisper.cpp-{Path(args.model_path).stem}"
    elif shutil.which("whisper"):
        backend, model_label = "openai", f"whisper-{args.model}"
    else:
        log.error("aucun backend Whisper trouvé (openai-whisper OU --binary/--model-path)")
        sys.exit(1)
    log.info(f"backend = {backend} ({model_label})")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    items = [it for it in manifest["items"] if it["item_type"] == "video"]
    log.info(f"manifest : {len(items)} vidéos candidates")

    con = sqlite3.connect(str(config.CATALOG_DB))

    # Sanity check schema
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "transcripts" not in tables:
        log.error("table 'transcripts' absente — lance d'abord la migration 001")
        sys.exit(1)

    n_done = n_skip = n_err = 0
    for it in items:
        if has_transcript(con, it["id"]):
            n_skip += 1
            continue
        src = Path(it["master_abs"])
        if not src.exists():
            log.warning(f"{it['id']} : master introuvable ({src})")
            n_err += 1
            continue

        t0 = time.time()
        log.info(f"{it['id']} : {src.name}")
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                wav_path = Path(tmp_wav.name)
            extract_audio(src, wav_path)

            if backend == "cpp":
                result = transcribe_with_whisper_cpp(wav_path, args.binary, args.model_path)
            else:
                result = transcribe_with_openai_whisper(wav_path, args.model)

            insert_transcript(con, it["id"], result, model_label, time.time() - t0)
            log.info(f"  → {len(result['text'])} chars en {time.time() - t0:.1f}s (lang={result['lang']})")
            n_done += 1
        except subprocess.CalledProcessError as e:
            log.error(f"  KO : {(e.stderr or '')[:300]}")
            n_err += 1
        except Exception as e:
            log.exception(f"  exception : {e}")
            n_err += 1
        finally:
            try: wav_path.unlink()
            except: pass

    con.close()
    log.info(f"fini. done={n_done} skip={n_skip} err={n_err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=config.DATA_DIR / "manifest.json")
    ap.add_argument("--model", default="medium")
    ap.add_argument("--binary", help="chemin whisper-cli (whisper.cpp)")
    ap.add_argument("--model-path", help="chemin ggml-*.bin (whisper.cpp)")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
