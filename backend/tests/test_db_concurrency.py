"""The app database is one sqlite3 connection shared by FastAPI's worker threads. Every read
must hold the repository lock, or concurrent requests fail with
``sqlite3.InterfaceError: bad parameter or other API misuse`` (seen in CI when Settings fetched
card backs and playmats at the same time)."""

from __future__ import annotations

import threading

from tests.fixtures.images import png


def test_concurrent_reads_and_writes_share_the_connection_safely(client):
    services = client.app.state.services
    for i in range(5):
        services.assets.add(png(4 + i, 4), kind="playmat" if i % 2 else "card_back", name=f"a{i}")
    errors: list[BaseException] = []
    start = threading.Barrier(8)

    def reader(n: int) -> None:
        try:
            start.wait()
            for _ in range(150):
                services.assets.list("playmat" if n % 2 else "card_back")
                services.macros.list_all()
                services.stats.players()
                services.stats.history(limit=5)
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    def writer() -> None:
        try:
            start.wait()
            for i in range(40):
                a = services.assets.add(png(9, 9, (i, 0, 0)), kind="playmat", name=f"w{i}")
                services.assets.rename(a["id"], f"renamed {i}")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=reader, args=(n,)) for n in range(7)] + [threading.Thread(target=writer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_concurrent_asset_requests_over_http(client):
    """The exact CI pattern: two asset listings requested in parallel, many times."""
    results: list[int] = []

    def fetch(kind: str) -> None:
        for _ in range(60):
            results.append(client.get(f"/api/assets?kind={kind}").status_code)

    threads = [threading.Thread(target=fetch, args=(k,)) for k in ("card_back", "playmat", "card_back", "playmat")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert set(results) == {200}
