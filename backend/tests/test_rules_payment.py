"""Mana payment: AUTO / ASK / MANUAL, and PREFER / NORMAL / SAVE per mana source."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from tests.game_helpers import act, enable, make_session, zone


def setup(cards, level="full", mountains=2):
    s = GameSession(enable(make_session(cards).state, level), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main 1
    act(s, "p1", type="draw", count=9)
    hand = [s.state.cards[c] for c in zone(s.state, "p1", "hand")]
    lands = [c for c in hand if c.name == "Mountain"][:mountains]
    ring = next(c for c in hand if c.name == "Sol Ring")
    act(s, "p1", type="move", card_ids=[c.id for c in lands] + [ring.id], to={"zone": "battlefield"})
    return s, lands, ring


def card(s, name):
    return next(s.state.cards[c] for c in zone(s.state, "p1", "hand") if s.state.cards[c].name == name)


def tapped(s, *cards_):
    return [s.state.cards[c.id].tapped for c in cards_]


def test_save_sources_are_kept_unless_needed(cards):
    s, (m1, m2), ring = setup(cards)
    act(s, "p1", type="set_prefs", mana_source=ring.id, mana_source_protection="save")
    act(s, "p1", type="cast_spell", card_id=card(s, "Fire // Ice").id)  # {1}{R}
    assert tapped(s, m1, m2, ring) == [True, True, False]  # Sol Ring (SAVE) left alone


def test_save_sources_are_used_when_there_is_no_other_way(cards):
    s, (m1,), ring = setup(cards, mountains=1)
    act(s, "p1", type="set_prefs", mana_source=ring.id, mana_source_protection="save")
    act(s, "p1", type="cast_spell", card_id=card(s, "Fire // Ice").id)
    assert tapped(s, m1, ring) == [True, True]


def test_prefer_sources_go_first(cards):
    s, (m1, m2), ring = setup(cards)
    act(s, "p1", type="set_prefs", mana_source=m2.id, mana_source_protection="prefer")
    act(s, "p1", type="cast_spell", card_id=card(s, "Lightning Bolt").id, targets=["p2"])
    assert tapped(s, m1, m2) == [False, True]
    with pytest.raises(ActionError, match="your own mana sources"):
        act(s, "p2", type="set_prefs", mana_source=m1.id, mana_source_protection="save")


def test_ask_suggests_a_payment_and_cancel_leaves_everything(cards):
    s, (m1, m2), ring = setup(cards)
    act(s, "p1", type="set_prefs", payment="ask")
    bolt = card(s, "Lightning Bolt")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    d = s.state.rules.decision
    assert d.player == "p1" and "Pay {R} for Lightning Bolt. Suggested payment: Mountain" in d.prompt
    assert s.state.cards[bolt.id].zone == "p1:hand"  # nothing has moved yet
    shown = s.view("p1")["rules"]["decision"]["display"]  # the payment panel's thumbnails, for the decider
    assert shown["kind"] == "payment" and shown["cost"] == "{R}" and len(shown["suggested"]) == 1
    assert "display" not in s.view("p2")["rules"]["decision"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["cancel"])
    assert s.state.cards[bolt.id].zone == "p1:hand" and s.state.rules.priority == "p1"
    assert tapped(s, m1, m2, ring) == [False, False, False]
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["pay"])
    assert s.state.cards[bolt.id].zone != "p1:hand" and sum(tapped(s, m1, m2)) == 1


def test_assisted_asks_by_default(cards):
    s, _, _ = setup(cards, "assisted")
    act(s, "p1", type="cast_spell", card_id=card(s, "Lightning Bolt").id, targets=["p2"])
    assert "Suggested payment" in s.state.rules.decision.prompt


def test_manual_payment_picks_exact_sources(cards):
    s, (m1, m2), ring = setup(cards)
    act(s, "p1", type="set_prefs", payment="manual")
    fire = card(s, "Fire // Ice")
    act(s, "p1", type="cast_spell", card_id=fire.id)
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and {o.id for o in d.options} == {m1.id, m2.id, ring.id}
    with pytest.raises(ActionError, match="can't pay"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[ring.id])  # colourless only: no {R}
    with pytest.raises(ActionError, match="isn't needed"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[m1.id, m2.id, ring.id])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[m1.id, ring.id])
    assert tapped(s, m1, m2, ring) == [True, False, True]
    assert s.state.cards[fire.id].zone != "p1:hand"


def test_sources_can_be_given_with_the_cast(cards):
    s, (m1, m2), ring = setup(cards)
    act(s, "p1", type="set_prefs", payment="ask")  # explicit sources are an answer: no prompt
    act(s, "p1", type="cast_spell", card_id=card(s, "Lightning Bolt").id, sources=[m2.id], targets=["p2"])
    assert tapped(s, m1, m2) == [False, True] and s.state.players["p2"].life == 37  # paid, cast, resolved by the engine
    with pytest.raises(ActionError, match="untapped mana sources you control"):
        act(s, "p1", type="cast_spell", card_id=card(s, "Fire // Ice").id, sources=[m2.id, ring.id])


def test_generic_spends_other_colors_once_colorless_runs_out():
    """Regression: with {C} and {G} left over for {2}, both are spent (colorless never goes negative)."""
    from app.rules import mana as M

    payment = M.solve(M.parse_cost("{2}"), {}, [M.Source("a", (("C",),)), M.Source("b", (("G",),))])
    assert payment.delta() == {} and sorted(payment.tapped) == ["a", "b"]
