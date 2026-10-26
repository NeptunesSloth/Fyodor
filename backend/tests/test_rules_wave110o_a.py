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
* 700.4, 603.10a, 603.2h: Rinoa returns one of the attacking creatures that died together, tapped with a flying counter; only once each turn.
* 603.4, 113.6k: Syrix, Carrier of the Flame fires at each end step if a creature card left its owner's graveyard, and may be cast from the graveyard when another Phoenix dies.
* 608.2d, 707.9: Lazav, Familiar Stranger grows when its controller commits a crime, may exile any graveyard card, and may copy a creature card so exiled.
* 404.1, 601.3, 614.1a: Bösium Strip lets its controller cast an instant or sorcery card only from the top of their graveyard, and exiles it afterwards.
* 115.1, 608.2d: Cuombajj Witches / Magus of the Arena: the second target is chosen by an opponent (the activator's choice of which), announced before the costs.
* 702.24a, 705.2, 115.1: Karplusan Minotaur flips a coin per age counter; a lost flip lets an opponent (the controller's choice) pick the 1 damage's target.
* 603.2h, 506.1, 500.8: Desert Were-Worm untaps its attackers and adds a combat phase the first time each turn it attacks with total power 12 or more.
* 905.2b: Spire Phantasm's "if you guessed correctly" can never hold in a game that had no draft: entering draws nothing.
* 702.43a: Zabaz, the Glimmerwasp adds one to the +1/+1 counters a modular triggered ability puts on a creature its controller controls, and to nothing else.
* 722.3, 722.3d, 707.10: Codie prepares every creature it can, and copies each prepared spell (one cast from the exiled prepare copy) as it is cast.
* 604.3a(5), 613.4b, 611.2b: Gaea's Liege's power and toughness (Forests you control, or defending player's while it attacks) are no characteristic-defining
  ability; its tap ability turns a land into a Forest for as long as it stays on the battlefield.
* 506.3, 509.1b: Become the Pilot's creature can be blocked only while it attacks its owner (or a planeswalker / battle its owner controls).
* 702.110b, 608.2h: Profaner of the Dead bounces the opponents' creatures with toughness below the exploited creature's (as it last existed).
* 701.24a, 608.2b: Serene Remembrance shuffles itself and up to three target cards from a single graveyard into their owners' libraries.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import build
from tests.wave53d_kit import table
from tests.wave110b_kit import attack
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

REMEMBRANCE, THRALL, SANDS, RACER, LOCKER, HELM, PORTENT, WITCH, RINOA, SYRIX, LAZAV, STRIP, WITCHES, MAGUS, MINOTAUR, WORM, PHANTASM, ZABAZ, CODIE, LIEGE, PILOT, PROFANER, OKO = "Serene Remembrance", "Evil's Thrall", "Reverse the Sands", "Filigree Racer", "The Grim Captain's Locker", "Helm of Obedience", "Portent of Calamity", "Scarlet Witch, Chaotic Avenger", "Rinoa, Angel Wing", "Syrix, Carrier of the Flame", "Lazav, Familiar Stranger", "Bösium Strip", "Cuombajj Witches", "Magus of the Arena", "Karplusan Minotaur", "Desert Were-Worm", "Spire Phantasm", "Zabaz, the Glimmerwasp", "Codie, Ravenous Codex", "Gaea's Liege", "Become the Pilot", "Profaner of the Dead", "Oko, Lorwyn Liege // Oko, Shadowmoor Scion"


@pytest.mark.parametrize("name", [REMEMBRANCE, THRALL, SANDS, RACER, LOCKER, HELM, PORTENT, WITCH, RINOA, SYRIX, LAZAV, STRIP, WITCHES, MAGUS, MINOTAUR, WORM, PHANTASM, ZABAZ, CODIE, LIEGE, PILOT, PROFANER, OKO])
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


def combat(s, blocks, pick=None, yes=True):
    """Play through combat; Bob declares ``blocks`` ((blocker, attacker) pairs); Rinoa's "may" is answered ``yes``, the creature chosen is ``pick``."""
    seen = []
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in blocks])
        elif d is not None:
            seen.append(d.prompt)
            if "creature to return" in d.prompt:
                ids = [next(o.id for o in d.options if o.card_id == pick.id)]
            else:
                ids = [next(o.id for o in d.options if (o.id == "yes") == yes or yes is None)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return seen
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def rinoa_table(cards, mine, theirs):
    s = build(cards, [RINOA, *mine], theirs)
    put(s, RINOA)
    return s


@pytest.mark.parametrize("yes", [True, False])
def test_rinoa_returns_the_attacking_creature_that_died_tapped_with_a_flying_counter(cards, yes):
    s = rinoa_table(cards, ["Grizzly Bears"], ["Grizzly Bears"])
    bears, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    attack(s, bears)
    combat(s, [(theirs, bears)], yes=yes)
    c = now(s, bears)
    if yes:
        assert c.zone == "p1:battlefield" and c.tapped and c.counters.get("flying") == 1 and "flying" in ch(s, bears).keywords
    else:
        assert c.zone == "p1:graveyard"
    check(s)


def test_rinoa_picks_one_of_the_attackers_that_died_together(cards):
    s = rinoa_table(cards, ["Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears", "Benalish Hero"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    b1, b2 = put(s, "Grizzly Bears", "p2"), put(s, "Benalish Hero", "p2")
    attack(s, bears, elves)
    seen = combat(s, [(b1, bears), (b2, elves)], pick=elves)
    assert "110o" not in seen[0]  # (the question reads as words, not as a primitive's name)
    assert any("creature to return" in p for p in seen)
    assert now(s, elves).zone == "p1:battlefield" and now(s, bears).zone == "p1:graveyard"
    check(s)


def test_rinoa_ignores_a_creature_that_was_not_attacking(cards):
    s = rinoa_table(cards, ["Grizzly Bears", "Lightning Bolt"], [])
    bears = put(s, "Grizzly Bears")
    cast_on(s, "Lightning Bolt", bears)
    assert now(s, bears).zone == "p1:graveyard" and not s.state.zones.get("stack") and s.state.rules.decision is None
    check(s)


def test_rinoa_returns_only_once_each_turn(cards):
    """603.2h: the first death (a Bolt on an attacker after blockers) returned one; the next one the same turn does not trigger."""
    s = rinoa_table(cards, ["Grizzly Bears", "Llanowar Elves", "Lightning Bolt"], ["Grizzly Bears"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    b1 = put(s, "Grizzly Bears", "p2")
    stops(s)
    for c in (bears, elves):
        s.state.rules.controlled_since[c.id].turn = 0
    for want in ("declare_attackers", "declare_blockers"):
        while s.state.rules.decision is None or s.state.rules.decision.kind != want:
            act(s, s.state.rules.priority, type="pass_priority")
        if want == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (bears, elves)])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b1.id, "attacker_id": bears.id}])
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[elves.id])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert now(s, elves).zone == "p1:battlefield" and now(s, elves).counters.get("flying") == 1
    seen = combat(s, [])
    assert not seen and now(s, bears).zone == "p1:graveyard"  # (Bears died in combat: no second return, no question)
    check(s)


def end_step(s, target="p2"):
    """Play to Alice's end step, answering a target question with ``target`` (a player or a card id)."""
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            ids = [target] if any(o.id == target for o in d.options) else [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.turn.phase == "end" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached the end step")


@pytest.mark.parametrize(("returned", "hits"), [("Grizzly Bears", True), ("Lightning Bolt", False), (None, False)])
def test_syrix_hits_at_the_end_step_only_if_a_creature_card_left_the_graveyard(cards, returned, hits):
    s = build(cards, [SYRIX, "Raise Dead", "Regrowth", "Grizzly Bears", "Lightning Bolt"])
    put(s, SYRIX)
    stops(s)
    if returned:
        grave_new(s, returned)
        cast_on(s, "Raise Dead" if returned == "Grizzly Bears" else "Regrowth", named(s, returned))
    end_step(s)
    assert life(s, "p2") == (37 if hits else 40)
    check(s)


def test_syrix_trigger_ignores_a_creature_card_that_left_someone_elses_graveyard(cards):
    s = build(cards, [SYRIX, "Regrowth"], ["Grizzly Bears"])
    put(s, SYRIX)
    stops(s)
    grave_new(s, "Grizzly Bears", "p2")
    move(s, named(s, "Grizzly Bears", "p2"), "exile", "p2")
    end_step(s)
    assert life(s, "p2") == 40
    check(s)


def disfigure(s, victim):
    """Cast Disfigure on ``victim`` and pass until the first question (or the stack is empty)."""
    c = to_hand(s, "Disfigure")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[victim.id])
    for _ in range(10):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")


@pytest.mark.parametrize(("phoenix_dies", "cast"), [(True, True), (True, False), (False, False)])
def test_syrix_may_be_cast_from_the_graveyard_when_another_phoenix_you_control_dies(cards, phoenix_dies, cast):
    s = build(cards, [SYRIX, "Phoenix Chick", "Disfigure", "Grizzly Bears"])
    syrix = grave_new(s, SYRIX)
    chick, bears = put(s, "Phoenix Chick"), put(s, "Grizzly Bears")
    stops(s)
    mana(s, "p1", C=4, R=2, B=2)  # (the Disfigure takes {B}; Syrix costs {2}{B}{R})
    disfigure(s, chick if phoenix_dies else bears)
    d = s.state.rules.decision
    if phoenix_dies:
        assert d is not None and d.player == "p1"
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == syrix.id)] if cast else [])
        settle(s)
    else:
        assert d is None
    assert now(s, syrix).zone == ("p1:battlefield" if cast else "p1:graveyard")
    check(s)


def crime(s, pick=None, copy=None, bolts=1):
    """Alice casts Lightning Bolt at Bob (targeting an opponent: a crime); Lazav's trigger asks for the card to exile (``pick``) and the copy (``copy``)."""
    asked = []
    for _ in range(bolts):
        bolt = to_hand(s, "Lightning Bolt")
        mana(s, "p1", R=1)
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
        for _ in range(12):
            d = s.state.rules.decision
            if d is None and not s.state.zones.get("stack"):
                break
            if d is None:
                act(s, s.state.rules.priority, type="pass_priority")
            elif "exile a card" in d.prompt:
                asked.append("exile")
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == pick.id)] if pick else [])
            else:
                asked.append("copy")
                act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if copy else "no"])
    return asked


@pytest.mark.parametrize(("pick", "copy", "name", "pt"), [
    ("Grizzly Bears", True, "Grizzly Bears", (3, 3)),            # a copy of the Bears with the new counter
    ("Grizzly Bears", False, "Lazav, Familiar Stranger", (2, 5)),
    ("Disfigure", None, "Lazav, Familiar Stranger", (2, 5)),     # not a creature card: no copy question
    (None, None, "Lazav, Familiar Stranger", (2, 5)),            # no exile
])
def test_lazav_crime_counter_exile_and_copy(cards, pick, copy, name, pt):
    s = build(cards, [LAZAV, "Grizzly Bears", "Disfigure", "Lightning Bolt"])
    lazav = put(s, LAZAV)
    grave = {n: grave_new(s, n) for n in ("Grizzly Bears", "Disfigure")}
    asked = crime(s, grave.get(pick), copy)
    assert asked == (["exile"] + (["copy"] if pick == "Grizzly Bears" else []))
    assert now(s, lazav).counters.get("+1/+1") == 1 and ch(s, lazav).name == name and ch(s, lazav).pt == pt
    assert (now(s, grave[pick]).zone == "p1:exile") if pick else all(now(s, c).zone == "p1:graveyard" for c in grave.values())
    to_phase(s, "main1", turn=3)  # (until end of turn: Lazav is Lazav again, the counter stays)
    assert ch(s, lazav).name == "Lazav, Familiar Stranger" and ch(s, lazav).pt == (2, 5)
    check(s)


def test_lazav_exiles_from_an_opponents_graveyard_and_triggers_only_once_each_turn(cards):
    s = build(cards, [LAZAV, "Lightning Bolt"], ["Grizzly Bears"])
    lazav = put(s, LAZAV)
    theirs = grave_new(s, "Grizzly Bears", "p2")
    asked = crime(s, theirs, True, bolts=1)
    assert asked == ["exile", "copy"] and now(s, theirs).zone == "p2:exile"
    again = crime(s, None, None)  # (a second crime the same turn: no second trigger)
    assert again == [] and now(s, lazav).counters.get("+1/+1") == 1
    check(s)


def strip_table(cards, order):
    """Bösium Strip activated; ``order`` names the cards put into Alice's graveyard one after another (the last is on top)."""
    s = build(cards, [STRIP, *dict.fromkeys(order), "Grizzly Bears", "Twisted Abomination"])
    st = put(s, STRIP)
    gy = {n: grave_new(s, n) for n in order}
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=st.id, ability=ability(s, st, "{3}"))
    settle(s)
    return s, gy


def cast_gy(s, card, *targets):
    mana(s, "p1", B=1, R=1)
    act(s, "p1", type="cast_spell", card_id=card.id, targets=list(targets))
    settle(s)


def test_bosium_strip_casts_only_the_top_card_and_exiles_it(cards):
    s, gy = strip_table(cards, ["Lightning Bolt", "Disfigure"])
    big = put(s, "Twisted Abomination")  # (5/3: it survives the Disfigure, so nothing else lands on top of the graveyard)
    with pytest.raises(ActionError):  # (the Bolt is under the Disfigure)
        cast_gy(s, gy["Lightning Bolt"], "p2")
    cast_gy(s, gy["Disfigure"], big.id)
    assert now(s, gy["Disfigure"]).zone == "p1:exile" and now(s, big).zone == "p1:battlefield"  # (exiled instead of put into the graveyard, 614.1a)
    cast_gy(s, gy["Lightning Bolt"], "p2")  # (now it is on top)
    assert life(s, "p2") == 37 and now(s, gy["Lightning Bolt"]).zone == "p1:exile"
    check(s)


def test_bosium_strip_cant_cast_an_instant_under_a_creature_card_or_without_the_ability(cards):
    s, gy = strip_table(cards, ["Lightning Bolt", "Grizzly Bears"])
    with pytest.raises(ActionError):
        cast_gy(s, gy["Lightning Bolt"], "p2")
    with pytest.raises(ActionError):  # (a creature card is no instant or sorcery)
        cast_gy(s, gy["Grizzly Bears"])
    check(s)


def test_bosium_strip_without_its_activation_allows_nothing(cards):
    s = build(cards, [STRIP, "Lightning Bolt"])
    put(s, STRIP)
    bolt = grave_new(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    check(s)


def ready(s, c):
    s.state.rules.controlled_since[c.id].turn = 0
    return c


def go(s, c, start, targets=(), mana_pool=None):
    if mana_pool:
        mana(s, "p1", **mana_pool)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, start), targets=list(targets), **({"target_counts": [1]} if targets else {}))


def pick_for(s, pid, option):
    d = s.state.rules.decision
    assert d is not None and d.player == pid, (d and d.player, pid)
    assert option in {o.id for o in d.options}, (option, [o.id for o in d.options])
    act(s, pid, type="choose", decision_id=d.id, option_ids=[option])


@pytest.mark.parametrize("second", ["p1", "p2", "bears"])
def test_cuombajj_witches_second_target_is_the_opponents_choice(cards, second):
    s = build(cards, [WITCHES, "Grizzly Bears"])
    w = ready(s, put(s, WITCHES))
    bears = put(s, "Grizzly Bears")
    go(s, w, "{T}")  # (no target announced by Alice: she picks the first one now)
    d = s.state.rules.decision
    assert d.player == "p1"
    pick_for(s, "p1", "p2")  # her own target: Bob
    pick_for(s, "p2", bears.id if second == "bears" else second)  # (Bob chooses the second: anything, even Alice's own creature)
    settle(s)
    assert now(s, w).tapped
    assert life(s, "p2") == (39 - (second == "p2")) and life(s, "p1") == 40 - (second == "p1") and (now(s, bears).damage == 1) == (second == "bears")
    check(s)


def test_cuombajj_witches_with_two_opponents_the_activator_picks_who_chooses(cards):
    s = table(cards, [WITCHES], [], [])
    w = ready(s, put(s, WITCHES))
    go(s, w, "{T}")
    pick_for(s, "p1", "p2")
    pick_for(s, "p1", "p3")  # Alice picks Carol as the chooser
    d = s.state.rules.decision
    assert d.player == "p3" and not s.view("p1")["rules"]["decision"].get("options")
    pick_for(s, "p3", "p1")
    settle(s)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (39, 39, 40)
    check(s)


def test_magus_of_the_arena_the_chosen_opponent_picks_one_of_their_own_creatures_and_the_two_fight(cards):
    s = table(cards, [MAGUS, "Grizzly Bears"], ["Grizzly Bears"], ["Benalish Hero"])
    m = ready(s, put(s, MAGUS))
    mine = put(s, "Grizzly Bears")
    bob_bears = put(s, "Grizzly Bears", "p2")
    carol = put(s, "Benalish Hero", "p3")
    go(s, m, "{3}", [], {"C": 3})
    pick_for(s, "p1", mine.id)
    pick_for(s, "p1", "p3")  # Alice has Carol choose
    d = s.state.rules.decision
    assert d.player == "p3" and {o.id for o in d.options} == {carol.id}  # (their own creature only: not Bob's)
    pick_for(s, "p3", carol.id)
    settle(s)
    assert now(s, mine).tapped and now(s, m).tapped  # (Carol's Hero was tapped too; it died in the fight)
    assert now(s, carol).zone == "p3:graveyard" and now(s, mine).damage == 1 and now(s, bob_bears).zone == "p2:battlefield"
    check(s)


def test_cuombajj_witches_alice_cannot_name_the_opponents_target_herself(cards):
    s = build(cards, [WITCHES])
    w = ready(s, put(s, WITCHES))
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=w.id, ability=ability(s, w, "{T}"), targets=["p2", "p2"], target_counts=[1, 1])
    assert not now(s, w).tapped and not s.state.zones.get("stack")
    # (no replay check: ``ready`` set the summoning-sickness stamp by hand, which a replay of the log cannot know)


def faces(monkeypatch, values):
    values = iter(values)
    monkeypatch.setattr("app.game.resolve._rng_int", lambda rng, lo, hi: next(values))


def upkeep(s, answers=None, limit=40):
    """Into Alice's next upkeep; the cumulative upkeep question is answered ``yes`` (pay) or not; the rest as ``answers`` (option ids) in turn."""
    answers = list(answers or [])
    start = s.state.turn.number
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answers.pop(0)] if answers else [d.options[0].id])
        elif s.state.turn.number > start + 1 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")


def test_karplusan_minotaur_lost_flip_lets_the_opponent_choose_the_target(cards, monkeypatch):
    s = build(cards, [MINOTAUR])
    m = put(s, MINOTAUR)
    faces(monkeypatch, [0])
    upkeep(s, ["pay", "p1"])  # (pay the cumulative upkeep: one flip, lost; Bob aims the 1 damage at Alice)
    assert now(s, m).zone == "p1:battlefield" and now(s, m).counters.get("age") == 1
    assert (life(s, "p1"), life(s, "p2")) == (39, 40)
    check(s)


def test_karplusan_minotaur_won_flip_is_aimed_by_its_controller(cards, monkeypatch):
    s = build(cards, [MINOTAUR])
    put(s, MINOTAUR)
    faces(monkeypatch, [1])
    upkeep(s, ["pay", "p2"])
    assert (life(s, "p1"), life(s, "p2")) == (40, 39)
    check(s)


def test_karplusan_minotaur_with_two_opponents_the_controller_picks_who_chooses(cards, monkeypatch):
    s = table(cards, [MINOTAUR], [], [])
    put(s, MINOTAUR)
    faces(monkeypatch, [0])
    seen = []
    answers = ["pay", "p3", "p2"]  # pay; Alice picks Carol; Carol aims at Bob
    start = s.state.turn.number
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            seen.append(d.player)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answers.pop(0)])
        elif s.state.turn.number > start + 2 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert seen == ["p1", "p1", "p3"] and (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 39, 40)
    check(s)


def test_karplusan_minotaur_is_sacrificed_if_its_upkeep_is_not_paid_and_nothing_is_flipped(cards, monkeypatch):
    s = build(cards, [MINOTAUR])
    m = put(s, MINOTAUR)
    faces(monkeypatch, [])  # (a flip here would raise StopIteration)
    upkeep(s, ["decline"])
    assert now(s, m).zone == "p1:graveyard" and (life(s, "p1"), life(s, "p2")) == (40, 40)
    check(s)


def test_karplusan_minotaur_flips_once_for_each_age_counter(cards, monkeypatch):
    s = build(cards, [MINOTAUR])
    m = put(s, MINOTAUR)
    act(s, "p1", type="counter", card_ids=[m.id], kind="age", delta=1)  # (an earlier upkeep's age counter: now two)
    faces(monkeypatch, [0, 1])
    for _ in range(40):  # a lost flip (Bob aims at Alice) and a won one (Alice aims at Bob): whoever is asked aims at the other player
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            pick = ["pay"] if "cumulative" in d.prompt else [o.id for o in d.options] if d.prompt.startswith("Order") else ["p2" if d.player == "p1" else "p1"]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.turn.number >= 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert now(s, m).counters.get("age") == 2 and (life(s, "p1"), life(s, "p2")) == (39, 39)
    check(s)


def attacks_this_turn(s, creatures):
    """Alice declares ``creatures`` as attackers every time she may this turn; returns the number of times (combat phases)."""
    for c in creatures:
        s.state.rules.controlled_since[c.id].turn = 0
    declared, start = 0, s.state.turn.number
    for _ in range(120):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            legal = [c for c in creatures if not now(s, c).tapped]
            declared += 1
            act(s, d.player, type=d.kind, attackers=[{"card_id": c.id, "target": "p2"} for c in legal])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type=d.kind, blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif s.state.turn.number > start:
            return declared
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("turn never ended")


@pytest.mark.parametrize(("counters", "combats"), [(7, 2), (6, 1)])
def test_desert_were_worm_extra_combat_only_with_total_power_12_and_only_the_first_time(cards, counters, combats):
    """The Worm (0 + 2 for the Mountain + the counters) and a 3-power Albino Troll attack: their powers add up to 12 or to 11."""
    s = build(cards, [WORM, "Mountain", "Albino Troll"])
    worm, troll = put(s, WORM), put(s, "Albino Troll")
    put(s, "Mountain")
    act(s, "p1", type="counter", card_ids=[worm.id], kind="+1/+1", delta=counters)
    assert int(ch(s, worm).pt[0]) + int(ch(s, troll).pt[0]) == (12 if combats == 2 else 11)
    assert attacks_this_turn(s, [worm, troll]) == combats
    check(s)


def test_spire_phantasm_enters_without_drawing_since_nothing_was_guessed(cards):
    s = build(cards, [PHANTASM])
    hand = len(s.state.zones["p1:hand"])
    cast_on(s, PHANTASM)
    assert now(s, named(s, PHANTASM)).zone == "p1:battlefield" and not s.state.zones.get("stack") and s.state.rules.decision is None
    assert len(s.state.zones["p1:hand"]) == hand  # (the spell left the hand; nothing was drawn)
    check(s)


def modular_death(s, stinger):
    """An Arcbound Worker (cast: it enters with its one +1/+1 counter) dies to a Bolt; its modular trigger puts its counters on ``stinger``."""
    worker = cast_on(s, "Arcbound Worker")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[worker.id])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[stinger.id if stinger.id in {o.id for o in d.options} else d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return worker


@pytest.mark.parametrize(("zabaz", "mine", "added"), [(True, True, 2), (False, True, 1), (True, False, 1)])
def test_zabaz_boosts_the_counters_a_modular_trigger_puts_on_your_creatures(cards, zabaz, mine, added):
    s = build(cards, [ZABAZ, "Lightning Bolt", "Arcbound Worker", "Arcbound Stinger"], ["Frogmite"])
    if zabaz:
        cast_on(s, ZABAZ)
    target = cast_on(s, "Arcbound Stinger") if mine else put(s, "Frogmite", "p2")
    before = now(s, target).counters.get("+1/+1", 0)
    worker = modular_death(s, target)
    assert now(s, worker).zone == "p1:graveyard"
    assert now(s, target).counters.get("+1/+1", 0) == before + added  # (the Worker's one counter, plus one more for Zabaz's controller's creature)
    check(s)


def test_zabaz_does_not_boost_a_plain_counter_effect(cards):
    s = build(cards, [ZABAZ, "Battlegrowth", "Grizzly Bears"])
    cast_on(s, ZABAZ)
    bears = put(s, "Grizzly Bears")
    cast_on(s, "Battlegrowth", bears)
    assert now(s, bears).counters.get("+1/+1") == 1
    check(s)


EMERITUS = "Emeritus of Conflict // Lightning Bolt"


def codie_table(cards, codie=True):
    s = build(cards, [CODIE, EMERITUS, "Lightning Bolt"])
    c = ready(s, put(s, CODIE)) if codie else None
    emeritus = put(s, EMERITUS)
    return s, c, emeritus


def prepared_copy(s, emeritus):
    return s.state.cards[s.state.rules.prepared[s.state.rules.object_id(emeritus.id)]]


def answer_all(s, first="p2"):
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [first] if any(o.id == first for o in d.options) else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_codie_prepares_each_creature_and_copies_the_prepared_spell(cards):
    s, c, emeritus = codie_table(cards)
    mana(s, "p1", W=1, U=1, B=1, R=1, G=1)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{W}"))
    settle(s)
    assert s.state.rules.object_id(emeritus.id) in s.state.rules.prepared and now(s, c).tapped
    copy = prepared_copy(s, emeritus)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=copy.id, targets=["p2"])
    answer_all(s)
    assert life(s, "p2") == 40 - 3 - 3  # (the prepared Bolt and Codie's copy of it)
    check(s)


def test_codie_does_not_copy_a_spell_that_is_not_prepared(cards):
    s, c, emeritus = codie_table(cards)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer_all(s)
    assert life(s, "p2") == 37
    check(s)


def test_a_prepared_spell_is_not_copied_by_an_opponents_codie(cards):
    """"Whenever you cast": Bob's Codie sees Bob's casts only. Alice's Studious First-Year enters prepared; its Rampant Growth fetches one land."""
    s = build(cards, ["Studious First-Year // Rampant Growth"], [CODIE])
    put(s, CODIE, "p2")
    first = to_hand(s, "Studious First-Year // Rampant Growth")
    mana(s, "p1", G=1)
    act(s, "p1", type="cast_spell", card_id=first.id)
    answer_all(s)
    copy = s.state.cards[next(iter(s.state.rules.prepared.values()))]
    lands = len([c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Forest"])
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=copy.id)
    answer_all(s)
    assert len([c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Forest"]) == lands + 1
    check(s)


def test_gaeas_liege_is_as_big_as_the_forests_you_control_while_not_attacking(cards):
    s = build(cards, [LIEGE], ["Breeding Pool"])
    liege = put(s, LIEGE)
    put(s, "Breeding Pool", "p2")  # (a Forest, but Bob's)
    for _ in range(3):
        put_new(s, "Forest")
    assert ch(s, liege).pt == (3, 3)
    put_new(s, "Forest")
    assert ch(s, liege).pt == (4, 4)
    check(s)


def test_gaeas_liege_makes_a_land_a_forest_while_it_stays_and_counts_the_defenders_forests_when_it_attacks(cards):
    s = build(cards, [LIEGE, "Lightning Bolt"], ["Breeding Pool"])
    liege = ready(s, put(s, LIEGE))
    pool = put(s, "Breeding Pool", "p2")
    island = put_new(s, "Island", "p2")
    put_new(s, "Forest")
    activate(s, liege, "{T}", targets=[island.id], target_counts=[1])
    assert "Forest" in ch(s, island).subtypes and ch(s, liege).pt == (1, 1)  # (my one Forest)
    stops(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": liege.id, "target": "p2"}])
    assert ch(s, liege).pt == (2, 2)  # (Bob's Breeding Pool and the Island that became a Forest)
    for _ in range(8):  # (through combat to the second main phase, where a Bolt ends the Liege and with it the land's Forest type)
        if s.state.turn.phase == "main2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    cast_on(s, "Lightning Bolt", liege)
    assert now(s, liege).zone == "p1:graveyard"
    assert "Forest" not in ch(s, island).subtypes and "Forest" in ch(s, pool).subtypes
    check(s)


@pytest.mark.parametrize(("target", "blocker_pid", "blockable"), [("p3", "p3", False), ("p2", "p2", True)])
def test_become_the_pilot_creature_is_blockable_only_when_attacking_its_owner(cards, target, blocker_pid, blockable):
    s = table(cards, [PILOT], ["Grizzly Bears", "Benalish Hero"], ["Mesa Pegasus"])
    stolen = put(s, "Grizzly Bears", "p2")
    bob_hero, carol_pegasus = put(s, "Benalish Hero", "p2"), put(s, "Mesa Pegasus", "p3")
    cast_on(s, PILOT, stolen)
    assert now(s, stolen).controller == "p1" and ch(s, stolen).pt == (4, 4)
    s.state.rules.controlled_since[stolen.id].turn = 0
    for want in ("declare_attackers", "declare_blockers"):
        while s.state.rules.decision is None or s.state.rules.decision.kind != want or (want == "declare_blockers" and s.state.rules.decision.player != blocker_pid):
            d = s.state.rules.decision
            if d is not None and d.kind == "declare_blockers":  # (the other defender declares nothing)
                act(s, d.player, type="declare_blockers", blocks=[])
            else:
                act(s, s.state.rules.priority, type="pass_priority")
        if want == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": stolen.id, "target": target}])
    blocker = bob_hero if blocker_pid == "p2" else carol_pegasus
    attempt = [{"blocker_id": blocker.id, "attacker_id": stolen.id}]
    if blockable:
        act(s, blocker_pid, type="declare_blockers", blocks=attempt)
        settle(s)
        assert now(s, blocker).zone == "p2:graveyard"  # (the 1/1 Hero blocked the 4/4 and died)
    else:
        with pytest.raises(ActionError):
            act(s, blocker_pid, type="declare_blockers", blocks=attempt)
        act(s, blocker_pid, type="declare_blockers", blocks=[])


@pytest.mark.parametrize(("exploit", "counters", "bounced"), [
    ("Grizzly Bears", 0, ["Benalish Hero"]),                       # toughness 2: only the 1/1 is less
    ("Twisted Abomination", 0, ["Benalish Hero", "Grizzly Bears"]),  # toughness 3
    ("Grizzly Bears", 1, ["Benalish Hero", "Grizzly Bears"]),       # a +1/+1 counter: 3, as it last existed
    (None, 0, []),                                                  # nothing exploited: the ability never triggers
])
def test_profaner_of_the_dead_returns_the_smaller_creatures_of_opponents(cards, exploit, counters, bounced):
    s = build(cards, [PROFANER, "Grizzly Bears", "Twisted Abomination"], ["Benalish Hero", "Grizzly Bears"])
    mine = put(s, exploit) if exploit else None
    if counters:
        act(s, "p1", type="counter", card_ids=[mine.id], kind="+1/+1", delta=counters)
    theirs = {n: put(s, n, "p2") for n in ("Benalish Hero", "Grizzly Bears")}
    profaner = to_hand(s, PROFANER)
    mana(s, "p1", C=3, U=1)
    act(s, "p1", type="cast_spell", card_id=profaner.id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            pick = ["no" if mine is None else "yes"] if d.kind == "confirm" else [mine.id]  # (the exploit "may": yes with a creature to sacrifice, then which one)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    for name, c in theirs.items():
        assert now(s, c).zone == ("p2:hand" if name in bounced else "p2:battlefield"), name
    assert (mine is None) or now(s, mine).zone == "p1:graveyard"
    check(s)
