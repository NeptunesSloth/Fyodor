"""Wave 110C: Pandemonium (ruling 2006-09-25, 603.3a): Pandemonium's controller controls the trigger, but the entering creature's controller chooses the target and whether the
creature deals damage equal to its power (120.3); a creature that leaves first still deals its last-known power (ruling 2004-10-04)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110c_kit import answer, cast, check, life, make_db, mana, put, real

TEXT = "Whenever a creature enters, that creature's controller may have it deal damage equal to its power to any target of their choice."
EXTRA = [real("Pandemonium", "{3}{R}", 4, "Enchantment", TEXT, None, "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Pandemonium")).level == "FULL"


@pytest.mark.parametrize(("owner", "yes"), [("p2", True), ("p2", False), ("p1", True)])
def test_the_entering_creatures_controller_chooses_target_and_whether(cards, owner, yes):
    """p1 casts Grizzly Bears (2 power); Pandemonium is controlled by ``owner``; p1 chooses in every case."""
    s = build(cards, ["Pandemonium", "Grizzly Bears"], ["Pandemonium"])
    put(s, "Pandemonium", owner)
    mana(s, G=1, C=1)
    cast(s, "Grizzly Bears")
    for pick in ("p2", "yes" if yes else "no"):
        while s.state.zones.get("stack") and s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
        assert d is not None and d.player == "p1"  # (the creature's controller, whoever controls Pandemonium)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    answer(s)
    assert life(s, "p2") == (38 if yes else 40)
    check(s)
