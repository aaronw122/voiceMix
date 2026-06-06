def test_index_renders_recorder_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert 'id="record-btn"' in html
    assert "/static/recorder.js" in html


def test_recorder_js_served(client):
    resp = client.get("/static/recorder.js")
    assert resp.status_code == 200
    body = resp.text
    # the JS drives the real pipeline: voices catalog + both convert endpoints
    assert "/voices" in body
    assert "/convert" in body
    assert "/impersonate" in body
