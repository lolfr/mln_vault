import os, tempfile, importlib

TOML = '''
[ingest]
source_label = "demo"
[ingest.sections]
"Hardware" = { section = "hardware", item_type = "visual" }
"Videos"   = { section = "video",    item_type = "video" }
[tags]
categories = ["Other"]
'''

def _cfg(tmp):
    p = os.path.join(tmp, "vault.toml"); open(p, "w").write(TOML); return p

def test_classify_uses_config_sections(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        monkeypatch.setenv("VAULT_CONFIG", _cfg(t))
        import common; importlib.reload(common)
        from pathlib import Path
        m = common.classify_path(Path("Hardware/AirThing/2019/x.jpg"))
        assert m["section"] == "hardware"
        assert m["item_type"] == "visual"
        assert m["year"] == 2019
        u = common.classify_path(Path("Unknown/x.jpg"))
        assert u["section"] == "other" and u["item_type"] == "other"
