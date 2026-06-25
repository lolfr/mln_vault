import categorize_tags as c   # conftest fournit une config neutre


def test_coerce_known():
    assert c.coerce_category("People") == "People"


def test_coerce_unknown_falls_back_to_last():
    assert c.coerce_category("Nonexistent") == "Other"
    assert c.coerce_category("") == "Other"


def test_coerce_trimmed_case_insensitive():
    assert c.coerce_category("  products ") == "Products"


def test_parse_batch_index_based():
    out = c.parse_batch('{"categories":["Products","Animals"]}', ["logo", "dog"])
    assert out == {"logo": "Products", "dog": "Animals"}


def test_parse_batch_length_mismatch_returns_none():
    assert c.parse_batch('{"categories":["Products"]}', ["a", "b"]) is None


def test_categories_from_config(monkeypatch):
    import os, tempfile, importlib
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "vault.toml")
        open(p, "w").write('[tags]\ncategories = ["X","Y","Other"]\n[ingest]\nsource_label="x"\n')
        monkeypatch.setenv("VAULT_CONFIG", p)
        import categorize_tags as c2; importlib.reload(c2)
        assert c2.CATEGORIES == ["X", "Y", "Other"]
        assert c2.coerce_category("y") == "Y"
        assert c2.coerce_category("zzz") == "Other"
        importlib.reload(c)  # restaure la config conftest pour les tests suivants (temp dir encore présent)
