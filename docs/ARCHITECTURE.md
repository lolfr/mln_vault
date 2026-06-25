# Architecture

Media Vault is a local pipeline that moves files from a source tree into a
normalized archive, enriches them with AI metadata, and exposes everything
through a read-only Flask site.

---

## Data flow

```
Source tree (source_root)
        │
        ▼
scripts/ingest.py
  • SHA-256 hash → idempotent skip if already known
  • classify by top-level folder name (vault.toml [ingest.sections])
  • copy into masters/<section>/<year>/
  • generate thumbnail + preview (Pillow / ffmpeg)
  • INSERT into catalog: items, sources
        │
        ▼
metadata/catalog.sqlite
  Tables: items, tags, item_tags, transcripts,
          enrichments, sources, blocklist
        │
        ├─────────────────────────────────────────────┐
        ▼                                             ▼
archive-enrich/                                   app/
  • enrich.py    — VLM vision descriptions         Flask catalog site
  • transcribe.py — Whisper audio transcription    • grid / item pages
  • tag_categorizer — LLM tag bucketing            • tag cloud + search
  • dedupe        — normalized-title dedup         • full-text search
    (soft, reversible via blocklist)               • enrichment-gaps page
```

---

## Catalog schema (SQLite)

| Table | Purpose |
|---|---|
| `items` | One row per ingested file: path, hash, section, item\_type, title, description, dates. |
| `tags` + `item_tags` | Many-to-many tag graph. |
| `transcripts` | Audio/video transcriptions (text + model metadata). |
| `enrichments` | Raw LLM/VLM output per item (applied flag + prompt version). |
| `sources` | Import runs (label, timestamp, source path). |
| `blocklist` | Soft-deleted duplicates; survivor id preserved for rollback. |

---

## Inference backends

All enrichment runs **100 % locally** — no external API calls, no recurring
cost.

- **Text LLM** (tag categorization, title heuristics) — any Ollama model or
  OpenAI-compatible local server.
- **Vision LLM** (image / poster-frame descriptions) — e.g. Qwen2.5-VL via an
  MLX hub or Ollama.
- **Whisper** (video transcription) — MLX Whisper or `openai-whisper` / `whisper-cpp`.

The enrichment pipeline reads `vault.toml` for collection context and writes
its output to the `enrichments` and `transcripts` tables. Nothing in the
pipeline touches the source files or the `masters/` copies.

---

## Configuration entry point

`vault_config.py` loads `vault.toml` (or the path in `$VAULT_CONFIG`) and
exposes a single `Config` object used by all scripts and the Flask app. See
`vault.example.toml` for the full annotated template.
