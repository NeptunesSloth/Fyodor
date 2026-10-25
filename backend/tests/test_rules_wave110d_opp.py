"""Wave 110D: "of an opponent's choice" targets, real Oracle text (tests/fixtures/wave110d_cards.json).

* 115.1, 601.2c, 603.3d: the opponent chosen announces the target of Evangelize (spell), Mausoleum Turnkey (triggered) and Arena (activated, together
  with its controller's own first target); the spell's/ability's controller still pays and owns legality.
* 701.14a: Arena's two creatures fight each other (after both are tapped by the ability).
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import ability, card_db, check, cost, full, mana, now, put_new, settle, to_phase  # noqa: F401


@pytest.mark.parametrize("name", ["Evangelize", "Mausoleum Turnkey", "Arena"])
def test_full(name):
    assert full(name)


def test_evangelize_opponent_picks_their_creature(cards):
    s = build(cards, ["Evangelize", "Grizzly Bears"], ["Grizzly Bears", "Grizzly Bears"])
    mine = put_new(s, "Grizzly Bears")
    t1, t2 = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Grizzly Bears", "p2")
    ev = to_hand(s, "Evangelize")
    mana(s, "p1", **cost("Evangelize"))
    act(s, "p1", type="cast_spell", card_id=ev.id, sources=[])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["p2"])  # (the opponent who picks)
    d = s.state.rules.decision
    assert d.player == "p2"
    ids = {o.id for o in d.options}
    assert ids == {t1.id, t2.id} and mine.id not in ids
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[t2.id])
    settle(s)
    assert now(s, t2).controller == "p1" and now(s, t1).controller == "p2"
    assert now(s, ev).zone == "p1:graveyard"
    check(s)


def test_evangelize_buyback_returns_to_hand(cards):
    s = build(cards, ["Evangelize", "Grizzly Bears"], ["Grizzly Bears"])
    t1 = put_new(s, "Grizzly Bears", "p2")
    ev = to_hand(s, "Evangelize")
    mana(s, "p1", W=3, C=6)
    act(s, "p1", type="cast_spell", card_id=ev.id, sources=[], buyback=True)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["p2"])
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[t1.id])
    settle(s)
    assert now(s, t1).controller == "p1" and now(s, ev).zone == "p1:hand"
    check(s)


def test_turnkey_opponent_picks_creature_card_from_my_graveyard(cards):
    s = build(cards, ["Mausoleum Turnkey", "Grizzly Bears", "Llanowar Elves"], [])
    a, b = to_hand(s, "Grizzly Bears"), to_hand(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[a.id, b.id], to={"player": "p1", "zone": "graveyard"})
    tk = to_hand(s, "Mausoleum Turnkey")
    mana(s, "p1", **cost("Mausoleum Turnkey"))
    act(s, "p1", type="cast_spell", card_id=tk.id, sources=[])
    for _ in range(6):  # (the creature spell, then its trigger, until the opponent is asked)
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and {o.id for o in d.options} == {a.id, b.id}
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[b.id])
    settle(s)
    assert now(s, b).zone == "p1:hand" and now(s, a).zone == "p1:graveyard"
    check(s)


def test_arena_tap_both_and_fight(cards):
    s = build(cards, ["Arena", "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears", "Llanowar Elves"])
    arena = put_new(s, "Arena")
    mine = put_new(s, "Grizzly Bears")
    t1, t2 = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Llanowar Elves", "p2")
    other = put_new(s, "Grizzly Bears")
    mana(s, "p1", C=3)
    to_phase(s, "main1", turn=3)
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=arena.id, ability=ability(s, arena, "{3}, {T}"), sources=[])
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {mine.id, other.id}  # the first target is mine
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[mine.id])
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} == {t1.id, t2.id}
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[t2.id])
    settle(s)
    assert now(s, mine).tapped  # tapped (the Elves die, so their tapped state is gone), then they fight: my Bears (2) kill the Elves (1/1) and take 1
    assert now(s, t2).zone == "p2:graveyard" and now(s, t1).zone == "p2:battlefield" and now(s, mine).zone == "p1:battlefield" and now(s, mine).damage == 1
    check(s)
