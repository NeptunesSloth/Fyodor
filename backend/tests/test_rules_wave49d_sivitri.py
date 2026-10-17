"""Wave 49D: an attack cost payable in life (CR 2026-09-25), real Oracle text (tests/fixtures/wave49d_small_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 508.1d, 508.1g-h, 119.4: Sivitri, Dragon Master's "+1: Until your next turn, creatures can't attack you or planeswalkers you control unless their controller
  pays 2 life for each of those creatures." - the total cost (2 life for each attacking creature) is determined and paid with the declaration; a player
  can pay life only if their life total is at least that much; nobody is required to pay, so a creature that must attack isn't forced to.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49d_small_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49d", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def table(cards):
    """Alice has Sivitri and has used her +1; it is Bob's declare attackers step with two Grizzly Bears (and Alice's creature on the table)."""
    s = build(cards, ["Sivitri, Dragon Master", "Grizzly Bears"], ["Grizzly Bears", "Grizzly Bears"], forests=30)
    stops(s)
    to_hand(s, "Sivitri, Dragon Master")
    mana(s, U=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sivitri, Dragon Master").id)
    settle(s)
    activate(s, "p1", card_named(s, "Sivitri, Dragon Master"), "+1")
    settle(s)
    put(s, "Grizzly Bears")  # Alice's own creature: the cost is for creatures attacking *her*
    theirs = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]
    for c in theirs:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    to_phase(s, "declare_attackers", turn=2)
    assert s.state.rules.decision.kind == "declare_attackers" and s.state.rules.decision.player == "p2"
    return s, theirs


def test_sivitri_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Sivitri, Dragon Master")).level == "FULL"


def test_each_attacking_creature_costs_two_life(cards):
    s, (one, two) = table(cards)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p1"}, {"card_id": two.id, "target": "p1"}])
    assert life(s, "p2") == 36 and life(s, "p1") == 40  # 2 life for each of the two creatures
    check(s)


def test_attacking_a_planeswalker_of_hers_costs_the_same(cards):
    s, (one, two) = table(cards)
    walker = card_named(s, "Sivitri, Dragon Master")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": one.id, "target": walker.id}])
    assert life(s, "p2") == 38
    check(s)


def test_a_player_without_the_life_cannot_attack_and_may_attack_with_fewer(cards):
    s, (one, two) = table(cards)
    act(s, "p2", type="set_life", player="p2", value=3)
    with pytest.raises(ActionError, match="can't pay"):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p1"}, {"card_id": two.id, "target": "p1"}])  # 4 life
    assert life(s, "p2") == 3
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p1"}])
    assert life(s, "p2") == 1
    check(s)


def test_declining_the_cost_means_no_attack_and_no_life_paid(cards):
    s, _ = table(cards)
    act(s, "p2", type="declare_attackers", attackers=[])
    assert life(s, "p2") == 40
    check(s)


def test_the_effect_ends_at_the_start_of_her_next_turn(cards):
    s, (one, two) = table(cards)
    act(s, "p2", type="declare_attackers", attackers=[])
    to_phase(s, "main1", turn=3)  # Alice's next turn begins: "until your next turn" is over
    to_phase(s, "declare_attackers", turn=4)
    assert life(s, "p2") == 40
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p1"}])
    assert life(s, "p2") == 40
    check(s)
