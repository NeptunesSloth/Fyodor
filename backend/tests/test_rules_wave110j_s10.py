"""Wave 110J session 10: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 603.8: Bomb Squad's "Whenever a creature has four or more fuse counters on it" is a state trigger, one per such creature ("that creature"): it also triggers on
  entering while a creature is already at four, and does not trigger again while it waits or is on the stack.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build, life
from tests.wave110j_kit import EXTRA, card_db, cast_on, check, mana, now, put_new, settle  # noqa: F401

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


APERTURE = "Temporal Aperture"


def _aperture(cards, deck, **kw):
    s = build(cards, [APERTURE, *deck], forests=0, islands=0, **kw)
    ap = put_new(s, APERTURE)
    mana(s, "p1", C=5)
    act(s, "p1", type="activate_ability", card_id=ap.id, ability=0)
    settle(s)
    return s, ap


def test_aperture_is_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(APERTURE)).level == "FULL"


def test_aperture_reveals_and_casts_the_top_card_free(cards):
    """401.5, 118.9: the top card is revealed to everyone and its spell can be cast for no mana."""
    from app.game import visibility

    s, ap = _aperture(cards, ["Grizzly Bears"])
    top = s.state.cards[s.state.zones["p1:library"][0]]
    assert top.name == "Grizzly Bears" and visibility.top_revealed(s.state, top, "p2")
    act(s, "p1", type="cast_spell", card_id=top.id, free=True)
    settle(s)
    assert now(s, top).zone == "p1:battlefield" and now(s, ap).tapped
    check(s)


def test_aperture_plays_a_land_from_the_top(cards):
    s, _ = _aperture(cards, ["Forest"])
    top = s.state.cards[s.state.zones["p1:library"][0]]
    act(s, "p1", type="play_land", card_id=top.id)
    assert now(s, top).zone == "p1:battlefield"
    check(s)


def test_aperture_ends_when_the_card_stops_being_on_top(cards):
    """Another card on top ends it for good, even when the first becomes the top card again; the reveal ends with it."""
    from app.game import visibility

    s, _ = _aperture(cards, ["Grizzly Bears", "Grizzly Bears"])
    first = s.state.cards[s.state.zones["p1:library"][0]]
    other = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.id != first.id and c.owner == "p1" and c.zone == "p1:hand" or
                 c.name == "Grizzly Bears" and c.id != first.id and c.owner == "p1" and c.zone.endswith(":library"))
    act(s, "p1", type="move", card_ids=[other.id], to={"zone": "library"})
    act(s, "p1", type="pass_priority")  # (the table is looked at again: permission expiry)
    act(s, "p1", type="move", card_ids=[other.id], to={"zone": "hand"})
    top = s.state.cards[s.state.zones["p1:library"][0]]
    assert top.id == first.id and not visibility.top_revealed(s.state, top, "p2")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=first.id, free=True)


BREACH = "Dimensional Breach"


def test_breach_is_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(BREACH)).level == "FULL"


def test_breach_returns_one_card_per_owner_each_upkeep(cards):
    """603.7, 611.2b: at each player's upkeep that player returns one exiled card they own (their choice among several); it ends with the last card."""
    from tests.wave110j_kit import to_phase

    s = build(cards, [BREACH, "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"])
    mine = [put_new(s, "Grizzly Bears") for _ in range(2)]
    theirs = put_new(s, "Grizzly Bears", "p2")
    cast_on(s, BREACH)
    assert all(now(s, c).zone.endswith(":exile") for c in (*mine, theirs))
    turn = s.state.turn.number
    to_phase(s, "upkeep", turn + 1)
    settle(s)
    assert now(s, theirs).zone == "p2:battlefield" and all(now(s, c).zone == "p1:exile" for c in mine)
    to_phase(s, "upkeep", turn + 2)
    for _ in range(5):  # (the trigger goes on the stack, then resolves with p1's choice between the two)
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and len(d.options) == 2
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[mine[1].id])
    settle(s)
    assert now(s, mine[1]).zone == "p1:battlefield" and now(s, mine[0]).zone == "p1:exile"
    assert any(t.when.get("whose") == "each110j" for t in s.state.rules.delayed)
    to_phase(s, "upkeep", turn + 4)  # p2's turn: nothing of theirs left; p1's: the last one
    settle(s)
    assert now(s, mine[0]).zone == "p1:battlefield"
    check(s)
    assert not any(t.when.get("whose") == "each110j" and breach_live_test(s, t) for t in s.state.rules.delayed)


def breach_live_test(s, t):
    from app.rules import wave110j_cards
    from app.rules.plan import Plan

    return wave110j_cards.breach_live(Plan(s.state, "p1", s.cards, None), t)


SPLICER = "Phyrexian Splicer"


def test_splicer_is_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(SPLICER)).level == "FULL"


@pytest.mark.parametrize(("mode", "first", "second"), [(0, "Storm Crow", "Youthful Knight"), (1, "Youthful Knight", "Storm Crow")])
def test_splicer_moves_the_chosen_ability(cards, mode, first, second):
    """Choosing flying (0) or first strike (1): the first target loses it, another target gains it until end of turn (613.1f)."""
    from tests.wave110j_kit import ch

    s = build(cards, [SPLICER, "Storm Crow", "Youthful Knight"])
    sp = put_new(s, SPLICER)
    a, b = put_new(s, first), put_new(s, second)
    kw = ("flying", "first strike")[mode]
    assert kw in ch(s, a).keywords and kw not in ch(s, b).keywords
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=sp.id, ability=0, modes=[mode], targets=[a.id, b.id], target_counts=[1, 1])
    settle(s)
    assert kw not in ch(s, a).keywords and kw in ch(s, b).keywords and now(s, sp).tapped
    check(s)


def test_splicer_target_must_have_the_chosen_ability(cards):
    from tests.wave110j_kit import ch  # noqa: F401

    s = build(cards, [SPLICER, "Storm Crow", "Youthful Knight"])
    sp = put_new(s, SPLICER)
    knight, crow = put_new(s, "Youthful Knight"), put_new(s, "Storm Crow")
    mana(s, "p1", C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=sp.id, ability=0, modes=[0], targets=[knight.id, crow.id], target_counts=[1, 1])
    with pytest.raises(ActionError):  # (another target: not the same creature)
        act(s, "p1", type="activate_ability", card_id=sp.id, ability=0, modes=[0], targets=[crow.id, crow.id], target_counts=[1, 1])
