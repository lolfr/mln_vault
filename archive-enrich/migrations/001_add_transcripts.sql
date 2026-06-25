-- version: 0.2.0
-- Migration 001 : ajouts pour archive-enrich
--
-- ADDITIVE & IDEMPOTENT : ne modifie aucune table existante.
-- Safe à exécuter plusieurs fois.
--
-- Usage :
--   sqlite3 /Volumes/Vault/archive/metadata/catalog.sqlite < migrations/001_add_transcripts.sql

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────────────────────
-- TRANSCRIPTIONS Whisper
-- Une table dédiée (vs notes_internal) pour :
--   - permettre le FTS sur le texte intégral
--   - garder notes_internal pour les vraies notes archiviste
--   - stocker proprement les segments timecodés
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transcripts (
    item_id         TEXT PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    lang            TEXT,                    -- ISO 639-1 détecté par Whisper
    text            TEXT NOT NULL,           -- transcription complète
    segments_json   TEXT,                    -- segments timecodés [{from,to,text}]
    model           TEXT,                    -- ex 'whisper-medium', 'whisper.cpp-large-v3'
    duration_s      REAL,                    -- durée du traitement
    word_count      INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_transcripts_lang ON transcripts(lang);

-- ─────────────────────────────────────────────────────────────
-- FTS5 sur les transcriptions (table virtuelle séparée)
-- On garde items_fts intact ; les requêtes peuvent UNION les deux.
-- ─────────────────────────────────────────────────────────────
CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
    text,
    content='transcripts',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS transcripts_fts_insert AFTER INSERT ON transcripts BEGIN
    INSERT INTO transcripts_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS transcripts_fts_delete AFTER DELETE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;

CREATE TRIGGER IF NOT EXISTS transcripts_fts_update AFTER UPDATE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO transcripts_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS transcripts_touch AFTER UPDATE ON transcripts BEGIN
    UPDATE transcripts SET updated_at = datetime('now') WHERE item_id = new.item_id;
END;

-- ─────────────────────────────────────────────────────────────
-- ENRICHMENT LOG : trace de chaque enrichissement LLM
-- Permet de relancer, comparer modèles, mesurer la qualité,
-- éventuellement rollback (les valeurs précédentes sont dans audit_log).
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS enrichments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    model           TEXT NOT NULL,           -- 'claude-haiku-4-5-...'
    prompt_version  TEXT NOT NULL,           -- 'v0.2.0'
    raw_json        TEXT NOT NULL,           -- réponse LLM brute (audit, debug)
    confidence      REAL,                    -- 0.0 - 1.0 auto-évaluation modèle
    applied         INTEGER NOT NULL DEFAULT 0,  -- 0 = en attente review, 1 = appliqué
    applied_at      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_enrichments_item    ON enrichments(item_id);
CREATE INDEX IF NOT EXISTS idx_enrichments_applied ON enrichments(applied);

-- ─────────────────────────────────────────────────────────────
-- Note : le champ tags.kind existant est étendu (via convention,
-- pas via contrainte CHECK) pour inclure 'auto'.
-- L'enum effectif devient : era|product|campaign|medium|theme|color|free|auto
-- Aucune migration nécessaire — tags.kind est déjà TEXT libre.
-- ─────────────────────────────────────────────────────────────
