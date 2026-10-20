"""Tangled Colony counts actual damage to its dying incarnation, including overkill."""

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import activate, cast
from tests.test_rules_designations import roundtrip
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


def rats(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Rat"]


def setup(cards):
    s = game(
        cards,
        [
            "Tangled Colony",
            "Lightning Bolt",
            "Prodigal Pyromancer",
            "Murder",
            "Cloudshift",
            "Anointed Procession",
        ],
    )
    colony = cast(s, "Tangled Colony")
    return s, colony


def test_full_canonical_colony(cards):
    assert coverage.of_card_data(cards.resolve("Tangled Colony")).level == "FULL"


def test_overkill_creates_actual_damage_count_with_native_rat_abilities(cards):
    s, colony = setup(cards)
    cast(s, "Lightning Bolt", [colony.id], pid="p2")
    assert colony.zone == "p1:graveyard" and len(rats(s)) == 3
    plan = Plan(s.state, "p1", cards, None)
    assert all(
        plan.ch(c).pt == (1, 1) and plan.ch(c).colors == {"B"} and "Rat" in plan.ch(c).subtypes
        for c in rats(s)
    )
    assert all(any("can't block" in a.text for a in plan.ch(c).abilities) for c in rats(s))
    roundtrip(s)


@pytest.mark.parametrize("prevented", [False, True])
def test_destroy_counts_only_actual_preceding_damage(cards, prevented):
    s, colony = setup(cards)
    red = cast(s, "Prodigal Pyromancer")
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main1", turn=7)
    if prevented:
        cast(s, "Healing Salve", [colony.id], modes=[1])
    activate(s, red, "deals 1 damage", [colony.id])
    cast(s, "Murder", [colony.id], pid="p2")
    assert len(rats(s)) == (0 if prevented else 1)
    roundtrip(s)


def test_new_incarnation_cannot_count_prior_damage(cards):
    s, colony = setup(cards)
    red = cast(s, "Prodigal Pyromancer")
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main1", turn=7)
    activate(s, red, "deals 1 damage", [colony.id])
    cast(s, "Cloudshift", [colony.id])
    cast(s, "Murder", [colony.id], pid="p2")
    assert rats(s) == []
    roundtrip(s)


def test_native_token_multiplier_applies_to_damage_sized_count(cards):
    s, colony = setup(cards)
    cast(s, "Anointed Procession")
    cast(s, "Lightning Bolt", [colony.id], pid="p2")
    assert len(rats(s)) == 6
    roundtrip(s)


def test_death_without_damage_creates_no_rats(cards):
    s, colony = setup(cards)
    cast(s, "Murder", [colony.id], pid="p2")
    assert rats(s) == []
    roundtrip(s)


def test_fresh_process_resolves_saved_death_from_damage_history(cards, tmp_path):
    import subprocess
    import sys

    s, colony = setup(cards)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    act(s, "p2", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    cast(s, "Lightning Bolt", [colony.id], pid="p2", resolve=False)
    for _ in range(12):
        if colony.zone == "p1:graveyard":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert colony.zone == "p1:graveyard" and not rats(s)
    saved = tmp_path / "tangled46.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle, roundtrip
repo=CardRepository(Path(sys.argv[2]), ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
assert len([c for c in s.state.cards.values() if c.is_token and c.name=='Rat'])==3
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("use_token", [False, True])
def test_printed_colony_and_created_rat_cannot_actually_block(cards, use_token):
    from app.game.errors import ActionError
    from tests.test_rules_conditional_prevention import attack
    from tests.test_rules_designations import put
    from tests.test_rules_wave30m_durations import to_phase

    s, colony = setup(cards)
    if use_token:
        cast(s, "Lightning Bolt", [colony.id], pid="p2")
    blocker = rats(s)[0] if use_token else colony
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    attack(s, [bear], pid="p2", target="p1", turn=5)
    to_phase(s, "declare_blockers")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match="block"):
        act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": bear.id}])
    assert s.state.model_dump_json() == before
    roundtrip(s)
