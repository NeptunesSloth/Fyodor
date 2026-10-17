"""Review 42: cards waves 50B-50F made FULL that played wrong (CR 2026-09-25), real Oracle text (tests/fixtures/review42_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 400.7, 614.1a: "When a spell or ability an opponent controls causes you to discard this card, … return this card from your graveyard to your hand
  [to the battlefield] at the beginning of the next end step." (Mangara's Blessing, Sand Golem) returned the card from wherever the discard put it: an
  opponent's Leyline of the Void exiles it instead, and it came back from exile. The ruling (Mangara's Blessing, 2004-10-04): only a card still in the
  graveyard, that never left it, is returned. Quagnoth's "return it to your hand" has no zone: it does come back from exile (its ruling, 2007-05-01).
* Checked and pinned: Psychic Purge's "that player" in a game of three is the opponent whose spell made you discard, not another opponent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import answer
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "review42_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r42", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


# ---- 400.7: "return this card from your graveyard" finds it only in the graveyard ----------------------------------------------------------------
def discarded_into_exile(cards, held):
    """Bob controls Leyline of the Void and makes Alice discard ``held`` with Mind Rot on his turn; play goes on to that turn's end step."""
    s = build(cards, [held], ["Mind Rot", "Leyline of the Void"])
    to_hand(s, held)
    put(s, "Leyline of the Void", "p2")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.priority == "p2", limit=300)
    mana(s, "p2", B=3)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Mind Rot", "p2").id, targets=["p1"])
    answer(s)  # (Leyline of the Void: exiled instead of put into the graveyard; the discard trigger still triggers, 603.10a)
    stops(s)  # (both players get priority in the end step)
    until(s, lambda s: s.state.turn.phase == "end", limit=60)
    answer(s)
    return s


@pytest.mark.parametrize("held", ["Mangara's Blessing", "Sand Golem"])
def test_a_card_discarded_into_exile_is_not_returned_from_your_graveyard(cards, held):
    s = discarded_into_exile(cards, held)
    assert zone_of(s, held) == "p1:exile"
    assert life(s) == (42 if held == "Mangara's Blessing" else 40)  # (the 2 life is gained as the trigger resolves, wherever the card is)
    check(s)


def test_quagnoth_discarded_into_exile_returns_to_your_hand(cards):
    s = discarded_into_exile(cards, "Quagnoth")
    assert zone_of(s, "Quagnoth") == "p1:hand"  # "return it to your hand": from the zone it went to (Quagnoth's ruling)
    check(s)


# ---- pinned: Psychic Purge's "that player" in a game of three ---------------------------------------------------------------------------------
def test_psychic_purge_costs_only_the_opponent_whose_spell_made_you_discard(cards):
    decks = [deck(cards, "Krenko, Mob Boss", [(1, "Psychic Purge"), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [(1, "Mind Rot"), (20, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    to_hand(s, "Psychic Purge")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.priority == "p3", limit=600)
    mana(s, "p3", B=3)
    act(s, "p3", type="cast_spell", card_id=card_named(s, "Mind Rot", "p3").id, targets=["p1"])
    answer(s)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 40, 35)
    check(s)
