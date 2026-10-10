"""-- no combat damage (wave 19E) -- "If you do, this creature assigns no combat damage this turn." (510.1a: the creature assigns 0;
a rule-modifying effect for the turn, read by combat._assigns) after "you may draw a card" (Ophidian) and "you may gain control of
target artifact defending player controls" (Kukemssa Pirates). Oracle text from the card database."""

from __future__ import annotations

import pytest

from tests.game_helpers import act, find
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import replay_matches

OPHIDIAN = ("Whenever this creature attacks and isn't blocked, you may draw a card. If you do, this creature assigns no combat damage "
            "this turn.")
PIRATES = ("Whenever this creature attacks and isn't blocked, you may gain control of target artifact defending player controls. If "
           "you do, this creature assigns no combat damage this turn.")


def through_combat(s, answer):
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            pick = [i for i in ids if i == answer] if answer in ids else ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
            continue
        if s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


@pytest.mark.parametrize("yes", [True, False])
def test_assigns_no_combat_damage_after_drawing(cards, yes):
    s = table(cards)
    snake = creature(s, "p1", "Ophidian", "1/3", OPHIDIAN)
    automate(s)
    hand = len(s.state.zones.get("p1:hand", []))
    attack(s, (snake, "p2"))
    through_combat(s, "yes" if yes else "no")
    assert s.state.players["p2"].life == (40 if yes else 39)  # 510.1a: it assigned no combat damage only if the card was drawn
    assert len(s.state.zones.get("p1:hand", [])) == hand + (1 if yes else 0)
    replay_matches(s)


def test_gain_control_of_an_artifact_then_no_combat_damage(cards):
    s = table(cards)
    pirates = creature(s, "p1", "Kukemssa Pirates", "2/2", PIRATES)
    act(s, "p2", type="create_token", player="p2", token={"name": "Trinket", "type_line": "Token Artifact — Test"})
    trinket = find(s.state, "Trinket", "p2")
    automate(s)
    attack(s, (pirates, "p2"))
    through_combat(s, "yes")
    assert s.state.cards[trinket.id].controller == "p1" and s.state.players["p2"].life == 40
    replay_matches(s)
