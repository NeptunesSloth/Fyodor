"""Wave 110M: a granted alternative cost for the next spell. 118.9 / 118.9b / 118.9c: an optional alternative cost, paid rather than the mana cost, with the
mana value unchanged; "the next spell you cast this turn" is used up by that cast (spell_grants). Every scenario checks the replay and a save and a load.

* Marshland Bloodcaster: "{1}{B}, {T}: Rather than pay the mana cost of the next spell you cast this turn, you may pay life equal to that spell's mana value."
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave36a_kit import ready
from tests.wave110m_kit import *

CASTER = "Marshland Bloodcaster"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([CASTER])


def armed(cards):
    s = build(cards, [CASTER, "Lightning Bolt", "Murder", "Hill Giant"], ["Elite Vanguard"], forests=20)
    caster = put(s, CASTER)
    ready(s, CASTER)
    mana(s, B=1, C=1)
    act(s, "p1", type="activate_ability", card_id=caster.id, ability=1)
    answer(s)
    return s, caster


def test_next_spell_may_be_cast_for_life_equal_to_its_mana_value(cards):
    s, caster = armed(cards)
    bolt = cast(s, "Lightning Bolt", ["p2"], pay=False, alt_cost=f"{card_named(s, 'Lightning Bolt').id}:life110m")
    answer(s)
    assert life(s) == 39 and life(s, "p2") == 37 and s.state.cards[bolt.id].zone == "p1:graveyard"
    check(s)


def test_a_mana_value_four_spell_costs_four_life(cards):
    s, caster = armed(cards)
    cast(s, "Hill Giant", pay=False, alt_cost=f"{card_named(s, 'Hill Giant').id}:life110m")
    answer(s)
    assert life(s) == 36 and zone_of(s, "Hill Giant") == "p1:battlefield"
    check(s)


def test_the_grant_is_for_the_next_spell_only(cards):
    s, caster = armed(cards)
    cast(s, "Lightning Bolt", ["p2"], pay=False, alt_cost=f"{card_named(s, 'Lightning Bolt').id}:life110m")
    answer(s)
    with pytest.raises(ActionError):
        cast(s, "Murder", ["p2"], pay=False, alt_cost=f"{card_named(s, 'Murder').id}:life110m")
    check(s)


def test_paying_the_mana_cost_still_uses_the_grant_up(cards):
    s, caster = armed(cards)
    cast(s, "Lightning Bolt", ["p2"])  # the mana cost, by choice (118.9b)
    answer(s)
    assert life(s) == 40
    with pytest.raises(ActionError):
        cast(s, "Murder", ["p2"], alt_cost=f"{card_named(s, 'Murder').id}:life110m")
    check(s)


def test_not_enough_life_to_pay_it(cards):
    s, caster = armed(cards)
    act(s, "p1", type="set_life", player="p1", value=3)
    with pytest.raises(ActionError):
        cast(s, "Hill Giant", pay=False, alt_cost=f"{card_named(s, 'Hill Giant').id}:life110m")
    assert life(s) == 3
    check(s)
