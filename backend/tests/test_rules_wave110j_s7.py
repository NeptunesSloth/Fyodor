"""Wave 110J session 7: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 500.1, 603.4, 122.1: Rasputin Dreamweaver gets a dream counter at the upkeep only if it was untapped as the turn began (before the untap step).
* 704.5r: Rasputin Dreamweaver can't have more than seven dream counters, however they arrive (put, proliferate, moved, enters with).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110j_kit import (  # noqa: F401
    EXTRA,
    ability,
    card_db,
    ch,
    check,
    cost,
    fresh,
    full,
    hand_new,
    life,
    mana,
    now,
    put_new,
    settle,
    to_hand,
    to_phase,
)

RASPUTIN = "Rasputin Dreamweaver"


def test_the_cards_are_full():
    assert full(RASPUTIN)


@pytest.mark.parametrize(("before", "tap_on_turn_2", "after"), [(5, False, 6), (5, True, 5), (7, False, 7)])
def test_rasputin_upkeep_counter(cards, before, tap_on_turn_2, after):
    """Untapped as the turn began: +1 dream counter, capped at seven; tapped as it began (it untaps afterwards): none."""
    s = build(cards, [RASPUTIN])
    r = put_new(s, RASPUTIN)
    act(s, "p1", type="counter", card_ids=[r.id], kind="dream", delta=before - now(s, r).counters.get("dream", 0))
    to_phase(s, "main1", turn=2)
    if tap_on_turn_2:
        act(s, "p1", type="tap", card_ids=[r.id])
    to_phase(s, "main1", turn=3)
    assert now(s, r).counters.get("dream", 0) == after and not now(s, r).tapped
    check(s)



def _rasputin_with(cards, extra=()):
    s = build(cards, [RASPUTIN, *extra])
    return s, put_new(s, RASPUTIN)


def test_rasputin_cap_trims_proliferate(cards):
    """704.5r: Proliferate cannot lift Rasputin over seven; a kind that is not capped still grows."""
    s, r = _rasputin_with(cards, ["Contentious Plan"])
    act(s, "p1", type="counter", card_ids=[r.id], kind="dream", delta=7)
    act(s, "p1", type="counter", card_ids=[r.id], kind="charge", delta=1)
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Contentious Plan").id)
    settle(s, answers=[[r.id]])
    assert now(s, r).counters.get("dream", 0) == 7 and now(s, r).counters.get("charge", 0) == 2
    check(s)


def test_rasputin_cap_trims_a_doubled_enters_with(cards):
    """614.1c + 704.5r: Doubling Season doubles "enters with seven" to fourteen; seven stay."""
    s = build(cards, [RASPUTIN, "Doubling Season"])
    put_new(s, "Doubling Season")
    mana(s, **cost(RASPUTIN))
    c = to_hand(s, RASPUTIN)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert now(s, c).counters.get("dream", 0) == 7
    check(s)


@pytest.mark.parametrize(("fuses", "dies"), [(3, True), (2, False)])
def test_bomb_squad_blows_up_at_four_fuse_counters(cards, fuses, dies):
    """603.4, 701.8: the upkeep counter makes four; the creature loses them all, is destroyed and deals 4 damage to its controller."""
    s = build(cards, ["Bomb Squad", "Templar Knight"])
    put_new(s, "Bomb Squad")
    bear = put_new(s, "Templar Knight")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="fuse", delta=fuses)
    to_phase(s, "upkeep", turn=3)
    settle(s)
    assert (now(s, bear).zone == "p1:graveyard") is dies
    assert life(s, "p1") == (36 if dies else 40) and now(s, bear).counters.get("fuse", 0) == (0 if dies else fuses + 1)
    check(s)


HYDRA = "Rock Hydra"


def test_hydra_is_full():
    assert full(HYDRA)


def _hydra(cards, x):
    s = build(cards, [HYDRA, "Lightning Bolt", "Forest"])
    mana(s, R=2 + x)
    c = to_hand(s, HYDRA)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=x)
    settle(s)
    return s, c


@pytest.mark.parametrize(("x", "left", "alive", "marked"), [(5, 2, True, 0), (3, 0, False, 0)])
def test_hydra_prevents_each_damage_while_a_counter_is_left(cards, x, left, alive, marked):
    """615.5: 3 damage from a Bolt — a counter removed and 1 damage prevented for each, as long as counters remain."""
    s, c = _hydra(cards, x)
    assert now(s, c).counters.get("+1/+1") == x
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[c.id])
    settle(s)
    h = now(s, c)
    assert (h.zone == "p1:battlefield") is alive
    if alive:
        assert h.counters.get("+1/+1", 0) == left and h.damage == marked
    check(s)


def test_hydra_counters_carry_over_between_damage_events(cards):
    """Two Bolts: 5 counters -> 2 -> the second (3 damage, 2 counters) strips the rest and the 0/0 Hydra dies (704.5f)."""
    s = build(cards, [HYDRA, "Lightning Bolt", "Lightning Bolt", "Forest"])
    mana(s, R=9)
    c = to_hand(s, HYDRA)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=5)
    settle(s)
    for left in (2, None):
        bolt = to_hand(s, "Lightning Bolt")
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[c.id])
        settle(s)
        assert (now(s, c).counters.get("+1/+1") == left) if left else now(s, c).zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize(("pick", "counters"), [(0, 2), (1, 3)])
def test_hydra_and_its_own_shield_are_ordered_by_its_controller(cards, pick, counters):
    """616.1: the {R} shield and the Hydra's counters both apply to a Bolt — the controller picks which goes first (5 counters: 5-3 or 5-2)."""
    from tests.wave110j_kit import activate

    s = build(cards, [HYDRA, "Lightning Bolt", "Forest"])
    mana(s, R=9)
    c = to_hand(s, HYDRA)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=5)
    settle(s)
    activate(s, now(s, c), "{R}:")
    settle(s)
    bolt = to_hand(s, "Lightning Bolt")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[c.id])
    settle(s, answers=[[s.state.rules.decision.options[pick].id] if s.state.rules.decision else None])
    assert now(s, c).counters == {"+1/+1": counters} and now(s, c).damage == 0
    check(s)


def test_echo_chamber_is_full():
    assert full("Echo Chamber")


def test_echo_chamber_copies_the_creature_an_opponent_picks(cards):
    """601.2c, 115.1: the opponent announces the target among creatures THEY control; the copy token is mine, has haste, and is exiled at the next end step (603.7)."""
    s = build(cards, ["Echo Chamber", "Grizzly Bears"], ["Grizzly Bears", "Grizzly Bears", "Templar Knight"])
    chamber = put_new(s, "Echo Chamber")
    mine = put_new(s, "Grizzly Bears")
    put_new(s, "Grizzly Bears", "p2")
    theirs = put_new(s, "Templar Knight", "p2")
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=chamber.id, ability=ability(s, chamber, "{4}"))
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["p2"])
    d = s.state.rules.decision
    assert d.player == "p2" and theirs.id in {o.id for o in d.options} and mine.id not in {o.id for o in d.options}
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[theirs.id])
    settle(s)
    token = next(c for c in s.state.cards.values() if c.token and c.zone == "p1:battlefield")
    assert token.name == "Templar Knight" and "haste" in ch(s, token).keywords
    to_phase(s, "main1", turn=2)
    assert not any(c.token and c.zone == "p1:battlefield" for c in s.state.cards.values())
    check(s)


def test_keeper_is_full():
    assert full("Keeper of the Dead")


@pytest.mark.parametrize(("mine", "theirs", "legal"), [(2, 0, True), (3, 1, True), (1, 0, False), (2, 1, False)])
def test_keeper_needs_an_opponent_with_two_fewer_creature_cards_in_graveyard(cards, mine, theirs, legal):
    """601.2c: the opponent is a target chosen as it is activated, with at least two fewer creature cards in their graveyard than you; then a nonblack creature they control dies."""
    from app.game.errors import ActionError

    s = build(cards, ["Keeper of the Dead", *["Grizzly Bears"] * (mine + 1)], ["Grizzly Bears"] * (theirs + 1))
    keeper = put_new(s, "Keeper of the Dead")
    s.state.rules.controlled_since[keeper.id].turn = 0
    for _ in range(mine):
        act(s, "p1", type="move", card_ids=[fresh(s, "Grizzly Bears").id], to={"zone": "graveyard"})
    for _ in range(theirs):
        act(s, "p2", type="move", card_ids=[fresh(s, "Grizzly Bears", "p2").id], to={"zone": "graveyard"})
    victim = put_new(s, "Grizzly Bears", "p2")
    mana(s, B=1)
    pay = {"type": "activate_ability", "card_id": keeper.id, "ability": ability(s, keeper, "{B}"), "targets": ["p2", victim.id], "target_counts": [1, 1]}
    if not legal:
        with pytest.raises(ActionError):
            act(s, "p1", **pay)
        return
    act(s, "p1", **pay)
    settle(s)
    assert now(s, victim).zone == "p2:graveyard"
    check(s)


def test_cycle_of_life_is_full():
    assert full("Cycle of Life")


def test_cycle_of_life_targets_only_a_creature_you_cast_this_turn(cards):
    """608.3: the target is the permanent a creature spell of yours became this turn; it is 0/1 until your next upkeep, where it gets a +1/+1 counter (603.7)."""
    s = build(cards, ["Cycle of Life", "Grizzly Bears", "Grizzly Bears"])
    cycle = put_new(s, "Cycle of Life")
    placed = put_new(s, "Grizzly Bears")  # (put on the battlefield, not cast)
    cast = hand_new(s, "Grizzly Bears")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=cast.id)
    settle(s)
    assert now(s, cast).zone == "p1:battlefield" and cast.id != placed.id
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=cycle.id, ability=ability(s, cycle, "Return"), targets=[placed.id])
    act(s, "p1", type="activate_ability", card_id=cycle.id, ability=ability(s, cycle, "Return"), targets=[cast.id])
    settle(s)
    assert now(s, cycle).zone == "p1:hand" and ch(s, cast).pt == (0, 1)
    to_phase(s, "main1", turn=3)
    assert now(s, cast).counters == {"+1/+1": 1} and ch(s, cast).pt == (3, 3)
    check(s)


def test_maria_hill_is_full():
    assert full("Agent Maria Hill")


@pytest.mark.parametrize("hill_taps", [True, False])
def test_maria_hill_grows_and_draws_when_tapped_for_a_teamwork_cost(cards, hill_taps):
    """702.194a: Teamwork taps creatures as a cost; Hill triggers only when she is one of them (603.2)."""
    s = build(cards, ["Agent Maria Hill", "Cruel Alliance", "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"])
    hill, bears = put_new(s, "Agent Maria Hill"), put_new(s, "Grizzly Bears")
    victim = put_new(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Cruel Alliance")
    mana(s, B=1, C=2)
    hand = len(s.state.zones["p1:hand"])
    helpers = [hill, bears] if hill_taps else [bears]
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id], target_counts=[0, 1],
        optional_costs=[f"{spell.id}:teamwork"], cost_choices=[{"component": 0, "cards": [h.id for h in helpers]}])
    settle(s)
    assert now(s, victim).zone == "p2:exile"
    assert now(s, hill).tapped == hill_taps and now(s, hill).counters == ({"+1/+1": 1} if hill_taps else {})
    assert len(s.state.zones["p1:hand"]) == hand - 1 + (1 if hill_taps else 0)
    check(s)
