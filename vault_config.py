"""vault_config.py — config unique de l'outil (stdlib tomllib).
Cherchée via $VAULT_CONFIG, sinon vault.toml à la racine du repo."""
import os, tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_DEFAULT = _ROOT / "vault.toml"

class Config:
    def __init__(self, d):
        self.site_name = d.get("site", {}).get("name", "Media Vault")
        self.collection_description = d.get("collection", {}).get("description", "a personal media archive")
        ing = d.get("ingest", {})
        self.source_label = ing.get("source_label", "media")
        self.source_root = ing.get("source_root", None)
        self.ingest_sections = {
            k: (v["section"], v["item_type"]) for k, v in (ing.get("sections", {}) or {}).items()
        }
        self.tag_categories = list(d.get("tags", {}).get("categories", []))

def load_config(path=None):
    p = Path(path or os.environ.get("VAULT_CONFIG") or _DEFAULT)
    if not p.exists():
        raise SystemExit(f"[vault] config introuvable: {p} — copie vault.example.toml -> vault.toml et adapte-la")
    with open(p, "rb") as f:
        return Config(tomllib.load(f))
