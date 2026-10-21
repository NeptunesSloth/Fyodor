"""Actual Inspired Ultimatum preserves its independent native targets."""

import pytest

from tests.test_rules_conditional_prevention import cast
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


@pytest.mark.parametrize("gain,damage", [("p1", "p2"), ("p2", "p1"), ("p1", "p1")])
def test_actual_ultimatum_players_and_five_draws(cards, gain, damage):
    s = game(cards, ["Inspired Ultimatum"])
    before = len(s.state.zones["p1:hand"])
    cast(s, "Inspired Ultimatum", [gain, damage], target_counts=[1, 1])
    assert s.state.players[gain].life == (40 if gain == damage else 45)
    assert s.state.players[damage].life == (40 if gain == damage else 35)
    assert len(s.state.zones["p1:hand"]) == before + 5
    roundtrip(s)


def test_actual_ultimatum_creature_damage(cards):
    s = game(cards, ["Inspired Ultimatum"])
    target = put(s, "Grizzly Bears", "battlefield", "p2")
    cast(s, "Inspired Ultimatum", ["p1", target.id], target_counts=[1, 1])
    assert s.state.players["p1"].life == 45
    assert target.zone == "p2:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("departures", [0, 2, 3, 4])
def test_actual_bonecache_activation_counts_individual_graveyard_departures(cards, departures):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import activate
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards, ["Bonecache Overseer"])
    source = cast(s, "Bonecache Overseer")
    to_phase(s, "main1", turn=7)
    moved = [c.id for c in s.state.cards.values() if c.zone == "p1:library"][:departures]
    if moved:
        act(s, "p1", type="move", card_ids=moved, to={"player": "p1", "zone": "graveyard"})
        act(s, "p1", type="move", card_ids=moved, to={"player": "p1", "zone": "exile"})
    before = len(s.state.zones["p1:hand"])
    if departures < 3:
        with pytest.raises(ActionError):
            activate(s, source, "Pay 1 life")
        assert not source.tapped and s.state.players["p1"].life == 40
    else:
        activate(s, source, "Pay 1 life")
        assert source.tapped and s.state.players["p1"].life == 39
        assert len(s.state.zones["p1:hand"]) == before + 1
    roundtrip(s)


@pytest.mark.parametrize("gain,damage,expected", [("p2", "p3", 35), ("p1", "p2", 40), ("p2", "p2", 40)])
def test_ultimatum_one_or_both_targets_leave_before_resolution(cards, gain, damage, expected):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle

    s = game(cards, ["Inspired Ultimatum"])
    act(s, "p1", type="set_prefs", hold_priority=True)
    source = cast(s, "Inspired Ultimatum", [gain, damage], target_counts=[1, 1], resolve=False)
    before = len(s.state.zones["p1:hand"])
    act(s, "p2", type="concede")
    settle(s)
    assert source.zone == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == before + (0 if gain == damage == "p2" else 5)
    assert s.state.players["p3"].life == expected
    if gain == "p1":
        assert s.state.players["p1"].life == 45
    roundtrip(s)


def test_ultimatum_illegal_creature_target_still_gains_and_draws(cards):
    from tests.game_helpers import act

    s = game(cards, ["Inspired Ultimatum", "Murder"])
    target = put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="set_prefs", hold_priority=True)
    cast(s, "Inspired Ultimatum", ["p1", target.id], target_counts=[1, 1], resolve=False)
    before = len(s.state.zones["p1:hand"])
    cast(s, "Murder", [target.id], pid="p2")
    assert s.state.players["p1"].life == 45
    assert len(s.state.zones["p1:hand"]) == before + 5
    assert target.zone == "p2:graveyard"
    roundtrip(s)


def test_actual_bonecache_nontoken_food_sacrifice_opens_activation(cards):
    from tests.test_rules_conditional_prevention import activate
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards, ["Bonecache Overseer", "Gingerbrute"])
    source = cast(s, "Bonecache Overseer")
    food = cast(s, "Gingerbrute")
    to_phase(s, "main1", turn=7)
    activate(s, food, "Sacrifice")
    before = len(s.state.zones["p1:hand"])
    activate(s, source, "Pay 1 life")
    assert food.zone == "p1:graveyard" and source.tapped
    assert s.state.players["p1"].life == 42
    assert len(s.state.zones["p1:hand"]) == before + 1
    roundtrip(s)


def test_bonecache_counts_repeated_departures_of_same_physical_card(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import activate
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards, ["Bonecache Overseer"])
    source = cast(s, "Bonecache Overseer")
    to_phase(s, "main1", turn=7)
    card = put(s, "Healing Salve", "hand")
    for _ in range(3):
        act(s, "p1", type="move", card_ids=[card.id], to={"player": "p1", "zone": "graveyard"})
        act(s, "p1", type="move", card_ids=[card.id], to={"player": "p1", "zone": "hand"})
    activate(s, source, "Pay 1 life")
    assert source.tapped and s.state.players["p1"].life == 39
    roundtrip(s)


def test_bonecache_opponents_departures_do_not_count(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import activate
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards, ["Bonecache Overseer"])
    source = cast(s, "Bonecache Overseer")
    to_phase(s, "main1", turn=7)
    cards_out = [c.id for c in s.state.cards.values() if c.zone == "p2:library"][:3]
    act(s, "p2", type="move", card_ids=cards_out, to={"player": "p2", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=cards_out, to={"player": "p2", "zone": "exile"})
    with pytest.raises(ActionError):
        activate(s, source, "Pay 1 life")
    assert not source.tapped and s.state.players["p1"].life == 40
    roundtrip(s)


@pytest.mark.parametrize("name", ["Inspired Ultimatum", "Bonecache Overseer"])
def test_two_native_life45_cards_fresh_process(cards, tmp_path, name):
    import subprocess
    import sys

    from tests.game_helpers import act
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards, [name])
    if name == "Inspired Ultimatum":
        act(s, "p1", type="set_prefs", hold_priority=True)
        cast(s, name, ["p1", "p2"], target_counts=[1, 1], resolve=False)
    else:
        cast(s, name)
        to_phase(s, "main1", turn=7)
        moved = [c.id for c in s.state.cards.values() if c.zone == "p1:library"][:3]
        act(s, "p1", type="move", card_ids=moved, to={"player": "p1", "zone": "graveyard"})
        act(s, "p1", type="move", card_ids=moved, to={"player": "p1", "zone": "exile"})
    saved = tmp_path / "life45.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_prevention import activate
from tests.test_rules_designations import roundtrip,settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
before=len(s.state.zones['p1:hand'])
if sys.argv[3]=='Inspired Ultimatum':
 settle(s)
 assert s.state.players['p1'].life==45 and s.state.players['p2'].life==35
 assert len(s.state.zones['p1:hand'])==before+5
else:
 source=next(c for c in s.state.cards.values() if c.name==sys.argv[3] and c.owner=='p1')
 activate(s,source,'Pay 1 life')
 assert source.tapped and s.state.players['p1'].life==39
 assert len(s.state.zones['p1:hand'])==before+1
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), name], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", ["Inspired Ultimatum", "Bonecache Overseer"])
def test_two_native_life45_full_printed_coverage(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"
