"""Wave 110B session 21: Aang, Swift Savior (airbending a spell) and Avatar Aang (bend triggers), real Oracle text in tests/fixtures/wave110b_cards.json.

* Aang, Swift Savior: 701.65a airbend exiles the creature or spell (not a counter), its owner may cast it for {2} instead of its mana cost.
* Avatar Aang: 701.65b, 701.66b, 701.67c, 702.189b each bend triggers "whenever you waterbend, earthbend, firebend, or airbend"; transforms after all four in a turn.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import (
    attack,
    build,
    card_named,
    check,
    drive,
    life,
    mana,
    put,
    repository,
    through_combat,
    to_hand,
)

AANG = "Aang, Swift Savior // Aang and La, Ocean's Fury"
AVATAR = "Avatar Aang // Aang, Master of Elements"


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", [AANG, AVATAR])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def pick(target, aang=None):
    def answer(d):
        assert aang is None or not any(aang.id in o.id for o in d.options)
        ids = [o.id for o in d.options if target.id in o.id]
        return ids[:1] or None
    return answer


@pytest.mark.parametrize("what", ["spell", "creature"])
def test_aang_airbends_a_spell_or_creature_not_itself(cards, what):
    """701.65a: a spell leaves the stack exiled (it never resolves) and can be cast for {2}; a creature is exiled the same way; "other": Aang itself is no legal target."""
    s = build(cards, [AANG, "Lightning Bolt"], ["Grizzly Bears"], forests=30, islands=40)
    act(s, "p1", type="set_prefs", hold_priority=True)
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, R=1, W=1, U=1, C=1)
    bolt = to_hand(s, "Lightning Bolt")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    target = {"spell": bolt, "creature": bears}[what]
    aang = to_hand(s, AANG)
    act(s, "p1", type="cast_spell", card_id=aang.id)
    drive(s, pick(target, aang))
    act(s, "p1", type="set_prefs", hold_priority=False)
    drive(s)
    if what == "spell":
        assert s.state.cards[bolt.id].zone == "p1:exile" and life(s, "p2") == 40
        mana(s, R=1, C=1)
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
        drive(s)
        assert life(s, "p2") == 37 and s.state.cards[bolt.id].zone == "p1:graveyard"
    else:
        assert s.state.cards[bears.id].zone == "p2:exile" and life(s, "p2") == 37
    assert s.state.cards[card_named(s, AANG).id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("skip", [None, "water", "earth", "fire", "air"])
def test_avatar_aang_draws_per_bend_and_transforms_after_all_four(cards, skip):
    """Each of the four bends draws a card; only once all four were done this turn does it transform (608.2i)."""
    s = build(cards, [AVATAR, "Earthbender Ascension", "Airbender Ascension", "Ruthless Waterbender"], ["Grizzly Bears"], forests=30, islands=40)
    aang = put(s, AVATAR)
    s.state.rules.controlled_since[aang.id].turn = 0
    bears = put(s, "Grizzly Bears", "p2")
    water = put(s, "Ruthless Waterbender")
    put(s, "Forest")  # a land to earthbend
    mana(s, G=3, W=2, C=2)
    hand = len(s.state.zones["p1:hand"])
    if skip != "earth":
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Earthbender Ascension").id)
        drive(s)
    if skip != "air":
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Airbender Ascension").id)
        drive(s, pick(bears))
    if skip != "water":
        act(s, "p1", type="activate_ability", card_id=water.id, ability=0)
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[])  # 701.67a: tap nothing, pay all of it with mana
        drive(s)
    bends = 4 - (skip is not None)
    if skip != "fire":
        attack(s, aang)
        through_combat(s)
    assert len(s.state.zones["p1:hand"]) - hand == bends  # one draw per bend
    assert s.state.cards[aang.id].face == (1 if skip is None else 0)
    check(s)
