# version: 0.2.0
"""Configuration centrale d'archive-enrich.

Tous les chemins et constantes ici. Surchargables par variables d'env :
    ARCHIVE_ROOT      par défaut /Volumes/Vault/archive
    CATALOG_DB        par défaut $ARCHIVE_ROOT/metadata/catalog.sqlite
    ANTHROPIC_API_KEY (requis pour enrich)
    ANTHROPIC_MODEL   par défaut claude-haiku-4-5-20251001
"""
from __future__ import annotations

import os
from pathlib import Path

# ─── Chemins ────────────────────────────────────────────────────
ARCHIVE_ROOT = Path(os.environ.get("ARCHIVE_ROOT", str(Path(__file__).resolve().parents[2])))
CATALOG_DB   = Path(os.environ.get("CATALOG_DB", str(ARCHIVE_ROOT / "metadata" / "catalog.sqlite")))
MASTERS_ROOT = ARCHIVE_ROOT / "masters"
PREVIEW_ROOT = ARCHIVE_ROOT / "derivatives" / "preview"
THUMBS_ROOT  = ARCHIVE_ROOT / "derivatives" / "thumbnails"

# Sortie du pilote (local au projet, pas dans l'archive)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ─── Modèles ────────────────────────────────────────────────────
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
PROMPT_VERSION  = "v0.2.0"

MAX_TOKENS_ENRICH = 1500

# ─── Heuristique titre brut ────────────────────────────────────
# Si le titre actuel correspond à ces signaux, on le remplace par le titre LLM.
# Marqueurs typiques d'un titre dérivé d'un nom de fichier source.
# Suffisent seuls à classifier comme "brut" (insensible à la casse).
RAW_TITLE_MARKERS = (
    "tpl", "1920x1080", "1280x720", "1080p", "720p", "480p",
    "_h264", "h264", "h265", "hevc", "prores", "1x1", "16x9",
    "_4k", "_uhd", " cc us ", " cc fr ", " ad us ", " ad fr ",
)


def is_raw_filename_title(title: str | None) -> bool:
    """Détecte un titre qui ressemble à un nom de fichier brut.

    Stratégie :
      1. Vide ou None → brut (à remplir)
      2. Contient un marqueur technique typique → brut
      3. Tout-minuscules + beaucoup de mots courts → brut
      4. Sinon → titre éditorial OK
    """
    if not title:
        return True
    t = title.strip()
    if not t:
        return True
    t_lower = t.lower()
    # 2. Marqueurs techniques
    if any(m in t_lower for m in RAW_TITLE_MARKERS):
        return True
    # 3. Tout-minuscules + mots courts
    is_lower = (t == t_lower)
    words = t.split()
    if is_lower and len(words) >= 5 and sum(1 for w in words if len(w) <= 4) >= 3:
        return True
    return False


# ─── Vocabulaires bornés (pour stabilité des tags) ─────────────
ALLOWED_PRODUCT_LINES = (
    "Mac", "iPod", "iPhone", "iPad", "Watch", "AirPods",
    "Vision Pro", "TV", "HomePod", "Services", "Software", "Corporate",
)

ALLOWED_CAMPAIGNS = (
    "other",
)
# Note: populate ALLOWED_CAMPAIGNS in your vault.toml [enrich] section

ALLOWED_FORMATS = (
    "tv_spot", "web", "keynote_excerpt", "retail_loop",
    "internal", "wwdc_bumper",
    "tutorial", "trade_show", "other",
)
