"""-- engine token stacks -- attacking with part of a stack (docs/TOKEN_STACKS.md §4). The declare-attackers decision names the stack once;
an attacker declaration with ``count`` attacks with that many members: the others are split off in the same action and stay home
(508.1a: each member is its own creature). A part of at most 100 is spread into separate tokens at the next action, still attacking.

Real Oracle text (the token-stack kit); every scenario checks the replay and a save/load round trip (wave9c_kit.check).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_engine_token_stacks import (
    card_db,
    finish_combat,
    goblins,
    members,
    stack_of,
    stacked,
    to_attack,
    until_phase,
)
from tests.wave9c_kit import check

__all__ = ["card_db"]  # (the kit's card database fixture)


def ready(cards):
    """512 Goblins in one stack, past their summoning sickness, Bob at 1,000 life, Alice declaring attackers."""
    s = stacked(cards)
    until_phase(s, "p2", "main1")
    until_phase(s, "p1", "main1")
    act(s, "p2", type="set_life", player="p2", value=1000)
    stack = stack_of(s)
    to_attack(s)
    return s, stack


@pytest.mark.parametrize("count", [150, 3])
def test_attacking_with_some_of_a_stack(cards, count):
    """Attack with 150 (or 3) of the 512 Goblins: Bob takes exactly that many; the rest stay home untapped, as one stack."""
    s, stack = ready(cards)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": stack.id, "target": "p2", "count": count}])
    part = s.state.cards[stack.id]
    assert part.quantity == count and part.tapped
    home = next(c for c in goblins(s) if c.id != stack.id)
    assert home.quantity == 512 - count and not home.tapped
    finish_combat(s)
    assert s.state.players["p2"].life == 1000 - count
    assert members(s) == 512
    assert sum(c.quantity for c in goblins(s) if c.tapped) == count
    check(s)


def test_count_of_the_whole_stack_attacks_with_all(cards):
    s, stack = ready(cards)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": stack.id, "target": "p2", "count": 512}])
    assert len(goblins(s)) == 1
    finish_combat(s)
    assert s.state.players["p2"].life == 1000 - 512
    check(s)


def test_a_count_bigger_than_the_stack_is_refused(cards):
    s, stack = ready(cards)
    with pytest.raises(ActionError, match="only 512"):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": stack.id, "target": "p2", "count": 513}])
    assert s.state.cards[stack.id].quantity == 512 and len(goblins(s)) == 1  # nothing happened
    check(s)
