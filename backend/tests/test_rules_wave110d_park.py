"""Wave 110D: Welcome to . . . // Jurassic Park chapter I, real Oracle text (tests/fixtures/wave110d_cards.json).

* 115.1, 601.2c / 603.3d: "For each opponent, up to one target noncreature artifact they control" is one target group per opponent (three players: two).
* 205.1b, 611.2b: the artifact becomes a 0/4 Wall artifact creature with defender for as long as you control the Saga.
"""

from __future__ import annotations

from app.rules import sba
from tests.game_helpers import act
from tests.wave9c_kit import to_hand
from tests.test_rules_wave110d_three import three
from tests.wave110d_kit import card_db, ch, check, cost, full, hand_new, mana, move, now, put_new, settle  # noqa: F401

NAME = "Welcome to . . . // Jurassic Park"


def test_full():
    assert full(NAME)


def test_each_opponent_gets_a_group(cards):
    s = three(cards, [NAME], ["Sol Ring"], ["Sol Ring"])
    rock2, rock3 = put_new(s, "Sol Ring", "p2"), put_new(s, "Sol Ring", "p3")
    c = to_hand(s, NAME)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s, answers=[rock2.id, rock3.id])
    for rock in (rock2, rock3):
        x = ch(s, rock)
        assert (sba.power(now(s, rock), x), sba.toughness(now(s, rock), x)) == (0, 4) and "Wall" in x.subtypes and "Creature" in x.types and "defender" in x.keywords | x.granted
    saga = now(s, c)
    move(s, saga, "graveyard")
    act(s, s.state.rules.priority, type="pass_priority")
    assert "Creature" not in ch(s, rock2).types  # (611.2b: the Saga left)
    check(s)
