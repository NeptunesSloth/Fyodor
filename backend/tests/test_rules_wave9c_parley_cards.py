"""Wave 9C: the other parley cards (Selvala's Charge, Selvala, Explorer Returned, Storm Fleet Negotiator, Cutthroat
Negotiator, Woodvine Elemental); the reveal-count machinery itself is covered by test_rules_wave9c_parley.py. Researched
against CR 2026-09-25.

* 701.20a/b: each player reveals the top card of their library; it stays there and the draw that follows takes it.
* 608.2c: the instruction after "for each nonland card" is carried out once per nonland card revealed.
* 605.1a: Selvala's ability draws cards, so it is not a mana ability: it uses the stack, and its {G} is added as it resolves.
* 207.2c: "Parley" is an ability word with no rules meaning.

Every scenario uses real Oracle text and checks the replay and a save and a load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave5i_top_escape import move
from tests.wave9c_kit import build, card_named, cast, check, life, mana, pt, put, to_hand


def make(name, number, cost, cmc, type_line, text, colors, keywords, power=None, toughness=None):
    extra = {"power": power, "toughness": toughness} if power else {}
    return card(name, set_code="wq", number=number, mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=text,
                colors=colors, color_identity=colors, keywords=keywords, **extra)


EXTRA = [
    make("Selvala's Charge", "A01", "{4}{G}", 5.0, "Sorcery", "Parley — Each player reveals the top card of their library. For each nonland card revealed this way, you create a 3/3 green Elephant creature token. Then each player draws a card.", ["G"], ["Parley"]),  # noqa: E501
    make("Selvala, Explorer Returned", "A02", "{1}{G}{W}", 3.0, "Legendary Creature — Elf Scout", "Parley — {T}: Each player reveals the top card of their library. For each nonland card revealed this way, add {G} and you gain 1 life. Then each player draws a card. (Activate only as an instant.)", ["G", "W"], ["Parley"], "2", "4"),  # noqa: E501
    make("Storm Fleet Negotiator", "A03", "{2}{U}", 3.0, "Creature — Siren Pirate", 'Flying\nParley — Whenever this creature attacks, each player reveals the top card of their library. For each nonland card revealed this way, you create a Map token. Then each player draws a card. (A Map token is an artifact with "{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.")', ["U"], ["Flying", "Explore", "Parley"], "2", "2"),  # noqa: E501
    make("Cutthroat Negotiator", "A04", "{2}{U}{R}", 4.0, "Creature — Orc Pirate", "Parley — Whenever this creature attacks, each player reveals the top card of their library. For each nonland card revealed this way, you create a tapped Treasure token. Then each player draws a card.", ["R", "U"], ["Treasure", "Parley"], "4", "3"),  # noqa: E501
    make("Woodvine Elemental", "A05", "{4}{G}{W}", 6.0, "Creature — Elemental", "Trample\nParley — Whenever this creature attacks, each player reveals the top card of their library. For each nonland card revealed this way, attacking creatures you control get +1/+1 until end of turn. Then each player draws a card.", ["G", "W"], ["Trample", "Parley"], "4", "4"),  # noqa: E501
    make("Plain Idol", "B01", "{2}", 2.0, "Artifact", "", [], []),
    make("Second Idol", "B02", "{2}", 2.0, "Artifact", "", [], []),
]
FULL = [c["name"] for c in EXTRA[:5]]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def named(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith("battlefield")]


def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            assert coverage.of_characteristics(characteristics(c["name"], c["type_line"], c["oracle_text"])).level == "FULL"


def test_selvala_s_charge_makes_an_elephant_for_each_nonland_card(cards):
    s = build(cards, ("Selvala's Charge", "Plain Idol"), ("Second Idol",))
    to_hand(s, "Selvala's Charge")
    move(s, "Plain Idol", "library", "top")
    move(s, "Second Idol", "library", "top", pid="p2")
    mana(s, G=5)
    cast(s, "Selvala's Charge")
    elephants = [c for c in s.state.cards.values() if c.name == "Elephant" and c.is_token]
    assert len(elephants) == 2 and all(pt(s, "Elephant") == (3, 3) for _ in elephants)
    check(s)


def test_selvala_explorer_returned_adds_green_and_gains_life_per_nonland(cards):
    from tests.game_helpers import turn_on
    from tests.test_rules_conditionals import sandbox

    s = sandbox(cards, "Selvala, Explorer Returned", "Plain Idol", p2=("Second Idol",))
    selvala = put(s, "Selvala, Explorer Returned")
    move(s, "Plain Idol", "library", "top")
    move(s, "Second Idol", "library", "top", pid="p2")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    before = life(s)
    act(s, "p1", type="activate_ability", card_id=selvala.id, ability=0)
    for _ in range(10):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p1"].mana.get("G") == 2 and life(s) == before + 2
    assert card_named(s, "Plain Idol").zone == "p1:hand" and card_named(s, "Second Idol", "p2").zone == "p2:hand"
    check(s)


def attack_with(cards, mine, tops):
    from tests.game_helpers import turn_on
    from tests.test_rules_conditionals import attack, sandbox

    s = sandbox(cards, *mine[:1], "Plain Idol", p2=("Second Idol",))
    put(s, mine[0])
    for name, pid in tops:
        move(s, name, "library", "top", pid=pid)
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    attack(s, (card_named(s, mine[0]), "p2"))
    for _ in range(10):
        if not s.state.zones.get("stack") and s.state.rules.decision is None:
            break
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s


def test_storm_fleet_negotiator_makes_a_map_for_each_nonland_card(cards):
    s = attack_with(cards, ["Storm Fleet Negotiator"], [("Plain Idol", "p1"), ("Second Idol", "p2")])
    assert len(named(s, "Map")) == 2
    check(s)


def test_cutthroat_negotiator_makes_tapped_treasures(cards):
    s = attack_with(cards, ["Cutthroat Negotiator"], [("Plain Idol", "p1"), ("Forest", "p2")])
    treasures = named(s, "Treasure")
    assert len(treasures) == 1 and treasures[0].tapped  # (Bob revealed a land)
    check(s)


def test_woodvine_elemental_pumps_the_attackers_once_per_nonland_card(cards):
    s = attack_with(cards, ["Woodvine Elemental"], [("Plain Idol", "p1"), ("Second Idol", "p2")])
    assert pt(s, "Woodvine Elemental") == (6, 6)
    check(s)


def test_woodvine_elemental_with_two_lands_revealed_pumps_nothing(cards):
    s = attack_with(cards, ["Woodvine Elemental"], [("Forest", "p1"), ("Forest", "p2")])
    assert pt(s, "Woodvine Elemental") == (4, 4)
    check(s)
