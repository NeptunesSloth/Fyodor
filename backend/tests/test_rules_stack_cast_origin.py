"""CR 601.2, 707.10: spell targets filtered by cast origin."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/stack_cast_origin_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_wash_away_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Wash Away')).level == 'FULL'


def setup_spell(cards, origin='hand'):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Wash Away', 'Twincast'], ['Lightning Bolt', 'Future Sight'])
    wash = put(s, 'Wash Away', 'hand')
    act(s, 'p2', type='set_prefs', hold_priority=True)
    if origin == 'hand':
        bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    else:
        put(s, 'Future Sight', 'battlefield', 'p2')
        bolt = put(s, 'Lightning Bolt', 'library', 'p2')
        act(s, 'p2', type='move', card_ids=[bolt.id], to={'player': 'p2', 'zone': 'library'}, index=0)
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    wait_priority(s, 'p1')
    return s, wash, bolt


@pytest.mark.parametrize('cleave', [False, True])
@pytest.mark.parametrize('origin', ['hand', 'library'])
def test_normal_filters_owner_hand_but_cleave_counters_any_spell(cards, cleave, origin):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    s, wash, bolt = setup_spell(cards, origin)
    mana(s, U=3)
    extra = {'alt_cost': f'{wash.id}:0'} if cleave else {}
    if origin == 'hand' and not cleave:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=wash.id, targets=[bolt.id])
        assert s.state.cards[wash.id].zone == 'p1:hand'
        assert s.state.players['p1'].mana == {'U': 3}
        assert s.state.cards[bolt.id].zone == 'stack'
    else:
        act(s, 'p1', type='cast_spell', card_id=wash.id, targets=[bolt.id], **extra)
        roundtrip(s)
        settle(s)
        assert s.state.cards[bolt.id].zone == 'p2:graveyard'
        assert s.state.players['p3'].life == 40
    roundtrip(s)


def test_copy_of_a_hand_cast_spell_was_not_cast_and_is_a_legal_target(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle

    s, wash, bolt = setup_spell(cards)
    twincast = put(s, 'Twincast', 'hand')
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=twincast.id, targets=[bolt.id])
    settle(s)
    d = s.state.rules.decision
    assert d and any(o.id == 'keep' for o in d.options)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep'])
    copied = next(cid for cid in s.state.zones['stack'] if cid != bolt.id)
    assert s.state.cards[copied].name == 'Lightning Bolt'
    assert s.state.rules.payments[s.state.rules.object_id(copied)].cast_from is None
    wait_priority(s, 'p1')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=wash.id, targets=[copied])
    roundtrip(s)
    settle(s)
    assert copied not in s.state.cards
    assert s.state.players['p3'].life == 37
    roundtrip(s)


def test_command_zone_spell_is_legal_for_the_one_mana_cost(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Wash Away'], [])
    wash = put(s, 'Wash Away', 'hand')
    to_phase(s, 'main1', turn=2)
    act(s, 'p2', type='set_prefs', hold_priority=True)
    commander = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.zone == 'p2:command')
    wait_priority(s, 'p2')
    mana(s, 'p2', W=1, U=1, B=1, G=1)
    act(s, 'p2', type='cast_spell', card_id=commander.id)
    wait_priority(s, 'p1')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=wash.id, targets=[commander.id])
    settle(s)
    d = s.state.rules.decision
    if d:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
    assert s.state.cards[commander.id].zone != 'p2:battlefield'
    assert s.state.cards[wash.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_flashback_spell_is_countered_and_exiled(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Wash Away'], ['Lightning Bolt', 'Snapcaster Mage'])
    wash = put(s, 'Wash Away', 'hand')
    bolt = put(s, 'Lightning Bolt', 'graveyard', 'p2')
    mage = put(s, 'Snapcaster Mage', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=mage.id)
    settle(s)
    d = s.state.rules.decision
    assert d and any(o.id == bolt.id for o in d.options)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[bolt.id])
    settle(s)
    wait_priority(s, 'p2')
    act(s, 'p2', type='set_prefs', hold_priority=True)
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    wait_priority(s, 'p1')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=wash.id, targets=[bolt.id])
    roundtrip(s)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p2:exile'
    assert s.state.players['p3'].life == 40
    roundtrip(s)
