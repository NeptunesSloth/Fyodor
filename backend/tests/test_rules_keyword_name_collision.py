"""CR 702: distinguish keyword forms from names and qualified enchant abilities."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/keyword_name_collision_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_card_name_is_not_the_unleash_keyword_but_actual_unleash_still_is(cards):
    from app.rules.characteristics import printed_from_data

    for name in ['Unleash Shell', 'Gore-House Chainwalker']:
        assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
    shell = printed_from_data(cards.resolve('Unleash Shell'))
    creature = printed_from_data(cards.resolve('Gore-House Chainwalker'))
    assert all('unleash' not in a.keywords for a in shell.abilities)
    assert any('unleash' in a.keywords for a in creature.abilities)


@pytest.mark.parametrize('planeswalker', [False, True])
@pytest.mark.parametrize('change_control', [False, True])
def test_shell_deals_both_damage_amounts_to_permanent_and_its_current_controller(cards, planeswalker, change_control):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    name = 'Chandra, Torch of Defiance' if planeswalker else 'Grizzly Bears'
    s = table(cards, ['Unleash Shell'], [name], [])
    target = put(s, name, 'battlefield', 'p2')
    if planeswalker:
        act(s, 'p2', type='set_counter', card_id=target.id, kind='loyalty', value=4)
    source = put(s, 'Unleash Shell', 'hand')
    mana(s, R=6)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id])
    if change_control:
        act(s, 'p2', type='set_controller', card_ids=[target.id], player='p3')
    roundtrip(s)
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    assert s.state.players['p3' if change_control else 'p2'].life == 38
    assert s.state.players['p2' if change_control else 'p3'].life == 40
    roundtrip(s)


def test_departed_only_target_prevents_both_damage_instructions(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Unleash Shell'], ['Grizzly Bears'])
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = put(s, 'Unleash Shell', 'hand')
    mana(s, R=6)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id])
    act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    assert s.state.players['p2'].life == 40 and s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)
