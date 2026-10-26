"""Wave 110C: Symbiote Spider-Man's Find New Host (602.2, 611.2a): from the graveyard, a +1/+1 counter on target creature you control, which gains the card's other abilities for good
(the combat damage trigger: look at that many cards, one to hand, the rest to the graveyard)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110c_kit import answer, check, make_db, mana, put, real
from tests.wave110d_kit import ability, move, to_phase

TEXT = ("Whenever this creature deals combat damage to a player, look at that many cards from the top of your library. Put one of them into your hand and the rest into your graveyard.\n"
        "Find New Host — {2}{U/B}, Exile this card from your graveyard: Put a +1/+1 counter on target creature you control. It gains this card's other abilities. Activate only as a sorcery.")
EXTRA = [real("Symbiote Spider-Man", "{2}{U/B}{U/B}", 4, "Legendary Creature — Symbiote Spider Hero", TEXT, ("2", "3"), "UB")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Symbiote Spider-Man")).level == "FULL"


def test_find_new_host_gives_a_counter_and_the_trigger(cards):
    s = build(cards, ["Symbiote Spider-Man", "Grizzly Bears", "Forest", "Forest", "Forest", "Forest"])
    sym = next(c for c in s.state.cards.values() if c.name == "Symbiote Spider-Man")
    bears = put(s, "Grizzly Bears")
    s.state.rules.controlled_since[bears.id].turn = 0
    move(s, sym, "graveyard")
    mana(s, U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=sym.id, ability=ability(s, sym, "Find New Host"), targets=[bears.id])
    answer(s)
    assert s.state.cards[sym.id].zone == "p1:exile" and s.state.cards[bears.id].counters.get("+1/+1") == 1
    to_phase(s, "declare_attackers", turn=3)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (three cards looked at: one to hand, two to the graveyard)
    assert len(s.state.zones["p1:graveyard"]) == 2
    check(s)
