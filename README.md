# Media Vault

A self-hosted pipeline and web catalog for a large personal media archive
(images, scans, press, videos) with **100 % local AI enrichment** — no cloud,
no per-call API budget, fully configurable via `vault.toml`.

> **This repository contains only the code and structure.** Media files,
> generated derivatives, the SQLite catalog and any secrets are **not**
> included (see [`.gitignore`](.gitignore)).

---

## Features

- **Ingest** (`scripts/`) — hashes each source file (SHA-256, idempotent dedup),
  classifies it from its path using the `[ingest.sections]` mapping in
  `vault.toml`, copies it into a normalized `masters/` tree, generates
  thumbnails and preview images, and records everything in a SQLite catalog.

- **Local AI enrichment** (`archive-enrich/`) — runs entirely on your hardware:
  - **Vision descriptions** of images and video poster frames via a local VLM
    (e.g. Qwen2.5-VL served by an MLX inference hub or Ollama).
  - **Transcription** of video audio via Whisper (e.g. `whisper-large-v3`
    via MLX or OpenAI Whisper).
  - **Tag categorization** into a fixed taxonomy via a local LLM (e.g. Qwen2.5).
  - **Deduplication** of re-encoded videos (normalized title + duration match),
    soft and fully reversible — duplicates are blocklisted, metadata is merged
    into the survivor.

- **Browse** (`app/`) — a Flask catalog site:
  - Grid and detail pages for every item.
  - Tag page with a **word cloud**, live search, and collapsible category tree.
  - Full-text search across titles, descriptions and tags.
  - Enrichment-gaps page to track items not yet processed.

---

## Quickstart

```bash
# 1. Copy the example config and fill in your paths and collection details.
cp vault.example.toml vault.toml
$EDITOR vault.toml

# 2. Install dependencies (Python 3.11+).
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Create the catalog schema.
python scripts/init_db.py

# 4. Ingest your source tree (reads source_root from vault.toml).
python scripts/ingest.py

# 5. Launch the catalog site.
./run-site.sh
# Then open http://127.0.0.1:5055
```

**Prerequisites:**
- Python 3.11+
- `ffmpeg` and `ffprobe` in PATH (thumbnail/preview generation, video audio)
- Pillow (`pip install Pillow`)
- A local inference backend for enrichment steps:
  - [Ollama](https://ollama.com/) for text LLM tasks (tag categorization, etc.)
  - An MLX inference hub or equivalent for vision (VLM) and Whisper transcription
  - Alternatively, any OpenAI-compatible local server works for the text tasks

---

## Configuration (`vault.toml`)

All runtime behaviour is driven by a single `vault.toml` at the repository
root (copy from `vault.example.toml`). Four top-level sections:

| Section | Purpose |
|---|---|
| `[site]` | Site title shown in the browser. |
| `[collection]` | Free-text description injected into enrichment prompts. |
| `[ingest]` | `source_label` (audit label), `source_root` (path to ingest). |
| `[ingest.sections]` | Maps each top-level folder name → `section` + `item_type`. |
| `[tags]` | Ordered list of tag categories for the LLM categorizer. |

See `vault.example.toml` for a fully commented template.

---

## Layout

```
scripts/          ingest, derivative generation, catalog import/export, schema init
archive-enrich/   enrichment pipeline (vision, transcription, tag categ., dedup + tests)
app/              Flask catalog site (+ tests)
docs/             architecture and setup documentation
vault.example.toml  fully commented configuration template
run-site.sh       convenience launcher for the Flask site
```

---

## Documentation

- [Architecture overview](docs/ARCHITECTURE.md)
- [Setup guide](docs/SETUP.md)
- [Enrichment pipeline](archive-enrich/README.md)

---

## License

This project is licensed under the **GNU Affero General Public License v3.0**.
See the [LICENSE](LICENSE) file for details.

In brief: if you modify and distribute this code — including running it as a
network service — you must make your modifications available under the same
license.
