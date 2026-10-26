"""Wave 110A: 611.2c / 603.2 Hellish Rebuke: opposing permanents gain a trigger bound to the caster until end of turn."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import answer, card_db, cast  # noqa: F401
from tests.test_rules_bandmate_references import wait_priority
from tests.wave9c_kit import build, check, life, mana, put, to_hand

EXTRA = [
    real("Hellish Rebuke", "{R}", 1, "Instant", "Until end of turn, permanents your opponents control gain \"When this permanent deals damage to the player who cast "
         "Hellish Rebuke, sacrifice this permanent. You lose 2 life.\"", None, "R"),
    real("Pinger110", "{1}", 1, "Creature — Wizard", "{T}: Pinger110 deals 1 damage to any target.", ("1", "1"), ""),
    real("Bear110", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]
_BASE.extend(EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Hellish Rebuke")).level == "FULL"


def _ping(cards, victim, rebuke=True):
    s = build(cards, ["Hellish Rebuke", "Bear110"], ["Pinger110"])
    pinger, bear = put(s, "Pinger110", "p2"), put(s, "Bear110")
    wait_priority(s, "p2")  # (p2's turn: the ping goes on the stack and p1, holding the spell, responds to it)
    mana(s, R=1)
    spell = to_hand(s, "Hellish Rebuke")
    act(s, "p2", type="activate_ability", card_id=pinger.id, ability=0, targets=[{"p1": "p1", "bear": bear.id}[victim]])
    if rebuke:
        act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    return s, pinger


def test_damage_to_caster_sacrifices_and_costs_its_controller_2(cards):
    s, pinger = _ping(cards, "p1")
    assert s.state.cards[pinger.id].zone == "p2:graveyard" and life(s, "p2") == 38 and life(s, "p1") == 39
    check(s)


def test_damage_to_a_creature_does_nothing(cards):
    s, pinger = _ping(cards, "bear")
    assert s.state.cards[pinger.id].zone == "p2:battlefield" and life(s, "p2") == 40


def test_without_the_spell_nothing_happens(cards):
    s, pinger = _ping(cards, "p1", rebuke=False)
    assert s.state.cards[pinger.id].zone == "p2:battlefield" and life(s, "p2") == 40


