"""Room passwords are PBKDF2 at 600,000 rounds; a room saved with fewer rounds still verifies and is upgraded on its next correct join."""

from __future__ import annotations

import hashlib
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.multiplayer import hub as hubmod
from app.multiplayer.hub import PASSWORD_ROUNDS, GameHub, Room
from app.multiplayer.lobby import LobbySettings
from tests.conftest import claim_host
from tests.test_recovery import lan_table

OLD_SALT = bytes(range(16))


def old_room(password: str = "friday", rounds: int | None = None) -> Room:
    """A room as the server saved it before ``password_rounds`` existed (120,000 rounds, no field)."""
    room = Room(mode="lan", code="ABCDEF", host_token="h", game_id="g")
    room.password_salt = OLD_SALT
    room.password_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), OLD_SALT, 120_000)
    if rounds is not None:
        room.password_rounds = rounds
    return room


def test_the_constant_and_the_old_default() -> None:
    assert PASSWORD_ROUNDS == 600_000
    assert Room(mode="lan", code="ABCDEF", host_token="h", game_id="g").password_rounds == 120_000


def test_a_new_room_stores_600000_rounds_and_verifies() -> None:
    room = GameHub().create_lobby(LobbySettings(), password="friday")
    assert room.password_rounds == 600_000
    assert room.password_hash == hashlib.pbkdf2_hmac("sha256", b"friday", room.password_salt or b"", 600_000)
    assert room.check_password("friday") and not room.check_password("thursday")


def test_a_room_without_a_password_stores_nothing_and_accepts_anything(monkeypatch: pytest.MonkeyPatch) -> None:
    room = GameHub().create_lobby(LobbySettings())
    assert room.password_hash is None and room.password_salt is None
    meta = GameHub().meta(room)
    assert meta["password_hash"] is None and meta["password_salt"] is None
    monkeypatch.setattr(hubmod, "_pbkdf2", lambda *a: pytest.fail("a room with no password hashes nothing"))
    assert room.check_password(None) and room.check_password("anything")


def test_an_old_room_verifies_and_is_upgraded_with_a_new_salt() -> None:
    room = old_room()
    assert room.check_password("friday")
    assert room.password_rounds == 600_000
    assert room.password_salt != OLD_SALT
    assert room.password_hash == hashlib.pbkdf2_hmac("sha256", b"friday", room.password_salt or b"", 600_000)
    assert room.check_password("friday") and not room.check_password("nope")


def test_a_wrong_password_does_not_upgrade() -> None:
    room = old_room()
    before = (room.password_salt, room.password_hash, room.password_rounds)
    assert not room.check_password("thursday") and not room.check_password(None)
    assert (room.password_salt, room.password_hash, room.password_rounds) == before == (OLD_SALT, before[1], 120_000)


def test_the_upgrade_is_reported_so_it_can_be_saved() -> None:
    room, saved = old_room(), []
    assert room.check_password("friday", on_upgrade=lambda: saved.append((room.password_rounds, room.password_salt)))
    assert saved == [(600_000, room.password_salt)]
    saved.clear()
    assert room.check_password("friday", on_upgrade=lambda: saved.append(1))  # already current: nothing to save
    assert saved == []


@pytest.mark.parametrize("rounds", [0, -5, 10_000_001, "600000", 1.5, True, None])
def test_untrusted_rounds_never_verify_and_never_hash_that_many_times(rounds, monkeypatch: pytest.MonkeyPatch) -> None:
    room = old_room()
    room.password_rounds = rounds  # type: ignore[assignment]
    seen: list[object] = []
    real = hubmod._pbkdf2
    monkeypatch.setattr(hubmod, "_pbkdf2", lambda p, s, r: seen.append(r) or real(p, s, 1))
    assert not room.check_password("friday")
    assert all(r == PASSWORD_ROUNDS for r in seen)  # (it costs a current room's check, and no more)


def test_metadata_round_trip_keeps_the_rounds_and_old_metadata_defaults(settings, card_db) -> None:
    first = TestClient(create_app(settings))  # no lifespan: the process just dies afterwards
    claim_host(first)
    gid, code, _host, _mike = lan_table(first)
    hub = first.app.state.services.hub  # type: ignore[attr-defined]
    room = hub.rooms[gid]
    assert room.password_rounds == 600_000
    meta = hub.meta(room)
    assert meta["password_rounds"] == 600_000
    # metadata written before the field: the 120,000-round hash, no password_rounds key
    salt = bytes(range(16))
    meta["password_salt"], meta["password_hash"] = salt.hex(), hashlib.pbkdf2_hmac("sha256", b"friday", salt, 120_000).hex()
    del meta["password_rounds"]
    session = room.game
    hub.close(gid)
    restored = hub.restore(meta, session, {})
    assert restored.password_rounds == 120_000 and restored.password_salt == salt
    assert restored.check_password("friday") is True
    assert restored.password_rounds == 600_000 and restored.password_salt != salt
    assert code == restored.code


def test_a_correct_join_on_an_old_room_is_saved_upgraded(settings, card_db) -> None:
    first = TestClient(create_app(settings))
    claim_host(first)
    gid, code, _host, _mike = lan_table(first)
    hub = first.app.state.services.hub  # type: ignore[attr-defined]
    room = hub.rooms[gid]
    old_hash = hashlib.pbkdf2_hmac("sha256", b"friday", OLD_SALT, 120_000)
    room.password_salt, room.password_hash, room.password_rounds = OLD_SALT, old_hash, 120_000
    hub.persist(room)
    del first

    with TestClient(create_app(settings)) as second:
        claim_host(second)
        again = second.app.state.services.hub.rooms[gid]  # type: ignore[attr-defined]
        assert again.password_rounds == 120_000 and again.password_salt == OLD_SALT
        bad = second.post("/api/join", json={"code": code, "password": "nope", "spectate": True})
        assert bad.status_code == 403 and again.password_rounds == 120_000
        assert second.post("/api/join", json={"code": code, "password": "friday", "spectate": True}).status_code == 200
        assert again.password_rounds == 600_000 and again.password_salt != OLD_SALT
        del second.app.state.services.hub.rooms[gid]  # type: ignore[attr-defined]  # (so the meta below is what the journal holds)

    with TestClient(create_app(settings)) as third:
        claim_host(third)
        reloaded = third.app.state.services.hub.rooms[gid]  # type: ignore[attr-defined]
        assert reloaded.password_rounds == 600_000 and reloaded.password_salt != OLD_SALT
        assert reloaded.check_password("friday") and not reloaded.check_password("nope")


def test_doctored_rounds_in_saved_metadata_fail_that_room_only(settings, card_db) -> None:
    first = TestClient(create_app(settings))
    claim_host(first)
    gid, _code, _host, _mike = lan_table(first)
    hub = first.app.state.services.hub  # type: ignore[attr-defined]
    room = hub.rooms[gid]
    for bad in (0, -1, 10_000_001, "5", 2.5, True, None, [1]):
        meta = hub.meta(room)
        meta["password_rounds"] = bad
        hub.close(gid)
        restored = hub.restore(meta, room.game, {})
        assert restored.password_hash is not None  # (still a passworded room: it is not opened up)
        assert not restored.check_password("friday")


def test_hashing_runs_at_most_4_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    active = peak = 0
    guard = threading.Lock()

    def slow(password: str, salt: bytes, rounds: int) -> bytes:
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with guard:
            active -= 1
        return b"x" * 32

    monkeypatch.setattr(hubmod, "_pbkdf2", slow)
    threads = [threading.Thread(target=hubmod._hash_password, args=("pw", OLD_SALT, 1000)) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert 1 <= peak <= 4


def test_the_unknown_code_dummy_costs_a_current_room(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []
    monkeypatch.setattr(hubmod, "_pbkdf2", lambda p, s, r: seen.append(r) or b"")
    hubmod.spend_password_check("x")
    assert seen == [PASSWORD_ROUNDS]
