"""Wave 110A: 701.20e look at a hand, 110.2 / 508.4 Zara, Renegade Recruiter puts a creature from the defending player's hand onto the battlefield under
its controller's control tapped and attacking, and returns it to its owner's hand at the next end step."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import attack, to_phase
from tests.wave110c_kit import answer, build, card_named, check, life, make_db, put, real, to_hand

EXTRA = [
    real("Zara, Renegade Recruiter", "{3}{U}{B}", 5, "Legendary Creature — Dragon", "Flying\nWhenever Zara attacks, look at defending player's hand. You may put a "
         "creature card from it onto the battlefield under your control tapped and attacking that player or a planeswalker they control. Return that creature to its "
         "owner's hand at the beginning of the next end step.", ("4", "4"), "UB"),
    real("Bear110", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Wall110", "{1}", 1, "Creature — Wall", "", ("0", "4"), ""),
    real("Spell110", "{R}", 1, "Instant", "You gain 1 life.", None, "R"),
]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Zara, Renegade Recruiter")).level == "FULL"


def _attack(cards, pick):
    s = build(cards, ["Zara, Renegade Recruiter"], ["Bear110", "Wall110", "Spell110"])
    zara = put(s, "Zara, Renegade Recruiter")
    s.state.rules.controlled_since[zara.id].turn = 0
    bear, spell = to_hand(s, "Bear110", "p2"), to_hand(s, "Spell110", "p2")
    to_phase(s, "declare_attackers", 3)
    attack(s, (zara, "p2"))
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and bear.id in {o.id for o in d.options} and spell.id not in {o.id for o in d.options}  # (creature cards only)
    answer(s, [bear.id] if pick else [])
    return s, zara, bear, spell


def test_creature_enters_under_your_control_tapped_and_attacking(cards):
    s, zara, bear, spell = _attack(cards, True)
    c = s.state.cards[bear.id]
    assert c.zone == "p1:battlefield" and c.controller == "p1" and c.owner == "p2" and c.tapped
    assert life(s, "p2") == 40 - 4 - 2  # (Zara's 4 and the Bear's 2: it attacked Bob)
    assert s.state.cards[spell.id].zone == "p2:hand"
    check(s)


def test_returns_to_owners_hand_at_next_end_step(cards):
    s, zara, bear, spell = _attack(cards, True)
    assert s.state.cards[bear.id].zone == "p1:battlefield"  # (still there after combat)
    for _ in range(4):
        act(s, s.state.rules.priority, type="pass_priority")
        if s.state.turn.number == 4:
            break
    assert s.state.cards[bear.id].zone == "p2:hand"


def test_may_decline(cards):
    s, zara, bear, spell = _attack(cards, False)
    assert s.state.cards[bear.id].zone == "p2:hand" and card_named(s, "Zara, Renegade Recruiter").zone == "p1:battlefield"

