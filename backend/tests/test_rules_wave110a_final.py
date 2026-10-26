"""Wave 110A final pass: Ice Cave (118.12, 107.3h), ..."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110a_kit import *

NAMES = ["Ice Cave", "Damping Engine", "Chaotic Transformation", "Grime Gorger", "Uldaros Theorix", "Dark Intimations"]


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


def _bob_graveyard(s, *names):
    for n in names:
        act(s, "p2", type="move", card_ids=[card_named(s, n, "p2").id], to={"player": "p2", "zone": "graveyard"})


def _attack_with_gorger(cards, theirs):
    s = build(cards, ["Grime Gorger"], theirs)
    gorger = put(s, "Grime Gorger")
    _bob_graveyard(s, *theirs)
    next_turn(s)
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": gorger.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None)
    return s, gorger


def test_grime_gorger_exiles_one_card_of_each_type_and_grows_per_card(cards):
    """Grime Gorger: Bob's graveyard holds an artifact, two creatures, an instant and a land; Alice exiles one of each type (4) and gets four +1/+1 counters."""
    names = ["Sol Ring", "Llanowar Elves", "Birds of Paradise", "Shock", "Island"]
    s, gorger = _attack_with_gorger(cards, names)
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and d.player == "p1" and d.min_choices == 0
    ids = {n: card_named(s, n, "p2").id for n in names}
    with pytest.raises(ActionError, match="one card of each card type"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[ids["Llanowar Elves"], ids["Birds of Paradise"]])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[ids[n] for n in ("Sol Ring", "Llanowar Elves", "Shock", "Island")])
    assert [s.state.cards[ids[n]].zone for n in names] == ["p2:exile"] * 2 + ["p2:graveyard", "p2:exile", "p2:exile"]
    assert s.state.cards[gorger.id].counters.get("+1/+1") == 4
    check(s)


def test_grime_gorger_choosing_none_is_allowed(cards):
    s, gorger = _attack_with_gorger(cards, ["Sol Ring"])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    assert not s.state.cards[gorger.id].counters.get("+1/+1")
    check(s)


@pytest.mark.parametrize(("picks", "ok"), [(("Walking Ballista", "Sol Ring"), True), (("Walking Ballista", "Sol Ring", "Llanowar Elves"), False),
                                           (("Walking Ballista", "Llanowar Elves"), True)])
def test_grime_gorger_a_card_with_two_types_takes_up_one_of_them(cards, picks, ok):
    """An artifact creature stands for the artifact or the creature, not both: with a Sol Ring and a Llanowar Elves too, three cards are one too many."""
    names = ["Walking Ballista", "Sol Ring", "Llanowar Elves"]
    s, gorger = _attack_with_gorger(cards, names)
    d = s.state.rules.decision
    ids = [card_named(s, n, "p2").id for n in picks]
    if ok:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=ids)
        assert s.state.cards[gorger.id].counters.get("+1/+1") == len(picks)
    else:
        with pytest.raises(ActionError, match="one card of each card type"):
            act(s, "p1", type="choose", decision_id=d.id, option_ids=ids)


def _alice_graveyard(s, *names):
    for n in names:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})


def _uldaros(cards):
    s = build(cards, ["Uldaros Theorix", "Sol Ring", "Wall of Omens", "Divination", "Shock", "Walking Ballista"])
    _alice_graveyard(s, "Sol Ring", "Wall of Omens", "Divination", "Shock", "Forest")
    return s, {n: card_named(s, n).id for n in ("Sol Ring", "Wall of Omens", "Divination", "Shock", "Walking Ballista")}


def test_uldaros_theorix_copies_one_card_per_type_and_casts_copies_up_to_total_mana_value_six(cards):
    """Uldaros: four targets (artifact, creature, instant, sorcery), all exiled and copied; Sol Ring 1 + Wall of Omens 2 + Divination 3 = 6, so Shock (1 more) is not offered."""
    s, ids = _uldaros(cards)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Uldaros Theorix")
    answer(s, "Sol Ring", "Wall of Omens", "Shock", "Divination", "Sol Ring", "Wall of Omens", "Divination")
    assert [s.state.cards[ids[n]].zone for n in ("Sol Ring", "Wall of Omens", "Shock", "Divination")] == ["p1:exile"] * 4  # the originals stay exiled
    assert s.state.cards[card_named(s, "Forest").id].zone == "p1:graveyard"  # (a land: not a legal target)
    bf = sorted(c.name for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name != "Uldaros Theorix")
    assert bf == ["Sol Ring", "Wall of Omens"]  # permanent spells cast this way become tokens: two copies on the battlefield
    assert len(s.state.zones["p1:hand"]) == hand + 3  # Divination's copy drew two, the Wall of Omens token one
    assert life(s, "p2") == 40  # no Shock copy: 1 + 2 + 3 used the whole budget
    check(s)


def test_uldaros_theorix_no_target_is_allowed_and_a_land_is_not_offered(cards):
    s, ids = _uldaros(cards)
    c = to_hand(s, "Uldaros Theorix")
    fund(s, c and (s.cards.resolve("Uldaros Theorix").get("mana_cost") or ""))
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = s.state.rules.decision
    for _ in range(3):
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert d is not None and "Forest" not in [o.label for o in d.options]  # "nonland"
    answer(s, [], [], [], [], [], [], [], [])  # up to one: none at all, nothing copied
    assert not [c for c in s.state.cards.values() if c.zone == "p1:exile"]
    check(s)


def test_uldaros_theorix_without_being_cast_does_nothing(cards):
    """"if you cast him" (intervening if, 603.4): put onto the battlefield by an effect, he exiles nothing."""
    s, ids = _uldaros(cards)
    put(s, "Uldaros Theorix")
    answer(s)
    assert s.state.cards[ids["Sol Ring"]].zone == "p1:graveyard"
    check(s)


def _loyalty(s, c):
    return s.state.cards[c.id].counters.get("loyalty", 0)


def test_dark_intimations_each_opponent_sacrifices_and_discards_then_you_return_and_draw(cards):
    """Dark Intimations: Bob sacrifices his creature or planeswalker (his choice) then discards; Alice returns a creature or planeswalker card to hand, then draws."""
    s = build(cards, ["Dark Intimations", "Wall of Omens", "Sol Ring"], ["Llanowar Elves", "Shock", "Nicol Bolas, Dragon-God"])
    _alice_graveyard(s, "Wall of Omens")
    elves = put(s, "Llanowar Elves", "p2")
    bolas = put(s, "Nicol Bolas, Dragon-God", "p2")
    act(s, "p2", type="set_counter", card_id=bolas.id, kind="loyalty", value=5)
    to_hand(s, "Shock", "p2")
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Dark Intimations")
    answer(s, bolas.id)
    assert s.state.cards[bolas.id].zone == "p2:graveyard" and s.state.cards[elves.id].zone == "p2:battlefield"
    assert card_named(s, "Shock", "p2").zone == "p2:graveyard"
    assert card_named(s, "Wall of Omens").zone == "p1:hand"
    assert len(s.state.zones["p1:hand"]) == hand + 2  # the returned creature card and the drawn card
    check(s)


@pytest.mark.parametrize(("name", "cost", "loyalty"), [("Nicol Bolas, Dragon-God", "{U}{B}{B}{B}{R}", 5), ("Karn Liberated", "{7}", 6)])
def test_dark_intimations_in_the_graveyard_gives_a_bolas_planeswalker_spell_an_extra_loyalty(cards, name, cost, loyalty):
    """113.6m / 614.1c: only a Bolas planeswalker spell exiles it from the graveyard and enters with one more loyalty counter (Dragon-God 4 -> 5; Karn stays 6)."""
    s = build(cards, ["Dark Intimations", name])
    _alice_graveyard(s, "Dark Intimations")
    cast(s, name)
    answer(s)
    walker = card_named(s, name)
    bolas = name.startswith("Nicol")
    assert s.state.cards[walker.id].zone == "p1:battlefield" and _loyalty(s, walker) == loyalty
    assert card_named(s, "Dark Intimations").zone == ("p1:exile" if bolas else "p1:graveyard")
    check(s)


def test_two_dark_intimations_give_two_extra_loyalty_counters(cards):
    """Ruling 2017-02-09: each one in the graveyard is exiled and the planeswalker gets that many additional counters."""
    s = build(cards, ["Dark Intimations", "Dark Intimations", "Nicol Bolas, Dragon-God"])
    for c in [c for c in s.state.cards.values() if c.name == "Dark Intimations"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Nicol Bolas, Dragon-God")
    answer(s)
    assert _loyalty(s, card_named(s, "Nicol Bolas, Dragon-God")) == 6
    assert all(c.zone == "p1:exile" for c in s.state.cards.values() if c.name == "Dark Intimations")
    check(s)
