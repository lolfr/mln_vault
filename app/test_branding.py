import os, tempfile, importlib

def test_site_name_from_config_not_hardcoded(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "vault.toml")
        open(p, "w").write('[site]\nname = "Test Vault"\n[ingest]\nsource_label = "x"\n[tags]\ncategories = ["Other"]\n')
        monkeypatch.setenv("VAULT_CONFIG", p)
        import app; importlib.reload(app)   # recharge avec la config de test
        html = app.app.test_client().get("/").get_data(as_text=True)
        assert "Test Vault" in html         # le nom configuré apparaît
