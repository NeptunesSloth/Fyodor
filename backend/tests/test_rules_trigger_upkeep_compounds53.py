"""Exact compound upkeep sacrifice instructions preserve native independent effects."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Second Chance'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_upkeep_compounds53_cards.json').read_text())
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



def setup(cards, name=NAME, life=5):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, name, {'C': 2, 'U': 1} if name == NAME else {'C': 4, 'U': 3})
    s.state.players['p1'].life = life
    return s, source


def upkeep_pending(s):
    to_phase(s, 'upkeep', turn=7)


@pytest.mark.parametrize('name', [NAME, 'Elder Spawn'])
def test_actual_whole_canonicals(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('life', [5, 6])
def test_native_chance_intervening_life_and_actual_extra_turn(cards, life):
    s, source = setup(cards, life=life)
    upkeep_pending(s)
    settle(s)
    assert source.zone == ('p1:graveyard' if life == 5 else 'p1:battlefield')
    assert len(s.state.rules.extra_turns) == (1 if life == 5 else 0)
    if life == 5:
        to_phase(s, 'main1', turn=8)
        assert s.state.turn.active_player == 'p1' and s.state.rules.extra_turn
    roundtrip(s)


def test_native_chance_resolution_rechecks_life(cards):
    s, source = setup(cards)
    upkeep_pending(s)
    assert s.state.zones['stack']
    cast(s, 'Revitalize', {'C': 1, 'W': 1})
    assert s.state.players['p1'].life == 8
    assert source.zone == 'p1:battlefield' and not s.state.rules.extra_turns
    roundtrip(s)


def test_native_chance_source_departure_does_not_cancel_extra_turn(cards):
    s, source = setup(cards)
    upkeep_pending(s)
    assert s.state.zones['stack']
    cast(s, 'Boomerang', {'U': 2}, [source.id])
    assert source.zone == 'p1:hand' and len(s.state.rules.extra_turns) == 1
    roundtrip(s)


def test_native_chance_control_change_prevents_sacrifice_but_not_extra_turn(cards):
    s, source = setup(cards)
    upkeep_pending(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert source.zone == 'p2:battlefield' and len(s.state.rules.extra_turns) == 1
    assert s.state.rules.extra_turns[0]['player'] == 'p1'
    roundtrip(s)


def test_native_elder_no_island_sacrifices_then_deals_six(cards):
    s, source = setup(cards, 'Elder Spawn', 40)
    upkeep_pending(s)
    settle(s)
    assert source.zone == 'p1:graveyard' and s.state.players['p1'].life == 34
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_native_elder_optional_island_payment_gates_both_followups(cards, pay):
    s, source = setup(cards, 'Elder Spawn', 40)
    island = put(s, 'Island', 'battlefield')
    upkeep_pending(s)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'pay', 'decline'}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if pay else 'decline'])
    settle(s)
    if pay and s.state.rules.decision:
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[island.id])
        settle(s)
    assert source.zone == ('p1:battlefield' if pay else 'p1:graveyard')
    assert island.zone == ('p1:graveyard' if pay else 'p1:battlefield')
    assert s.state.players['p1'].life == (40 if pay else 34)
    roundtrip(s)


def test_native_elder_red_creature_cannot_block(cards):
    from tests.test_rules_conditional_prevention import attack, damage

    s, source = setup(cards, 'Elder Spawn', 40)
    blocker = put(s, 'Hill Giant', 'battlefield', 'p2')
    # Pay this turn's upkeep without manufacturing counterfactual survival.
    island = put(s, 'Island', 'battlefield')
    upkeep_pending(s)
    settle(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    if s.state.rules.decision:
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[island.id])
        settle(s)
    attack(s, [source], turn=7)
    to_phase(s, 'declare_blockers')
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': source.id}])
    act(s, 'p2', type='declare_blockers', blocks=[])
    damage(s)
    assert s.state.players['p2'].life == 34
    roundtrip(s)


def test_native_elder_departed_source_still_deals_damage(cards):
    s, source = setup(cards, 'Elder Spawn', 40)
    upkeep_pending(s)
    cast(s, 'Boomerang', {'U': 2}, [source.id])
    assert source.zone == 'p1:hand' and s.state.players['p1'].life == 34
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Elder Spawn'])
def test_true_cold_native_upkeep_continuations(cards, tmp_path, name):
    import subprocess
    import sys

    s, source = setup(cards, name, 5 if name == NAME else 40)
    upkeep_pending(s)
    saved = tmp_path / 'upkeep53.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack']
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
if sys.argv[4]=='Second Chance':
    assert len(s.state.rules.extra_turns)==1 and s.state.rules.extra_turns[0]['player']=='p1'
else:
    assert s.state.players['p1'].life==34
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, name],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_elder_cannot_sacrifice_stolen_source_still_deals_damage(cards):
    s, source = setup(cards, 'Elder Spawn', 40)
    upkeep_pending(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert source.zone == 'p2:battlefield' and s.state.players['p1'].life == 34
    assert s.state.players['p2'].life == 40
    roundtrip(s)
