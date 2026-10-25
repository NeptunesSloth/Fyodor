"""Wave 110D: Coveted Falcon, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 108.3, 110.2, 701.12: "Whenever this creature attacks, gain control of target permanent you own but don't control." — only a permanent you own that another player controls.
* 702.168, 701.34, 608.2b: "When this creature is turned face up, target opponent gains control of any number of target permanents you control. Draw a card for each one they
  gained control of this way." — one card per permanent given away; none given, none drawn.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import card_db, check, full, mana, next_turn, now, put, put_new, settle, to_phase  # noqa: F401


def test_falcon_is_full():
    assert full("Coveted Falcon")


def turned_up(cards, give):
    s = build(cards, ["Coveted Falcon", "Grizzly Bears", "Llanowar Elves"])
    falcon = to_hand(s, "Coveted Falcon")
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=falcon.id, face_down=True)
    settle(s)
    assert now(s, falcon).face_down
    hand = len(s.state.zones["p1:hand"])
    mana(s, U=1, C=1)
    act(s, "p1", type="turn_face_up", card_id=falcon.id)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[{"b": bears.id, "e": elves.id}[k] for k in give])
    settle(s)
    return s, (bears, elves), len(s.state.zones["p1:hand"]) - hand


def test_turned_up_gives_permanents_and_draws_for_each(cards):
    s, (bears, elves), drawn = turned_up(cards, "be")
    assert now(s, bears).controller == "p2" and now(s, elves).controller == "p2" and drawn == 2
    check(s)


def test_turned_up_gives_none_draws_none(cards):
    s, (bears, elves), drawn = turned_up(cards, "")
    assert now(s, bears).controller == "p1" and drawn == 0
    check(s)


def test_attack_takes_back_a_permanent_you_own(cards):
    s = build(cards, ["Coveted Falcon", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    falcon, mine = put_new(s, "Coveted Falcon"), put_new(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p2", "zone": "battlefield"})  # (an opponent controls my Bears)
    theirs = put_new(s, "Grizzly Bears", pid="p2")
    assert now(s, mine).controller == "p2" and now(s, mine).owner == "p1"
    next_turn(s)
    next_turn(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": falcon.id, "target": "p2"}])
    d = s.state.rules.decision
    assert [o.id for o in d.options] == [mine.id]  # (not their own Bears, not mine under my control)
    settle(s)
    assert now(s, mine).controller == "p1" and now(s, theirs).controller == "p2"
    check(s)
