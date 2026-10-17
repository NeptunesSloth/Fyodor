"""Wave 49A: "blocked creature" (CR 2026-09-25), real Oracle text (tests/fixtures/wave49a_blocked_cards.json, from data/cards.sqlite). Every scenario checks the replay and a
save and a load.

* 509.1h: an attacking creature that has become blocked is a "blocked creature" - "Destroy target blocked creature." (Smite), "Warpath deals 3 damage to each blocking
  creature and each blocked creature." (Warpath), "{R}{G}: Each blocked creature gets +1/+0 and gains trample until end of turn." (Tattermunge Witch), "Until end of turn,
  target blocked creature you control gets +X/+0 and gains trample …" (Duelist's Flame), "… dealt by target blocked creature this turn" (Benalish Missionary). An
  unblocked attacker is no blocked creature, and neither is a creature that isn't attacking.
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
from tests.test_rules_wave34b_activated import ask, attack, next_turn, settle, stops
from tests.wave9c_kit import build, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49a_blocked_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49a", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Smite", "Warpath", "Tattermunge Witch", "Benalish Missionary", "Duelist's Flame"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def combat(cards, spell):
    """Alice's two Grizzly Bears attack; Bob's one blocks the first. Alice has priority in the declare blockers step with ``spell`` in hand."""
    s = build(cards, ["Grizzly Bears", "Grizzly Bears", spell], ["Grizzly Bears"])
    stops(s)
    first, second = (c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1")
    for c in (first, second):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    blocker = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    attack(s, first, second)
    assert ask(s).kind == "declare_blockers"
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": first.id}])
    assert s.state.rules.decision is None
    return s, first, second, blocker


def test_the_cards_are_full(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_smite_destroys_a_blocked_creature_but_not_an_unblocked_one(cards):
    s, first, second, _ = combat(cards, "Smite")
    mana(s, W=1)
    smite = to_hand(s, "Smite")
    with pytest.raises(ActionError):  # the second Bears were not blocked
        act(s, "p1", type="cast_spell", card_id=smite.id, targets=[second.id])
    act(s, "p1", type="cast_spell", card_id=smite.id, targets=[first.id])
    settle(s)
    assert s.state.cards[first.id].zone == "p1:graveyard" and s.state.cards[second.id].zone == "p1:battlefield"
    check(s)


def test_warpath_hits_each_blocking_creature_and_each_blocked_creature(cards):
    s, first, second, blocker = combat(cards, "Warpath")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Warpath").id)
    settle(s)
    assert s.state.cards[first.id].zone == "p1:graveyard" and s.state.cards[blocker.id].zone == "p2:graveyard"
    assert s.state.cards[second.id].zone == "p1:battlefield" and s.state.cards[second.id].damage == 0  # unblocked: untouched
    check(s)


def test_a_creature_that_is_not_attacking_is_no_blocked_creature(cards):
    s = build(cards, ["Grizzly Bears", "Smite"])
    bears = put(s, "Grizzly Bears")
    mana(s, W=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Smite").id, targets=[bears.id])
    check(s)
