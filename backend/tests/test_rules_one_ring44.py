"""Canonical One Ring chapters and saved native Ring choice."""

import json

import pytest

from tests.game_helpers import act
from tests.test_rules_conditional_prevention import cast, choose
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game
from tests.test_rules_wave30m_durations import to_phase


@pytest.mark.parametrize("bearer", ["Grizzly Bears", "Captain Sisay"])
def test_first_chapter_real_choice_then_current_power_mill(cards, bearer):
    s = game(cards, ["One Ring to Rule Them All", "Captain Sisay"])
    bear = put(s, "Grizzly Bears", "battlefield")
    captain = put(s, "Captain Sisay", "battlefield")
    source = cast(s, "One Ring to Rule Them All")
    assert s.state.rules.decision
    before = {p: len(s.state.zones[p + ":library"]) for p in s.state.players}
    selected = bear if bearer == "Grizzly Bears" else captain
    choose(s, [selected.id])
    assert all(len(s.state.zones[p + ":library"]) == before[p] - 2 for p in before)
    assert s.state.rules.ring_tempted["p1"] == 1
    assert source.zone == "p1:battlefield" and source.counters.get("lore") == 1
    roundtrip(s)


def test_no_creature_still_tempted_mills_zero(cards):
    s = game(cards, ["One Ring to Rule Them All"])
    source = cast(s, "One Ring to Rule Them All")
    assert not s.state.rules.decision
    assert s.state.rules.ring_tempted["p1"] == 1 and "p1" not in s.state.rules.ring_bearers
    assert all(not s.state.zones[p + ":graveyard"] for p in s.state.players)
    assert source.zone == "p1:battlefield"
    roundtrip(s)


def test_negative_ring_bearer_power_mills_zero(cards):
    s = game(cards, ["One Ring to Rule Them All", "Dizzy Spell"])
    bearer = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Dizzy Spell", [bearer.id], pid="p2")
    source = cast(s, "One Ring to Rule Them All")
    assert s.state.rules.ring_tempted["p1"] == 1 and source.counters.get("lore") == 1
    assert all(
        not any(c.zone == p + ":graveyard" and c.name != "Dizzy Spell" for c in s.state.cards.values())
        for p in s.state.players
    )
    roundtrip(s)


def test_natural_all_three_chapters_legendary_and_individual_graveyard_counts(cards):
    from app.rules.plan import Plan

    s = game(cards, ["One Ring to Rule Them All", "Captain Sisay"])
    ours = put(s, "Grizzly Bears", "battlefield")
    captain = put(s, "Captain Sisay", "battlefield")
    victims = [
        put(s, "Grizzly Bears", "battlefield", "p2"),
        put(s, "Llanowar Elves", "battlefield", "p2"),
        put(s, "Grizzly Bears", "battlefield", "p3"),
    ]
    source = cast(s, "One Ring to Rule Them All")
    choose(s, [ours.id])
    to_phase(s, "main1", turn=7)
    settle(s)
    assert ours.zone == "p1:battlefield" and captain.zone == "p1:battlefield"
    assert all(c.zone == c.owner + ":graveyard" for c in victims)
    plan = Plan(s.state, "p1", cards, None)
    expected = {
        p: sum(plan.ch(s.state.cards[c]).is_creature for c in s.state.zones[p + ":graveyard"])
        for p in ["p2", "p3"]
    }
    assert expected["p2"] != expected["p3"]
    before = {p: s.state.players[p].life for p in expected}
    to_phase(s, "main1", turn=10)
    settle(s)
    assert source.zone == "p1:graveyard"
    assert all(s.state.players[p].life == before[p] - expected[p] for p in expected)
    roundtrip(s)


def test_chapter_trigger_survives_actual_source_disenchant(cards):
    s = game(cards, ["One Ring to Rule Them All", "Captain Sisay", "Disenchant"])
    bear = put(s, "Grizzly Bears", "battlefield")
    put(s, "Captain Sisay", "battlefield")
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    source = cast(s, "One Ring to Rule Them All", resolve=False)
    for _ in range(8):
        if source.zone != "stack":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.stack and not s.state.rules.decision
    cast(s, "Disenchant", [source.id], pid="p2")
    before = {p: len(s.state.zones[p + ":library"]) for p in s.state.players}
    choose(s, [bear.id])
    assert source.zone == "p1:graveyard"
    assert all(len(s.state.zones[p + ":library"]) == before[p] - 2 for p in before)
    roundtrip(s)


def test_real_ring_choice_cold_without_adapter(cards, tmp_path):
    import subprocess
    import sys

    s = game(cards, ["One Ring to Rule Them All", "Captain Sisay"])
    bear = put(s, "Grizzly Bears", "battlefield")
    put(s, "Captain Sisay", "battlefield")
    cast(s, "One Ring to Rule Them All")
    assert s.state.rules.decision
    before = {p: len(s.state.zones[p + ":library"]) for p in s.state.players}
    saved = tmp_path / "pending.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys,json
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
choose(s,[sys.argv[3]])
before=json.loads(sys.argv[4])
assert all(len(s.state.zones[p+':library'])==before[p]-2 for p in before)
assert s.state.rules.ring_tempted['p1']==1 and not s.state.rules.decision
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), bear.id, json.dumps(before)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_all_printed_full(cards):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve("One Ring to Rule Them All"))
    assert result.level == "FULL", result.manual_parts
