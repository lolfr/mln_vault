import app as A

def test_failures_page():
    c = A.app.test_client()
    r = c.get("/failures")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Sans preview" in html
    assert "Vision échouée" in html
    assert "non transcrites" in html
