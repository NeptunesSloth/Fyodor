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
