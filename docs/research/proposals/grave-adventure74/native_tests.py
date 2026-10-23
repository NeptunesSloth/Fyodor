"""Native death grants retain actual graveyard successors and Adventure timing."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/grave_adventure74_cards.json').read_text())
NAMES = [c['name'] for c in DATA]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json',
                     'fight_exile_receipts65_cards.json', 'top_library_authorities69_cards.json',
                     'pooled_casting_authorities71_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='ga74', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='ga74', number='a' + str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *NAMES, 'Lightning Bolt', 'Disperse', 'Counterspell', 'Rest in Peace')


def death(s, name):
    source = cast(s, name)
    cast(s, 'Lightning Bolt', targets=[source.id])
    assert source.zone == 'p1:graveyard'
    assert any(p.card == source.id for p in s.state.rules.permissions)
    return source


@pytest.mark.parametrize('name', NAMES)
def test_canonical_whole74(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', NAMES)
def test_native_death_only_allows_actual_adventure_then_native_exile_front_cast(cards, name):
    s = setup(cards)
    source = death(s, name)
    mana(s, C=10, B=10, G=10, W=10)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, face=0)
    assert s.state.model_dump(mode='json') == before
    hand = len(s.state.zones['p1:hand'])
    life = s.state.players['p1'].life
    act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    settle(s)
    assert source.zone == 'p1:exile'
    if name.startswith('Mosswood'):
        assert len(s.state.zones['p1:hand']) == hand + 1 and s.state.players['p1'].life == life - 1
    else:
        zombies = [c for c in s.state.cards.values() if c.is_token and 'Zombie' in Plan(s.state, 'p1', cards, None).ch(c).subtypes]
        assert len(zombies) == 1 and Plan(s.state, 'p1', cards, None).ch(zombies[0]).pt == (2, 2)
    mana(s, C=10, B=10, G=10, W=10)
    act(s, 'p1', type='cast_spell', card_id=source.id, face=0)
    settle(s)
    assert source.zone == 'p1:battlefield'
    if not name.startswith('Mosswood'):
        assert Plan(s.state, 'p1', cards, None).ch(zombies[0]).pt == (3, 3)
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_graveyard_card_without_actual_death_has_no_permission(cards, name):
    s = setup(cards)
    source = put(s, name, 'graveyard')
    mana(s, C=10, B=10, G=10, W=10)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    assert s.state.model_dump(mode='json') == before


def test_native_instant_adventure_can_use_opponent_priority_but_sorcery_cannot(cards):
    s = setup(cards)
    moss = death(s, NAMES[0])
    hildi = death(s, NAMES[1])
    to_phase(s, 'main1', turn=2)
    settle(s)
    mana(s, C=10, B=10)
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=moss.id, face=1)
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='cast_spell', card_id=hildi.id, face=1)
    settle(s)
    assert hildi.zone == 'p1:exile' and moss.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('expired', [False, True])
def test_native_until_end_of_next_turn_permission_expires_at_actual_cleanup(cards, expired):
    s = setup(cards)
    source = death(s, NAMES[0])
    to_phase(s, 'main1', turn=7 if expired else 4)
    settle(s)
    mana(s, C=5, B=5)
    wait_priority(s, 'p1')
    if expired:
        before = s.state.model_dump(mode='json')
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
        assert s.state.model_dump(mode='json') == before
    else:
        act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
        settle(s)
        assert source.zone == 'p1:exile'
    roundtrip(s)


def test_actual_source_controller_cannot_cast_from_its_owners_different_graveyard(cards):
    s = setup(cards)
    source = cast(s, NAMES[0])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    cast(s, 'Lightning Bolt', targets=[source.id])
    assert source.zone == 'p1:graveyard'
    assert not any(p.card == source.id for p in s.state.rules.permissions)
    roundtrip(s)


def test_a_new_graveyard_incarnation_cannot_reuse_the_original_death_permission(cards):
    s = setup(cards)
    source = death(s, NAMES[0])
    original = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert s.state.rules.object_id(source.id) != original
    mana(s, C=5, B=5)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_native_exile_replacement_prevents_the_dies_trigger_and_permission(cards):
    s = setup(cards)
    cast(s, 'Rest in Peace')
    source = cast(s, NAMES[0])
    cast(s, 'Lightning Bolt', targets=[source.id])
    assert source.zone == 'p1:exile'
    assert not any(p.card == source.id for p in s.state.rules.permissions)
    mana(s, C=5, B=5)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_native_countered_adventure_returns_as_a_new_unpermitted_graveyard_object(cards):
    s = setup(cards)
    source = death(s, NAMES[0])
    original = s.state.rules.object_id(source.id)
    mana(s, C=5, B=5)
    act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    mana(s, pid='p2', U=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[source.id])
    settle(s)
    assert source.zone == 'p1:graveyard' and s.state.rules.object_id(source.id) != original
    wait_priority(s, 'p1')
    mana(s, C=5, B=5)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_native_adventure_permission_does_not_waive_the_actual_mana_cost(cards):
    s = setup(cards)
    source = death(s, NAMES[0])
    act(s, 'p1', type='clear_mana')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, face=1)
    assert s.state.model_dump(mode='json') == before


def pending_death(s, name):
    source = cast(s, name)
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[source.id])
    for _ in range(20):
        if source.zone == 'p1:graveyard':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert source.zone == 'p1:graveyard'
    entry = next(e for e in s.state.rules.stack.values() if e.kind == 'trigger' and e.source_card == source.id)
    assert entry.event is not None and entry.event.new_objects
    return source, entry


@pytest.mark.parametrize('mode', ['pending_death', 'stored_permission', 'missing_original'])
def test_genuine_cold_death_or_permission_retains_actual_original_object(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    name = NAMES[1] if mode == 'stored_permission' else NAMES[0]
    s = setup(cards)
    if mode == 'stored_permission':
        source = death(s, name)
        to_phase(s, 'main1', turn=2)
        settle(s)
        mana(s, C=5, B=5)
        wait_priority(s, 'p1')
    else:
        source, entry = pending_death(s, name)
        if mode == 'missing_original':
            entry.event.new_objects = []
    saved = tmp_path / 'adventure.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana,wait_priority
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
mode,cid=sys.argv[3:]
if mode!='stored_permission': settle(s)
if mode=='missing_original':
 d=s.state.rules.decision
 assert d and d.kind=='manual_resolution' and 'original graveyard object' in d.prompt
 assert not any(p.card==cid for p in s.state.rules.permissions)
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['done'])
 settle(s)
 assert not any(p.card==cid for p in s.state.rules.permissions)
else:
 permission=next(p for p in s.state.rules.permissions if p.card==cid)
 assert permission.object_id==s.state.rules.object_id(cid)
 mana(s,C=5,B=5)
 wait_priority(s,'p1')
 act(s,'p1',type='cast_spell',card_id=cid,face=1)
 settle(s)
 assert s.state.cards[cid].zone=='p1:exile'
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), mode, source.id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
