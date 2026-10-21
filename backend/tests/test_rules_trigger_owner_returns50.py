"""Explicitly introduced face-up exile targets use native owner/library moves."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_owner_returns50_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Lightning Bolt']
    s = table(cards, names, names, names)
    start(s)
    return s


def cast_riftsweeper(s):
    source = put(s, 'Riftsweeper', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield'
    return source


def target(s, cid):
    d = s.state.rules.decision
    assert d is not None and cid in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[cid])


def shuffled_card(s, name, owner):
    found = [c for c in s.state.cards.values() if c.name == name and c.owner == owner]
    assert len(found) == 1
    assert found[0].zone == owner + ':library'
    assert not found[0].counters
    return found[0]


def test_complete_canonical_riftsweeper(cards):
    assert coverage.of_card_data(cards.resolve('Riftsweeper')).level == 'FULL'


@pytest.mark.parametrize('owner', ['p1', 'p2', 'p3'])
def test_face_up_card_is_shuffled_into_actual_owners_library(cards, owner):
    s = setup(cards)
    exiled = put(s, 'Grizzly Bears', 'exile', owner)
    cast_riftsweeper(s)
    before = {p: len(s.state.zones[p + ':library']) for p in ['p1', 'p2', 'p3']}
    target(s, exiled.id)
    settle(s)
    shuffled_card(s, 'Grizzly Bears', owner)
    assert len(s.state.zones[owner + ':library']) == before[owner] + 1
    roundtrip(s)


def test_face_down_exiled_card_cannot_be_selected_even_by_its_owner(cards):
    s = setup(cards)
    visible = put(s, 'Grizzly Bears', 'exile', 'p2')
    hidden = put(s, 'Llanowar Elves', 'hand')
    act(s, 'p1', type='move', card_ids=[hidden.id], to={'player': 'p1', 'zone': 'exile'}, face_down=True)
    cast_riftsweeper(s)
    d = s.state.rules.decision
    assert d is not None and hidden.id not in {o.id for o in d.options}
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[hidden.id])
    assert s.state.model_dump_json() == before
    target(s, visible.id)
    settle(s)
    assert hidden.zone == 'p1:exile' and hidden.face_down
    roundtrip(s)


def test_no_legal_face_up_card_does_not_leave_a_target_prompt(cards):
    s = setup(cards)
    hidden = put(s, 'Llanowar Elves', 'hand')
    act(s, 'p1', type='move', card_ids=[hidden.id], to={'player': 'p1', 'zone': 'exile'}, face_down=True)
    source = cast_riftsweeper(s)
    assert s.state.rules.decision is None
    assert source.zone == 'p1:battlefield'
    assert hidden.zone == 'p1:exile'
    roundtrip(s)


def test_target_zone_change_invalidates_old_object_without_shuffling_successor(cards):
    s = setup(cards)
    exiled = put(s, 'Grizzly Bears', 'exile', 'p2')
    cast_riftsweeper(s)
    target(s, exiled.id)
    before = len(s.state.zones['p2:library'])
    act(s, 'p2', type='move', card_ids=[exiled.id], to={'player': 'p2', 'zone': 'hand'})
    act(s, 'p2', type='move', card_ids=[exiled.id], to={'player': 'p2', 'zone': 'exile'})
    settle(s)
    assert exiled.zone == 'p2:exile'
    assert len(s.state.zones['p2:library']) == before
    roundtrip(s)


def test_actual_suspended_card_loses_time_counters_and_suspend_permission(cards):
    s = setup(cards)
    bolt = put(s, 'Rift Bolt', 'hand')
    mana(s, R=1)
    index = next(a.index for a in casting.chars.of(bolt, cards).abilities if 'suspend' in a.keywords)
    act(s, 'p1', type='activate_ability', card_id=bolt.id, ability=index, sources=[])
    assert bolt.zone == 'p1:exile' and bolt.counters.get('time') == 1
    assert bolt.id in s.state.rules.suspended
    cast_riftsweeper(s)
    target(s, bolt.id)
    settle(s)
    shuffled_card(s, 'Rift Bolt', 'p1')
    assert not s.state.rules.suspended
    to_phase(s, 'main1', turn=7)
    assert s.state.rules.decision is None
    assert not any(c.zone == 'stack' and c.name == 'Rift Bolt' for c in s.state.cards.values())
    roundtrip(s)


def test_actual_haunt_link_ends_when_haunting_card_is_shuffled(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    hunter = put(s, 'Blind Hunter', 'hand')
    mana(s, C=2, W=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=hunter.id, sources=[])
    settle(s)
    target(s, 'p2')
    settle(s)
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[hunter.id], sources=[])
    settle(s)
    target(s, bear.id)
    settle(s)
    assert hunter.zone == 'p1:exile' and s.state.rules.haunting
    cast_riftsweeper(s)
    target(s, hunter.id)
    settle(s)
    shuffled_card(s, 'Blind Hunter', 'p1')
    before = {p: s.state.players[p].life for p in ['p1', 'p2']}
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[bear.id], sources=[])
    settle(s)
    assert bear.zone == 'p2:graveyard' and s.state.rules.decision is None
    assert all(s.state.players[p].life == before[p] for p in before)
    roundtrip(s)


def test_true_cold_pending_owner_shuffle_survives_source_departure(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s = setup(cards)
    exiled = put(s, 'Grizzly Bears', 'exile', 'p3')
    source = cast_riftsweeper(s)
    target(s, exiled.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    before = len(s.state.zones['p3:library'])
    saved = tmp_path / 'riftsweeper50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
found=[c for c in s.state.cards.values() if c.name=='Grizzly Bears' and c.owner=='p3']
assert len(found)==1 and found[0].zone=='p3:library'
assert len(s.state.zones['p3:library'])==int(sys.argv[3])+1
assert s.state.cards[sys.argv[4]].zone=='p1:graveyard'
assert not s.state.zones['stack']
roundtrip(s)
"""
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), str(before), source.id],
        cwd=Path(app.__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
