"""Wave 110A final pass: Ice Cave (118.12, 107.3h), ..."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110a_kit import *

NAMES = ["Ice Cave", "Damping Engine", "Chaotic Transformation"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test(NAMES)


def _decision(s):
    d = s.state.rules.decision
    return None if d is None else (d.player, d.kind, [o.id for o in d.options])


@pytest.mark.parametrize("pay", [True, False])
def test_ice_cave_other_player_may_pay_the_spells_mana_cost_to_counter_it(cards, pay):
    """Ice Cave: Bob (the only other player) may pay Alice's Divination's {2}{U}; if he does it is countered (118.12)."""
    s = build(cards, ["Ice Cave", "Divination"], ["Shock"])
    put(s, "Ice Cave")
    hand = len(s.state.zones["p1:hand"])
    fund(s, "{2}{U}", "p2")
    cast(s, "Divination")
    assert _decision(s)[:2] == ("p2", "choose_one")
    answer(s, "pay" if pay else "decline")
    assert len(s.state.zones["p1:hand"]) == hand + (0 if pay else 2)
    check(s)


def test_ice_cave_unpayable_cost_is_not_offered(cards):
    """No mana in Bob's pool: nothing to pay (118.3), the spell resolves."""
    s = build(cards, ["Ice Cave", "Divination"])
    put(s, "Ice Cave")
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Divination")
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 2
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_ice_cave_x_is_the_value_chosen_for_the_spell(cards, pay):
    """107.3h: Blaze {X}{R} with X=2 on the stack costs {2}{R}."""
    s = build(cards, ["Ice Cave", "Blaze"])
    put(s, "Ice Cave")
    fund(s, "{2}{R}" if pay else "{R}", "p2")
    fund(s, "{2}{R}")
    cast(s, "Blaze", targets=["p2"], pay=False, x_value=2)
    answer(s, "pay" if pay else "decline")
    assert life(s, "p2") == (40 if pay else 38)
    check(s)


def _engine(cards):
    s = build(cards, ["Damping Engine", "Sol Ring", "Llanowar Elves", "Sylvan Library", "Shock"])
    return s, put(s, "Damping Engine")


@pytest.mark.parametrize("name", ["Sol Ring", "Llanowar Elves", "Sylvan Library"])
def test_damping_engine_stops_artifact_creature_and_enchantment_spells_of_the_player_with_most_permanents(cards, name):
    """601.3: Alice controls 1 permanent, Bob 0: she can't cast an artifact, creature or enchantment spell (116.2d: Bob, with fewer, can)."""
    s, _ = _engine(cards)
    c = to_hand(s, name)
    fund(s, "{2}{G}")
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p1", type="cast_spell", card_id=c.id)


def test_damping_engine_allows_other_spells_and_stops_land_plays(cards):
    s, _ = _engine(cards)
    to_hand(s, "Shock")
    fund(s, "{R}")
    cast(s, "Shock", targets=["p2"], pay=False)
    answer(s)
    assert life(s, "p2") == 38
    land = to_hand(s, "Forest")
    with pytest.raises(ActionError, match="can't play lands"):
        act(s, "p1", type="play_land", card_id=land.id)
    check(s)


def test_damping_engine_binds_nobody_on_a_tie(cards):
    s, _ = _engine(cards)
    put(s, "Island", "p2")
    c = to_hand(s, "Sol Ring")
    fund(s, "{1}")
    act(s, "p1", type="cast_spell", card_id=c.id)  # 1 permanent each: nobody controls more
    answer(s)
    assert s.state.cards[c.id].zone == "p1:battlefield"


def test_damping_engine_sacrifice_special_action_ignores_it_until_end_of_turn(cards):
    """116.2d: sacrificing a permanent of its player's choice is a special action (no stack), lasts the turn and works once."""
    s, eng = _engine(cards)
    forest = put(s, "Forest")
    c = to_hand(s, "Sol Ring")
    fund(s, "{1}")
    act(s, "p1", type="end_effect", card_id=eng.id)
    assert not s.state.zones.get("stack")
    answer(s, forest.id)
    assert s.state.cards[forest.id].zone == "p1:graveyard"
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert s.state.cards[c.id].zone == "p1:battlefield"
    check(s)
    next_turn(s)
    c2 = to_hand(s, "Llanowar Elves")
    fund(s, "{G}")
    put(s, "Forest")
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p1", type="cast_spell", card_id=c2.id)  # new turn: the effect applies again


def _zones(s, name, pid):
    return [c.zone for c in s.state.cards.values() if c.name == name and c.owner == pid]


def test_chaotic_transformation_each_controller_finds_a_card_sharing_a_type_with_the_exiled_permanent(cards):
    """Exile an artifact and a creature of different controllers; each controller reveals until a card sharing a type, puts it onto the battlefield, shuffles."""
    s = build(cards, ["Chaotic Transformation", "Sol Ring", "Arcane Signet"], ["Llanowar Elves", "Birds of Paradise"])
    ring = put(s, "Sol Ring")
    elves = put(s, "Llanowar Elves", "p2")
    cast(s, "Chaotic Transformation", targets=[ring.id, elves.id], target_counts=[1, 1, 0, 0, 0])
    answer(s)
    assert s.state.cards[ring.id].zone == "p1:exile" and s.state.cards[elves.id].zone == "p2:exile"
    assert _zones(s, "Arcane Signet", "p1") == ["p1:battlefield"] and _zones(s, "Birds of Paradise", "p2") == ["p2:battlefield"]
    check(s)


def test_chaotic_transformation_controller_of_several_chooses_the_order(cards):
    """Ruling 2022-09-09: a player who controls several exiled permanents chooses which one they consider first."""
    s = build(cards, ["Chaotic Transformation"], ["Llanowar Elves", "Birds of Paradise"])
    elves = put(s, "Llanowar Elves", "p2")
    isle = put(s, "Island", "p2")
    cast(s, "Chaotic Transformation", targets=[elves.id, isle.id], target_counts=[0, 1, 0, 0, 1])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and len(d.options) == 2
    answer(s)
    assert _zones(s, "Birds of Paradise", "p2") == ["p2:battlefield"]
    assert sum(1 for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:battlefield") == 1  # one land found for the exiled land
    check(s)
