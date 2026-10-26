"""Wave 110C: Kefka, Dancing Mad (608.2c, 118.4): at the end step a card is picked at random from each opponent's graveyard and exiled; any number of the spells among them may be
cast free; each player who owns a spell cast this way loses life equal to its mana value (lands are not spells: no loss)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110c_kit import STEPS, answer, check, life, make_db, put, real
from tests.wave110d_kit import move, to_phase

BLAZE = real("Blaze", "{X}{R}", 1, "Sorcery", "Blaze deals X damage to any target.", None, "R")
TEXT = ("During your turn, Kefka has indestructible.\nAt the beginning of your end step, exile a card at random from each opponent's graveyard. You may cast any number of spells from among "
        "cards exiled this way without paying their mana costs. Then each player who owns a spell you cast this way loses life equal to its mana value.")
EXTRA = [real("Kefka, Dancing Mad", "{3}{B}{B}", 5, "Legendary Creature — Noble Wizard", TEXT, ("4", "4"), "B"), BLAZE]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Kefka, Dancing Mad")).level == "FULL"


def end_step(cards, grave, cast):
    s = build(cards, ["Kefka, Dancing Mad"], ["Lightning Bolt", "Forest", "Blaze"])
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False, hold_priority=False)
    put(s, "Kefka, Dancing Mad")
    card = next(c for c in s.state.cards.values() if c.name == grave and c.owner == "p2")
    move(s, card, "graveyard", "p2")
    to_phase(s, "end", turn=1)
    d = s.state.rules.decision
    if d is None:  # (the trigger waits on the stack)
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    if d is not None and d.kind == "choose_cards" and not cast:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[])  # (any number: none)
    answer(s, *([card.id, "p2"] if cast else []))
    return s, card


@pytest.mark.parametrize("cast", [True, False])
def test_cast_the_exiled_spell_and_its_owner_loses_its_mana_value(cards, cast):
    s, bolt = end_step(cards, "Lightning Bolt", cast)
    if cast:
        assert s.state.cards[bolt.id].zone == "p2:graveyard" and life(s, "p2") == 40 - 1 - 3  # (the loss, then the Bolt aimed at p2)
    else:
        assert s.state.cards[bolt.id].zone == "p2:exile" and life(s, "p2") == 40
    check(s)


def test_a_land_is_exiled_but_is_not_a_spell(cards):
    s, forest = end_step(cards, "Forest", False)
    assert s.state.cards[forest.id].zone == "p2:exile" and life(s, "p2") == 40
    check(s)


def test_x_spell_is_cast_with_x_zero_and_its_owner_loses_one(cards):
    """Ruling 2025-06-06: X is 0 when cast free, so the mana value on the stack is 1 ({X}{R}, 202.3b); the graveyard is its owner's, so one owner per card (400.3)."""
    s, blaze = end_step(cards, "Blaze", True)
    assert life(s, "p2") == 39
    check(s)
