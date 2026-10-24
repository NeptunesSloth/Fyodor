"""Four exact unless-pay recipes use native targeting and payment continuations."""
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

DATA = json.loads((Path(__file__).parent / 'fixtures/rhystic90_cards.json').read_text())
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



@pytest.mark.parametrize('name', ['Rhystic Lightning', 'Rhystic Syphon', 'Scarwood Bandits', 'Divert'])
def test_whole(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def cast(s, name, targets=(), pid='p1', mana=None, **kwargs):
    source = put(s, name, 'hand', pid=pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana=mana or {'C': 5, 'U': 2, 'B': 2, 'R': 1, 'G': 2})
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[], **kwargs)
    settle(s)
    return source


@pytest.mark.parametrize('payment,expected', [('pay', 38), ('decline', 36), (None, 36)])
def test_lightning_real_player_payment_branch(cards, payment, expected):
    s = game(cards)
    if payment:
        act(s, 'p2', type='add_mana', player='p2', mana={'C': 2})
    cast(s, 'Rhystic Lightning', ['p2'])
    if payment:
        assert s.state.rules.decision.player == 'p2'
        choose(s, [payment])
    assert s.state.players['p2'].life == expected
    assert s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('paid', [False, True])
def test_syphon_paid_prevents_both_native_life_outcomes(cards, paid):
    s = game(cards)
    if paid:
        act(s, 'p2', type='add_mana', player='p2', mana={'C': 3})
    cast(s, 'Rhystic Syphon', ['p2'])
    if paid:
        assert s.state.rules.decision.player == 'p2'
        choose(s, ['pay'])
    assert s.state.players['p2'].life == (40 if paid else 35)
    assert s.state.players['p1'].life == (40 if paid else 45)
    roundtrip(s)


def bandits_game(cards):
    s = game(cards)
    source = put(s, 'Scarwood Bandits', 'battlefield')
    target = put(s, 'Phyrexian Altar', 'battlefield', pid='p2')
    cast(s, 'Expedite', [source.id], mana={'R': 1})
    return s, source, target


def activate_bandits(s, source, target):
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'G': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id], sources=[])
    settle(s)


@pytest.mark.parametrize('payer', [None, 'p2', 'p3'])
def test_bandits_every_opponent_native_offer_in_apnap_then_control(cards, payer):
    s, source, target = bandits_game(cards)
    for pid in ['p2', 'p3']:
        act(s, pid, type='add_mana', player=pid, mana={'C': 2})
    activate_bandits(s, source, target)
    for pid in ['p2', 'p3']:
        assert s.state.rules.decision.player == pid
        choose(s, ['pay' if pid == payer else 'decline'])
    assert s.state.cards[target.id].controller == ('p1' if payer is None else 'p2')
    assert s.state.cards[source.id].tapped
    roundtrip(s)


def test_bandits_control_duration_original_source_departure_and_reentry(cards):
    s, source, target = bandits_game(cards)
    activate_bandits(s, source, target)
    assert s.state.cards[target.id].controller == 'p1'
    cast(s, 'Unsummon', [source.id], pid='p2', mana={'U': 1})
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert s.state.cards[target.id].controller == 'p2'
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'G': 2})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[], sources=[])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].controller == 'p2'
    roundtrip(s)


def hold(s):
    for pid in s.state.players:
        act(s, pid, type='set_prefs', hold_priority=True)


def on_stack(s, name, pid, targets, mana, **kwargs):
    source = put(s, name, 'hand', pid=pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana=mana)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[], **kwargs)
    return source


@pytest.mark.parametrize('paid', [False, True])
def test_divert_actual_payment_or_mandatory_new_legal_target(cards, paid):
    s = game(cards)
    hold(s)
    bolt = on_stack(s, 'Lightning Bolt', 'p2', ['p3'], {'R': 1, **({'C': 2} if paid else {})})
    cast(s, 'Divert', [bolt.id], mana={'U': 1})
    d = s.state.rules.decision
    if paid:
        assert d.player == 'p2'
        choose(s, ['pay'])
    else:
        assert d.player == 'p1' and d.resume['step'] == 'change_target'
        assert 'p2' in {o.id for o in d.options} and 'p3' not in {o.id for o in d.options}
        choose(s, ['p2'])
    assert s.state.players['p2'].life == (40 if paid else 37)
    assert s.state.players['p3'].life == (37 if paid else 40)
    roundtrip(s)


def test_divert_no_legal_alternate_keeps_original_target(cards):
    from app.rules.plan import Plan

    s = game(cards)
    hold(s)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    growth = on_stack(s, 'Giant Growth', 'p2', [bear.id], {'G': 1})
    cast(s, 'Divert', [growth.id], mana={'U': 1})
    assert s.state.rules.decision is None
    assert Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[bear.id]).pt == (5, 5)
    roundtrip(s)


def test_divert_multi_target_spell_atomic_cast_rejection(cards):
    from app.game.errors import ActionError

    s = game(cards)
    hold(s)
    first = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    second = put(s, 'Hill Giant', 'battlefield')
    bond = on_stack(s, 'Common Bond', 'p2', [first.id, second.id], {'C': 1, 'G': 1, 'W': 1}, target_counts=[1, 1])
    divert = put(s, 'Divert', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=divert.id, targets=[bond.id], sources=[])
    assert s.state.model_dump(mode='json') == before


def test_lightning_payer_is_actual_controlled_creature_controller_not_owner(cards):
    s = game(cards)
    giant = put(s, 'Hill Giant', 'battlefield', pid='p2')
    cast(s, 'Dominate', [giant.id], pid='p3', mana={'C': 7, 'U': 2}, x_value=4)
    assert s.state.cards[giant.id].controller == 'p3' and s.state.cards[giant.id].owner == 'p2'
    cast(s, 'Rhystic Lightning', [giant.id])
    assert s.state.rules.decision.player == 'p3'
    choose(s, ['pay'])
    assert s.state.cards[giant.id].zone == 'p3:battlefield'
    assert s.state.cards[giant.id].damage == 2
    roundtrip(s)


def resolve_one(s, cid):
    for _ in range(60):
        if s.state.cards[cid].zone != 'stack':
            return
        if s.state.rules.decision is not None:
            d = s.state.rules.decision
            assert 'keep' in {o.id for o in d.options}
            act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep'])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('Native stack object did not resolve')


def test_divert_payer_is_native_aethersnatched_spell_controller(cards):
    s = game(cards)
    hold(s)
    bolt = on_stack(s, 'Lightning Bolt', 'p2', ['p1'], {'R': 1})
    steal = on_stack(s, 'Aethersnatch', 'p3', [bolt.id], {'C': 6, 'U': 2})
    resolve_one(s, steal.id)
    assert s.state.cards[bolt.id].zone == 'stack'
    assert s.state.cards[bolt.id].controller == 'p3' and s.state.cards[bolt.id].owner == 'p2'
    cast(s, 'Divert', [bolt.id], mana={'U': 1})
    assert s.state.rules.decision.player == 'p3'
    choose(s, ['pay'])
    assert s.state.players['p1'].life == 37
    assert s.state.players['p2'].life == s.state.players['p3'].life == 40
    roundtrip(s)


def test_zero_floating_lightning_tax_native_manual_mana_and_atomic_early_pay(cards):
    from app.game.errors import ActionError

    s = game(cards)
    altar = put(s, 'Phyrexian Altar', 'battlefield', pid='p2')
    first = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    second = put(s, 'Hill Giant', 'battlefield', pid='p2')
    cast(s, 'Rhystic Lightning', ['p2'])
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
    assert s.state.model_dump(mode='json') == before
    for creature in [first, second]:
        act(s, 'p2', type='activate_ability', card_id=altar.id, ability=0, mana_choice='R', sources=[],
            cost_choices=[{'component': 0, 'cards': [creature.id]}])
    choose(s, ['pay'])
    assert s.state.players['p2'].life == 38
    assert s.state.cards[first.id].zone == s.state.cards[second.id].zone == 'p2:graveyard'
    assert s.state.players['p2'].mana == {}
    roundtrip(s)


def test_bandits_source_leaves_before_resolution_no_old_control_effect(cards):
    s, source, target = bandits_game(cards)
    hold(s)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'G': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id], sources=[])
    cast(s, 'Unsummon', [source.id], pid='p2', mana={'U': 1})
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert s.state.cards[target.id].controller == 'p2'
    roundtrip(s)


@pytest.mark.parametrize('stage', ['divert_payment', 'divert_retarget', 'bandits_after_payer'])
def test_true_cold_native_payment_retarget_and_shared_opponent_verdict(cards, tmp_path, stage):
    import os
    import subprocess
    import sys

    import app

    if stage == 'bandits_after_payer':
        s, source, target = bandits_game(cards)
        for pid in ['p2', 'p3']:
            act(s, pid, type='add_mana', player=pid, mana={'C': 2})
        activate_bandits(s, source, target)
        choose(s, ['pay'])
        assert s.state.rules.decision.player == 'p3'
        target_id = target.id
    else:
        s = game(cards)
        hold(s)
        bolt = on_stack(s, 'Lightning Bolt', 'p2', ['p3'], {'R': 1, **({'C': 2} if stage == 'divert_payment' else {})})
        cast(s, 'Divert', [bolt.id], mana={'U': 1})
        target_id = bolt.id
    saved = tmp_path / 'rhystic90.json'
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
stage,target=sys.argv[3:]
d=s.state.rules.decision
assert d
if stage=='divert_payment':
 assert d.player=='p2'
 ids=['pay']
elif stage=='divert_retarget':
 assert d.player=='p1' and d.resume['step']=='change_target'
 assert 'p3' not in {o.id for o in d.options}
 ids=['p2']
else:
 assert d.player=='p3' and s.state.cards[target].controller=='p2'
 ids=['decline']
act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
settle(s)
assert s.state.rules.decision is None
if stage=='bandits_after_payer':
 assert s.state.cards[target].controller=='p2'
else:
 assert s.state.players['p2'].life==(40 if stage=='divert_payment' else 37)
 assert s.state.players['p3'].life==(37 if stage=='divert_payment' else 40)
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), stage, target_id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
