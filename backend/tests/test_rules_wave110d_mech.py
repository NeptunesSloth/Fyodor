"""Wave 110D: Mechtitan Core, real Oracle text.

* 602.2, 118.3: the cost exiles the Vehicle and four OTHER artifact creatures and/or Vehicles (a Vehicle that is not crewed counts), all or nothing.
* The Enigma Jewel // Locus of Enlightenment: craft with four or more nonlands that have activated abilities (602.1, 605.1a: a mana ability counts), then the
  transformed permanent has each activated ability of the exiled materials (113.10), each usable only once each turn (602.5b).
* 607.2a: the cards exiled for the cost are the ones "exiled with" the Core, except the Core itself; 603.7: when the token leaves, they return tapped under their owners' control.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named
from tests.wave110d_kit import (  # noqa: F401
    EXTRA,
    activate,
    card_db,
    ch,
    check,
    full,
    life,
    mana,
    next_turn,
    now,
    put,
    refused,
)

COST = "{5}, Exile this Vehicle and four other artifact creatures and/or Vehicles you control"
OTHERS = ["Frogmite", "Shimmer Myr", "Foundry Inspector", "Sky-Skiff"]


def test_full():
    assert full("Mechtitan Core")


def setup(cards, others=OTHERS):
    s = build(cards, ["Mechtitan Core", *others, "Grizzly Bears"])
    core = put(s, "Mechtitan Core")
    return s, core, [put(s, n) for n in others]


def run(s, core, paid):
    mana(s, C=5)
    activate(s, core, COST, cost_choices=[{"component": 2, "cards": [c.id for c in paid]}])


def kill(s, tok):
    from tests.game_helpers import act

    act(s, "p1", type="set_damage", card_ids=[tok.id], value=99)
    from tests.wave110d_kit import settle

    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)


def test_exiled_cards_return_tapped_when_the_token_leaves_and_the_core_stays(cards):
    s, core, paid = setup(cards)
    run(s, core, paid)
    tok = next(c for c in s.state.cards.values() if c.name == "Mechtitan")
    assert all(now(s, c).zone == "p1:exile" for c in [core, *paid]) and tok.zone == "p1:battlefield"
    ch = s.state.cards[tok.id]
    assert (ch.token.power, ch.token.toughness) == ("10", "10") and len(ch.token.colors) == 5
    kill(s, tok)
    assert all(now(s, c).zone == "p1:battlefield" and now(s, c).tapped for c in paid)
    assert now(s, core).zone == "p1:exile"  # "except this card"
    check(s)


def test_three_others_is_not_enough(cards):
    s, core, paid = setup(cards)
    mana(s, C=5)
    refused(s, "Choose|pay|enough|isn.t|aren.t", core, COST, cost_choices=[{"component": 2, "cards": [c.id for c in paid[:3]]}])
    assert now(s, core).zone == "p1:battlefield" and all(now(s, c).zone == "p1:battlefield" for c in paid)


def test_a_plain_creature_does_not_count(cards):
    s, core, paid = setup(cards, OTHERS[:3] + ["Grizzly Bears"])
    mana(s, C=5)
    refused(s, "Choose|pay|enough|isn.t|aren.t|legal", core, COST, cost_choices=[{"component": 2, "cards": [c.id for c in paid]}])


JEWEL = "The Enigma Jewel // Locus of Enlightenment"
GAIN = real("Jewel Healer", "{1}", 1, "Creature — Cleric", "{1}: You gain 1 life.", ("1", "1"), "")
BIGGAIN = real("Jewel Medic", "{1}", 1, "Creature — Cleric", "{2}: You gain 3 life.", ("1", "1"), "")
MANA = real("Jewel Sprout", "{1}", 1, "Creature — Elf", "{T}: Add {G}.", ("1", "1"), "G")
EXTRA_GAIN = real("Jewel Nurse", "{1}", 1, "Creature — Cleric", "{1}: You gain 2 life.", ("1", "1"), "")
PLAIN = real("Jewel Idler", "{1}", 1, "Creature — Human", "", ("1", "1"), "")
EXTRA.extend([GAIN, BIGGAIN, MANA, EXTRA_GAIN, PLAIN])
MATS = ["Jewel Healer", "Jewel Medic", "Jewel Sprout", "Jewel Nurse"]
CRAFT = "{8}{U}, Exile this"


def craft(cards, mats=MATS):
    s = build(cards, [JEWEL, *MATS, "Jewel Idler"])
    jewel = put(s, JEWEL)
    got = [card_named(s, n) for n in mats]
    act(s, "p1", type="move", card_ids=[c.id for c in got], to={"player": "p1", "zone": "graveyard"})
    return s, jewel, got


def pay_craft(s, jewel, got):
    mana(s, C=8, U=1)
    activate(s, jewel, CRAFT, cost_choices=[{"component": 2, "cards": [c.id for c in got]}])


def test_enigma_jewel_is_full():
    assert full(JEWEL)


def test_locus_has_each_material_ability_once_each_turn(cards):
    s, jewel, got = craft(cards)
    pay_craft(s, jewel, got)
    locus = now(s, jewel)
    assert locus.zone == "p1:battlefield" and locus.face == 1 and all(now(s, c).zone == "p1:exile" for c in got)
    assert any(a.kind == "mana" and a.text.endswith("Activate only once each turn.") for a in ch(s, locus).abilities)  # the lent mana ability is limited too
    before = life(s, "p1")
    mana(s, C=1)
    activate(s, locus, "{1}: You gain 1 life")
    assert life(s, "p1") == before + 2  # the ability, and the copy of it ("Whenever you activate an ability that isn't a mana ability, copy it")
    mana(s, C=1)
    refused(s, "once|only|can.t", locus, "{1}: You gain 1 life")  # 602.5b: that one ability, once each turn
    mana(s, C=2)
    activate(s, locus, "{2}: You gain 3 life")  # a different lent ability is not used up
    assert life(s, "p1") == before + 8
    next_turn(s)
    next_turn(s)
    mana(s, C=1)
    activate(s, now(s, jewel), "{1}: You gain 1 life")  # a new turn
    check(s)


def test_a_card_without_an_activated_ability_cannot_be_a_material(cards):
    s, jewel, got = craft(cards, MATS[:3] + ["Jewel Idler"])
    mana(s, C=8, U=1)
    refused(s, "Choose|pay|enough|isn.t|aren.t|legal", jewel, CRAFT, cost_choices=[{"component": 2, "cards": [c.id for c in got]}])
    assert now(s, jewel).face == 0

