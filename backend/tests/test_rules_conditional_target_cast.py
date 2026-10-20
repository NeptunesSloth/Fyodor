"""CR 608.2g: conditional paid casting and further-spell limits."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/conditional_target_cast_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_conduit_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Conduit of Worlds')).level == 'FULL'


@pytest.mark.parametrize('accept', [False, True])
def test_conduit_paid_cast_during_resolution_only_locks_further_casts_on_success(cards, accept):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Conduit of Worlds', 'Grizzly Bears', 'Sol Ring'], [], [])
    conduit = put(s, 'Conduit of Worlds', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    ring = put(s, 'Sol Ring', 'hand')
    mana(s, G=2, C=1)
    act(s, 'p1', type='activate_ability', card_id=conduit.id, ability=ability_index(s, conduit, 'Choose target'), targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d
    roundtrip(s)
    assert bear.id in {o.id for o in d.options}
    assert d.min_choices == 0
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id] if accept else [])
    settle(s)
    assert s.state.cards[bear.id].zone == ('p1:battlefield' if accept else 'p1:graveyard')
    roundtrip(s)
    if accept:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=ring.id)
        to_phase(s, 'main1', turn=4)
        mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=ring.id)
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_prior_spell_prevents_conduit_cast_without_banning_other_spells(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Conduit of Worlds', 'Grizzly Bears', 'Sol Ring', 'Lightning Bolt'], [], [])
    conduit = put(s, 'Conduit of Worlds', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    ring = put(s, 'Sol Ring', 'hand')
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, C=1, R=1, G=2)
    act(s, 'p1', type='cast_spell', card_id=ring.id)
    settle(s)
    act(s, 'p1', type='activate_ability', card_id=conduit.id, ability=ability_index(s, conduit, 'Choose target'), targets=[bear.id])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('bad_target', ['Forest', 'Lightning Bolt', 'opponent'])
def test_conduit_requires_own_nonland_permanent_graveyard_target(cards, bad_target):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Conduit of Worlds', 'Lightning Bolt'], ['Grizzly Bears'], [])
    conduit = put(s, 'Conduit of Worlds', 'battlefield')
    c = put(s, 'Grizzly Bears' if bad_target == 'opponent' else bad_target, 'graveyard', 'p2' if bad_target == 'opponent' else 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=conduit.id, ability=ability_index(s, conduit, 'Choose target'), targets=[c.id])
    assert not s.state.cards[conduit.id].tapped
    roundtrip(s)


def test_target_leaving_before_resolution_does_not_impose_cast_limit(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Conduit of Worlds', 'Grizzly Bears', 'Sol Ring'], [], [])
    conduit = put(s, 'Conduit of Worlds', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    ring = put(s, 'Sol Ring', 'hand')
    act(s, 'p1', type='activate_ability', card_id=conduit.id, ability=ability_index(s, conduit, 'Choose target'), targets=[bear.id])
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert s.state.rules.decision is None
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=ring.id)
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_source_departure_does_not_cancel_cast_and_opponents_remain_unrestricted(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Conduit of Worlds', 'Grizzly Bears', 'Sol Ring'], ['Lightning Bolt'], [])
    conduit = put(s, 'Conduit of Worlds', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    ring = put(s, 'Sol Ring', 'hand')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    mana(s, G=2, C=1)
    act(s, 'p1', type='activate_ability', card_id=conduit.id, ability=ability_index(s, conduit, 'Choose target'), targets=[bear.id])
    act(s, 'p1', type='move', card_ids=[conduit.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ring.id)
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p1'])
    settle(s)
    assert s.state.players['p1'].life == 37
    roundtrip(s)


def test_unpayable_cast_does_not_restrict_future_spells(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Conduit of Worlds', 'Grizzly Bears', 'Sol Ring'], [], [])
    conduit = put(s, 'Conduit of Worlds', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    ring = put(s, 'Sol Ring', 'hand')
    act(s, 'p1', type='activate_ability', card_id=conduit.id, ability=ability_index(s, conduit, 'Choose target'), targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=ring.id)
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    roundtrip(s)
