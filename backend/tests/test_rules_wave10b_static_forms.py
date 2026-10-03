"""Wave 10B: static wordings that turned up as the sole blocker of many cards (real Oracle text throughout).

* The Gates ("This land enters tapped." and, on its own line, "As this land enters, choose a color other than green.",
  614.1c, 614.1d, 614.12a): app/rules/entry_forms.py ``standalone_choice``.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.state import GameState
from app.rules import coverage
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
GATES = ["Manor Gate", "Sea Gate"]


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
