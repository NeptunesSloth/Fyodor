"""Wave 47B: "Choose an opponent at random." / "… an opponent chosen at random" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave47b_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* No rule governs "at random": nobody chooses, the table picks without bias, while the ability resolves, from the players still in the game (800.4a)
  (Vial Smasher the Fierce ruling 2020-11-10). The pick is recorded in the resolution (a decision's resume, the saved rules state) and every
  instruction after it is a recorded step, so a replay or a load never draws again.
* Vial Smasher: after the pick its controller chooses the player or one of that player's planeswalkers (ruling).
* Zaffai, Thunder Conductor: "… deals 10 damage to an opponent chosen at random" inside the "mana value 10 or greater" condition.
"""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave34b_activated import activate, ask, settle
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave47b_kit import FULL, build3, cast, life, open_cards, pin_random


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("index, hit, spared", [(0, "p2", "p3"), (-1, "p3", "p2")])
def test_vial_smasher_deals_the_first_spells_mana_value_to_one_opponent_at_random(cards, monkeypatch, index, hit, spared):
    pin_random(monkeypatch, index)
    s = build3(cards, ["Vial Smasher the Fierce", "Lightning Bolt"])
    put(s, "Vial Smasher the Fierce")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=["p1"])  # (aimed at Alice herself: the trigger's damage is the only one an opponent takes)
    assert (life(s, hit), life(s, spared)) == (39, 40)  # the first spell has mana value 1
    log = json.dumps(s.view("p2")["log"])
    assert f"{s.state.players[hit].name} is chosen at random" in log
    check(s)


def test_vial_smasher_triggers_only_for_the_first_spell_each_turn(cards, monkeypatch):
    pin_random(monkeypatch)
    s = build3(cards, ["Vial Smasher the Fierce", "Lightning Bolt", "Grizzly Bears"])
    put(s, "Vial Smasher the Fierce")
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Grizzly Bears")
    mana(s, R=1, G=2)
    cast(s, "Lightning Bolt", targets=["p1"])
    cast(s, "Grizzly Bears")
    assert (life(s, "p2"), life(s, "p3")) == (40, 39)  # one pick, one hit
    check(s)


def test_vial_smasher_controller_chooses_the_player_or_one_of_their_planeswalkers(cards, monkeypatch):
    pin_random(monkeypatch)  # Carol
    s = build3(cards, ["Vial Smasher the Fierce", "Lightning Bolt"], carols=["Jace Beleren"])
    put(s, "Vial Smasher the Fierce")
    jace = put(s, "Jace Beleren", "p3")
    act(s, "p3", type="counter", card_ids=[jace.id], kind="loyalty", delta=3)  # (a card moved onto the table has none)
    loyalty = s.state.cards[jace.id].counters.get("loyalty", 0)
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p1"])
    d = ask(s)  # (the trigger resolves first, before the Bolt)
    assert d.player == "p1"
    assert [o.id for o in d.options] == ["p3", jace.id]  # Carol herself, or her planeswalker (public choices)
    check(s)  # a save and a load while the choice is pending
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[jace.id])
    settle(s)
    assert s.state.cards[jace.id].counters.get("loyalty", 0) == loyalty - 1 and life(s, "p3") == 40
    check(s)


def test_vial_smasher_asks_nothing_when_the_opponent_has_no_planeswalker(cards, monkeypatch):
    pin_random(monkeypatch)
    s = build3(cards, ["Vial Smasher the Fierce", "Lightning Bolt"])
    put(s, "Vial Smasher the Fierce")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=["p1"])
    assert s.state.rules.decision is None and life(s, "p3") == 39
    check(s)


def test_with_one_opponent_left_that_opponent_is_the_pick(cards):
    s = build3(cards, ["Vial Smasher the Fierce", "Lightning Bolt"])
    act(s, "p3", type="concede")  # 800.4a: a player who left the game can't be chosen
    put(s, "Vial Smasher the Fierce")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=["p1"])
    assert life(s, "p2") == 39
    check(s)


@pytest.mark.parametrize("spent, damage", [(8, 0), (9, 10)])
def test_zaffai_deals_10_to_one_opponent_at_random_only_for_a_spell_of_mana_value_10(cards, monkeypatch, spent, damage):
    pin_random(monkeypatch)  # Carol
    s = build3(cards, ["Zaffai, Thunder Conductor", "Blaze"])
    put(s, "Zaffai, Thunder Conductor")
    to_hand(s, "Blaze")
    mana(s, R=spent + 1)  # Blaze {X}{R}: mana value X + 1
    cast(s, "Blaze", targets=["p1"], x_value=spent)
    assert life(s, "p3") == 40 - damage and life(s, "p2") == 40
    log = json.dumps(s.view("p2")["log"])
    assert ("Carol is chosen at random" in log) is bool(damage)  # (nothing is picked when the condition fails)
    check(s)


# -- "Choose a player at random. When you do, Strax fights another target creature that player controls." ------------------------------------------
def strax_table(cards, monkeypatch, index):
    pin_random(monkeypatch, index)
    s = build3(cards, ["Strax, Sontaran Nurse", "Sol Ring"], bobs=["Grizzly Bears"], carols=["Hill Giant"])
    strax = put(s, "Strax, Sontaran Nurse")
    put(s, "Sol Ring")  # (the artifact sacrificed as the cost)
    bears, hill = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p3")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (no summoning sickness)
    mana(s, C=2)
    activate(s, "p1", strax, "Choose a player at random")
    return s, strax, bears, hill


def test_strax_fights_a_creature_of_the_player_chosen_at_random_and_no_other(cards, monkeypatch):
    s, strax, bears, hill = strax_table(cards, monkeypatch, -1)  # Carol
    d = s.state.rules.decision  # the reflexive ability's target: only Carol's creatures are legal
    if d is not None and d.kind != "confirm":
        assert [o.id for o in d.options] == [hill.id]
    settle(s)
    assert s.state.cards[hill.id].zone == "p3:graveyard" and s.state.cards[bears.id].zone == "p2:battlefield"  # 5 damage to a 3/3; Bob's creature untouched
    assert s.state.cards[strax.id].damage == 3 and s.state.cards[strax.id].counters.get("+1/+1") == 1  # Glory of Battle
    assert "Carol is chosen at random" in json.dumps(s.view("p2")["log"])
    check(s)


def test_strax_with_the_player_chosen_having_no_other_creature_fights_nothing(cards, monkeypatch):
    s, strax, bears, hill = strax_table(cards, monkeypatch, 0)  # Alice herself: Strax is her only creature
    settle(s)
    assert (s.state.cards[bears.id].zone, s.state.cards[hill.id].zone) == ("p2:battlefield", "p3:battlefield") and s.state.cards[strax.id].damage == 0
    check(s)


# -- "At the beginning of combat on your turn, choose an opponent at random. Ruhan attacks that player this combat if able." --------------
def to_declare(s):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")


def test_ruhan_must_attack_the_opponent_chosen_at_random_not_another(cards, monkeypatch):
    """508.1d: the requirement is to attack that player (not a planeswalker of theirs); another player may not be attacked while the requirement
    can be obeyed (Ruhan ruling 2011-09-22). It lasts this combat only (611.2)."""
    pin_random(monkeypatch)  # Carol
    s = build3(cards, ["Ruhan of the Fomori"])
    ruhan = put(s, "Ruhan of the Fomori")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (Alice's second turn: no summoning sickness)
    to_declare(s)
    assert "Carol is chosen at random" in json.dumps(s.view("p2")["log"])
    check(s)  # a save and a load with the requirement in force
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": ruhan.id, "target": "p2"}])
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[])  # (it must attack: it is able)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ruhan.id, "target": "p3"}])
    check(s)


def test_ruhan_is_free_when_the_chosen_opponent_has_left(cards):
    s = build3(cards, ["Ruhan of the Fomori"])
    ruhan = put(s, "Ruhan of the Fomori")
    act(s, "p3", type="concede")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (turn 3 was Carol's: gone)
    to_declare(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ruhan.id, "target": "p2"}])  # (Bob is the only opponent left: he is the pick)
    check(s)
