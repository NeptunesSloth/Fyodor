"""Wave 110D: Kytheon, Hero of Akros // Gideon, Battle-Forged, real Oracle text (tests/fixtures/wave110d_cards.json).

* 508.1, 500.8: "if Kytheon and at least two other creatures attacked this combat" counts the attackers declared in this combat.
* 508.1d: Gideon's +2 makes the creature attack Gideon during its controller's next turn if able.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave110d_kit import activate, build, card_db, check, full, now, put_new, settle, to_phase  # noqa: F401

NAME = "Kytheon, Hero of Akros // Gideon, Battle-Forged"


def test_full():
    assert full(NAME)


def attack(s, n):
    kyth = put_new(s, NAME)
    bears = [put_new(s, "Grizzly Bears") for _ in range(n)]
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in [kyth, *bears]])
    to_phase(s, "main2", turn=3)
    settle(s)
    return kyth


def test_transforms_with_two_other_attackers(cards):
    s = build(cards, [NAME, "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"])
    kyth = attack(s, 2)
    assert now(s, kyth).face == 1 and now(s, kyth).zone == "p1:battlefield"
    check(s)


def test_stays_with_one_other_attacker(cards):
    s = build(cards, [NAME, "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"])
    kyth = attack(s, 1)
    assert now(s, kyth).face == 0
    check(s)


def test_plus_two_forces_the_attack_on_gideon(cards):
    s = build(cards, [NAME, "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"])
    theirs = put_new(s, "Grizzly Bears", "p2")
    kyth = attack(s, 2)
    activate(s, kyth, "+2", targets=[theirs.id], target_counts=[1])
    to_phase(s, "declare_attackers", turn=4)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": theirs.id, "target": "p1"}])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": theirs.id, "target": kyth.id}])
    check(s)
