"""Native pure replacement planner staging; no production registry mutations."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import replace
from app.rules.life_changes44 import plan_changes
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put


@pytest.fixture()
def cards(settings):
    rows = json.loads((Path(__file__).parent / "fixtures/life_changes44_cards.json").read_text())
    base = {c["name"]: c for c in fixture_cards()}
    for i, row in enumerate(rows):
        base[row["name"]] = card(row["name"], number=str(i), **{k: v for k, v in row.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def scene(cards):
    s = build(cards, ["Alhammarret's Archive", "Cleric Class", "Platinum Angel"])
    for name in ("Alhammarret's Archive", "Cleric Class", "Platinum Angel"):
        put(s, name, "battlefield")
    act(s, "p1", type="life", player="p1", delta=-40)
    return s


@pytest.mark.parametrize("first,expected", [("Archive", 11), ("Cleric Class", 12)])
def test_one_mixed_plan_freezes_every_event_before_asking_and_never_commits(cards, first, expected):
    s = scene(cards)
    p = Plan(s.state, "p1", cards, None)
    before = p.state.model_dump_json()
    # Input order intentionally puts the losing player first: native APNAP still asks p1.
    changes = [("p2", -30), ("p1", 5)]
    q = plan_changes(p, changes, answers={}, ask=True)
    assert isinstance(q, replace.Ask) and q.chooser == "p1"
    assert p.state.model_dump_json() == before and p.steps == []
    chosen = next(c.id for c in q.applicable if first in c.label)
    result = plan_changes(p, changes, answers={q.fp: chosen}, ask=True)
    assert not isinstance(result, replace.Ask)
    finals, planner = result
    assert [(ev["player"], ev["kind"], ev["n"]) for _, out in finals for ev in out] == [
        ("p1", "life", expected),
        ("p2", "life_loss", 30),
    ]
    assert len({c.id for c in planner.cands}) == len(planner.cands)
    assert p.state.model_dump_json() == before and p.steps == []


def test_gain_to_loss_reenters_native_loss_candidates_without_duplicate_effect(cards):
    s = scene(cards)
    # Native temporary loss replacement record; same engine candidate/planner protocol.
    p = Plan(s.state, "p1", cards, None)
    remedy = replace.add_record(
        p,
        event="life",
        match={"who": "you"},
        op={"do": "lose"},
        controller="p1",
        source=None,
        source_card=None,
        label="gain converted",
    )
    loss = replace.add_record(
        p,
        event="life_loss",
        match={"who": "you"},
        op={"do": "mul", "n": 2},
        controller="p1",
        source=None,
        source_card=None,
        label="loss doubled",
    )
    # Gate out the unrelated Archive/Class in this kernel by removing those real sources.
    for c in list(p.state.cards.values()):
        if c.name in ("Alhammarret's Archive", "Cleric Class") and c.zone.endswith(":battlefield"):
            p.do({"type": "move", "card_ids": [c.id], "to": {"zone": "graveyard", "player": c.owner}})
    before = p.state.model_dump_json()
    steps = len(p.steps)
    result = plan_changes(p, [("p1", 3), ("p2", -4)], answers={}, ask=True)
    assert not isinstance(result, replace.Ask)
    finals, planner = result
    assert [(e["player"], e["kind"], e["n"]) for _, out in finals for e in out] == [
        ("p1", "life_loss", 6),
        ("p2", "life_loss", 4),
    ]
    assert planner.used.count("r:" + remedy["id"]) == 1 and planner.used.count("r:" + loss["id"]) == 1
    assert p.state.model_dump_json() == before and len(p.steps) == steps


def stripped_plan(cards):
    s = scene(cards)
    p = Plan(s.state, "p1", cards, None)
    for c in list(p.state.cards.values()):
        if c.name in ("Alhammarret's Archive", "Cleric Class") and c.zone.endswith(":battlefield"):
            p.do({"type": "move", "card_ids": [c.id], "to": {"zone": "graveyard", "player": c.owner}})
    p.do({"type": "life", "player": "p1", "delta": 20})
    return p


def test_native_atomic_action_preserves_distinct_events_group_actual_loss_and_replay(cards):
    from app.game import actions as A
    from app.game import engine
    from app.game.errors import ActionError
    from app.game.resolve import resolve
    from app.rules import life_changes44 as site

    p = stripped_plan(cards)
    p.rules.events = []
    p.steps = []
    before = p.state.model_copy(deep=True)
    p.state.seq += 1  # Native outer intent owns one sequence; its compiled steps share it.
    ctx = {"controller": "p1", "refs": {}}
    request = {
        "mode": "set",
        "actor": "p1",
        "operation": 991,
        "bind": "actual",
        "changes": [["p1", 10], ["p1", -3], ["p2", -5]],
    }
    assert site.change(p, request, then=None, ctx=ctx)
    assert (p.state.players["p1"].life, p.state.players["p2"].life) == (27, 35)
    events = [e for e in p.rules.events if e.kind in ("life_gain", "life_loss")]
    assert len(events) == 3 and len({e.batch for e in events}) == 1
    assert [e.amount for e in events] == [10, 3, 5]
    assert [e.group for e in events] == [0, 991, 991]
    assert ctx["refs"]["actual"]["n"] == 3
    steps = [s for s in p.steps if s["type"] == "rules_life_changes"]
    assert len(steps) == 1 and len(steps[0]["changes"]) == 3
    with pytest.raises(ActionError, match="Only the rules engine"):
        resolve(before, A.parse_action(steps[0]), actor="p1", cards=cards, trusted=False)
    p.do({"type": "rules_sync", "rules": p.rules.model_dump(mode="json")})
    replay = before.model_copy(deep=True)
    engine.apply(replay, A.PassPriority(actor="p1", r=p.steps))
    assert replay.model_dump(mode="json") == p.state.model_dump(mode="json")


@pytest.mark.parametrize("first,expected", [("Archive", 11), ("Cleric Class", 12)])
def test_native_choice_resumes_one_frozen_mixed_request_then_continues_once(
    cards, monkeypatch, first, expected
):
    from app.game.session import GameSession
    from app.rules import life_changes44 as site

    s = scene(cards)
    p = Plan(s.state, "p1", cards, None)

    def finished(plan, then):
        plan.rules.once_per_turn["kernel:finished"] = plan.rules.once_per_turn.get("kernel:finished", 0) + 1

    monkeypatch.setitem(replace.THEN, "kernel_life_finished", finished)
    request = {"mode": "set", "actor": "p1", "operation": 777, "changes": [["p2", -35], ["p1", 5]]}
    then = {"do": "kernel_life_finished", "ctx": {"controller": "p1", "refs": {}}}
    assert not site.change(p, request, then=then)
    assert (p.state.players["p1"].life, p.state.players["p2"].life) == (0, 40)
    assert not any(a["type"] == "rules_life_changes" for a in p.steps)
    s = GameSession(p.state, cards=cards)
    d = s.state.rules.decision
    candidate = next(
        c
        for c in replace.candidates(Plan(s.state, "p1", cards, None), ("life", "life_loss"))
        if first in c.label
    )
    option = next(key for key, val in d.resume["map"].items() if val == candidate.id)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])
    assert s.state.rules.decision is None
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (expected, 5)
    assert s.state.rules.once_per_turn["kernel:finished"] == 1


def test_once_record_is_consumed_only_at_commit_and_not_reapplied_to_next_operation(cards):
    from app.rules import life_changes44 as site

    p = stripped_plan(cards)
    record = replace.add_record(
        p,
        event="life",
        match={"who": "you"},
        op={"do": "mul", "n": 2, "once": True},
        controller="p1",
        source=None,
        source_card=None,
        label="once only",
    )
    request = {"mode": "set", "actor": "p1", "operation": 812, "changes": [["p1", 2], ["p1", 3], ["p2", -1]]}
    assert site.change(p, request, then=None)
    assert p.state.players["p1"].life == 27 and record["spent"]
    assert site.change(p, {**request, "operation": 813, "changes": [["p1", 1]]}, then=None)
    assert p.state.players["p1"].life == 28


def test_two_positive_events_in_one_batch_create_two_native_gain_triggers(cards):
    from app.game.session import GameSession
    from app.rules import life_changes44 as site
    from tests.test_rules_designations import settle

    s = build(cards, ["Ajani's Pridemate"])
    creature = put(s, "Ajani's Pridemate", "battlefield")
    p = Plan(s.state, "p1", cards, None)
    assert site.change(
        p, {"mode": "set", "actor": "p1", "operation": 851, "changes": [["p1", 2], ["p1", 3]]}, then=None
    )
    from app.rules import triggers

    triggers.collect(p)
    triggers.flush(p)
    s = GameSession(p.state, cards=cards)
    settle(s)
    assert s.state.cards[creature.id].counters.get("+1/+1") == 2
    assert s.state.players["p1"].life == 45


@pytest.mark.parametrize(
    "name,stat,initial,expected",
    [("Tree of Redemption", "toughness", 13, 26), ("Evra, Halcyon Witness", "power", 4, 8)],
)
@pytest.mark.parametrize("alter", ["unchanged", "depart", "pt_control"])
@pytest.mark.parametrize("cold", [False, True])
def test_actual_stat_primitive_freezes_before_choice_and_cancels_both_halves_if_source_gone(
    cards, name, stat, initial, expected, alter, cold, tmp_path
):
    from app.game.session import GameSession
    from app.rules import layers
    from tests.test_rules_conditional_prevention import activate
    from tests.test_rules_designations import settle

    s = scene(cards)
    # Add the actual canonical creature as a native card in the deck, then move it.
    # build() must include all actual sources before the game starts.
    s = build(cards, ["Alhammarret's Archive", "Cleric Class", "Platinum Angel", name])
    for n in ("Alhammarret's Archive", "Cleric Class", "Platinum Angel", name):
        put(s, n, "battlefield")
    act(s, "p1", type="set_life", player="p1", value=1)
    creature = next(c for c in s.state.cards.values() if c.name == name)
    s.state.rules.controlled_since[creature.id].turn = 0
    # Native activated ability resolves into the production primitive (staged site only).
    activate(s, creature, "Exchange your life total")
    d = s.state.rules.decision
    assert d and d.kind == "confirm"
    assert s.state.players["p1"].life == 1
    p = Plan(s.state, "p1", cards, None)
    assert p.ch(creature).pt[0 if stat == "power" else 1] == initial
    assert d.resume["site"] == "life_changes44"
    assert d.resume["request"]["stat"]["life"] == 1
    if alter == "depart":
        p.do({"type": "move", "card_ids": [creature.id], "to": {"zone": "graveyard", "player": "p1"}})
    elif alter == "pt_control":
        layers.add_effect(
            p,
            affected=[p.oid(creature)],
            layer="7b",
            power=99 if stat == "power" else None,
            toughness=99 if stat == "toughness" else None,
            duration="permanent",
            controller="p1",
            source=None,
        )
        p.do({"type": "set_controller", "card_ids": [creature.id], "player": "p2"})
    s = GameSession(p.state, cards=cards)
    d = s.state.rules.decision
    candidate = next(
        c
        for c in replace.candidates(Plan(s.state, "p1", cards, None), ("life", "life_loss"))
        if "Archive" in c.label
    )
    option = next(key for key, val in d.resume["map"].items() if val == candidate.id)
    if cold:
        import os
        import subprocess
        import sys

        from app.game.state import GameState

        statefile = tmp_path / "saved.json"
        statefile.write_text(s.state.model_dump_json())
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent)}
        child = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("life_changes44_worker.py")),
                str(statefile),
                str(cards.db_path),
                option,
            ],
            cwd=str(Path(__file__).parent.parent),
            env=env,
            capture_output=True,
            text=True,
        )
        assert child.returncode == 0, child.stdout + child.stderr
        s = GameSession(GameState.model_validate_json(statefile.read_text()), cards=cards)
    else:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])
    settle(s)
    p = Plan(s.state, "p1", cards, None)
    if alter == "depart":
        assert s.state.players["p1"].life == 1
        assert not any(e.layer == "7b" and creature.id in str(e.affected) for e in p.rules.effects)
    else:
        assert s.state.players["p1"].life == expected
        assert p.ch(s.state.cards[creature.id]).pt[0 if stat == "power" else 1] == 1
        assert s.state.cards[creature.id].controller == ("p2" if alter == "pt_control" else "p1")


def test_once_record_planning_does_not_consume_before_later_question(cards):
    from app.rules import life_changes44 as site

    p = stripped_plan(cards)
    once = replace.add_record(
        p,
        event="life",
        match={"who": "you"},
        op={"do": "mul", "n": 2, "once": True},
        controller="p1",
        source=None,
        source_card=None,
        label="once",
    )
    for op in ({"do": "mul", "n": 2}, {"do": "floor"}):
        replace.add_record(
            p,
            event="life_loss",
            match={"who": "opponent"},
            op=op,
            controller="p1",
            source=None,
            source_card=None,
            label=str(op),
        )
    before = p.state.model_dump_json()
    q = site.plan_changes(p, [["p1", 3], ["p2", -50]], answers={}, ask=True)
    assert isinstance(q, replace.Ask) and q.chooser == "p2"
    assert not once.get("spent") and p.state.model_dump_json() == before


def test_exchange_loss_choice_commits_neither_side_before_answer(cards):
    from app.game.session import GameSession
    from app.rules import life_changes44 as site

    p = stripped_plan(cards)
    for op in ({"do": "mul", "n": 2}, {"do": "floor"}):
        replace.add_record(
            p,
            event="life_loss",
            match={"who": "opponent"},
            op=op,
            controller="p1",
            source=None,
            source_card=None,
            label=str(op),
        )
    p.do({"type": "life", "player": "p1", "delta": -40})
    request = {
        "mode": "exchange",
        "participants": ["p1", "p2"],
        "changes": [["p1", 60], ["p2", -60]],
        "actor": "p1",
        "operation": 855,
    }
    assert not site.change(p, request, then={"do": "noop"})
    assert [p.state.players[x].life for x in ("p1", "p2")] == [-20, 40]
    assert not any(x["type"] == "rules_life_changes" for x in p.steps)
    d = p.rules.decision
    assert d.player == "p2"
    s = GameSession(p.state, cards=cards)
    floor = next(c.id for c in replace.candidates(p, ("life_loss",)) if c.op["do"] == "floor")
    option = next(key for key, val in d.resume["map"].items() if val == floor)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[option])
    assert s.state.players["p1"].life == 40
    assert s.state.players["p2"].life == -38
