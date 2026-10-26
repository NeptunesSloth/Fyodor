"""Wave 110M: named Aura tokens and Auras returning from a graveyard. 111.3 / 303.4f: a token Aura made attached to an object enters attached to it (it does not target it);
303.4g: an Aura put onto the battlefield without being cast has its controller choose what it enchants; 702.89a umbra armor.
Every scenario checks the replay and a save and a load.

* Estrid, the Masked: "−1: Create a white Aura enchantment token named Mask attached to another target permanent. ..." and the −7.
* Smoke Spirits' Aid: "For each of up to X target creatures, create a red Aura enchantment token named Smoke Blessing attached to that creature. ..."
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.test_rules_wave36a_trigger_words import loyal
from tests.wave110m_kit import *

ESTRID = "Estrid, the Masked"
SMOKE = "Smoke Spirits' Aid"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([ESTRID, SMOKE])


def masks(s):
    return [c for c in s.state.cards.values() if c.name == "Mask" and c.zone == "p1:battlefield"]


def test_estrid_minus_one_makes_a_mask_that_keeps_the_permanent_from_being_destroyed(cards):
    s = build(cards, [ESTRID, "Grizzly Bears", "Murder"], ["Elite Vanguard"], forests=20)
    walker = loyal(s, ESTRID, loyalty=3)
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=1, targets=[bears.id])
    answer(s)
    (mask,) = masks(s)
    assert mask.attached_to == bears.id and s.state.cards[walker.id].counters.get("loyalty") == 2
    cast(s, "Murder", [bears.id])
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and not masks(s)  # (umbra armor: the Mask is destroyed instead, 702.89a)
    check(s)


def test_the_mask_can_enchant_a_land_but_never_estrid_herself(cards):
    s = build(cards, [ESTRID], ["Elite Vanguard"], forests=20)
    walker = loyal(s, ESTRID, loyalty=3)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=walker.id, ability=1, targets=[walker.id])
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=1, targets=[forest.id])
    answer(s)
    (mask,) = masks(s)
    assert mask.attached_to == forest.id
    check(s)


def test_estrid_minus_seven_returns_enchantments_then_auras_that_may_enchant_them(cards):
    s = build(cards, [ESTRID, "Pacifism", "Courser of Kruphix", "Test Rest"], ["Elite Vanguard"], forests=20)
    walker = loyal(s, ESTRID, loyalty=7)
    for n in ("Pacifism", "Courser of Kruphix", "Test Rest"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=2)
    courser = card_named(s, "Courser of Kruphix")
    answer(s, courser.id)  # Pacifism enchants the Courser that came back in the first step (it enters after, 608.2c)
    assert [zone_of(s, n) for n in ("Courser of Kruphix", "Test Rest", "Pacifism")] == ["p1:battlefield"] * 3
    assert card_named(s, "Pacifism").attached_to == courser.id
    assert s.state.cards[walker.id].zone == "p1:graveyard"  # (loyalty 0)
    check(s)


def test_smoke_spirits_aid_blesses_each_target_and_a_dying_creature_pays_out(cards):
    s = build(cards, [SMOKE, "Lightning Bolt"], ["Elite Vanguard", "Hill Giant"], forests=20)
    vanguard, giant = put(s, "Elite Vanguard", "p2"), put(s, "Hill Giant", "p2")
    c = to_hand(s, SMOKE)
    fund(s, "{2}{R}")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[vanguard.id, giant.id], target_counts=[2], x_value=2)
    answer(s)
    blessings = [t for t in s.state.cards.values() if t.name == "Smoke Blessing" and t.zone == "p1:battlefield"]
    assert sorted(t.attached_to for t in blessings) == sorted([vanguard.id, giant.id])
    cast(s, "Lightning Bolt", [vanguard.id])
    answer(s)
    assert zone_of(s, "Elite Vanguard", "p2") == "p2:graveyard" and life(s, "p2") == 39  # (the Bolt kills the 2/1; its controller takes 1)
    assert any(t.name == "Treasure" and t.zone == "p1:battlefield" for t in s.state.cards.values())
    check(s)


def test_smoke_spirits_aid_for_x_zero_makes_nothing(cards):
    s = build(cards, [SMOKE], ["Elite Vanguard"], forests=20)
    c = to_hand(s, SMOKE)
    fund(s, "{R}")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[], target_counts=[0], x_value=0)
    answer(s)
    assert not any(t.name == "Smoke Blessing" for t in s.state.cards.values())
    check(s)
