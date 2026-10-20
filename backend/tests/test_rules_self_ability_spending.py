"""CR 609.4b: source-specific spending permissions for activated abilities."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import pt
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/self_ability_spending_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Manascape Refractor', 'Sharkey, Tyrant of the Shire'])
def test_self_ability_spending_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', ['Manascape Refractor', 'Sharkey, Tyrant of the Shire'])
def test_any_mana_pays_colored_costs_of_the_sources_borrowed_land_abilities(cards, name):
    s = table(cards, [name, 'Grizzly Bears'], ['Gavony Township'])
    source = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    land = put(s, 'Gavony Township', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    mana(s, C=4)
    index = ability_index(s, source, 'Put a +1/+1 counter on each creature you control')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    settle(s)
    assert pt(s, bear) == (3, 3) and s.state.cards[source.id].tapped
    assert not s.state.cards[land.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('name,allowed', [('Manascape Refractor', False), ('Sharkey, Tyrant of the Shire', True)])
def test_any_color_preserves_colorless_costs_but_any_type_can_pay_them(cards, name, allowed):
    from app.game.errors import ActionError

    s = table(cards, [name], ['Sea Gate Wreckage'])
    source = put(s, name, 'battlefield')
    put(s, 'Sea Gate Wreckage', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    hand = list(s.state.zones['p1:hand'])
    if hand:
        act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'graveyard'})
    mana(s, R=3)
    index = ability_index(s, source, 'Draw a card')
    if not allowed:
        with pytest.raises(ActionError):
            act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
        assert not s.state.cards[source.id].tapped
        mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    settle(s)
    assert len(s.state.zones['p1:hand']) == 1
    roundtrip(s)


@pytest.mark.parametrize('name', ['Manascape Refractor', 'Sharkey, Tyrant of the Shire'])
def test_source_specific_permission_does_not_pay_other_abilities_or_spells(cards, name):
    from app.game.errors import ActionError

    s = table(cards, [name, 'Gavony Township', 'Shivan Dragon', 'Lightning Bolt'], [])
    put(s, name, 'battlefield')
    township = put(s, 'Gavony Township', 'battlefield')
    dragon = put(s, 'Shivan Dragon', 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand')
    to_phase(s, 'main1', turn=4)
    mana(s, C=4)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=township.id,
            ability=ability_index(s, township, 'Put a +1/+1 counter'))
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=dragon.id,
            ability=ability_index(s, dragon, 'gets +1/+0'))
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    assert not s.state.cards[township.id].tapped and not s.state.zones.get('stack')
    roundtrip(s)


def test_refractor_borrowed_mana_ability_still_obeys_its_tap_cost(cards):
    from app.game.errors import ActionError

    s = table(cards, ['Manascape Refractor'], ['Gavony Township'])
    source = put(s, 'Manascape Refractor', 'battlefield')
    land = put(s, 'Gavony Township', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    index = ability_index(s, source, 'Add {C}')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    assert not s.state.zones.get('stack')
    assert s.state.cards[source.id].tapped and not s.state.cards[land.id].tapped
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    roundtrip(s)
