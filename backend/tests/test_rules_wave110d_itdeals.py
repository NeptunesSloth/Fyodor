"""Wave 110D: "it deals N damage to X and N damage to Y" in a creature's own ETB trigger (real Oracle text).

* 120.3, 603.7: "it" is the trigger's source (the creature), not the first target; both damage amounts are dealt by it.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_wave110d_three import three
from tests.wave110d_kit import card_db, check, cost, life, mana, now, put_new, settle, to_hand  # noqa: F401


def test_forge_devil_hits_creature_and_you(cards):
    s = three(cards, ["Forge Devil"], ["Grizzly Bears"])
    bears = put_new(s, "Grizzly Bears", "p2")
    c = to_hand(s, "Forge Devil")
    mana(s, "p1", **cost("Forge Devil"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s, answers=[bears.id])
    assert life(s, "p1") == 39 and now(s, bears).damage == 1
    check(s)


def test_firewheeler_hits_opponent_and_creature(cards):
    s = three(cards, ["Rakdos Firewheeler"], ["Grizzly Bears"])
    bears = put_new(s, "Grizzly Bears", "p2")
    c = to_hand(s, "Rakdos Firewheeler")
    mana(s, "p1", **cost("Rakdos Firewheeler"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s, answers=["p2", bears.id])
    assert life(s, "p2") == 38 and now(s, bears).zone == "p2:graveyard"
    check(s)
