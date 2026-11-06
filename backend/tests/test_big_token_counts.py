"""-- big token counts -- More tokens or copies than one action makes as separate objects become one card ×N (the table's token stack),
made by hand while rules automation is paused. With automation on, the engine keeps each token its own object (111.6) and each token copy
of a card its own object (docs/TOKEN_STACKS.md); its refusal of a too-big creation now points at this way of finishing by hand.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_combat import table
from tests.test_rules_conditionals import build
from tests.test_rules_effects import replay_matches
from tests.test_rules_token_stacks import saved

INSECT = {"name": "Insect", "type_line": "Token Creature — Insect", "power": "1", "toughness": "1", "colors": ["G"]}
SCUTE_TEXT = ("Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, "
              "create a token that's a copy of this creature instead.")
SWARM = {"name": "Scute Swarm", "type_line": "Creature — Insect", "power": "1", "toughness": "1", "colors": ["G"], "text": SCUTE_TEXT}


def on_field(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone == f"{pid}:battlefield"]


def test_more_than_a_hundred_tokens_by_hand_are_one_card(cards):
    s = table(cards)  # automation off
    made = act(s, "p1", type="create_token", player="p1", token=INSECT, count=65_536)
    assert made.stacked is True
    (stack,) = on_field(s, "Insect")
    assert stack.quantity == 65_536 and stack.token is not None and stack.token.power == "1"
    assert "65,536 Insect tokens (stack ×65,536)" in str(s.state.log[-1].model_dump())
    s = saved(s)
    replay_matches(s)


def test_more_than_a_hundred_separate_tokens_is_refused(cards):
    s = table(cards)
    with pytest.raises(ActionError, match="one card ×N"):
        act(s, "p1", type="create_token", player="p1", token=INSECT, count=101, stacked=False)
    assert on_field(s, "Insect") == []


def test_with_automation_on_tokens_by_hand_stay_separate_and_capped(cards):
    s = build(cards)
    with pytest.raises(ActionError, match="Pause automation"):
        act(s, "p1", type="create_token", player="p1", token=INSECT, count=500)
    assert on_field(s, "Insect") == []
    act(s, "p1", type="create_token", player="p1", token=INSECT, count=100)
    assert len(on_field(s, "Insect")) == 100
    replay_matches(s)


def test_copies_of_a_card_by_hand_as_one_card(cards):
    s = table(cards)
    act(s, "p1", type="create_token", player="p1", token=SWARM)
    (swarm,) = on_field(s, "Scute Swarm")
    act(s, "p1", type="copy_card", card_id=swarm.id, player="p1", count=4096, stacked=True)
    copies = [c for c in on_field(s, "Scute Swarm") if c.id != swarm.id]
    assert len(copies) == 1
    (stack,) = copies
    assert stack.quantity == 4096 and stack.copy_of is not None and stack.copy_of.source_name == "Scute Swarm"
    assert stack.token is not None and "Landfall" in stack.token.text  # the card keeps its text
    assert "4,096 copies (stack ×4,096)" in str(s.state.log[-1].model_dump())
    act(s, "p1", type="split_stack", card_id=stack.id, count=96)  # the table's split still works on it
    assert sorted(c.quantity for c in on_field(s, "Scute Swarm")) == [1, 96, 4000]
    s = saved(s)
    replay_matches(s)


def test_many_separate_copies_are_refused(cards):
    s = table(cards)
    act(s, "p1", type="create_token", player="p1", token=SWARM)
    (swarm,) = on_field(s, "Scute Swarm")
    with pytest.raises(ActionError, match="one card ×N"):
        act(s, "p1", type="copy_card", card_id=swarm.id, player="p1", count=51)
    act(s, "p1", type="copy_card", card_id=swarm.id, player="p1", count=50)
    assert len(on_field(s, "Scute Swarm")) == 51


def test_a_stack_of_copies_needs_automation_paused(cards):
    s = build(cards)
    act(s, "p1", type="create_token", player="p1", token=SWARM)
    (swarm,) = on_field(s, "Scute Swarm")
    with pytest.raises(ActionError, match="Pause automation"):
        act(s, "p1", type="copy_card", card_id=swarm.id, player="p1", count=200, stacked=True)
    assert len(on_field(s, "Scute Swarm")) == 1
