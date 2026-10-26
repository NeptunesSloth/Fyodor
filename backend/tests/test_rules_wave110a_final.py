"""Wave 110A final pass: Ice Cave (118.12, 107.3h), ..."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules.plan import Plan
from tests.test_rules_wave30p_combat import three, to_phase
from tests.wave110a_kit import *

NAMES = ["Ice Cave", "Damping Engine", "Chaotic Transformation", "Grime Gorger", "Uldaros Theorix", "Dark Intimations", "Exterminator Magmarch", "Threefold Signal", "Deification", "Voltaic Visionary // Volt-Charged Berserker",
         "Prowl, Stoic Strategist // Prowl, Pursuit Vehicle", "Snowblind",
         "Eye of Ojer Taq // Apex Observatory", "Apple of Eden, Isu Relic", "Lucy MacLean, Positively Armed", "False Orders"]


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


def _magmarch(cards, bob=("Llanowar Elves",), carol=("Birds of Paradise",), shock_at=None):
    names_b = [n for n in bob]
    s = three(cards, ["Exterminator Magmarch", "Shock"], names_b, list(carol))
    put(s, "Exterminator Magmarch")
    mine = {n: put(s, n, "p2") for n in bob}
    theirs = {n: put(s, n, "p3") for n in carol}
    fund(s, "{R}")
    cast(s, "Shock", targets=[(shock_at or mine[bob[0]]).id], pay=False)
    return s, mine, theirs


def test_magmarch_copies_the_spell_at_the_other_opponents_only_permanent(cards):
    """Exterminator Magmarch: Alice's Shock at Bob's Llanowar Elves; Carol controls a nonland permanent it could target, so the copy kills Birds of Paradise too."""
    s, bob, carol = _magmarch(cards)
    answer(s)
    assert s.state.cards[bob["Llanowar Elves"].id].zone == "p2:graveyard" and s.state.cards[carol["Birds of Paradise"].id].zone == "p3:graveyard"
    check(s)


def test_magmarch_asks_which_of_several_permanents_the_copy_targets(cards):
    s, bob, carol = _magmarch(cards, carol=("Birds of Paradise", "Llanowar Elves"))
    d = s.state.rules.decision
    for _ in range(3):
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert d is not None and d.player == "p1" and sorted(o.label for o in d.options) == ["Birds of Paradise", "Llanowar Elves"]  # (Bob's own is not among them)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[carol["Llanowar Elves"].id])
    answer(s)
    assert s.state.cards[carol["Llanowar Elves"].id].zone == "p3:graveyard" and s.state.cards[carol["Birds of Paradise"].id].zone == "p3:battlefield"
    check(s)


def test_magmarch_does_not_trigger_when_no_other_opponent_has_a_nonland_permanent(cards):
    """Ruling 2024-06-07: Carol has only a land (a nonland permanent is required): no trigger, no copy."""
    s = three(cards, ["Exterminator Magmarch", "Shock"], ["Llanowar Elves"], [])
    put(s, "Exterminator Magmarch")
    elves = put(s, "Llanowar Elves", "p2")
    put(s, "Island", "p3")
    fund(s, "{R}")
    cast(s, "Shock", targets=[elves.id], pay=False)
    answer(s)
    assert s.state.cards[elves.id].zone == "p2:graveyard"
    assert not any(e for e in s.state.log if "Magmarch" in repr(e.parts) and "Resolved" in repr(e.parts))
    check(s)


def test_magmarch_ignores_a_spell_that_targets_a_player_or_two_things(cards):
    s = three(cards, ["Exterminator Magmarch", "Shock"], ["Llanowar Elves"], ["Birds of Paradise"])
    put(s, "Exterminator Magmarch")
    put(s, "Llanowar Elves", "p2")
    birds = put(s, "Birds of Paradise", "p3")
    fund(s, "{R}")
    cast(s, "Shock", targets=["p2"], pay=False)  # a player: not a nonland permanent
    answer(s)
    assert s.state.cards[birds.id].zone == "p3:battlefield" and life(s, "p2") == 38
    check(s)


def test_threefold_signal_gives_replicate_three_to_spells_of_exactly_three_colors(cards):
    """702.56a, ruling 2022-04-29: Woolly Thoctar (red, green and white) cast with one replicate payment of {3} makes one copy, a token; Grizzly Bears (one color) gets none."""
    s = build(cards, ["Threefold Signal", "Woolly Thoctar", "Grizzly Bears"])
    put(s, "Threefold Signal")
    c = to_hand(s, "Woolly Thoctar")
    fund(s, "{R}{G}{W}{3}")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1)
    answer(s)
    assert sum(1 for x in s.state.cards.values() if x.name == "Woolly Thoctar" and x.zone == "p1:battlefield") == 2
    b = to_hand(s, "Grizzly Bears")
    fund(s, "{1}{G}{3}")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=b.id, kicker=1)
    check(s)


def _deification(cards, chosen="Jace", creature=True, loyalty=2):
    s = build(cards, ["Deification", "Jace Beleren", "Karn Liberated", "Llanowar Elves", "Shock"], ["Shock"])
    cast(s, "Deification")
    answer(s, chosen)
    for n in ("Jace Beleren", "Karn Liberated"):
        w = put(s, n)
        act(s, "p1", type="set_counter", card_id=w.id, kind="loyalty", value=loyalty)
    if creature:
        put(s, "Llanowar Elves")
    return s, card_named(s, "Jace Beleren"), card_named(s, "Karn Liberated")


def _shock(s, target, pid="p1"):
    fund(s, "{R}", pid)
    cast(s, "Shock", targets=[target.id], pid=pid, pay=False)
    answer(s)


def test_deification_records_the_chosen_type_and_all_but_one_loyalty_counter_is_removed(cards):
    """Deification: Alice chooses Jace; with a creature, Shock (2) at her Jace Beleren (2 loyalty) leaves it at 1 (the damage is still dealt)."""
    s, jace, karn = _deification(cards)
    assert card_named(s, "Deification").choices.get("Chosen planeswalker type") == "Jace"
    _shock(s, jace)
    assert s.state.cards[jace.id].zone == "p1:battlefield" and _loyalty(s, jace) == 1
    check(s)


@pytest.mark.parametrize(("chosen", "creature"), [("Jace", False), ("Chandra", True)])
def test_deification_does_not_apply_without_a_creature_or_for_another_type(cards, chosen, creature):
    s, jace, karn = _deification(cards, chosen, creature)
    _shock(s, jace)
    assert s.state.cards[jace.id].zone == "p1:graveyard"
    check(s)


def test_deification_normal_damage_that_leaves_loyalty_is_unchanged(cards):
    s, jace, karn = _deification(cards, loyalty=5)
    _shock(s, jace)
    assert _loyalty(s, jace) == 3
    check(s)


def test_deification_gives_chosen_type_planeswalkers_hexproof(cards):
    """Bob can't target Alice's Jace Beleren with Shock (hexproof) but can target her Karn (not the chosen type)."""
    s, jace, karn = _deification(cards, loyalty=4)
    act(s, "p2", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    act(s, "p1", type="pass_priority")  # (Bob gets priority in Alice's main phase)
    assert s.state.rules.priority == "p2"
    fund(s, "{R}", "p2")
    c = to_hand(s, "Shock", "p2")
    with pytest.raises(ActionError, match="legal|target"):
        act(s, "p2", type="cast_spell", card_id=c.id, targets=[jace.id])
    act(s, "p2", type="cast_spell", card_id=c.id, targets=[karn.id])
    answer(s)
    assert _loyalty(s, karn) == 2
    check(s)


VV = "Voltaic Visionary // Volt-Charged Berserker"


def _visionary(cards, top):
    s = build(cards, [VV, "Divination", "Sol Ring"])
    v = put(s, VV)
    next_turn(s)  # (no summoning sickness; the top card is chosen after the draw step)
    top_card = card_named(s, top) if top != "Forest" else next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[top_card.id], to={"player": "p1", "zone": "library"}, position="top")
    ab = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[v.id]).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=v.id, ability=ab)
    answer(s)
    return s, v, top_card


def test_voltaic_visionary_land_exiled_with_it_played_transforms_it(cards):
    """Voltaic Visionary: {T}: 2 damage to you, exile the top card, you may play it this turn. Playing that land (305.1) transforms it (607.2a link)."""
    s, v, land = _visionary(cards, "Forest")
    assert s.state.cards[land.id].zone == "p1:exile" and life(s, "p1") == 38
    assert not _is_back(s, v)
    act(s, "p1", type="play_land", card_id=land.id)
    answer(s)
    assert s.state.cards[land.id].zone == "p1:battlefield"
    assert _is_back(s, v)
    check(s)


def _is_back(s, v):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[v.id]).name == "Volt-Charged Berserker"


def test_voltaic_visionary_spell_exiled_with_it_cast_transforms_it_before_it_resolves(cards):
    s, v, spell = _visionary(cards, "Divination")
    fund(s, "{2}{U}")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert _is_back(s, v)
    check(s)


def test_voltaic_visionary_does_not_transform_for_a_card_not_exiled_with_it(cards):
    s, v, land = _visionary(cards, "Forest")
    other = to_hand(s, "Sol Ring")
    fund(s, "{1}")
    act(s, "p1", type="cast_spell", card_id=other.id)
    answer(s)
    assert not _is_back(s, v)
    check(s)


PROWL = "Prowl, Stoic Strategist // Prowl, Pursuit Vehicle"


def _prowl_attack(cards, creature="Llanowar Elves"):
    s = build(cards, [PROWL], [creature])
    prowl = put(s, PROWL)
    victim = put(s, creature, "p2")
    next_turn(s)
    act(s, "p2", type="tap", card_ids=[victim.id])
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": prowl.id, "target": "p2"}])
    answer(s, victim.id)
    return s, prowl, victim


def test_prowl_exiles_a_tapped_creature_and_its_owner_may_play_it_then_prowl_converts_and_controller_draws(cards):
    """Prowl: Elves (tapped) exiled; Bob, its owner, casts it from exile on his turn (607.2a play of a card exiled with Prowl): Alice draws and Prowl converts (ruling 2022-10-14)."""
    s, prowl, elves = _prowl_attack(cards)
    assert s.state.cards[elves.id].zone == "p2:exile"
    hand = len(s.state.zones["p1:hand"])
    to_phase(s, "main1", turn=s.state.turn.number + 1)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[prowl.id]).name == "Prowl, Stoic Strategist"
    fund(s, "{G}", "p2")
    act(s, "p2", type="cast_spell", card_id=elves.id)
    answer(s)
    assert s.state.cards[elves.id].zone == "p2:battlefield"
    assert len(s.state.zones["p1:hand"]) == hand + 1
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[prowl.id]).name == "Prowl, Pursuit Vehicle"
    check(s)


def test_prowl_a_card_not_exiled_with_it_does_nothing(cards):
    s, prowl, elves = _prowl_attack(cards)
    to_phase(s, "main1", turn=s.state.turn.number + 1)
    other = to_hand(s, "Island", "p2")
    act(s, "p2", type="play_land", card_id=other.id)
    answer(s)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[prowl.id]).name == "Prowl, Stoic Strategist"
    check(s)


SNOWS = ["Snow-Covered Island", "Snow-Covered Swamp", "Snow-Covered Mountain", "Snow-Covered Plains"]


def _snowblind(cards, mine_snow=1, bob_snow=3, growth=False):
    s = build(cards, ["Snowblind", "Hill Giant", "Giant Growth", "Snow-Covered Forest"], SNOWS)
    giant = put(s, "Hill Giant")
    put(s, "Snow-Covered Forest")
    for n in SNOWS[:bob_snow]:
        put(s, n, "p2")
    cast(s, "Snowblind", targets=[giant.id])
    answer(s)
    return s, giant


@pytest.mark.parametrize("bob_snow", [0, 2])
def test_snowblind_not_attacking_counts_its_controllers_snow_lands(cards, bob_snow):
    """Snowblind on Alice's Hill Giant (3/3); Alice has 1 snow land, Bob 0 or 2: not attacking, X = 1 -> -1/-1 (Y = min(1, 3-1))."""
    s, giant = _snowblind(cards, bob_snow=bob_snow)
    assert pt(s, "Hill Giant") == (2, 2)


def test_snowblind_y_is_capped_by_toughness_minus_one_so_the_creature_survives(cards):
    """Five snow lands for Alice would be -5/-5: Y = min(5, 3-1) = 2 gives -5/-2, a 3/3 becomes -2/1 and stays."""
    s = build(cards, ["Snowblind", "Hill Giant", *SNOWS, "Snow-Covered Forest"])
    giant = put(s, "Hill Giant")
    for n in (*SNOWS, "Snow-Covered Forest"):
        put(s, n)
    cast(s, "Snowblind", targets=[giant.id])
    answer(s)
    assert pt(s, "Hill Giant") == (-2, 1) and s.state.cards[giant.id].zone == "p1:battlefield"
    check(s)


def test_snowblind_reads_toughness_after_the_other_layer_7c_effects_whenever_they_came(cards):
    """613.8a-b: Y depends on the other toughness modifiers, which apply first even though Giant Growth (+3/+3) is newer: 6/6, then with five snow lands -5/-min(5, 5) = 1/1 (applied first it would end 1/4)."""
    s = build(cards, ["Snowblind", "Hill Giant", "Giant Growth", *SNOWS, "Snow-Covered Forest"])
    giant = put(s, "Hill Giant")
    for n in (*SNOWS, "Snow-Covered Forest"):
        put(s, n)
    cast(s, "Snowblind", targets=[giant.id])
    answer(s)
    cast(s, "Giant Growth", targets=[giant.id])
    answer(s)
    assert pt(s, "Hill Giant") == (1, 1)
    check(s)


def test_snowblind_attacking_counts_the_defending_players_snow_lands(cards):
    """Attacking Bob (3 snow lands) the Giant gets X = 3: -3/-2 -> 0/1; before and after combat X is Alice's (1)."""
    s, giant = _snowblind(cards, bob_snow=3)
    assert pt(s, "Hill Giant") == (2, 2)
    next_turn(s)
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p2"}])
    assert pt(s, "Hill Giant") == (0, 1)
    check(s)


EYE = "Eye of Ojer Taq // Apex Observatory"


def _craft_eye(cards, on_field, in_gy):
    s = build(cards, [EYE, *on_field, *in_gy, "Arcane Signet", "Wall of Omens"])
    eye = put(s, EYE)
    mats = [put(s, n) for n in on_field]
    gone = [to_hand(s, n) for n in in_gy]
    if gone:
        act(s, "p1", type="move", card_ids=[c.id for c in gone], to={"player": "p1", "zone": "graveyard"})
    fund(s, "{6}")
    ab = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[eye.id]).abilities if a.kind == "activated" and "Exile" in a.text and a.index != 0)
    return s, eye, [*mats, *gone], ab


def test_eye_of_ojer_taq_craft_needs_two_that_share_a_card_type_and_chooses_one_they_share(cards):
    """Craft with two that share a card type: Sol Ring (artifact, battlefield) and Arcane Signet (artifact, graveyard) are exiled; Apex Observatory enters tapped with Artifact chosen."""
    s, eye, mats, ab = _craft_eye(cards, ["Sol Ring"], ["Walking Ballista"])
    act(s, "p1", type="activate_ability", card_id=eye.id, ability=ab, cost_choices=[{"component": 2, "cards": [m.id for m in mats]}])
    answer(s)
    assert s.state.cards[eye.id].face == 1 and all(s.state.cards[m.id].zone == "p1:exile" for m in mats)
    assert s.state.cards[eye.id].tapped and s.state.cards[eye.id].choices.get("Chosen card type") == "Artifact"
    check(s)


def test_eye_of_ojer_taq_materials_that_share_no_type_cannot_be_exiled(cards):
    s, eye, mats, ab = _craft_eye(cards, ["Sol Ring"], ["Llanowar Elves"])
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=eye.id, ability=ab, cost_choices=[{"component": 2, "cards": [m.id for m in mats]}])
    assert s.state.cards[eye.id].face == 0


def test_apex_observatory_makes_the_next_spell_of_the_chosen_type_free_once(cards):
    """{T}: the next spell you cast this turn of the chosen type (artifact) is free: Arcane Signet costs nothing, a Wall of Omens (creature) still costs mana."""
    s, eye, mats, ab = _craft_eye(cards, ["Sol Ring"], ["Walking Ballista"])
    act(s, "p1", type="activate_ability", card_id=eye.id, ability=ab, cost_choices=[{"component": 2, "cards": [m.id for m in mats]}])
    answer(s)
    next_turn(s)
    act(s, "p1", type="activate_ability", card_id=eye.id, ability=next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[eye.id]).abilities if a.kind == "activated"))
    answer(s)
    wall = to_hand(s, "Wall of Omens")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=wall.id, free=True)  # a creature spell is not of the chosen type: it can't be cast for free
    signet = to_hand(s, "Arcane Signet")
    act(s, "p1", type="cast_spell", card_id=signet.id, free=True)
    answer(s)
    assert s.state.cards[signet.id].zone == "p1:battlefield"
    again = to_hand(s, "Sol Ring")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=again.id, free=True)  # only the next one
    check(s)


APPLE = "Apple of Eden, Isu Relic"


def _apple(cards):
    s = build(cards, [APPLE], ["Island", "Shock", "Llanowar Elves", "Wall of Omens"])
    apple = put(s, APPLE)
    next_turn(s)
    for n in ("Island", "Shock", "Llanowar Elves"):
        to_hand(s, n, "p2")
    act(s, "p1", type="activate_ability", card_id=apple.id, ability=0, targets=["p2"])
    answer(s)
    return s, apple


def _exiled(s, name):
    """The face-down card of that name Alice exiled from Bob's hand (a face-down card in exile is a new object with its own id)."""
    return next(c for c in s.state.cards.values() if c.name == name and c.zone == "p2:exile")


def test_apple_of_eden_exiles_the_hand_face_down_and_its_cards_can_be_played_for_any_mana_and_the_owner_draws(cards):
    """Apple of Eden: Bob's hand goes face down into exile; Alice plays the Island (Bob draws), casts Shock with colorless mana (118.14; Bob draws); the Llanowar Elves returns at the end step."""
    s, apple = _apple(cards)
    assert life(s, "p1") == 36 and s.state.cards[apple.id].zone == "p1:graveyard"
    exiled = {n: _exiled(s, n) for n in ("Island", "Shock", "Llanowar Elves")}
    assert all(c.face_down for c in exiled.values()) and not s.state.zones.get("p2:hand")
    act(s, "p1", type="play_land", card_id=exiled["Island"].id)
    answer(s)
    assert len(s.state.zones["p2:hand"]) == 1  # its owner drew
    fund(s, "{C}")
    act(s, "p1", type="cast_spell", card_id=exiled["Shock"].id, targets=["p2"])
    answer(s)
    assert len(s.state.zones["p2:hand"]) == 2 and life(s, "p2") == 38
    goto(s, "end")
    answer(s)
    assert any(c.name == "Llanowar Elves" and c.zone == "p2:hand" for c in s.state.cards.values())  # (still exiled: returned; the Island and Shock were played: not)
    assert any(c.name == "Island" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    check(s)


LUCY = "Lucy MacLean, Positively Armed"


def _soldiers(s, pid):
    return [c for c in s.state.cards.values() if c.name == "Soldier" and c.zone == f"{pid}:battlefield"]


def _run(s, targets=(), confirms=()):
    """Resolve everything: trigger orders keep their order, targets and confirmations are answered from the lists (by label), else the first option."""
    targets, confirms = list(targets), list(confirms)
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "order":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        elif d.kind == "confirm":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[confirms.pop(0) if confirms else "yes"])
        else:
            want = targets.pop(0) if targets else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o.id for o in d.options if o.label == want), d.options[0].id)])
    raise AssertionError("never settled")


def _lucy_alarm(cards, targets, confirms):
    s = three(cards, [LUCY, "Raise the Alarm"], [], [])
    put(s, LUCY)
    fund(s, "{1}{W}")
    cast(s, "Raise the Alarm", pay=False)
    _run(s, targets, confirms)
    return s


def test_lucy_macLean_another_player_creates_a_copy_of_the_token_and_lucys_controller_draws_once_a_turn(cards):
    """Golden Rule: Raise the Alarm makes two Soldiers, two triggers (the one ordered last resolves first); it has Carol create a copy (Alice draws, Carol is an opponent); the other, and the one
    for the copy's own entering, do nothing: once each turn."""
    s = _lucy_alarm(cards, ["Bob", "Carol"], ["yes", "yes", "yes"])
    assert len(_soldiers(s, "p3")) == 1 and not _soldiers(s, "p2") and len(_soldiers(s, "p1")) == 2
    assert len(s.state.zones["p1:hand"]) == 1
    check(s)


def test_lucy_declining_does_not_use_up_the_turn(cards):
    s = _lucy_alarm(cards, ["Bob", "Carol"], ["no", "yes", "yes"])  # (the first to resolve, aimed at Carol, is declined; the next, aimed at Bob, is done)
    assert len(_soldiers(s, "p2")) == 1 and not _soldiers(s, "p3") and len(s.state.zones["p1:hand"]) == 1
    check(s)


def test_lucy_the_chosen_player_may_be_lucys_controller_when_an_opponents_token_entered_and_no_card_is_drawn(cards):
    """Bob's Soldiers enter: "target player other than its controller" excludes Bob; Alice chooses herself: she creates a copy and, no opponent having created it, draws nothing."""
    s = three(cards, [LUCY], ["Raise the Alarm"], [])
    put(s, LUCY)
    to_phase(s, "main1", turn=2)
    hand = len(s.state.zones["p1:hand"])
    fund(s, "{1}{W}", "p2")
    c = to_hand(s, "Raise the Alarm", "p2")
    act(s, "p2", type="cast_spell", card_id=c.id)
    d = None
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        if d is not None and d.kind == "order":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and sorted(o.label for o in d.options) == ["Alice", "Carol"]  # never Bob
    _run(s, ["Alice", "Alice", "Alice"], ["yes", "yes", "yes"])
    assert len(_soldiers(s, "p1")) == 1 and len(_soldiers(s, "p2")) == 2
    assert len(s.state.zones["p1:hand"]) == hand  # no opponent created a token: no card
    check(s)


def _false_orders(cards, blocks=True):
    """Alice attacks Bob with Grizzly Bears and Hill Giant; Bob's Wall of Omens blocks the Bears; Alice casts False Orders on the Wall in the declare blockers step."""
    s = build(cards, ["Grizzly Bears", "Hill Giant", "False Orders"], ["Wall of Omens"])
    bears, giant = put(s, "Grizzly Bears"), put(s, "Hill Giant")
    wall = put(s, "Wall of Omens", "p2")
    next_turn(s)
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}, {"card_id": giant.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": bears.id}] if blocks else [])
    until(s, lambda s: s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1")
    fund(s, "{R}")
    c = to_hand(s, "False Orders")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[wall.id], free=False)
    return s, bears, giant, wall


@pytest.mark.parametrize("block", [True, False])
def test_false_orders_unblocks_what_only_it_blocked_and_it_may_block_another_attacker(cards, block):
    """False Orders: the Wall leaves combat, the Bears (blocked only by it) become unblocked, then Alice may have the Wall block the Hill Giant."""
    s, bears, giant, wall = _false_orders(cards)
    d = None
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and d.min_choices == 0 and giant.id in [o.id for o in d.options]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant.id] if block else [])
    until(s, lambda s: s.state.turn.phase == "end_combat" or s.state.turn.phase == "main2")
    assert life(s, "p2") == 40 - 2 - (0 if block else 3)  # the Bears are unblocked; the Giant is unblocked only if the Wall was not made to block it
    assert s.state.cards[wall.id].zone == "p2:battlefield" and s.state.cards[giant.id].zone == "p1:battlefield"
    check(s)


def test_false_orders_on_a_creature_that_is_not_blocking_may_still_have_it_block(cards):
    """The target need not be blocking: nothing to remove or unblock, and Alice may still have the Wall block the Bears (so the Giant alone is unblocked)."""
    s, bears, giant, wall = _false_orders(cards, blocks=False)
    d = None
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and {bears.id, giant.id} <= {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == 40 - 3
    check(s)
