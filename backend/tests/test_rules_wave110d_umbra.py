"""Wave 110D: Dog Umbra, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 702.89a, 611.3a: "As long as another player controls enchanted creature, it can't attack or block. Otherwise, this Aura has umbra armor." — you control
  it: umbra armor (a destroy removes the damage and destroys the Aura instead); another player does: it can't attack, and no umbra armor.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, cast_on, check, full, now, put_new, settle, to_phase  # noqa: F401


def test_dog_umbra_is_full():
    assert full("Dog Umbra")


def test_own_creature_has_umbra_armor(cards):
    s = build(cards, ["Dog Umbra", "Grizzly Bears", "Murder"])
    bears = put_new(s, "Grizzly Bears")
    aura = cast_on(s, "Dog Umbra", bears)
    assert aura.attached_to == bears.id
    cast_on(s, "Murder", bears)
    assert now(s, bears).zone == "p1:battlefield" and now(s, aura).zone == "p1:graveyard"
    check(s)


def test_opponents_creature_cant_attack_and_has_no_armor(cards):
    s = build(cards, ["Dog Umbra", "Dog Umbra", "Murder"], ["Grizzly Bears", "Grizzly Bears"])
    bears = put_new(s, "Grizzly Bears", "p2")
    aura = cast_on(s, "Dog Umbra", bears)
    assert aura.attached_to == bears.id
    cast_on(s, "Murder", bears)
    assert now(s, bears).zone == "p2:graveyard"
    bears = put_new(s, "Grizzly Bears", "p2")
    cast_on(s, "Dog Umbra", bears)
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="set_stops", own=["declare_attackers"], smart_pass=False)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    check(s)
