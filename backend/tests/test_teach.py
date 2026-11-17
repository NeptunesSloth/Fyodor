"""-- Teach Fyodor -- a taught keyword ("Dive N", the worked example of docs/TEACH_FYODOR.md: invented, the real card's text is
unknown) and a taught card line run through the normal engine: coverage, behaviour (ETB mill, then an optional return), replay and
save/load, games in progress keeping their snapshot, the shape checks, shared files, backups and the Try it table."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile

import pytest

from app.cards.importer import build_database
from app.rules import coverage, taught
from app.rules.taught import TeachError
from app.storage.taught import TaughtRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import on_top
from tests.wave9c_kit import build, card_named, check, mana, reloaded, to_hand

DIVE_TEXT = ("Dive 2 (When this creature enters, mill two cards, then you may return a creature card with mana value 2 or less "
             "milled this way to your hand.)")
STALKER_LINE = "Whenever Reef Stalker attacks, you may tumble a coin. If you do, draw a card."
EXTRA = [
    card("Dive Tester", mana_cost="{1}{U}", cmc=2.0, type_line="Creature — Merfolk", power="2", toughness="1", colors=["U"],
         color_identity=["U"], oracle_text=DIVE_TEXT),
    card("Reef Stalker", mana_cost="{2}{U}", cmc=3.0, type_line="Creature — Merfolk Rogue", power="2", toughness="2", colors=["U"],
         color_identity=["U"], oracle_text=f"Flying\n{STALKER_LINE}"),
]

DIVE = {"kind": "keyword", "name": "Dive", "param": True,
        "reminder": "When this creature enters, mill N cards, then you may return a creature card with mana value N or less milled this way to your hand.",
        "abilities": [{"hat": {"id": "etb"},
                       "body": [{"id": "mill", "values": {"n": "N"}},
                                {"id": "may", "body": [{"id": "from_milled", "values": {"n": "N", "card": "card_creature"}}]}]}]}


def stalker_entry(oracle_id: str) -> dict:
    return {"kind": "card", "oracle_id": oracle_id, "line": STALKER_LINE, "card_name": "Reef Stalker",
            "abilities": [{"hat": {"id": "attacks"}, "body": [{"id": "pay_life", "values": {"n": 1}, "body": [{"id": "draw"}]}]}]}


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.fixture(autouse=True)
def _clean_library():
    taught.set_library([])
    yield
    taught.set_library([])


def _teach(*entries):
    taught.set_library([taught.clean_entry(e) for e in entries])


def _resolve(s, pick=None, limit=40):
    """Resolve the stack; a choice is answered with ``pick`` (a card id, or None: take nothing / the first option when one is required)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options if (getattr(o, "card_id", None) or o.id) == pick] if pick else []
            if not ids and d.min_choices:
                ids = [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


# -- coverage ---------------------------------------------------------------------------------------------------------
def test_dive_card_is_manual_until_taught(cards):
    data = cards.resolve("Dive Tester")
    before = coverage.of_card_data(data)
    assert before.level != "FULL" and "Dive 2" in before.manual_parts
    _teach(DIVE)
    after = taught.apply(data, taught.snapshot())
    assert after is not data and after["_taught"]
    assert after["oracle_text"].startswith("When this creature enters, mill two cards.")
    assert coverage.of_card_data(after).level == "FULL"


def test_a_card_line_is_full_once_taught(cards):
    data = cards.resolve("Reef Stalker")
    assert STALKER_LINE in coverage.of_card_data(data).manual_parts
    _teach(stalker_entry(data["oracle_id"]))
    after = taught.apply(data, taught.snapshot())
    assert after["oracle_text"] == "Flying\nWhenever this creature attacks, you may pay 1 life. If you do, draw a card."
    assert coverage.of_card_data(after).level == "FULL"
    # the same line on another card is not touched
    other = dict(data, oracle_id="someone-else")
    assert taught.apply(other, taught.snapshot()) is other


def test_dive_reads_the_engines_own_definition():
    result = taught.check(DIVE)
    assert result["ok"] and result["lines"] == ["When this creature enters, mill N cards. You may put a creature card with mana value N or "
                                                 "less from among the cards milled this way into your hand."]
    definition = result["abilities"][0]["definition"]
    assert definition["kind"] == "triggered" and definition["trigger"] == "enters_self"
    assert [e["do"] for e in definition["effects"]] == ["mill", "pick_looked"]


# -- behaviour --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("keep", [True, False])
def test_dive_mills_then_may_return_a_cheap_creature(cards, keep):
    _teach(DIVE)
    s = build(cards, ["Dive Tester", "Grizzly Bears", "Elvish Visionary"])
    assert s.state.taught and s.state.taught[0]["name"] == "Dive"
    diver = to_hand(s, "Dive Tester")
    bears = on_top(s, "Grizzly Bears", "p1")  # (mv 2: may come back)
    on_top(s, "Elvish Visionary", "p1")
    mana(s, "p1", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=diver.id)
    _resolve(s, pick=bears.id if keep else None)
    assert s.state.cards[diver.id].zone == "p1:battlefield"
    assert s.state.cards[bears.id].zone == ("p1:hand" if keep else "p1:graveyard")
    assert s.state.cards[card_named(s, "Elvish Visionary").id].zone == "p1:graveyard"
    check(s)  # replay, and a save and a load


def test_dive_with_another_number_mills_that_many(cards):
    _teach(DIVE)
    s = build(cards, ["Dive Tester", "Grizzly Bears"])
    data = s.cards.get(card_named(s, "Dive Tester").card_id)
    assert data["oracle_text"].startswith("When this creature enters, mill two cards.")
    # the same keyword with a different number on another card
    other = dict(cards.resolve("Reef Stalker"), oracle_text="Dive 3")
    assert taught.apply(other, s.state.taught)["oracle_text"].startswith("When this creature enters, mill three cards.")


def test_a_taught_card_line_works_at_the_table(cards):
    data = cards.resolve("Reef Stalker")
    _teach(stalker_entry(data["oracle_id"]))
    s = build(cards, ["Reef Stalker"])
    stalker = to_hand(s, "Reef Stalker")
    mana(s, "p1", U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=stalker.id)
    _resolve(s)
    assert s.state.cards[stalker.id].zone == "p1:battlefield"
    check(s)


# -- a game in progress keeps what it started with ------------------------------------------------------------------
def test_a_game_in_progress_keeps_its_snapshot_when_the_library_changes(cards):
    _teach(DIVE)
    s = build(cards, ["Dive Tester"])
    cid = card_named(s, "Dive Tester").card_id
    taught.set_library([])  # the host deletes Dive
    assert s.cards.get(cid)["oracle_text"].startswith("When this creature enters")
    fresh = build(cards, ["Dive Tester"])
    assert fresh.cards.get(cid)["oracle_text"].startswith("Dive 2") and fresh.state.taught == []
    # ... and the saved game comes back with its own entries
    again = reloaded(s)
    assert again.state.taught == s.state.taught and again.cards.get(cid)["oracle_text"].startswith("When this creature enters")
    from app.game.state import GameState

    assert GameState.model_validate(s.state.model_dump(mode="json")).taught == s.state.taught


def test_a_game_from_before_teaching_is_left_alone(cards):
    _teach(DIVE)
    from app.game.session import GameSession

    s = build(cards, ["Dive Tester"])
    old = s.state.model_dump(mode="json")
    old["taught"] = None  # (a save from before Teach Fyodor existed)
    from app.game.state import GameState

    loaded = GameSession(GameState.model_validate(old), cards=cards, history=s.history)
    cid = card_named(s, "Dive Tester").card_id
    assert loaded.cards.get(cid)["oracle_text"].startswith("Dive 2")


# -- shape checks -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw, said", [
    ({**DIVE, "abilities": [{"hat": {"id": "etb"}, "body": [{"id": "make_coffee"}]}]}, "unknown piece"),
    ({**DIVE, "code": "import os"}, "unknown field"),
    ({**DIVE, "abilities": [{"hat": {"id": "etb"}, "body": [{"id": "draw", "values": {"n": "99 or 1=1"}}]}]}, "whole number"),
    ({**DIVE, "abilities": [{"hat": {"id": "etb"}, "body": [{"id": "draw", "values": {"n": 999}}]}]}, "number from"),
    ({**DIVE, "abilities": [{"hat": {"id": "etb"}, "body": [{"id": "draw", "values": {"evil": 1}}]}]}, "unknown setting"),
    ({**DIVE, "abilities": [{"hat": {"id": "etb"}, "body": [{"id": "draw", "body": [{"id": "draw"}]}]}]}, "can't hold"),
    ({**DIVE, "abilities": [{"hat": {"id": "draw"}, "body": [{"id": "draw"}]}]}, "start with a When"),
    ({**DIVE, "abilities": [{"hat": {"id": "etb"}, "body": []}]}, "add a Do piece"),
    ({**DIVE, "abilities": [{"hat": {"id": "etb"}, "body": [{"id": "ifdo", "body": [{"id": "draw"}]}]}]}, "right after"),
    ({**DIVE, "param": False}, "N is only for a keyword with a number"),
    ({**DIVE, "name": "Flying"}, "already knows"),
    ({**DIVE, "name": "x; DROP TABLE taught"}, "name:"),
    ({**DIVE, "abilities": [{"hat": {"id": "activated"}, "body": [{"id": "draw"}]}]}, "Cost piece"),
    ({**DIVE, "abilities": [{"hat": {"id": "etb"}, "body": [{"id": "damage", "values": {"n": 2, "to": "t_self"}}]}]}, "offered choices"),
    ({**DIVE, "abilities": []}, "between 1 and"),
    ("not even a dict", "not a taught entry"),
])
def test_bad_pieces_are_refused(raw, said):
    with pytest.raises(TeachError, match=said):
        taught.clean_entry(raw)
    assert taught.problems(raw) and not taught.check(raw)["ok"]


def test_clean_entry_rebuilds_from_the_vocabulary():
    clean = taught.clean_entry(DIVE)
    assert set(clean) == {"kind", "name", "param", "reminder", "abilities"}
    assert clean["abilities"][0]["body"][0] == {"id": "mill", "values": {"n": "N"}}
    assert taught.match_key_of(clean) == "keyword:dive"


# -- shared files -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("data, said", [
    ({"format": "fyodor-teach", "version": 1, "entries": [DIVE], "run": "rm -rf"}, "Not a Teach Fyodor file"),
    ({"format": "fyodor-deck", "version": 1, "entries": [DIVE]}, "Not a Teach Fyodor file"),
    ({"format": "fyodor-teach", "version": 9, "entries": [DIVE]}, "different version"),
    ({"format": "fyodor-teach", "version": 1, "entries": []}, "no taught entries"),
    ({"format": "fyodor-teach", "version": 1, "entries": [{**DIVE, "__proto__": {"polluted": True}}]}, "unknown field"),
    ({"format": "fyodor-teach", "version": 1, "entries": [DIVE, {**DIVE, "reminder": "again"}]}, "same thing twice"),
    ([DIVE], "Not a Teach Fyodor file"),
])
def test_import_refuses_anything_unexpected(data, said):
    with pytest.raises(ValueError, match=said):
        TaughtRepository.read_file(data)


# -- the API, the library, backups and Try it -----------------------------------------------------------------------
def test_teach_api_library_export_import_and_games(client):
    voc = client.get("/api/teach/vocabulary").json()
    assert {c["id"] for c in voc["categories"]} >= {"when", "if", "cost", "do", "then", "target", "value"}
    checked = client.post("/api/teach/check", json={"entry": DIVE}).json()
    assert checked["ok"] and checked["abilities"][0]["understood"]
    made = client.post("/api/teach", json={"entry": DIVE})
    assert made.status_code == 201, made.text
    row = made.json()
    assert row["kind"] == "keyword" and row["enabled"] and row["lines"][0].startswith("When this creature enters, mill N cards.")
    # the engine's library follows the saved rows
    assert [e["name"] for e in taught.snapshot()] == ["Dive"]
    # the card page shows the line as manual, now taught, and the card as FULL once applied
    diver = client.get("/api/cards/search", params={"q": "Dive Tester"}).json()["results"][0]
    lines = client.get(f"/api/teach/card/{diver['id']}").json()
    assert lines["level"] != "FULL" and lines["level_taught"] == "FULL"
    assert lines["lines"][0]["text"] == "Dive 2" and lines["lines"][0]["manual"] and lines["lines"][0]["taught_id"] == row["id"]
    assert lines["lines"][0]["keyword"] == {"name": "Dive", "param": True}
    # a new game starts with it; disabling afterwards leaves that game alone
    game = client.post("/api/teach/try", json={"entry": DIVE})
    assert game.status_code == 201, game.text
    gid, seat = game.json()["game"]["id"], game.json()["seat"]
    got = client.get(f"/api/games/{gid}/view", headers={"x-seat-token": seat["token"]})
    assert got.status_code == 200, got.text
    view = got.json()
    assert [view["cards"][c]["name"] for c in view["zones"]["p1:hand"]] == ["Dive Tester"]
    assert len(view["seat_order"]) == 2  # (you and the target dummy)
    off = client.patch(f"/api/teach/{row['id']}", json={"enabled": False})
    assert off.status_code == 200 and not off.json()["enabled"] and taught.snapshot() == []
    room = client.app.state.services.hub.get(gid)
    assert room.session.state.taught and room.session.state.taught[-1]["name"] == "Dive"  # (a real card with Dive: no stand-in)
    # export, delete, import brings it back
    exported = client.get("/api/teach/export")
    assert exported.status_code == 200 and exported.headers["content-disposition"].endswith('.json"')
    blob = exported.json()
    assert blob == {"format": "fyodor-teach", "version": 1, "entries": [row["entry"]]}
    assert client.delete(f"/api/teach/{row['id']}").status_code == 204 and client.get("/api/teach").json() == []
    back = client.post("/api/teach/import", content=json.dumps(blob).encode(), headers={"content-type": "application/json"})
    assert back.status_code == 200 and back.json()["imported"] == 1 and len(back.json()["entries"]) == 1
    bad = client.post("/api/teach/import", content=b'{"format": "fyodor-teach", "version": 1, "entries": [{"kind": "keyword", "name": "Evil", "abilities": [{"hat": {"id": "etb"}, "body": [{"id": "__import__"}]}]}]}',
                      headers={"content-type": "application/json"})
    assert bad.status_code == 422 and "unknown piece" in bad.json()["detail"]
    assert client.post("/api/teach/import", content=b"not json", headers={"content-type": "application/json"}).status_code == 422
    # a backup carries the library
    made = client.post("/api/backups")
    assert made.status_code == 201, made.text
    zipped = zipfile.ZipFile(io.BytesIO(client.get(f"/api/backups/{made.json()['name']}").content))
    tmp = client.app.state.services.settings.data_dir / "unzipped-app.sqlite"
    tmp.write_bytes(zipped.read("app.sqlite"))
    con = sqlite3.connect(tmp)
    try:
        assert con.execute("SELECT name, kind FROM taught").fetchall() == [("Dive", "keyword")]
    finally:
        con.close()


def test_teach_api_refuses_bad_entries_and_remote_hosts(client):
    bad = client.post("/api/teach", json={"entry": {**DIVE, "abilities": [{"hat": {"id": "etb"}, "body": [{"id": "nope"}]}]}})
    assert bad.status_code == 422 and "unknown piece" in bad.json()["detail"]
    remote = client.post("/api/teach", json={"entry": DIVE}, headers={"x-forwarded-for": "192.168.50.20"})
    assert remote.status_code == 403
    assert client.get("/api/teach", headers={"x-forwarded-for": "192.168.50.20"}).status_code == 200  # (reading is fine)


def test_teaching_a_card_line_through_the_api(client):
    stalker = client.get("/api/cards/search", params={"q": "Reef Stalker"}).json()["results"][0]
    entry = stalker_entry(stalker["oracle_id"])
    made = client.post("/api/teach", json={"entry": entry})
    assert made.status_code == 201, made.text
    lines = client.get(f"/api/teach/card/{stalker['id']}").json()
    assert lines["level_taught"] == "FULL"
    by_text = {ln["text"]: ln for ln in lines["lines"]}
    assert by_text[STALKER_LINE]["manual"] and by_text[STALKER_LINE]["taught_id"] == made.json()["id"]
    assert not by_text["Flying"]["manual"] and by_text["Flying"]["taught_id"] is None
    # teaching the same line again replaces the first (one entry per line)
    again = client.post("/api/teach", json={"entry": entry})
    assert again.status_code == 201 and again.json()["id"] == made.json()["id"] and len(client.get("/api/teach").json()) == 1


def test_coverage_tool_counts_taught_cards(cards):
    from tools.commander_coverage import rows, with_taught

    pool, _ = rows(cards.db_path)
    applied, changed = with_taught(pool, [taught.clean_entry(DIVE)])
    assert changed == 1 and len(applied) == len(pool)
    assert next(c for c in applied if c["name"] == "Dive Tester")["oracle_text"].startswith("When this creature enters")
    assert with_taught(pool, []) == (pool, 0)
