"""The desktop-shortcut offer: only the Fyodor app on Windows makes one; a source checkout says it can't."""


def test_a_source_checkout_offers_no_shortcut(client):
    assert client.get("/api/shortcut").json()["supported"] is False
    assert client.post("/api/shortcut").status_code == 400
