"""Wave 110M: instants and sorceries whose last unread sentence is now read. Every scenario checks the replay and a save and a load.

* 614.1a, 614.5, 104.3b: "The next time you would lose the game this turn, instead draw seven cards and your life total becomes 1. Exile Stunning Reversal."
  (Stunning Reversal): a one-shot replacement for this turn; the second loss, or one on a later turn, is not replaced.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110m_kit import *

REVERSAL = "Stunning Reversal"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([REVERSAL])


def reversal_table(cards):
    s = build(cards, [REVERSAL, "Lightning Bolt"], forests=20)
    act(s, "p1", type="set_life", player="p1", value=3)
    cast(s, REVERSAL)
    answer(s)
    return s


def test_stunning_reversal_replaces_the_next_loss_with_seven_cards_and_one_life(cards):
    s = reversal_table(cards)
    assert zone_of(s, REVERSAL) == "p1:exile" and life(s) == 3
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Lightning Bolt", ["p1"])
    answer(s)
    assert s.state.rules.winner is None and life(s) == 1 and len(s.state.zones["p1:hand"]) == hand + 7
    check(s)


def test_stunning_reversal_replaces_only_the_next_loss_this_turn(cards):
    s = reversal_table(cards)
    cast(s, "Lightning Bolt", ["p1"])
    answer(s)
    assert life(s) == 1
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")  # (704.3: the state-based actions are checked before a player would receive priority)
    answer(s)
    assert s.state.rules.winner == "p2"
    check(s)


def test_stunning_reversal_ends_with_the_turn(cards):
    s = reversal_table(cards)
    to_phase(s, "main1", turn=s.state.turn.number + 2)
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")
    answer(s)
    assert s.state.rules.winner == "p2"
    check(s)


# -- Choice of Damnations ------------------------------------------------------------------------------------------------------------------
DAMN = "Choice of Damnations"
test_damnations_full = full_test([DAMN])


def type_number(s, n):
    """Pass priority until a typed-number decision is asked, and answer it."""
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.options[0].group == "number"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[], name=str(n))


def damnations_table(cards):
    s = build(cards, [DAMN], ["Grizzly Bears", "Llanowar Elves", "Elite Vanguard"], forests=20)
    for n in ("Grizzly Bears", "Llanowar Elves", "Elite Vanguard"):
        put(s, n, "p2")
    return s


def theirs(s):
    return sorted(s.state.cards[c].name for c in s.state.zones["p2:battlefield"])


@pytest.mark.parametrize("number,controller,life_after,kept", [
    (5, "yes", 35, 3),         # lose that much life
    (0, "yes", 40, 3),         # losing 0 life
    (1, "no", 40, 1),          # sacrifice all but one: they keep one of their choice
    (0, "no", 40, 0),          # all of them
    (3, "no", 40, 3),          # exactly as many as they have: none is sacrificed
    (9, "no", 40, 3),          # more than they have
])
def test_choice_of_damnations_lose_life_or_sacrifice_all_but_the_chosen_number(cards, number, controller, life_after, kept):
    s = damnations_table(cards)
    cast(s, DAMN, ["p2"])
    type_number(s, number)
    picks = [controller]
    if controller == "no" and 0 < number < 3:
        picks.append([card_named(s, "Llanowar Elves", "p2").id])
    answer(s, *picks)
    assert life(s, "p2") == life_after and len(theirs(s)) == kept
    if kept == 1:
        assert theirs(s) == ["Llanowar Elves"]  # (the permanent the player kept)
    check(s)


# -- Kaervek's Spite -----------------------------------------------------------------------------------------------------------------------
SPITE = "Kaervek's Spite"
test_spite_full = full_test([SPITE])


@pytest.mark.parametrize("hand_cards", [("Grizzly Bears", "Llanowar Elves"), ()])
def test_kaervek_spite_sacrifices_every_permanent_and_discards_the_hand_as_a_cost(cards, hand_cards):
    """601.2b, 118.3: both parts of the additional cost are paid as it is cast (the spell is already on the stack, so it isn't in the hand it discards)."""
    s = build(cards, [SPITE, "Grizzly Bears", "Llanowar Elves", "Elite Vanguard"], forests=20)
    board = [put(s, "Elite Vanguard"), put(s, "Forest")]
    hand = [to_hand(s, n) for n in hand_cards]
    cast(s, SPITE, ["p2"])
    assert all(zone_of(s, "Elite Vanguard") == "p1:graveyard" for _ in board[:1]) and board[1].id not in s.state.zones["p1:battlefield"]
    assert all(c.id in s.state.zones["p1:graveyard"] for c in hand) and not s.state.zones["p1:hand"]
    answer(s)
    assert life(s, "p2") == 35 and zone_of(s, SPITE) == "p1:graveyard"
    check(s)


# -- Rhino's Rampage -------------------------------------------------------------------------------------------------------------------------
RAMPAGE = "Rhino's Rampage"
test_rampage_full = full_test([RAMPAGE])


def rampage_table(cards, victim):
    s = build(cards, [RAMPAGE, "Grizzly Bears"], [victim, "Sol Ring", "Gilded Lotus", "Ornithopter"], forests=20)
    bears = put(s, "Grizzly Bears")
    for n in (victim, "Sol Ring", "Gilded Lotus", "Ornithopter"):
        put(s, n, "p2")
    return s, bears


@pytest.mark.parametrize("victim,excess", [("Llanowar Elves", True), ("Hill Giant", False)])
def test_rhino_rampage_destroys_an_artifact_only_when_excess_damage_was_dealt(cards, victim, excess):
    """Bears get +1/+0 (3 power): a 1/1 takes 2 excess damage, a 3/3 exactly lethal damage (120.10). The artifact is chosen as the reflexive ability goes on the stack."""
    s, bears = rampage_table(cards, victim)
    c = to_hand(s, RAMPAGE)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id, card_named(s, victim, "p2").id], target_counts=[1, 1])
    if excess:
        d = None
        for _ in range(20):
            d = s.state.rules.decision
            if d is not None:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert d is not None and {o.label for o in d.options} >= {"Sol Ring"} and not {o.label for o in d.options} & {"Gilded Lotus", "Ornithopter"}
        sol = card_named(s, "Sol Ring", "p2")
        answer(s, [sol.id])
        assert zone_of(s, "Sol Ring", "p2") == "p2:graveyard"
    else:
        answer(s)
        assert zone_of(s, "Sol Ring", "p2") == "p2:battlefield"
    assert zone_of(s, victim, "p2") == "p2:graveyard"
    assert zone_of(s, "Gilded Lotus", "p2") == "p2:battlefield" and zone_of(s, "Ornithopter", "p2") == "p2:battlefield"
    check(s)


# -- Brilliance Unleashed --------------------------------------------------------------------------------------------------------------------
BRILLIANCE = "Brilliance Unleashed"
test_brilliance_full = full_test([BRILLIANCE])


def brilliance_table(cards):
    s = build(cards, [BRILLIANCE, "Sol Ring", "Ornithopter"], ["Hill Giant"], forests=20)
    for n in ("Sol Ring", "Ornithopter"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    return s, put(s, "Hill Giant", "p2")


@pytest.mark.parametrize("modes,artifact", [([0], None), ([1], "Sol Ring"), ([1], "Ornithopter"), ([0, 1], "Sol Ring")])
def test_brilliance_unleashed_damage_and_or_return_an_artifact_as_a_robot(cards, modes, artifact):
    """Choose one or both: 5 damage to a creature; and/or an artifact card returns, becoming a 3/3 Robot artifact creature with flying unless it already is a creature card."""
    s, giant = brilliance_table(cards)
    targets = ([giant.id] if 0 in modes else []) + ([card_named(s, artifact).id] if artifact else [])
    cast(s, BRILLIANCE, targets, modes=modes, **({"target_counts": [1, 1]} if len(modes) == 2 else {}))
    answer(s)
    assert (zone_of(s, "Hill Giant", "p2") == "p2:graveyard") is (0 in modes)
    if artifact is None:
        assert zone_of(s, "Sol Ring") == "p1:graveyard"
    else:
        back = card_named(s, artifact)
        assert back.zone == "p1:battlefield"
        got = ch(s, back)
        assert (got.pt, "flying" in got.keywords, "Robot" in got.subtypes) == (((3, 3), True, True) if artifact == "Sol Ring" else ((0, 2), True, False))
    check(s)


# -- Deadly Cover-Up -------------------------------------------------------------------------------------------------------------------------
COVER = "Deadly Cover-Up"
test_cover_full = full_test([COVER])


def cover_table(cards, theirs_in_graveyard=True):
    s = build(cards, [COVER, "Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Elite Vanguard"], ["Llanowar Elves", "Llanowar Elves", "Llanowar Elves"], forests=20)
    mine = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    for c in mine:  # three mana value 2 cards: collect evidence 6
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    elves = [c for c in s.state.cards.values() if c.name == "Llanowar Elves" and c.owner == "p2"]
    if theirs_in_graveyard:
        act(s, "p2", type="move", card_ids=[elves[0].id], to={"zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[elves[1].id], to={"zone": "hand"})  # (the third stays in the library)
    put(s, "Elite Vanguard")  # (the creature that Cover-Up destroys: into its owner's graveyard, not an opponent's)
    return s, mine, elves


def cover_up(s, collect):
    c = to_hand(s, COVER)
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, **({"optional_costs": [f"{c.id}:evidence"]} if collect else {}))
    for _ in range(40):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            return
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:  # the evidence, then the search: take every match
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.max_choices or 1)])


def test_deadly_cover_up_with_evidence_exiles_a_graveyard_card_and_every_copy_the_owner_has(cards):
    s, mine, elves = cover_table(cards)
    hand_before = len(s.state.zones["p2:hand"])
    cover_up(s, collect=True)
    assert zone_of(s, "Elite Vanguard") == "p1:graveyard"  # (destroy all creatures)
    assert all(s.state.cards[e.id].zone == "p2:exile" for e in elves)  # the graveyard card, then the copies in hand and library
    assert len(s.state.zones["p2:hand"]) == hand_before - 1 + 1  # (the hand copy exiled, one card drawn for it)
    assert all(s.state.cards[c.id].zone == "p1:exile" for c in mine)
    check(s)


def test_deadly_cover_up_without_evidence_only_destroys_creatures(cards):
    s, mine, elves = cover_table(cards)
    cover_up(s, collect=False)
    assert zone_of(s, "Elite Vanguard") == "p1:graveyard"
    assert [s.state.cards[e.id].zone for e in elves] == ["p2:graveyard", "p2:hand", "p2:library"]
    check(s)


def test_deadly_cover_up_with_evidence_but_no_card_in_an_opponents_graveyard_exiles_nothing(cards):
    s, mine, elves = cover_table(cards, theirs_in_graveyard=False)
    cover_up(s, collect=True)
    assert all(s.state.cards[e.id].zone != "p2:exile" for e in elves) and zone_of(s, "Elite Vanguard") == "p1:graveyard"
    check(s)


# -- Hunted by The Family --------------------------------------------------------------------------------------------------------------------
HUNTED = "Hunted by The Family"
test_hunted_full = full_test([HUNTED])


@pytest.mark.parametrize("birds_choice,elves_choice", [("a", "b"), ("b", "a"), ("a", "a"), ("b", "b")])
def test_hunted_by_the_family_each_controller_picks_a_villainous_option_for_each_target(cards, birds_choice, elves_choice):
    s = build(cards, [HUNTED], ["Birds of Paradise", "Llanowar Elves", "Grizzly Bears"], forests=20)
    birds, elves, bears = (put(s, n, "p2") for n in ("Birds of Paradise", "Llanowar Elves", "Grizzly Bears"))
    cast(s, HUNTED, [birds.id, elves.id], target_counts=[2])
    d = None
    for choice in (birds_choice, elves_choice):
        for _ in range(20):
            d = s.state.rules.decision
            if d is not None:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert d is not None and d.player == "p2" and [o.id for o in d.options] == ["a", "b"]
        act(s, "p2", type="choose", decision_id=d.id, option_ids=[choice])
        d = None
    answer(s)
    for card, choice, subtypes in ((birds, birds_choice, {"Bird"}), (elves, elves_choice, {"Elf", "Druid"})):
        got = ch(s, card)
        if choice == "a":
            assert (got.pt, set(got.types), set(got.subtypes), set(got.colors), "flying" in got.keywords) == ((1, 1), {"Creature"}, {"Human"}, {"W"}, False)
        else:
            assert set(got.subtypes) == subtypes and (card is not birds or "flying" in got.keywords)  # (left as it was)
    copies = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.token is not None]
    assert sorted(c.name for c in copies) == sorted(n for n, choice in (("Birds of Paradise", birds_choice), ("Llanowar Elves", elves_choice)) if choice == "b")
    assert pt(s, "Grizzly Bears", "p2") == (2, 2)  # (not targeted)
    check(s)


def test_kaervek_spite_can_be_paid_with_mana_from_lands_it_then_sacrifices(cards):
    """601.2g-h: mana abilities are activated before the costs are paid, so the lands tapped for the spell's mana can be sacrificed to it; the automatic payment
    never taps a land the cost takes, so the player taps them first."""
    from app.game.errors import ActionError
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(1, SPITE), (10, "Swamp")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    swamps = [c for c in s.state.cards.values() if c.name == "Swamp" and c.owner == "p1" and c.zone == "p1:library"][:3]
    act(s, "p1", type="move", card_ids=[c.id for c in swamps], to={"player": "p1", "zone": "battlefield"})
    spite = to_hand(s, SPITE)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spite.id, targets=["p2"])  # (every Swamp would be sacrificed: none left to pay with)
    for c in swamps:
        act(s, "p1", type="activate_ability", card_id=c.id, ability=0)
    act(s, "p1", type="cast_spell", card_id=spite.id, targets=["p2"])
    answer(s)
    assert all(s.state.cards[c.id].zone == "p1:graveyard" for c in swamps) and life(s, "p2") == 35
    check(s)


# -- Teferi Akosa of Zhalfir's −3 (a stand-in planeswalker with that one ability: the card itself is the back face of a Siege) -------------------
TEFERI = "Test Teferi 110M"


def next_decision(s):
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")


def teferi_table(cards):
    from tests.test_rules_wave36a_trigger_words import loyal

    s = build(cards, [TEFERI, "Grizzly Bears", "Llanowar Elves"], ["Sol Ring", "Mind Stone", "Gilded Lotus", "Grizzly Bears"], forests=20)
    walker = loyal(s, TEFERI, loyalty=5)
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    for n in ("Sol Ring", "Mind Stone", "Gilded Lotus"):
        put(s, n, "p2")
    return s, walker, bears, elves


@pytest.mark.parametrize("tapped,hit", [(2, "Mind Stone"), (1, "Sol Ring")])
def test_teferi_minus_three_shuffles_a_permanent_with_mana_value_up_to_the_creatures_tapped(cards, tapped, hit):
    s, walker, bears, elves = teferi_table(cards)
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=0)
    act(s, "p1", type="choose", decision_id=next_decision(s).id, option_ids=[bears.id, elves.id][:tapped])
    d = next_decision(s)
    labels = {o.label for o in d.options}
    assert "Gilded Lotus" not in labels and "Forest" not in labels and (("Mind Stone" in labels) is (tapped == 2)) and "Sol Ring" in labels
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == hit)])
    answer(s)
    assert card_named(s, hit, "p2").zone == "p2:library" and zone_of(s, "Gilded Lotus", "p2") == "p2:battlefield"
    check(s)


def test_teferi_minus_three_with_no_creature_tapped_does_nothing_more(cards):
    s, walker, bears, elves = teferi_table(cards)
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=0)
    act(s, "p1", type="choose", decision_id=next_decision(s).id, option_ids=[])
    answer(s)
    assert all(zone_of(s, n, "p2") == "p2:battlefield" for n in ("Sol Ring", "Mind Stone", "Gilded Lotus"))
    check(s)


# -- March from Velis Vel --------------------------------------------------------------------------------------------------------------------
MARCH = "March from Velis Vel"
test_march_full = full_test([MARCH])


def test_march_from_velis_vel_turns_every_land_of_the_chosen_type_into_a_hasty_copy_until_end_of_turn(cards):
    s = build(cards, [MARCH, "Grizzly Bears", "Desert", "Desert"], forests=20)
    bears = put(s, "Grizzly Bears")
    deserts = [c for c in s.state.cards.values() if c.name == "Desert" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[c.id for c in deserts], to={"player": "p1", "zone": "battlefield"})
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    cast(s, MARCH, [bears.id])
    d = next_decision(s)
    assert "Desert" in {o.id for o in d.options} and "Forest" not in {o.id for o in d.options} and "Urza’s" not in {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Desert"])
    answer(s)
    for c in deserts:
        got = ch(s, s.state.cards[c.id])
        assert (got.name, got.pt, "Creature" in got.types, "Land" in got.types, "haste" in got.keywords) == ("Grizzly Bears", (2, 2), True, False, True)
    assert "Land" in ch(s, s.state.cards[forest.id]).types and "Creature" not in ch(s, s.state.cards[forest.id]).types
    check(s)
    next_turn(s)
    assert all("Land" in ch(s, s.state.cards[c.id]).types and ch(s, s.state.cards[c.id]).name == "Desert" for c in deserts)  # (until end of turn)
