"""Wave 110C core: exact wordings built from the native grammar. One docstring line per card names the rule handled."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real, zone

EXTRA = [
    real('Catastrophe', '{4}{W}{W}', 6, 'Sorcery',
         "Destroy all lands or all creatures. Creatures destroyed this way can't be regenerated.", None, 'W'),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("pick, lands_gone", [("Destroy all lands", True), ("Destroy all creatures", False)])
def test_catastrophe_destroys_the_chosen_kind(cards, pick, lands_gone):
    """Catastrophe: its controller chooses as it resolves (608.2d) and only that kind is destroyed (701.8)."""
    s = build(cards, ["Catastrophe", "Grizzly Bears", "Forest"], ["Grizzly Bears"])
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    forest = put(s, "Forest")
    mana(s, W=2, C=4)
    cast(s, "Catastrophe")
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            break
        from tests.game_helpers import act

        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and {o.label for o in d.options} == {"Destroy all lands", "Destroy all creatures"}
    answer(s, next(o.id for o in d.options if o.label == pick))
    assert (zone(s, forest) == "p1:graveyard") == lands_gone
    assert (zone(s, mine) == "p1:battlefield") == lands_gone and (zone(s, theirs) == "p2:battlefield") == lands_gone
    check(s)
