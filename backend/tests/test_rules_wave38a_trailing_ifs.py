"""Wave 38A: trailing and "Then if" conditions inside effects, and intervening "if" clauses checked again on resolution (CR 2026-09-25, real Oracle text,
tests/fixtures/wave38a_cards.json from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 603.4: an intervening "if" is checked as the trigger event happens (the ability doesn't trigger if it's false) and again as the ability resolves (it does
  nothing if it's false then). Mangara / Tomik: "two or more of those creatures are attacking you and/or planeswalkers you control" is counted again as it
  resolves — a creature removed from combat no longer counts, one that left the battlefield counts as it last existed (rulings of 2020-06-23, 608.2h).
* 608.2c: a trailing "if" or a "Then if" is read when that part of the effect happens ("draw a card if your life total is greater than your starting life
  total. Otherwise, you gain 2 life."; "Then if it wasn't kicked, discard three cards.").
* 102.4: outside a team game "your team" is "you". 119.1, 903.7: the starting life total. 506.4, 508.1, 500.8: attacked / enlisted "this combat".
* 113.6b: "At the beginning of your upkeep, if Oloro is in the command zone, you gain 2 life." works from the command zone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle, until
from tests.wave9c_kit import card_named, check, life, mana, pt, put, to_hand
from tests.wave36a_kit import attack, attack_as, next_own_turn, offered, pick, ready, to_attackers, to_turn_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave38a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w38a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_the_trailing_and_intervening_if_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


# The intervening "if" cards this wave refused are all read now: Ashnod (test_rules_activated_copy_family.py), Kazuul and Rayne
# (test_rules_wave44b_trigger_other.py), O-Kagachi (test_rules_wave100a_triggers.py), Ramses (test_rules_wave110b_ramses.py).


def table(cards, mine=(), theirs=(), players=2, commander="Krenko, Mob Boss", advance=True):
    """Alice (commander ``commander``), Bob and, with ``players=3``, Carol; ``mine`` / ``theirs`` are in Alice's / everyone else's library."""
    decks = [deck(cards, commander, [*((1, n) for n in mine), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (20, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (20, "Swamp")])][:players]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol")[:players], decks, strict=True)], shuffle=False)),
                    cards=cards)
    for pid in ("p1", "p2", "p3")[:players]:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack, so a trigger can be answered before it resolves)
    if advance:
        until(s, lambda s: s.state.turn.phase == "main1" and s.state.rules.decision is None)  # → Alice's main phase
    return s


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def triggered(s):
    """Is an ability on the stack, or waiting to be put there (a target to choose)?"""
    return bool(s.state.zones.get("stack") or s.state.rules.pending_triggers)


def keywords(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(card_named(s, name, pid)).keywords


def swing(s, pid, names, target):
    """On ``pid``'s turn, ``names`` (their creatures, summoning sickness gone) attack ``target`` (a player id)."""
    for n in names:
        ready(s, n, pid=pid)
    to_turn_of(s, pid)
    attack_as(s, pid, [card_named(s, n, pid) for n in names], target)


# -- Mangara, the Diplomat / Tomik, Wielder of Law: "if two or more of those creatures are attacking you and/or planeswalkers you control" -------------
def mangara_table(cards, bob=("Grizzly Bears", "Young Wolf"), players=2):
    s = table(cards, ["Mangara, the Diplomat"], list(bob), players)
    put(s, "Mangara, the Diplomat")
    for n in bob:
        put(s, n, "p2")
    return s


def test_mangara_draws_when_two_attackers_are_attacking_you(cards):
    s = mangara_table(cards)
    before = hand(s)
    swing(s, "p2", ["Grizzly Bears", "Young Wolf"], "p1")
    assert s.state.zones.get("stack")  # (it triggered)
    settle(s)
    assert hand(s) == before + 1
    check(s)


def test_mangara_does_not_trigger_for_a_single_attacker(cards):
    s = mangara_table(cards, bob=("Grizzly Bears",))
    before = hand(s)
    swing(s, "p2", ["Grizzly Bears"], "p1")
    assert not s.state.zones.get("stack")  # (false as the attack is declared: 603.4, it never triggers)
    settle(s)
    assert hand(s) == before
    check(s)


def test_mangara_checks_again_on_resolution_one_removed_from_combat(cards):
    s = mangara_table(cards)
    before = hand(s)
    swing(s, "p2", ["Grizzly Bears", "Young Wolf"], "p1")
    assert s.state.zones.get("stack")  # (true when it triggered …)
    act(s, "p2", type="attack", card_ids=[card_named(s, "Young Wolf", "p2").id], target=None)  # … Young Wolf is removed from combat
    settle(s)
    assert hand(s) == before  # (… false as it resolves: nothing happens)
    check(s)


def test_mangara_counts_an_attacker_that_left_the_battlefield_as_it_last_existed(cards):
    s = mangara_table(cards)
    before = hand(s)
    swing(s, "p2", ["Grizzly Bears", "Young Wolf"], "p1")
    act(s, "p2", type="move", card_ids=[card_named(s, "Young Wolf", "p2").id], to={"zone": "graveyard"})  # it dies: it was attacking Alice
    settle(s)
    assert hand(s) == before + 1  # (the 2020-06-23 ruling: use the player it was attacking before it left)
    check(s)


def test_mangara_does_not_count_attackers_attacking_another_player(cards):
    s = mangara_table(cards, players=3)
    before = hand(s)
    swing(s, "p2", ["Grizzly Bears", "Young Wolf"], "p3")  # Bob attacks Carol with both
    assert not s.state.zones.get("stack")
    settle(s)
    assert hand(s) == before
    check(s)


def walker_table(cards):
    """Bob's Grizzly Bears attacks Alice's Gideon Jura and his Young Wolf attacks Alice, in one declaration."""
    s = table(cards, ["Mangara, the Diplomat", "Gideon Jura"], ["Grizzly Bears", "Young Wolf"])
    put(s, "Mangara, the Diplomat")
    gideon = put(s, "Gideon Jura")
    act(s, "p1", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    for n in ("Grizzly Bears", "Young Wolf"):
        put(s, n, "p2")
        ready(s, n, pid="p2")
    to_turn_of(s, "p2")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": card_named(s, "Grizzly Bears", "p2").id, "target": gideon.id},
                                                      {"card_id": card_named(s, "Young Wolf", "p2").id, "target": "p1"}])
    return s


def test_mangara_counts_you_and_a_planeswalker_you_control(cards):
    s = walker_table(cards)
    before = hand(s)
    assert s.state.zones.get("stack")  # (one attacker at Alice, one at her planeswalker: two attacking "you and/or planeswalkers you control")
    settle(s)
    assert hand(s) == before + 1
    check(s)


def test_mangara_does_not_count_an_attacker_whose_planeswalker_left_before_it_resolved(cards):
    s = walker_table(cards)
    before = hand(s)
    act(s, "p1", type="move", card_ids=[card_named(s, "Gideon Jura").id], to={"zone": "graveyard"})  # the planeswalker dies: nothing is attacked any more
    settle(s)
    assert hand(s) == before  # (true as it triggered, false as it resolves: 506.4, the Bears is still attacking, but not a planeswalker you control)
    check(s)


def test_tomik_makes_that_opponent_lose_three_and_draws(cards):
    s = table(cards, ["Tomik, Wielder of Law"], ["Grizzly Bears", "Young Wolf"])
    put(s, "Tomik, Wielder of Law")
    for n in ("Grizzly Bears", "Young Wolf"):
        put(s, n, "p2")
    before, bob = hand(s), life(s, "p2")
    swing(s, "p2", ["Grizzly Bears", "Young Wolf"], "p1")
    settle(s)
    assert hand(s) == before + 1 and life(s, "p2") == bob - 3
    check(s)


def test_tomik_does_nothing_if_the_attackers_are_gone_when_it_resolves(cards):
    s = table(cards, ["Tomik, Wielder of Law"], ["Grizzly Bears", "Young Wolf"])
    put(s, "Tomik, Wielder of Law")
    for n in ("Grizzly Bears", "Young Wolf"):
        put(s, n, "p2")
    before, bob = hand(s), life(s, "p2")
    swing(s, "p2", ["Grizzly Bears", "Young Wolf"], "p1")
    act(s, "p2", type="attack", card_ids=[card_named(s, "Grizzly Bears", "p2").id], target=None)
    settle(s)
    assert hand(s) == before and life(s, "p2") == bob
    check(s)


# -- Ever-Watching Threshold: "Whenever an opponent attacks, if they attacked you and/or a planeswalker you control, draw a card." --------------------
def threshold_table(cards):
    s = table(cards, ["Ever-Watching Threshold"], ["Grizzly Bears", "Young Wolf"], players=3)
    put(s, "Ever-Watching Threshold")
    for n in ("Grizzly Bears", "Young Wolf"):
        put(s, n, "p2")
    return s


def test_ever_watching_threshold_draws_once_however_many_attack_you(cards):
    s = threshold_table(cards)
    before = hand(s)
    swing(s, "p2", ["Grizzly Bears", "Young Wolf"], "p1")
    settle(s)
    assert hand(s) == before + 1  # (one card for each opponent attacking you, no matter how many creatures: the 2018-07-13 ruling)
    check(s)


def test_ever_watching_threshold_does_not_trigger_when_they_attacked_someone_else(cards):
    s = threshold_table(cards)
    before = hand(s)
    swing(s, "p2", ["Grizzly Bears", "Young Wolf"], "p3")
    assert not s.state.zones.get("stack")  # (false as the attack is declared: 603.4)
    settle(s)
    assert hand(s) == before
    check(s)


def test_ever_watching_threshold_counts_the_attacker_that_attacked_you_among_others(cards):
    s = threshold_table(cards)
    before = hand(s)
    for n in ("Grizzly Bears", "Young Wolf"):
        ready(s, n, pid="p2")
    to_turn_of(s, "p2")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": card_named(s, "Grizzly Bears", "p2").id, "target": "p1"},
                                                      {"card_id": card_named(s, "Young Wolf", "p2").id, "target": "p3"}])
    settle(s)
    assert hand(s) == before + 1
    check(s)


# -- M'Baku, Jabari Chieftain: "Whenever a creature attacks one of your opponents, if that player is the monarch, …" -----------------------------------
def mbaku_table(cards, monarch):
    s = table(cards, ["M'Baku, Jabari Chieftain"], ["Grizzly Bears"])
    put(s, "M'Baku, Jabari Chieftain")
    ready(s, "M'Baku, Jabari Chieftain")
    act(s, "p1", type="set_monarch", player=monarch)
    return s


def test_mbaku_pumps_a_creature_attacking_the_monarch(cards):
    s = mbaku_table(cards, "p2")
    attack(s, card_named(s, "M'Baku, Jabari Chieftain"))
    assert s.state.zones.get("stack")
    settle(s)
    assert pt(s, "M'Baku, Jabari Chieftain") == (5, 4) and "trample" in keywords(s, "M'Baku, Jabari Chieftain")
    check(s)


def test_mbaku_does_not_trigger_when_the_defending_player_is_not_the_monarch(cards):
    s = mbaku_table(cards, "p1")
    attack(s, card_named(s, "M'Baku, Jabari Chieftain"))
    assert not s.state.zones.get("stack")  # (false as the attack is declared: 603.4)
    settle(s)
    assert pt(s, "M'Baku, Jabari Chieftain") == (4, 3)
    check(s)


def test_mbaku_checks_the_monarch_again_on_resolution(cards):
    s = mbaku_table(cards, "p2")
    attack(s, card_named(s, "M'Baku, Jabari Chieftain"))
    assert s.state.zones.get("stack")  # (true when it triggered …)
    act(s, "p1", type="set_monarch", player="p1")  # … Alice becomes the monarch in response
    settle(s)
    assert pt(s, "M'Baku, Jabari Chieftain") == (4, 3)  # (… false as it resolves: nothing happens)
    check(s)


# -- Tolsimir, Midnight's Light: "Whenever a Wolf you control attacks, if Tolsimir attacked this combat, target creature an opponent controls blocks that Wolf" --
def tolsimir_table(cards):
    s = table(cards, ["Tolsimir, Midnight's Light", "Young Wolf"], ["Grizzly Bears"])
    put(s, "Tolsimir, Midnight's Light")
    put(s, "Young Wolf")
    put(s, "Grizzly Bears", "p2")
    ready(s, "Tolsimir, Midnight's Light", "Young Wolf")
    return s


def must_block(s):
    """Bob is asked for blockers: may he block with nothing? (509.1c: a creature that must block if able has to)"""
    from app.game.errors import ActionError

    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[])


def test_tolsimir_makes_a_creature_block_the_wolf_when_he_attacked_too(cards):
    s = tolsimir_table(cards)
    attack(s, card_named(s, "Tolsimir, Midnight's Light"), card_named(s, "Young Wolf"))
    assert triggered(s)
    settle(s)
    must_block(s)
    check(s)


def test_tolsimir_does_nothing_for_a_wolf_attacking_without_him(cards):
    s = tolsimir_table(cards)
    attack(s, card_named(s, "Young Wolf"))
    assert not triggered(s)  # (Tolsimir didn't attack this combat: it never triggers)
    settle(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[])  # (no requirement)
    check(s)


def test_tolsimir_attacked_this_combat_is_still_so_after_he_left_it(cards):
    s = tolsimir_table(cards)
    attack(s, card_named(s, "Tolsimir, Midnight's Light"), card_named(s, "Young Wolf"))
    act(s, "p1", type="move", card_ids=[card_named(s, "Tolsimir, Midnight's Light").id], to={"zone": "graveyard"})  # he dies with the trigger on the stack
    settle(s)
    must_block(s)  # (he attacked: 603.4 asks nothing more of a fact that has happened)
    check(s)


# -- Aradesh, the Founder: "Whenever a creature you control attacks, if it enlisted a creature this combat, the creature that attacked gains double strike …" --
def aradesh_table(cards):
    s = table(cards, ["Aradesh, the Founder", "Albino Troll"], ["Grizzly Bears"])
    put(s, "Aradesh, the Founder")
    put(s, "Albino Troll")
    ready(s, "Aradesh, the Founder", "Albino Troll")
    return s


def declare_aradesh(s):
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Aradesh, the Founder").id, "target": "p2"}])


def test_aradesh_gains_double_strike_and_draws_when_it_enlisted_a_creature(cards):
    s = aradesh_table(cards)
    before = hand(s)
    declare_aradesh(s)
    pick(s, "Albino Troll")  # (enlist, 702.154a: tap the Troll, Aradesh gets +3/+0)
    assert triggered(s)
    settle(s)
    assert "double strike" in keywords(s, "Aradesh, the Founder")
    assert hand(s) == before + 1  # (1 + 3 power is 4 or greater)
    check(s)


def test_aradesh_does_not_trigger_when_it_did_not_enlist(cards):
    s = aradesh_table(cards)
    before = hand(s)
    declare_aradesh(s)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[])  # (enlist nobody)
    assert not triggered(s)  # (false as the attack is declared: 603.4, Aradesh's rulings of 2024-03-08)
    settle(s)
    assert "double strike" not in keywords(s, "Aradesh, the Founder") and hand(s) == before
    check(s)


# -- Doctor Strange, Surgeon: "At the beginning of each combat, if you have at least 10 life more than your starting life total, …" ---------------------
def strange_table(cards, life_total):
    s = table(cards, ["Doctor Strange, Surgeon", "Grizzly Bears"])
    put(s, "Doctor Strange, Surgeon")
    put(s, "Grizzly Bears")
    act(s, "p1", type="set_life", player="p1", value=life_total)
    until(s, lambda s: s.state.turn.phase == "begin_combat")
    return s


def test_doctor_strange_pumps_with_ten_more_life_than_the_starting_total(cards):
    s = strange_table(cards, 50)
    assert triggered(s)
    settle(s)
    assert pt(s, "Grizzly Bears") == (4, 4) and "vigilance" in keywords(s, "Grizzly Bears")
    check(s)


def test_doctor_strange_does_not_trigger_with_nine_more(cards):
    s = strange_table(cards, 49)
    assert not triggered(s)  # (false as the combat begins)
    settle(s)
    assert pt(s, "Grizzly Bears") == (2, 2)
    check(s)


def test_doctor_strange_checks_the_life_total_again_on_resolution(cards):
    s = strange_table(cards, 50)
    assert triggered(s)  # (true when it triggered …)
    act(s, "p1", type="life", player="p1", delta=-1)  # … 49 as it resolves
    settle(s)
    assert pt(s, "Grizzly Bears") == (2, 2)
    check(s)


# -- Cosmos Elixir: "draw a card if your life total is greater than your starting life total. Otherwise, you gain 2 life." -------------------------------
@pytest.mark.parametrize(("total", "drew", "gained"), [(41, 1, 0), (40, 0, 2), (39, 0, 2)])
def test_cosmos_elixir_draws_or_gains_life_at_the_end_step(cards, total, drew, gained):
    s = table(cards, ["Cosmos Elixir"])
    put(s, "Cosmos Elixir")
    act(s, "p1", type="set_life", player="p1", value=total)
    before = hand(s)
    until(s, lambda s: s.state.turn.phase == "end")
    settle(s)
    assert hand(s) == before + drew and life(s) == total + gained  # (608.2c: the condition is read as that instruction happens)
    check(s)


# -- Sphinx of Lost Truths / Skizzik: "Then if it wasn't kicked, discard three cards." / "if this creature wasn't kicked, sacrifice it" --------------
@pytest.mark.parametrize("kicked", [0, 1])
def test_sphinx_of_lost_truths_discards_three_only_if_it_was_not_kicked(cards, kicked):
    s = table(cards, ["Sphinx of Lost Truths"])
    to_hand(s, "Sphinx of Lost Truths")
    before = hand(s)  # (with the Sphinx in it)
    mana(s, U=3 if kicked else 2, G=4 if kicked else 3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sphinx of Lost Truths").id, kicker=kicked)
    settle(s)
    assert hand(s) == before - 1 + 3 - (0 if kicked else 3)  # (it left the hand, three cards drawn, then three discarded if it wasn't kicked)
    check(s)


@pytest.mark.parametrize("kicked", [0, 1])
def test_skizzik_is_sacrificed_at_the_end_step_only_if_it_was_not_kicked(cards, kicked):
    s = table(cards, ["Skizzik"])
    to_hand(s, "Skizzik")
    mana(s, R=2 if kicked else 1, G=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Skizzik").id, kicker=kicked)
    settle(s)
    until(s, lambda s: s.state.turn.phase == "end")
    settle(s)
    assert s.state.cards[card_named(s, "Skizzik").id].zone == ("p1:battlefield" if kicked else "p1:graveyard")
    check(s)


# -- Ephara, God of the Polis: "At the beginning of each upkeep, if you had another creature enter the battlefield under your control last turn, …" ----
@pytest.mark.parametrize("bears", [True, False])
def test_ephara_draws_at_the_next_upkeep_only_after_another_creature_entered(cards, bears):
    s = table(cards, ["Ephara, God of the Polis", "Grizzly Bears"])
    put(s, "Ephara, God of the Polis")
    if bears:
        put(s, "Grizzly Bears")
    before = hand(s)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "upkeep")
    assert triggered(s) == bears  # (Ephara herself entering is no "another creature": false when the upkeep begins, 603.4)
    settle(s)
    assert hand(s) == before + int(bears)
    check(s)


def test_ephara_looks_only_at_the_turn_before(cards):
    s = table(cards, ["Ephara, God of the Polis", "Grizzly Bears"])
    put(s, "Ephara, God of the Polis")
    put(s, "Grizzly Bears")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "upkeep")
    settle(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "upkeep")
    assert not triggered(s)  # (nothing entered during turn 2)
    check(s)


# -- Oloro, Ageless Ascetic: "At the beginning of your upkeep, if Oloro is in the command zone, you gain 2 life." -----------------------------------
def oloro_table(cards):
    s = table(cards, commander="Oloro, Ageless Ascetic", advance=False)
    until(s, lambda s: s.state.turn.phase == "upkeep" and s.state.turn.number == 1)
    return s


def test_oloro_gains_two_life_at_the_upkeep_from_the_command_zone(cards):
    s = oloro_table(cards)
    assert triggered(s) and s.state.cards[card_named(s, "Oloro, Ageless Ascetic").id].zone == "p1:command"
    settle(s)
    assert life(s) == 42
    check(s)


def test_oloro_checks_the_command_zone_again_on_resolution(cards):
    s = oloro_table(cards)
    assert triggered(s)  # (true when it triggered …)
    act(s, "p1", type="move", card_ids=[card_named(s, "Oloro, Ageless Ascetic").id], to={"zone": "hand"})  # … it leaves the command zone
    settle(s)
    assert life(s) == 40  # (… false as it resolves)
    check(s)


def test_oloro_on_the_battlefield_gains_two_not_four(cards):
    s = oloro_table(cards)
    settle(s)
    put(s, "Oloro, Ageless Ascetic")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "upkeep")
    settle(s)
    assert life(s) == 44  # (42, then only its battlefield upkeep ability: the command zone one is false)
    check(s)


# -- Sickle Dancer / Nimbus Champion: "your team" (102.4: outside a team game, "you") -----------------------------------------------------------------
@pytest.mark.parametrize("warrior", [True, False])
def test_sickle_dancer_grows_only_if_your_team_controls_another_warrior(cards, warrior):
    s = table(cards, ["Sickle Dancer", "Nimbus Champion"], ["Grizzly Bears"])
    put(s, "Sickle Dancer")
    if warrior:
        put(s, "Nimbus Champion")
    ready(s, "Sickle Dancer")
    attack(s, card_named(s, "Sickle Dancer"))
    assert triggered(s) == warrior  # (an intervening "if": false as it attacks, it never triggers, 603.4)
    settle(s)
    assert pt(s, "Sickle Dancer") == ((4, 3) if warrior else (3, 2))
    check(s)


@pytest.mark.parametrize(("target", "returned"), [("Young Wolf", True), ("Grizzly Bears", False)])
def test_nimbus_champion_returns_a_creature_only_if_its_power_is_at_most_your_warriors(cards, target, returned):
    s = table(cards, ["Nimbus Champion"], ["Grizzly Bears", "Young Wolf"])
    put(s, "Nimbus Champion")
    put(s, "Grizzly Bears", "p2")
    put(s, "Young Wolf", "p2")
    ready(s, "Nimbus Champion")
    attack(s, card_named(s, "Nimbus Champion"))
    pick(s, target)  # (one Warrior: Young Wolf's power 1 is at most 1, Grizzly Bears' 2 is not; read as it resolves, 608.2c)
    settle(s)
    assert s.state.cards[card_named(s, target, "p2").id].zone == ("p2:hand" if returned else "p2:battlefield")
    check(s)


# -- Tokka & Rahzar, Terrible Twos: "…, Tokka & Rahzar deal 3 damage to that player." (the plural verb of a name that is two creatures) --------------------
def tokka_table(cards, artifacts):
    s = table(cards, ["Tokka & Rahzar, Terrible Twos", "Frogmite", "Sol Ring", "Arcane Signet"])
    put(s, "Tokka & Rahzar, Terrible Twos")
    if artifacts:
        put(s, "Sol Ring")
        put(s, "Arcane Signet")
    to_hand(s, "Frogmite")
    return s


def test_tokka_deals_three_to_a_player_who_paid_less_than_the_mana_value(cards):
    s = tokka_table(cards, artifacts=True)
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Frogmite").id)  # (affinity for artifacts: {4} costs {2} with two artifacts)
    settle(s)
    assert life(s) == 37
    check(s)


def test_tokka_does_nothing_when_the_whole_mana_value_was_paid(cards):
    s = tokka_table(cards, artifacts=False)
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Frogmite").id)
    settle(s)
    assert life(s) == 40
    check(s)


# -- Imoen, Mystic Trickster: "…, if you have the initiative, draw a card. Draw another card if you've completed a dungeon." ----------------------------
@pytest.mark.parametrize("initiative", [True, False])
def test_imoen_draws_one_card_with_the_initiative_and_no_dungeon_completed(cards, initiative):
    s = table(cards, ["Imoen, Mystic Trickster"])
    put(s, "Imoen, Mystic Trickster")
    if initiative:
        act(s, "p1", type="set_initiative", player="p1")
    before = hand(s)
    until(s, lambda s: s.state.turn.phase == "end")
    assert triggered(s) == initiative  # (without the initiative: false when the end step begins, 603.4)
    settle(s)
    assert hand(s) == before + int(initiative)  # (the second draw is gated by its own trailing "if": no dungeon completed)
    check(s)


# -- Agrus Kos, Spirit of Justice: "choose up to one target creature. If it's suspected, exile it. Otherwise, suspect it." ----------------------------------
def test_agrus_kos_suspects_a_creature_and_exiles_it_when_it_is_already_suspected(cards):
    s = table(cards, ["Agrus Kos, Spirit of Justice"], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Agrus Kos, Spirit of Justice")
    mana(s, R=1, W=1, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Agrus Kos, Spirit of Justice").id)
    offered(s)
    pick(s, "Grizzly Bears")  # (enters: the Bears isn't suspected, so he suspects it; 701.60a)
    settle(s)
    bears = card_named(s, "Grizzly Bears", "p2")
    assert s.state.rules.suspected and s.state.cards[bears.id].zone == "p2:battlefield"
    next_own_turn(s)
    attack(s, card_named(s, "Agrus Kos, Spirit of Justice"))
    offered(s)
    pick(s, "Grizzly Bears")  # (attacks: it is suspected now, read as the instruction is carried out, 608.2c)
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:exile"
    check(s)


# -- Deathbringer Liege: "Whenever you cast a black spell, you may destroy target creature if it's tapped." -------------------------------------------
@pytest.mark.parametrize("tapped", [True, False])
def test_deathbringer_liege_destroys_the_target_only_if_it_is_tapped(cards, tapped):
    s = table(cards, ["Deathbringer Liege", "Dregscape Zombie"], ["Grizzly Bears"])
    put(s, "Deathbringer Liege")
    bears = put(s, "Grizzly Bears", "p2")
    if tapped:
        act(s, "p2", type="tap", card_ids=[bears.id])
    to_hand(s, "Dregscape Zombie")
    mana(s, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Dregscape Zombie").id)
    offered(s)
    pick(s, "Grizzly Bears")
    settle(s)
    assert s.state.cards[bears.id].zone == ("p2:graveyard" if tapped else "p2:battlefield")  # (608.2c: tapped or not as it resolves)
    check(s)
