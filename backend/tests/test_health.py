def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["card_database"]["available"] is True


def test_health_without_card_db(bare_client):
    body = bare_client.get("/api/health").json()
    assert body["card_database"]["available"] is False
    res = bare_client.get("/api/cards/search", params={"q": "sol"})
    assert res.status_code == 503
    assert res.json()["code"] == "card_db_missing"
