"""Suspend (CR 702.62): exile with time counters for the suspend cost; remove one each upkeep;
when the last is removed, cast it without paying its mana cost (a creature gains haste)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana


def build(cards, name):
    alice = deck(cards, "Krenko, Mob Boss", [(1, name), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    card = next(c for c in s.state.cards.values() if c.name == name)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "hand"})
    return s, card


def until(s, done, limit=300):
    for _ in range(limit):
        if done(s):
            return
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None and d.kind == "choose_cards":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:d.min_choices])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def prompt(s):
    d = s.state.rules.decision
    return d is not None and (d.resume or {}).get("step") == "suspend_cast"


def test_rift_bolt(cards):
    s, bolt = build(cards, "Rift Bolt")
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=bolt.id, ability=1)  # "Suspend 1—{R}"
    c = s.state.cards[bolt.id]
    assert c.zone == "p1:exile" and c.counters == {"time": 1} and s.state.players["p1"].mana == {}
    until(s, prompt)  # Alice's next upkeep
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    d = s.state.rules.decision  # its target
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 37 and s.state.cards[bolt.id].zone == "p1:graveyard"
    assert not s.state.rules.free_casts and not s.state.rules.suspended


def test_suspended_creature_has_haste(cards):
    s, eph = build(cards, "Errant Ephemeron")
    mana(s, U=1, C=1)
    act(s, "p1", type="activate_ability", card_id=eph.id, ability=1)
    until(s, prompt, limit=2000)
    assert s.state.turn.number >= 7  # four of Alice's upkeeps later
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    until(s, lambda s: s.state.cards[eph.id].zone == "p1:battlefield")
    assert "haste" in Plan(s.state, "p1", cards, None).ch(s.state.cards[eph.id]).keywords


def test_free_cast_only_when_granted(cards):
    s, bolt = build(cards, "Rift Bolt")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, targets=["p2"])


def test_cascade_casts_a_cheaper_card_for_free(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Bloodbraid Elf"), (1, "Lightning Bolt"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    elf = next(c for c in s.state.cards.values() if c.name == "Bloodbraid Elf")
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, R=1, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=elf.id)
    until(s, lambda s: s.state.rules.decision is not None and "Cascade" in s.state.rules.decision.prompt)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 37
    assert s.state.cards[elf.id].zone == "p1:battlefield"
    assert s.state.zones["p1:library"][-1] == forest.id  # the missed land went to the bottom
