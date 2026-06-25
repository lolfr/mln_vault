import app as A

def test_tags_page_has_cloud_and_categories():
    c = A.app.test_client()
    r = c.get("/tags")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="tag-cloud"' in html
    assert 'id="tag-search"' in html
    assert "details" in html  # au moins une catégorie dépliable
