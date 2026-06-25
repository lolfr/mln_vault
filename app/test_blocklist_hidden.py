import re, sqlite3, app

# DB_PATH is in common (imported by app), expose it
DB_PATH = str(app.common.DB_PATH)

def test_blocklisted_item_disappears_from_items_listing():
    c = app.app.test_client()
    html = c.get("/items").get_data(as_text=True)
    slugs = re.findall(r'/item/([^"\'#?]+)', html)
    assert slugs, "aucun item liste au depart"
    slug = slugs[0]
    con = sqlite3.connect(DB_PATH)
    iid = con.execute("SELECT id FROM items WHERE slug=?", (slug,)).fetchone()[0]
    con.execute("INSERT INTO blocklist(item_id,reason) VALUES(?, 'test-dedupe')", (iid,)); con.commit()
    try:
        html2 = c.get("/items").get_data(as_text=True)
        assert ("/item/" + slug) not in html2
    finally:
        con.execute("DELETE FROM blocklist WHERE item_id=? AND reason='test-dedupe'", (iid,)); con.commit()
