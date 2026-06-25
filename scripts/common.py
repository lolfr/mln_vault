"""Shared helpers: paths, slug, classification, checksum."""
from __future__ import annotations

import hashlib
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # racine repo
import vault_config  # noqa: E402
_CFG = vault_config.load_config()
SOURCE_LABEL = _CFG.source_label

ARCHIVE_ROOT = Path(os.environ.get("ARCHIVE_ROOT") or Path(__file__).resolve().parents[1])
MASTERS_ROOT = ARCHIVE_ROOT / "masters"
THUMBS_ROOT = ARCHIVE_ROOT / "derivatives" / "thumbnails"
PREVIEW_ROOT = ARCHIVE_ROOT / "derivatives" / "preview"
DB_PATH = ARCHIVE_ROOT / "metadata" / "catalog.sqlite"

_source_root_raw = os.environ.get("SOURCE_ROOT") or _CFG.source_root or ""
SOURCE_ROOT = Path(_source_root_raw) if _source_root_raw else Path("/mnt/vault-source")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp", ".webp", ".heic"}
VECTOR_EXTS = {".eps", ".ai", ".pdf"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg", ".wmv", ".ts", ".qt", ".m2ts"}
SKIP_NAMES = {".DS_Store", ".localized", "Icon\r", "Thumbs.db"}
SKIP_DIRS = {".fseventsd", ".Spotlight-V100", ".Trashes", ".TemporaryItems"}


def slugify(value: str, *, max_len: int = 80) -> str:
    """URL-safe slug (ASCII, lower, dashes)."""
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    if not value:
        value = "untitled"
    return value[:max_len].rstrip("-")


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            data = fp.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def classify_path(rel: Path) -> dict:
    """Derive metadata from the path relative to the source vault.

    rel example: 'Hardware/Widget/2019/x.jpg' or 'Videos/1980s/foo.mp4'.
    """
    parts = rel.parts
    top = parts[0] if parts else ""
    section, item_type = _CFG.ingest_sections.get(top, ("other", "other"))

    # Detect decade/year from any path part
    year = None
    circa_start = circa_end = None
    decade_re = re.compile(r"^(19|20)(\d)0[\'']?s?\s*(Photos)?$", re.IGNORECASE)
    year_re = re.compile(r"^(19|20)\d{2}(\s+Photos)?$")
    product = None
    campaign = None

    # For videos: .../Videos by Decade/<decade>/<year?>/xxx
    for p in parts[1:-1]:
        p_clean = p.strip()
        m = year_re.match(p_clean)
        if m:
            year = int(m.group(0).split()[0])
            continue
        m = decade_re.match(p_clean)
        if m:
            base = int(m.group(1) + m.group(2) + "0")
            circa_start, circa_end = base, base + 9
            continue
        # premier composant non-année/décennie après le top = sujet (générique)
        if product is None:
            product = p_clean

    # If .../<decade>/<year>/... was captured we keep both
    return {
        "section": section,
        "item_type": item_type,
        "year": year,
        "circa_start": circa_start,
        "circa_end": circa_end,
        "product": product,
        "campaign": campaign,
    }


def guess_digital_format(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return ext or "unknown"


def short_id(checksum: str) -> str:
    return checksum[:8]


def make_item_id(section: str, year: int | None, seq: int) -> str:
    yr = str(year) if year else "0000"
    return f"{yr}-{section[:3]}-{seq:06d}"


def should_skip(path: Path) -> bool:
    if path.name in SKIP_NAMES:
        return True
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    return False
