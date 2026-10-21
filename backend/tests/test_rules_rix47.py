"""Rix Maadi Guildmage targets actual life loss this turn, including its controller."""

import pytest

from app.game.errors import ActionError
from app.rules import coverage, selectors
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import activate, attack, cast
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game
from tests.test_rules_wave30m_durations import to_phase


def setup(cards):
    s = game(cards, ["Rix Maadi Guildmage", "Lightning Bolt", "Greed"])
    source = cast(s, "Rix Maadi Guildmage")
    return s, source


def lose_ability(s, source):
    return next(
        a.index for a in Plan(s.state, "p1", s.cards, None).ch(source).abilities if "loses 1 life" in a.text
    )


def test_full_canonical_and_reject_unsupported_nonplayer_history():
    assert selectors.parse("creature who lost life this turn") is None
    assert selectors.parse("player from your graveyard") is None


def test_rix_complete_canonical(cards):
    assert coverage.of_card_data(cards.resolve("Rix Maadi Guildmage")).level == "FULL"


def test_damage_loss_then_gain_still_allows_repeat_activation(cards):
    s, source = setup(cards)
    cast(s, "Lightning Bolt", ["p2"])
    cast(s, "Healing Salve", ["p2"], modes=[0])
    assert s.state.players["p2"].life == 40
    for _ in range(2):
        activate(s, source, "loses 1 life", ["p2"])
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_actual_life_payment_makes_controller_legal(cards):
    s, source = setup(cards)
    greed = cast(s, "Greed")
    activate(s, greed, "Draw a card")
    activate(s, source, "loses 1 life", ["p1"])
    assert s.state.players["p1"].life == 37
    roundtrip(s)


@pytest.mark.parametrize("prevented", [False, True])
def test_no_loss_or_fully_prevented_damage_cannot_be_targeted(cards, prevented):
    s, source = setup(cards)
    if prevented:
        cast(s, "Healing Salve", ["p2"], pid="p2", modes=[1])
        cast(s, "Lightning Bolt", ["p2"])
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=source.id,
            ability=lose_ability(s, source),
            targets=["p2"],
            sources=[],
        )
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_previous_turn_loss_does_not_count(cards):
    s, source = setup(cards)
    cast(s, "Lightning Bolt", ["p2"])
    to_phase(s, "main1", turn=5)
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, "p1")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=source.id,
            ability=lose_ability(s, source),
            targets=["p2"],
            sources=[],
        )
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_other_ability_targets_real_blocking_creature(cards):
    s, source = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    attack(s, [source], turn=7)
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bear.id, "attacker_id": source.id}])
    activate(s, source, "blocking creature", [bear.id])
    assert Plan(s.state, "p1", cards, None).ch(bear).pt == (1, 1)
    roundtrip(s)


def test_saved_activated_target_history_survives_native_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s, source = setup(cards)
    cast(s, "Lightning Bolt", ["p2"])
    act(s, "p1", type="set_prefs", hold_priority=True)
    activate(s, source, "loses 1 life", ["p2"], resolve=False)
    assert s.state.zones.get("stack")
    saved = tmp_path / "rix47.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
assert s.state.players['p2'].life==36
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
