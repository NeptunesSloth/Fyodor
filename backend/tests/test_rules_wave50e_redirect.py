"""Wave 50E: redirection statics (CR 2026-09-25), real Oracle text (tests/fixtures/wave50e_prevent_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 614.9: "As long as this creature is untapped, all [combat] damage that would be dealt to you by unblocked creatures is dealt to this creature instead." (Veteran Bodyguard, Weathered Bodyguards:
  the rulings - only an unblocked creature's damage, and the latter only combat damage), "… by artifacts …" (Martyrs of Korlis) - while the holder is untapped.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave34b_activated import attack, next_turn, settle, to_phase
from tests.test_rules_wave50e_prevent import cards  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, check, mana, put, to_hand


@pytest.mark.parametrize("guard", ["Veteran Bodyguard", "Weathered Bodyguards"])
def test_a_bodyguard_takes_the_damage_of_an_unblocked_creature(cards, guard):  # noqa: F811
    s = build(cards, ["Hill Giant"], [guard])
    giant = put(s, "Hill Giant")
    bodyguard = put(s, guard, "p2")
    next_turn(s)
    attack(s, giant)
    to_phase(s, "main2")
    assert s.state.players["p2"].life == 40 and s.state.cards[bodyguard.id].damage == 3
    check(s)


@pytest.mark.parametrize("guard", ["Veteran Bodyguard", "Weathered Bodyguards"])
def test_a_tapped_bodyguard_takes_nothing(cards, guard):  # noqa: F811
    s = build(cards, ["Hill Giant"], [guard])
    giant = put(s, "Hill Giant")
    bodyguard = put(s, guard, "p2")
    next_turn(s)
    act(s, "p2", type="tap", card_ids=[bodyguard.id])
    attack(s, giant)
    to_phase(s, "main2")
    assert s.state.players["p2"].life == 37 and s.state.cards[bodyguard.id].damage == 0
    check(s)


@pytest.mark.parametrize("guard", ["Veteran Bodyguard", "Weathered Bodyguards"])
def test_a_bodyguard_does_not_take_a_spells_damage(cards, guard):  # noqa: F811
    s = build(cards, ["Lightning Bolt"], [guard])
    put(s, guard, "p2")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 37
    check(s)


def test_martyrs_of_korlis_take_an_artifacts_damage(cards):  # noqa: F811
    s = build(cards, ["Granite Shard", "Lightning Bolt"], ["Martyrs of Korlis"])
    shard = put(s, "Granite Shard")
    martyrs = put(s, "Martyrs of Korlis", "p2")
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=shard.id, ability=1, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 40 and s.state.cards[martyrs.id].damage == 1
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])  # a spell is no artifact
    settle(s)
    assert s.state.players["p2"].life == 37
    check(s)
