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


@pytest.mark.parametrize("name", [AANG, AVATAR, "Havengul Lich", "The Rise of Sozin // Fire Lord Sozin", "Flameblade Angel"])
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


LICH = "Havengul Lich"


@pytest.mark.parametrize("cast_it", [True, False])
def test_havengul_lich_gains_activated_abilities_only_when_the_card_is_cast(cards, cast_it):
    """603.7a delayed trigger on casting that card; ruling 2011-01-22: nothing is gained if it isn't cast; 613.1f the abilities last until end of turn."""
    from tests.wave110b_kit import ch

    s = build(cards, [LICH, "Ruthless Waterbender"], [], forests=30, islands=40)
    lich = put(s, LICH)
    waterbender = card_named(s, "Ruthless Waterbender")
    act(s, "p1", type="move", card_ids=[waterbender.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=lich.id, ability=0, targets=[waterbender.id])
    drive(s)
    if cast_it:
        mana(s, B=1, C=1)
        act(s, "p1", type="cast_spell", card_id=waterbender.id)
        drive(s)
    texts = [a.text for a in ch(s, lich).abilities]
    assert any(t.startswith("Waterbend {2}") for t in texts) is cast_it
    if cast_it:
        assert s.state.cards[waterbender.id].zone == "p1:battlefield"
        mana(s, C=2)
        index = next(a.index for a in ch(s, lich).abilities if a.text.startswith("Waterbend {2}"))
        act(s, "p1", type="activate_ability", card_id=lich.id, ability=index)
        d = s.state.rules.decision
        if d is not None:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
        drive(s)
        from app.rules import sba
        assert sba.power(s.state.cards[lich.id], ch(s, lich)) == 5
        from tests.test_rules_wave30m_durations import to_phase

        to_phase(s, "main1", turn=3)
        assert not any(a.text.startswith("Waterbend {2}") for a in ch(s, lich).abilities)  # until end of turn
    check(s)


def test_flameblade_angel_triggers_once_per_recipient_of_one_source(cards):
    """Ruling 2016-04-08: one source dealing damage to you and to a permanent you control at the same time triggers once for each (here Earthquake: Bob and his Bears, not the flyer)."""
    s = build(cards, ["Earthquake"], ["Flameblade Angel", "Grizzly Bears"])
    put(s, "Flameblade Angel", "p2")
    put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Earthquake").id, x_value=1)
    drive(s)
    assert s.state.players["p1"].life == 40 - 1 - 2  # Earthquake hits Alice too; Bob's Angel pings twice
    check(s)


SOZIN = "The Rise of Sozin // Fire Lord Sozin"


def sozin_hit(cards, x):
    """Fire Lord Sozin (the back face) hits Bob, who has Grizzly Bears (MV 2) and Llanowar Elves (MV 1) in his graveyard; Alice has 3 mana."""
    s = build(cards, [SOZIN], ["Grizzly Bears", "Llanowar Elves"])
    sozin = put(s, SOZIN)
    act(s, "p1", type="set_face", card_id=sozin.id, face=1)
    for n in ("Grizzly Bears", "Llanowar Elves"):
        c = card_named(s, n, "p2")
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "graveyard"})
    mana(s, C=3)
    attack(s, sozin)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_one"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[x])
    return s


@pytest.mark.parametrize(("x", "picked", "back"), [("x:2", ["Grizzly Bears"], ["Grizzly Bears"]), ("x:2", ["Llanowar Elves"], ["Llanowar Elves"]),
                                                    ("x:3", ["Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears", "Llanowar Elves"]), ("x:0", [], [])])
def test_fire_lord_sozin_reanimates_creatures_up_to_the_x_paid(cards, x, picked, back):
    """603.12, 107.3f: the reflexive ability's targets are chosen knowing X; any number of creature cards from that player's graveyard with total mana value X or less."""
    s = sozin_hit(cards, x)
    d = s.state.rules.decision
    assert d is not None  # "any number": choosing none is allowed
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if s.state.cards[o.id].name in picked])
    drive(s)
    assert sorted(c.name for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name in ("Grizzly Bears", "Llanowar Elves")) == sorted(back)
    check(s)


def test_fire_lord_sozin_total_mana_value_over_x_is_refused(cards):
    """601.2c: two cards with total mana value 3 can't both be chosen when 2 was paid."""
    from app.game.errors import ActionError

    s = sozin_hit(cards, "x:2")
    d = s.state.rules.decision
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
