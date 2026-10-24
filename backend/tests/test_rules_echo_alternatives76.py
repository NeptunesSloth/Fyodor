"""Every other player pays one shared nominal life-gain event as a real alternative cost."""

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
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Thick-Skinned Goblin"]
DATA = json.loads((Path(__file__).parent / "fixtures/echo_alternatives76_cards.json").read_text())


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,name='Uktabi Drake',goblin=True):
    ns=[c['name'] for c in DATA]*2
    s=table(cards,ns,ns,ns)
    for pid in ['p1','p2','p3']:
        act(s,pid,type='set_prefs',hold_priority=True,response='on')
    to_phase(s,'main1',4)
    source=put(s,'Thick-Skinned Goblin','battlefield') if goblin else None
    permanent=put(s,name,'battlefield')
    return s,source,permanent


def echo(s):
    to_phase(s,'upkeep',7)
    for _ in range(10):
        d=s.state.rules.decision
        if d:
            return d
        act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('Expected echo payment')


def pick(s,option):
    d=s.state.rules.decision
    assert d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[option])


def test_canonical(cards):
    assert coverage.of_card_data(cards.resolve('Thick-Skinned Goblin')).level=='FULL'


@pytest.mark.parametrize('name',['Uktabi Drake','Deepcavern Imp'])
def test_zero_alternative_replaces_mana_and_discard_echo_but_never_discards_hand(cards,name):
    s,_,permanent=setup(cards,name)
    d=echo(s)
    assert d.resume['step']=='echo_alternative76'
    before=list(s.state.zones['p1:hand'])
    pick(s,'zero')
    answer(s)
    assert permanent.zone=='p1:battlefield'
    assert s.state.zones['p1:hand']==before
    roundtrip(s)


def test_original_mana_echo_cost_remains_optional(cards):
    s,_,permanent=setup(cards)
    echo(s)
    pick(s,'original')
    d=s.state.rules.decision
    assert d and d.resume['step']=='pay_or_sacrifice'
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'G':2})
    pick(s,'pay')
    answer(s)
    assert permanent.zone=='p1:battlefield'
    assert sum(s.state.players['p1'].mana.values())==0


def test_original_nonmana_echo_keeps_actual_private_discard(cards):
    s,_,permanent=setup(cards,'Deepcavern Imp')
    put(s,'Lightning Bolt','hand')
    put(s,'Grizzly Bears','hand')
    echo(s)
    pick(s,'original')
    before=len(s.state.zones['p1:hand'])
    pick(s,'pay')
    d=s.state.rules.decision
    assert d and d.kind=='choose_cards'
    paid=d.options[0].id
    pick(s,paid)
    answer(s)
    assert permanent.zone=='p1:battlefield'
    assert s.state.cards[paid].zone=='p1:graveyard'
    assert len(s.state.zones['p1:hand'])==before-1
    assert len([e for e in s.state.rules.events if e.kind=='designation' and e.counter=='echo_paid76' and e.card==permanent.id])==1


@pytest.mark.parametrize('name',['Uktabi Drake','Deepcavern Imp'])
def test_can_decline_zero_and_sacrifice_instead(cards,name):
    s,_,permanent=setup(cards,name)
    echo(s)
    pick(s,'sacrifice')
    answer(s)
    assert permanent.zone=='p1:graveyard'


def test_other_controller_goblin_does_not_change_original_echo(cards):
    s,source,permanent=setup(cards)
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    d=echo(s)
    assert d.resume['step']=='pay_or_sacrifice'
    assert 'zero' not in [o.id for o in d.options]
    pick(s,'sacrifice')
    answer(s)
    assert permanent.zone=='p1:graveyard'


def test_goblin_departure_before_echo_resolution_restores_original_cost(cards):
    s,source,permanent=setup(cards)
    to_phase(s,'upkeep',7)
    assert s.state.zones.get('stack')
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'graveyard','player':'p1'})
    d=echo(s)
    assert d.resume['step']=='pay_or_sacrifice'
    pick(s,'sacrifice')
    answer(s)
    assert permanent.zone=='p1:graveyard'


def test_shah_canonical(cards):
    assert coverage.of_card_data(cards.resolve('Shah of Naar Isle')).level=='FULL'


def draw_question(s):
    for _ in range(12):
        d=s.state.rules.decision
        if d:
            assert d.resume['step']=='echo_draw_count76'
            assert 'Shah of Naar Isle' in d.prompt
            return d
        assert s.state.zones.get('stack')
        act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('Missing echo-paid draw trigger')


@pytest.mark.parametrize('goblin',[False,True])
def test_real_original_and_alternative_echo_payments_trigger_shah_and_native_opponent_draw_choices(cards,goblin):
    s,_,permanent=setup(cards,'Shah of Naar Isle',goblin)
    echo(s)
    before={p:len(s.state.zones.get(f'{p}:hand',[])) for p in ['p2','p3']}
    pick(s,'zero' if goblin else 'pay')
    d=draw_question(s)
    assert d.player=='p2'
    assert [o.id for o in d.options]==['0','1','2','3']
    pick(s,'2')
    d=s.state.rules.decision
    assert d and d.player=='p3'
    assert all(len(s.state.zones.get(f'{p}:hand',[]))==before[p] for p in ['p2','p3'])
    pick(s,'1')
    answer(s)
    assert permanent.zone=='p1:battlefield'
    assert len(s.state.zones['p2:hand'])==before['p2']+2
    assert len(s.state.zones['p3:hand'])==before['p3']+1
    roundtrip(s)


@pytest.mark.parametrize('goblin',[False,True])
def test_unpaid_echo_never_creates_false_echo_paid_draw_trigger(cards,goblin):
    s,_,permanent=setup(cards,'Shah of Naar Isle',goblin)
    echo(s)
    before={p:len(s.state.zones.get(f'{p}:hand',[])) for p in ['p2','p3']}
    pick(s,'sacrifice')
    answer(s)
    assert permanent.zone=='p1:graveyard'
    assert all(len(s.state.zones.get(f'{p}:hand',[]))==before[p] for p in ['p2','p3'])
    assert not s.state.zones.get('stack')


def test_actual_frogify_removes_goblins_echo_alternative(cards):
    s,source,permanent=setup(cards)
    frog=put(s,'Frogify','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'U':1})
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=frog.id,targets=[source.id],sources=[])
    answer(s)
    d=echo(s)
    assert d.resume['step']=='pay_or_sacrifice'
    pick(s,'sacrifice')
    answer(s)
    assert permanent.zone=='p1:graveyard'


def test_actual_goblin_cast_and_protection_activation_remain_native(cards):
    s,source,_=setup(cards)
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'hand','player':'p1'})
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'R':1})
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    answer(s)
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[])
    answer(s)
    bolt=put(s,'Lightning Bolt','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'R':1})
    wait_priority(s,'p2')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=bolt.id,targets=[source.id],sources=[])
    assert s.state.model_dump_json()==before


@pytest.mark.parametrize('stage',['echo','draw'])
def test_true_cold_alternative_and_shah_draw_choices(cards,tmp_path,stage):
    import os
    import subprocess
    import sys
    s,_,permanent=setup(cards,'Shah of Naar Isle')
    echo(s)
    before={p:len(s.state.zones.get(f'{p}:hand',[])) for p in ['p2','p3']}
    if stage=='draw':
        pick(s,'zero')
        draw_question(s)
        pick(s,'2')
        assert s.state.rules.decision.player=='p3'
    saved=tmp_path/'save.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
saved,database,cid,stage,before=sys.argv[1:]
before=json.loads(before)
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p3')
for _ in range(30):
 d=s.state.rules.decision
 if d:
  step=d.resume['step']
  assert step in ['echo_alternative76','echo_draw_count76']
  pick='zero' if step=='echo_alternative76' else '2' if d.player=='p2' else '1'
  act(s,d.player,type='choose',decision_id=d.id,option_ids=[pick])
 elif s.state.zones.get('stack'):
  act(s,s.state.rules.priority,type='pass_priority')
 else: break
assert s.state.cards[cid].zone=='p1:battlefield'
assert len(s.state.zones['p2:hand'])==before['p2']+2
assert len(s.state.zones['p3:hand'])==before['p3']+1
GameState.model_validate_json(s.state.model_dump_json())
'''
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),permanent.id,stage,json.dumps(before)],capture_output=True,text=True,env=os.environ.copy())
    assert run.returncode==0,run.stdout+run.stderr


def test_shah_pending_opponent_concedes_and_remaining_opponent_still_chooses_and_draws(cards):
    s,_,permanent=setup(cards,'Shah of Naar Isle')
    echo(s)
    pick(s,'zero')
    d=draw_question(s)
    assert d.player=='p2'
    before=len(s.state.zones.get('p3:hand',[]))
    act(s,'p2',type='concede')
    d=s.state.rules.decision
    assert d and d.player=='p3' and d.resume['step']=='echo_draw_count76'
    pick(s,'2')
    answer(s)
    assert permanent.zone=='p1:battlefield'
    assert len(s.state.zones.get('p3:hand',[]))==before+2
    roundtrip(s)


def test_shah_native_draw_replacement_acts_after_all_opponent_number_choices(cards):
    s,_,permanent=setup(cards,'Shah of Naar Isle')
    put(s,'Notion Thief','battlefield')
    echo(s)
    before={p:len(s.state.zones.get(f'{p}:hand',[])) for p in ['p1','p2','p3']}
    pick(s,'zero')
    draw_question(s)
    pick(s,'2')
    assert all(len(s.state.zones.get(f'{p}:hand',[]))==before[p] for p in ['p1','p2','p3'])
    pick(s,'1')
    answer(s)
    assert permanent.zone=='p1:battlefield'
    assert len(s.state.zones['p1:hand'])==before['p1']+3
    assert all(len(s.state.zones.get(f'{p}:hand',[]))==before[p] for p in ['p2','p3'])
    roundtrip(s)


@pytest.mark.parametrize('pay',[False,True])
def test_original_echo_controller_can_pay_after_control_change_but_cannot_sacrifice_opponents_shah(cards,pay):
    s,_,permanent=setup(cards,'Shah of Naar Isle')
    to_phase(s,'upkeep',7)
    assert s.state.zones.get('stack')
    act(s,'p1',type='set_controller',card_ids=[permanent.id],player='p2')
    d=echo(s)
    assert d.player=='p1' and d.resume['step']=='pay_or_sacrifice'
    assert 'zero' not in [o.id for o in d.options]
    before={p:len(s.state.zones.get(f'{p}:hand',[])) for p in ['p1','p2','p3']}
    pick(s,'pay' if pay else 'sacrifice')
    if pay:
        d=draw_question(s)
        assert d.player=='p1'
        pick(s,'2')
        d=s.state.rules.decision
        assert d and d.player=='p3'
        pick(s,'1')
        answer(s)
        assert len(s.state.zones['p1:hand'])==before['p1']+2
        assert len(s.state.zones['p2:hand'])==before['p2']
        assert len(s.state.zones['p3:hand'])==before['p3']+1
    else:
        answer(s)
        assert all(len(s.state.zones.get(f'{p}:hand',[]))==before[p] for p in ['p1','p2','p3'])
    assert permanent.zone=='p2:battlefield' and permanent.controller=='p2'
    roundtrip(s)


def test_original_nonmana_echo_can_be_paid_after_permanent_changes_control(cards):
    s,_,permanent=setup(cards,'Deepcavern Imp')
    put(s,'Lightning Bolt','hand')
    put(s,'Grizzly Bears','hand')
    to_phase(s,'upkeep',7)
    act(s,'p1',type='set_controller',card_ids=[permanent.id],player='p2')
    d=echo(s)
    assert d.player=='p1' and d.resume['step']=='pay_or_sacrifice'
    before=len(s.state.zones['p1:hand'])
    pick(s,'pay')
    d=s.state.rules.decision
    assert d and d.player=='p1'
    pick(s,d.options[0].id)
    answer(s)
    assert permanent.controller=='p2' and permanent.zone=='p2:battlefield'
    assert len(s.state.zones['p1:hand'])==before-1
    assert len([e for e in s.state.rules.events if e.counter=='echo_paid76' and e.card==permanent.id])==1
    roundtrip(s)


def test_original_mana_echo_payment_remains_optional_after_original_permanent_leaves(cards):
    s,_,permanent=setup(cards,'Shah of Naar Isle')
    to_phase(s,'upkeep',7)
    act(s,'p1',type='move',card_ids=[permanent.id],to={'zone':'graveyard','player':'p1'})
    d=echo(s)
    assert d.player=='p1' and d.resume['step']=='pay_or_sacrifice'
    assert 'zero' not in [o.id for o in d.options]
    pick(s,'pay')
    answer(s)
    assert permanent.zone=='p1:graveyard'
    assert len([e for e in s.state.rules.events if e.counter=='echo_paid76' and e.card==permanent.id])==1
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_true_cold_original_echo_payer_and_new_shah_trigger_controller_after_control_change(cards,tmp_path):
    import os
    import subprocess
    import sys
    s,_,permanent=setup(cards,'Shah of Naar Isle')
    to_phase(s,'upkeep',7)
    act(s,'p1',type='set_controller',card_ids=[permanent.id],player='p2')
    d=echo(s)
    assert d.player=='p1' and d.resume['step']=='pay_or_sacrifice'
    before={p:len(s.state.zones.get(f'{p}:hand',[])) for p in ['p1','p2','p3']}
    saved=tmp_path/'controlled.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
saved,database,cid,before=sys.argv[1:]
before=json.loads(before)
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p3')
d=s.state.rules.decision
assert d and d.player=='p1' and d.resume['step']=='pay_or_sacrifice'
assert 'zero' not in [o.id for o in d.options]
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
for _ in range(30):
 d=s.state.rules.decision
 if d:
  assert d.resume['step']=='echo_draw_count76'
  assert d.player in ['p1','p3']
  act(s,d.player,type='choose',decision_id=d.id,option_ids=['2' if d.player=='p1' else '1'])
 elif s.state.zones.get('stack'):
  act(s,s.state.rules.priority,type='pass_priority')
 else: break
assert s.state.cards[cid].controller=='p2'
assert s.state.cards[cid].zone=='p2:battlefield'
assert len(s.state.zones['p1:hand'])==before['p1']+2
assert len(s.state.zones['p2:hand'])==before['p2']
assert len(s.state.zones['p3:hand'])==before['p3']+1
GameState.model_validate_json(s.state.model_dump_json())
'''
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),permanent.id,json.dumps(before)],capture_output=True,text=True,env=os.environ.copy())
    assert run.returncode==0,run.stdout+run.stderr
