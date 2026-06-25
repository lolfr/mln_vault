# archive-enrich — Makefile
# version: 0.2.0
#
# Pipeline complet :
#   make migrate              (une fois)
#   make read LIMIT=30        (sélectionne 30 items)
#   make transcribe           (Whisper sur les vidéos sans transcript)
#   make enrich               (Claude Haiku → enrichments)
#   make review               (HTML de validation)
#   make csv                  (genère enrichments.csv)
#   make apply IMPORTER=/chemin/vers/import_csv.py
#   make mark-applied         (une fois l'import OK)

PYTHON   ?= python3
LIMIT    ?= 30
SECTION  ?=
WHISPER_MODEL ?= medium
MODEL    ?= claude-haiku-4-5-20251001
MIN_CONF ?= 0.5

# Pointe sur ton import_csv.py (configurable)
IMPORTER ?=

.PHONY: help setup migrate read transcribe enrich enrich-dry review csv apply mark-applied stats clean

help:
	@echo "archive-enrich — pipeline d'enrichissement archive"
	@echo ""
	@echo "  setup              installe les dépendances"
	@echo "  migrate            applique migrations/001_add_transcripts.sql"
	@echo "  read [LIMIT=N]     sélectionne N items éligibles → data/manifest.json"
	@echo "  transcribe         Whisper sur les vidéos du manifest"
	@echo "  enrich             Claude Haiku → table enrichments"
	@echo "  enrich-dry         simulation sans appel API"
	@echo "  review             génère data/enrich_review.html"
	@echo "  csv                produit data/enrichments.csv (conforme à ton import_csv.py)"
	@echo "  apply IMPORTER=..  exécute ton import_csv.py sur enrichments.csv"
	@echo "  mark-applied       marque applied=1 (une fois l'import validé)"
	@echo "  stats              état actuel de la base"
	@echo ""
	@echo "Variables : LIMIT, SECTION, WHISPER_MODEL, MODEL, MIN_CONF, IMPORTER"

setup:
	$(PYTHON) -m pip install -r requirements.txt

migrate:
	@if [ -z "$$ARCHIVE_ROOT" ]; then \
	  echo "ERROR: set ARCHIVE_ROOT to your archive path" >&2; exit 1; \
	else \
	  DB="$$ARCHIVE_ROOT/metadata/catalog.sqlite"; \
	fi; \
	echo "→ migration sur $$DB"; \
	sqlite3 "$$DB" < migrations/001_add_transcripts.sql && echo "migration OK"

read:
	$(PYTHON) src/read_items.py --limit $(LIMIT) $(if $(SECTION),--section $(SECTION),)

transcribe:
	$(PYTHON) src/transcribe.py --model $(WHISPER_MODEL)

transcribe-cpp:
	@if [ -z "$(WHISPER_BIN)" ] || [ -z "$(WHISPER_MODEL_PATH)" ]; then \
	  echo "Usage: make transcribe-cpp WHISPER_BIN=/path/whisper-cli WHISPER_MODEL_PATH=/path/ggml.bin"; \
	  exit 1; \
	fi
	$(PYTHON) src/transcribe.py --binary $(WHISPER_BIN) --model-path $(WHISPER_MODEL_PATH)

enrich:
	$(PYTHON) src/enrich.py --model $(MODEL)

enrich-dry:
	$(PYTHON) src/enrich.py --model $(MODEL) --dry-run

review:
	$(PYTHON) src/build_review.py

csv:
	$(PYTHON) src/build_csv.py --min-confidence $(MIN_CONF)

apply:
	@if [ -z "$(IMPORTER)" ]; then \
	  echo "Usage: make apply IMPORTER=/chemin/vers/import_csv.py"; \
	  exit 1; \
	fi
	$(PYTHON) $(IMPORTER) data/enrichments.csv

mark-applied:
	$(PYTHON) src/build_csv.py --min-confidence $(MIN_CONF) --mark-applied --out /tmp/already_done.csv
	@rm -f /tmp/already_done.csv

stats:
	@DB="$${ARCHIVE_ROOT:?set ARCHIVE_ROOT to your archive path}/metadata/catalog.sqlite"; \
	sqlite3 "$$DB" "SELECT 'items total', COUNT(*) FROM items UNION ALL \
	              SELECT 'items sans description', COUNT(*) FROM items WHERE description IS NULL UNION ALL \
	              SELECT 'items sans product', COUNT(*) FROM items WHERE product IS NULL UNION ALL \
	              SELECT 'transcripts', COUNT(*) FROM transcripts UNION ALL \
	              SELECT 'enrichments en attente', COUNT(*) FROM enrichments WHERE applied=0 UNION ALL \
	              SELECT 'enrichments appliqués', COUNT(*) FROM enrichments WHERE applied=1;" 2>/dev/null

clean:
	rm -f data/manifest.json data/enrichments.csv data/enrich_review.html
