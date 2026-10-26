"""Wave 110C: Voltaic Visionary // Volt-Charged Berserker. 607.2a (linked to the creature's own exile), 603.4 (intervening "if": the played card is the object it exiled,
400.7), 701.28 (transform), 305.1 / 601.2 (playing a land / casting from exile)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import answer, build, check, life, make_db, mana, put, real
from tests.wave110d_kit import ability

FRONT = ("{T}: This creature deals 2 damage to you. Exile the top card of your library. You may play that card this turn. Activate only as a sorcery.\n"
         "When you play a card exiled with this creature, transform this creature.")
NAME = "Voltaic Visionary // Volt-Charged Berserker"
EXTRA = [card(NAME, set_code="tst", number="110C-V", layout="transform", mana_cost="{1}{R}", cmc=2.0, type_line="Creature — Human Wizard // Creature — Human Berserker",
              oracle_text="", power="3", toughness="1", colors=["R"], color_identity=["R"], keywords=["Transform"],
              card_faces=[{"name": "Voltaic Visionary", "mana_cost": "{1}{R}", "type_line": "Creature — Human Wizard", "oracle_text": FRONT, "power": "3", "toughness": "1",
                           "colors": ["R"]},
                          {"name": "Volt-Charged Berserker", "mana_cost": "", "type_line": "Creature — Human Berserker", "oracle_text": "This creature can't block.",
                           "power": "4", "toughness": "3", "colors": ["R"]}]),
         real("Test Bolt", "{R}", 1, "Instant", "Test Bolt deals 3 damage to target player.", None, "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def vv(s):
    return next(c for c in s.state.cards.values() if c.name == NAME)


def front(s):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[vv(s).id]).name


def activate(cards, top, forests=0):
    s = build(cards, [NAME, top, top], forests=forests)
    v = put(s, NAME)
    to_phase(s, "main1", 3)
    act(s, "p1", type="activate_ability", card_id=v.id, ability=ability(s, v, "{T}"))
    answer(s)
    return s, v


def test_playing_the_exiled_card_transforms_it(cards):
    s, v = activate(cards, "Test Bolt")
    bolt = next(c for c in s.state.cards.values() if c.zone == "p1:exile")
    assert bolt.name == "Test Bolt" and life(s, "p1") == 38
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer(s)
    assert s.state.cards[v.id].face == 1
    check(s)


def test_playing_an_exiled_land_transforms_it_too(cards):
    s = build(cards, [NAME], forests=9)
    v = put(s, NAME)
    to_phase(s, "main1", 3)
    act(s, "p1", type="activate_ability", card_id=v.id, ability=ability(s, v, "{T}"))
    answer(s)
    land = next(c for c in s.state.cards.values() if c.zone == "p1:exile")
    act(s, "p1", type="play_land", card_id=land.id)
    answer(s)
    assert s.state.cards[v.id].face == 1


def test_a_card_from_the_hand_does_not(cards):
    s, v = activate(cards, "Test Bolt", forests=3)
    assert s.state.cards[v.id].face == 0
    other = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[other.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=other.id)
    answer(s)
    assert s.state.cards[v.id].face == 0
