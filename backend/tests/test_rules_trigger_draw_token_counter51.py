"""Construct a Cosmic Cube joins native second-card draws to token/counter and seventh-counter control effects."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.control import controller_of
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_counter_event_comparisons50 import resolve_only
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave18h_player_control import drive
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Construct a Cosmic Cube'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_draw_token_counter51_cards.json').read_text())
NAMES = [c['name'] for c in DATA]


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


def cast(s, name, pool, targets=(), *, pid='p1', resolve=True):
    wait_priority(s, pid)
    c = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=c.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return c


def setup(cards, initial=0, replacement=None):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, NAME, {'C': 2, 'B': 1})
    assert s.state.rules.draws_this_turn.get('p1') == 1 and not s.state.players['p1'].mana
    if initial:
        act(s, 'p1', type='counter', card_ids=[source.id], kind='plan', delta=initial)
    if replacement:
        put(s, replacement, 'battlefield')
    return s, source


def villains(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == 'Villain' and c.zone == 'p1:battlefield']


def draw_pending(cards, initial=0, replacement=None):
    s, source = setup(cards, initial, replacement)
    spell = cast(s, 'Divination', {'C': 2, 'U': 1}, resolve=False)
    resolve_only(s, spell)
    assert s.state.zones['stack']
    return s, source


def choose_opponent(s, pid='p2'):
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and pid in {o.id for o in d.options}
    assert 'p1' not in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[pid])
    settle(s)


def test_complete_canonical_supported(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_native_second_draw_creates_one_menace_token_and_one_plan_third_does_not(cards):
    from app.rules.plan import Plan

    s, source = setup(cards)
    cast(s, 'Divination', {'C': 2, 'U': 1})
    made, = villains(s)
    ch = Plan(s.state, 'p1', cards, None).ch(made)
    assert ch.pt == (2, 1) and 'menace' in ch.keywords and 'Villain' in ch.subtypes
    assert source.counters == {'plan': 1} and s.state.rules.draws_this_turn['p1'] == 3
    roundtrip(s)


def test_native_second_own_draw_on_opponent_turn_counts_but_their_draw_does_not(cards):
    s, source = setup(cards)
    to_phase(s, 'upkeep', turn=5)
    cast(s, 'Inspiration', {'C': 3, 'U': 1}, ['p1'])
    assert source.counters == {'plan': 1} and len(villains(s)) == 1
    to_phase(s, 'main1', turn=5)
    cast(s, 'Divination', {'C': 2, 'U': 1}, pid='p2')
    assert source.counters == {'plan': 1} and len(villains(s)) == 1
    roundtrip(s)


@pytest.mark.parametrize('replacement,plans,tokens', [('Doubling Season', 2, 2), ('Solemnity', 0, 1)])
def test_native_token_and_counter_replacements_are_independent(cards, replacement, plans, tokens):
    s, source = setup(cards, replacement=replacement)
    cast(s, 'Divination', {'C': 2, 'U': 1})
    assert source.counters.get('plan', 0) == plans and len(villains(s)) == tokens
    roundtrip(s)


@pytest.mark.parametrize('replacement,count', [(None, 7), ('Doubling Season', 8)])
def test_native_seventh_crossing_sacrifices_then_targets_opponent_for_next_turn(cards, replacement, count):
    s, source = draw_pending(cards, 6, replacement)
    old = s.state.rules.object_id(source.id)
    settle(s)
    assert source.zone == 'p1:graveyard' and s.state.rules.lki[old].counters == {'plan': count}
    choose_opponent(s)
    assert [(c.controlled, c.controller, c.status) for c in s.state.rules.player_control] == [('p2', 'p1', 'pending')]
    roundtrip(s)


def test_native_next_turn_control_allows_controller_to_act_then_expires(cards):
    s, source = draw_pending(cards, 6)
    island = put(s, 'Island', 'hand', 'p2')
    settle(s)
    choose_opponent(s)
    drive(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == 'main1')
    assert controller_of(s.state, 'p2') == 'p1'
    with pytest.raises(ActionError):
        act(s, 'p2', type='play_land', card_id=island.id)
    act(s, 'p1', type='play_land', card_id=island.id)
    assert island.zone == 'p2:battlefield' and island.controller == 'p2'
    drive(s, lambda s: s.state.turn.number == 6 and s.state.turn.phase == 'main1')
    assert controller_of(s.state, 'p2') == 'p2'
    roundtrip(s)


def test_counter_prohibition_prevents_seventh_but_still_creates_token(cards):
    s, source = draw_pending(cards, 6, 'Solemnity')
    settle(s)
    assert source.zone == 'p1:battlefield' and source.counters == {'plan': 6}
    assert len(villains(s)) == 1 and not s.state.rules.player_control
    roundtrip(s)


def test_unable_to_sacrifice_after_source_control_change_does_not_control_player(cards):
    s, source = draw_pending(cards, 6)
    for _ in range(30):
        if source.counters.get('plan') == 7:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert source.counters == {'plan': 7} and source.zone == 'p1:battlefield'
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert source.zone == 'p2:battlefield' and not s.state.rules.player_control
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('mode', ['draw', 'seventh', 'controlled'])
def test_true_cold_second_draw_seventh_and_player_control(cards, tmp_path, mode):
    import subprocess
    import sys

    s, source = draw_pending(cards, 0 if mode == 'draw' else 6)
    island = put(s, 'Island', 'hand', 'p2')
    if mode == 'controlled':
        settle(s)
        choose_opponent(s)
    saved = tmp_path / 'cube51.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.game.control import controller_of
from tests.game_helpers import act
from tests.test_rules_trigger_draw_token_counter51 import choose_opponent, villains
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.test_rules_wave18h_player_control import drive
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=s.state.cards[sys.argv[3]]
mode=sys.argv[4]
if mode!='controlled':
    assert s.state.zones['stack']
    settle(s)
    assert len(villains(s))==1
    if mode=='draw':
        assert source.zone=='p1:battlefield' and source.counters=={'plan':1}
    else:
        assert source.zone=='p1:graveyard'
        choose_opponent(s)
        assert [(c.controlled,c.controller,c.status) for c in s.state.rules.player_control]==[('p2','p1','pending')]
else:
    drive(s,lambda s:s.state.turn.number==5 and s.state.turn.phase=='main1')
    assert controller_of(s.state,'p2')=='p1'
    act(s,'p1',type='play_land',card_id=sys.argv[5])
    assert s.state.cards[sys.argv[5]].zone=='p2:battlefield'
    drive(s,lambda s:s.state.turn.number==6 and s.state.turn.phase=='main1')
    assert controller_of(s.state,'p2')=='p2'
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, mode, island.id],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_blink_successor_gets_no_old_counter_but_old_trigger_makes_token(cards):
    s, source = draw_pending(cards)
    old = s.state.rules.object_id(source.id)
    cast(s, 'Flicker of Fate', {'C': 1, 'W': 1}, [source.id])
    assert s.state.rules.object_id(source.id) != old
    assert source.zone == 'p1:battlefield' and not source.counters
    assert len(villains(s)) == 1
    roundtrip(s)
