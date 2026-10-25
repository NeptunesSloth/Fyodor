"""Wave 110K: single-card wordings, real Oracle text (tests/fixtures/wave110k_cards.json). Every scenario checks the replay and a save and a load.

* 608.2d, 800.4: Library of Lat-Nam's mode is chosen on resolution by an opponent (the caster picks which one with several): three cards at the
  next turn's upkeep, or a tutor.
* 111.1, 303.7, 608.2c: Twisted Sewer-Witch makes a Rat, then one Wicked Role for each Rat its controller has, each on its own Rat.
* 608.2d, 118.9, 702.145: Transforming Flourish destroys a permanent you don't control; only if it was destroyed does its controller exile until a nonland
  card and may cast it free.
* 602.2b, 118.3: Bullseye, Death Dealer's activation cost is a choice announced with the activation: sacrifice an artifact or discard a nonland card.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build, life
from tests.wave47b_kit import build3
from tests.wave110k_kit import (  # noqa: F401
    EXTRA,
    activate,
    card_db,
    cast_on,
    ch,
    check,
    full,
    hand_new,
    mana,
    now,
    put_new,
    refused,
    settle,
    to_hand,
    to_phase,
)


def test_bullseye_is_full():
    assert full("Bullseye, Death Dealer")


def _ready(cards):
    """Bullseye in play (its enter trigger declined), a Sol Ring and a Grizzly Bears (a nonland card) as the cost's two sides."""
    s = build(cards, ["Bullseye, Death Dealer", "Sol Ring", "Grizzly Bears"])
    bull = put_new(s, "Bullseye, Death Dealer")
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    s.state.rules.controlled_since[bull.id].turn = 0
    return s, bull, put_new(s, "Sol Ring"), hand_new(s, "Grizzly Bears")


@pytest.mark.parametrize(("side", "zone_of_paid"), [(0, "ring"), (1, "bears")])
def test_bullseye_activation_cost_is_either_side(cards, side, zone_of_paid):
    s, bull, ring, bears = _ready(cards)
    mana(s, C=3)
    before = life(s, "p2")
    act(s, "p1", type="activate_ability", card_id=bull.id, ability=1, targets=["p2"],
        cost_choices=[{"component": 20, "cards": [f"either:{side}"]}])
    settle(s)
    assert life(s, "p2") == before - 2
    assert now(s, bull).tapped
    paid = {"ring": ring, "bears": bears}[zone_of_paid]
    kept = {"ring": bears, "bears": ring}[zone_of_paid]
    assert now(s, paid).zone.endswith(("graveyard",)) and not now(s, kept).zone.endswith("graveyard")
    check(s)


def test_bullseye_cannot_activate_without_either_side(cards):
    s, bull, ring, bears = _ready(cards)
    act(s, "p1", type="move", card_ids=[ring.id, bears.id], to={"zone": "exile"})
    mana(s, C=3)
    refused(s, "activation cost", bull, "{3}", targets=["p2"])


def test_library_of_lat_nam_is_full():
    assert full("Library of Lat-Nam")


def _hand_size(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


@pytest.mark.parametrize("pick", ["0", "1"])
def test_library_of_lat_nam_opponent_chooses_the_mode(cards, pick):
    s = build(cards, ["Library of Lat-Nam", "Sol Ring"])
    c = hand_new(s, "Library of Lat-Nam")
    mana(s, U=1, C=4)
    before = _hand_size(s)
    act(s, "p1", type="cast_spell", card_id=c.id)
    while s.state.zones.get("stack") and s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and [o.id for o in d.options] == ["0", "1"]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[pick])
    settle(s)
    if pick == "1":
        # a tutor: the controller finds a card; the hand lost the sorcery and gained that card
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options)])
            settle(s)
        assert _hand_size(s) == before
    else:
        assert _hand_size(s) == before - 1
        to_phase(s, "upkeep", turn=2)  # the next turn (Bob's), not Alice's next: 603.7 delayed trigger, once
        settle(s)
        assert _hand_size(s) == before - 1 + 3
        to_phase(s, "main1", turn=3)  # only Alice's own draw step adds a card: the delayed trigger fired once
        assert _hand_size(s) == before - 1 + 3 + 1
    check(s)


def test_library_of_lat_nam_controller_names_which_opponent_chooses(cards):
    s = build3(cards, ["Library of Lat-Nam"])
    c = to_hand(s, "Library of Lat-Nam")
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id)
    while s.state.zones.get("stack") and s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and sorted(o.id for o in d.options) == ["p2", "p3"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p3" and [o.id for o in d.options] == ["0", "1"]
    act(s, "p3", type="choose", decision_id=d.id, option_ids=["1"])
    settle(s)
    check(s)


def test_twisted_sewer_witch_is_full():
    assert full("Twisted Sewer-Witch")


def _roles(s):
    return [c for c in s.state.cards.values() if c.name == "Wicked" and c.zone.endswith(":battlefield")]


def test_twisted_sewer_witch_gives_each_rat_a_wicked_role(cards):
    s = build(cards, ["Twisted Sewer-Witch"])
    cast_on(s, "Twisted Sewer-Witch")
    rats = [c for c in s.state.cards.values() if c.name == "Rat" and c.zone.endswith(":battlefield")]
    assert len(rats) == 1 and [r.attached_to for r in _roles(s)] == [rats[0].id]
    assert int(ch(s, rats[0]).pt[0]) == 2  # 1/1 with Wicked's +1/+1
    check(s)


def test_second_witch_counts_the_rat_already_there_and_each_keeps_one_role(cards):
    s = build(cards, ["Twisted Sewer-Witch", "Twisted Sewer-Witch"])
    cast_on(s, "Twisted Sewer-Witch")
    life_before = life(s, "p2")
    cast_on(s, "Twisted Sewer-Witch")
    rats = [c for c in s.state.cards.values() if c.name == "Rat" and c.zone.endswith(":battlefield")]
    assert len(rats) == 2
    # 303.7 / 111.10: a Role replaces another Role you control on the same permanent; the old Role goes to the graveyard and its owner's opponents lose 1 life
    assert sorted(r.attached_to for r in _roles(s)) == sorted(r.id for r in rats)
    assert life(s, "p2") == life_before - 1
    check(s)


def test_transforming_flourish_is_full():
    assert full("Transforming Flourish")


def _flourish(cards, target_name, foe_top):
    from tests.wave110b_kit import top

    s = build(cards, ["Transforming Flourish"], [target_name, *dict.fromkeys(foe_top)])
    victim = put_new(s, target_name, "p2")
    for name in foe_top:
        top(s, name, "p2")
    cast = to_hand(s, "Transforming Flourish")
    mana(s, R=1, C=2)  # {2}{R}
    act(s, "p1", type="cast_spell", card_id=cast.id, targets=[victim.id])
    return s, victim


def _finish(s):
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)] if d.kind != "choose_one" else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def test_flourish_makes_the_controller_exile_to_a_nonland_card_and_cast_it_free(cards):
    s, victim = _flourish(cards, "Grizzly Bears", ["Elvish Visionary", "Island"])  # listed bottom-up: an Island is on top of the Visionary
    _finish(s)
    assert now(s, victim).zone.endswith(":graveyard")
    assert sorted(c.name for c in s.state.cards.values() if c.zone == "p2:exile") == ["Island"]
    knight = [c for c in s.state.cards.values() if c.name == "Elvish Visionary" and c.zone.endswith(":battlefield")]
    assert len(knight) == 1 and knight[0].controller == "p2"
    check(s)


def test_flourish_does_nothing_more_when_the_permanent_survives(cards):
    s, victim = _flourish(cards, "Darksteel Colossus", ["Elvish Visionary"])
    _finish(s)
    assert now(s, victim).zone.endswith(":battlefield")
    assert not [c for c in s.state.cards.values() if c.zone == "p2:exile"]
    check(s)
