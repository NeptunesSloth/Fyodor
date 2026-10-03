"""Wave 12B: lure (509.1c) — "All creatures able to block this creature do so." as a static and as an activated ability."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_combat import creature
from tests.test_rules_conditionals import settle
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import build, card_named, mana, reloaded
from tests.test_rules_wave7e_activated import combat_table


EXTRA = [
    card('Deadbridge Goliath', set_code='tst', number='Y01', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Insect Skeleton', oracle_text="Scavenge {4}{G}{G} ({4}{G}{G}, Exile this card from your graveyard: Put a number of +1/+1 counters equal to this card's power on target creature. Scavenge only as a sorcery.)", power='5', toughness='5', colors=['G'], color_identity=['G'], keywords=['Scavenge']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_scavenge_puts_counters_equal_to_the_exiled_cards_power(cards):
    s = build(cards, "Deadbridge Goliath", forests=12)
    goliath = card_named(s, "Deadbridge Goliath")
    bear = creature(s, "p1", "Bear", "2/2")
    act(s, "p1", type="move", card_ids=[goliath.id], to={"zone": "graveyard"})
    mana(s, G=2, C=4)
    act(s, "p1", type="activate_ability", card_id=goliath.id, ability=0, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].counters == {"+1/+1": 5}  # 702.97a: the power of the card exiled
    assert s.state.cards[goliath.id].zone == "p1:exile"
    check(s)


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def test_static_lure_makes_every_able_creature_block(cards):
    from tests.test_rules_combat import attack, block

    s, lure, guard, spare = combat_table(cards, "All creatures able to block this creature do so.")
    act(s, "p1", type="pass_priority")
    attack(s, (lure, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2")
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2", (guard, lure))
    block(s, "p2", (guard, lure), (spare, lure))
    check(s)


def test_activated_lure_lasts_the_turn(cards):
    from tests.test_rules_combat import attack, block

    s, lure, guard, spare = combat_table(cards, "{2}{G}: All creatures able to block this creature this turn do so.")
    mana(s, G=1, C=2)
    act(s, "p1", type="activate_ability", card_id=lure.id, ability=0)
    settle(s)
    act(s, "p1", type="pass_priority")
    attack(s, (lure, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2", (guard, lure))
    block(s, "p2", (guard, lure), (spare, lure))
    check(s)


# -- landwalk variants (702.14a, 702.14c) --
@pytest.mark.parametrize(("walk", "land", "blockable"), [
    ("Snow landwalk", "Token Snow Land — Forest", False),
    ("Snow landwalk", "Token Land — Forest", True),
    ("Snow swampwalk", "Token Snow Land — Forest", True),
    ("Snow forestwalk", "Token Snow Land — Forest", False),
    ("Nonbasic landwalk", "Token Land", False),
    ("Nonbasic landwalk", "Token Basic Land — Forest", True),
    ("Legendary landwalk", "Token Legendary Land", False),
    ("Legendary landwalk", "Token Land", True),
    ("Artifact landwalk", "Token Artifact Land", False),
    ("Desertwalk", "Token Land — Desert", False),
])
def test_landwalk_variants(cards, walk, land, blockable):
    from tests.test_rules_combat import _blocks, _evasion_table

    s, sneak, guard = _evasion_table(cards, walk)
    act(s, "p2", type="create_token", player="p2", token={"name": "Terrain", "type_line": land})
    assert _blocks(s, sneak, guard) is blockable
    check(s)
