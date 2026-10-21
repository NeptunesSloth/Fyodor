"""Printed hand placements preserve private card selection and private library order."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.view import decision_view
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/hand_library_choices52_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='hlc', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s):
    for _ in range(100):
        d = s.state.rules.decision
        if d is not None:
            if d.kind == 'order' and d.resume.get('step') != 'order_library':
                act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
            else:
                return
        elif s.state.zones.get('stack'):
            act(s, s.state.rules.priority, type='pass_priority')
        else:
            return
    raise AssertionError('Did not settle')


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def setup(cards, name):
    names = [name, 'Grizzly Bears', 'Llanowar Elves', 'Forest', 'Island', 'Sol Ring', 'Serra Angel']
    s = table(cards, names, names, names)
    source = put(s, name, 'hand')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    return s, source


def cast(s, source, targets=()):
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'G': 2, 'U': 1, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=list(targets), sources=[])
    settle(s)


@pytest.mark.parametrize('name', ['Sawtooth Loon', 'Dream Cache', 'Stunted Growth'])
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('place', ['top', 'bottom'])
def test_dream_cache_places_both_together_with_private_selection_and_order(cards, place):
    s, source = setup(cards, 'Dream Cache')
    before = len(s.state.zones['p1:hand'])
    cast(s, source)
    assert len(s.state.zones['p1:hand']) == before - 1 + 3
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'pick_one'
    choose(s, ['0' if place == 'top' else '1'])
    d = s.state.rules.decision
    assert d is not None and d.kind == 'choose_cards'
    assert 'options' not in decision_view(s.state, d, 'p2')
    ids = [o.id for o in d.options[:2]]
    choose(s, ids)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'order_library'
    assert all(s.state.cards[c].zone == 'p1:hand' for c in ids)
    assert 'options' not in decision_view(s.state, d, 'p3')
    choose(s, list(reversed(ids)))
    lib = s.state.zones['p1:library']
    assert (lib[:2] if place == 'top' else lib[-2:]) == (list(reversed(ids)) if place == 'top' else ids)
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


def test_stunted_target_chooses_own_cards_and_order_privately(cards):
    s, source = setup(cards, 'Stunted Growth')
    for name in ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest']:
        put(s, name, 'hand', 'p2')
    before = len(s.state.zones['p2:hand'])
    cast(s, source, ['p2'])
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2' and d.min_choices == 3
    assert 'options' not in decision_view(s.state, d, 'p1')
    ids = [o.id for o in d.options[:3]]
    choose(s, ids)
    assert s.state.rules.decision.player == 'p2'
    choose(s, list(reversed(ids)))
    assert s.state.zones['p2:library'][:3] == list(reversed(ids))
    assert len(s.state.zones['p2:hand']) == before - 3
    roundtrip(s)


@pytest.mark.parametrize('remaining', [0, 1, 2])
def test_stunted_short_hand_uses_as_many_as_possible(cards, remaining):
    s, source = setup(cards, 'Stunted Growth')
    for cid in list(s.state.zones['p2:hand']):
        act(s, 'p2', type='move', card_ids=[cid], to={'player': 'p2', 'zone': 'graveyard'})
    for card_name in ['Grizzly Bears', 'Llanowar Elves'][:remaining]:
        put(s, card_name, 'hand', 'p2')
    ids = list(s.state.zones['p2:hand'])
    assert len(ids) == remaining
    cast(s, source, ['p2'])
    if remaining > 1:
        assert s.state.rules.decision.kind == 'order'
        choose(s, list(reversed(ids)))
    assert not s.state.zones['p2:hand']
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone == 'p2:library' for c in ids)
    roundtrip(s)


def test_loon_actual_two_triggers_return_self_then_draw_and_bottom(cards):
    s, source = setup(cards, 'Sawtooth Loon')
    before = len(s.state.zones['p1:hand'])
    cast(s, source)
    d = s.state.rules.decision
    assert d is not None
    # Whichever trigger is ordered first, each native instruction must complete.
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            break
        if d.resume.get('step') == 'put_back':
            choose(s, [o.id for o in d.options if o.id != source.id][:2])
        elif d.resume.get('step') == 'order_library':
            choose(s, [o.id for o in d.options])
        else:
            assert any(o.id == source.id for o in d.options)
            choose(s, [source.id])
    assert source.zone == 'p1:hand'
    assert len(s.state.zones['p1:hand']) == before
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name', ['Dream Cache', 'Stunted Growth', 'Sawtooth Loon'])
def test_true_cold_hidden_hand_continuations(cards, tmp_path, name):
    import subprocess
    import sys

    s, source = setup(cards, name)
    if name == 'Stunted Growth':
        for card_name in ['Grizzly Bears', 'Llanowar Elves', 'Forest', 'Sol Ring']:
            put(s, card_name, 'hand', 'p2')
    cast(s, source, ['p2'] if name == 'Stunted Growth' else [])
    saved = tmp_path / 'hand-library.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_hand_library_choices52 import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
name=sys.argv[3]
source=sys.argv[4]
if name=='Sawtooth Loon' and s.state.rules.decision.resume.get('step')!='put_back':
 d=s.state.rules.decision
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[source])
 settle(s)
if name=='Dream Cache':
 d=s.state.rules.decision
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['1'])
 settle(s)
d=s.state.rules.decision
assert d is not None and d.kind=='choose_cards'
pid=d.player
ids=[o.id for o in d.options if name!='Sawtooth Loon' or o.id!=source][:3 if name=='Stunted Growth' else 2]
act(s,pid,type='choose',decision_id=d.id,option_ids=ids)
settle(s)
d=s.state.rules.decision
assert d is not None and d.resume['step']=='order_library'
assert all(s.state.cards[c].zone==pid+':hand' for c in ids)
act(s,pid,type='choose',decision_id=d.id,option_ids=list(reversed(ids)))
settle(s)
lib=s.state.zones[pid+':library']
assert (lib[:3]==list(reversed(ids)) if name=='Stunted Growth' else lib[-2:]==ids)
if name=='Sawtooth Loon':
 if s.state.rules.decision is not None:
  d=s.state.rules.decision
  act(s,d.player,type='choose',decision_id=d.id,option_ids=[source])
  settle(s)
 assert s.state.cards[source].zone=='p1:hand'
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), name, source.id],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_loon_can_return_another_white_creature_then_fly_past_ground_blocker(cards):
    from app.game.errors import ActionError
    from tests.test_rules_conditional_prevention import attack, damage

    s, source = setup(cards, 'Sawtooth Loon')
    angel = put(s, 'Serra Angel', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, source)
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            break
        if d.resume.get('step') == 'put_back':
            choose(s, [o.id for o in d.options if o.id != angel.id][:2])
        elif d.resume.get('step') == 'order_library':
            choose(s, [o.id for o in d.options])
        else:
            assert any(o.id == angel.id for o in d.options)
            choose(s, [angel.id])
    assert angel.zone == 'p1:hand' and source.zone == 'p1:battlefield'
    attack(s, [source], target='p2', turn=7)
    to_phase(s, 'declare_blockers')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': source.id}])
    assert s.state.model_dump_json() == before
    act(s, 'p2', type='declare_blockers', blocks=[])
    before_life = s.state.players['p2'].life
    damage(s)
    assert s.state.players['p2'].life == before_life - 2
    roundtrip(s)
