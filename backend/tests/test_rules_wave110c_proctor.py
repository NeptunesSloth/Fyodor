"""Wave 110C: Strict Proctor: a permanent entering causes a triggered ability to trigger (603.2), so each Proctor triggers for it; the controller orders both
(603.3b): Proctor's ability above the other counters it unless its controller pays {2} (701.6a, 118.12); below it, there is nothing left to counter."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110c_kit import cast, check, life, make_db, mana, put, real

PROCTOR = "Flying\nWhenever a permanent entering causes a triggered ability to trigger, counter that ability unless its controller pays {2}."
EXTRA = [real("Strict Proctor", "{1}{W}", 2, "Creature — Spirit Cleric", PROCTOR, ("1", "3"), "W"),
         real("Lifelinker", "{1}", 1, "Creature — Human", "When this creature enters, you gain 3 life.", ("1", "1"), "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Strict Proctor")).level == "FULL"


def settle_asking(s, order=None, pay=None):
    """Resolve everything: the order decision picks ``order`` (ids by name), the Proctor payment ``pay`` ("pay" / "decline")."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            if d.kind == "order":
                names = {o.id: o.label for o in d.options}
                ids = sorted(names, key=lambda i: order.index(names[i]))
            else:
                ids = [pay]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.rules.stack:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def enter(cards, order, pay, extra_mana=0):
    s = build(cards, ["Strict Proctor", "Lifelinker"])
    put(s, "Strict Proctor")
    mana(s, C=1 + extra_mana)
    cast(s, "Lifelinker")
    settle_asking(s, order, pay)
    return s


@pytest.mark.parametrize("pay,gained", [("decline", 0), ("pay", 3)])
def test_proctor_above_counters_unless_paid(cards, pay, gained):
    s = enter(cards, ["Lifelinker", "Strict Proctor"], pay, extra_mana=2)  # (first picked goes on the stack first, resolves last)
    assert life(s, "p1") == 40 + gained
    check(s)


def test_proctor_below_finds_nothing(cards):
    s = enter(cards, ["Strict Proctor", "Lifelinker"], "decline", extra_mana=2)
    assert life(s, "p1") == 43
    check(s)
