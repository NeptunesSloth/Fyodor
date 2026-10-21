"""Counter alternatives are resolution choices, not announcement modes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditional_prevention import attack
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Sigurd, Jarl of Ravensthorpe', 'Plague Boiler', 'History of Benalia', 'Grizzly Bears', 'Sol Ring', 'Solemnity', 'Doubling Season']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/counter_alternatives50_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    return s


def cast_boiler(cards):
    s = game(cards)
    source = put(s, 'Plague Boiler', 'hand')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    return s, source


def activate_boiler(s, source):
    wait_priority(s, 'p1')
    mana(s, C=1, B=1, G=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    assert s.state.zones['stack'] and s.state.rules.decision is None
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert d.resume['step'] == 'pick_one'
        assert {o.id for o in d.options} == {'0', '1'}
    return d


def choose(s, option):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    settle(s)


@pytest.mark.parametrize('name', ['Sigurd, Jarl of Ravensthorpe', 'Plague Boiler'])
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_boiler_add_and_remove_are_paid_resolution_choices(cards):
    s, source = cast_boiler(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='plague', delta=1)
    activate_boiler(s, source)
    assert source.counters == {'plague': 1}
    choose(s, '0')
    assert source.counters == {'plague': 2} and not s.state.players['p1'].mana
    activate_boiler(s, source)
    choose(s, '1')
    assert source.counters == {'plague': 1}
    roundtrip(s)


def test_boiler_with_zero_counters_must_add_and_cannot_choose_removal(cards):
    s, source = cast_boiler(cards)
    assert activate_boiler(s, source) is None
    assert source.counters == {'plague': 1} and not s.state.players['p1'].mana
    roundtrip(s)


def test_boiler_upkeep_and_state_trigger_sacrifice_destroy_whole_board(cards):
    s, source = cast_boiler(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    their = put(s, 'Sol Ring', 'battlefield', 'p2')
    land = next(c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1')
    act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='counter', card_ids=[source.id], kind='plague', delta=2)
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    assert source.zone == 'p1:graveyard'
    assert own.zone == 'p1:graveyard' and their.zone == 'p2:graveyard'
    assert land.zone == 'p1:battlefield'
    roundtrip(s)


def test_boiler_ability_does_not_put_counters_on_blinked_successor(cards):
    s, source = cast_boiler(cards)
    wait_priority(s, 'p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, C=1, B=1, G=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    old = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert s.state.rules.object_id(source.id) != old
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[source.id].counters
    roundtrip(s)


def cast_sigurd(cards):
    s = game(cards)
    source = put(s, 'Sigurd, Jarl of Ravensthorpe', 'hand')
    mana(s, R=1, G=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    return s, source


def attacked_sigurd(cards):
    s, source = cast_sigurd(cards)
    attack(s, [source], turn=7)
    to_phase(s, 'main2')
    assert not source.tapped  # Actual vigilance; the unblocked attack gains three life.
    assert s.state.players['p1'].life == 43 and s.state.players['p2'].life == 37
    saga = put(s, 'History of Benalia', 'hand')
    mana(s, C=1, W=2)
    act(s, 'p1', type='cast_spell', card_id=saga.id, sources=[])
    settle(s)
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert d.min_choices == 0
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert saga.counters.get('lore') == 1
    return s, source, saga


def boast(s, source, saga):
    wait_priority(s, 'p1')
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[saga.id], sources=[])
    assert s.state.rules.decision is None
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'pick_one'


def test_sigurd_add_lore_triggers_chapter_and_optional_counter_recipient(cards):
    s, source, saga = attacked_sigurd(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    before = len([c for c in s.state.cards.values() if c.is_token and c.controller == 'p1'])
    boast(s, source, saga)
    choose(s, '0')
    assert saga.counters.get('lore') == 2
    d = s.state.rules.decision
    assert d is not None
    assert any(o.card_id == bear.id for o in d.options)
    assert all(o.card_id != source.id for o in d.options)
    choose(s, bear.id)
    assert bear.counters.get('+1/+1') == 1
    assert len([c for c in s.state.cards.values() if c.is_token and c.controller == 'p1']) == before + 1
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_sigurd_remove_lore_does_not_trigger_put_counter_rider_and_boast_once(cards):
    s, source, saga = attacked_sigurd(cards)
    boast(s, source, saga)
    choose(s, '1')
    assert not saga.counters and s.state.rules.decision is None
    mana(s, C=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[saga.id], sources=[])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_sigurd_cannot_boast_before_attacking(cards):
    s, source = cast_sigurd(cards)
    saga = put(s, 'History of Benalia', 'battlefield')
    settle(s)
    mana(s, C=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[saga.id], sources=[])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_sigurd_trample_lifelink_and_vigilance_in_native_combat(cards):
    from tests.test_rules_conditional_prevention import damage

    s, source = cast_sigurd(cards)
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack(s, [source], turn=7)
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': source.id}])
    damage(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, amounts=[2, 1])
    settle(s)
    assert blocker.zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 39 and s.state.players['p1'].life == 43
    assert not source.tapped and source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('option,expected', [('0', 2), ('1', 0)])
def test_true_cold_boiler_resolution_choice(cards, tmp_path, option, expected):
    import subprocess
    import sys

    s, source = cast_boiler(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='plague', delta=1)
    activate_boiler(s, source)
    saved = tmp_path / 'boiler50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d.resume['step']=='pick_one'
act(s,'p1',type='choose',decision_id=d.id,option_ids=[sys.argv[4]])
settle(s)
assert s.state.cards[sys.argv[3]].counters.get('plague',0)==int(sys.argv[5])
assert not s.state.players['p1'].mana
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, option, str(expected)],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_put_counter_prohibition_forces_removal_when_possible(cards):
    s, source = cast_boiler(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='plague', delta=1)
    put(s, 'Solemnity', 'battlefield')
    assert activate_boiler(s, source) is None
    assert not source.counters and not s.state.players['p1'].mana
    roundtrip(s)


def test_both_impossible_counter_instructions_do_nothing_after_payment(cards):
    s, source = cast_boiler(cards)
    put(s, 'Solemnity', 'battlefield')
    assert activate_boiler(s, source) is None
    assert not source.counters and not s.state.players['p1'].mana
    roundtrip(s)


def test_forced_add_uses_native_counter_replacement_doubling(cards):
    s, source = cast_boiler(cards)
    put(s, 'Doubling Season', 'battlefield')
    assert activate_boiler(s, source) is None
    assert source.counters == {'plague': 2} and not s.state.players['p1'].mana
    roundtrip(s)


def test_removing_counter_after_state_trigger_does_not_stop_boiler_sacrifice(cards):
    s, source = cast_boiler(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='plague', delta=2)
    d = activate_boiler(s, source)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['0'])
    assert source.counters.get('plague') == 3 and s.state.zones['stack']
    activate_boiler(s, source)
    choose(s, '1')
    assert source.zone == 'p1:graveyard' and bear.zone == 'p2:graveyard'
    roundtrip(s)


def test_source_departure_before_state_trigger_resolves_prevents_sacrifice_and_destruction(cards):
    s, source = cast_boiler(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='plague', delta=2)
    d = activate_boiler(s, source)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['0'])
    assert source.counters.get('plague') == 3 and s.state.zones['stack']
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert source.zone == 'p1:exile' and bear.zone == 'p2:battlefield'
    roundtrip(s)


def test_new_controller_can_boast_on_other_players_turn_after_same_object_attacked(cards):
    s, source, _ = attacked_sigurd(cards)
    saga = put(s, 'History of Benalia', 'battlefield', 'p2')
    act(s, 'p2', type='counter', card_ids=[saga.id], kind='lore', delta=1)
    settle(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', C=1)
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=1, targets=[saga.id], sources=[])
    settle(s)
    assert s.state.rules.decision.player == 'p2'
    choose(s, '0')
    d = s.state.rules.decision
    if d is not None:
        assert d.player == 'p2' and d.min_choices == 0
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert saga.counters.get('lore') == 2
    assert not s.state.players['p2'].mana
    roundtrip(s)


def test_blinked_sigurd_does_not_inherit_earlier_attack_permission(cards):
    s, source, saga = attacked_sigurd(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    mana(s, C=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[saga.id], sources=[])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_true_cold_sigurd_boast_choice_and_used_limit_persist(cards, tmp_path):
    import subprocess
    import sys

    s, source, saga = attacked_sigurd(cards)
    boast(s, source, saga)
    saved = tmp_path / 'sigurd50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana,wait_priority
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d.resume['step']=='pick_one'
act(s,'p1',type='choose',decision_id=d.id,option_ids=['0'])
settle(s)
if s.state.rules.decision is not None:
 d=s.state.rules.decision
 assert d.min_choices==0
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
 settle(s)
assert s.state.cards[sys.argv[4]].counters.get('lore')==2
wait_priority(s,'p1')
mana(s,C=1)
before=s.state.model_dump_json()
try:
 act(s,'p1',type='activate_ability',card_id=sys.argv[3],ability=1,targets=[sys.argv[4]],sources=[])
except ActionError: pass
else: raise AssertionError('Saved boast use was forgotten')
assert s.state.model_dump_json()==before
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, saga.id],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('initial,delta,expected', [(0, 1, 0), (1, -1, 1)])
def test_counter_options_use_resolution_state_not_announcement_state(cards, initial, delta, expected):
    s, source = cast_boiler(cards)
    if initial:
        act(s, 'p1', type='counter', card_ids=[source.id], kind='plague', delta=initial)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, C=1, B=1, G=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    assert s.state.zones['stack'] and s.state.rules.decision is None
    act(s, 'p1', type='counter', card_ids=[source.id], kind='plague', delta=delta)
    settle(s)
    if initial == 0:
        assert s.state.rules.decision is not None
        choose(s, '1')
    else:
        assert s.state.rules.decision is None
    assert source.counters.get('plague', 0) == expected
    assert not s.state.players['p1'].mana
    roundtrip(s)
