"""Counterspells (701.6), "counter unless its controller pays", and ward (702.21)."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_suspend import until


def build(cards, bob_spell):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Lightning Bolt"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, bob_spell), (9, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt")
    answer = next(c for c in s.state.cards.values() if c.name == bob_spell)
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    act(s, "p2", type="move", card_ids=[answer.id], to={"zone": "hand"})
    act(s, "p2", type="set_prefs", response="on")
    return s, bolt, answer


def bolt_then_answer(s, bolt, answer, **bob_mana):
    mana(s, "p2", **bob_mana)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=answer.id, targets=[bolt.id])


def test_counterspell(cards):
    s, bolt, counterspell = build(cards, "Counterspell")
    bolt_then_answer(s, bolt, counterspell, U=2)
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 40 and s.state.cards[bolt.id].zone == "p1:graveyard"


def test_mana_leak_paid(cards):
    s, bolt, leak = build(cards, "Mana Leak")
    mana(s, C=3)  # (review 4R: she can pay, so she's asked — 118.3)
    bolt_then_answer(s, bolt, leak, U=1, C=1)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == "p1")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 37


def test_mana_leak_declined(cards):
    s, bolt, leak = build(cards, "Mana Leak")
    mana(s, C=3)  # (review 4R: she can pay, so she's asked — 118.3)
    bolt_then_answer(s, bolt, leak, U=1, C=1)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == "p1")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 40 and s.state.cards[bolt.id].zone == "p1:graveyard"


def test_ward_counters_unless_paid(cards):
    s, bolt, _ = build(cards, "Counterspell")
    act(s, "p2", type="create_token", player="p2", token={"name": "Warden", "type_line": "Token Creature — Test",
                                                         "power": "2", "toughness": "2", "text": "Ward {2}"})
    warden = next(c for c in s.state.cards.values() if c.name == "Warden")
    mana(s, R=1, C=2)  # (review 4R: she can pay the ward cost, so she's asked — 118.3)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[warden.id])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == "p1")
    d = s.state.rules.decision
    assert "{2}" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[warden.id].zone == "p2:battlefield" and s.state.cards[warden.id].damage == 0
    assert zone(s.state, "p1", "graveyard") == [bolt.id]


# -- review (wave 4R) -- 118.3: "counter ... unless its controller pays" / ward don't offer PAY to a player who can't pay
def test_mana_leak_a_player_who_cant_pay_isnt_asked(cards):
    s, bolt, leak = build(cards, "Mana Leak")
    bolt_then_answer(s, bolt, leak, U=1, C=1)
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 40 and s.state.cards[bolt.id].zone == "p1:graveyard"
    replay_matches(s)


def test_ward_a_player_who_cant_pay_isnt_asked(cards):
    s, bolt, _ = build(cards, "Counterspell")
    act(s, "p2", type="create_token", player="p2", token={"name": "Warden", "type_line": "Token Creature — Test",
                                                         "power": "2", "toughness": "2", "text": "Ward {2}"})
    warden = next(c for c in s.state.cards.values() if c.name == "Warden")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[warden.id])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[warden.id].zone == "p2:battlefield" and s.state.cards[warden.id].damage == 0
    assert zone(s.state, "p1", "graveyard") == [bolt.id]
    replay_matches(s)
