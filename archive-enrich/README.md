# archive-enrich

Semantic enrichment layer for the Media Vault catalog.
Reads your existing SQLite catalog, produces titles / descriptions / tags /
transcriptions via fully local inference, and writes results back to the
`enrichments` and `transcripts` tables.

## Philosophy

**Enrich, don't overwrite.**

- Your masters are read-only (`masters/`)
- `catalog.sqlite` is the source of truth
- The LLM produces proposals, written to the `enrichments` table (`applied=0`)
- You validate via a review page, then apply
- Full rollback always possible via the `blocklist` table and `enrichments` raw JSON

## Architecture

```
catalog.sqlite
   │
   │  SELECT items to enrich
   ▼
manifest.json ──→ transcribe.py ──→ catalog.sqlite (table transcripts)
   │
   │  + existing JPEG previews
   ▼
enrich.py (local VLM/LLM) ──→ catalog.sqlite (table enrichments, applied=0)
   │
   ▼
build_review.py ──→ enrich_review.html ──→ visual validation
   │
   ▼
build_csv.py ──→ enrichments.csv
   │
   ▼
import_csv.py ──→ catalog.sqlite (items + tags + item_tags + audit_log)
```

## Prerequisites

- `catalog.sqlite` initialized by `python scripts/init_db.py`
- `ffmpeg`, `ffprobe` in PATH
- For Whisper transcription, one of:
  - `pip install openai-whisper` (simple, CPU/GPU)
  - `whisper-cpp` + a ggml model (~5× faster on ARM / Apple Silicon)
  - MLX Whisper server (fastest on Apple Silicon / Metal)
- Python 3.11+
- A local inference backend (Ollama, MLX hub, or any OpenAI-compatible server)

## Installation

```bash
cd archive-enrich
make setup
# No external API key needed — all inference is local.
# Set OLLAMA_HOST or your hub URL in vault.toml / environment if not localhost.
```

## Schema migration (one-time)

Adds the `transcripts` and `enrichments` tables without modifying existing data:

```bash
make migrate
```

Idempotent — safe to re-run.

## Pipeline (pilot run: 30 items)

```bash
# 1. Select 30 eligible items (videos first — more enrichment value)
make read LIMIT=30 SECTION=videos

# 2. Transcribe videos
make transcribe              # openai-whisper
# or:
make transcribe-cpp WHISPER_BIN=$(which whisper-cli) WHISPER_MODEL_PATH=~/models/ggml-medium.bin

# 3. Dry-run (no inference called, just display)
make enrich-dry

# 4. Real enrichment
make enrich

# 5. Validation page
make review
open data/enrich_review.html

# 6. Generate CSV
make csv MIN_CONF=0.5

# 7. Apply via import_csv.py
make apply IMPORTER=/path/to/vault/import_csv.py

# 8. Mark enrichments as applied
make mark-applied
```

## Guarantees

- **Idempotent**: every step can be re-run safely, nothing is duplicated
- **Non-destructive**: `year/product/campaign/country/language` only written if NULL
- **Titles**: replaced only when heuristically flagged as "raw" (see `config.py`)
- **Tags**: added via `INSERT OR IGNORE` — coexist with hand-curated tags
- **Audit log**: every write is traced by the importer
- **Rollback**: the `enrichments` table keeps raw JSON output for comparison / restore

## Fields never modified

`id`, `slug`, `checksum_sha256`, `file_path_*`, `rights_status`,
`publication_level`, `source_*`, `created_at`, `phash`

## Files

```
archive-enrich/
├── Makefile                      pipeline orchestration
├── README.md                     this file
├── requirements.txt              Python dependencies
├── migrations/
│   └── 001_add_transcripts.sql   transcripts + enrichments tables (additive)
├── prompts/
│   └── enrich.py                 SYSTEM + USER prompts
├── src/
│   ├── config.py                 paths, models, heuristics
│   ├── read_items.py             select eligible items → manifest.json
│   ├── transcribe.py             Whisper → table transcripts
│   ├── enrich.py                 VLM/LLM → table enrichments
│   ├── build_review.py           enrich_review.html
│   └── build_csv.py              enrichments.csv
└── data/                         (generated: manifest, csv, html)
```

## Prompt iteration

The prompt lives in `prompts/enrich.py`. Version it via `config.PROMPT_VERSION`
(increment on significant changes). The `enrichments.prompt_version` column lets
you compare output across prompt versions.
