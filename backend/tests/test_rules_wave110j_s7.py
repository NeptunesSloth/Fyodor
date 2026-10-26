"""Wave 110J session 7: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 500.1, 603.4, 122.1: Rasputin Dreamweaver gets a dream counter at the upkeep only if it was untapped as the turn began (before the untap step).
* 614.17: Rasputin Dreamweaver can't have more than seven dream counters, however many are put.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110j_kit import (  # noqa: F401
    EXTRA,
    ability,
    card_db,
    ch,
    check,
    fresh,
    full,
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
