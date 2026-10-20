"""CR 608.2h: exiled creature power and nontargeted commander counters."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/counter_damage_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'All Will Be One'


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, multiplier=False, prohibition=False):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, [NAME, 'Travel Preparations', 'Aether Hub', 'Vorinclex, Monstrous Raider', 'Solemnity'], ['Grizzly Bears', 'Chandra, Torch of Defiance'])
    put(s, NAME, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if multiplier:
        put(s, 'Vorinclex, Monstrous Raider', 'battlefield')
    if prohibition:
        put(s, 'Solemnity', 'battlefield')
    return s, bear


def resolve_damage(s, target='p2'):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target])
    settle(s)


@pytest.mark.parametrize('multiplier', [False, True])
def test_you_put_counters_on_opponent_permanent(cards, multiplier):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    s, bear = setup(cards, multiplier=multiplier)
    spell = put(s, 'Travel Preparations', 'hand')
    mana(s, G=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id], target_counts=[1])
    settle(s)
    resolve_damage(s)
    assert s.state.players['p2'].life == 40 - (2 if multiplier else 1)
    roundtrip(s)


def test_player_energy_counter_triggers(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    s, _ = setup(cards)
    land = put(s, 'Aether Hub', 'hand')
    act(s, 'p1', type='play_land', card_id=land.id)
    resolve_damage(s)
    assert s.state.players['p1'].resources['energy'] == 1
    assert s.state.players['p2'].life == 39
    roundtrip(s)


@pytest.mark.parametrize('recipient', ['permanent', 'player'])
def test_proliferate_sums_distinct_counter_kinds_once_per_recipient(cards, recipient):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, [NAME, 'Contentious Plan'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if recipient == 'permanent':
        act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=1)
        act(s, 'p1', type='counter', card_ids=[bear.id], kind='charge', delta=1)
        choice = bear.id
    else:
        act(s, 'p1', type='resource', player='p2', key='poison', delta=1)
        act(s, 'p1', type='resource', player='p2', key='experience', delta=1)
        choice = 'p2'
    put(s, NAME, 'battlefield')
    spell = put(s, 'Contentious Plan', 'hand')
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith('Proliferate')
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[choice])
    resolve_damage(s)
    assert s.state.rules.decision is None
    assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_opponent_putting_player_counters_does_not_trigger(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards, [NAME], ['Aether Hub'])
    put(s, NAME, 'battlefield')
    to_phase(s, 'main1', turn=2)
    land = put(s, 'Aether Hub', 'hand', 'p2')
    act(s, 'p2', type='play_land', card_id=land.id)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players['p2'].resources['energy'] == 1
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_only_opponents_and_their_creatures_or_planeswalkers_are_targets(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    s, bear = setup(cards)
    own = put(s, 'Krenko, Mob Boss', 'battlefield')
    pw = put(s, 'Chandra, Torch of Defiance', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=pw.id, kind='loyalty', value=4)
    land = put(s, 'Aether Hub', 'hand')
    act(s, 'p1', type='play_land', card_id=land.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    ids = {o.id for o in d.options}
    assert {'p2', 'p3', bear.id, pw.id} <= ids
    assert 'p1' not in ids and own.id not in ids and land.id not in ids
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[pw.id])
    settle(s)
    assert s.state.cards[pw.id].counters['loyalty'] == 3
    roundtrip(s)


def test_infect_poison_is_put_by_damage_source_controller_not_spell_controller(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, [NAME, 'Backlash'], ['Glistener Elf'])
    put(s, NAME, 'battlefield')
    elf = put(s, 'Glistener Elf', 'battlefield', 'p2')
    spell = put(s, 'Backlash', 'hand')
    mana(s, R=2, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[elf.id])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players['p2'].resources.get('poison', 0) == 1
    assert all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)


def test_prevented_counters_do_not_trigger(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    s, bear = setup(cards, prohibition=True)
    spell = put(s, 'Travel Preparations', 'hand')
    mana(s, G=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id], target_counts=[1])
    settle(s)
    assert not s.state.cards[bear.id].counters
    assert s.state.rules.decision is None
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_multiplied_multi_kind_counter_trigger_keeps_total_amount(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, [NAME, 'Contentious Plan', 'Opalescence', 'Maskwood Nexus', 'Harmonic Prodigy'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=1)
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='charge', delta=1)
    for name in [NAME, 'Opalescence', 'Maskwood Nexus', 'Harmonic Prodigy']:
        put(s, name, 'battlefield')
    spell = put(s, 'Contentious Plan', 'hand')
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith('Proliferate')
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
    resolve_damage(s)
    resolve_damage(s)
    assert s.state.rules.decision is None
    assert s.state.players['p2'].life == 36
    roundtrip(s)
