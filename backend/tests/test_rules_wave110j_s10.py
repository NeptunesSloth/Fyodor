"""Wave 110J session 10: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 603.8: Bomb Squad's "Whenever a creature has four or more fuse counters on it" is a state trigger, one per such creature ("that creature"): it also triggers on
  entering while a creature is already at four, and does not trigger again while it waits or is on the stack.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, life
from tests.wave110j_kit import EXTRA, card_db, cast_on, check, now, put_new, settle  # noqa: F401

SQUAD = "Bomb Squad"


def _fuse(s, c, n):
    act(s, "p2", type="counter", card_ids=[c.id], kind="fuse", delta=n)


def _squad(s):
    """Bomb Squad in play, able to tap."""
    sq = put_new(s, SQUAD)
    s.state.rules.controlled_since[sq.id].turn = 0
    return sq


def test_the_card_is_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(SQUAD)).level == "FULL"


def test_fourth_counter_destroys_and_damages_controller(cards):
    """The fuse counters are removed, the creature destroyed, and it deals 4 to its controller (not Bomb Squad's)."""
    s = build(cards, [SQUAD], ["Grizzly Bears"])
    sq = _squad(s)
    bears = put_new(s, "Grizzly Bears", "p2")
    _fuse(s, bears, 3)
    settle(s)
    assert now(s, bears).counters.get("fuse") == 3 and life(s, "p2") == 40  # 3 counters: nothing
    act(s, "p1", type="activate_ability", card_id=sq.id, ability=0, targets=[bears.id])
    settle(s)
    assert now(s, bears).zone.endswith(":graveyard") and life(s, "p2") == 36 and life(s, "p1") == 40
    check(s)


def test_entering_with_a_creature_already_at_four_triggers(cards):
    s = build(cards, [SQUAD], ["Grizzly Bears"])
    bears = put_new(s, "Grizzly Bears", "p2")
    _fuse(s, bears, 5)
    cast_on(s, SQUAD)
    assert now(s, bears).zone.endswith(":graveyard") and life(s, "p2") == 36
    check(s)


def test_no_second_trigger_while_the_first_waits(cards):
    """603.8: it doesn't trigger again for the same creature while the first instance is waiting or on the stack (even for a fifth counter)."""
    s = build(cards, [SQUAD], ["Grizzly Bears"])
    _squad(s)
    bears = put_new(s, "Grizzly Bears", "p2")
    _fuse(s, bears, 4)
    from app.rules import state_triggers
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", s.cards, None)
    state_triggers.check(plan)
    assert len(plan.rules.pending_triggers) == 1
    plan.state.cards[bears.id].counters["fuse"] = 5
    state_triggers.check(plan)
    assert len(plan.rules.pending_triggers) == 1  # still one: waiting


def test_two_creatures_trigger_separately(cards):
    s = build(cards, [SQUAD], ["Grizzly Bears", "Grizzly Bears"])
    sq = _squad(s)
    a, b = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Grizzly Bears", "p2")
    _fuse(s, a, 4)
    _fuse(s, b, 3)
    act(s, "p1", type="activate_ability", card_id=sq.id, ability=0, targets=[b.id])
    settle(s)
    assert life(s, "p2") == 32 and all(now(s, c).zone.endswith(":graveyard") for c in (a, b))
    check(s)
