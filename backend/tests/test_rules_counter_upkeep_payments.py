"""Canonical counter-upkeep costs use real native payments, never aggregated choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Primordial Ooze','Rogue Skycaptain','Phantasmal Sphere','Cyclone','Delaying Shield']
EXTRA=['Grizzly Bears','Solemnity','Doubling Season','Forest','Shock','Vilis, Broker of Blood','Sol Ring']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/counter_upkeep_payments_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='cup',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=[*NAMES,*EXTRA]
    return table(cards,ns,ns,ns)


def counters(s,c,n,kind):
    act(s,'p1',type='set_counter',card_id=c.id,kind=kind,value=n)


def upkeep(s):
    to_phase(s,'upkeep',turn=4)


def choose(s,value,finish=True):
    d=s.state.rules.decision
    assert d and value in {x.id for x in d.options}, (d.prompt if d else None,value)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    if finish:
        settle(s)


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('pay',[True,False])
def test_ooze_actual_counter_total_cost_pay_or_decline_damage_and_tap(cards,pay):
    s=game(cards)
    c=put(s,'Primordial Ooze','battlefield')
    counters(s,c,2,'+1/+1')
    upkeep(s)
    act(s,'p1',type='add_mana',mana={'C':3})
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['cost']=='{3}'
    roundtrip(s)
    choose(s,'pay' if pay else 'decline')
    assert s.state.cards[c.id].counters['+1/+1']==3
    assert s.state.cards[c.id].tapped is (not pay)
    assert s.state.players['p1'].life==(40 if pay else 37)
    assert mana_pool(s)==({} if pay else {'C':3})
    roundtrip(s)


@pytest.mark.parametrize('pay',[True,False])
def test_ooze_zero_counter_payment_is_real_optional_choice(cards,pay):
    s=game(cards)
    c=put(s,'Primordial Ooze','battlefield')
    put(s,'Solemnity','battlefield')
    upkeep(s)
    settle(s)
    assert s.state.rules.decision.resume['cost']=='{0}'
    choose(s,'pay' if pay else 'decline')
    assert s.state.players['p1'].life==40
    assert s.state.cards[c.id].tapped is (not pay)
    roundtrip(s)


def test_ooze_counter_replacement_sizes_full_cost(cards):
    s=game(cards)
    c=put(s,'Primordial Ooze','battlefield')
    counters(s,c,2,'+1/+1')
    put(s,'Doubling Season','battlefield')
    upkeep(s)
    act(s,'p1',type='add_mana',mana={'C':4})
    settle(s)
    assert s.state.rules.decision.resume['cost']=='{4}'
    choose(s,'pay')
    assert s.state.cards[c.id].counters['+1/+1']==4
    roundtrip(s)


def test_ooze_departed_source_uses_exact_lki_quantity_without_tapping_new_object(cards):
    s=game(cards)
    c=put(s,'Primordial Ooze','battlefield')
    counters(s,c,3,'+1/+1')
    upkeep(s)
    put(s,'Primordial Ooze','graveyard')
    put(s,'Primordial Ooze','battlefield')
    settle(s)
    assert s.state.players['p1'].life==37
    assert not s.state.cards[c.id].tapped and not s.state.cards[c.id].counters
    roundtrip(s)


@pytest.mark.parametrize('pay',[True,False])
def test_rogue_pay_wages_or_remove_all_and_choose_actual_opponent(cards,pay):
    s=game(cards)
    c=put(s,'Rogue Skycaptain','battlefield')
    counters(s,c,2,'wage')
    upkeep(s)
    act(s,'p1',type='add_mana',mana={'C':6})
    settle(s)
    assert s.state.rules.decision.resume['cost']=='{6}'
    choose(s,'pay' if pay else 'decline')
    if not pay:
        choose(s,'p3')
    assert s.state.cards[c.id].controller==('p1' if pay else 'p3')
    assert s.state.cards[c.id].counters.get('wage',0)==(3 if pay else 0)
    roundtrip(s)


@pytest.mark.parametrize('pay',[True,False])
def test_sphere_full_scaled_payment_or_sacrifice_and_real_lki_token(cards,pay):
    s=game(cards)
    c=put(s,'Phantasmal Sphere','battlefield')
    counters(s,c,2,'+1/+1')
    upkeep(s)
    act(s,'p1',type='add_mana',mana={'C':3})
    settle(s)
    choose(s,'pay' if pay else 'decline')
    if pay:
        assert s.state.cards[c.id].zone=='p1:battlefield'
    else:
        d=s.state.rules.decision
        assert d and 'p2' in {o.id for o in d.options}
        choose(s,'p2')
        tokens=[x for x in s.state.cards.values() if x.is_token and x.zone=='p2:battlefield']
        assert len(tokens)==1
        from app.rules.plan import Plan
        assert Plan(s.state,'p1',s.cards,None).ch(tokens[0]).pt==(3,3)
    roundtrip(s)


@pytest.mark.parametrize('pay',[True,False])
def test_cyclone_each_green_required_and_damage_only_when_paid(cards,pay):
    s=game(cards)
    c=put(s,'Cyclone','battlefield')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    counters(s,c,1,'wind')
    upkeep(s)
    act(s,'p1',type='add_mana',mana={'G':2})
    settle(s)
    assert s.state.rules.decision.resume['cost']=='{G}{G}'
    choose(s,'pay' if pay else 'decline')
    assert s.state.cards[c.id].zone==('p1:battlefield' if pay else 'p1:graveyard')
    assert s.state.cards[bear.id].zone==('p2:graveyard' if pay else 'p2:battlefield')
    assert all(p.life==(38 if pay else 40) for p in s.state.players.values())
    roundtrip(s)


def test_cyclone_generic_mana_does_not_pay_green_scaled_cost(cards):
    s=game(cards)
    c=put(s,'Cyclone','battlefield')
    upkeep(s)
    act(s,'p1',type='add_mana',mana={'C':20})
    settle(s)
    assert not s.state.rules.decision and s.state.cards[c.id].zone=='p1:graveyard'
    assert all(p.life==40 for p in s.state.players.values())
    roundtrip(s)


def test_delaying_real_damage_replacement_then_independent_payments(cards):
    s=game(cards)
    c=put(s,'Delaying Shield','battlefield')
    shock=put(s,'Shock','hand','p2')
    from tests.test_rules_remaining_talents import pay
    pay(s,'p2','Shock')
    # Use p2's actual priority for the instant.
    act(s,'p1',type='pass_priority')
    act(s,'p2',type='cast_spell',card_id=shock.id,targets=['p1'],sources=[])
    settle(s)
    assert s.state.players['p1'].life==40 and s.state.cards[c.id].counters['delay']==2
    upkeep(s)
    act(s,'p1',type='add_mana',mana={'C':1,'W':1})
    settle(s)
    assert not s.state.cards[c.id].counters
    choose(s,'pay')
    # Cannot pay the second full cost, so native optional payment declines it.
    assert not s.state.rules.decision and s.state.players['p1'].life==39
    roundtrip(s)


@pytest.mark.parametrize('n',[0,43,1005])
def test_delaying_unpayable_iterations_are_individual_losses_without_expansion(cards,n):
    s=game(cards)
    c=put(s,'Delaying Shield','battlefield')
    counters(s,c,n,'delay')
    act(s,'p1',type='set_life',player='p1',value=2000)
    upkeep(s)
    settle(s)
    checkpoints=0
    while s.state.rules.decision:
        assert s.state.rules.decision.resume['step']=='counter_upkeep_continue'
        assert len(s.state.rules.decision.resume['ctx']['effects'])==4
        choose(s,'continue')
        checkpoints+=1
    assert bool(checkpoints)==(n==1005)
    assert s.state.players['p1'].life==2000-n
    assert not s.state.cards[c.id].counters
    losses=[e for e in s.state.rules.events if e.kind=='life_lost' and e.player=='p1']
    assert all(e.amount==1 for e in losses)
    roundtrip(s)


def test_delaying_separate_partial_choices_resume_in_fresh_process(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    c=put(s,'Delaying Shield','battlefield')
    counters(s,c,3,'delay')
    upkeep(s)
    act(s,'p1',type='add_mana',mana={'C':3,'W':3})
    settle(s)
    choose(s,'decline')
    assert s.state.players['p1'].life==39
    d=s.state.rules.decision
    assert d and len(d.resume['ctx']['effects'])==4
    saved=tmp_path/'upkeep.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import mana_pool
save,db=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
for answer in ['pay','decline']:
 d=s.state.rules.decision
 assert d and len(d.resume['ctx']['effects'])==4
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[answer]})
assert s.state.rules.decision is None
assert s.state.players['p1'].life==38
assert mana_pool(s)=={'C':2,'W':2}
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path)],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_cyclone_scaled_payment_allows_real_manual_mana_window(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s=game(cards)
    c=put(s,'Cyclone','battlefield')
    forest=put(s,'Forest','battlefield')
    act(s,'p1',type='set_prefs',payment='self')
    upkeep(s)
    settle(s)
    original=s.state.rules.decision
    assert original and original.resume['cost']=='{G}'
    act(s,'p1',type='activate_ability',card_id=forest.id,ability=ability_index(s,forest,'Add'),sources=[])
    assert s.state.rules.decision and s.state.rules.decision.id==original.id
    choose(s,'pay')
    assert s.state.cards[c.id].zone=='p1:battlefield'
    assert all(p.life==39 for p in s.state.players.values())
    assert not mana_pool(s)
    roundtrip(s)


def test_delaying_each_unpaid_counter_emits_real_separate_vilis_trigger(cards):
    s=game(cards)
    c=put(s,'Delaying Shield','battlefield')
    put(s,'Vilis, Broker of Blood','battlefield')
    counters(s,c,3,'delay')
    upkeep(s)
    # Resolving the upkeep makes three distinct loss events and three abilities;
    # none is allowed to draw until the original upkeep ability has finished.
    for _ in range(12):
        if len(s.state.zones['stack'])==3:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert len(s.state.zones['stack'])==3
    assert s.state.players['p1'].life==37
    before=len(s.state.zones['p1:hand'])
    settle(s)
    assert len(s.state.zones['p1:hand'])==before+3
    roundtrip(s)


def test_large_mandatory_checkpoint_cold_load_preserves_exact_remaining_count(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    c=put(s,'Delaying Shield','battlefield')
    counters(s,c,1005,'delay')
    act(s,'p1',type='set_life',player='p1',value=2000)
    upkeep(s)
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='counter_upkeep_continue'
    assert 0<d.resume['ctx']['effects'][3]['n']<1005
    saved=tmp_path/'large-upkeep.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
for _ in range(20):
 d=s.state.rules.decision
 if d is None:break
 assert d.resume['step']=='counter_upkeep_continue'
 assert len(d.resume['ctx']['effects'])==4
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['continue']})
assert s.state.rules.decision is None and not s.state.zones['stack']
assert s.state.players['p1'].life==995
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path)],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_delaying_departed_source_removes_nothing_from_new_incarnation(cards):
    s=game(cards)
    c=put(s,'Delaying Shield','battlefield')
    counters(s,c,3,'delay')
    upkeep(s)
    put(s,'Delaying Shield','exile')
    put(s,'Delaying Shield','battlefield')
    counters(s,c,7,'delay')
    settle(s)
    assert s.state.players['p1'].life==40
    assert s.state.cards[c.id].counters['delay']==7
    roundtrip(s)


def test_ooze_large_computed_payment_is_not_a_player_x_input_limit(cards):
    s=game(cards)
    c=put(s,'Primordial Ooze','battlefield')
    counters(s,c,1005,'+1/+1')
    upkeep(s)
    for _ in range(10):
        act(s,'p1',type='add_mana',mana={'C':100})
    act(s,'p1',type='add_mana',mana={'C':6})
    settle(s)
    assert s.state.rules.decision.resume['cost']=='{1006}'
    choose(s,'pay')
    assert not mana_pool(s) and s.state.players['p1'].life==40
    roundtrip(s)


def test_large_payment_splits_plain_spending_but_taps_actual_source_once(cards):
    s=game(cards)
    c=put(s,'Primordial Ooze','battlefield')
    ring=put(s,'Sol Ring','battlefield')
    counters(s,c,1005,'+1/+1')
    upkeep(s)
    for _ in range(10):
        act(s,'p1',type='add_mana',mana={'C':100})
    act(s,'p1',type='add_mana',mana={'C':4})
    settle(s)
    choose(s,'pay')
    assert s.state.cards[ring.id].tapped
    assert not mana_pool(s) and s.state.players['p1'].life==40
    tapped=[e for e in s.state.rules.events if e.kind=='tapped' and e.card==ring.id]
    assert len(tapped)==1
    roundtrip(s)
