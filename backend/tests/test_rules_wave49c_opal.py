"""Wave 49C: the Odyssey/Nemesis "enchantment becomes a creature" cycle (CR 2026-09-25), real Oracle text (tests/fixtures/wave49c_opal_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 205.1a, 611.2a: "it becomes a 3/4 Gargoyle creature with flying and protection from red" (Opal Guardian) - the new card type replaces enchantment, nothing ends it, and the
  intervening "if this permanent is an enchantment" (603.4) is checked as the trigger would go on the stack.
* 603.8, 603.4: the same as a state trigger - "When an opponent controls a creature with power 4 or greater" (Hidden Predators), "When you have 10 or less life" (Opal Avenger),
  "When an opponent has 10 or less life" (Lurking Jackals). Once it is a creature it is no longer an enchantment, so the state does not trigger it again.
* A quoted ability after a keyword ("flying and \\"At the beginning of your upkeep, …\\"", Veiled Apparition) is granted too.
* Veiled Crocodile ("When a player has no cards in hand") stays manual: its ruling says the state can be met in the middle of a resolution, which is not modelled.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle, stops
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49c_opal_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49c", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Opal Guardian", "Hidden Predators", "Opal Avenger", "Lurking Jackals", "Veiled Apparition"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def chars(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id, **kw)
    settle(s)


def bob_casts(s, name, **m):
    """Alice passes in her main phase (every player gets priority, stops on); Bob casts this flash card or instant."""
    act(s, "p1", type="pass_priority")
    mana(s, "p2", **m)
    cast(s, name, "p2")


def test_the_cards_are_full_and_the_crocodile_is_not(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name
    assert coverage.of_card_data(cards.resolve("Veiled Crocodile")).level != "FULL"


def test_opal_guardian_becomes_a_creature_when_an_opponent_casts_a_creature_spell(cards):
    s = build(cards, ["Opal Guardian"], ["Ambush Viper"])
    stops(s)
    put(s, "Opal Guardian")
    assert chars(s, "Opal Guardian").types == {"Enchantment"}
    bob_casts(s, "Ambush Viper", G=1, C=1)
    ch = chars(s, "Opal Guardian")
    assert ch.types == {"Creature"} and ch.subtypes == {"Gargoyle"} and ch.pt == (3, 4)  # (205.1a: no longer an enchantment)
    assert "flying" in ch.granted and "Protection from red." in [a.text for a in ch.abilities]
    check(s)


def test_opal_guardian_ignores_a_noncreature_spell(cards):
    s = build(cards, ["Opal Guardian"], ["Shock"])
    stops(s)
    put(s, "Opal Guardian")
    bob_casts(s, "Shock", R=1)
    assert chars(s, "Opal Guardian").types == {"Enchantment"}
    check(s)


def test_hidden_predators_becomes_a_creature_when_an_opponent_controls_power_four(cards):
    s = build(cards, ["Hidden Predators", "Giant Growth"], ["Grizzly Bears"])
    put(s, "Hidden Predators")
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, G=1)
    cast(s, "Giant Growth", targets=[bears.id])  # 5/5 until end of turn: the table changed, the state now matches
    ch = chars(s, "Hidden Predators")
    assert ch.types == {"Creature"} and ch.subtypes == {"Beast"} and ch.pt == (4, 4)
    check(s)


def test_hidden_predators_ignores_your_own_big_creature(cards):
    s = build(cards, ["Hidden Predators", "Giant Growth", "Grizzly Bears"])
    put(s, "Hidden Predators")
    mine = put(s, "Grizzly Bears")
    mana(s, G=1)
    cast(s, "Giant Growth", targets=[mine.id])  # power 5, but it is Alice's own
    assert chars(s, "Hidden Predators").types == {"Enchantment"}
    check(s)


def test_opal_avenger_becomes_a_creature_at_ten_life_or_less(cards):
    s = build(cards, ["Opal Avenger", "Shock"])
    put(s, "Opal Avenger")
    act(s, "p1", type="set_life", player="p1", value=13)
    mana(s, R=2)
    cast(s, "Shock", targets=["p1"])
    assert chars(s, "Opal Avenger").types == {"Enchantment"}  # 11
    cast(s, "Shock", targets=["p1"])
    ch = chars(s, "Opal Avenger")
    assert ch.types == {"Creature"} and ch.subtypes == {"Soldier"} and ch.pt == (3, 5)  # 9
    act(s, "p1", type="set_life", player="p1", value=20)  # it stays a creature (a layer-4 effect with no duration, 611.2a)
    assert chars(s, "Opal Avenger").types == {"Creature"}
    check(s)


def test_lurking_jackals_watches_the_opponents_life_not_yours(cards):
    s = build(cards, ["Lurking Jackals", "Shock"])
    put(s, "Lurking Jackals")
    act(s, "p1", type="set_life", player="p1", value=5)
    act(s, "p1", type="set_life", player="p2", value=12)
    mana(s, R=2)
    cast(s, "Shock", targets=["p1"])  # Alice at 3: not the opponent
    assert chars(s, "Lurking Jackals").types == {"Enchantment"}
    cast(s, "Shock", targets=["p2"])  # Bob at 10
    ch = chars(s, "Lurking Jackals")
    assert ch.types == {"Creature"} and ch.subtypes == {"Jackal"} and ch.pt == (3, 2)
    check(s)


def test_veiled_apparition_gets_its_flying_and_its_upkeep_ability(cards):
    s = build(cards, ["Veiled Apparition"], ["Shock"])
    stops(s)
    put(s, "Veiled Apparition")
    bob_casts(s, "Shock", R=1)
    ch = chars(s, "Veiled Apparition")
    assert ch.types == {"Creature"} and ch.subtypes == {"Illusion"} and ch.pt == (3, 3) and "flying" in ch.granted
    assert any("sacrifice this creature unless you pay" in a.text for a in ch.abilities)
    check(s)
