"""Wave 48D: an alternative cost for the first activation of a turn (CR 2026-09-25), real Oracle text (tests/fixtures/wave48d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 118.9, 602.2b: "You may pay {0} rather than pay the equip cost of the first equip ability you activate each turn." (Bruenor Battlehammer, Kíli the
  Resourceful; Forge Anew: "during each of your turns") and "You may pay {0} rather than pay the cycling cost of the first card you cycle each turn."
  (Gavi, Nest Warden) are alternative costs announced as the ability is activated (601.2b); the second activation of the turn pays its full cost.
* Gavi's ruling (2020-04-17): the whole turn counts, so a card cycled before Gavi came under your control was the first.
* 702.29f: typecycling abilities are cycling abilities; Gavi's ruling: an {X} in the cycling cost is 0 when {0} is paid instead.
* 702.6a: Forge Anew's second ability lets equip be activated at instant speed during your turn only.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave48d_kit import FULL, cast, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def ability_of(s, card, word):
    return next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id]).abilities if word in a.keywords)


def pool(s, pid="p1"):
    return sum(s.state.players[pid].mana.values())


def equip(s, equipment, creature, pid="p1", side=None):
    """Activate the equip ability at that creature; ``side`` answers the question about the cost to pay ("{0}" or the equip cost), if one is asked."""
    act(s, pid, type="activate_ability", card_id=equipment.id, ability=ability_of(s, equipment, "equip"), targets=[creature.id])
    d = s.state.rules.decision
    assert (d is not None) == (side is not None), d
    if side is not None:
        assert d.kind == "choose_cards" and "cost of its equip ability" in d.prompt, d.prompt
        act(s, pid, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == side)])
    settle(s)


def attached_to(s, equipment):
    return s.state.cards[equipment.id].attached_to


def test_bruenor_lets_the_first_equip_ability_of_a_turn_cost_nothing_and_the_second_pays_in_full(cards):
    s = build(cards, ["Bruenor Battlehammer", "Bonesplitter", "Loxodon Warhammer", "Grizzly Bears"], [])
    put(s, "Bruenor Battlehammer")
    bears, bone, hammer = put(s, "Grizzly Bears"), put(s, "Bonesplitter"), put(s, "Loxodon Warhammer")
    equip(s, hammer, bears)  # 118.9: {0} rather than {3} (only {0} can be paid: nothing to ask)
    assert attached_to(s, hammer) == bears.id
    with pytest.raises(ActionError):
        equip(s, bone, bears)  # the second equip ability of the turn costs {1}: there is no mana for it
    mana(s, C=1)
    equip(s, bone, bears)
    assert attached_to(s, bone) == bears.id
    check(s)


def test_bruenor_is_ignored_for_an_opponents_equip_abilities(cards):
    s = build(cards, ["Bonesplitter", "Grizzly Bears"], ["Bruenor Battlehammer"])
    put(s, "Bruenor Battlehammer", "p2")
    bears, bone = put(s, "Grizzly Bears"), put(s, "Bonesplitter")
    with pytest.raises(ActionError):
        equip(s, bone, bears)  # "You may pay {0}" is Bob's: Alice pays {1}
    check(s)


def test_kili_gives_the_alternative_cost_only_with_an_enduring_story(cards):
    s = build(cards, ["Kíli the Resourceful", "Bonesplitter", "Loxodon Warhammer", "Grizzly Bears"], [])
    put(s, "Kíli the Resourceful")
    bears, bone = put(s, "Grizzly Bears"), put(s, "Bonesplitter")
    assert s.state.rules.enduring_story == []  # Kíli and one artifact: two of the three permanents
    with pytest.raises(ActionError):
        equip(s, bone, bears)  # no enduring story: the equip cost {1}, with an empty pool
    to_hand(s, "Loxodon Warhammer")
    mana(s, C=3)
    cast(s, "Loxodon Warhammer")
    hammer = card_named(s, "Loxodon Warhammer")
    assert s.state.rules.enduring_story == ["p1"]  # 702.195a: Kíli (legendary) and two artifacts
    equip(s, bone, bears)  # 118.9: {0} now
    assert attached_to(s, bone) == bears.id
    with pytest.raises(ActionError):
        equip(s, hammer, bears)  # the second one of the turn: {3}
    check(s)


def cycle(s, card, side=None, pid="p1"):
    word = "plainscycling" if card.name == "Eternal Dragon" else "cycling"
    act(s, pid, type="activate_ability", card_id=card.id, ability=ability_of(s, card, word))
    d = s.state.rules.decision
    assert (d is not None) == (side is not None), d
    if side is not None:
        assert d.kind == "choose_cards" and "cost of its cycling ability" in d.prompt, d.prompt
        act(s, pid, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == side)])
    settle(s)


def sandbars_in_hand(s):
    out = [c for c in s.state.cards.values() if c.name == "Lonely Sandbar" and c.owner == "p1"]
    for c in out:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    return out


def test_gavi_lets_the_first_card_cycled_each_turn_be_cycled_for_nothing(cards):
    s = build(cards, ["Gavi, Nest Warden", "Lonely Sandbar", "Lonely Sandbar"], [])
    put(s, "Gavi, Nest Warden")
    first, second = sandbars_in_hand(s)
    hand = len(s.state.zones["p1:hand"])
    cycle(s, first)  # {U} -> {0}: only {0} can be paid, nothing to ask
    assert s.state.cards[first.id].zone == "p1:graveyard" and len(s.state.zones["p1:hand"]) == hand  # discarded, a card drawn
    with pytest.raises(ActionError):
        cycle(s, second)  # the second card cycled this turn pays {U}: nothing to pay it with
    mana(s, U=1)
    cycle(s, second)
    assert s.state.cards[second.id].zone == "p1:graveyard"
    check(s)


def test_gavi_asks_which_cost_to_pay_and_typecycling_is_cycling(cards):
    s = build(cards, ["Gavi, Nest Warden", "Lonely Sandbar", "Eternal Dragon"], [])
    put(s, "Gavi, Nest Warden")
    dragon, sandbar = to_hand(s, "Eternal Dragon"), to_hand(s, "Lonely Sandbar")
    mana(s, C=2)
    cycle(s, dragon, side="{0}")  # 702.29f: plainscycling {2} is a cycling cost, and the first one this turn
    assert s.state.cards[dragon.id].zone == "p1:graveyard"
    with pytest.raises(ActionError):
        cycle(s, sandbar)  # the second: {U}, and only {C}{C} are in the pool
    check(s)


def test_a_card_cycled_before_gavi_arrived_was_the_first(cards):
    # Gavi's ruling: the whole turn counts
    s = build(cards, ["Gavi, Nest Warden", "Lonely Sandbar", "Lonely Sandbar"], [])
    first, second = sandbars_in_hand(s)
    mana(s, U=1)
    cycle(s, first)
    put(s, "Gavi, Nest Warden")
    with pytest.raises(ActionError):
        cycle(s, second)  # {U}: the first card was cycled already this turn
    check(s)


def test_forge_anew_makes_equip_free_once_and_instant_speed_during_your_turn_only(cards):
    s = build(cards, ["Forge Anew", "Bonesplitter", "Loxodon Warhammer", "Grizzly Bears"], [])
    put(s, "Forge Anew")
    bears, bone, hammer = put(s, "Grizzly Bears"), put(s, "Bonesplitter"), put(s, "Loxodon Warhammer")
    stops(s)
    to_phase(s, "begin_combat")  # 702.6a: beginning of combat is no time for a sorcery, but for an instant
    equip(s, hammer, bears)  # {0} rather than {3}
    assert attached_to(s, hammer) == bears.id
    with pytest.raises(ActionError):
        equip(s, bone, bears)  # the second equip ability of the turn: {1}
    to_phase(s, "upkeep", turn=2)
    act(s, "p2", type="pass_priority")
    mana(s, C=1)
    with pytest.raises(ActionError):
        equip(s, bone, bears)  # "During your turn": on Bob's turn equip is a sorcery again
    check(s)


def test_equip_stays_a_sorcery_without_forge_anew_in_the_combat_phase(cards):
    s = build(cards, ["Bonesplitter", "Grizzly Bears"], [])
    bears, bone = put(s, "Grizzly Bears"), put(s, "Bonesplitter")
    stops(s)
    to_phase(s, "begin_combat")
    mana(s, C=1)
    with pytest.raises(ActionError):
        equip(s, bone, bears)
    check(s)


def test_bruenor_asks_which_cost_to_pay_when_both_can_be_paid(cards):
    s = build(cards, ["Bruenor Battlehammer", "Bonesplitter", "Grizzly Bears"], [])
    put(s, "Bruenor Battlehammer")
    bears, bone = put(s, "Grizzly Bears"), put(s, "Bonesplitter")
    mana(s, C=1)
    equip(s, bone, bears, side="{1}")  # 118.9a: the controller may pay the equip cost instead
    assert attached_to(s, bone) == bears.id
    assert pool(s) == 0
    check(s)
