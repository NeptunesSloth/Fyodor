"""Wave 110A: 106.7 / 605.1a Squandered Resources: sacrifice a land, add one mana of any type that land could produce."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import answer, card_db  # noqa: F401
from tests.wave9c_kit import build, check, put

EXTRA = [
    real("Squandered Resources", "{2}{G}", 3, "Enchantment", "Sacrifice a land: Add one mana of any type the sacrificed land could produce.", None, "G"),
    real("Taiga110", "", 0, "Land — Mountain Forest", "({T}: Add {R} or {G}.)", None, ""),
    real("Wastes110", "", 0, "Land", "{T}: Add {C}.", None, ""),
    real("Barren110", "", 0, "Land", "", None, ""),
]
_BASE.extend(EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Squandered Resources")).level == "FULL"


def _run(cards, land, pick=None):
    s = build(cards, ["Squandered Resources", land])
    sq = put(s, "Squandered Resources")
    ld = put(s, land)
    act(s, "p1", type="activate_ability", card_id=sq.id, ability=0, **({"mana_choice": pick} if pick else {}))
    answer(s)
    return s, ld


@pytest.mark.parametrize(("land", "pick", "mana"), [("Taiga110", "G", {"G": 1}), ("Taiga110", "R", {"R": 1}), ("Wastes110", None, {"C": 1}), ("Forest", None, {"G": 1})])
def test_adds_a_type_the_land_could_produce(cards, land, pick, mana):
    from app.rules import mana_units

    s, ld = _run(cards, land, pick)
    assert s.state.cards[ld.id].zone == "p1:graveyard"
    assert dict(mana_units.visible_pool(s.state, "p1")) == mana
    check(s)


def test_taiga_cannot_add_other_type(cards):
    from app.game.errors import ActionError

    with pytest.raises(ActionError):
        _run(cards, "Taiga110", "U")


def test_land_with_no_mana_ability_adds_nothing(cards):
    from app.rules import mana_units

    s, ld = _run(cards, "Barren110")
    assert s.state.cards[ld.id].zone == "p1:graveyard" and not sum(mana_units.visible_pool(s.state, "p1").values())
