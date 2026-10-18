"""Milestone 15d: activated and loyalty abilities go on the stack with their costs paid."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act, find, turn_on, zone
from tests.test_rules_combat import table


def token(s, pid, name, type_line, text="", **extra):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "text": text, **extra})
    return find(s.state, name, pid)


def to_main(s):
    turn_on(s)  # what's already there isn't summoning sick
    act(s, "p1", type="pass_priority")


def test_tap_ability_goes_on_the_stack_and_resolves_by_hand(cards):
    s = table(cards)
    # (Krenko's token ability is automated now — test_rules_tokens.py; a coin flip is since wave 7E; a die roll is since wave 12A, rerolls (706.2b) are not)
    gambler = token(s, "p1", "Gambler", "Token Creature — Human", "{T}: Roll a d6. If the result is odd, reroll it.")
    to_main(s)
    hints = s.view("p1")["rules"]["hints"]
    assert {"card_id": gambler.id, "ability": 0} in hints["activatable"]
    act(s, "p1", type="activate_ability", card_id=gambler.id, ability=0)
    d = s.state.rules.decision
    assert s.state.cards[gambler.id].tapped
    assert d and d.kind == "manual_resolution" and "Roll a d6" in d.prompt and "Gambler" in d.prompt
    assert not s.state.zones["stack"]  # the ability object is gone once it resolved
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["done"])
    with pytest.raises(ActionError, match="tapped"):
        act(s, "p1", type="activate_ability", card_id=gambler.id, ability=0)


def test_loyalty_abilities(cards):
    s = table(cards)
    walker = token(s, "p1", "Sage", "Token Legendary Planeswalker — Sage", "+1: Draw a card.\n−5: You win the game.")
    act(s, "p1", type="counter", card_ids=[walker.id], kind="loyalty", delta=3)
    to_main(s)
    with pytest.raises(ActionError, match="enough loyalty"):
        act(s, "p1", type="activate_ability", card_id=walker.id, ability=1)
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=0)
    assert s.state.cards[walker.id].counters["loyalty"] == 4
    for _ in range(4):  # (the +1 is automated now: it goes on the stack and resolves)
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    with pytest.raises(ActionError, match="already used a loyalty ability"):
        act(s, "p1", type="activate_ability", card_id=walker.id, ability=0)


def test_mana_and_sacrifice_costs(cards):
    s = table(cards)
    stone = token(s, "p1", "Stone", "Token Artifact", "{1}, {T}, Sacrifice this artifact: Draw a card.")
    forest = find(s.state, "Forest", "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    to_main(s)
    act(s, "p1", type="activate_ability", card_id=stone.id, ability=0)
    assert stone.id not in s.state.cards  # sacrificed (a token: gone)
    assert s.state.cards[forest.id].tapped  # paid {1}
    assert "paid {1} to activate Stone" in json.dumps(s.view("p2")["log"])


def test_costs_and_timing_the_engine_cannot_handle_are_refused(cards):
    s = table(cards)
    odd = token(s, "p1", "Oddity", "Token Artifact",
                "Sacrifice another creature or token: Scry 1.\n{T}: Draw a card. Activate only as a sorcery.")  # (wave 4H)
    to_main(s)
    with pytest.raises(ActionError):  # (read since wave 50G: "another" covers the token too, so the Oddity can't pay with itself)
        act(s, "p1", type="activate_ability", card_id=odd.id, ability=0)
    act(s, "p1", type="phase", to="end")  # manual jump out of the main phase
    with pytest.raises(ActionError, match="main phase"):
        act(s, "p1", type="activate_ability", card_id=odd.id, ability=1)
