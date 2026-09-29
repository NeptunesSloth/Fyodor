"""Echo (CR 702.30) and "At the beginning of your upkeep, sacrifice ~ unless you pay {cost}"."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable


def build(cards, name):
    alice = deck(cards, "Krenko, Mob Boss", [(1, name), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    card = next(c for c in s.state.cards.values() if c.name == name)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "battlefield"})
    s = GameSession(enable(s.state), cards=cards)
    return s, card


def until_prompt(s, turns=3):
    """Pass along (no attacks/blocks) until a pay-or-sacrifice prompt appears."""
    for _ in range(200):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one" and d.resume.get("step") == "pay_or_sacrifice":
            return d
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None and d.kind == "choose_cards":  # cleanup discard
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:d.min_choices])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no prompt")


def answer(s, d, choice):
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[choice])
    for _ in range(10):
        if not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")


def test_echo_pay_keeps_it_and_is_asked_only_once(cards):
    s, troll = build(cards, "Albino Troll")
    d = until_prompt(s)
    assert d.player == "p1" and {o.id for o in d.options} == {"pay", "sacrifice"}
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])  # nothing to pay with
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["sacrifice"])
    assert s.state.cards[troll.id].zone == "p1:graveyard"


def test_echo_paid(cards):
    s, troll = build(cards, "Albino Troll")
    forests = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:2]
    act(s, "p1", type="move", card_ids=forests, to={"zone": "battlefield"})
    d = until_prompt(s)
    assert "pay" in {o.id for o in d.options}
    answer(s, d, "pay")
    assert s.state.cards[troll.id].zone == "p1:battlefield"
    assert all(s.state.cards[f].tapped for f in forests)  # {1}{G} paid with the two Forests
    assert f"{s.state.rules.object_id(troll.id)}:p1" in s.state.rules.echo_done


def test_sacrifice_unless_you_pay_template(cards):
    s, forces = build(cards, "Phantasmal Forces")
    d = until_prompt(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["sacrifice"])
    assert s.state.cards[forces.id].zone == "p1:graveyard"


def test_cumulative_upkeep_grows(cards):
    s, _ = build(cards, "Forest")
    forests = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:4]
    act(s, "p1", type="move", card_ids=forests, to={"zone": "battlefield"})
    act(s, "p1", type="create_token", player="p1", token={"name": "Glacier", "type_line": "Token Enchantment — Test",
                                                         "text": "Cumulative upkeep {1}"})
    glacier = next(c for c in s.state.cards.values() if c.name == "Glacier")
    d = until_prompt(s)
    assert "{1}" in d.prompt and s.state.cards[glacier.id].counters == {"age": 1}
    answer(s, d, "pay")
    d = until_prompt(s)
    assert "{2}" in d.prompt and s.state.cards[glacier.id].counters == {"age": 2}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["sacrifice"])
    assert glacier.id not in s.state.cards or not s.state.cards[glacier.id].zone.endswith(":battlefield")
