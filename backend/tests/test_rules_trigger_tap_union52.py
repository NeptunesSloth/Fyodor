"""Printed non-target cast counters preserve the original spell and independent instructions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Royal Decree']
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_tap_union52_cards.json').read_text())


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


def cast(s, name, pool, targets=(), pid='p1', resolve=True):
    wait_priority(s, pid)
    spell = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=spell.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return spell



def setup(cards):
    names = [c['name'] for c in DATA] + ['Forest','Sol Ring','Boomerang']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, NAMES[0], {'C': 2,'W': 2})
    icy = put(s, 'Icy Manipulator', 'battlefield')
    return s, source, icy


def icy_tap(s, icy, target, *, resolve=True):
    wait_priority(s, 'p1')
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=icy.id, ability=0, sources=[], targets=[target.id])
    if resolve:
        settle(s)


def test_full_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAMES[0])).level == 'FULL'


@pytest.mark.parametrize('name,hit', [('Swamp',True),('Mountain',True),('Badlands',True),('Mardu Scout',True),('Vampire Nighthawk',True),('Island',False),('Grizzly Bears',False),('Sol Ring',False)])
def test_native_foreign_tap_matches_union_once_and_damages_permanent_controller(cards, name, hit):
    s, _, icy = setup(cards)
    target = put(s, name, 'battlefield', 'p2')
    icy_tap(s, icy, target)
    assert target.tapped and icy.tapped
    assert s.state.players['p2'].life == 40-int(hit) and s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name', ['Swamp','Mountain','Badlands'])
def test_native_mana_ability_tap_emits_single_trigger(cards, name):
    from tests.test_rules_wave7b_activation import ability_index

    s, _, _ = setup(cards)
    target = put(s, name, 'battlefield', 'p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=target.id, ability=ability_index(s, target, 'Add'), sources=[])
    settle(s)
    assert target.tapped and s.state.players['p2'].life == 39
    roundtrip(s)


def pending_tap(cards):
    s, source, icy = setup(cards)
    target = put(s, 'Swamp', 'battlefield', 'p2')
    icy_tap(s, icy, target, resolve=False)
    ability = s.state.zones['stack'][-1]
    for _ in range(30):
        if ability not in s.state.zones['stack']:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert target.tapped and s.state.zones['stack'] and s.state.players['p2'].life == 40
    return s, source, target


@pytest.mark.parametrize('dead', [False,True])
def test_controller_at_resolution_or_last_known_controller_receives_damage(cards, dead):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s, _, target = pending_tap(cards)
    act(s, 'p1', type='set_controller', card_ids=[target.id], player='p3')
    if dead:
        spell = cast(s, 'Wrecking Ball', {'C': 2,'B': 1,'R': 1}, [target.id], resolve=False)
        resolve_only(s, spell)
        assert target.zone == 'p2:graveyard'
    settle(s)
    assert s.state.players['p2'].life == 40 and s.state.players['p3'].life == 39
    roundtrip(s)


def test_repeated_native_tap_of_already_tapped_permanent_does_not_trigger(cards):
    s, _, icy = setup(cards)
    target = put(s, 'Swamp', 'battlefield', 'p2')
    icy_tap(s, icy, target)
    assert s.state.players['p2'].life == 39
    act(s, 'p1', type='tap', card_ids=[icy.id], tapped=False)
    icy_tap(s, icy, target)
    assert s.state.players['p2'].life == 39
    roundtrip(s)


def test_native_cumulative_upkeep_age_payment_and_sacrifice(cards):
    s, source, _ = setup(cards)
    to_phase(s, 'upkeep', turn=7)
    mana(s, W=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and source.counters == {'age': 1}
    assert 'pay' in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert source.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    to_phase(s, 'upkeep', turn=10)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and source.counters == {'age': 2}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['sacrifice'])
    settle(s)
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


def test_departed_enchantment_still_deals_original_trigger_damage(cards):
    s, source, _ = pending_tap(cards)
    cast(s, 'Boomerang', {'U': 2}, [source.id])
    assert source.zone == 'p1:hand' and s.state.players['p2'].life == 39
    roundtrip(s)


@pytest.mark.parametrize('mode', ['tap_lki','upkeep'])
def test_true_cold_original_tap_controller_or_cumulative_payment(cards, tmp_path, mode):
    import app
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    if mode == 'tap_lki':
        s, source, target = pending_tap(cards)
        act(s, 'p1', type='set_controller', card_ids=[target.id], player='p3')
        spell = cast(s, 'Wrecking Ball', {'C': 2,'B': 1,'R': 1}, [target.id], resolve=False)
        resolve_only(s, spell)
        assert target.zone == 'p2:graveyard' and s.state.zones['stack']
    else:
        s, source, _ = setup(cards)
        to_phase(s, 'upkeep', turn=7)
        mana(s, W=1)
        settle(s)
        assert s.state.rules.decision is not None and source.counters == {'age': 1}
    saved = tmp_path / 'royal.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=s.state.cards[sys.argv[3]]
if sys.argv[4]=='tap_lki':
 assert s.state.zones['stack']
 settle(s)
 assert s.state.players['p2'].life==40 and s.state.players['p3'].life==39
else:
 d=s.state.rules.decision
 assert d is not None and source.counters=={'age':1}
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
 settle(s)
 assert source.zone=='p1:battlefield' and not s.state.players['p1'].mana
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, mode],
                            capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr
