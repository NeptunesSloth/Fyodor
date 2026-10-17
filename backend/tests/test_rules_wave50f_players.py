"""Wave 50F: "for each player / opponent, … target … that player controls / from that player's graveyard" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave50f_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 603.3d, 115.1, 601.2c: one group of targets for each player (Nils, Discipline Enforcer: the controller too) or opponent (Tasha, the Witch Queen;
  Sepulchral Primordial: a card in that opponent's graveyard); a sentence before it ("Draw a card.") is carried out once, not once per opponent.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, to_phase
from tests.test_rules_wave50f_small import cards, cast_from_hand, settle  # noqa: F401  (cards: the fixture)
from tests.wave9c_kit import build, card_named, check, put


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


@pytest.mark.parametrize("name", ["Tasha, the Witch Queen", "Sepulchral Primordial"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_tasha_draws_once_then_exiles_an_instant_from_the_opponents_graveyard(cards):
    s = build(cards, ["Tasha, the Witch Queen"], ["Lightning Bolt", "Grizzly Bears"])
    tasha = put(s, "Tasha, the Witch Queen")
    bolt = card_named(s, "Lightning Bolt", "p2")
    bears = card_named(s, "Grizzly Bears", "p2")
    for c in (bolt, bears):
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    before = hand(s)
    activate(s, "p1", tasha, "+1")
    settle(s, target="Lightning Bolt")
    assert hand(s) == before + 1 and s.state.cards[bolt.id].zone == "p2:exile" and s.state.cards[bears.id].zone == "p2:graveyard"
    assert s.state.cards[bolt.id].counters.get("page") == 1
    check(s)


def test_tasha_with_no_instant_or_sorcery_still_draws(cards):
    s = build(cards, ["Tasha, the Witch Queen"], ["Grizzly Bears"])
    tasha = put(s, "Tasha, the Witch Queen")
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    before = hand(s)
    activate(s, "p1", tasha, "+1")
    settle(s)
    assert hand(s) == before + 1 and s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def test_nils_puts_a_counter_on_a_creature_of_each_player_including_its_controller(cards):
    s = build(cards, ["Nils, Discipline Enforcer", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Nils, Discipline Enforcer")
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    to_phase(s, "end")
    settle(s, target="Grizzly Bears")
    assert s.state.cards[mine.id].counters.get("+1/+1") == 1 and s.state.cards[theirs.id].counters.get("+1/+1") == 1
    check(s)


def test_sepulchral_primordial_takes_a_creature_from_the_opponents_graveyard(cards):
    s = build(cards, ["Sepulchral Primordial"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    cast_from_hand(s, "Sepulchral Primordial", B=2, G=5)
    settle(s, answer="yes", target="Grizzly Bears")
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)
