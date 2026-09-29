""""At the beginning of [whose] [step]" triggers (CR 503.1a upkeep, 504 draw, 505 main phases,
507 beginning of combat, 513 end step; 513.1a "the end step" = each end step), one generic
trigger: whose step it is decides (yours, each, each opponent's, enchanted player's, the
enchanted permanent's controller's)."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_attachments import build, token


def life_after_turns(s, phase_goal: int = 2) -> None:
    """Pass priority through ``phase_goal`` full turns (both players)."""
    start = s.state.turn.number
    for _ in range(400):
        if s.state.turn.number >= start + phase_goal:
            return
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            if d.kind == "declare_attackers":
                act(s, d.player, type="declare_attackers", attackers=[])
            elif d.kind == "declare_blockers":
                act(s, d.player, type="declare_blockers", blockers=[])
            elif d.kind in ("order", "choose_cards"):
                act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: d.max_choices or len(ids)])
            else:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[:1])
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("the turns didn't advance")


@pytest.mark.parametrize(("text", "gains"), [
    ("At the beginning of combat on your turn, you gain 1 life.", 1),
    ("At the beginning of each combat, you gain 1 life.", 2),
    # (the window covers three upkeeps: Bob's, Alice's, and Bob's next one, which the pass
    # that starts his turn also resolves)
    ("At the beginning of each upkeep, you gain 1 life.", 3),
    ("At the beginning of each player's upkeep, you gain 1 life.", 3),
    ("At the beginning of each opponent's upkeep, you gain 1 life.", 2),
    ("At the beginning of your draw step, you gain 1 life.", 1),
    ("At the beginning of your first main phase, you gain 1 life.", 1),
    ("At the beginning of your second main phase, you gain 1 life.", 1),
    ("At the beginning of each end step, you gain 1 life.", 2),
    ("At the beginning of the end step, you gain 1 life.", 2),
    ("At the beginning of each opponent's end step, you gain 1 life.", 1),
    ("At the beginning of combat on each opponent's turn, you gain 1 life.", 1),
])
def test_step_triggers(cards, text, gains):
    s = build(cards)  # Alice's first main phase
    token(s, "p1", "Watcher", text=text)
    act(s, "p1", type="pass_priority", until="next_turn")  # → from here: Bob's turn, then Alice's
    life = s.state.players["p1"].life
    life_after_turns(s, 2)
    assert s.state.players["p1"].life == life + gains, text


def test_enchanted_players_upkeep(cards):
    s = build(cards, "Holy Strength")
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Hex", "type_line": "Token Enchantment — Aura Curse",
        "text": "Enchant player\nAt the beginning of enchanted player's upkeep, you gain 1 life."})
    hex_ = next(c for c in s.state.cards.values() if c.name == "Hex")
    act(s, "p1", type="attach", card_ids=[hex_.id], to="p2")
    act(s, "p1", type="pass_priority", until="next_turn")
    life = s.state.players["p1"].life
    life_after_turns(s, 2)
    assert s.state.players["p1"].life == life + 2  # only in Bob's upkeeps (two in the window), not Alice's
