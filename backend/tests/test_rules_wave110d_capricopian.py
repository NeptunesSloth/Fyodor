"""Wave 110D: Capricopian, real Oracle text (tests/fixtures/wave110d_cards.json).

* 602.2 / 602.2a: only the player it attacks may activate {2}, during the declare attackers step; that player is "you" (counter, then reselect).
* 508.7c: they may reselect which player it attacks (not the creature's controller), with the creature still attacking.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave47b_kit import build3
from tests.wave110d_kit import card_db, check, full, mana, now, settle, to_hand  # noqa: F401

NAME = "Capricopian"


def test_full():
    assert full(NAME)


def _attack(cards, defender="p2"):
    """Alice casts Capricopian (X=2) in main 1 of turn 1 ... then attacks on turn 4 with the declare attackers decision still open."""
    s = build3(cards, [NAME], [], [])
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", response="on")  # (every priority is stopped at)
    mana(s, "p1", G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, NAME).id, x_value=2)
    settle(s)
    cap = next(c for c in s.state.cards.values() if c.name == NAME)
    for _ in range(300):
        d = s.state.rules.decision
        if s.state.turn.number == 4 and d is not None and d.kind == "declare_attackers":
            break
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s, cap


def _go(s, cap, defender):
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": cap.id, "target": defender}])
    for _ in range(4):  # the attack trigger-free declare step: Alice passes first, then Bob holds priority
        if s.state.rules.priority == defender:
            break
        act(s, s.state.rules.priority, type="pass_priority")


def _activate(s, cap, pid):
    ab = next(a.index for a in __import__("tests.wave110d_kit", fromlist=["ch"]).ch(s, cap).abilities if a.text.startswith("{2}"))
    act(s, pid, type="activate_ability", card_id=cap.id, ability=ab)


def test_the_defender_adds_a_counter_and_reselects(cards):
    s, cap = _attack(cards)
    assert now(s, cap).counters["+1/+1"] == 2
    _go(s, cap, "p2")
    assert now(s, cap).attacking.id == "p2"
    mana(s, "p2", C=2)
    _activate(s, cap, "p2")
    settle_to_choice(s)
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} == {"decline", "p2", "p3"}  # (never the creature's controller)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["p3"])
    settle(s)
    assert now(s, cap).counters["+1/+1"] == 3 and now(s, cap).attacking.id == "p3"
    check(s)


def settle_to_choice(s):
    for _ in range(10):
        if s.state.rules.decision is not None:
            return
        act(s, s.state.rules.priority, type="pass_priority")


def test_declining_keeps_the_attack(cards):
    s, cap = _attack(cards)
    _go(s, cap, "p2")
    mana(s, "p2", C=2)
    _activate(s, cap, "p2")
    settle_to_choice(s)
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["decline"])
    settle(s)
    assert now(s, cap).counters["+1/+1"] == 3 and now(s, cap).attacking.id == "p2"
    check(s)


@pytest.mark.parametrize("who", ["p1", "p3"])
def test_nobody_else_may_activate_it(cards, who):
    s, cap = _attack(cards)
    _go(s, cap, "p2")
    mana(s, who, C=2)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        _activate(s, cap, who)
    assert s.state.model_dump(mode="json") == before
