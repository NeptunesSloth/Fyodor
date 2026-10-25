"""Wave 110D: Requiem Monolith, real Oracle text.

* 608.2d: "That creature's controller may have this artifact deal 1 damage to it" is the TARGET's controller's choice, not the Monolith's.
* 120.3, 603.2: the damage is dealt by the Monolith; the granted trigger then makes the creature's controller draw and lose that much life.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave110d_kit import ability, build, card_db, check, full, now, put_new, settle, to_phase  # noqa: F401

START = "{T}: Until end of turn, target creature gains"


def test_full():
    assert full("Requiem Monolith")


@pytest.mark.parametrize("answer, damage, drawn", [("yes", 1, 1), ("no", 0, 0)])
def test_target_controller_chooses(cards, answer, damage, drawn):
    s = build(cards, ["Requiem Monolith"], ["Grizzly Bears"])
    mono = put_new(s, "Requiem Monolith")
    bear = put_new(s, "Grizzly Bears", pid="p2")
    to_phase(s, "main1", turn=3)
    hand, life = len([c for c in s.state.cards.values() if c.zone == "p2:hand"]), s.state.players["p2"].life
    act(s, "p1", type="activate_ability", card_id=mono.id, ability=ability(s, mono, START), targets=[bear.id])
    settle(s, answers=[answer])
    assert now(s, bear).damage == damage
    assert len([c for c in s.state.cards.values() if c.zone == "p2:hand"]) == hand + drawn
    assert s.state.players["p2"].life == life - drawn
    check(s)
