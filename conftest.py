# conftest.py — config de test neutre (permet d'importer les modules sans vault.toml privé)
import os, tempfile
_d = tempfile.mkdtemp(prefix="vaulttest-")
_p = os.path.join(_d, "vault.toml")
open(_p, "w").write(
    '[site]\nname = "Test Vault"\n'
    '[collection]\ndescription = "a test media archive"\n'
    '[ingest]\nsource_label = "test"\nsource_root = "/tmp/src"\n'
    '[ingest.sections]\n"Photos" = { section = "photo", item_type = "scan" }\n'
    '"Videos" = { section = "video", item_type = "video" }\n'
    '[tags]\ncategories = ["Products","People","Colors","Animals","Other"]\n'
)
os.environ["VAULT_CONFIG"] = _p
