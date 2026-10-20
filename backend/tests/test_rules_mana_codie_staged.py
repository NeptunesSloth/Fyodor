"""Production native Codie whole-card gameplay, refusal and true-cold gates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_abundance import set_library
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Codie, Vociferous Codex'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ('mana_followthrough_profiles_cards.json', 'mana_codie_staged_cards.json'):
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='codie', number=f'{filename[:4]}{i}',
                                  **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):  # noqa: F811
    s = table(cards, [NAME, 'Think Twice', 'Forest', 'Grizzly Bears', 'Counterspell', 'Counterspell', 'Opt', 'Mountain', 'Stifle',
                      'Blaze', 'Fire // Ice', 'Bonecrusher Giant // Stomp', 'Bala Ged Recovery // Bala Ged Sanctuary',
                      'Pestilent Cauldron // Restorative Burst', 'Jwari Disruption // Jwari Ruins', 'Village Rites'], [], [])
    source = put(s, NAME, 'battlefield')
    spell = put(s, 'Think Twice', 'hand')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    packet = set_library(s, ['Forest', 'Grizzly Bears', 'Counterspell', 'Opt', 'Mountain'])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, sources=[])
    assert source.tapped and mana_pool(s) == dict.fromkeys('WUBRG', 1)
    assert not s.state.zones.get('stack')
    assert len(s.state.rules.delayed) == 1
    return s, source, spell, packet


def test_native_codie_delayed_trigger_timed_cast_and_random_rest(cards):  # noqa: F811
    s, source, spell, packet = setup(cards)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    assert len(s.state.zones['stack']) == 2
    assert not s.state.rules.delayed
    settle(s)
    found = packet[3]
    assert s.state.cards[found].zone == 'p1:exile'
    assert set(s.state.zones['p1:library'][-3:]) == set(packet[:3])
    assert any(p.object_id == s.state.rules.object_id(found) and p.free for p in s.state.rules.permissions)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=found, free=True, sources=[])
    answer(s)
    assert s.state.cards[found].zone == 'p1:graveyard'
    roundtrip(s)


def test_native_codie_preserves_existing_no_permanent_spell_rule(cards):  # noqa: F811
    s, source, _, _ = setup(cards)
    creature = put(s, 'Grizzly Bears', 'hand')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match="can't cast"):
        act(s, 'p1', type='cast_spell', card_id=creature.id, sources=[])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='cast_spell', card_id=creature.id, sources=[])
    assert s.state.cards[creature.id].zone == 'stack'


def test_native_codie_source_departure_still_watches_next_permanent_spell(cards):  # noqa: F811
    s, source, _, packet = setup(cards)
    creature = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='cast_spell', card_id=creature.id, sources=[])
    assert len(s.state.zones['stack']) == 2
    settle(s)
    assert s.state.cards[packet[3]].zone == 'p1:exile'
    assert s.state.cards[creature.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_native_codie_countered_next_spell_reads_exact_stack_lki(cards):  # noqa: F811
    s, source, spell, packet = setup(cards)
    counter = put(s, 'Counterspell', 'hand')
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2})
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[spell.id], sources=[])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.cards[packet[3]].zone == 'p1:exile'
    roundtrip(s)


def test_native_codie_delayed_trigger_can_be_countered_but_mana_was_added(cards):  # noqa: F811
    s, _, spell, packet = setup(cards)
    stifle = put(s, 'Stifle', 'hand')
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    trigger = s.state.zones['stack'][-1]
    assert trigger != spell.id
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    act(s, 'p1', type='cast_spell', card_id=stifle.id, targets=[trigger], sources=[])
    settle(s)
    assert s.state.cards[packet[3]].zone == 'p1:library'
    assert not s.state.rules.permissions
    assert mana_pool(s)
    roundtrip(s)


@pytest.mark.parametrize('empty', [False, True])
def test_native_codie_no_match_returns_whole_packet_once(cards, empty):  # noqa: F811
    s, source, _, _ = setup(cards)
    creature = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    packet = set_library(s, [] if empty else ['Forest', 'Mountain', 'Counterspell'])
    act(s, 'p1', type='cast_spell', card_id=creature.id, sources=[])
    settle(s)
    assert set(s.state.zones.get('p1:library', [])) == set(packet)
    assert not s.state.zones.get('p1:exile') and not s.state.rules.permissions
    assert s.state.cards[creature.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_native_codie_watcher_expires_this_turn_and_unused_hit_remains_exiled(cards):  # noqa: F811
    s, _, spell, packet = setup(cards)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    settle(s)
    found = packet[3]
    assert s.state.cards[found].zone == 'p1:exile'
    to_phase(s, 'main1', 5)
    assert s.state.cards[found].zone == 'p1:exile'
    assert not s.state.rules.permissions and not s.state.rules.delayed
    roundtrip(s)
    s, _, _, _ = setup(cards)
    to_phase(s, 'main1', 5)
    assert not s.state.rules.delayed
    roundtrip(s)


def test_native_codie_existing_watcher_keeps_original_controller(cards):  # noqa: F811
    s, source, spell, packet = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    settle(s)
    assert s.state.cards[packet[3]].zone == 'p1:exile'
    assert any(p.player == 'p1' and p.card == packet[3] for p in s.state.rules.permissions)
    roundtrip(s)


def test_native_codie_two_actual_activations_watch_same_next_spell(cards):  # noqa: F811
    s, source, spell, _ = setup(cards)
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, sources=[])
    assert len(s.state.rules.delayed) == 2
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    assert not s.state.rules.delayed
    assert len(s.state.zones['stack']) == 3
    answer(s)
    roundtrip(s)


@pytest.mark.parametrize('x,names,hit', [
    (2, ['Forest', 'Fire // Ice', 'Opt'], 2),
    (3, ['Forest', 'Bonecrusher Giant // Stomp', 'Opt'], 2),
    (5, ['Pestilent Cauldron // Restorative Burst', 'Jwari Disruption // Jwari Ruins'], 1),
    (3, ['Bala Ged Recovery // Bala Ged Sanctuary', 'Opt'], 0),
])
def test_native_codie_current_x_and_actual_exiled_front_or_combined_split_mana_value(cards, x, names, hit):  # noqa: F811
    s, _, _, _ = setup(cards)
    spell = put(s, 'Blaze', 'hand')
    packet = set_library(s, names)
    if x > 4:
        act(s, 'p1', type='add_mana', player='p1', mana={'C': x - 4})
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=x, targets=['p2'], sources=[])
    settle(s)
    found = packet[hit]
    assert s.state.cards[found].zone == 'p1:exile'
    assert {c for c in packet if s.state.cards[c].zone == 'p1:exile'} == {found}
    assert any(p.card == found and p.free for p in s.state.rules.permissions)
    if names[hit].startswith('Bala Ged'):
        wait_priority(s, 'p1')
        with pytest.raises(ActionError):
            act(s, 'p1', type='play_land', card_id=found, face=1)
    roundtrip(s)


def test_native_codie_countered_x_spell_lki_retains_announced_mana_value(cards):  # noqa: F811
    s, source, _, packet = setup(cards)
    spell = put(s, 'Blaze', 'hand')
    counter = next(c for c in s.state.cards.values() if c.name == 'Counterspell' and c.owner == 'p1' and c.id not in packet)
    act(s, 'p1', type='move', card_ids=[counter.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=3, targets=['p2'], sources=[])
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2})
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[spell.id], sources=[])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.cards[packet[2]].zone == 'p1:exile'  # Counterspell MV2 < actual original Blaze MV4.
    assert s.state.cards[packet[3]].zone == 'p1:library'
    roundtrip(s)


@pytest.mark.parametrize('stage', ['watch', 'countered_spell_trigger', 'permission'])
def test_native_codie_true_cold_native_watch_trigger_or_ordinary_permission(cards, tmp_path, stage):  # noqa: F811
    import subprocess
    import sys

    from tests.test_rules_copy import resolve_top

    s, source, spell, packet = setup(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    if stage != 'watch':
        act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    if stage == 'countered_spell_trigger':
        counter = next(c for c in s.state.cards.values() if c.name == 'Counterspell' and c.owner == 'p1' and c.id not in packet)
        act(s, 'p1', type='move', card_ids=[counter.id], to={'player': 'p1', 'zone': 'hand'})
        act(s, 'p1', type='add_mana', player='p1', mana={'U': 2})
        act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[spell.id], sources=[])
        resolve_top(s)
        assert s.state.cards[spell.id].zone == 'p1:graveyard'
        assert len(s.state.zones['stack']) == 1
    if stage == 'permission':
        settle(s)
        assert s.state.cards[packet[3]].zone == 'p1:exile'
    path = tmp_path / f'codie-{stage}.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_activated_copy_family import answer
path,database,stage,spell,found=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
if stage=='watch':
 assert len(s.state.rules.delayed)==1
 s.perform('p1',{'type':'cast_spell','card_id':spell,'sources':[]})
 assert len(s.state.zones['stack'])==2
answer(s)
assert s.state.cards[found].zone=='p1:exile'
assert any(p.card==found and p.free and p.player=='p1' for p in s.state.rules.permissions)
s.perform('p1',{'type':'cast_spell','card_id':found,'free':True,'sources':[]})
answer(s)
assert s.state.cards[found].zone=='p1:graveyard'
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), stage, spell.id, packet[3]],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('sacrifice_available', [False, True])
def test_native_codie_timed_free_cast_still_requires_actual_mandatory_additional_cost(cards, sacrifice_available):  # noqa: F811
    s, source, spell, _ = setup(cards)
    packet = set_library(s, ['Village Rites', 'Forest', 'Mountain'])
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    settle(s)
    found = packet[0]
    assert s.state.cards[found].zone == 'p1:exile'
    if sacrifice_available:
        act(s, 'p1', type='cast_spell', card_id=found, free=True, sources=[],
            cost_choices=[{'component': 0, 'cards': [source.id]}])
        assert s.state.cards[source.id].zone == 'p1:graveyard'
        record = s.state.rules.payments[s.state.rules.object_id(found)]
        assert record.sacrificed == [source.id] and not record.mana_spent
        answer(s)
        assert s.state.cards[found].zone == 'p1:graveyard'
    else:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
        before = s.state.model_dump(mode='json')
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=found, free=True, sources=[])
        assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_native_codie_timed_free_x_card_announces_zero(cards):  # noqa: F811
    s, _, spell, _ = setup(cards)
    packet = set_library(s, ['Blaze', 'Mountain'])
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    settle(s)
    found = packet[0]
    assert s.state.cards[found].zone == 'p1:exile'
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=found, free=True, x_value=1, targets=['p2'], sources=[])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='cast_spell', card_id=found, free=True, x_value=0, targets=['p2'], sources=[])
    assert not s.state.rules.payments[s.state.rules.object_id(found)].mana_spent
    answer(s)
    roundtrip(s)


def test_native_codie_legacy_unknown_original_spell_ref_does_not_read_new_physical_incarnation(cards):  # noqa: F811
    from app.game.session import GameSession
    from app.game.state import GameState
    from tests.test_rules_copy import resolve_top

    s, _, spell, packet = setup(cards)
    counter = next(c for c in s.state.cards.values() if c.name == 'Counterspell' and c.owner == 'p1' and c.id not in packet)
    act(s, 'p1', type='move', card_ids=[counter.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    original = s.state.rules.object_id(spell.id)
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2})
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[spell.id], sources=[])
    resolve_top(s)
    act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
    assert s.state.rules.object_id(spell.id) != original
    data = s.state.model_dump(mode='json')
    data['rules']['lki'].pop(original, None)
    trigger = data['zones']['stack'][-1]
    for ref in data['rules']['stack'][trigger]['event']['objects']:
        if ref['object_id'] == original:
            ref.pop('snapshot', None)
    loaded = GameSession(GameState.model_validate(data), cards=cards)
    library = loaded.state.zones['p1:library'].copy()
    settle(loaded)
    d = loaded.state.rules.decision
    assert d is not None and d.kind == 'manual_resolution'
    assert d.resume['step'] == 'codie_legacy_mv_done'
    assert loaded.state.zones['p1:library'] == library
    assert not loaded.state.rules.permissions
    act(loaded, 'p1', type='choose', decision_id=d.id, option_ids=['done'])
    assert not loaded.state.zones.get('stack')
    roundtrip(loaded)


@pytest.mark.parametrize('nested', [False, True])
def test_native_codie_activating_during_native_spell_payment_watches_that_same_spell(cards, nested):  # noqa: F811
    s = table(cards, [NAME, 'Divination', 'Forest', 'Counterspell', 'Opt', 'Mountain'], [], [])
    source = put(s, NAME, 'battlefield')
    spell = put(s, 'Divination', 'hand')
    packet = set_library(s, ['Forest', 'Counterspell', 'Opt', 'Mountain'])
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    if nested:
        act(s, 'p1', type='set_prefs', payment='self')
        act(s, 'p1', type='cast_spell', card_id=spell.id)
        assert s.state.rules.decision.resume['step'] == 'pay_mana'
        index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, sources=[])
        if s.state.rules.decision is not None:
            d = s.state.rules.decision
            assert d.resume['step'] == 'pay_mana'
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    else:
        act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[source.id])
    assert s.state.cards[source.id].tapped
    assert len(s.state.zones['stack']) == 2
    assert not s.state.rules.delayed
    record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert sum(record.mana_spent.values()) == 3
    assert sum(mana_pool(s).values()) == 2
    settle(s)
    assert s.state.cards[packet[1]].zone == 'p1:exile'
    assert any(p.card == packet[1] and p.free for p in s.state.rules.permissions)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Sol Ring', 'Grizzly Bears', 'Rancor', 'Jace Beleren',
                                'Invasion of Zendikar // Awakened Skyclave'])
def test_native_codie_all_five_permanent_spell_types_refused_atomically(cards, name):  # noqa: F811
    s = table(cards, [NAME, name], [], [])
    put(s, NAME, 'battlefield')
    spell = put(s, name, 'hand')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={c: 10 for c in 'WUBRG'})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='Codie'):
        act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_native_codie_allows_land_play_and_uses_current_controller_for_cast_prohibition(cards):  # noqa: F811
    s = table(cards, [NAME, 'Sol Ring', 'Forest'], [], [])
    source = put(s, NAME, 'battlefield')
    spell = put(s, 'Sol Ring', 'hand')
    land = put(s, 'Forest', 'hand')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='play_land', card_id=land.id)
    assert s.state.cards[land.id].zone == 'p1:battlefield'
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    assert s.state.cards[spell.id].zone == 'stack'
    answer(s)
    roundtrip(s)
