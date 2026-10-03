"""Wave 10B: static wordings that turned up as the sole blocker of many cards (real Oracle text throughout).

* "Creatures your opponents control lose flying and can't have or gain flying." (the Archetypes, 613.1f; the denial
  holds whatever the timestamps): app/rules/statics.py ``_DENY``, app/rules/layers.py ``_layer6``.
* The Gates ("This land enters tapped." and, on its own line, "As this land enters, choose a color other than green.",
  614.1c, 614.1d, 614.12a): app/rules/entry_forms.py ``standalone_choice``.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.state import GameState
from app.rules import coverage
from app.rules.plan import Plan
from app.rules.casting import mana_sources
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_permissions import build, put
from tests.test_rules_wave5f_types_entries import rules

EXTRA = [
    card('Manor Gate', set_code="tst", number="10B100", type_line='Land',
         oracle_text='This land enters tapped.\nAs this land enters, choose a color other than green.\n{T}: Add {G} or one mana of the chosen color.'),  # noqa: E501
    card('Sea Gate', set_code="tst", number="10B101", type_line='Land',
         oracle_text='This land enters tapped.\nAs this land enters, choose a color other than blue.\n{T}: Add {U} or one mana of the chosen color.'),  # noqa: E501
]
EXTRA += [
    card('Archetype of Imagination', set_code="tst", number="10B110", mana_cost='{4}{U}{U}', cmc=6.0, type_line='Enchantment Creature — Human Wizard', oracle_text='Creatures you control have flying.\nCreatures your opponents control lose flying and can\'t have or gain flying.', power='3', toughness='2', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Archetype of Courage', set_code="tst", number="10B111", mana_cost='{1}{W}{W}', cmc=3.0, type_line='Enchantment Creature — Human Soldier', oracle_text='Creatures you control have first strike.\nCreatures your opponents control lose first strike and can\'t have or gain first strike.', power='2', toughness='2', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Serra Angel', set_code="tst", number="10B112", mana_cost='{3}{W}{W}', cmc=5.0, type_line='Creature — Angel', oracle_text="Flying\nVigilance (Attacking doesn't cause this creature to tap.)", power='4', toughness='4', colors=['W'], color_identity=['W'], keywords=['Flying', 'Vigilance']),  # noqa: E501
]
GATES = ["Manor Gate", "Sea Gate"]
ARCHETYPES = ["Archetype of Imagination", "Archetype of Courage"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


@pytest.mark.parametrize("name", GATES)
def test_gates_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_a_gate_enters_tapped_with_a_color_other_than_its_own(cards):
    s = build(cards, [(1, "Manor Gate")])
    gate = put(s, "Manor Gate", "hand")
    act(s, "p1", type="play_land", card_id=gate.id)
    d = rules(s).decision  # 614.12a: chosen before it enters
    assert d is not None and [o.id for o in d.options] == ["White", "Blue", "Black", "Red"]  # not green
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Blue"])
    gate = s.state.cards[gate.id]
    assert gate.zone == "p1:battlefield" and gate.tapped and gate.choices == {"Chosen color": "Blue"}  # 614.1d
    act(s, "p1", type="tap", card_ids=[gate.id], tapped=False)
    options = {o for src in mana_sources(s.state, "p1", cards) if src.card_id == gate.id for o in src.options}
    assert options == {("G",), ("U",)}
    roundtrip(s)


@pytest.mark.parametrize("name", ARCHETYPES)
def test_archetypes_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def keywords(s, cards, c):
    return set(Plan(s.state, "p1", cards, None).ch(s.state.cards[c.id]).keywords)


def test_an_archetype_takes_flying_from_the_opponents_creatures_and_gives_it_to_yours(cards):
    s = build(cards, [(1, "Archetype of Imagination"), (1, "Grizzly Bears")], [(1, "Serra Angel"), (1, "Grizzly Bears")])
    bears = put(s, "Grizzly Bears", "battlefield", pid="p1")
    theirs = put(s, "Serra Angel", "battlefield", pid="p2")
    assert "flying" in keywords(s, cards, theirs) and "flying" not in keywords(s, cards, bears)
    put(s, "Archetype of Imagination", "battlefield")
    assert "flying" in keywords(s, cards, bears)  # creatures you control have flying
    assert "flying" not in keywords(s, cards, theirs) and "vigilance" in keywords(s, cards, theirs)  # lose flying only
    roundtrip(s)


def test_the_denial_beats_a_later_grant_whatever_the_timestamps(cards):
    """Both players control an Archetype of Imagination: each one's grant of flying to its own creatures comes after
    or before the other's loss, yet neither side's creatures have flying (they "can't have or gain" it)."""
    s = build(cards, [(1, "Archetype of Imagination"), (1, "Grizzly Bears")], [(1, "Archetype of Imagination"), (1, "Grizzly Bears")])
    mine = put(s, "Archetype of Imagination", "battlefield", pid="p1")
    theirs = put(s, "Archetype of Imagination", "battlefield", pid="p2")
    for c in (mine, theirs):
        assert "flying" not in keywords(s, cards, c)
    roundtrip(s)
