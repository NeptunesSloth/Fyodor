"""Wicked Akuba targets players damaged by its exact source incarnation."""

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import activate, attack, cast, damage
from tests.test_rules_designations import roundtrip
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game
from tests.test_rules_wave30m_durations import to_phase


def setup(cards):
    s = game(cards, ["Wicked Akuba", "Hermetic Study", "Lightning Bolt", "Murder", "Cloudshift"])
    source = cast(s, "Wicked Akuba")
    return s, source


def ping_setup(cards):
    s, source = setup(cards)
    cast(s, "Hermetic Study", [source.id])
    to_phase(s, "main1", turn=7)
    return s, source


def drain_index(s, source):
    return next(
        a.index for a in Plan(s.state, "p1", s.cards, None).ch(source).abilities if "loses 1 life" in a.text
    )


def assert_not_targetable(s, source, target):
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=source.id,
            ability=drain_index(s, source),
            targets=[target],
            sources=[],
        )
    assert s.state.model_dump_json() == before


def test_complete_canonical_akuba(cards):
    assert coverage.of_card_data(cards.resolve("Wicked Akuba")).level == "FULL"


def test_combat_damage_qualifies_and_repeated_activation_does_not_require_new_damage(cards):
    s, source = setup(cards)
    attack(s, [source], turn=7)
    damage(s)
    for _ in range(2):
        activate(s, source, "loses 1 life", ["p2"])
    assert s.state.players["p2"].life == 36
    roundtrip(s)


def test_noncombat_self_damage_qualifies_controller_as_target(cards):
    s, source = ping_setup(cards)
    activate(s, source, "deals 1 damage", ["p1"])
    activate(s, source, "loses 1 life", ["p1"])
    assert s.state.players["p1"].life == 38
    roundtrip(s)


@pytest.mark.parametrize("scenario", ["none", "other_source", "prevented"])
def test_no_matching_actual_damage_rejects_target_atomically(cards, scenario):
    s, source = ping_setup(cards)
    if scenario == "other_source":
        cast(s, "Lightning Bolt", ["p2"])
    elif scenario == "prevented":
        cast(s, "Healing Salve", ["p2"], pid="p2", modes=[1])
        activate(s, source, "deals 1 damage", ["p2"])
    assert_not_targetable(s, source, "p2")
    roundtrip(s)


def test_blink_before_activation_cannot_inherit_old_damage(cards):
    s, source = ping_setup(cards)
    activate(s, source, "deals 1 damage", ["p2"])
    cast(s, "Cloudshift", [source.id])
    assert_not_targetable(s, source, "p2")
    roundtrip(s)


@pytest.mark.parametrize("response", ["Cloudshift", "Murder"])
def test_source_leaves_after_announcement_uses_original_damage_history(cards, response):
    s, source = ping_setup(cards)
    activate(s, source, "deals 1 damage", ["p2"])
    act(s, "p1", type="set_prefs", hold_priority=True)
    activate(s, source, "loses 1 life", ["p2"], resolve=False)
    cast(s, response, [source.id])
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_previous_turn_damage_does_not_qualify(cards):
    s, source = ping_setup(cards)
    activate(s, source, "deals 1 damage", ["p2"])
    to_phase(s, "main1", turn=10)
    assert_not_targetable(s, source, "p2")
    roundtrip(s)


def test_true_cold_saved_ability_retains_original_source_oid_after_blink(cards, tmp_path):
    import subprocess
    import sys

    s, source = ping_setup(cards)
    activate(s, source, "deals 1 damage", ["p2"])
    act(s, "p1", type="set_prefs", hold_priority=True)
    activate(s, source, "loses 1 life", ["p2"], resolve=False)
    saved = tmp_path / "akuba48.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_prevention import cast
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
cast(s,'Cloudshift',[sys.argv[3]])
assert s.state.players['p2'].life==38
roundtrip(s)
"""
    p = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert p.returncode == 0, p.stdout + p.stderr


def test_damage_counts_even_when_life_total_cannot_change(cards):
    from tests.test_rules_designations import put

    s = game(cards, ["Wicked Akuba", "Hermetic Study", "Platinum Emperion"])
    source = cast(s, "Wicked Akuba")
    cast(s, "Hermetic Study", [source.id])
    put(s, "Platinum Emperion", "battlefield", "p2")
    to_phase(s, "main1", turn=7)
    activate(s, source, "deals 1 damage", ["p2"])
    assert s.state.players["p2"].life == 40
    activate(s, source, "loses 1 life", ["p2"])
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_other_same_named_source_does_not_qualify_player(cards):
    from tests.test_rules_designations import put

    s, source = setup(cards)
    other = put(s, "Wicked Akuba", "battlefield", "p2")
    to_phase(s, "main1", turn=5)
    cast(s, "Hermetic Study", [other.id], pid="p2")
    to_phase(s, "main1", turn=7)
    activate(s, other, "deals 1 damage", ["p3"], pid="p2")
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, "p1")
    assert_not_targetable(s, source, "p3")
    roundtrip(s)
