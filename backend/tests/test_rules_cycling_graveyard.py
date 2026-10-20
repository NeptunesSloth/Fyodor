"""CR 702.29c/f, 614.1: cycling permissions and graveyard replacements."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/cycling_graveyard_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_sarcophagus_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Abandoned Sarcophagus')).level == 'FULL'


@pytest.mark.parametrize('name', ['Street Wraith', 'Edge of Autumn', "Sojourner's Companion"])
def test_cycling_cost_discard_is_not_exiled(cards, name):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Abandoned Sarcophagus', name], [], [])
    put(s, 'Abandoned Sarcophagus', 'battlefield')
    c = put(s, name, 'hand')
    land = put(s, 'Forest', 'battlefield')
    mana(s, C=3)
    kw = {'cost_choices': [{'component': 0, 'cards': [land.id]}]} if name == 'Edge of Autumn' else {}
    act(s, 'p1', type='activate_ability', card_id=c.id, ability=ability_index(s, c, 'cycling' if name == "Sojourner's Companion" else 'Cycling'), **kw)
    assert s.state.cards[c.id].zone == 'p1:graveyard'
    roundtrip(s)
    settle(s)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Street Wraith', 'Edge of Autumn', "Sojourner's Companion", 'Tranquil Thicket'])
@pytest.mark.parametrize('pid', ['p1', 'p2'])
def test_other_zone_changes_exile_only_owners_cycling_cards(cards, name, pid):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Abandoned Sarcophagus', name, 'One with Nothing'], [name, 'One with Nothing'], [])
    put(s, 'Abandoned Sarcophagus', 'battlefield')
    c = put(s, name, 'hand', pid)
    spell = put(s, 'One with Nothing', 'hand', pid)
    wait_priority(s, pid)
    mana(s, pid, B=1)
    act(s, pid, type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.cards[c.id].zone == f'{pid}:' + ('exile' if pid == 'p1' else 'graveyard')
    roundtrip(s)


def test_graveyard_permission_casts_cycling_spells_but_not_lands_or_other_cards(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Abandoned Sarcophagus', 'Street Wraith', 'Tranquil Thicket', 'Grizzly Bears', 'Murder'], [], [])
    wraith = put(s, 'Street Wraith', 'graveyard')
    land = put(s, 'Tranquil Thicket', 'graveyard')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    put(s, 'Abandoned Sarcophagus', 'battlefield')
    mana(s, B=5, G=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=land.id)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bear.id)
    act(s, 'p1', type='cast_spell', card_id=wraith.id)
    roundtrip(s)
    settle(s)
    assert s.state.cards[wraith.id].zone == 'p1:battlefield'
    murder = put(s, 'Murder', 'hand')
    mana(s, B=3)
    act(s, 'p1', type='cast_spell', card_id=murder.id, targets=[wraith.id])
    settle(s)
    assert s.state.cards[wraith.id].zone == 'p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('cycling', [False, True])
def test_granted_cycling_is_checked_in_hand_and_does_not_persist_in_graveyard(cards, cycling):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Abandoned Sarcophagus', 'Homing Sliver', 'Metallic Sliver', 'One with Nothing'], [], [])
    put(s, 'Abandoned Sarcophagus', 'battlefield')
    put(s, 'Homing Sliver', 'battlefield')
    sliver = put(s, 'Metallic Sliver', 'hand')
    if cycling:
        index = s.view('p1')['rules']['stats'][sliver.id]['abilities'][0]['index']
        mana(s, C=3)
        act(s, 'p1', type='activate_ability', card_id=sliver.id, ability=index)
    else:
        spell = put(s, 'One with Nothing', 'hand')
        mana(s, B=1)
        act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    if s.state.rules.decision:
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert s.state.cards[sliver.id].zone == ('p1:graveyard' if cycling else 'p1:exile')
    if cycling:
        mana(s, C=1)
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=sliver.id)
    roundtrip(s)


def test_graveyard_permission_ends_when_sarcophagus_leaves(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Abandoned Sarcophagus', 'Street Wraith'], [], [])
    wraith = put(s, 'Street Wraith', 'graveyard')
    src = put(s, 'Abandoned Sarcophagus', 'battlefield')
    act(s, 'p1', type='move', card_ids=[src.id], to={'player': 'p1', 'zone': 'exile'})
    mana(s, B=5)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=wraith.id)
    roundtrip(s)


@pytest.mark.parametrize('name,expected', [('Street Wraith', 'exile'), ('Metallic Sliver', 'graveyard')])
def test_milling_checks_cycling_in_library_and_not_hand_grants(cards, name, expected):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Abandoned Sarcophagus', 'Homing Sliver', name, 'Tome Scour'], [], [])
    put(s, 'Abandoned Sarcophagus', 'battlefield')
    put(s, 'Homing Sliver', 'battlefield')
    c = put(s, name, 'hand')
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    spell = put(s, 'Tome Scour', 'hand')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p1'])
    settle(s)
    assert s.state.cards[c.id].zone == 'p1:' + expected
    roundtrip(s)
