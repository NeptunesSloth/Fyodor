"""Attached-upkeep offers preserve native payment, event-player and prevention semantics."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/attached92_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest', 'Island']


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


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)




def hold(s):
    for pid in s.state.players:
        act(s, pid, type='set_prefs', hold_priority=True)


def cast(s, name, targets=(), pid='p1', mana=None, **kwargs):
    source = put(s, name, 'hand', pid=pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana=mana or {'C': 5, 'U': 2, 'B': 2, 'R': 1, 'G': 2})
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[], **kwargs)
    settle(s)
    return source


def setup(cards, name):
    s = game(cards)
    target = put(s, 'Glorious Anthem' if name == 'Power Leak' else 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', 2)
    costs = {'Power Leak': {'C': 1, 'U': 1}, 'Errant Minion': {'C': 2, 'U': 1}, 'Mind Whip': {'C': 2, 'B': 2}}
    aura = cast(s, name, [target.id], pid='p2', mana=costs[name])
    return s, aura, target


def upkeep(s):
    hold(s)
    to_phase(s, 'upkeep', 4)
    assert s.state.zones.get('stack')


def amount(s, n):
    d = s.state.rules.decision
    assert d and d.options[0].id == '__number__'
    act(s, d.player, type='choose', decision_id=d.id, name=str(n))
    settle(s)


@pytest.mark.parametrize('name', ['Power Leak', 'Errant Minion', 'Mind Whip'])
def test_whole(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', ['Power Leak', 'Errant Minion'])
@pytest.mark.parametrize('n', [0, 1, 2, 41, 'pass'])
def test_original_host_player_pays_arbitrary_amount_and_only_this_damage_is_prevented(cards, name, n):
    s, _, _ = setup(cards, name)
    upkeep(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 41})
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    life = s.state.players['p1'].life
    amount(s, n)
    paid = 0 if n == 'pass' else n
    assert s.state.players['p1'].life == life - max(0, 2 - paid)
    assert s.state.players['p1'].mana == ({'C': 41 - paid} if paid < 41 else {})
    assert not s.state.rules.replacements and not s.state.rules.prevention
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_mind_whip_paid_skips_both_damage_and_tap(cards, pay):
    s, _, target = setup(cards, 'Mind Whip')
    upkeep(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    life = s.state.players['p1'].life
    choose(s, ['pay' if pay else 'decline'])
    assert s.state.players['p1'].life == life - (0 if pay else 2)
    assert s.state.cards[target.id].tapped == (not pay)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Power Leak', 'Errant Minion', 'Mind Whip'])
def test_actual_aura_graft_keeps_old_upkeep_player_and_original_host_reference(cards, name):
    s, aura, old_host = setup(cards, name)
    new_host = put(s, 'Glorious Anthem' if name == 'Power Leak' else 'Grizzly Bears', 'battlefield', pid='p3')
    upkeep(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    graft = put(s, 'Aura Graft', 'hand', pid='p3')
    wait_priority(s, 'p3')
    act(s, 'p3', type='add_mana', player='p3', mana={'C': 1, 'U': 1})
    act(s, 'p3', type='cast_spell', card_id=graft.id, targets=[aura.id], sources=[])
    settle(s)
    choose(s, [new_host.id])
    assert s.state.cards[aura.id].controller == 'p3' and s.state.cards[aura.id].attached_to == new_host.id
    assert s.state.rules.decision.player == 'p1'
    life = s.state.players['p1'].life
    if name == 'Mind Whip':
        choose(s, ['decline'])
        assert s.state.cards[old_host.id].tapped and not s.state.cards[new_host.id].tapped
        assert s.state.players['p1'].life == life - 2
    else:
        amount(s, 1)
        assert s.state.players['p1'].life == life - 1
    assert s.state.players['p3'].mana == {}
    roundtrip(s)


@pytest.mark.parametrize('name', ['Power Leak', 'Errant Minion'])
def test_manual_sacrifice_mana_is_chosen_explicitly_and_early_amount_atomic(cards, name):
    from app.game.errors import ActionError

    s, _, _ = setup(cards, name)
    altar = put(s, 'Phyrexian Altar', 'battlefield')
    fodder = put(s, 'Grizzly Bears', 'battlefield')
    upkeep(s)
    settle(s)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        amount(s, 1)
    assert s.state.model_dump_json() == before
    act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0, mana_choice='R', sources=[],
        cost_choices=[{'component': 0, 'cards': [fodder.id]}])
    amount(s, 1)
    assert s.state.cards[fodder.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].mana == {}
    roundtrip(s)


@pytest.mark.parametrize('first', ['Furnace of Rath', 'Errant Minion'])
def test_paid_prevention_competes_with_real_damage_doubling_in_native_616_order(cards, first):
    s, _, _ = setup(cards, 'Errant Minion')
    put(s, 'Furnace of Rath', 'battlefield', pid='p3')
    upkeep(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    settle(s)
    life = s.state.players['p1'].life
    amount(s, 1)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    choice = next(o for o in d.options if first in o.label)
    choose(s, [choice.id])
    assert s.state.players['p1'].life == life - (3 if first == 'Furnace of Rath' else 2)
    assert not any(r.get('label') == 'Errant Minion' for r in s.state.rules.replacements)
    roundtrip(s)


def test_unpreventable_damage_is_full_two_despite_payment_and_leaves_no_budget(cards):
    s, _, _ = setup(cards, 'Errant Minion')
    put(s, 'Leyline of Punishment', 'battlefield', pid='p3')
    upkeep(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 41})
    settle(s)
    life = s.state.players['p1'].life
    amount(s, 41)
    assert s.state.players['p1'].life == life - 2
    assert s.state.players['p1'].mana == {}
    assert not s.state.rules.prevention
    assert not any(r.get('label') == 'Errant Minion' for r in s.state.rules.replacements)
    roundtrip(s)


@pytest.mark.parametrize('stage', ['amount', 'replacement'])
def test_true_cold_native_amount_or_finite_prevention_choice(cards, tmp_path, stage):
    import os
    import subprocess
    import sys

    import app

    s, _, _ = setup(cards, 'Errant Minion')
    if stage == 'replacement':
        put(s, 'Furnace of Rath', 'battlefield', pid='p3')
    upkeep(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 41 if stage == 'amount' else 1})
    settle(s)
    life = s.state.players['p1'].life
    if stage == 'replacement':
        amount(s, 1)
    saved = tmp_path / 'attached92.json'
    saved.write_text(s.state.model_dump_json())
    backend = Path(app.__file__).resolve().parents[1]
    code = r'''
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
stage,life=sys.argv[3],int(sys.argv[4])
d=s.state.rules.decision
assert d and d.player=='p1'
if stage=='amount':
 assert d.options[0].id=='__number__'
 act(s,'p1',type='choose',decision_id=d.id,name='41')
else:
 option=next(o for o in d.options if 'Errant Minion' in o.label)
 act(s,'p1',type='choose',decision_id=d.id,option_ids=[option.id])
settle(s)
assert s.state.players['p1'].life==life-(0 if stage=='amount' else 2)
assert s.state.players['p1'].mana=={}
assert not s.state.rules.prevention
assert not any(r.get('label')=='Errant Minion' for r in s.state.rules.replacements)
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), stage, str(life)],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', ['Power Leak', 'Errant Minion', 'Mind Whip'])
def test_original_aura_departure_does_not_cancel_stacked_payment_damage_or_old_host_tap(cards, name):
    s, aura, host = setup(cards, name)
    upkeep(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    spell = put(s, 'Naturalize', 'hand', pid='p3')
    wait_priority(s, 'p3')
    act(s, 'p3', type='add_mana', player='p3', mana={'C': 1, 'G': 1})
    act(s, 'p3', type='cast_spell', card_id=spell.id, targets=[aura.id], sources=[])
    settle(s)
    assert s.state.cards[aura.id].zone == 'p2:graveyard'
    assert s.state.rules.decision.player == 'p1'
    life = s.state.players['p1'].life
    if name == 'Mind Whip':
        choose(s, ['decline'])
        assert s.state.cards[host.id].tapped
        assert s.state.players['p1'].life == life - 2
    else:
        amount(s, 1)
        assert s.state.players['p1'].life == life - 1
    assert not any(r.get('label') == name for r in s.state.rules.replacements)
    roundtrip(s)


def test_real_graft_controller_concession_during_616_does_not_leave_prevention_for_later_upkeep(cards):
    s = game(cards)
    old_host = put(s, 'Grizzly Bears', 'battlefield', pid='p3')
    host = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', 3)
    aura = cast(s, 'Errant Minion', [old_host.id], pid='p3', mana={'C': 2, 'U': 1})
    cast(s, 'Aura Graft', [aura.id], pid='p2', mana={'C': 1, 'U': 1})
    choose(s, [host.id])
    assert s.state.cards[aura.id].owner == 'p3' and s.state.cards[aura.id].controller == 'p2'
    put(s, 'Furnace of Rath', 'battlefield', pid='p3')
    upkeep(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    settle(s)
    amount(s, 1)
    assert s.state.rules.decision.player == 'p1'
    act(s, 'p2', type='concede')
    settle(s)
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert d.player == 'p1'
        choose(s, [next(o.id for o in d.options if 'Errant Minion' in o.label)])
    assert s.state.cards[aura.id].zone == 'p3:battlefield'
    assert not any(r.get('label') == 'Errant Minion' for r in s.state.rules.replacements)
    hold(s)
    to_phase(s, 'upkeep', 6)
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    life = s.state.players['p1'].life
    amount(s, 0)
    assert s.state.players['p1'].life == life - 4
    roundtrip(s)
