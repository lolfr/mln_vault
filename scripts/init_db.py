#!/usr/bin/env python3
"""Initialize the SQLite catalog with full schema + FTS5.

Idempotent: safe to run multiple times.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ARCHIVE = Path("/Volumes/Vault/archive")
DB_PATH = ARCHIVE / "metadata" / "catalog.sqlite"

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS items (
  id                TEXT PRIMARY KEY,
  slug              TEXT UNIQUE NOT NULL,
  title             TEXT NOT NULL,
  description       TEXT,
  item_type         TEXT NOT NULL,       -- ad, brochure, visual, scan, video, press, other
  product           TEXT,                -- iPhone, Mac, iPod, etc.
  campaign          TEXT,                -- Think Different, Get a Mac, etc.
  brand             TEXT DEFAULT '',
  year              INTEGER,
  date_exact        TEXT,                -- ISO-8601 when known
  circa_start       INTEGER,
  circa_end         INTEGER,
  language          TEXT,                -- en, fr, ja, multi
  country           TEXT,                -- ISO-3166 alpha-2
  source_type       TEXT,                -- personal_scan, web_archive, purchase, gift, unknown
  source_reference  TEXT,                -- URL or citation
  rights_status     TEXT NOT NULL DEFAULT 'unknown',
                                         -- unknown, likely_copyrighted, public_domain,
                                         -- licensed, permission_granted, private_only,
                                         -- remove_on_request
  publication_level TEXT NOT NULL DEFAULT 'private',
                                         -- private, semi_public, public
  physical_format   TEXT,                -- poster A2, leaflet, photograph, tape, etc.
  digital_format    TEXT,                -- jpeg, pdf, mp4, tiff, etc.
  file_path_master  TEXT,                -- relative to /Volumes/Vault/archive
  file_path_preview TEXT,
  file_path_thumb   TEXT,
  file_size_bytes   INTEGER,
  width_px          INTEGER,
  height_px         INTEGER,
  duration_seconds  REAL,
  checksum_sha256   TEXT,
  phash             TEXT,                -- perceptual hash for images
  notes_internal    TEXT,                -- never exposed publicly
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_items_year      ON items(year);
CREATE INDEX IF NOT EXISTS idx_items_type      ON items(item_type);
CREATE INDEX IF NOT EXISTS idx_items_product   ON items(product);
CREATE INDEX IF NOT EXISTS idx_items_pub       ON items(publication_level);
CREATE INDEX IF NOT EXISTS idx_items_checksum  ON items(checksum_sha256);
CREATE INDEX IF NOT EXISTS idx_items_phash     ON items(phash);

CREATE TABLE IF NOT EXISTS tags (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  slug  TEXT UNIQUE NOT NULL,
  label TEXT NOT NULL,
  kind  TEXT NOT NULL DEFAULT 'free'
        -- era, product, campaign, medium, theme, color, free
);

CREATE TABLE IF NOT EXISTS item_tags (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, tag_id)
);

CREATE TABLE IF NOT EXISTS sources (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id     TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,            -- personal_scan, web_archive, purchase, gift
  reference   TEXT,                      -- URL, seller, donor
  acquired_at TEXT,
  notes       TEXT
);
CREATE INDEX IF NOT EXISTS idx_sources_item ON sources(item_id);

CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id    TEXT,
  action     TEXT NOT NULL,              -- ingest, edit, delete, publish, takedown
  actor      TEXT,
  payload    TEXT,                       -- JSON
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_item ON audit_log(item_id);

CREATE TABLE IF NOT EXISTS blocklist (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id     TEXT REFERENCES items(id) ON DELETE CASCADE,
  reason      TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
  title, description, product, campaign, item_type,
  content='items', content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS items_fts_insert AFTER INSERT ON items BEGIN
  INSERT INTO items_fts(rowid, title, description, product, campaign, item_type)
  VALUES (new.rowid, new.title, new.description, new.product, new.campaign, new.item_type);
END;

CREATE TRIGGER IF NOT EXISTS items_fts_delete AFTER DELETE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, description, product, campaign, item_type)
  VALUES ('delete', old.rowid, old.title, old.description, old.product, old.campaign, old.item_type);
END;

CREATE TRIGGER IF NOT EXISTS items_fts_update AFTER UPDATE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, description, product, campaign, item_type)
  VALUES ('delete', old.rowid, old.title, old.description, old.product, old.campaign, old.item_type);
  INSERT INTO items_fts(rowid, title, description, product, campaign, item_type)
  VALUES (new.rowid, new.title, new.description, new.product, new.campaign, new.item_type);
END;

CREATE TRIGGER IF NOT EXISTS items_touch AFTER UPDATE ON items BEGIN
  UPDATE items SET updated_at = datetime('now') WHERE id = new.id;
END;
"""


def main() -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.executescript(SCHEMA)
    print(f"ok: schema ready at {DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
