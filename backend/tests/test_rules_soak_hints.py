"""Hints and the engine agree (found by tools/soak.py playing whole games with real decks): the castability hint never offers a spell
that cast_spell would refuse because its modes or required targets can't be chosen (601.2b, 601.2c, 700.2a: the cast is illegal, 601.5).
Real Oracle text (tests/fixtures/soak_cards.json); every scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules.view import hints
from tests.game_helpers import act
from tests.soak_kit import cards  # noqa: F401 - the fixture
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, check, mana, put, to_hand


def castable(s, pid="p1"):
    return hints(s.state, pid, s.cards)["castable"]


def test_counter_target_spell_is_offered_only_with_a_spell_to_counter(cards):  # noqa: F811
    """Counterspell ("Counter target spell.") with an empty stack has no legal target: not offered, and the cast is refused. Once a
    spell is on the stack it is offered (and still is for the other player, whose turn it isn't)."""
    s = build(cards, mine=["Counterspell", "Llanowar Elves"])
    counter = to_hand(s, "Counterspell")
    elves = to_hand(s, "Llanowar Elves")
    mana(s, U=2, G=1)
    assert counter.id not in castable(s)
    with pytest.raises(ActionError, match="no legal target"):
        act(s, "p1", type="cast_spell", card_id=counter.id)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=elves.id)
    assert s.state.rules.priority == "p1" and elves.id in s.state.zones["stack"]
    assert counter.id in castable(s)
    check(s)


def test_destroy_target_creature_needs_a_creature(cards):  # noqa: F811
    """Pongify ("Destroy target creature. …") with no creature anywhere: not offered; with one (any player's), offered."""
    s = build(cards, mine=["Pongify"])
    pongify = to_hand(s, "Pongify")
    mana(s, U=1)
    assert pongify.id not in castable(s)
    token(s, "p2", "Bear", "2/2")
    assert pongify.id in castable(s)
    check(s)


def test_a_gift_card_in_hand_gets_its_hints(cards):  # noqa: F811
    """Octomancer ("Gift an Octopus …"): with it in hand the hints are built (choosing an opponent is the whole gift cost, 702.174a: no
    cost part to check) and offer the promise; cast with it, the opponent gets the 8/8 Octopus as it enters."""
    s = build(cards, mine=["Octomancer"])
    octo = to_hand(s, "Octomancer")
    mana(s, U=2, G=3)
    h = hints(s.state, "p1", s.cards)
    assert octo.id in h["castable"] and [o["id"] for o in h["optional_costs"][octo.id]] == [f"{octo.id}:gift"]
    assert s.view("p1")["rules"]["hints"]["optional_costs"][octo.id]
    act(s, "p1", type="cast_spell", card_id=octo.id, optional_costs=[f"{octo.id}:gift"], gift_to="p2")
    settle(s)
    assert s.state.cards[octo.id].zone == "p1:battlefield"
    assert [c.name for c in s.state.cards.values() if c.zone == "p2:battlefield" and c.token] == ["Octopus"]
    check(s)


def test_channel_with_nothing_to_destroy_is_not_offered(cards):  # noqa: F811
    """Boseiju, Who Endures ("Channel — {1}{G}, Discard this card: Destroy target artifact, enchantment, or nonbasic land an opponent
    controls. …"): with only basic lands across the table the ability has no legal target (602.2b → 601.2c), so the hint doesn't offer it
    and the activation is refused; once Bob has an artifact it is offered and destroys it."""
    s = build(cards, mine=["Boseiju, Who Endures"], theirs=["Sol Ring"])
    boseiju = to_hand(s, "Boseiju, Who Endures")
    mana(s, G=2)
    channel = {"card_id": boseiju.id, "ability": 1}
    assert channel not in hints(s.state, "p1", s.cards)["activatable"]
    with pytest.raises(ActionError, match="no legal target"):
        act(s, "p1", type="activate_ability", **channel)
    ring = put(s, "Sol Ring", "p2")
    assert channel in hints(s.state, "p1", s.cards)["activatable"]
    act(s, "p1", type="activate_ability", targets=[ring.id], **channel)
    settle(s)
    assert s.state.cards[ring.id].zone == "p2:graveyard" and s.state.cards[boseiju.id].zone == "p1:graveyard"
    check(s)
