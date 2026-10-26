"""Wave 110M: "You may reveal the first card you draw each turn as you draw it." 701.20a (a revealed card is shown to everyone), 121.2 (a draw is one card at a time: the turn's first one).
The question is the drawing player's own, asked before anyone gets priority; "Whenever you reveal an instant or sorcery card this way" triggers (603.2) only for such a card.
Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110m_kit import *

EISENHORN = "Inquisitor Eisenhorn"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([EISENHORN])


def table(cards, top):
    s = build(cards, [EISENHORN, "Lightning Bolt", "Grizzly Bears"], ["Elite Vanguard"], forests=20)
    put(s, EISENHORN)
    for n in (top, "Grizzly Bears"):  # (the card Alice draws on turn 3 is on top; one under it is drawn by nothing)
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p1", type="move", card_ids=[card_named(s, top).id], to={"player": "p1", "zone": "library"}, position="top")
    return s


def to_question(s):
    stops(s)
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and "Reveal" in d.prompt:
            return d
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def cherubaels(s):
    return [c for c in s.state.cards.values() if c.name == "Cherubael" and c.zone == "p1:battlefield"]


def test_revealing_an_instant_makes_cherubael(cards):
    s = table(cards, "Lightning Bolt")
    d = to_question(s)
    assert "Lightning Bolt" in d.prompt and d.player == "p1"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
    answer(s)
    (token,) = cherubaels(s)
    assert ch(s, token).pt == (4, 4) and "flying" in ch(s, token).keywords and "Legendary" in ch(s, token).supertypes
    assert any(c.name == "Lightning Bolt" and c.zone == "p1:hand" for c in s.state.cards.values())
    check(s)


def test_revealing_a_nonland_noninstant_does_not_trigger(cards):
    s = table(cards, "Grizzly Bears")
    d = to_question(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
    answer(s)
    assert not cherubaels(s)
    check(s)


def test_declining_reveals_nothing(cards):
    s = table(cards, "Lightning Bolt")
    d = to_question(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["no"])
    answer(s)
    assert not cherubaels(s)
    check(s)


# -- Sen Triplets ------------------------------------------------------------------------------------------------------------------------------
TRIPLETS = "Sen Triplets"
test_triplets_full = full_test([TRIPLETS])


def triplets_table(cards):
    from app.game.visibility import hand_revealed

    s = build(cards, [TRIPLETS], ["Lightning Bolt", "Forest", "Grizzly Bears"], forests=20)
    put(s, TRIPLETS)
    s.state.rules.controlled_since[card_named(s, TRIPLETS).id].turn = 0
    for n in ("Lightning Bolt", "Forest", "Grizzly Bears"):
        act(s, "p2", type="move", card_ids=[card_named(s, n, "p2").id], to={"player": "p2", "zone": "hand"})
    assert not hand_revealed(s.state, card_named(s, "Lightning Bolt", "p2"))
    stops(s)
    next_turn(s)  # Alice's upkeep: the trigger chooses Bob (the only opponent)
    return s


def test_the_opponents_hand_is_revealed_and_cannot_act_this_turn(cards):
    from app.game.errors import ActionError
    from app.game.visibility import hand_revealed

    s = triplets_table(cards)
    assert hand_revealed(s.state, card_named(s, "Lightning Bolt", "p2"))
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=["p1"])
    check(s)


def test_the_controller_casts_a_spell_from_that_hand_with_their_own_mana(cards):
    s = table_cast(cards)
    assert zone_of(s, "Lightning Bolt", "p2") == "p2:graveyard" and life(s, "p2") == 37  # (cast by Alice: it goes to its owner's graveyard)
    check(s)


def table_cast(cards):
    s = triplets_table(cards)
    bolt = card_named(s, "Lightning Bolt", "p2")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer(s)
    return s


def test_the_controller_plays_a_land_from_that_hand_and_controls_it(cards):
    s = triplets_table(cards)
    forest = card_named(s, "Forest", "p2")
    act(s, "p1", type="play_land", card_id=forest.id)
    assert s.state.cards[forest.id].zone == "p1:battlefield" and s.state.cards[forest.id].controller == "p1" and s.state.cards[forest.id].owner == "p2"
    check(s)


# -- God-Eternal Kefnet ------------------------------------------------------------------------------------------------------------------------
KEFNET = "God-Eternal Kefnet"
test_kefnet_full = full_test([KEFNET])


def kefnet_question(cards, top="Murder"):
    s = build(cards, [KEFNET, top, "Grizzly Bears"], ["Elite Vanguard"], forests=20)
    put(s, KEFNET)
    put(s, "Elite Vanguard", "p2")
    for n in (top,):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p1", type="move", card_ids=[card_named(s, "Grizzly Bears").id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p1", type="move", card_ids=[card_named(s, top).id], to={"player": "p1", "zone": "library"}, position="top")
    return s, to_question(s)


def copies_of(s, name):
    return [c for c in s.state.cards.values() if c.name == name and c.is_token and c.owner == "p1"]


def test_kefnet_copies_the_revealed_card_and_the_copy_costs_two_less(cards):
    s, d = kefnet_question(cards)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
    mana(s, B=2)  # {1}{B}{B} less {2} is {B}{B}
    vanguard = card_named(s, "Elite Vanguard", "p2")
    for _ in range(30):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if "yes" in ids else vanguard.id if vanguard.id in ids else ids[0]])
    assert zone_of(s, "Elite Vanguard", "p2") == "p2:graveyard"
    assert any(c.name == "Murder" and c.zone == "p1:hand" for c in s.state.cards.values() if not c.is_token)  # (the revealed card itself stays in hand)
    assert not copies_of(s, "Murder") or all(c.zone not in ("p1:hand",) for c in copies_of(s, "Murder"))
    check(s)


def test_a_copy_that_is_not_cast_ceases_to_exist(cards):
    s, d = kefnet_question(cards)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
    for _ in range(30):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["no" if "no" in ids else []] if "no" in ids else [])
    assert not copies_of(s, "Murder")
    assert zone_of(s, "Elite Vanguard", "p2") == "p2:battlefield"
    check(s)
