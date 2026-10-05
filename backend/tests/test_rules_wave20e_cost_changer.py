"""Wave 20E: cost changers. Real Oracle text; every scenario checks the replay and a save and a load.

* 601.2f / 118.7: "Red creature spells and green creature spells cost {1} more to cast" - one color list ("red or green creature spells"),
  every caster; "As long as this creature is tapped, creature spells you cast cost {2} less to cast" - the same sentence with its condition.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_permissions import build, cost_of, put
from tests.wave9c_kit import reloaded

EXTRA = [
    card('High Seas', set_code='tst', number='20E0', mana_cost='{1}{U}', cmc=2.0, type_line='Enchantment', oracle_text='Red creature spells and green creature spells cost {1} more to cast.', colors=['U'], color_identity=['U'], keywords=[]),
    card('Irini Sengir', set_code='tst', number='20E1', mana_cost='{2}{B}', cmc=3.0, type_line='Enchantment', oracle_text='Green enchantment spells and white enchantment spells cost {2} more to cast.', colors=['B'], color_identity=['B'], keywords=[]),
    card('Centaur Omenreader', set_code='tst', number='20E2', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Centaur Shaman', oracle_text='As long as this creature is tapped, creature spells you cast cost {2} less to cast.', colors=['G'], color_identity=['G'], keywords=[], power='3', toughness='3'),
    card('Probe Vine', set_code='tst', number='20E3', mana_cost='{G}', cmc=1.0, type_line='Enchantment', oracle_text='', colors=['G'], color_identity=['G'], keywords=[]),
    card('Probe Halo', set_code='tst', number='20E4', mana_cost='{W}', cmc=1.0, type_line='Enchantment', oracle_text='', colors=['W'], color_identity=['W'], keywords=[]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["High Seas", "Irini Sengir", "Centaur Omenreader"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def test_a_list_of_colors_taxes_each_listed_color_for_every_caster(cards):
    s = build(cards, [(1, "High Seas"), (1, "Grizzly Bears"), (1, "Lightning Bolt")], bob=[(1, "Grizzly Bears"), (9, "Island")])
    bears, bolt, theirs = put(s, "Grizzly Bears", "hand"), put(s, "Lightning Bolt", "hand"), put(s, "Grizzly Bears", "hand", "p2")
    assert cost_of(s, bears, cards) == "{1}{G}"
    put(s, "High Seas", "battlefield")
    assert cost_of(s, bears, cards) == "{2}{G}" and cost_of(s, theirs, cards, "p2") == "{2}{G}"  # (a green creature spell: either player)
    assert cost_of(s, bolt, cards) == "{R}"  # (an instant: not a creature spell)
    _check(s)


def test_one_color_list_and_one_type_each_pair(cards):
    s = build(cards, [(1, "Irini Sengir"), (1, "Probe Vine"), (1, "Probe Halo"), (1, "Grizzly Bears")])
    vine, halo, bears = put(s, "Probe Vine", "hand"), put(s, "Probe Halo", "hand"), put(s, "Grizzly Bears", "hand")
    put(s, "Irini Sengir", "battlefield")
    assert cost_of(s, vine, cards) == "{2}{G}" and cost_of(s, halo, cards) == "{2}{W}" and cost_of(s, bears, cards) == "{1}{G}"
    _check(s)


def test_as_long_as_this_creature_is_tapped(cards):
    s = build(cards, [(1, "Centaur Omenreader"), (1, "Grizzly Bears"), (1, "Lightning Bolt")])
    reader = put(s, "Centaur Omenreader", "battlefield")
    bears, bolt = put(s, "Grizzly Bears", "hand"), put(s, "Lightning Bolt", "hand")
    assert cost_of(s, bears, cards) == "{1}{G}"  # (untapped: no change)
    act(s, "p1", type="tap", card_ids=[reader.id], tapped=True)
    assert cost_of(s, bears, cards) == "{G}" and cost_of(s, bolt, cards) == "{R}"  # (118.7a: generic only; a creature spell only)
    _check(s)
