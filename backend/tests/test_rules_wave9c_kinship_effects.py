"""Wave 9C: what each kinship card does once its top card is revealed (the look and reveal themselves are covered by
test_rules_wave9c_kinship.py), researched against CR 2026-09-25.

* 207.2c: "Kinship" is an ability word with no rules meaning; the "If you do" instructions happen only when the card was
  revealed (the Changeling on top shares a creature type with any creature, 205.3m / 702.73a).
* 701.20a: revealing leaves the card on top of the library (701.20b).

Every scenario uses real Oracle text and checks the replay and a save and a load.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_wave5i_top_escape import answer, move
from tests.test_rules_wave9c_kinship import finish, setup, to_upkeep
from tests.wave9c_kit import card_named, check, life, pt

KINSHIP = ("Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature "
           "type with this creature, you may reveal it. If you do, ")


def kin(name, number, cost, cmc, type_line, tail, colors, power, toughness):
    return card(name, set_code="wj", number=number, mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=KINSHIP + tail,
                colors=colors, color_identity=colors, keywords=["Kinship"], power=power, toughness=toughness)


def filler(name, number, cost, type_line, text="", colors=(), power=None, toughness=None):
    extra = {"power": power, "toughness": toughness} if power else {}
    return card(name, set_code="wj", number=number, mana_cost=cost, cmc=1.0, type_line=type_line, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=[], **extra)


EXTRA = [
    kin("Ink Dissolver", "A01", "{3}{U}", 4.0, "Creature — Merfolk Wizard", "each opponent mills three cards.", ["U"], "3", "2"),
    kin("Kithkin Zephyrnaut", "A02", "{4}{W}", 5.0, "Creature — Kithkin Soldier",
        "this creature gets +2/+2 and gains flying and vigilance until end of turn.", ["W"], "2", "2"),
    kin("Mudbutton Clanger", "A03", "{1}{R}", 2.0, "Creature — Goblin Warrior", "this creature gets +1/+1 until end of turn.",
        ["R"], "1", "1"),
    kin("Nightshade Schemers", "A04", "{4}{B}", 5.0, "Creature — Faerie Wizard", "each opponent loses 2 life.", ["B"], "2", "4"),
    kin("Waterspout Weavers", "A05", "{3}{U}", 4.0, "Creature — Merfolk Wizard",
        "each creature you control gains flying until end of turn.", ["U"], "3", "3"),
    kin("Pyroclast Consul", "A06", "{3}{R}{R}", 5.0, "Creature — Elemental Shaman", "this creature deals 2 damage to each creature.",
        ["R"], "5", "5"),
    kin("Squeaking Pie Grubfellows", "A07", "{3}{B}", 4.0, "Creature — Goblin Shaman", "each opponent discards a card.", ["B"],
        "3", "2"),
    kin("Winnower Patrol", "A08", "{2}{G}", 3.0, "Creature — Elf Warrior", "put a +1/+1 counter on this creature.", ["G"], "2", "2"),
    kin("Sensation Gorger", "A09", "{1}{R}{R}", 3.0, "Creature — Goblin Shaman", "each player discards their hand, then draws four cards.",
        ["R"], "3", "3"),
    filler("Elf Scout", "B01", "{G}", "Creature — Elf Scout", colors="G", power="1", toughness="1"),
    filler("Goblin Raider", "B02", "{R}", "Creature — Goblin Warrior", colors="R", power="1", toughness="1"),
    filler("Shifty Changeling", "B03", "{1}{G}", "Creature — Shapeshifter", "Changeling (This card is every creature type.)",
           "G", "1", "1"),
    filler("Plain Idol", "B04", "{2}", "Artifact"),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def revealed_upkeep(cards, name):
    s = setup(cards, name, "Shifty Changeling")
    top = move(s, "Shifty Changeling", "library", "top")
    to_upkeep(s)
    s.opp_library = len(s.state.zones["p2:library"])  # (the mill may happen as the answer is given)
    answer(s, ["look"])
    answer(s, [top.id])
    return s, top


def kws(s, name):
    return {k.lower() for k in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name).id]).keywords}


def test_the_text_of_every_card_here_matches_the_oracle_template():
    for c in EXTRA:
        if "Kinship" in c["oracle_text"]:
            assert c["oracle_text"].startswith(KINSHIP)


def test_ink_dissolver_mills_each_opponent(cards):
    s, _ = revealed_upkeep(cards, "Ink Dissolver")
    finish(s)
    assert len(s.state.zones["p2:library"]) == s.opp_library - 3
    check(s)


def test_kithkin_zephyrnaut_pumps_and_gains_flying_and_vigilance(cards):
    s, _ = revealed_upkeep(cards, "Kithkin Zephyrnaut")
    finish(s)
    assert pt(s, "Kithkin Zephyrnaut") == (4, 4) and {"flying", "vigilance"} <= kws(s, "Kithkin Zephyrnaut")
    check(s)


def test_mudbutton_clanger_gets_plus_one(cards):
    s, _ = revealed_upkeep(cards, "Mudbutton Clanger")
    finish(s)
    assert pt(s, "Mudbutton Clanger") == (2, 2)
    check(s)


def test_nightshade_schemers_drains_each_opponent(cards):
    s, _ = revealed_upkeep(cards, "Nightshade Schemers")
    finish(s)
    assert life(s, "p2") == 38
    check(s)


def test_waterspout_weavers_gives_each_creature_you_control_flying(cards):
    s = setup(cards, "Waterspout Weavers", "Shifty Changeling")
    move(s, "Elf Scout", "battlefield")
    top = move(s, "Shifty Changeling", "library", "top")
    to_upkeep(s)
    answer(s, ["look"])
    answer(s, [top.id])
    finish(s)
    assert "flying" in kws(s, "Elf Scout") and "flying" in kws(s, "Waterspout Weavers")
    check(s)


def test_pyroclast_consul_deals_two_to_each_creature(cards):
    s = setup(cards, "Pyroclast Consul", "Shifty Changeling")
    move(s, "Elf Scout", "battlefield")
    top = move(s, "Shifty Changeling", "library", "top")
    to_upkeep(s)
    answer(s, ["look"])
    answer(s, [top.id])
    finish(s)
    assert s.state.cards[card_named(s, "Elf Scout").id].zone == "p1:graveyard"
    assert s.state.cards[card_named(s, "Pyroclast Consul").id].damage == 2
    check(s)


def test_squeaking_pie_grubfellows_makes_each_opponent_discard(cards):
    s = setup(cards, "Squeaking Pie Grubfellows", "Shifty Changeling")
    move(s, "Island", "hand", pid="p2")
    top = move(s, "Shifty Changeling", "library", "top")
    to_upkeep(s)
    hand, graveyard = len(s.state.zones["p2:hand"]), len(s.state.zones["p2:graveyard"])
    answer(s, ["look"])
    answer(s, [top.id])
    finish(s)
    assert len(s.state.zones["p2:hand"]) == hand - 1 and len(s.state.zones["p2:graveyard"]) == graveyard + 1
    check(s)


def test_winnower_patrol_gets_a_counter(cards):
    s, _ = revealed_upkeep(cards, "Winnower Patrol")
    finish(s)
    assert s.state.cards[card_named(s, "Winnower Patrol").id].counters.get("+1/+1") == 1
    check(s)


def test_sensation_gorger_refills_each_hand_to_four(cards):
    s = setup(cards, "Sensation Gorger", "Shifty Changeling")
    move(s, "Island", "hand", pid="p2")
    top = move(s, "Shifty Changeling", "library", "top")
    to_upkeep(s)
    answer(s, ["look"])
    answer(s, [top.id])
    finish(s)
    # (Alice then takes her draw step's card: four from the Gorger, one more from the step)
    assert len(s.state.zones["p1:hand"]) == 5 and len(s.state.zones["p2:hand"]) == 4
    check(s)


def test_nothing_happens_when_the_card_is_not_revealed(cards):
    s = setup(cards, "Nightshade Schemers", "Shifty Changeling")
    move(s, "Shifty Changeling", "library", "top")
    to_upkeep(s)
    answer(s, ["look"])
    answer(s, [])
    finish(s)
    assert life(s, "p2") == 40 and "Shifty Changeling" not in json.dumps(s.view("p2")["log"])  # (not revealed)
    check(s)
