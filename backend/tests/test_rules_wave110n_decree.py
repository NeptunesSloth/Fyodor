"""Wave 110N: Thranduil's Decree (608.2c, 701.6a: only a permanent spell is exiled by it, and only that card may be cast free)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.wave110a_kit import STEPS
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, real, to_hand, zone

DECREE = "Thranduil's Decree"
EXTRA = [real(DECREE, "{1}{U}{U}", 3, "Instant",
              "Counter target spell. If a permanent spell is countered this way, exile it instead of putting it into its owner's graveyard. "
              "You may cast that card without paying its mana cost for as long as it remains exiled.", None, "U")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(DECREE)).level == "FULL"


@pytest.mark.parametrize("name,dest", [("Grizzly Bears", "p1:exile"), ("Lightning Bolt", "p1:graveyard")])
def test_exiles_a_permanent_spell_only_and_lets_the_card_be_cast_free(cards, name, dest):
    s = build(cards, [name], [DECREE])
    mana(s, "p1", R=1, G=1, C=1)
    mana(s, "p2", U=2, C=1)
    decree = to_hand(s, DECREE, "p2")
    victim = cast(s, name, ["p2"] if name == "Lightning Bolt" else [])
    act(s, "p2", type="cast_spell", card_id=decree.id, targets=[victim.id])
    answer(s)
    assert zone(s, victim) == dest
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and s.state.rules.priority == "p2")
    mana(s, "p2")
    if name == "Grizzly Bears":
        act(s, "p2", type="cast_spell", card_id=victim.id, targets=[], free=True)
        answer(s)
        assert zone(s, victim) == "p2:battlefield"
    else:
        with pytest.raises(ActionError):
            act(s, "p2", type="cast_spell", card_id=victim.id, targets=["p2"], free=True)
    check(s)
