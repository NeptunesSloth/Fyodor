"""CR 707.10 / 702.172: mixed spell and ability copying with spree."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/hybrid_stack_copy_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_return_the_favor_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Return the Favor')).level == 'FULL'


@pytest.mark.parametrize('kind', ['spell', 'activated'])
def test_hybrid_copy_targets_spell_or_activated_ability_and_can_retarget(cards, kind):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Return the Favor', 'Lightning Bolt', 'Prodigal Pyromancer'], [], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    if kind == 'activated':
        source = put(s, 'Prodigal Pyromancer', 'battlefield')
        to_phase(s, 'main1', turn=4)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'deals 1 damage'), targets=['p2'])
        target = s.state.zones['stack'][-1]
    else:
        source = put(s, 'Lightning Bolt', 'hand')
        mana(s, R=1)
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'])
        target = source.id
    favor = put(s, 'Return the Favor', 'hand')
    wait_priority(s, 'p1')
    mana(s, R=3)
    assert s.state.cards[target].zone == 'stack', (s.state.cards[target].zone, s.state.rules.passed)
    act(s, 'p1', type='cast_spell', card_id=favor.id, modes=[0], targets=[target])
    settle(s)
    d = s.state.rules.decision
    assert d and 'p3' in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    settle(s)
    damage = 1 if kind == 'activated' else 3
    assert s.state.players['p2'].life == 40 - damage
    assert s.state.players['p3'].life == 40 - damage
    assert s.state.cards[favor.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_hybrid_copy_rejects_permanent_spells(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Return the Favor', 'Grizzly Bears'], [], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    bear = put(s, 'Grizzly Bears', 'hand')
    favor = put(s, 'Return the Favor', 'hand')
    mana(s, G=2, R=3)
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=favor.id, modes=[0], targets=[bear.id])
    assert s.state.cards[favor.id].zone == 'p1:hand'
    roundtrip(s)


def test_hybrid_copy_targets_triggered_ability_without_recasting_creature(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Return the Favor', 'Elvish Visionary'], [], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    visionary = put(s, 'Elvish Visionary', 'hand')
    favor = put(s, 'Return the Favor', 'hand')
    mana(s, G=2, R=3)
    act(s, 'p1', type='cast_spell', card_id=visionary.id)
    for _ in range(4):
        if s.state.cards[visionary.id].zone != 'stack':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    target = s.state.zones['stack'][-1]
    assert s.state.cards[target].ability is not None
    wait_priority(s, 'p1')
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=favor.id, modes=[0], targets=[target])
    settle(s)
    assert s.state.rules.decision is None
    assert len(s.state.zones['p1:hand']) == before + 1  # two draws, Favor leaves hand
    assert s.state.cards[visionary.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_both_spree_modes_pay_both_costs_then_copy_and_change_original_target(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Return the Favor', 'Lightning Bolt'], [], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    bolt = put(s, 'Lightning Bolt', 'hand')
    favor = put(s, 'Return the Favor', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    wait_priority(s, 'p1')
    mana(s, R=3)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=favor.id, modes=[0, 1], targets=[bolt.id, bolt.id])
    mana(s, R=4)
    act(s, 'p1', type='cast_spell', card_id=favor.id, modes=[0, 1], targets=[bolt.id, bolt.id])
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    d = s.state.rules.decision
    assert d and 'p1' in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p1'])
    settle(s)
    assert s.state.players['p1'].life == 37
    assert s.state.players['p2'].life == 40
    assert s.state.players['p3'].life == 37
    roundtrip(s)


def test_hybrid_copy_accepts_sorcery_spell(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Return the Favor', 'Divination'], [], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    divination = put(s, 'Divination', 'hand')
    favor = put(s, 'Return the Favor', 'hand')
    mana(s, U=3, R=3)
    act(s, 'p1', type='cast_spell', card_id=divination.id)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=favor.id, modes=[0], targets=[divination.id])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 3
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('kind', ['spell', 'activated', 'triggered'])
def test_sister_of_silence_counters_all_supported_stack_kinds(cards, kind):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Sister of Silence', 'Lightning Bolt', 'Prodigal Pyromancer', 'Elvish Visionary'], [], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    sister = put(s, 'Sister of Silence', 'hand')
    if kind == 'activated':
        source = put(s, 'Prodigal Pyromancer', 'battlefield')
        to_phase(s, 'main1', turn=4)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'deals 1 damage'), targets=['p2'])
        target = s.state.zones['stack'][-1]
    elif kind == 'spell':
        source = put(s, 'Lightning Bolt', 'hand')
        mana(s, R=1)
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'])
        target = source.id
    else:
        source = put(s, 'Elvish Visionary', 'hand')
        mana(s, G=2)
        act(s, 'p1', type='cast_spell', card_id=source.id)
        for _ in range(4):
            if s.state.cards[source.id].zone != 'stack':
                break
            act(s, s.state.rules.priority, type='pass_priority')
        target = s.state.zones['stack'][-1]
    wait_priority(s, 'p1')
    before = len(s.state.zones['p1:hand'])
    mana(s, U=5)
    act(s, 'p1', type='cast_spell', card_id=sister.id)
    settle(s)
    d = s.state.rules.decision
    if d:
        assert target in {o.id for o in d.options}
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[target])
        settle(s)
    assert s.state.rules.decision is None
    assert not s.state.zones.get('stack')
    assert s.state.players['p2'].life == 40
    assert len(s.state.zones['p1:hand']) == before - 1
    assert s.state.cards[sister.id].zone == 'p1:battlefield'
    if kind == 'spell':
        assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)
