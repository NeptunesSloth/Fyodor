"""Wave 44B: commanders whose only gap was one trigger line (CR 2026-09-25, real Oracle text, tests/fixtures/wave44b_cards.json from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 120.1, 510.2: Zagras, "Whenever a creature you control deals combat damage to a planeswalker, destroy that planeswalker." - the planeswalker dealt damage.
* 508.1, 508.5, 118.12a: Merry ("you attack with Merry and another legendary creature"), Kazuul ("if you're the defending player" - you, a planeswalker you control or
  a battle you protect; the attacker's controller may pay {3} or you get the Ogre).
* 608.2c, 614: Selvala (the new creature's power against each other creature as the ability resolves, its controller draws) and Rayne (the "additional" draw is a
  second optional draw that happens only if Rayne is enchanted as the ability resolves, ruling of 2004-10-04).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave38a_trailing_ifs import hand, table
from tests.wave9c_kit import card_named, check, mana, put
from tests.wave36a_kit import attack_as, ready, to_turn_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave44b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w44b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
COMMANDERS = ["Zagras, Thief of Heartbeats", "Merry, Esquire of Rohan", "Kazuul, Tyrant of the Cliffs", "Selvala, Heart of the Wilds", "Rayne, Academy Chancellor"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", COMMANDERS)
def test_the_commanders_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


# -- Zagras ------------------------------------------------------------------------------------------------------------------------------------
def zagras_table(cards, target):
    """Alice's hasty Zagras attacks ``target`` ("p2" or Bob's Gideon Jura, loyalty 6) on her first turn."""
    s = table(cards, ["Zagras, Thief of Heartbeats"], ["Gideon Jura"])
    zagras, gideon = put(s, "Zagras, Thief of Heartbeats"), put(s, "Gideon Jura", "p2")
    act(s, "p2", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    attack_as(s, "p1", [zagras], gideon.id if target == "gideon" else target)
    settle(s)
    return s


def test_zagras_destroys_the_planeswalker_it_dealt_combat_damage_to(cards):
    s = zagras_table(cards, "gideon")
    for _ in range(12):
        if zone(s, "Gideon Jura", "p2") != "p2:battlefield":
            break
        act(s, s.state.rules.priority, type="pass_priority")
        settle(s)
    assert zone(s, "Gideon Jura", "p2") == "p2:graveyard"  # (4 damage left it at 2 loyalty: only the trigger destroyed it)
    check(s)


def test_zagras_does_nothing_for_damage_to_a_player(cards):
    s = zagras_table(cards, "p2")
    for _ in range(12):
        act(s, s.state.rules.priority, type="pass_priority")
        settle(s)
        if s.state.turn.phase not in ("declare_attackers", "declare_blockers", "combat_damage", "first_strike_damage"):
            break
    assert s.state.players["p2"].life == 40 - 4
    assert zone(s, "Gideon Jura", "p2") == "p2:battlefield"
    check(s)


# -- Merry ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("attackers", "draws"), [(("Merry, Esquire of Rohan", "Isamaru, Hound of Konda"), 1), (("Merry, Esquire of Rohan", "Grizzly Bears"), 0),
                                                  (("Merry, Esquire of Rohan",), 0), (("Isamaru, Hound of Konda", "Grizzly Bears"), 0)])
def test_merry_draws_when_she_attacks_with_another_legendary_creature(cards, attackers, draws):
    s = table(cards, ["Merry, Esquire of Rohan", "Isamaru, Hound of Konda", "Grizzly Bears"])
    for n in ("Merry, Esquire of Rohan", "Isamaru, Hound of Konda", "Grizzly Bears"):
        put(s, n)
    ready(s, "Merry, Esquire of Rohan", "Isamaru, Hound of Konda", "Grizzly Bears")
    before = hand(s)
    attack_as(s, "p1", [card_named(s, n) for n in attackers], "p2")
    settle(s)
    assert hand(s) == before + draws
    check(s)


# -- Kazuul --------------------------------------------------------------------------------------------------------------------------------------
def ogres(s):
    return [c for c in s.state.cards.values() if c.name == "Ogre" and c.zone == "p1:battlefield"]


def kazuul_attack(cards, defender, players=2, lands=3):
    """Bob's Grizzly Bears (and ``lands`` Islands) attack ``defender`` ("p1" Alice, with Kazuul, or "p3" Carol); the table stops at the choice that comes up."""
    s = table(cards, ["Kazuul, Tyrant of the Cliffs"], ["Grizzly Bears"], players)
    put(s, "Kazuul, Tyrant of the Cliffs")
    put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears", pid="p2")
    for _ in range(lands):
        act(s, "p2", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone == "p2:library")],
            to={"player": "p2", "zone": "battlefield"})
    to_turn_of(s, "p2")
    attack_as(s, "p2", [card_named(s, "Grizzly Bears", "p2")], defender)
    for _ in range(10):  # (the trigger resolves, then Bob is asked)
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s


def test_kazuul_makes_an_ogre_unless_the_attackers_controller_pays(cards):
    s = kazuul_attack(cards, "p1")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and sorted(o.id for o in d.options) == ["decline", "pay"], d
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["decline"])
    settle(s)
    assert len(ogres(s)) == 1
    check(s)


def test_kazuul_makes_nothing_when_the_attacker_pays(cards):
    s = kazuul_attack(cards, "p1")
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert ogres(s) == []
    assert sum(1 for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:battlefield" and c.tapped) == 3
    check(s)


def test_kazuul_does_not_trigger_for_creatures_attacking_another_player(cards):
    s = kazuul_attack(cards, "p3", players=3)
    assert not s.state.zones.get("stack") and (s.state.rules.decision is None or s.state.rules.decision.kind != "optional_payment")
    settle(s)
    assert ogres(s) == []
    check(s)


# -- Selvala -------------------------------------------------------------------------------------------------------------------------------------
def library(s, pid):
    return len(s.state.zones[f"{pid}:library"])


def cast_creature(s, pid, name):
    """``pid`` casts the creature in their own first main phase (a card put onto the battlefield by hand triggers nothing); the cards each player drew."""
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    before = {p: library(s, p) for p in ("p1", "p2")}
    mana(s, pid, R=1, G=1, C=3)
    act(s, pid, type="cast_spell", card_id=c.id)
    settle(s)
    return {p: before[p] - library(s, p) for p in ("p1", "p2")}


@pytest.mark.parametrize(("who", "creature", "draws"), [("p1", "Hill Giant", "p1"), ("p2", "Hill Giant", "p2"), ("p1", "Grizzly Bears", None), ("p2", "Grizzly Bears", None)])
def test_selvala_lets_the_controller_of_a_creature_with_the_greatest_power_draw(cards, who, creature, draws):
    """Selvala is a 2/3: a 3/3 is strictly greater than every other creature's power, so its controller (not Selvala's) may draw; a 2/2 ties with her
    (ruling of 2016-08-23: the same or higher power, no one draws)."""
    s = table(cards, ["Selvala, Heart of the Wilds", "Hill Giant", "Grizzly Bears"], ["Hill Giant", "Grizzly Bears"])
    put(s, "Selvala, Heart of the Wilds")
    if who == "p2":
        to_turn_of(s, "p2")
    assert cast_creature(s, who, creature) == {p: int(p == draws) for p in ("p1", "p2")}
    check(s)


def test_selvala_compares_with_a_bigger_creature_on_the_battlefield(cards):
    s = table(cards, ["Selvala, Heart of the Wilds", "Hill Giant"], ["Hill Giant"])
    put(s, "Selvala, Heart of the Wilds")
    put(s, "Hill Giant", "p2")
    assert cast_creature(s, "p1", "Hill Giant") == {"p1": 0, "p2": 0}  # (a 3/3 ties with Bob's 3/3)
    check(s)


# -- Rayne ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("enchanted", "bolter", "draws"), [(False, "p2", 1), (True, "p2", 2), (True, "p1", 0)])
def test_rayne_draws_a_card_and_another_one_when_enchanted(cards, enchanted, bolter, draws):
    """Rayne: Bob's Lightning Bolt targets Alice's Grizzly Bears: she may draw a card, and (ruling of 2004-10-04: checked as the ability resolves) one more if
    Rayne is enchanted. Her own Bolt on her own creature is no opponent's spell."""
    s = table(cards, ["Rayne, Academy Chancellor", "Grizzly Bears", "Pacifism", "Lightning Bolt"], ["Lightning Bolt"])
    put(s, "Rayne, Academy Chancellor")
    bears = put(s, "Grizzly Bears")
    if enchanted:
        pacifism = card_named(s, "Pacifism")
        act(s, "p1", type="move", card_ids=[pacifism.id], to={"zone": "hand"})
        mana(s, "p1", W=1, C=1)
        act(s, "p1", type="cast_spell", card_id=pacifism.id, targets=[card_named(s, "Rayne, Academy Chancellor").id])
        settle(s)
    if bolter == "p2":
        to_turn_of(s, "p2")
    bolt = card_named(s, "Lightning Bolt", bolter)
    act(s, bolter, type="move", card_ids=[bolt.id], to={"zone": "hand"})
    before = library(s, "p1")
    mana(s, bolter, R=1)
    act(s, bolter, type="cast_spell", card_id=bolt.id, targets=[bears.id])
    settle(s)
    assert before - library(s, "p1") == draws
    check(s)
