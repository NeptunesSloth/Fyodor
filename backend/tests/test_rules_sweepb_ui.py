"""Sweep B (nov 18): what the table says about a cast. A replicated spell isn't "Kicked" on the stack (702.56), and Pay with mana still
missing names what is missing, as the payment plaque's "Remaining" does, not the whole cost again."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_conditionals import token_of
from tests.test_rules_wave6c_tokens_pumps import build, mana, to_hand
from tests.test_rules_wave15e_keywords import (
    EXTRA,  # noqa: F401  (the fixture cards, Shattering Spree among them)
    card_db,  # noqa: F401  (the module's card database, with EXTRA)
)


def _spree(cards):
    s = build(cards, "Shattering Spree")
    spree = to_hand(s, "Shattering Spree")
    rock = token_of(s, "p2", "Rock", "Token Artifact — Rock", "0/0")
    return s, spree, rock


def test_a_replicated_spell_reads_replicated_not_kicked(cards):
    s, spree, rock = _spree(cards)
    act(s, "p1", type="set_prefs", response="on")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=spree.id, targets=[rock.id], kicker=2)
    tags = s.state.cards[spree.id].stack_info.tags
    assert "Replicated ×2" in tags and not any(t.startswith("Kicked") for t in tags)


def test_pay_with_mana_missing_names_what_is_left(cards):
    s, spree, rock = _spree(cards)
    act(s, "p1", type="set_prefs", payment="self")  # (the table's default: the player taps their own mana)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=spree.id, targets=[rock.id], kicker=1)  # {R}{R}: one {R} in the pool
    d = s.state.rules.decision
    assert d is not None and d.display.get("kind") == "tap_mana"
    with pytest.raises(ActionError, match=r"Tap your mana first: \{R\} isn't paid yet"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])


def test_the_blockers_prompt_says_which_creatures_may_block_more_than_one(cards):
    """509.1a: ``display.limits`` lists a creature that may block several attackers, capped at how many attack (the table offers
    "+ also blocks…" only there); a creature that blocks one isn't listed."""
    from tests.test_rules_wave13b_multiblock import board, to_blocks

    s, a1, a2, wall = board(cards, wall_text="This creature can block any number of creatures.")
    to_blocks(s, a1, a2)
    d = s.view("p2")["rules"]["decision"]
    assert d["kind"] == "declare_blockers"
    assert d["display"]["limits"] == {wall.id: 2}  # (any number: as many as attack)


def test_a_creature_that_blocks_one_is_not_listed(cards):
    from tests.test_rules_wave13b_multiblock import board, to_blocks

    s, a1, a2, _ = board(cards, wall_text="")
    to_blocks(s, a1, a2)
    assert s.view("p2")["rules"]["decision"]["display"]["limits"] == {}
