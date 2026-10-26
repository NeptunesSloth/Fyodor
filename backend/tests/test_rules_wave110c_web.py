"""Wave 110C: Scarlet Spider, Ben Reilly: cast using web-slinging (702.188a), it enters with X +1/+1 counters, X = the returned creature's mana value (608.2h, 614.1c)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110c_kit import answer, check, make_db, mana, put, real, to_hand

SCARLET = ("Web-slinging {R}{G} (You may cast this spell for {R}{G} if you also return a tapped creature you control to its owner's hand.)\nTrample\n"
           "Sensational Save — If Scarlet Spider was cast using web-slinging, he enters with X +1/+1 counters on him, where X is the mana value of the returned creature.")
EXTRA = [real("Scarlet Spider, Ben Reilly", "{1}{R}{G}", 3, "Legendary Creature — Spider Human Hero", SCARLET, ("3", "3"), "RG"),
         real("Five Drop", "{5}", 5, "Artifact Creature — Golem", "", ("2", "2"), "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Scarlet Spider, Ben Reilly")).level == "FULL"


def cast_spider(web):
    def run(cards):
        s = build(cards, ["Scarlet Spider, Ben Reilly", "Five Drop"])
        spider = to_hand(s, "Scarlet Spider, Ben Reilly")
        drop = put(s, "Five Drop")
        if web:
            act(s, "p1", type="tap", card_ids=[drop.id], tapped=True)
            mana(s, R=1, G=1)
            act(s, "p1", type="cast_spell", card_id=spider.id, alt_cost=f"{spider.id}:0", cost_choices=[{"component": 0, "cards": [drop.id]}])
        else:
            mana(s, R=1, G=1, C=1)
            act(s, "p1", type="cast_spell", card_id=spider.id)
        answer(s)
        return s, spider
    return run


def test_web_slinging_counters_equal_returned_mana_value(cards):
    s, spider = cast_spider(True)(cards)
    c = s.state.cards[spider.id]
    assert c.zone == "p1:battlefield" and c.counters.get("+1/+1") == 5
    check(s)


def test_cast_normally_no_counters(cards):
    s, spider = cast_spider(False)(cards)
    c = s.state.cards[spider.id]
    assert c.zone == "p1:battlefield" and not c.counters.get("+1/+1")
    check(s)
