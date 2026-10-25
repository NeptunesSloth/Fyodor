"""Wave 110A: instants and sorceries whose last unread sentence is now read (CR 2026-09-25), real Oracle text (tests/fixtures/wave110a_cards.json).
Every scenario checks the replay and a save and a load.

* Berserk - "At the beginning of the next end step, destroy that creature if it attacked this turn." (508.1: declared as an attacker; 603.4 the
  condition is judged as the delayed trigger resolves).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110a_kit import (
    act,
    answer,
    build,
    cast,
    ch,
    check,
    full_test,
    life,
    mana,
    next_turn,
    open_repo,
    pt,
    put,
    stops,
    to_phase,
    zone_of,
)

BERSERK, MANDATE = "Berserk", "Mandate of Peace"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([BERSERK, MANDATE])


def attack(s, c, target="p2"):
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": target}])


@pytest.mark.parametrize("attacks", [True, False])
def test_berserk_destroys_the_creature_at_end_step_only_if_it_attacked(cards, attacks):
    s = build(cards, [BERSERK, "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    next_turn(s)
    stops(s)
    mana(s, G=1)
    cast(s, BERSERK, [bears.id])
    answer(s)
    assert pt(s, "Grizzly Bears") == (4, 2) and "trample" in ch(s, bears).keywords  # (+X/+0, X its power: 2)
    if attacks:
        attack(s, bears)
    to_phase(s, "end")
    answer(s)
    assert zone_of(s, "Grizzly Bears") == ("p1:graveyard" if attacks else "p1:battlefield")
    check(s)


def test_berserk_cant_be_cast_after_combat_damage_begins(cards):
    s = build(cards, [BERSERK, "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    next_turn(s)
    stops(s)
    attack(s, bears)
    to_phase(s, "combat_damage")
    mana(s, G=1)
    with pytest.raises(ActionError):
        cast(s, BERSERK, [bears.id])
    check(s)


def test_mandate_of_peace_ends_combat_and_stops_opponents_casting(cards):
    """724.2: no combat damage, combat left, on to the postcombat main; the opponents can't cast spells this turn."""
    s = build(cards, [MANDATE, "Grizzly Bears"], ["Counterspell"])
    bears = put(s, "Grizzly Bears")
    next_turn(s)
    stops(s)
    attack(s, bears)
    to_phase(s, "declare_blockers")
    mana(s, W=1, C=1)
    cast(s, MANDATE)
    answer(s)
    assert s.state.turn.phase == "main2" and s.state.cards[bears.id].attacking is None
    assert life(s, "p2") == 40
    mana(s, "p2", U=2)
    with pytest.raises(ActionError):
        cast(s, "Counterspell", [bears.id], pid="p2")
    assert zone_of(s, MANDATE) == "p1:exile"  # (724.2b: the resolving spell too)
    check(s)


def test_mandate_of_peace_cant_be_cast_outside_combat(cards):
    s = build(cards, [MANDATE])
    mana(s, W=1, C=1)
    with pytest.raises(ActionError):
        cast(s, MANDATE)
