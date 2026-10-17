"""Wave 45B: a grant and a block restriction in one sentence (CR 2026-09-25). Real Oracle text of Rhonas's Stalwart (Hour of Devastation).

* 611.2c, 509.1b: "When you do, it gets +1/+1 until end of turn and can't be blocked by creatures with power 2 or less this turn." One subject, two
  instructions (app/rules/turn_grants.py ``_SHARED``): the pump and a "can't be blocked by" restriction until the turn ends. The restriction's own
  template (``_UNBLOCKED``) used to read the whole clause as its subject and refuse it.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import scripts
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_combat import block
from tests.test_rules_conditionals import token_of
from tests.test_rules_wave6e_statics import attack_with
from tests.wave9c_kit import build, check

STALWART = ("You may exert this creature as it attacks. When you do, it gets +1/+1 until end of turn and can't be blocked by creatures with power 2 or "
            "less this turn. (An exerted creature won't untap during your next untap step.)")


def test_the_pump_and_the_block_restriction_are_two_effects_on_the_same_creature():
    effects, _, _ = scripts.parse_effects(
        "It gets +1/+1 until end of turn and can't be blocked by creatures with power 2 or less this turn.", "self")
    assert [e["do"] for e in effects] == ["pump", "restrict"]
    assert effects[1]["rules"] == ['cant_be_blocked_by:sel:{"compare":[["power","<=",2]],"types":["Creature"]}']


def test_an_exerted_rhonas_stalwart_can_not_be_blocked_by_a_creature_with_power_2_or_less(cards):
    """Bob's 2/2 may not block the exerted Stalwart (3/3 for the turn), his 3/3 may."""
    s = build(cards)
    stalwart = token_of(s, "p1", "Stalwart", "Token Creature — Jackal Soldier", "2/2", "Haste\n" + STALWART)
    guard = token_of(s, "p2", "Guard", "Token Creature — Bear", "2/2")
    giant = token_of(s, "p2", "Giant", "Token Creature — Giant", "3/3")
    attack_with(s, stalwart)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and [o.id for o in d.options] == [stalwart.id]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[stalwart.id])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[stalwart.id]).pt == (3, 3)
    with pytest.raises(ActionError, match="can't be blocked"):
        block(s, "p2", (guard, stalwart))
    block(s, "p2", (giant, stalwart))
    check(s)
