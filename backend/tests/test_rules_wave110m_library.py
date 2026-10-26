"""Wave 110M: effects that read or move the top card of a library. Every scenario checks the replay and a save and a load.

* 613.4c, 400.7: "As long as the top card of your library is a creature card, creatures you control that share a color with that card get +1/+1." and
  "{G}{W}: Put the top card of your library on the bottom of your library." (Crown of Convergence).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError

from tests.wave36a_kit import ready, to_turn_of
from tests.wave110m_kit import *

CROWN = "Crown of Convergence"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([CROWN])


def on_top(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


def top(s, pid="p1"):
    return s.state.zones[f"{pid}:library"][0]


# top card -> (Bears (green) pt, Lions (white) pt)
@pytest.mark.parametrize("top_name,bears,lions", [
    ("Llanowar Elves", (3, 3), (2, 1)),     # a green creature card: green creatures
    ("Elite Vanguard", (2, 2), (3, 2)),      # a white creature card: white creatures
    ("Forest", (2, 2), (2, 1)),              # not a creature card: nobody
])
def test_crown_pumps_the_creatures_sharing_a_color_with_a_top_creature_card(cards, top_name, bears, lions):
    s = build(cards, [CROWN, "Grizzly Bears", "Savannah Lions", "Llanowar Elves", "Elite Vanguard"])
    for n in (CROWN, "Grizzly Bears", "Savannah Lions"):
        put(s, n)
    on_top(s, top_name)
    assert pt(s, "Grizzly Bears") == bears and pt(s, "Savannah Lions") == lions
    check(s)


def test_crown_ability_puts_the_top_card_on_the_bottom_and_the_bonus_follows(cards):
    s = build(cards, [CROWN, "Grizzly Bears", "Savannah Lions", "Llanowar Elves", "Elite Vanguard"])
    crown = put(s, CROWN)
    put(s, "Grizzly Bears")
    put(s, "Savannah Lions")
    vanguard = on_top(s, "Elite Vanguard")
    elves = on_top(s, "Llanowar Elves")
    assert pt(s, "Grizzly Bears") == (3, 3) and pt(s, "Savannah Lions") == (2, 1)
    mana(s, G=1, W=1)
    act(s, "p1", type="activate_ability", card_id=crown.id, ability=2)
    answer(s)
    assert top(s) == vanguard.id and s.state.zones["p1:library"][-1] == elves.id
    assert pt(s, "Grizzly Bears") == (2, 2) and pt(s, "Savannah Lions") == (3, 2)
    check(s)


# -- Faces of the Past ----------------------------------------------------------------------------------------------------------------
FACES = "Faces of the Past"


@pytest.mark.parametrize("choice,tapped_after", [("tap", {"Mother of Runes": True, "Llanowar Elves": False, "Savannah Lions": False}),
                                                  ("untap", {"Mother of Runes": False, "Llanowar Elves": True, "Savannah Lions": True})])
def test_faces_of_the_past_taps_or_untaps_only_creatures_sharing_a_type_with_the_dead_one(cards, choice, tapped_after):
    """The controller picks as it resolves; Elite Vanguard (Human Soldier) died, so only the other Human shares a creature type with it (not the Elf or the Cat)."""
    s = build(cards, [FACES, "Elite Vanguard", "Mother of Runes", "Llanowar Elves", "Savannah Lions", "Murder"], forests=20)
    put(s, FACES)
    vanguard = put(s, "Elite Vanguard")
    for n in tapped_after:
        put(s, n)
    if choice == "untap":  # (everything else starts tapped, so only the creatures sharing a type change)
        act(s, "p1", type="tap", card_ids=[card_named(s, n).id for n in tapped_after], tapped=True)
    cast(s, "Murder", [vanguard.id])
    answer(s, choice)
    assert s.state.cards[vanguard.id].zone == "p1:graveyard"
    assert {n: s.state.cards[card_named(s, n).id].tapped for n in tapped_after} == tapped_after
    check(s)


def test_faces_of_the_past_with_a_dying_changeling_reaches_every_creature_with_a_type(cards):
    """702.73a: a changeling has every creature type, so every creature with a creature type shares one with it."""
    s = build(cards, [FACES, "Changeling Outcast", "Mother of Runes", "Llanowar Elves", "Murder"], forests=20)
    put(s, FACES)
    outcast = put(s, "Changeling Outcast")
    put(s, "Mother of Runes")
    put(s, "Llanowar Elves")
    cast(s, "Murder", [outcast.id])
    answer(s, "tap")
    assert s.state.cards[card_named(s, "Mother of Runes").id].tapped and s.state.cards[card_named(s, "Llanowar Elves").id].tapped
    check(s)


# -- Lucius the Eternal ----------------------------------------------------------------------------------------------------------------------
LUCIUS = "Lucius the Eternal"
test_lucius_full = full_test([LUCIUS])


def lucius_table(cards, theirs=("Grizzly Bears",)):
    s = build(cards, [LUCIUS, "Murder", "Doom Blade"], list(theirs), forests=20)
    lucius = put(s, LUCIUS)
    for n in theirs:
        put(s, n, "p2")
    return s, lucius


@pytest.mark.parametrize("dies,returns", [("Elite Vanguard", True), ("Grizzly Bears", False)])
def test_lucius_exiles_itself_and_returns_when_the_chosen_creature_leaves(cards, dies, returns):
    s, lucius = lucius_table(cards, ("Grizzly Bears", "Elite Vanguard"))
    cast(s, "Murder", [lucius.id])
    answer(s, card_named(s, "Elite Vanguard", "p2").id)  # (the chosen creature: Elite Vanguard)
    assert s.state.cards[lucius.id].zone == "p1:exile"
    check(s)
    cast(s, "Doom Blade", [card_named(s, dies, "p2").id])
    answer(s)
    assert zone_of(s, dies, "p2") == "p2:graveyard"
    assert (s.state.cards[lucius.id].zone, s.state.cards[lucius.id].controller) == (("p1:battlefield", "p1") if returns else ("p1:exile", "p1"))
    check(s)


def test_lucius_with_no_opponent_creature_to_choose_stays_in_the_graveyard(cards):
    s, lucius = lucius_table(cards, ())
    cast(s, "Murder", [lucius.id])
    answer(s)
    assert s.state.cards[lucius.id].zone == "p1:graveyard"
    check(s)


# -- Soul Sculptor ---------------------------------------------------------------------------------------------------------------------------
SCULPTOR = "Soul Sculptor"
test_sculptor_full = full_test([SCULPTOR])


def sculpted(cards):
    s = build(cards, [SCULPTOR, "Llanowar Elves", "Lightning Bolt"], ["Birds of Paradise", "Elite Vanguard"], forests=20)
    sculptor = put(s, SCULPTOR)
    birds = put(s, "Birds of Paradise", "p2")
    ready(s, SCULPTOR)
    mana(s, W=1, C=1)
    act(s, "p1", type="activate_ability", card_id=sculptor.id, ability=0, targets=[birds.id])
    answer(s)
    return s, birds


def test_soul_sculptor_makes_the_creature_an_enchantment_without_abilities(cards):
    s, birds = sculpted(cards)
    got = ch(s, birds)
    assert "Creature" not in got.types and "Enchantment" in got.types and "flying" not in got.keywords
    check(s)


def test_soul_sculptor_lasts_through_other_spells_and_across_turns(cards):
    s, birds = sculpted(cards)
    cast(s, "Lightning Bolt", ["p2"])
    answer(s)
    to_turn_of(s, "p2")
    got = ch(s, birds)
    assert "Creature" not in got.types and "flying" not in got.keywords
    check(s)


@pytest.mark.parametrize("caster", ["p1", "p2"])
def test_soul_sculptor_ends_when_any_player_casts_a_creature_spell(cards, caster):
    s, birds = sculpted(cards)
    if caster == "p2":
        to_turn_of(s, "p2")
        cast(s, "Elite Vanguard", pid="p2")
    else:
        cast(s, "Llanowar Elves")
    answer(s)
    got = ch(s, birds)
    assert "Creature" in got.types and "Enchantment" not in got.types and "flying" in got.keywords
    check(s)


# -- Merieke Ri Berit ------------------------------------------------------------------------------------------------------------------------
MERIEKE = "Merieke Ri Berit"
test_merieke_full = full_test([MERIEKE])


def merieke_table(cards):
    s = build(cards, [MERIEKE, "Twiddle", "Murder"], ["Grizzly Bears"], forests=20)
    merieke = put(s, MERIEKE)
    bears = put(s, "Grizzly Bears", "p2")
    ready(s, MERIEKE)
    act(s, "p1", type="activate_ability", card_id=merieke.id, ability=1, targets=[bears.id])
    answer(s)
    assert s.state.cards[bears.id].controller == "p1" and s.state.cards[merieke.id].tapped
    return s, merieke, bears


def test_merieke_steals_the_creature_while_she_stays_tapped_and_controlled(cards):
    s, merieke, bears = merieke_table(cards)
    to_turn_of(s, "p2")
    assert s.state.cards[bears.id].controller == "p1" and s.state.cards[merieke.id].tapped  # (she doesn't untap, and no destroy yet)
    check(s)


def test_merieke_untapping_destroys_the_creature(cards):
    s, merieke, bears = merieke_table(cards)
    cast(s, "Twiddle", [merieke.id])
    answer(s, "untap")
    assert not s.state.cards[merieke.id].tapped and zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    check(s)


def test_merieke_leaving_the_battlefield_destroys_the_creature(cards):
    s, merieke, bears = merieke_table(cards)
    cast(s, "Murder", [merieke.id])
    answer(s)
    assert s.state.cards[merieke.id].zone == "p1:graveyard" and zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    check(s)


# -- Darksteel Garrison (Fortify) --------------------------------------------------------------------------------------------------------------
GARRISON = "Darksteel Garrison"
test_garrison_full = full_test([GARRISON])


def garrison_table(cards):
    s = build(cards, [GARRISON, "Grizzly Bears"], ["Forest"], forests=9)
    garrison = put(s, GARRISON)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    bears = put(s, "Grizzly Bears")
    return s, garrison, s.state.cards[forest.id], bears


def fortify(s, garrison, land):
    fund(s, "{3}")
    act(s, "p1", type="activate_ability", card_id=garrison.id, ability=2, targets=[land.id])
    answer(s)


def test_fortify_attaches_to_a_land_that_then_has_indestructible_and_pumps_a_creature_when_tapped(cards):
    s, garrison, forest, bears = garrison_table(cards)
    fortify(s, garrison, forest)
    assert s.state.cards[garrison.id].attached_to == forest.id and "indestructible" in ch(s, forest).keywords
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)  # tapped for mana: it becomes tapped (603.2)
    answer(s)
    assert pt(s, "Grizzly Bears") == (3, 3)
    check(s)


def test_fortify_is_sorcery_speed_and_needs_a_land_you_control(cards):
    from app.game.errors import ActionError

    s, garrison, forest, bears = garrison_table(cards)
    with pytest.raises(ActionError):
        fund(s, "{3}")
        act(s, "p1", type="activate_ability", card_id=garrison.id, ability=2, targets=[bears.id])  # a creature isn't a land
    to_turn_of(s, "p2")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=garrison.id, ability=2, targets=[forest.id])


# -- Booby Trap ------------------------------------------------------------------------------------------------------------------------------
TRAP = "Booby Trap"
test_trap_full = full_test([TRAP])


def trap_table(cards, drawn="Llanowar Elves"):
    from app.rules import card_names

    s = build(cards, [TRAP, "Llanowar Elves"], ["Llanowar Elves", "Grizzly Bears"], forests=20)
    trap = to_hand(s, TRAP)
    fund(s, "{6}")
    act(s, "p1", type="cast_spell", card_id=trap.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif card_names.is_free_text(d):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[], name="Llanowar Elves")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.cards[trap.id].zone == "p1:battlefield" and s.state.cards[trap.id].choices
    top = card_named(s, drawn, "p2")
    act(s, "p2", type="move", card_ids=[top.id], to={"player": "p2", "zone": "library"}, position="top")
    return s, trap, top


@pytest.mark.parametrize("drawn,explodes", [("Llanowar Elves", True), ("Grizzly Bears", False)])
def test_booby_trap_reveals_each_card_the_chosen_player_draws_and_blows_up_on_the_named_one(cards, drawn, explodes):
    s, trap, top = trap_table(cards, drawn)
    before = life(s, "p2")
    to_turn_of(s, "p2")
    answer(s)
    assert top.id in s.state.zones["p2:hand"]
    assert any("reveals" in "".join(str(getattr(p, "t", p)) for p in e.parts) for e in s.state.log[-40:])
    assert (s.state.cards[trap.id].zone == "p1:graveyard", life(s, "p2")) == ((True, before - 10) if explodes else (False, before))
    check(s)


def test_booby_trap_ignores_the_named_card_drawn_by_a_player_who_was_not_chosen(cards):
    s, trap, top = trap_table(cards)
    mine = card_named(s, "Llanowar Elves", "p1")
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p1", type="draw", player="p1", count=1)
    answer(s)
    assert mine.id in s.state.zones["p1:hand"] and s.state.cards[trap.id].zone == "p1:battlefield" and life(s, "p1") == 40
    check(s)


# -- Queen Kayla bin-Kroog -------------------------------------------------------------------------------------------------------------------
KAYLA = "Queen Kayla bin-Kroog"
test_kayla_full = full_test([KAYLA])


def kayla_table(cards):
    names = ["Llanowar Elves", "Mother of Runes", "Grizzly Bears", "Hill Giant", "Sol Ring", "Mind Stone"]
    s = build(cards, [KAYLA, *names], forests=20)
    kayla = put(s, KAYLA)
    ready(s, KAYLA)
    hand = [to_hand(s, n) for n in names]
    fund(s, "{4}")
    act(s, "p1", type="activate_ability", card_id=kayla.id, ability=0)
    return s, kayla, {c.name: c.id for c in hand}


def test_kayla_discards_the_hand_draws_that_many_and_returns_one_card_for_each_mana_value(cards):
    s, kayla, ids = kayla_table(cards)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and {o.id for o in d.options} == {ids[n] for n in ("Llanowar Elves", "Mother of Runes", "Grizzly Bears", "Sol Ring", "Mind Stone")}  # (not Hill Giant: mana value 4)
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[ids["Llanowar Elves"], ids["Mother of Runes"]])  # two with mana value 1
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[ids["Llanowar Elves"], ids["Grizzly Bears"]])
    answer(s)
    assert s.state.cards[ids["Llanowar Elves"]].zone == "p1:battlefield" and s.state.cards[ids["Grizzly Bears"]].zone == "p1:battlefield"
    assert all(s.state.cards[ids[n]].zone == "p1:graveyard" for n in ("Mother of Runes", "Hill Giant", "Sol Ring", "Mind Stone"))
    assert len(s.state.zones["p1:hand"]) == 6  # (drew as many as were discarded)
    check(s)


# -- Primal Adversary ------------------------------------------------------------------------------------------------------------------------
ADVERSARY = "Primal Adversary"
test_adversary_full = full_test([ADVERSARY])


@pytest.mark.parametrize("times", [0, 1, 2])
def test_primal_adversary_pays_n_times_for_n_counters_and_n_wolf_lands(cards, times):
    """603.12, 107.3f: the counters and the "up to that many" lands (chosen as the reflexive ability goes on the stack) follow the times paid."""
    s = build(cards, [ADVERSARY], forests=20)
    lands = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:3]  # (three different Forests)
    act(s, "p1", type="move", card_ids=[c.id for c in lands], to={"player": "p1", "zone": "battlefield"})
    mana(s, G=14)
    adv = cast(s, ADVERSARY, pay=False)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert "how many times" in d.prompt
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[f"x:{times}" if times else "decline"])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options if o.card_id in {x.id for x in lands}][:times]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids or [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[adv.id].counters.get("+1/+1", 0) == times
    wolves = [x for x in lands if "Creature" in ch(s, x).types]
    assert len(wolves) == times and all(ch(s, x).pt == (3, 3) and "Land" in ch(s, x).types and "haste" in ch(s, x).keywords and "Wolf" in ch(s, x).subtypes for x in wolves)
    check(s)
