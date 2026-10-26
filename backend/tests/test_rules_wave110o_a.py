"""Wave 110O: single-card wordings, real Oracle text (tests/fixtures/wave110o_cards.json). Every scenario checks the replay and a save and a load.

* 608.2c, 611.2a, 109.4: Evil's Thrall takes the creature until end of turn, or until the end of your next turn while you control a Villain of greater mana value.
* 205.3m, 613.1d: Oko's +2 gives a creature every creature type for good; his -6 emblem boosts the chosen type for the rest of the game (114.1).
* 119.7-8, 616.1: Reverse the Sands lets its caster hand the chosen players' life totals out again, one each (an exchange; a player who can't
  gain or lose life can't get a higher or lower one).
* 702.133a, 611.2a: Filigree Racer, paying {E}{E} as it attacks, gives an instant or sorcery card in the graveyard jump-start for the turn.
* 702.138a, 611.2a, 611.2c: The Grim Captain's Locker gives each creature card in the graveyard (as it resolves) "Escape—{3}{B}, Exile four other cards" for the turn.
* 701.24a, 608.2b: Serene Remembrance shuffles itself and up to three target cards from a single graveyard into their owners' libraries.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave53d_kit import table
from tests.wave110o_kit import (  # noqa: F401
    EXTRA,
    ability,
    activate,
    card_db,
    cast_on,
    ch,
    check,
    cost,
    full,
    grave_new,
    hand_new,
    life,
    mana,
    move,
    now,
    put,
    put_new,
    refused,
    settle,
    to_hand,
    to_phase,
)

REMEMBRANCE, THRALL, SANDS, RACER, LOCKER, OKO = "Serene Remembrance", "Evil's Thrall", "Reverse the Sands", "Filigree Racer", "The Grim Captain's Locker", "Oko, Lorwyn Liege // Oko, Shadowmoor Scion"


@pytest.mark.parametrize("name", [REMEMBRANCE, THRALL, SANDS, RACER, LOCKER, OKO])
def test_the_cards_are_full(name):
    assert full(name)


def remembrance(s, targets):
    c = to_hand(s, REMEMBRANCE)
    mana(s, "p1", G=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[t.id for t in targets], target_counts=[len(targets)])
    settle(s)
    return now(s, c)


@pytest.mark.parametrize("n", [0, 1, 3])
def test_serene_remembrance_shuffles_itself_and_up_to_three_targets_into_their_owner_library(cards, n):
    s = build(cards, [REMEMBRANCE])
    mine = [grave_new(s, "Forest") for _ in range(n)]
    lib = len(s.state.zones["p1:library"])
    spell = remembrance(s, mine)
    assert spell.zone == "p1:library" and len(s.state.zones["p1:library"]) == lib + n
    assert all(now(s, c).zone == "p1:library" for c in mine) and len(s.state.zones["p1:graveyard"]) == 0
    check(s)


def test_serene_remembrance_sends_a_graveyard_card_to_its_owner_not_the_caster(cards):
    s = build(cards, [REMEMBRANCE])
    theirs = grave_new(s, "Island", "p2")
    lib = len(s.state.zones["p2:library"])
    spell = remembrance(s, [theirs])
    assert spell.zone == "p1:library" and now(s, theirs).zone == "p2:library" and len(s.state.zones["p2:library"]) == lib + 1
    check(s)


def test_serene_remembrance_cant_target_cards_of_two_graveyards(cards):
    s = build(cards, [REMEMBRANCE])
    a, b = grave_new(s, "Forest"), grave_new(s, "Island", "p2")
    c = to_hand(s, REMEMBRANCE)
    mana(s, "p1", G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, targets=[a.id, b.id], target_counts=[2])
    check(s)


def thrall(s, villain):
    bears = put(s, "Grizzly Bears", "p2")
    if villain:
        put_new(s, villain)
    bears_now = now(s, bears)
    assert bears_now.controller == "p2"
    cast_on(s, THRALL, bears)
    return bears


@pytest.mark.parametrize(("villain", "next_turn_too"), [(None, False), ("Common Crook", False), ("Roxxon Brutes", True)])
def test_evil_thrall_lasts_until_the_end_of_your_next_turn_only_with_a_bigger_villain(cards, villain, next_turn_too):
    """A Villain of equal mana value (Common Crook 2, Grizzly Bears 2) is not "greater"."""
    s = build(cards, [THRALL, "Common Crook", "Roxxon Brutes"], ["Grizzly Bears"])
    bears = thrall(s, villain)
    c = now(s, bears)
    assert c.controller == "p1" and not c.tapped and "haste" in ch(s, bears).keywords
    to_phase(s, "main1", turn=2)
    assert now(s, bears).controller == ("p1" if next_turn_too else "p2")
    to_phase(s, "main2", turn=3)
    assert now(s, bears).controller == ("p1" if next_turn_too else "p2")
    to_phase(s, "main1", turn=4)
    assert now(s, bears).controller == "p2"
    check(s)



def test_evil_thrall_ignores_a_bigger_villain_an_opponent_controls(cards):
    s = build(cards, [THRALL], ["Grizzly Bears", "Roxxon Brutes"])
    put(s, "Roxxon Brutes", "p2")
    bears = thrall(s, None)
    to_phase(s, "main1", turn=2)
    assert now(s, bears).controller == "p2"
    check(s)


def oko(s, face=0, loyalty=3):
    c = put(s, OKO)
    if face:
        act(s, "p1", type="set_face", card_id=c.id, face=face)
    act(s, "p1", type="counter", card_ids=[c.id], kind="loyalty", delta=loyalty)
    return c


def loyalty_ability(s, c, start, resolve=True, **kw):
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, start), **kw)
    if resolve:
        settle(s)


@pytest.mark.parametrize("target", [True, False])
def test_oko_plus_two_gives_a_creature_every_creature_type_permanently(cards, target):
    s = build(cards, [OKO, "Grizzly Bears"])
    c = oko(s)
    bears = put(s, "Grizzly Bears")
    assert "Elf" not in ch(s, bears).subtypes
    loyalty_ability(s, c, "+2", targets=[bears.id] if target else [], target_counts=[1] if target else [0])
    assert ("Elf" in ch(s, bears).subtypes and "Bear" in ch(s, bears).subtypes) == target
    assert now(s, c).counters.get("loyalty") == 5
    to_phase(s, "main1", turn=3)  # (an effect that doesn't end)
    assert ("Elf" in ch(s, bears).subtypes) == target
    check(s)


def test_oko_minus_six_emblem_pumps_the_chosen_type_only(cards):
    s = build(cards, [OKO, "Grizzly Bears", "Llanowar Elves"])
    c = oko(s, face=1, loyalty=7)
    bears, elf = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    base = ch(s, elf).pt
    loyalty_ability(s, c, "−6", resolve=False)
    answer_pick(s, "Elf")
    assert now(s, c).counters.get("loyalty") == 1
    assert ch(s, bears).pt == (2, 2) and "vigilance" not in ch(s, bears).keywords
    assert ch(s, elf).pt == (int(base[0]) + 3, int(base[1]) + 3) and {"vigilance", "hexproof"} <= set(ch(s, elf).keywords)
    check(s)


def answer_pick(s, option):
    d = s.state.rules.decision
    assert d is not None and option in {o.id for o in d.options}
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])
    settle(s)


@pytest.mark.parametrize("kind", ["Time Lord", "C’tan", "Cyclops"])
def test_oko_minus_six_emblem_names_any_creature_type(cards, kind):
    s = build(cards, [OKO])
    c = oko(s, face=1, loyalty=6)
    loyalty_ability(s, c, "−6", resolve=False)
    answer_pick(s, kind)
    emblems = [x for x in s.state.cards.values() if x.zone == "p1:command" and x.token is not None]
    assert len(emblems) == 1 and emblems[0].token.text.startswith(kind)
    check(s)


def test_oko_plus_two_ends_when_the_creature_leaves_the_battlefield(cards):
    """400.7: a creature that leaves and comes back is a new object, so the effect is gone."""
    s = build(cards, [OKO, "Grizzly Bears"])
    c = oko(s)
    bears = put(s, "Grizzly Bears")
    loyalty_ability(s, c, "+2", targets=[bears.id], target_counts=[1])
    move(s, bears, "hand")
    put(s, "Grizzly Bears")
    assert "Elf" not in ch(s, bears).subtypes
    check(s)


def lives(s, **kw):
    for pid, n in kw.items():
        act(s, "p1", type="set_life", player=pid, value=n)


def sands(s, pick):
    """Cast Reverse the Sands (8 mana), choose the players ``pick`` (None: none)."""
    c = to_hand(s, SANDS)
    mana(s, "p1", C=6, W=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    # (the others pass; the first decision is Alice's)
    d = s.state.rules.decision
    while d is None:
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=list(pick))


def give(s, *gets):
    """Answer each "which life total" question in turn with the owner it came from."""
    for src in gets:
        d = s.state.rules.decision
        assert d is not None and d.player == "p1" and "life total does" in d.prompt, d and d.prompt
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[src])


@pytest.mark.parametrize("pick", [[], ["p2"], ["p1"]])
def test_reverse_the_sands_with_fewer_than_two_players_changes_nothing(cards, pick):
    s = build(cards, [SANDS])
    lives(s, p2=17)
    sands(s, pick)
    settle(s)
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (40, 17)
    check(s)


@pytest.mark.parametrize(("gets", "result"), [(["p2"], (17, 40)), (["p1"], (40, 17))])
def test_reverse_the_sands_two_players_swap_or_keep(cards, gets, result):
    s = build(cards, [SANDS])
    lives(s, p2=17)
    sands(s, ["p1", "p2"])
    give(s, *gets)  # (the second player gets the total left)
    settle(s)
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == result
    check(s)


def test_reverse_the_sands_three_players_in_a_cycle_and_a_bystander(cards):
    s = table(cards, [SANDS], [], [])
    lives(s, p1=10, p2=20, p3=30)
    sands(s, ["p1", "p2", "p3"])
    give(s, "p3", "p1")  # Alice gets Carol's 30, Bob gets Alice's 10, Carol the 20 left
    settle(s)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [30, 10, 20]
    check(s)


def test_reverse_the_sands_leaves_a_player_not_chosen_alone(cards):
    s = table(cards, [SANDS], [], [])
    lives(s, p1=10, p2=20, p3=30)
    sands(s, ["p1", "p3"])
    give(s, "p3")
    settle(s)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [30, 20, 10]
    check(s)


def test_reverse_the_sands_cant_give_a_player_who_cant_gain_life_a_higher_total(cards):
    """119.7: with Everlasting Torment out ("Players can't gain life"), Bob (17) can't get Alice's 40, so Alice can only keep hers."""
    s = build(cards, [SANDS, "Everlasting Torment"])
    put(s, "Everlasting Torment")
    lives(s, p2=17)
    sands(s, ["p1", "p2"])
    d = s.state.rules.decision
    assert d is None or [o.id for o in d.options] == ["p1"]
    settle(s)
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (40, 17)
    check(s)


def racer_attacks(s):
    """Filigree Racer (crewed by a Grizzly Bears) attacks Bob; the energy trigger waits on Alice's answer."""
    racer = put(s, RACER)
    act(s, "p1", type="resource", player="p1", key="energy", delta=4)  # (its own enters trigger is not what is tested)
    bears = put(s, "Grizzly Bears")
    for c in (racer, bears):
        s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=racer.id, ability=ability(s, racer, "Crew"), crew=[bears.id])
    settle(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": racer.id, "target": "p2"}])
    return racer


@pytest.mark.parametrize("pay", [True, False])
def test_filigree_racer_pay_energy_to_give_jump_start_for_the_turn(cards, pay):
    s = build(cards, [RACER, "Grizzly Bears", "Lightning Bolt", "Templar Knight"])
    bolt, spare = grave_new(s, "Lightning Bolt"), hand_new(s, "Templar Knight")
    racer_attacks(s)
    for _ in range(6):  # (the attack trigger resolves: pass priority round)
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1", (s.state.zones.get("stack"), s.state.rules.priority)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay" if pay else "decline"])
    settle(s, answers=[[bolt.id]] if pay else [])
    assert s.state.players["p1"].resources.get("energy", 0) == (2 if pay else 4)
    mana(s, "p1", R=1)
    if pay:
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
        settle(s)
        assert life(s, "p2") == 40 - 5 - 3 and now(s, bolt).zone == "p1:exile" and now(s, spare).zone == "p1:graveyard"  # (the discard, then exiled)
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    check(s)


def test_filigree_racer_jump_start_ends_with_the_turn(cards):
    s = build(cards, [RACER, "Grizzly Bears", "Lightning Bolt", "Templar Knight"])
    bolt = grave_new(s, "Lightning Bolt")
    hand_new(s, "Templar Knight")
    racer_attacks(s)
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, s.state.rules.decision.player, type="choose", decision_id=s.state.rules.decision.id, option_ids=["pay"])
    settle(s, answers=[[bolt.id]])
    to_phase(s, "main1", turn=3)
    mana(s, "p1", R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    check(s)


def locker(s, fillers=4):
    lock = put(s, LOCKER)
    bears, bolt = grave_new(s, "Grizzly Bears"), grave_new(s, "Lightning Bolt")
    for _ in range(fillers):
        grave_new(s, "Forest")
    return lock, bears, bolt


def escape_bears(s, bears):
    mana(s, "p1", C=3, B=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)


def test_grim_captains_locker_creature_cards_escape_by_exiling_four_others(cards):
    s = build(cards, [LOCKER, "Grizzly Bears", "Lightning Bolt"])
    lock, bears, bolt = locker(s, 3)  # (the Bolt and three Forests: four other cards)
    activate(s, lock, "{T}: Until end of turn")
    escape_bears(s, bears)
    assert now(s, bears).zone == "p1:battlefield" and sum(1 for c in s.state.cards.values() if c.zone == "p1:exile") == 4
    assert s.state.rules.payments[s.state.rules.object_id(bears.id)].alternative == "escape"
    check(s)


def test_grim_captains_locker_escape_needs_four_other_cards(cards):
    s = build(cards, [LOCKER, "Grizzly Bears", "Lightning Bolt"])
    lock, bears, bolt = locker(s, 2)
    activate(s, lock, "{T}: Until end of turn")
    with pytest.raises(ActionError):
        escape_bears(s, bears)
    check(s)


@pytest.mark.parametrize("what", ["noncreature", "later", "next turn", "no ability"])
def test_grim_captains_locker_grants_only_to_the_creature_cards_there_then_and_this_turn(cards, what):
    s = build(cards, [LOCKER, "Grizzly Bears", "Lightning Bolt", "Llanowar Elves"])
    lock, bears, bolt = locker(s, 3)
    if what != "no ability":
        activate(s, lock, "{T}: Until end of turn")
    target = bears
    if what == "noncreature":
        target = bolt
    if what == "later":
        target = grave_new(s, "Llanowar Elves")
    if what == "next turn":
        to_phase(s, "main1", turn=3)
    mana(s, "p1", C=3, B=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=target.id, **({"targets": ["p2"]} if target is bolt else {}))
    check(s)
