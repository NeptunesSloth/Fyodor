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


@pytest.mark.parametrize("name", ["Evangelize", "Mausoleum Turnkey", "Arena", "Cuombajj Witches", "Diaochan, Artful Beauty", "Echo Chamber"])
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


def test_witches_players_and_creatures_both_targetable(cards):
    """Cuombajj Witches: the first 1 damage goes where its controller says, the second where the opponent says (a player too)."""
    s = build(cards, ["Cuombajj Witches", "Grizzly Bears"], ["Grizzly Bears"])
    w = put_new(s, "Cuombajj Witches")
    mine = put_new(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=ability(s, w, "{T}"), sources=[])
    d = s.state.rules.decision
    assert d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])  # my pick: the opponent's face
    d = s.state.rules.decision
    assert d.player == "p2" and {"p1", "p2", mine.id} <= {o.id for o in d.options}
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[mine.id])  # theirs: my creature
    settle(s)
    assert s.state.players["p2"].life == 39 and now(s, mine).damage == 1 and s.state.players["p1"].life == 40
    check(s)


def test_diaochan_destroys_in_order(cards):
    s = build(cards, ["Diaochan, Artful Beauty", "Grizzly Bears"], ["Grizzly Bears", "Grizzly Bears"])
    di = put_new(s, "Diaochan, Artful Beauty")
    mine = put_new(s, "Grizzly Bears")
    t1, t2 = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="activate_ability", card_id=di.id, ability=ability(s, di, "{T}"), sources=[])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[t1.id])
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} >= {t2.id, mine.id}
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[mine.id])  # the opponent picks my creature: any creature is legal
    settle(s)
    assert now(s, t1).zone == "p2:graveyard" and now(s, mine).zone == "p1:graveyard" and now(s, t2).zone == "p2:battlefield"
    check(s)


def test_echo_chamber_copy_of_their_creature(cards):
    s = build(cards, ["Echo Chamber", "Grizzly Bears"], ["Llanowar Elves", "Grizzly Bears"])
    ec = put_new(s, "Echo Chamber")
    mine = put_new(s, "Grizzly Bears")
    theirs = put_new(s, "Llanowar Elves", "p2")
    to_phase(s, "main1", turn=3)
    mana(s, "p1", C=4)
    act(s, "p1", type="activate_ability", card_id=ec.id, ability=ability(s, ec, "{4}, {T}"), sources=[])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["p2"])
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} == {theirs.id}  # their creatures only
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[theirs.id])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.token and c.name == "Llanowar Elves" and c.zone == "p1:battlefield"]
    assert len(tokens) == 1
    check(s)
