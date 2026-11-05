"""Big boards, round 3 (perf): Adrix and Nev with Scute Swarms (tools/bench_big_board.py). The speed-ups keep every answer exactly as
before:

* a kept read pass compares the rules fields that grow with every step (the events, the last known information, the stack, the turn's
  history) and the per-step bookkeeping only if it read them (read_pass.WATCHED): a pass that never read one outlives its change, one
  that read it does not, also when it read it in a nested pass; those fields still read, write, copy and save like plain fields;
* the statics table's key serialises the copy effects' recipes in one call, and still tells a changed recipe apart;
* a step's capture builds each snapshot when first asked for, from the fields read at the capture: the same snapshot, and ``track``
  reads the fields of the rest without building them;
* the swarm board plays out with replay and a save/load round trip (the real-card-database version in test_rules_perf_big_boards is
  skipped without that database: this one runs on the fixtures, with the same Oracle text)."""

from __future__ import annotations

import copy
import pickle

import pytest

from app.game.rules_state import Capture, Event, RulesState, TurnFact, TurnLog, snapshot
from app.rules import layers, read_pass
from app.rules.plan import READ_REUSE_FROM, Plan
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_permissions import build
from tests.wave9c_kit import check
from tools import bench_big_board as bench


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *bench.EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def big_table(cards):
    s = build(cards, [(10, "Forest")])
    act(s, "p1", type="create_token", player="p1", count=READ_REUSE_FROM, stacked=False,
        token={"name": "Insect", "type_line": "Token Artifact Creature — Insect", "power": "1", "toughness": "1", "colors": []})
    return s


def insect(plan):
    return next(c for c in plan.state.cards.values() if c.name == "Insect")


# -- watched rules fields --------------------------------------------------------------------------------------------------------
def test_watched_fields_read_write_copy_and_save_like_plain_fields():
    assert all(isinstance(RulesState.__dict__[n], read_pass._Watched) for n in read_pass.WATCHED)
    assert all(isinstance(TurnLog.__dict__[n], read_pass._Watched) for n in read_pass.WATCHED_LOG)
    r = RulesState()
    r.events = [Event(batch=1, kind="zone_change", card="c1")]
    r.batch = 3
    r.events.append(Event(batch=2, kind="tapped", card="c2"))
    r.turn_log.facts.append(TurnFact(kind="token", player="p1"))
    assert r.__dict__["events"] is r.events and [e.card for e in r.events] == ["c1", "c2"] and r.batch == 3
    assert {"events", "batch"} <= r.model_fields_set  # (assignment still goes through pydantic: exclude_unset dumps are unchanged)
    again = RulesState.model_validate(r.model_dump(mode="json"))
    assert again == r and again.model_dump_json() == r.model_dump_json() and len(again.turn_log.facts) == 1
    for twin in (r.model_copy(deep=True), copy.deepcopy(r), pickle.loads(pickle.dumps(r))):
        assert twin == r and twin.events is not r.events and twin.events == r.events
    assert r.model_copy().events is r.events


def test_a_kept_pass_outlives_a_change_to_a_watched_field_it_never_read(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    bug = insect(plan)
    with plan.reading() as first:
        assert plan.ch(bug).toughness == "1"
    assert first.seen is not None and "events" not in first.seen and "batch" not in first.seen
    plan.rules.batch += 1  # per-step bookkeeping and a new event: nothing the pass read
    plan.rules.events.append(Event(batch=plan.rules.batch, kind="tapped", card=bug.id))
    with plan.reading() as again:
        assert again is first
        assert plan.ch(bug).toughness == "1"
    plan.rules.lost["p2"] = "test"  # a field outside WATCHED: compared whole, as before
    with plan.reading() as after:
        assert after is not first


def test_a_kept_pass_that_read_a_watched_field_ends_when_it_changes(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    bug = insect(plan)
    with plan.reading() as first:
        assert plan.rules.events is not None and plan.rules.turn_log.facts is not None
    assert {"events", "log.facts"} <= set(first.seen or ())
    with plan.reading() as again:
        assert again is first  # (read, but unchanged)
    plan.rules.turn_log.facts.append(TurnFact(kind="token", player="p1"))  # changed in place: compared by value
    with plan.reading() as after:
        assert after is not first
        assert after.seen == {}  # (a new pass: nothing read yet)
        assert plan.rules.events is not None
    plan.rules.events.append(Event(batch=plan.rules.batch, kind="tapped", card=bug.id))
    with plan.reading() as last:
        assert last is not after


def test_a_watched_field_read_in_a_nested_pass_is_noted_in_the_kept_one(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    other = build(cards, [(10, "Forest")])
    with plan.reading() as first, read_pass.scope(other.state, other.cards):  # (a pass over another table, open inside the kept one)
        assert read_pass.current(plan.state, plan.info) is None
        assert plan.rules.stack is not None  # read while the kept pass is open: what it keeps may depend on it
    assert first.seen is not None and "stack" in first.seen
    with read_pass.scope(other.state, other.cards):
        assert other.state.rules.lki is not None  # (no kept pass open: noted nowhere)
    assert "lki" not in first.seen


def test_a_pass_that_is_not_kept_notes_nothing(cards):
    s = build(cards, [(10, "Forest")])  # (a small table: nothing kept)
    plan = Plan(s.state, "p1", s.cards, None)
    with plan.reading() as sc:
        assert plan.rules.events is not None
    assert sc.seen is None and not getattr(read_pass._WATCHING, "passes", None)


# -- the swarm board ---------------------------------------------------------------------------------------------------------------
def test_the_swarm_board_plays_out_and_replays(cards):
    s, forest = bench.table(cards, 6)
    act(s, "p1", type="play_land", card_id=forest)
    bench.resolve_all(s)
    swarms = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Scute Swarm"]
    assert len(swarms) == 6 + 2 * 6 and sum(c.is_token for c in swarms) == 12  # each landfall: a copy of Scute Swarm, doubled
    check(s)


def test_the_statics_key_tells_copy_recipes_apart(cards):
    s, forest = bench.table(cards, 2)
    act(s, "p1", type="play_land", card_id=forest)
    bench.resolve_all(s)
    state, info = s.state, s.cards
    table = layers.statics(state, info)
    layers._STATIC_CACHE.clear()
    assert layers.statics(state, info) == table and len(layers._STATIC_CACHE) == 1  # (read afresh: the same table, one key)
    assert layers.statics(state, info) == table and len(layers._STATIC_CACHE) == 1  # (the same key again)
    copied = next(e for e in state.rules.effects if e.layer == "1" and e.copy_recipe is not None)
    copied.copy_recipe = copied.copy_recipe.model_copy(update={"source": "Another source"})
    layers.statics(state, info)
    assert len(layers._STATIC_CACHE) == 2  # a changed recipe is a new key


# -- a step's capture --------------------------------------------------------------------------------------------------------------
def test_a_capture_builds_each_snapshot_when_first_asked_for(cards):
    s = big_table(cards)
    state = s.state
    bug = next(c for c in state.cards.values() if c.name == "Insect")
    caught = Capture(state)
    want = snapshot(state, bug.id)
    viewed = dict(caught.fields())  # (what ``track`` compares: no snapshot built)
    assert set(viewed) == set(caught.snaps) and not caught.snaps.built  # type: ignore[attr-defined]
    for name in ("zone", "counters", "tapped", "attached_to", "attached_player", "face", "face_down", "object_id", "merged"):
        assert getattr(viewed[bug.id], name) == getattr(want, name), name
    state.cards[bug.id].counters["+1/+1"] = 2  # (the step changes the card after the capture: the capture keeps what it read)
    snap = caught.snaps[bug.id]
    assert snap.model_dump() == want.model_dump() and snap.counters == {}  # (built from the fields read at the capture)
    assert caught.snaps[bug.id] is snap and caught.snaps.get(bug.id) is snap  # (then the same object for every reader)
    snap.attached = ["changed by a reader"]
    assert dict(caught.fields())[bug.id] is snap  # (a snapshot built, and changed since: ``fields`` gives that one)
    assert list(dict(caught.snaps)) == list(viewed)  # (a copy of the whole map builds them all, in the same order)
