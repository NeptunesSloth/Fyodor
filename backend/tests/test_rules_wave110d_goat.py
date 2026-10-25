"""Wave 110D: Oft-Nabbed Goat, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 602.2, 611.2, 109.5: "{1}: Draw a card. Gain control of this creature and put a -1/-1 counter on it. Only your opponents may activate this ability and only as a
  sorcery." — the opponent draws, takes the Goat and puts the counter on it; its controller can't activate it.
* 603.10a, 608.2h: "When this creature dies, if it had one or more -1/-1 counters on it, its owner draws that many cards and each other player loses that much life."
  — the owner (not the controller) draws, the other players lose life; with no counter on it, nothing.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, life
from tests.wave110d_kit import activate, card_db, cast_on, check, full, mana, now, put, refused, settle, to_phase  # noqa: F401


def hand(s, pid):
    return len(s.state.zones[f"{pid}:hand"])


def p2_turn(s):
    to_phase(s, "main1", turn=2)
    assert s.state.turn.active_player == "p2"


def test_goat_is_full():
    assert full("Oft-Nabbed Goat")


def test_opponent_steals_and_dies_to_owner_draw(cards):
    s = build(cards, ["Oft-Nabbed Goat", "Murder"], ["Murder"])
    goat = put(s, "Oft-Nabbed Goat")
    refused(s, "opponent|only|can.t", goat, "{1}")  # (its controller may not activate it)
    p2_turn(s)
    mana(s, "p2", C=1)
    h2, h1, l1, l2 = hand(s, "p2"), hand(s, "p1"), life(s, "p1"), life(s, "p2")
    activate(s, goat, "{1}", pid="p2")
    assert now(s, goat).controller == "p2" and hand(s, "p2") == h2 + 1
    assert now(s, goat).counters.get("-1/-1") == 1
    cast_on(s, "Murder", goat, pid="p2")
    assert now(s, goat).zone.endswith(":graveyard")
    assert hand(s, "p1") == h1 + 1 and life(s, "p1") == l1 and life(s, "p2") == l2 - 1
    check(s)


def test_no_counter_no_trigger(cards):
    s = build(cards, ["Oft-Nabbed Goat"], ["Murder"])
    goat = put(s, "Oft-Nabbed Goat")
    p2_turn(s)
    h1, l2 = hand(s, "p1"), life(s, "p2")
    cast_on(s, "Murder", goat, pid="p2")
    assert hand(s, "p1") == h1 and life(s, "p2") == l2
    check(s)
