"""Big boards (perf): Adrix and Nev with Scute Swarms. The speed-ups keep every answer exactly as before: what a kept read pass
serves after a change is what a fresh derivation says (a static ability entering and leaving, a counter, an Equipment attached,
a control change), the facts a pass keeps are read again after a table action or a new effect, and the cheaper copies and
snapshots equal the ones they replace. With the real card database: the swarm board plays out with replay and a save/load round
trip, and a land drop derives each permanent a bounded number of times per trigger (a count, so the guard is not timing-flaky)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from app.game.rules_state import Capture, ContinuousEffect, PendingTrigger, snapshot
from app.rules import layers, read_pass
from app.rules.characteristics import AbilityText, Characteristics, evolve
from app.rules.plan import READ_REUSE_FROM, Plan
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_permissions import build


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database(fixture_cards(), settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def big_table(cards):
    s = build(cards, [(10, "Forest"), (1, "Master of Etherium"), (1, "Behemoth Sledge")])
    act(s, "p1", type="create_token", player="p1", count=READ_REUSE_FROM, stacked=False,
        token={"name": "Insect", "type_line": "Token Artifact Creature — Insect", "power": "1", "toughness": "1", "colors": []})
    return s


def named(plan, name):
    return next(c for c in plan.state.cards.values() if c.name == name and c.owner == "p1")


def pt(plan, card):
    """The insect's power/toughness from a (kept) read pass, checked against a derivation outside any pass."""
    with plan.reading():
        kept = plan.ch(card).pt
    assert read_pass.current(plan.state, plan.info) is None
    assert plan.ch(card).pt == kept  # (no pass: everything read afresh)
    return kept


# -- Characteristics copies ---------------------------------------------------------------------------------------------------
def test_evolve_is_dataclasses_replace():
    ch = Characteristics(name="Bear", types=frozenset({"Creature"}), power="2", toughness="2",
                         abilities=(AbilityText(index=0, text="Flying", kind="keywords", keywords=("flying",)),))
    marker = object()
    for changes in ({}, {"pt": (3, 3)}, {"name": "Cub", "granted": frozenset({"trample"}), "lost": frozenset({"flying"})},
                    {"name_test": marker, "object_counters": frozenset({"+1/+1"})}):
        want, got = dataclasses.replace(ch, **changes), evolve(ch, **changes)  # type: ignore[arg-type]
        assert type(got) is Characteristics and got == want and hash(got) == hash(want)
        assert list(vars(got).items()) == list(vars(want).items())  # every field, in field order (name_test too: compare=False)
    assert evolve(ch).abilities is ch.abilities  # (a copy of the fields, like replace: no deep copy)
    with pytest.raises(TypeError):
        evolve(ch, not_a_field=1)  # type: ignore[arg-type]


# -- snapshots of a step's table ----------------------------------------------------------------------------------------------
def test_a_steps_snapshots_read_blockers_and_attachments_like_one_card_at_a_time(cards):
    s = big_table(cards)
    state = s.state
    bugs = [c for c in state.cards.values() if c.name == "Insect"]
    sledge = named(Plan.view(state, "p1", s.cards), "Behemoth Sledge")
    act(s, "p1", type="move", card_ids=[sledge.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="attach", card_ids=[sledge.id], to=bugs[0].id)
    state = s.state
    a, b, c = (state.cards[x.id] for x in bugs[1:4])  # (test-only combat: c blocks a and b, a second blocker on a)
    c.blocking, c.blocking_more = a.id, [b.id, a.id]
    state.cards[bugs[4].id].blocking = a.id
    caught = Capture(state)
    for cid, snap in caught.snaps.items():
        assert snap.model_dump() == snapshot(state, cid).model_dump(), cid
    assert caught.snaps[a.id].blocked_by_ids == [c.id, bugs[4].id]
    assert caught.snaps[bugs[0].id].attached_objects == {sledge.id: state.rules.object_id(sledge.id)}


# -- kept read passes ---------------------------------------------------------------------------------------------------------
def test_kept_answers_follow_every_change(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    bug, master, sledge = named(plan, "Insect"), named(plan, "Master of Etherium"), named(plan, "Behemoth Sledge")
    assert pt(plan, bug) == (1, 1)
    plan.note("a log line")
    assert pt(plan, bug) == (1, 1)
    plan.do({"type": "move", "card_ids": [master.id], "to": {"player": "p1", "zone": "battlefield"}})  # a static ability enters
    assert pt(plan, bug) == (2, 2)
    plan.do({"type": "counter", "card_ids": [bug.id], "kind": "+1/+1", "delta": 1})  # a counter
    assert pt(plan, bug) == (3, 3)
    plan.do({"type": "move", "card_ids": [sledge.id], "to": {"player": "p1", "zone": "battlefield"}})
    plan.do({"type": "attach", "card_ids": [sledge.id], "to": bug.id})  # an Equipment attached to it
    assert pt(plan, bug) == (5, 5)
    plan.do({"type": "set_controller", "card_ids": [master.id], "player": "p2"})  # a control change: not "you control" any more
    assert pt(plan, bug) == (4, 4)
    plan.do({"type": "move", "card_ids": [sledge.id], "to": {"player": "p1", "zone": "graveyard"}})  # a static ability leaves
    assert pt(plan, bug) == (2, 2)


def test_a_log_line_keeps_the_pass_and_a_table_action_ends_it(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    with plan.reading() as first:
        pass
    plan.note("nothing on the table changed")
    with plan.reading() as again:
        assert again is first
    assert plan.steps[-1]["type"] == "rules_log"  # (still a step of the action, replayed like any other)
    plan.do({"type": "tap", "card_ids": [named(plan, "Insect").id], "tapped": True})
    with plan.reading() as after:
        assert after is not first


def test_waiting_triggers_and_step_stamps_keep_the_pass_other_rules_changes_end_it(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    bug = named(plan, "Insect")
    with plan.reading() as first:
        pass
    plan.rules.pending_triggers.append(PendingTrigger(id="t1", controller="p1", source_card=bug.id, source_object=plan.oid(bug),
                                                      name="Insect", ability={"kind": "triggered", "effects": []}))
    plan.rules.cause110g, plan.rules.craft110b = "p1", True
    with plan.reading() as again:
        assert again is first
    plan.rules.lost["p2"] = "test"
    with plan.reading() as after:
        assert after is not first


def test_the_attachment_fact_is_read_again_after_a_table_action_in_the_same_pass(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    bug, sledge = named(plan, "Insect"), named(plan, "Behemoth Sledge")
    assert layers.attached_hosts(plan.state) is None  # (outside a pass: the caller reads the cards)
    with plan.reading():
        assert bug.id not in (layers.attached_hosts(plan.state) or ())
        plan.do({"type": "move", "card_ids": [sledge.id], "to": {"player": "p1", "zone": "battlefield"}})
        plan.do({"type": "attach", "card_ids": [sledge.id], "to": bug.id})
        assert bug.id in (layers.attached_hosts(plan.state) or ())


def test_the_effects_index_follows_new_effects_and_table_actions(cards):
    s = big_table(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    bug = named(plan, "Insect")
    oid = plan.oid(bug)
    assert read_pass.effects_by_object(plan.state) is None  # (outside a pass)
    with plan.reading():
        first = read_pass.effects_by_object(plan.state)
        assert first is not None and oid not in first and layers.affecting(plan.state, bug, plan.info) == []
        pump = ContinuousEffect(id="test-pump", affected=[oid], layer="7c", controller="p1", power=2, toughness=2)
        plan.rules.effects.append(pump)  # (a new effect: read again)
        assert [e.id for e in layers.affecting(plan.state, bug, plan.info)] == ["test-pump"]
        index = read_pass.effects_by_object(plan.state)
        assert index is not None and index is not first and index[oid] == [pump]
        plan.do({"type": "set_life", "player": "p2", "value": 39})  # (a table action: read again)
        assert read_pass.effects_by_object(plan.state) is not index


# -- the swarm board (real card database) -------------------------------------------------------------------------------------
@pytest.fixture()
def real_cards():
    from app.cards.images import ImageStore
    from app.cards.repository import CardRepository

    db = Path(__file__).resolve().parents[2] / "data" / "cards.sqlite"
    if not db.is_file():
        pytest.skip("needs the real card database at data/cards.sqlite")
    repo = CardRepository(db, ImageStore(db.parent / "images"))
    yield repo
    repo.close()


def swarm(cards, n):
    """Adrix and Nev, ``n`` Scute Swarms and six Forests on the battlefield, a seventh Forest in hand (landfall ×n, each token doubled)."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Adrix and Nev, Twincasters", [(n, "Scute Swarm"), (8, "Forest")])
    bob = deck(cards, "Krenko, Mob Boss", [(10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    mine = lambda name: [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == name]  # noqa: E731
    act(s, "p1", type="move", card_ids=mine("Adrix and Nev, Twincasters") + mine("Scute Swarm") + mine("Forest")[:6],
        to={"player": "p1", "zone": "battlefield"})
    forest = mine("Forest")[6]
    act(s, "p1", type="move", card_ids=[forest], to={"player": "p1", "zone": "hand"})
    return s, forest


def resolve_all(s):
    while s.state.zones.get("stack"):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")


def test_the_swarm_board_plays_out_and_replays(real_cards):
    from tests.wave9c_kit import check

    s, forest = swarm(real_cards, 6)
    act(s, "p1", type="play_land", card_id=forest)
    resolve_all(s)
    swarms = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Scute Swarm"]
    assert len(swarms) == 6 + 2 * 6  # seven lands: each landfall makes a copy of Scute Swarm, doubled by Adrix and Nev
    assert sum(c.is_token for c in swarms) == 12
    check(s)


def test_a_big_land_drop_derives_each_permanent_a_bounded_number_of_times(real_cards, monkeypatch):
    s, forest = swarm(real_cards, 24)
    calls = [0]
    real = layers._derive

    def counted(*args, **kw):  # type: ignore[no-untyped-def]
        calls[0] += 1
        return real(*args, **kw)

    monkeypatch.setattr(layers, "_derive", counted)
    act(s, "p1", type="play_land", card_id=forest)
    board = len(s.state.zones["p1:battlefield"])
    assert board == 1 + 24 * 3 + 7 and not s.state.zones.get("stack")
    # 24 triggers on a board growing to 80: about 2.8 derivations per permanent per trigger (4.4 before the big-board work, which
    # derived the whole board again for each Strict Proctor check, log line and waiting trigger); a regression to that shows here
    assert calls[0] / 24 / board < 3.5, calls[0]


def test_passing_through_the_steps_derives_each_permanent_a_bounded_number_of_times(cards, monkeypatch):
    """-- big boards (step scans) -- every step's start scans the whole battlefield (step triggers, skipped steps, what can be
    attacked): each scan derives the board once in a read pass, not each permanent from scratch, which rebuilt the statics key over
    every card per derivation (a 360-card table took 8-12 s to pass priority into the next turn)."""
    s = big_table(cards)
    board = sum(len(ids) for z, ids in s.state.zones.items() if z.endswith(":battlefield"))
    assert board >= READ_REUSE_FROM
    calls = [0]
    real = layers._derive

    def counted(*args, **kw):  # type: ignore[no-untyped-def]
        calls[0] += 1
        return real(*args, **kw)

    monkeypatch.setattr(layers, "_derive", counted)
    steps = [s.state.turn.phase]
    for _ in range(3):  # main 1 → combat → main 2 → end → the next player's turn
        act(s, s.state.rules.priority, type="pass_priority")
        steps.append(s.state.turn.phase)
    assert steps[-1] == "main2" and s.state.turn.active_player == "p2"
    # about 10 derivations per permanent per pass (16 before: the scans derived every permanent outside a read pass); a count, not a time
    assert calls[0] / board / 3 < 13, calls[0]
