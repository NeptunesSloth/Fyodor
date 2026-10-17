"""Wave 50E: "When a spell or ability an opponent controls causes you to discard this card, …" with the card as "it" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave50e_discard_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 701.9a, 603.10a: the trigger of the discarded card itself; "it" is the card, now in the graveyard (Guerrilla Tactics: "it deals 4 damage to any target", Quagnoth: "return it to your hand").
* 400.7: "return this card from your graveyard to your hand [at the beginning of the next end step]" (Mangara's Blessing, Sand Golem: "… to the battlefield with a +1/+1 counter on it"): the card is
  found in the graveyard; "you gain 2 life, and you return …" is two instructions.
* 603.2, 608.2k: "that player loses 5 life" (Psychic Purge) is the opponent whose spell or ability caused the discard, not the player who discarded.
* The discard of your own spell or ability, or of a cost, is no one's doing but yours: nothing triggers (the rulings of Guerrilla Tactics and Pure Intentions).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import answer
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import build, card_named, check, life, mana, pt, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50e_discard_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50e", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA if c["name"] != "Mind Rot"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_the_cards_are_full(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def discard(cards, held, caster="p2"):
    """Alice holds ``held``; ``caster`` (Bob on his turn, Alice on hers) casts Mind Rot at Alice."""
    s = build(cards, [held, "Mind Rot"], ["Mind Rot"])
    to_hand(s, held)
    if caster == "p2":
        until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.priority == "p2", limit=300)
        mana(s, "p2", B=3)
        act(s, "p2", type="cast_spell", card_id=card_named(s, "Mind Rot", "p2").id, targets=["p1"])
    else:
        to_hand(s, "Mind Rot")
        mana(s, "p1", B=3)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Mind Rot").id, targets=["p1"])
    return s


def test_guerrilla_tactics_deals_four_when_an_opponents_spell_discards_it(cards):
    s = discard(cards, "Guerrilla Tactics")
    answer(s, "p2")
    assert zone_of(s, "Guerrilla Tactics") == "p1:graveyard" and life(s, "p2") == 36
    check(s)


def test_guerrilla_tactics_discarded_by_your_own_spell_does_nothing(cards):
    s = discard(cards, "Guerrilla Tactics", "p1")
    answer(s)
    assert zone_of(s, "Guerrilla Tactics") == "p1:graveyard" and life(s, "p2") == 40 and life(s) == 40
    check(s)


def test_psychic_purge_costs_the_opponent_who_made_you_discard_five_life(cards):
    s = discard(cards, "Psychic Purge")
    answer(s)
    assert life(s, "p2") == 35 and life(s) == 40
    check(s)


def test_psychic_purge_discarded_by_your_own_spell_does_nothing(cards):
    s = discard(cards, "Psychic Purge", "p1")
    answer(s)
    assert life(s, "p2") == 40 and life(s) == 40
    check(s)


def test_quagnoth_returns_to_hand_when_an_opponents_spell_discards_it(cards):
    s = discard(cards, "Quagnoth")
    answer(s)
    assert zone_of(s, "Quagnoth") == "p1:hand"
    check(s)


def test_quagnoth_discarded_by_your_own_spell_stays_in_the_graveyard(cards):
    s = discard(cards, "Quagnoth", "p1")
    answer(s)
    assert zone_of(s, "Quagnoth") == "p1:graveyard"
    check(s)


def test_mangaras_blessing_gains_two_now_and_returns_at_the_next_end_step(cards):
    s = discard(cards, "Mangara's Blessing")
    answer(s)
    assert life(s) == 42 and zone_of(s, "Mangara's Blessing") == "p1:graveyard"
    stops(s)  # (both players get priority in the end step)
    until(s, lambda s: s.state.turn.phase == "end", limit=60)
    answer(s)
    assert zone_of(s, "Mangara's Blessing") == "p1:hand"
    check(s)


def test_mangaras_blessing_discarded_by_your_own_spell_stays(cards):
    s = discard(cards, "Mangara's Blessing", "p1")
    answer(s)
    stops(s)  # (both players get priority in the end step)
    until(s, lambda s: s.state.turn.phase == "end", limit=60)
    answer(s)
    assert life(s) == 40 and zone_of(s, "Mangara's Blessing") == "p1:graveyard"
    check(s)


def test_sand_golem_returns_with_a_counter_at_the_next_end_step(cards):
    s = discard(cards, "Sand Golem")
    answer(s)
    assert zone_of(s, "Sand Golem") == "p1:graveyard"
    stops(s)  # (both players get priority in the end step)
    until(s, lambda s: s.state.turn.phase == "end", limit=60)
    answer(s)
    assert zone_of(s, "Sand Golem") == "p1:battlefield" and pt(s, "Sand Golem") == (4, 4)
    check(s)


def test_sand_golem_discarded_by_your_own_spell_stays(cards):
    s = discard(cards, "Sand Golem", "p1")
    answer(s)
    stops(s)  # (both players get priority in the end step)
    until(s, lambda s: s.state.turn.phase == "end", limit=60)
    answer(s)
    assert zone_of(s, "Sand Golem") == "p1:graveyard"
    check(s)
