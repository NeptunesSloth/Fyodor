"""Wave 11F: outlaws (700.12) - an object with the Assassin, Mercenary, Pirate, Rogue and/or Warlock creature types.
Real Oracle text; replay and save/load round trip."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import life, settle
from tests.test_rules_wave11f_events import real, roundtrip
from tests.wave9c_kit import build, cast, mana, pt, put, to_hand

EXTRA = [
    real("Mine Raider", "{2}{R}", 3, "Creature — Human Rogue",
         "Trample\nWhen this creature enters, if you control another outlaw, create a Treasure token. (Assassins, Mercenaries, "
         "Pirates, Rogues, and Warlocks are outlaws. A Treasure token is an artifact with \"{T}, Sacrifice this token: Add one "
         "mana of any color.\")", ("3", "2"), "R"),
    real("Rakish Crew", "{2}{B}", 3, "Enchantment",
         "When this enchantment enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets "
         "+1/+0 until end of turn. Activate only as a sorcery.\"\nWhenever an outlaw you control dies, each opponent loses 1 life "
         "and you gain 1 life. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)", None, "B"),
    real("Take the Fall", "{U}", 1, "Instant",
         "Target creature gets -1/-0 until end of turn. It gets -4/-0 until end of turn instead if you control an outlaw. "
         "(Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nDraw a card.", None, "U"),
    real("Hellspur Posse Boss", "{2}{R}{R}", 4, "Creature — Lizard Rogue",
         "Other outlaws you control have haste. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nWhen this "
         "creature enters, create two 1/1 red Mercenary creature tokens with \"{T}: Target creature you control gets +1/+0 until "
         "end of turn. Activate only as a sorcery.\"", ("2", "4"), "R"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c.name if hasattr(c, "name") else c["name"] for c in EXTRA])
def test_outlaw_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def cast_raider(s):
    to_hand(s, "Mine Raider")
    mana(s, R=1, C=2)
    cast(s, "Mine Raider")


def treasures(s):
    return [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]


def test_another_outlaw_you_control_not_the_creature_itself(cards):
    s = build(cards, ("Mine Raider",))
    cast_raider(s)  # a Rogue itself, but "another outlaw" leaves it out
    assert not treasures(s)
    roundtrip(s)


def test_another_outlaw_you_control_makes_the_treasure(cards):
    s = build(cards, ("Mine Raider", "Merfolk Looter"))  # a Merfolk Rogue is an outlaw
    put(s, "Merfolk Looter")
    cast_raider(s)
    assert len(treasures(s)) == 1
    roundtrip(s)


def test_a_creature_that_is_no_outlaw_does_not_count(cards):
    s = build(cards, ("Mine Raider", "Grizzly Bears"))
    put(s, "Grizzly Bears")
    cast_raider(s)
    assert not treasures(s)
    roundtrip(s)


def test_whenever_an_outlaw_you_control_dies(cards):
    s = build(cards, ("Rakish Crew", "Merfolk Looter", "Grizzly Bears", "Lightning Bolt"))
    put(s, "Rakish Crew")
    settle(s)
    looter, bears = put(s, "Merfolk Looter"), put(s, "Grizzly Bears")
    for victim in (bears, looter):
        spell = to_hand(s, "Lightning Bolt")
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
        settle(s)
        if victim is bears:
            assert (life(s, "p1"), life(s, "p2")) == (40, 40)  # a Bear is no outlaw
    assert (life(s, "p1"), life(s, "p2")) == (41, 39)
    roundtrip(s)


def test_if_you_control_an_outlaw_the_spell_does_more(cards):
    s = build(cards, ("Take the Fall", "Merfolk Looter", "Grizzly Bears"))
    put(s, "Merfolk Looter")
    bears = put(s, "Grizzly Bears")
    spell = to_hand(s, "Take the Fall")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id])
    settle(s)
    assert pt(s, "Grizzly Bears")[0] == -2  # 2 - 4: the "instead" form
    roundtrip(s)


def test_without_an_outlaw_the_spell_does_less(cards):
    s = build(cards, ("Take the Fall", "Grizzly Bears"))
    bears = put(s, "Grizzly Bears")
    spell = to_hand(s, "Take the Fall")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id])
    settle(s)
    assert pt(s, "Grizzly Bears")[0] == 1  # 2 - 1
    roundtrip(s)
