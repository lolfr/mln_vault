# Setup guide

## Prerequisites

### Runtime

| Requirement | Notes |
|---|---|
| Python 3.11+ | 3.12 recommended |
| SQLite 3.35+ | bundled with Python on most platforms |
| `ffmpeg` + `ffprobe` | thumbnail / preview generation; video audio extraction for Whisper |
| Pillow | image thumbnails — installed via `requirements.txt` |

### Local inference backend (for enrichment)

Enrichment runs entirely locally. You need at least one of:

- **[Ollama](https://ollama.com/)** — pull any model compatible with your
  hardware (e.g. `qwen2.5:14b` for tag categorization).
- **MLX hub** — if you run on Apple Silicon / Metal, an MLX inference server
  (FastAPI wrapper around `mlx_lm` + `mlx_whisper`) gives fast vision and
  Whisper throughput without a GPU cluster.
- **Any OpenAI-compatible local server** — Ollama, LM Studio, llama.cpp,
  etc. all work for the text-only steps.
- **Whisper** — `openai-whisper` (CPU/GPU) or `whisper-cpp` (fast on ARM)
  for transcription.

The ingest pipeline and the Flask site work independently from the enrichment
layer — you can ingest and browse without any inference backend.

---

## Installation

```bash
git clone <repo-url> media-vault
cd media-vault

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
# For enrichment extras:
pip install -r archive-enrich/requirements.txt
```

---

## Configuration

```bash
cp vault.example.toml vault.toml
$EDITOR vault.toml
```

Key fields to fill in:

```toml
[site]
name = "My Archive"          # browser title

[collection]
description = "my personal photo and video archive"   # injected into AI prompts

[ingest]
source_label = "import-2024"     # label for this import batch in audit logs
source_root  = "/Volumes/MyDisk/Photos"   # absolute path to the source tree

[ingest.sections]
# Map each top-level folder name under source_root → (section, item_type).
# item_type: scan | visual | video | press | photo | other
"Photos"   = { section = "photo",  item_type = "photo" }
"Videos"   = { section = "video",  item_type = "video" }

[tags]
categories = ["People", "Places & Landscapes", "Objects & Gear", "Other"]
```

See `vault.example.toml` for the fully commented template.

---

## Initialize the catalog

Creates `metadata/catalog.sqlite` with the full schema (idempotent):

```bash
python scripts/init_db.py
```

---

## First ingest

```bash
python scripts/ingest.py
```

The ingester walks `source_root`, classifies each file, copies it into
`masters/`, generates a thumbnail and a preview JPEG, and records it in
the catalog. Re-running is safe — files are identified by SHA-256 and skipped
if already known.

---

## Launch the catalog site

```bash
./run-site.sh
# Opens on http://127.0.0.1:5055
```

Or manually:

```bash
cd app && python -m flask run --host 127.0.0.1 --port 5055 --no-reload
```

---

## Run the enrichment pipeline

See [archive-enrich/README.md](../archive-enrich/README.md) for the full
enrichment workflow (vision, transcription, tag categorization, deduplication).

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `VAULT_CONFIG` | `vault.toml` (repo root) | Path to the config file |

---

## Running tests

```bash
# All tests
python -m pytest

# Enrichment tests only
cd archive-enrich && python -m pytest

# Flask site tests only
cd app && python -m pytest
```
