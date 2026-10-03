"""Wave 13E: "return that card / it to your hand" for a pronoun (Sigil of the New Dawn, Zodiac Dragon, Surprise Deployment).
400.3: a card that would go to a hand other than its owner's goes to its owner's, so "your hand" for a card that was put into
your graveyard is its owner's hand, exactly as "its owner's hand" reads. Researched against CR 2026-09-25; replay and save/load.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip

EXTRA = [
    card('Sigil of the New Dawn', set_code="tst", number="H01", mana_cost='{3}{W}', cmc=4.0, type_line='Enchantment', oracle_text="Whenever a creature is put into your graveyard from the battlefield, you may pay {1}{W}. If you do, return that card to your hand.", colors=['W'], color_identity=['W']),  # noqa: E501
    card('Surprise Deployment', set_code="tst", number="H03", mana_cost='{3}{U}', cmc=4.0, type_line='Instant', oracle_text="Cast this spell only during combat.\nYou may put a nonwhite creature card from your hand onto the battlefield. At the beginning of the next end step, return that creature to your hand. (Return it only if it's on the battlefield.)", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Quick Deployment', set_code="tst", number="H04", mana_cost='{3}{U}', cmc=4.0, type_line='Instant', oracle_text="You may put a nonwhite creature card from your hand onto the battlefield. At the beginning of the next end step, return that creature to your hand. (Return it only if it's on the battlefield.)", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Zodiac Dragon', set_code="tst", number="H02", mana_cost='{7}{R}{R}', cmc=9.0, type_line='Creature — Dragon', oracle_text="Flying\nWhen this creature is put into your graveyard from the battlefield, you may return it to your hand.", power='7', toughness='7', colors=['R'], color_identity=['R'], keywords=['Flying']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def kill(s, c):
    act(s, "p1", type="set_damage", card_ids=[c.id], value=20)
    act(s, s.state.rules.priority, type="pass_priority")


def test_sigil_returns_the_dead_creature_card_to_its_owners_hand_for_a_payment(cards):
    s = build(cards, p1=("Sigil of the New Dawn", "Ambush Viper"))
    put(s, "Sigil of the New Dawn", "battlefield")
    viper = put(s, "Ambush Viper", "battlefield")
    mana(s, W=2)
    kill(s, viper)
    answer(s)  # the payment (yes), then the trigger resolves
    assert any(c.name == "Ambush Viper" and c.zone == "p1:hand" for c in s.state.cards.values())
    roundtrip(s)


def test_zodiac_dragon_may_return_itself_to_its_hand(cards):
    s = build(cards, p1=("Zodiac Dragon",))
    dragon = put(s, "Zodiac Dragon", "battlefield")
    kill(s, dragon)
    answer(s)
    assert any(c.name == "Zodiac Dragon" and c.zone == "p1:hand" for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize("dies", [False, True])
def test_surprise_deployment_returns_the_creature_only_if_it_is_still_on_the_battlefield(cards, dies):
    """Surprise Deployment's effect sentences (its "Cast this spell only during combat." line is its own static; the combat steps
    give a test no priority stop to cast in, so a stand-in card carries the effect alone)."""
    from tests.test_rules_conditionals import to_hand, until
    from tests.test_rules_effects import replay_matches

    s = build(cards, p1=("Quick Deployment", "Ambush Viper"))
    spell, viper = to_hand(s, "Quick Deployment"), to_hand(s, "Ambush Viper")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s, pick=viper.id)
    assert s.state.cards[viper.id].zone == "p1:battlefield"
    if dies:
        act(s, "p1", type="set_damage", card_ids=[viper.id], value=20)
    until(s, lambda s: s.state.turn.number > 1)
    here = [c.zone for c in s.state.cards.values() if c.name == "Ambush Viper" and c.owner == "p1"]
    assert here == (["p1:graveyard"] if dies else ["p1:hand"])
    replay_matches(s)
