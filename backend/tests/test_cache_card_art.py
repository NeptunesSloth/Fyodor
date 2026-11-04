"""The Bag of Extras asks the host for the art of the common tokens it shows (POST /api/cards/cache-art): downloaded like
deck art (linked from Scryfall, cached, never shipped), only on the host and only while it may go online."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for _ in range(100):
        state = client.get(f"/api/jobs/{job_id}").json()
        if state["state"] != "running":
            break
        time.sleep(0.02)
    return state


def test_cache_card_art_downloads_on_the_host_while_online(client: TestClient) -> None:
    services = client.app.state.services
    seen: dict[str, Any] = {}

    def fake_cache(ids: list[str], progress: Any) -> str:
        seen["ids"] = ids
        progress(len(ids), len(ids), 0)
        return f"{len(ids)} downloaded"

    services.cache_artwork = fake_cache
    job = client.post("/api/cards/cache-art", json={"ids": ["tok-a", "tok-b", "tok-a"]})
    assert job.status_code == 202
    state = _wait(client, job.json()["id"])
    assert state["state"] == "done" and state["message"] == "2 downloaded"
    assert seen["ids"] == ["tok-a", "tok-b"]


def test_cache_card_art_is_host_only_and_respects_offline_mode(client: TestClient) -> None:
    services = client.app.state.services
    services.cache_artwork = lambda ids, progress: (_ for _ in ()).throw(AssertionError("downloaded"))
    remote = {"X-Forwarded-For": "192.168.1.50"}
    assert client.post("/api/cards/cache-art", json={"ids": ["tok-a"]}, headers=remote).status_code == 403
    object.__setattr__(services.settings, "allow_network", False)
    try:
        assert client.post("/api/cards/cache-art", json={"ids": ["tok-a"]}).status_code == 409
    finally:
        object.__setattr__(services.settings, "allow_network", True)
    assert client.post("/api/cards/cache-art", json={"ids": []}).status_code == 422
    assert client.post("/api/cards/cache-art", json={"ids": [f"t{i}" for i in range(51)]}).status_code == 422
