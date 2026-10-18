"""Wave 51F: Incubation Druid (CR 2026-09-25), real Oracle text (tests/fixtures/wave51f_mana_cards.json, from data/cards.sqlite). Every scenario checks the replay and a
save and a load.

* "{T}: Add one mana of any type that a land you control could produce. If this creature has a +1/+1 counter on it, add three mana of that type instead." - 605.3a: a mana
  ability resolves as it is activated, so the counter is looked at then; 106.1b: the types are colors and colorless; 106.7: only the mana lands you control could produce.
* "{3}{G}{G}: Adapt 3." (701.46a): the counters come from its own ability, and with them the Druid taps for three.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ability, next_turn, settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51f_mana_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51m", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def produced(s, name="Incubation Druid"):
    """The mana the Druid's mana ability can add right now (options resolved against the table)."""
    return [ab.options for _, ab in casting.mana_abilities(s.state, card_named(s, name), s.cards)]


def game(cards, lands=1):
    """Alice has the Druid (since the turn began) and ``lands`` Forests on the battlefield, an Island in her library too."""
    s = build(cards, ["Incubation Druid", "Kitchen Finks", "Island"])
    druid = put(s, "Incubation Druid")
    for _ in range(lands):
        put(s, "Forest")
    next_turn(s)
    return s, druid


def test_incubation_druid_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Incubation Druid")).level == "FULL"


def test_without_a_counter_it_adds_one_mana_of_a_type_a_land_could_produce(cards):
    s, druid = game(cards)
    assert produced(s) == [(("G",),)]  # Forests only: green
    put(s, "Island")
    assert sorted(produced(s)[0]) == [("G",), ("U",)]  # an Island too: either type
    check(s)


def test_with_no_land_there_is_nothing_to_add(cards):
    s, druid = game(cards, lands=0)
    assert produced(s) == []  # 106.7
    check(s)


def test_with_a_counter_it_adds_three_mana_of_the_same_type(cards):
    s, druid = game(cards)
    put(s, "Island")
    act(s, "p1", type="counter", card_ids=[druid.id], kind="+1/+1", delta=1)
    assert sorted(produced(s)[0]) == [("G", "G", "G"), ("U", "U", "U")]  # three of one type, not a mix
    check(s)


def test_adapt_gives_the_counters_and_then_the_druid_pays_for_a_three_mana_spell_alone(cards):
    s, druid = game(cards)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:battlefield")
    finks = to_hand(s, "Kitchen Finks")
    act(s, "p1", type="tap", card_ids=[forest.id])
    with pytest.raises(ActionError):  # one mana: not enough for {1}{G/W}{G/W}
        act(s, "p1", type="cast_spell", card_id=finks.id)
    mana(s, G=5)
    act(s, "p1", type="activate_ability", card_id=druid.id, ability=ability(s, "Incubation Druid", contains="Adapt"))
    settle(s)
    assert s.state.cards[druid.id].counters.get("+1/+1") == 3
    act(s, "p1", type="cast_spell", card_id=finks.id)  # the Druid taps for {G}{G}{G}
    settle(s)
    assert zone_of(s, "Kitchen Finks") == "p1:battlefield" and s.state.cards[druid.id].tapped
    check(s)
