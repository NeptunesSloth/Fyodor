"""Native alternative and upkeep taxes retain actual payers and affected objects."""
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

NAMES = ['Sabertooth Cobra','Glass Asp','Nafs Asp','Quenchable Fire']
DATA = json.loads((Path(__file__).parent / 'fixtures/deferred82_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Lightning Bolt', 'Counterspell', 'Forest', 'Island', 'Mountain']


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


def choose(s, ids, resolve=True):
    d = s.state.rules.decision
    assert d
    result = act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    if resolve:
        settle(s)
    return result


def cast(s, name, targets=(), pid='p1', resolve=True, **extra):
    c = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana={'C': 30, 'W': 4, 'U': 5, 'R': 2, 'B': 3, 'G': 3})
    act(s, pid, type='cast_spell', card_id=c.id, targets=list(targets), sources=[], **extra)
    if resolve:
        settle(s)
    return c


@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def fire_game(cards):
    s=game(cards)
    source=cast(s,NAMES[3],['p2'])
    assert s.state.players['p2'].life==37
    assert len(s.state.rules.deferred_payments)==1
    return s,source


def test_fire_real_resolution_payment_special_action_no_stack_and_once_only(cards):
    from app.game.errors import ActionError
    s,source=fire_game(cards)
    row=s.state.rules.deferred_payments[0]
    assert row.payer=='p2' and row.cost=='{U}'
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    wait_priority(s,'p2')
    assert s.view('p2')['rules']['hints']['deferred_payments'][0]['id']==row.id
    assert 'deferred_payments' not in s.view('p3')['rules']['hints']
    stack=list(s.state.zones.get('stack',[]))
    act(s,'p2',type='pay_deferred',window_id=row.id,sources=[])
    assert not s.state.rules.deferred_payments and not s.state.rules.delayed
    assert s.state.zones.get('stack',[])==stack
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p2',type='pay_deferred',window_id=row.id,sources=[])
    assert s.state.model_dump(mode='json')==before
    to_phase(s,'upkeep',4)
    settle(s)
    assert s.state.players['p2'].life==37
    roundtrip(s)


def test_fire_unpaid_deadline_triggers_and_payment_is_too_late(cards):
    from app.game.errors import ActionError
    s,source=fire_game(cards)
    row=s.state.rules.deferred_payments[0]
    to_phase(s,'upkeep',4)
    assert not s.state.rules.deferred_payments
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p2',type='pay_deferred',window_id=row.id,sources=[])
    assert s.state.model_dump(mode='json')==before
    settle(s)
    assert s.state.players['p2'].life==34
    roundtrip(s)


def combat_game(cards,name):
    s=game(cards)
    source=cast(s,name)
    to_phase(s,'declare_attackers',4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    to_phase(s,'main2',4)
    settle(s)
    assert len(s.state.rules.deferred_payments)==1
    return s,source


@pytest.mark.parametrize('name',NAMES[:3])
@pytest.mark.parametrize('pay',[False,True])
def test_real_combat_damage_opens_original_players_exact_before_step_window(cards,name,pay):
    s,source=combat_game(cards,name)
    life=s.state.players['p2'].life
    poison=s.state.players['p2'].resources.get('poison',0)
    row=s.state.rules.deferred_payments[0]
    assert row.payer=='p2'
    if name==NAMES[0]:
        assert poison==1
    if pay:
        act(s,'p1',type='move',card_ids=[source.id],to={'zone':'exile'})
        act(s,'p2',type='add_mana',player='p2',mana={'C':2})
        wait_priority(s,'p2')
        act(s,'p2',type='pay_deferred',window_id=row.id,sources=[])
        assert not s.state.rules.deferred_payments
    to_phase(s,'upkeep' if name==NAMES[0] else 'draw',5)
    settle(s)
    assert not s.state.rules.deferred_payments
    if name==NAMES[0]:
        assert s.state.players['p2'].resources.get('poison',0)==(1 if pay else 2)
        assert s.state.players['p2'].life==life
    else:
        assert s.state.players['p2'].life==life-(0 if pay else 2 if name==NAMES[1] else 1)
    roundtrip(s)


def test_fire_special_action_is_available_with_nonempty_stack_and_wrong_payer_rejected(cards):
    from app.game.errors import ActionError
    s,source=fire_game(cards)
    row=s.state.rules.deferred_payments[0]
    act(s,'p3',type='set_prefs',hold_priority=True)
    bolt=cast(s,'Lightning Bolt',['p1'],pid='p3',resolve=False)
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p3',type='pay_deferred',window_id=row.id,sources=[])
    assert s.state.model_dump(mode='json')==before
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    wait_priority(s,'p2')
    stack=list(s.state.zones['stack'])
    act(s,'p2',type='pay_deferred',window_id=row.id,sources=[])
    assert s.state.zones['stack']==stack and s.state.cards[bolt.id].zone=='stack'
    assert not s.state.rules.deferred_payments
    settle(s)
    assert s.state.players['p1'].life==37
    roundtrip(s)


def test_fire_payment_native_mana_ability_inside_saved_payment_decision(cards):
    s,source=fire_game(cards)
    row=s.state.rules.deferred_payments[0]
    land=put(s,'Island','battlefield','p2')
    act(s,'p2',type='set_prefs',payment='self')
    wait_priority(s,'p2')
    act(s,'p2',type='pay_deferred',window_id=row.id)
    assert s.state.rules.decision and s.state.rules.decision.resume['step']=='pay_mana'
    act(s,'p2',type='activate_ability',card_id=land.id,ability=0,sources=[])
    if s.state.rules.decision:
        choose(s,['pay'])
    assert not s.state.rules.deferred_payments and not s.state.rules.delayed
    assert s.state.cards[land.id].tapped
    roundtrip(s)


def test_cancelled_native_payment_keeps_window_and_delayed_trigger(cards):
    s,source=fire_game(cards)
    row=s.state.rules.deferred_payments[0]
    put(s,'Island','battlefield','p2')
    act(s,'p2',type='set_prefs',payment='self')
    wait_priority(s,'p2')
    act(s,'p2',type='pay_deferred',window_id=row.id)
    assert s.state.rules.decision
    choose(s,['cancel'],resolve=False)
    assert len(s.state.rules.deferred_payments)==1 and s.state.rules.delayed[0].id==row.delayed
    roundtrip(s)


@pytest.mark.parametrize('kind',['fire-payment','glass-unpaid'])
def test_fresh_process_typed_window_native_payment_or_delayed_draw_trigger(cards,tmp_path,kind):
    import os
    import subprocess
    import sys

    import app

    backend = Path(app.__file__).resolve().parents[1]
    if kind=='fire-payment':
        s,source=fire_game(cards)
        land=put(s,'Island','battlefield','p2')
        act(s,'p2',type='set_prefs',payment='self')
        wait_priority(s,'p2')
        act(s,'p2',type='pay_deferred',window_id=s.state.rules.deferred_payments[0].id)
        assert s.state.rules.decision and s.state.rules.decision.resume['step']=='pay_mana'
    else:
        s,source=combat_game(cards,NAMES[1])
        land=source
    saved=tmp_path/'deferred.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
kind,land=sys.argv[3:]
if kind=='fire-payment':
 assert s.state.rules.decision.resume['step']=='pay_mana'
 act(s,'p2',type='activate_ability',card_id=land,ability=0,sources=[])
 d=s.state.rules.decision
 if d:
  act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
 settle(s)
 assert not s.state.rules.deferred_payments and not s.state.rules.delayed and s.state.cards[land].tapped
 to_phase(s,'upkeep',4)
 settle(s)
 assert s.state.players['p2'].life==37
else:
 life=s.state.players['p2'].life
 to_phase(s,'draw',5)
 settle(s)
 assert s.state.players['p2'].life==life-2 and not s.state.rules.deferred_payments
assert GameState.model_validate_json(s.state.model_dump_json()).model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),kind,land.id],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


def test_nafs_asp_last_chance_payment_in_affected_players_upkeep(cards):
    s,source=combat_game(cards,NAMES[2])
    life=s.state.players['p2'].life
    row=s.state.rules.deferred_payments[0]
    to_phase(s,'upkeep',5)
    assert s.state.rules.deferred_payments[0].id==row.id
    act(s,'p2',type='add_mana',player='p2',mana={'C':1})
    wait_priority(s,'p2')
    act(s,'p2',type='pay_deferred',window_id=row.id,sources=[])
    to_phase(s,'draw',5)
    settle(s)
    assert s.state.players['p2'].life==life and not s.state.rules.deferred_payments
    roundtrip(s)


@pytest.mark.parametrize('blink',[False,True])
def test_fire_planeswalker_original_recipient_and_actual_original_controller(cards,blink):
    s=game(cards)
    target=cast(s,'Ugin, the Spirit Dragon')
    act(s,'p1',type='set_controller',card_ids=[target.id],player='p2')
    cast(s,NAMES[3],[target.id])
    assert s.state.cards[target.id].counters['loyalty']==4
    row=s.state.rules.deferred_payments[0]
    assert row.payer=='p2'
    if blink:
        cast(s,"Teferi's Time Twist",[target.id],pid='p2')
        to_phase(s,'end',1)
        settle(s)
        assert s.state.cards[target.id].counters['loyalty']==7
    else:
        act(s,'p2',type='set_controller',card_ids=[target.id],player='p3')
    to_phase(s,'upkeep',4)
    settle(s)
    assert s.state.cards[target.id].counters['loyalty']==(7 if blink else 1)
    assert not s.state.rules.deferred_payments
    roundtrip(s)


def test_two_real_casts_same_card_create_independent_original_object_windows(cards):
    s,source=fire_game(cards)
    original=s.state.rules.deferred_payments[0]
    cast(s,'Regrowth',[source.id])
    assert s.state.cards[source.id].zone=='p1:hand'
    cast(s,NAMES[3],['p2'])
    assert len(s.state.rules.deferred_payments)==2
    assert len({w.id for w in s.state.rules.deferred_payments})==2
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    wait_priority(s,'p2')
    act(s,'p2',type='pay_deferred',window_id=original.id,sources=[])
    assert len(s.state.rules.deferred_payments)==1 and s.state.rules.deferred_payments[0].id!=original.id
    to_phase(s,'upkeep',4)
    settle(s)
    assert s.state.players['p2'].life==31
    roundtrip(s)


def test_draw_step_deadline_closes_before_native_draw_replacement_choice(cards):
    s,source=combat_game(cards,NAMES[2])
    words=put(s,'Words of Wind','battlefield','p2')
    put(s,'Island','battlefield','p2')
    life=s.state.players['p2'].life
    to_phase(s,'upkeep',5)
    act(s,'p2',type='add_mana',player='p2',mana={'C':1})
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=words.id,ability=0,sources=[])
    settle(s)
    to_phase(s,'draw',5)
    assert s.state.rules.decision and s.state.rules.decision.player=='p2'
    assert not s.state.rules.deferred_payments
    assert s.state.rules.pending_triggers and not s.state.rules.stack
    assert s.state.players['p2'].life==life
    for _ in range(5):
        d=s.state.rules.decision
        if not d:
            break
        choose(s,[d.options[0].id])
    settle(s)
    assert s.state.players['p2'].life==life-1
    roundtrip(s)


def test_fire_initial_damage_prevented_and_reflected_keeps_original_target_payer(cards):
    s=game(cards)
    source=cast(s,NAMES[3],['p2'],resolve=False)
    cast(s,'Deflecting Palm',pid='p2')
    d=s.state.rules.decision
    assert d and d.player=='p2'
    options=[o.id for o in d.options if o.card_id==source.id or 'Quenchable Fire' in o.label]
    assert len(options)==1
    choose(s,options)
    assert s.state.players['p2'].life==40 and s.state.players['p1'].life==37
    row=s.state.rules.deferred_payments[0]
    assert row.payer=='p2'
    to_phase(s,'upkeep',4)
    settle(s)
    assert s.state.players['p2'].life==37 and s.state.players['p1'].life==37
    roundtrip(s)


def test_missing_original_legacy_damage_player_is_explicit_manual_fallback(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    s=game(cards)
    source=cast(s,NAMES[0])
    to_phase(s,'declare_attackers',4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    to_phase(s,'combat_damage',4)
    body=s.state.model_dump(mode='json')
    entries=list(body['rules']['stack'].values())
    assert len(entries)==1 and entries[0]['event']['players']==['p2']
    entries[0]['event'].pop('players')
    loaded=GameSession(GameState.model_validate(body),cards=cards)
    settle(loaded)
    d=loaded.state.rules.decision
    assert d and d.kind=='manual_resolution' and 'original affected player' in d.prompt
    assert not loaded.state.rules.deferred_payments
    choose(loaded,['done'])
    assert loaded.state.players['p2'].resources.get('poison',0)==0


def test_unaffordable_payment_rejects_atomically_without_consuming_window(cards):
    from app.game.errors import ActionError
    s,source=fire_game(cards)
    row=s.state.rules.deferred_payments[0]
    act(s,'p2',type='set_prefs',hold_priority=True)
    wait_priority(s,'p2')
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p2',type='pay_deferred',window_id=row.id,sources=[])
    assert s.state.model_dump(mode='json')==before


def test_quench_original_planeswalker_payer_retains_special_action_after_control_change(cards):
    from app.game.errors import ActionError

    s = game(cards)
    target = cast(s, 'Ugin, the Spirit Dragon')
    act(s, 'p1', type='set_controller', card_ids=[target.id], player='p2')
    cast(s, NAMES[3], [target.id])
    row = s.state.rules.deferred_payments[0]
    assert row.payer == 'p2' and s.state.cards[target.id].counters['loyalty'] == 4
    act(s, 'p2', type='set_controller', card_ids=[target.id], player='p3')
    act(s, 'p3', type='set_prefs', hold_priority=True)
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p3', resolve=False)
    assert s.state.rules.priority == 'p3'
    assert 'deferred_payments' not in s.view('p3')['rules']['hints']
    assert s.view('p2')['rules']['hints']['deferred_payments'][0]['id'] == row.id
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p3', type='pay_deferred', window_id=row.id, sources=[])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    wait_priority(s, 'p2')
    stack = list(s.state.zones['stack'])
    act(s, 'p2', type='pay_deferred', window_id=row.id, sources=[])
    assert s.state.zones['stack'] == stack and s.state.cards[bolt.id].zone == 'stack'
    assert not s.state.rules.deferred_payments and not s.state.rules.delayed
    settle(s)
    to_phase(s, 'upkeep', 4)
    settle(s)
    assert s.state.cards[target.id].controller == 'p3'
    assert s.state.cards[target.id].counters['loyalty'] == 4
    roundtrip(s)
