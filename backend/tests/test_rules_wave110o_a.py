"""Wave 110O: single-card wordings, real Oracle text (tests/fixtures/wave110o_cards.json). Every scenario checks the replay and a save and a load.

* 608.2c, 611.2a, 109.4: Evil's Thrall takes the creature until end of turn, or until the end of your next turn while you control a Villain of greater mana value.
* 205.3m, 613.1d: Oko's +2 gives a creature every creature type for good; his -6 emblem boosts the chosen type for the rest of the game (114.1).
* 119.7-8, 616.1: Reverse the Sands lets its caster hand the chosen players' life totals out again, one each (an exchange; a player who can't
  gain or lose life can't get a higher or lower one).
* 702.133a, 611.2a: Filigree Racer, paying {E}{E} as it attacks, gives an instant or sorcery card in the graveyard jump-start for the turn.
* 702.138a, 611.2a, 611.2c: The Grim Captain's Locker gives each creature card in the graveyard (as it resolves) "Escape—{3}{B}, Exile four other cards" for the turn.
* 701.17a, 608.2c: Helm of Obedience mills one card at a time until a creature card or X cards reached the graveyard, then a creature is stolen.
* 701.20a, 608.2c: Portent of Calamity exiles at most one card of each card type from among the top X, casts one free with four or more,
  and takes the rest of what it exiled.
* 607.2a, 406.3b: Scarlet Witch exiles two cards face down on each hit and may cast a Hero or noncreature spell from all the cards exiled with her.
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

REMEMBRANCE, THRALL, SANDS, RACER, LOCKER, HELM, PORTENT, WITCH, OKO = "Serene Remembrance", "Evil's Thrall", "Reverse the Sands", "Filigree Racer", "The Grim Captain's Locker", "Helm of Obedience", "Portent of Calamity", "Scarlet Witch, Chaotic Avenger", "Oko, Lorwyn Liege // Oko, Shadowmoor Scion"


@pytest.mark.parametrize("name", [REMEMBRANCE, THRALL, SANDS, RACER, LOCKER, HELM, PORTENT, WITCH, OKO])
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


def library_top(s, *names, pid="p2"):
    """Bob's library starts with ``names`` (in order); the rest is his Islands."""
    used: set[str] = set()
    picks = []
    for name in names:
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.id not in used)
        used.add(c.id)
        picks.append(c)
    for c in reversed(picks):
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "library"}, position="top")


def helm(s, x):
    h = put(s, HELM)
    mana(s, "p1", C=x)
    act(s, "p1", type="activate_ability", card_id=h.id, ability=ability(s, h, "{X}"), x_value=x, targets=["p2"])
    settle(s)
    return h


@pytest.mark.parametrize(("top", "x", "milled", "stolen"), [
    (["Island", "Island", "Island", "Grizzly Bears"], 3, 3, False),   # X cards, the creature is the 4th: stays in the library
    (["Island", "Grizzly Bears", "Island"], 5, 2, True),             # a creature card ends it
    (["Grizzly Bears", "Island"], 2, 1, True),
    (["Island", "Island"], 1, 1, False),
])
def test_helm_of_obedience_mills_until_a_creature_or_x_cards(cards, top, x, milled, stolen):
    s = build(cards, [HELM], ["Grizzly Bears"])
    library_top(s, *top)
    lib = len(s.state.zones["p2:library"])
    h = helm(s, x)
    assert len(s.state.zones["p2:library"]) == lib - milled
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2")
    assert (now(s, bears).zone, now(s, bears).controller) == (("p1:battlefield", "p1") if stolen else (now(s, bears).zone, "p2"))
    assert (now(s, h).zone == "p1:graveyard") == stolen
    assert len(s.state.zones["p2:graveyard"]) == milled - (1 if stolen else 0)
    check(s)


def test_helm_of_obedience_x_cant_be_zero(cards):
    s = build(cards, [HELM], ["Grizzly Bears"])
    h = put(s, HELM)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=h.id, ability=ability(s, h, "{X}"), x_value=0, targets=["p2"])


def test_helm_of_obedience_stops_when_the_library_runs_out(cards):
    s = build(cards, [HELM], [])
    for cid in list(s.state.zones["p2:library"])[1:]:
        act(s, "p2", type="move", card_ids=[cid], to={"zone": "exile"})
    helm(s, 4)
    assert len(s.state.zones["p2:library"]) == 0 and len(s.state.zones["p2:graveyard"]) == 1
    check(s)


TOP5 = ["Forest", "Grizzly Bears", "Lightning Bolt", "Sol Ring", "Frogmite"]


def portent(s, x=5, top=TOP5):
    """Cast Portent of Calamity for X, the top of Alice's library as given; the pick decision is left open."""
    c = to_hand(s, PORTENT)
    library_top(s, *top, pid="p1")
    mana(s, "p1", C=x, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=x)
    for _ in range(4):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return c


def pick(s, *names):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    ids = [next(o.id for o in d.options if o.label == n) for n in names]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


@pytest.mark.parametrize(("exiled", "cast"), [
    (["Forest", "Grizzly Bears", "Lightning Bolt", "Sol Ring"], "Grizzly Bears"),   # four: a free cast from them
    (["Forest", "Grizzly Bears", "Lightning Bolt", "Sol Ring"], None),               # four, but the cast is declined
    (["Forest", "Grizzly Bears", "Lightning Bolt"], None),                           # three: no cast offered
    ([], None),
])
def test_portent_of_calamity_exiles_a_card_of_each_type_casts_one_free_with_four_and_takes_the_rest(cards, exiled, cast):
    s = build(cards, [PORTENT, *TOP5[1:]])
    portent(s)
    pick(s, *exiled)
    d = s.state.rules.decision
    if len(exiled) >= 4:
        assert d is not None and d.player == "p1"
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == cast)] if cast else [])
    settle(s)
    assert s.state.rules.decision is None
    for name in TOP5:
        z = now(s, named(s, name)).zone
        if name in exiled and name == cast:
            assert z == "p1:battlefield", (name, z)
        elif name in exiled:
            assert z == "p1:hand", (name, z)
        else:
            assert z == "p1:graveyard", (name, z)
    check(s)


def test_portent_of_calamity_cant_exile_two_cards_for_one_type_and_a_card_stands_for_one_type(cards):
    s = build(cards, [PORTENT, *TOP5[1:]])
    portent(s)
    d = s.state.rules.decision
    ids = {o.label: o.id for o in d.options}
    with pytest.raises(ActionError):  # Grizzly Bears and Frogmite (an artifact creature) are creature and creature/artifact: with Sol Ring only two types fit three cards
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[ids["Grizzly Bears"], ids["Frogmite"], ids["Sol Ring"]])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[ids["Grizzly Bears"], ids["Frogmite"]])  # creature + artifact: fine
    settle(s)
    assert now(s, named(s, "Frogmite")).zone == "p1:hand" and now(s, named(s, "Sol Ring")).zone == "p1:graveyard"
    check(s)


def witch_hits(s, witch, turn=1):
    """Scarlet Witch attacks Bob (flying, nobody blocks) and the damage trigger goes on the stack and resolves up to its first question."""
    s.state.rules.controlled_since[witch.id].turn = 0
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": witch.id, "target": "p2"}])
    for _ in range(12):
        if s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_cards":
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no question")


def test_scarlet_witch_casts_a_noncreature_spell_free_from_what_she_exiled_and_keeps_the_rest(cards):
    s = build(cards, [WITCH, "Lightning Bolt", "Grizzly Bears"])
    witch = put(s, WITCH)
    library_top(s, "Grizzly Bears", "Lightning Bolt", pid="p1")
    witch_hits(s, witch)
    d = s.state.rules.decision
    assert [o.label for o in d.options] == ["Lightning Bolt"]  # (the Bears is no Hero and no noncreature spell)
    bolt, bears = named(s, "Lightning Bolt"), named(s, "Grizzly Bears")
    assert now(s, bears).face_down and now(s, bears).zone == "p1:exile"
    from app.game.visibility import can_see

    assert can_see(s.state, now(s, bears), "p1") and not can_see(s.state, now(s, bears), "p2")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bolt.id])
    settle(s, answers=[["p2"]])
    assert life(s, "p2") == 40 - 3 - 3 and now(s, bolt).zone == "p1:graveyard" and now(s, bears).zone == "p1:exile"
    check(s)


def test_scarlet_witch_can_cast_a_card_exiled_by_an_earlier_hit(cards):
    s = build(cards, [WITCH, "Lightning Bolt", "Grizzly Bears"])
    witch = put(s, WITCH)
    library_top(s, "Lightning Bolt", "Grizzly Bears", pid="p1")
    witch_hits(s, witch)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[])  # (declines: the Bolt stays exiled)
    settle(s)
    bolt = named(s, "Lightning Bolt")
    assert now(s, bolt).zone == "p1:exile"
    to_phase(s, "main1", turn=3)
    library_top(s, "Forest", "Forest", pid="p1")
    witch_hits(s, witch, turn=3)
    assert [o.label for o in s.state.rules.decision.options] == ["Lightning Bolt"]
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[bolt.id])
    settle(s, answers=[["p2"]])
    assert now(s, bolt).zone == "p1:graveyard"
    check(s)
