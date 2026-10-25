"""Wave 110C: Tilonalli's Summoner (603.1 attack trigger, pay {X}{R}; 603.7 delayed exile of the tokens unless the controller has the city's blessing, 702.131)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import pick, until_asked
from tests.test_rules_wave30p_combat import attack, to_phase
from tests.wave110c_kit import answer, build, check, make_db, mana, put, real

EXTRA = [real("Tilonalli's Summoner", "{1}{R}", 2, "Creature — Goblin Shaman",
              "Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.)\nWhenever this creature attacks, you may pay {X}{R}. "
              "If you do, create X 1/1 red Elemental creature tokens that are tapped and attacking. At the beginning of the next end step, exile those tokens unless "
              "you have the city's blessing.", ("1", "1"), "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Tilonalli's Summoner")).level == "FULL"


def _attack_and_pay(cards, blessing=False):
    s = build(cards, ["Tilonalli's Summoner", "Forest"])
    summoner = put(s, "Tilonalli's Summoner")
    if blessing:
        act(s, "p1", type="city_blessing", player="p1")
    to_phase(s, "declare_attackers", 3)
    mana(s, "p1", R=3)
    attack(s, (summoner, "p2"))
    return s


def _tokens(s):
    return [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Elemental"]


@pytest.mark.parametrize("blessing", [False, True])
def test_tokens_exiled_unless_blessing(cards, blessing):
    s = _attack_and_pay(cards, blessing)
    until_asked(s)
    pick(s, "x:2")
    answer(s)
    assert len(_tokens(s)) == 2
    to_phase(s, "main1", 4)  # (the end step passes without stopping)
    assert len(_tokens(s)) == (2 if blessing else 0)
    check(s)
