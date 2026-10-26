"""Wave 110D: creatures that return as Auras (Bronzehide Lion, Harold and Bob, Old-Growth Troll), real Oracle text. Every scenario checks the replay and a save and a load.

* 700.4: "dies" - to the graveyard from the battlefield; 205.1a: "It's an Aura enchantment" is no creature and has the subtype Aura only.
* 303.4f: the returned Aura enters attached to a host its controller (the owner) chooses that fits "enchant ... you control"; with none it stays in the graveyard.
* 113.6, 702.5: it has the enchant ability and the quoted ability and no others.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, mana
from tests.wave110d_kit import activate, cast_on, ch, check, cost, hand_new, now, put_new, settle, to_phase  # noqa: F401

EXTRA = [
    real("Bronzehide Lion", "{G}{W}", 2, "Creature — Cat",
         "{G}{W}: This creature gains indestructible until end of turn.\nWhen this creature dies, return it to the battlefield. It's an Aura enchantment with enchant creature you control and \"{G}{W}: Enchanted creature gains indestructible until end of turn,\" and it loses all other abilities.",
         ("3", "3"), "GW"),
    real("Old-Growth Troll", "{G}{G}{G}", 3, "Creature — Troll Warrior",
         "Trample\nWhen Old-Growth Troll dies, if it was a creature, return it to the battlefield. It's an Aura enchantment with enchant Forest you control and \"Enchanted Forest has '{T}: Add {G}{G}' and '{1}, {T}, Sacrifice this land: Create a tapped 4/4 green Troll Warrior creature token with trample.'\"",
         ("4", "4"), "G"),
    real("Harold and Bob, First Numens", "{2}{G}", 3, "Legendary Creature — Treefolk Mutant",
         "Reach, vigilance\nWhen Harold and Bob dies, if it was a creature, return it to the battlefield. It's an Aura enchantment with enchant Forest you control and \"Enchanted Forest has '{T}: Add three mana of any one color. You get two rad counters.'\" Harold and Bob loses all other abilities.",
         ("3", "3"), "G"),
]


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def die(s, c):
    cast_on(s, "Murder", c)
    settle(s)


def test_lion_returns_as_aura_on_my_creature(cards):
    s = build(cards, ["Bronzehide Lion", "Grizzly Bears", "Murder"])
    lion, bears = put_new(s, "Bronzehide Lion"), put_new(s, "Grizzly Bears")
    die(s, lion)
    c = ch(s, now(s, lion))
    assert now(s, lion).zone == "p1:battlefield" and now(s, lion).attached_to == bears.id
    assert c.types == {"Enchantment"} and c.subtypes == {"Aura"}
    assert [a.text for a in c.abilities if a.kind != "keywords"] == ["{G}{W}: Enchanted creature gains indestructible until end of turn."]
    assert [a.text for a in c.abilities if a.kind == "keywords"] == ["Enchant creature you control."]
    mana(s, "p1", G=1, W=1)
    activate(s, lion, "{G}{W}")  # the Aura's own ability: the enchanted creature, not the Aura
    assert "indestructible" in ch(s, now(s, bears)).keywords and "indestructible" not in ch(s, now(s, lion)).keywords
    check(s)


def test_no_creature_to_enchant_stays_in_graveyard(cards):
    s = build(cards, ["Bronzehide Lion", "Murder"])
    lion = put_new(s, "Bronzehide Lion")
    die(s, lion)
    assert now(s, lion).zone == "p1:graveyard"  # 303.4g
    check(s)


def test_cant_enchant_opponents_creature(cards):
    s = build(cards, ["Bronzehide Lion", "Murder"], ["Grizzly Bears"])
    lion, theirs = put_new(s, "Bronzehide Lion"), put_new(s, "Grizzly Bears", "p2")
    die(s, lion)
    assert now(s, lion).zone == "p1:graveyard" and now(s, theirs).zone == "p2:battlefield"  # "you control"
    check(s)


def test_two_hosts_asks_the_owner(cards):
    s = build(cards, ["Bronzehide Lion", "Grizzly Bears", "Grizzly Bears", "Murder"])
    lion = put_new(s, "Bronzehide Lion")
    a, b = put_new(s, "Grizzly Bears"), put_new(s, "Grizzly Bears")
    m = hand_new(s, "Murder")
    mana(s, "p1", **cost("Murder"))
    act(s, "p1", type="cast_spell", card_id=m.id, targets=[lion.id], sources=[])
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {a.id, b.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[b.id])
    settle(s)
    assert now(s, lion).attached_to == b.id
    check(s)


def test_troll_aura_gives_the_forest_its_abilities(cards):
    s = build(cards, ["Old-Growth Troll", "Murder"])
    troll, forest = put_new(s, "Old-Growth Troll"), put_new(s, "Forest")
    die(s, troll)
    c = ch(s, now(s, troll))
    assert now(s, troll).attached_to == forest.id and c.types == {"Enchantment"} and c.subtypes == {"Aura"} and not [a for a in c.abilities if a.kind == "activated"]
    assert "trample" not in c.keywords  # it loses its other abilities (Trample)
    texts = [a.text for a in ch(s, now(s, forest)).abilities]
    assert "{T}: Add {G}{G}." in texts and any(x.startswith("{1}, {T}, Sacrifice") for x in texts)
    mana(s, "p1", C=1)
    activate(s, forest, "{1}, {T}, Sacrifice")
    token = next(x for x in s.state.cards.values() if x.is_token and x.controller == "p1")
    assert now(s, forest).zone == "p1:graveyard" and ch(s, token).power == "4" and token.tapped
    assert now(s, troll).zone == "p1:graveyard"  # the Aura falls off with its Forest (704.5m)
    check(s)


def test_harold_aura_taps_forest_for_three_and_two_rad(cards):
    s = build(cards, ["Harold and Bob, First Numens", "Murder"])
    harold, forest = put_new(s, "Harold and Bob, First Numens"), put_new(s, "Forest")
    die(s, harold)
    assert now(s, harold).attached_to == forest.id and [a.text for a in ch(s, now(s, harold)).abilities if a.kind != "keywords"] == ['Enchanted land has "{T}: Add three mana of any one color. You get two rad counters.".']
    assert "reach" not in ch(s, now(s, harold)).keywords and "vigilance" not in ch(s, now(s, harold)).keywords
    activate(s, forest, "{T}: Add three mana")
    p = s.state.players["p1"]
    assert now(s, forest).tapped and len({u.sym for u in p.mana_units}) == 1 and len(p.mana_units) == 3 and p.resources["rad"] == 2  # three mana of one color, two rad counters
    check(s)
