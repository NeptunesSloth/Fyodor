"""Canonical Revenant uses completed native surveil-kept receipts."""

import pytest

from tests.test_rules_conditional_prevention import cast, choose
from tests.test_rules_designations import roundtrip
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


@pytest.mark.parametrize("discarded", [0, 1, 2])
def test_actual_etb_native_kept_count(cards, discarded):
    s = game(cards, ["Starving Revenant"])
    source = cast(s, "Starving Revenant")
    d = s.state.rules.decision
    assert d and d.kind == "choose_cards" and len(d.options) == 2
    before = len(s.state.zones["p1:library"])
    choose(s, [o.id for o in d.options[:discarded]])
    assert s.state.players["p1"].life == 40 - 3 * (2 - discarded)
    assert len(s.state.zones["p1:library"]) == before - 2
    assert source.zone == "p1:battlefield" and not s.state.rules.decision
    roundtrip(s)


def test_native_archive_each_kept_card_draw_then_lose(cards):
    s = game(cards, ["Starving Revenant", "Alhammarret's Archive"])
    cast(s, "Alhammarret's Archive")
    cast(s, "Starving Revenant")
    before = len(s.state.zones["p1:library"])
    choose(s, [])
    assert len(s.state.zones["p1:library"]) == before - 4
    assert s.state.players["p1"].life == 34
    roundtrip(s)


def test_legacy_missing_kept_receipt_stops_before_any_draw_or_life_loss(cards):
    s = game(cards, ["Starving Revenant"])
    cast(s, "Starving Revenant")
    d = s.state.rules.decision
    d.resume.pop("as_kept")
    before = len(s.state.zones["p1:library"])
    choose(s, [])
    assert s.state.rules.decision and s.state.rules.decision.kind == "manual_resolution"
    assert s.state.players["p1"].life == 40 and len(s.state.zones["p1:library"]) == before
    choose(s, ["done"])
    assert not s.state.rules.decision and s.state.players["p1"].life == 40
    roundtrip(s)


def test_actual_descend8_sees_eighth_permanent_from_surveil_before_drawing(cards):
    from app.rules.plan import Plan
    from tests.game_helpers import act
    from tests.test_rules_designations import put

    s = game(cards, ["Starving Revenant"])
    plan = Plan(s.state, "p1", cards, None)
    selected = [
        c.id
        for c in s.state.cards.values()
        if c.owner == "p1"
        and c.zone == "p1:library"
        and c.name not in ["Starving Revenant", "Grizzly Bears", "Llanowar Elves"]
        and plan.ch(c).is_permanent_card
    ][:7]
    assert len(selected) == 7
    act(s, "p1", type="move", card_ids=selected, to={"player": "p1", "zone": "graveyard"})
    bear = put(s, "Grizzly Bears", "hand")
    elf = put(s, "Llanowar Elves", "hand")
    act(
        s,
        "p1",
        type="move",
        card_ids=[bear.id, elf.id],
        to={"player": "p1", "zone": "library"},
        position="top",
    )
    cast(s, "Starving Revenant")
    choose(s, [bear.id])
    d = s.state.rules.decision
    assert d, "Descend8 must trigger on the actual draw after the eighth permanent arrived"
    choose(s, ["p2"])
    assert s.state.players["p1"].life == 38 and s.state.players["p2"].life == 39
    assert elf.zone == "p1:hand"
    roundtrip(s)


def test_actual_surveil_shuffle_then_only_kept_card_is_drawn(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put

    s = game(cards, ["Starving Revenant", "Progenitus"])
    put(s, "Starving Revenant", "hand")
    progenitus = put(s, "Progenitus", "hand")
    kept = put(s, "Healing Salve", "hand")
    act(
        s,
        "p1",
        type="move",
        card_ids=[progenitus.id, kept.id],
        to={"player": "p1", "zone": "library"},
        position="top",
    )
    cast(s, "Starving Revenant")
    choose(s, [progenitus.id])
    assert kept.zone == "p1:hand" and progenitus.zone == "p1:library"
    assert s.state.players["p1"].life == 37
    roundtrip(s)


def test_empty_library_surveil_attempts_no_draw_and_no_life_loss(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put

    s = game(cards, ["Starving Revenant"])
    put(s, "Starving Revenant", "hand")
    act(
        s, "p1", type="move", card_ids=list(s.state.zones["p1:library"]), to={"player": "p1", "zone": "exile"}
    )
    source = cast(s, "Starving Revenant")
    assert source.zone == "p1:battlefield" and s.state.players["p1"].life == 40
    assert not s.state.rules.decision and "p1" not in s.state.rules.lost
    roundtrip(s)


def test_actual_draw_replacement_preserves_each_kept_card_life_loss(cards):
    s = game(cards, ["Starving Revenant", "Notion Thief"])
    cast(s, "Notion Thief", pid="p2")
    cast(s, "Starving Revenant")
    before = {p: len(s.state.zones[p + ":library"]) for p in ["p1", "p2"]}
    choose(s, [])
    assert len(s.state.zones["p1:library"]) == before["p1"]
    assert len(s.state.zones["p2:library"]) == before["p2"] - 2
    assert s.state.players["p1"].life == 34
    roundtrip(s)


def test_source_destroyed_before_trigger_still_surveils_draws_loses(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s = game(cards, ["Starving Revenant", "Murder"])
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    source = cast(s, "Starving Revenant", resolve=False)
    for _ in range(10):
        if source.zone != "stack":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert source.zone == "p1:battlefield" and s.state.rules.stack
    cast(s, "Murder", [source.id], pid="p2")
    assert source.zone == "p1:graveyard" and s.state.rules.decision
    choose(s, [])
    settle(s)
    assert s.state.players["p1"].life == 34
    roundtrip(s)


@pytest.mark.parametrize("stage", ["surveil", "order"])
def test_true_cold_native_surveil_or_order_then_individual_draw_loss(cards, tmp_path, stage):
    import subprocess
    import sys

    from tests.game_helpers import act

    s = game(cards, ["Starving Revenant"])
    cast(s, "Starving Revenant")
    if stage == "order":
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
        assert s.state.rules.decision.resume["step"] == "order_library"
    saved = tmp_path / "revenant.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
choose(s,[o.id for o in reversed(d.options)] if sys.argv[3]=='order' else [])
assert not s.state.rules.decision and s.state.players['p1'].life==34
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), stage], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_descend8_rechecks_actual_permanent_count_at_resolution(cards):
    from app.rules.plan import Plan
    from tests.game_helpers import act
    from tests.test_rules_designations import put, settle

    s = game(cards, ["Starving Revenant", "Noxious Revival"])
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    plan = Plan(s.state, "p1", cards, None)
    selected = [
        c.id
        for c in s.state.cards.values()
        if c.owner == "p1"
        and c.zone == "p1:library"
        and c.name not in ["Starving Revenant", "Grizzly Bears", "Llanowar Elves"]
        and plan.ch(c).is_permanent_card
    ][:7]
    assert len(selected) == 7
    act(s, "p1", type="move", card_ids=selected, to={"player": "p1", "zone": "graveyard"})
    bear = put(s, "Grizzly Bears", "hand")
    elf = put(s, "Llanowar Elves", "hand")
    act(
        s,
        "p1",
        type="move",
        card_ids=[bear.id, elf.id],
        to={"player": "p1", "zone": "library"},
        position="top",
    )
    cast(s, "Starving Revenant")
    choose(s, [bear.id])
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
    assert s.state.rules.stack
    cast(s, "Noxious Revival", [selected[0]], pid="p2")
    settle(s)
    assert s.state.players["p1"].life == 37 and s.state.players["p2"].life == 40
    roundtrip(s)


def test_actual_complete_printed_card(cards):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve("Starving Revenant"))
    assert result.level == "FULL", result.manual_parts
