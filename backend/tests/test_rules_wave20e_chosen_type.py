"""Wave 20E: "the chosen color" after "Choose a color.". Real Oracle text; every scenario checks the replay and a save and a load.

* 608.2c / 105.1: the color is chosen as the instruction is reached, then "gain protection from the chosen color until end of turn" reads it.
* 702.16b/e: the creatures that gained protection from red can't be targeted by red spells; 611.2c: the set is locked in as it resolves.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

EXTRA = [
    real("Akroma's Blessing", '{2}{W}', 3, 'Instant', 'Choose a color. Creatures you control gain protection from the chosen color until end of turn.', None, 'W'),
    real('Brave the Elements', '{W}', 1, 'Instant', 'Choose a color. White creatures you control gain protection from the chosen color until end of turn.', None, 'W'),
    real('Bathe in Light', '{W}', 1, 'Instant', 'Radiance — Choose a color. Target creature and each other creature that shares a color with it gain protection from the chosen color until end of turn.', None, 'W'),
    real('Glory', '{3}{W}{W}', 5, 'Creature — Incarnation', "Flying\n{2}{W}: Choose a color. Creatures you control gain protection from the chosen color until end of turn. Activate only if this card is in your graveyard.", ("3", "3"), 'W'),
    real('Probe Soldier', '{1}{W}', 2, 'Creature — Human Soldier', '', ("1", "1"), 'W'),
    real('Probe Knight', '{1}{W}', 2, 'Creature — Human Knight', '', ("2", "2"), 'W'),
    real('Probe Elf', '{G}', 1, 'Creature — Elf', '', ("1", "1"), 'G'),
    real('Probe Burst', '{R}', 1, 'Instant', 'Probe Burst deals 1 damage to any target.', None, 'R'),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Akroma's Blessing", "Brave the Elements"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_protection_from_the_color_that_was_chosen(cards):
    s = build(cards, ["Akroma's Blessing", "Probe Soldier", "Probe Burst"], [])
    soldier = put(s, "Probe Soldier")
    blessing, burst = to_hand(s, "Akroma's Blessing"), to_hand(s, "Probe Burst")
    mana(s, "p1", W=1, C=2, R=1)
    act(s, "p1", type="cast_spell", card_id=blessing.id)
    answer(s, "Red")
    assert not s.state.rules.stack
    with pytest.raises(ActionError):  # (protection from red: a red spell can't target it)
        act(s, "p1", type="cast_spell", card_id=burst.id, targets=[soldier.id])
    act(s, "p1", type="cast_spell", card_id=burst.id, targets=["p2"])  # (the player isn't protected)
    check(s)


def test_radiance_gives_every_creature_of_a_shared_color_the_chosen_protection(cards):
    """Radiance (207.2c) is no rules text: the target and each other creature that shares a color with it gain it; a green one doesn't."""
    s = build(cards, ["Bathe in Light", "Probe Soldier", "Probe Knight", "Probe Elf", "Probe Burst", "Probe Burst"], [])
    soldier, knight, elf = put(s, "Probe Soldier"), put(s, "Probe Knight"), put(s, "Probe Elf")
    light = to_hand(s, "Bathe in Light")
    mana(s, "p1", W=1, R=3)
    act(s, "p1", type="cast_spell", card_id=light.id, targets=[soldier.id])
    answer(s, "Red")
    for protected in (soldier, knight):
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Burst").id, targets=[protected.id])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Probe Burst").id, targets=[elf.id])  # (green: shares no color with the target)
    check(s)


def test_glory_is_activated_from_the_graveyard_and_each_activation_keeps_its_own_color(cards):
    """(review 20E) "Activate only if this card is in your graveyard" (113.6m: the ability works there, and only there); two
    activations naming red and blue give protection from both (each effect reads its own choice)."""
    from app.rules import protection
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

    s = build(cards, ["Glory", "Probe Soldier"], [])
    glory = card_named(s, "Glory")
    soldier = put(s, "Probe Soldier")
    act(s, "p1", type="move", card_ids=[glory.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", W=2, C=4)
    idx = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[glory.id]).abilities if "{2}{W}" in a.text)
    for color in ("Red", "Blue"):
        act(s, "p1", type="activate_ability", card_id=glory.id, ability=idx)
        answer(s, color)
    plan = Plan(s.state, "p1", s.cards, None)
    ch = plan.ch(s.state.cards[soldier.id])
    assert [protection.protected_from(ch, Characteristics(name="x", colors=frozenset({c}))) for c in "RUG"] == [True, True, False]
    check(s)
