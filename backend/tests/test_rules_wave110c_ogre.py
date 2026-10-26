"""Wave 110C: Ogre Battlecaster. 608.2g / 118.9d (cast from the graveyard as the ability resolves, paying {R}{R} in addition to its other costs), 614.1 (exiled
instead of going to the graveyard), 603.7c (the reflexive "when you cast that spell" pump: +X/+0 with X the spell's mana value)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import pt
from tests.wave110c_kit import answer, build, card_named, check, life, make_db, mana, put, real, zone

OGRE = ("First strike\nWhenever this creature attacks, you may cast target instant or sorcery card from your graveyard by paying {R}{R} in addition to its "
        "other costs. If that spell would be put into a graveyard, exile it instead. When you cast that spell, this creature gets +X/+0 until end of turn, "
        "where X is that spell's mana value.")
EXTRA = [real("Ogre Battlecaster", "{3}{R}", 4, "Creature — Ogre Wizard", OGRE, ("3", "3"), "R"),
         real("Test Bolt", "{R}", 1, "Instant", "Test Bolt deals 3 damage to target player.", None, "R"),
         real("Test Big Burn", "{2}{R}{R}", 4, "Sorcery", "Test Big Burn deals 4 damage to target player.", None, "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Ogre Battlecaster")).level == "FULL"


def attack(cards, spell, red):
    s = build(cards, ["Ogre Battlecaster", spell])
    ogre = put(s, "Ogre Battlecaster")
    sp = put(s, spell)
    act(s, "p1", type="move", card_ids=[sp.id], to={"player": "p1", "zone": "graveyard"})
    to_phase(s, "declare_attackers", 3)
    mana(s, **red)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p2"}])
    return s, ogre, sp


def test_cast_from_graveyard_pays_extra_rr_exiles_and_pumps(cards):
    s, ogre, bolt = attack(cards, "Test Bolt", {"R": 3})  # {R} + the extra {R}{R}
    answer(s, bolt.id, bolt.id, "p2")
    assert life(s, "p2") == 33  # 3 from the Bolt, then 4 from the pumped Ogre in combat
    assert zone(s, bolt) == "p1:exile"
    assert pt(s, "Ogre Battlecaster") == (4, 3)  # X = mana value 1
    check(s)


def test_pump_is_the_spells_mana_value(cards):
    s, ogre, burn = attack(cards, "Test Big Burn", {"R": 6})
    answer(s, burn.id, burn.id, "p2")
    assert life(s, "p2") == 29 and pt(s, "Ogre Battlecaster") == (7, 3)  # 4 burn, then 7 combat damage


def test_without_the_extra_mana_it_cant_be_cast(cards):
    s, ogre, bolt = attack(cards, "Test Bolt", {"R": 2})  # {R}{R}: enough for the extra but not for the Bolt itself
    with pytest.raises(ActionError):
        answer(s, bolt.id, bolt.id, "p2")
    assert life(s, "p2") == 40 and zone(s, bolt) == "p1:graveyard"
