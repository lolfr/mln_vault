import tempfile, os, vault_config

TOML = '''
[site]
name = "Demo Vault"
[collection]
description = "a demo archive"
[ingest]
source_label = "demo"
[ingest.sections]
"Photos" = { section = "photo", item_type = "scan" }
"Clips"  = { section = "video", item_type = "video" }
[tags]
categories = ["Products", "People", "Other"]
'''

def _write(tmp):
    p = os.path.join(tmp, "vault.toml"); open(p, "w").write(TOML); return p

def test_loads_all_fields():
    with tempfile.TemporaryDirectory() as t:
        c = vault_config.load_config(_write(t))
        assert c.site_name == "Demo Vault"
        assert c.collection_description == "a demo archive"
        assert c.source_label == "demo"
        assert c.ingest_sections["Photos"] == ("photo", "scan")
        assert c.ingest_sections["Clips"] == ("video", "video")
        assert c.tag_categories == ["Products", "People", "Other"]

def test_missing_config_raises():
    import pytest
    with pytest.raises(SystemExit):
        vault_config.load_config("/nonexistent/vault.toml")
