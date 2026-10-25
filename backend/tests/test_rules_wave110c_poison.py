"""Wave 110C corrupted counter: Bring the Ending (counter unless its controller pays {2}; countered outright if that controller has three or more poison counters, 207.2c, 122.1f, 608.2c)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real, to_hand, zone

EXTRA = [real("Bring the Ending", "{1}{W}{U}", 3, "Instant",
              "Counter target spell unless its controller pays {2}.\nCorrupted — Counter that spell instead if its controller has three or more poison counters.", None, "WU")]

OOZE = real("Printlifter Ooze", "{2}{G}", 3, "Creature — Ooze", "Deathtouch\nWhenever this creature or another creature you control is turned face up, create a 0/0 green Ooze creature token with trample. "
            "The token enters with X +1/+1 counters on it, where X is the number of other creatures you control.\nDisguise {3}{G}", ("2", "2"), "G")
EXTRA.append(OOZE)


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Bring the Ending")).level == "FULL"


@pytest.mark.parametrize("poison,dest", [(0, "p1:battlefield"), (2, "p1:battlefield"), (3, "p1:graveyard")])
def test_bring_the_ending(cards, poison, dest):
    s = build(cards, ["Grizzly Bears"], ["Bring the Ending"])
    act(s, "p1", type="resource", player="p1", key="poison", delta=poison)
    mana(s, "p1", G=1, C=3)
    mana(s, "p2", W=1, U=1, C=1)
    spell = to_hand(s, "Bring the Ending", "p2")
    victim = cast(s, "Grizzly Bears")
    act(s, "p2", type="cast_spell", card_id=spell.id, targets=[victim.id])
    answer(s, "pay")
    assert zone(s, victim) == dest
    check(s)


def test_printlifter_ooze_counts_creatures_without_the_new_token(cards):
    """614.1c: the token enters with the counters, so it is not one of the other creatures counted (here: Grizzly Bears alone)."""
    s = build(cards, ["Printlifter Ooze", "Grizzly Bears"], forests=40)
    assert coverage.of_card_data(cards.resolve("Printlifter Ooze")).level == "FULL"
    put(s, "Grizzly Bears")
    ooze = to_hand(s, "Printlifter Ooze")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=ooze.id, face_down=True)
    answer(s)
    mana(s, G=1, C=3)
    act(s, "p1", type="turn_face_up", card_id=ooze.id)
    answer(s)
    toks = [c for c in s.state.cards.values() if c.name == "Ooze" and c.zone == "p1:battlefield"]
    assert len(toks) == 1 and toks[0].counters.get("+1/+1") == 1
    check(s)
