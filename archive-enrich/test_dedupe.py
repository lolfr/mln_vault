import dedupe_report as d


def test_norm_strips_yt_id():
    assert d.norm_title("How to shoot — Brand Yx6eIGUe5M") == "how to shoot — brand"
    assert d.norm_title("Bokeh'd — Brand IKok5dykRBM.f248") == "bokeh'd — brand"


def test_norm_keeps_plain_words():
    assert d.norm_title("Mac OS X Jaguar Promo") == "mac os x jaguar promo"


def test_has_suffix():
    assert d.has_suffix("Foo Brand 1Xf6gvi8og") is True
    assert d.has_suffix("Foo Brand") is False


def test_pick_survivor_largest_then_clean_then_id():
    items = [
        {"id": "b", "title": "X Yx6eIGUe5M", "file_size_bytes": 100},
        {"id": "a", "title": "X", "file_size_bytes": 100},
        {"id": "c", "title": "X", "file_size_bytes": 999},
    ]
    assert d.pick_survivor(items)["id"] == "c"
    items2 = [{"id": "b", "title": "X Yx6eIGUe5M", "file_size_bytes": 100},
              {"id": "a", "title": "X", "file_size_bytes": 100}]
    assert d.pick_survivor(items2)["id"] == "a"


def test_group_videos_groups_by_normtitle_and_duration():
    rows = [
        {"id": "1", "title": "Clip A", "duration_seconds": 27.93, "file_size_bytes": 10, "item_type": "video"},
        {"id": "2", "title": "Clip A AbcdEf1234", "duration_seconds": 27.94, "file_size_bytes": 20, "item_type": "video"},
        {"id": "3", "title": "Clip B", "duration_seconds": 12.0, "file_size_bytes": 5, "item_type": "video"},
    ]
    groups = d.group_videos(rows)
    assert len(groups) == 1 and {r["id"] for r in groups[0]} == {"1", "2"}


import sqlite3, dedupe_apply as a


def _fixture():
    con = sqlite3.connect(":memory:")
    con.executescript('''
      CREATE TABLE items(id TEXT PRIMARY KEY, title TEXT, item_type TEXT,
        duration_seconds REAL, file_size_bytes INT);
      CREATE TABLE tags(id INTEGER PRIMARY KEY, slug TEXT, label TEXT);
      CREATE TABLE item_tags(item_id TEXT, tag_id INT, PRIMARY KEY(item_id,tag_id));
      CREATE TABLE transcripts(item_id TEXT PRIMARY KEY, lang TEXT, text TEXT NOT NULL,
        segments_json TEXT, model TEXT, duration_s REAL, word_count INT,
        created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
      CREATE TABLE enrichments(id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT, model TEXT NOT NULL,
        prompt_version TEXT NOT NULL, raw_json TEXT NOT NULL, confidence REAL,
        applied INT DEFAULT 0, applied_at TEXT, created_at TEXT DEFAULT (datetime('now')));
      CREATE TABLE blocklist(id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT, reason TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')));
      INSERT INTO items VALUES('keep','X',  'video',27.9,13000000),('dup','X AbcdEf1234','video',27.9,2400000);
      INSERT INTO tags VALUES(1,'a','A'),(2,'b','B');
      INSERT INTO item_tags VALUES('keep',1),('dup',2);
      INSERT INTO transcripts(item_id,text,model) VALUES('dup','hello','whisper');
      INSERT INTO enrichments(item_id,model,prompt_version,raw_json) VALUES('dup','hub:x','v','{}');
    ''')
    return con


def test_apply_merges_and_blocklists():
    con = _fixture()
    a.apply_group(con, "keep", ["dup"])
    assert con.execute("SELECT COUNT(*) FROM item_tags WHERE item_id='keep' AND tag_id=2").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM transcripts WHERE item_id='keep'").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM enrichments WHERE item_id='keep' AND model='hub:x'").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM blocklist WHERE item_id='dup'").fetchone()[0] == 1


def test_apply_idempotent():
    con = _fixture()
    a.apply_group(con, "keep", ["dup"])
    a.apply_group(con, "keep", ["dup"])
    assert con.execute("SELECT COUNT(*) FROM blocklist WHERE item_id='dup'").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM item_tags WHERE item_id='keep'").fetchone()[0] == 2
