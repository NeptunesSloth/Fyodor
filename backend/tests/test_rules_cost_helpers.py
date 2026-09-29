"""Delve and improvise (paid by the player during the "tap your mana" prompt), evoke, rebound."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import mana
from tests.test_rules_suspend import until


def build(cards, name, *, self_tap=True):
    alice = deck(cards, "Krenko, Mob Boss", [(1, name), (15, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False))
    if self_tap:
        for prefs in state.rules.prefs.values():
            prefs.payment = "self"
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")
    card = next(c for c in s.state.cards.values() if c.name == name)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "hand"})
    return s, card


def test_delve(cards):
    s, cruise = build(cards, "Treasure Cruise")
    forests = [c for c in zone(s.state, "p1", "library") if s.state.cards[c].name == "Forest"][:7]
    act(s, "p1", type="move", card_ids=forests, to={"zone": "graveyard"})
    mana(s, U=1)
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="cast_spell", card_id=cruise.id)
    d = s.state.rules.decision
    assert set(d.display["delve"]) == set(forests)
    for c in forests:
        act(s, "p1", type="activate_ability", card_id=c, ability=0, delve=True)
    until(s, lambda s: not s.state.zones.get("stack"))
    assert all(s.state.cards[c].zone == "p1:exile" for c in forests)
    assert len(zone(s.state, "p1", "hand")) == hand - 1 + 3


def test_improvise(cards):
    s, rev = build(cards, "Reverse Engineer")
    ids = []
    for i in range(3):
        act(s, "p1", type="create_token", player="p1", token={"name": f"Thopter{i}", "type_line": "Token Artifact — Thopter"})
        ids.append(next(c.id for c in s.state.cards.values() if c.name == f"Thopter{i}"))
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=rev.id)
    d = s.state.rules.decision
    assert set(d.display["improvise"]) == set(ids)
    for c in ids:
        act(s, "p1", type="activate_ability", card_id=c, ability=0, improvise=True)
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[rev.id].zone == "p1:graveyard" and all(s.state.cards[c].tapped for c in ids)


def test_evoke(cards):
    s, drifter = build(cards, "Mulldrifter", self_tap=False)
    mana(s, U=1, C=2)
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="cast_spell", card_id=drifter.id, evoke=True)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "order")
    d = s.state.rules.decision  # its enters trigger and the evoke sacrifice trigger: its controller orders them
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    until(s, lambda s: not s.state.zones.get("stack") and s.state.cards[drifter.id].zone != "stack"
          and s.state.cards[drifter.id].zone != "p1:battlefield")
    assert s.state.cards[drifter.id].zone == "p1:graveyard"
    assert len(zone(s.state, "p1", "hand")) == hand - 1 + 2


def test_rebound(cards):
    s, shock = build(cards, "Staggershock", self_tap=False)
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=["p2"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 38 and s.state.cards[shock.id].zone == "p1:exile"
    until(s, lambda s: s.state.rules.decision is not None and "Rebound" in s.state.rules.decision.prompt, limit=400)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 36 and s.state.cards[shock.id].zone == "p1:graveyard"
