"""Wave 110D: Call for Aid, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 611.2c, 702.10: "Gain control of all creatures target opponent controls until end of turn. Untap those creatures. They gain haste until end of turn."
* 508.1c: "You can't attack that player this turn." — no creature you control may attack the player, a stolen one or your own.
* 701.21: "You can't sacrifice those creatures this turn." — the stolen creatures can't be sacrificed.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import prohibitions
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, cast_on, check, full, now, put_new, to_phase  # noqa: F401


def test_call_for_aid_is_full():
    assert full("Call for Aid")


@pytest.mark.parametrize("stolen", [True, False])
def test_control_haste_no_sacrifice_no_attack_on_that_player(cards, stolen):
    s = build(cards, ["Call for Aid", "Grizzly Bears"], ["Grizzly Bears"])
    mine = put_new(s, "Grizzly Bears")
    theirs = put_new(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=3)
    cast_on(s, "Call for Aid", "p2")
    assert now(s, theirs).controller == "p1" and not now(s, theirs).tapped
    plan = Plan(s.state, "p1", cards, None)
    assert prohibitions.sacrifice_forbidden(plan, now(s, theirs)) and not prohibitions.sacrifice_forbidden(plan, now(s, mine))
    to_phase(s, "declare_attackers", turn=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": (theirs if stolen else mine).id, "target": "p2"}])
    check(s)


def test_without_the_spell_the_attack_is_legal(cards):
    s = build(cards, ["Grizzly Bears"], [])
    mine = put_new(s, "Grizzly Bears")
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": mine.id, "target": "p2"}])
    check(s)
