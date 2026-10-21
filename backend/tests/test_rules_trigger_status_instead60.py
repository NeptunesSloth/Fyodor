"""Native upkeep monarch and city blessing alternatives use one frozen resolution verdict."""
from __future__ import annotations

import json
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

NAME = 'Court of Cunning'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_status_instead60_cards.json').read_text())
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




def setup(cards, name=NAME, blessed=False):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    if blessed:
        forests = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest'][:9]
        act(s, 'p1', type='move', card_ids=[c.id for c in forests], to={'player': 'p1', 'zone': 'battlefield'})
    pools = {NAME: {'C': 1, 'U': 2}, 'Court of Bounty': {'C': 2, 'G': 2}, "Kumena's Awakening": {'C': 2, 'U': 2}}
    source = cast(s, name, pools[name])
    if name.startswith('Court'):
        assert s.state.table.monarch == 'p1'
    else:
        assert s.state.players['p1'].city_blessing == blessed
    return s, source


def other_monarch(s):
    to_phase(s, 'main1', turn=5)
    cast(s, 'Thorn of the Black Rose', {'C': 3, 'B': 1}, pid='p2')
    assert s.state.table.monarch == 'p2'


def cunning_pending(cards, monarch=True, players=('p1', 'p3')):
    s, source = setup(cards)
    if not monarch:
        other_monarch(s)
    put(s, 'Throne of the High City', 'battlefield')
    put(s, 'Throne of the High City', 'battlefield', 'p2')
    put(s, 'Boomerang', 'hand')
    put(s, 'Flicker of Fate', 'hand')
    to_phase(s, 'upkeep', turn=7)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=list(players))
    before = {p: len(s.state.zones[p + ':library']) for p in s.state.players}
    return s, source, before


def assert_milled(s, before, count, players=('p1', 'p3')):
    assert {p: before[p] - len(s.state.zones[p + ':library']) for p in before} == {
        p: count if p in players else 0 for p in before}


def throne(s, pid):
    from app.rules.plan import Plan

    land = put(s, 'Throne of the High City', 'battlefield', pid)
    wait_priority(s, pid)
    mana(s, pid=pid, C=4)
    a = next(a for a in Plan(s.state, pid, s.cards, None).ch(land).abilities if 'become the monarch' in a.text)
    act(s, pid, type='activate_ability', card_id=land.id, ability=a.index, sources=[])
    settle(s)
    assert land.zone == pid + ':graveyard' and s.state.table.monarch == pid


@pytest.mark.parametrize('name', [NAME, 'Court of Bounty', "Kumena's Awakening"])
def test_complete_canonicals(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('monarch', [False, True])
@pytest.mark.parametrize('players', [(), ('p1', 'p3')])
def test_native_cunning_any_number_players_single_branch(cards, monarch, players):
    s, source, before = cunning_pending(cards, monarch, players)
    settle(s)
    assert_milled(s, before, 10 if monarch else 2, players)
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('start_monarch', [False, True])
def test_native_cunning_status_changes_before_resolution(cards, start_monarch):
    s, source, before = cunning_pending(cards, start_monarch)
    throne(s, 'p2' if start_monarch else 'p1')
    assert_milled(s, before, 2 if start_monarch else 10)
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


def test_native_cunning_uses_original_trigger_controller_after_source_transfer(cards):
    s, source, before = cunning_pending(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert s.state.table.monarch == 'p1' and source.zone == 'p2:battlefield'
    assert_milled(s, before, 10)
    roundtrip(s)


def bounty_pending(cards, monarch=True):
    s, source = setup(cards, 'Court of Bounty')
    bear = put(s, 'Grizzly Bears', 'hand')
    land = put(s, 'Forest', 'hand')
    foreign = put(s, 'Grizzly Bears', 'hand', 'p2')
    if not monarch:
        other_monarch(s)
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    return s, source, bear, land, foreign


def accept_bounty(s, yes=True):
    d = s.state.rules.decision
    assert d is not None and d.kind == 'choose_cards' and d.min_choices == 0
    if not yes:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        settle(s)


@pytest.mark.parametrize('monarch', [False, True])
def test_native_bounty_branch_own_hand_selection_and_no_cast_cost(cards, monarch):
    s, source, bear, land, foreign = bounty_pending(cards, monarch)
    accept_bounty(s)
    d = s.state.rules.decision
    assert d is not None and foreign.id not in {o.card_id for o in d.options}
    assert (bear.id in {o.card_id for o in d.options}) == monarch
    chosen = bear if monarch else land
    act(s, 'p1', type='choose', decision_id=d.id,
        option_ids=[next(o.id for o in d.options if o.card_id == chosen.id)])
    settle(s)
    assert s.state.rules.decision is None
    assert chosen.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    assert foreign.zone == 'p2:hand' and source.zone == 'p1:battlefield'
    roundtrip(s)


def test_native_bounty_can_decline(cards):
    s, source, bear, land, foreign = bounty_pending(cards)
    accept_bounty(s, False)
    assert bear.zone == land.zone == 'p1:hand' and source.zone == 'p1:battlefield'
    assert foreign.zone == 'p2:hand' and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('blessed', [False, True])
def test_native_kumena_draws_all_or_only_original_controller(cards, blessed):
    s, source = setup(cards, "Kumena's Awakening", blessed)
    to_phase(s, 'upkeep', turn=7)
    before = {p: len(s.state.zones[p + ':hand']) for p in s.state.players}
    settle(s)
    assert {p: len(s.state.zones[p + ':hand']) - before[p] for p in before} == {
        p: 1 if not blessed or p == 'p1' else 0 for p in before}
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


def test_native_bounty_land_put_does_not_consume_land_play(cards):
    s, source, bear, land, foreign = bounty_pending(cards, False)
    accept_bounty(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id,
        option_ids=[next(o.id for o in d.options if o.card_id == land.id)])
    settle(s)
    other = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest' and c.id != land.id)
    act(s, 'p1', type='move', card_ids=[other.id], to={'player': 'p1', 'zone': 'hand'})
    to_phase(s, 'main1', turn=7)
    act(s, 'p1', type='play_land', card_id=other.id)
    assert land.zone == other.zone == 'p1:battlefield' and source.zone == 'p1:battlefield'
    assert bear.zone == 'p1:hand' and foreign.zone == 'p2:hand'
    roundtrip(s)


def test_native_kumena_gains_blessing_before_resolution_and_draws_only_once(cards):
    s, source = setup(cards, "Kumena's Awakening")
    forests = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest'][:8]
    act(s, 'p1', type='move', card_ids=[c.id for c in forests], to={'player': 'p1', 'zone': 'battlefield'})
    assert not s.state.players['p1'].city_blessing
    to_phase(s, 'upkeep', turn=7)
    from tests.test_rules_counter_event_comparisons50 import resolve_only
    spell = cast(s, 'Raise the Alarm', {'C': 1, 'W': 1}, resolve=False)
    resolve_only(s, spell)
    assert s.state.players['p1'].city_blessing
    before = {p: len(s.state.zones[p + ':hand']) for p in s.state.players}
    settle(s)
    assert {p: len(s.state.zones[p + ':hand']) - before[p] for p in before} == {'p1': 1, 'p2': 0, 'p3': 0}
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['control', 'bounce'])
def test_native_kumena_blessing_persists_with_original_trigger_controller(cards, mode):
    s, source = setup(cards, "Kumena's Awakening", True)
    to_phase(s, 'upkeep', turn=7)
    if mode == 'control':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    else:
        from tests.test_rules_counter_event_comparisons50 import resolve_only
        spell = cast(s, 'Boomerang', {'U': 2}, [source.id], resolve=False)
        resolve_only(s, spell)
    assert s.state.players['p1'].city_blessing
    before = {p: len(s.state.zones[p + ':hand']) for p in s.state.players}
    settle(s)
    assert {p: len(s.state.zones[p + ':hand']) - before[p] for p in before} == {'p1': 1, 'p2': 0, 'p3': 0}
    assert source.zone == ('p2:battlefield' if mode == 'control' else 'p1:hand')
    roundtrip(s)


@pytest.mark.parametrize('mode', ['bounce', 'blink'])
def test_native_cunning_source_departure_does_not_cancel_old_trigger(cards, mode):
    s, source, before = cunning_pending(cards)
    old = s.state.rules.object_id(source.id)
    cast(s, 'Boomerang' if mode == 'bounce' else 'Flicker of Fate',
         {'U': 2} if mode == 'bounce' else {'C': 1, 'W': 1}, [source.id])
    assert_milled(s, before, 10)
    assert source.zone == ('p1:hand' if mode == 'bounce' else 'p1:battlefield')
    assert s.state.rules.object_id(source.id) != old
    roundtrip(s)


@pytest.mark.parametrize('start_monarch', [False, True])
def test_native_bounty_checks_status_when_resolving_not_when_queued(cards, start_monarch):
    s, source = setup(cards, 'Court of Bounty')
    bear = put(s, 'Grizzly Bears', 'hand')
    put(s, 'Forest', 'hand')
    if not start_monarch:
        other_monarch(s)
    put(s, 'Throne of the High City', 'battlefield')
    put(s, 'Throne of the High City', 'battlefield', 'p2')
    to_phase(s, 'upkeep', turn=7)
    throne(s, 'p2' if start_monarch else 'p1')
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0
    assert (bear.id in {o.card_id for o in d.options}) != start_monarch
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert bear.zone == 'p1:hand' and source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['cunning', 'bounty', 'kumena'])
def test_true_cold_native_upkeep_status_branches(cards, tmp_path, mode):
    import subprocess
    import sys

    if mode == 'cunning':
        s, source, before = cunning_pending(cards)
        other = ''
    elif mode == 'bounty':
        s, source, bear, land, _ = bounty_pending(cards)
        before, other = {'land': land.id}, bear.id
    else:
        s, source = setup(cards, "Kumena's Awakening", True)
        to_phase(s, 'upkeep', turn=7)
        before = {p: len(s.state.zones[p + ':hand']) for p in s.state.players}
        other = ''
    saved = tmp_path / 'status60.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.test_rules_trigger_status_instead60 import assert_milled
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
mode=sys.argv[3]; before=json.loads(sys.argv[4])
if mode=='bounty':
    d=s.state.rules.decision
    assert d is not None and d.min_choices==0
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==sys.argv[5])])
    settle(s)
    assert s.state.cards[sys.argv[5]].zone=='p1:battlefield' and s.state.cards[before['land']].zone=='p1:hand'
    assert s.state.rules.decision is None
elif mode=='cunning':
    assert s.state.zones['stack']
    settle(s)
    assert_milled(s,before,10)
else:
    assert s.state.zones['stack']
    settle(s)
    assert {p:len(s.state.zones[p+':hand'])-before[p] for p in before}=={'p1':1,'p2':0,'p3':0}
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), mode, json.dumps(before), other],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
