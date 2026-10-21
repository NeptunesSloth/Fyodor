"""Historical combat trigger qualification and legacy uncertainty."""
from types import SimpleNamespace

import pytest

from app.game.rules_state import TurnFact, TurnLog
from app.rules.combat_player_scope43 import first_result as first
from tests.combat_scope43_kit import cards as cards


def plan(facts):
    return SimpleNamespace(state=SimpleNamespace(turn=SimpleNamespace(number=3)),
        rules=SimpleNamespace(turn_log=TurnLog(turn=3, facts=facts), events=[], trigger_batch=2))


def damage(player, controller, *, oid='object:1', batch=1, combat=True):
    return TurnFact(kind='damage', object_id=oid, player=player, source_controller=controller,
                    batch=batch, amount=2, combat=combat)


@pytest.mark.parametrize('recipient,historical,expected', [
    ('p2', 'p1', False),  # Previously an opponent; stealing the source cannot reset first.
    ('p1', 'p1', True),   # Previously itself; stealing cannot turn this into an old opponent hit.
    ('p1', 'p2', False),
    ('p2', 'p2', True),
])
def test_self_uses_native_historical_controller_instead_of_current_controller(recipient, historical, expected):
    assert first(plan([damage(recipient,historical)]),
                 {'subject':'self','combat_recipient':'opponent'}, {'batch':2,'oid':'object:1'}) is expected


def test_all_player_scope_counts_previous_self_damage_without_controller_knowledge():
    assert first(plan([damage('p1',None)]), {'subject':'self','combat_recipient':'player'},
                 {'batch':2,'oid':'object:1'}) is False


def test_legacy_unknown_is_explicit_and_definite_prior_hit_still_wins():
    cond, info = {'subject':'self','combat_recipient':'opponent'}, {'batch':3,'oid':'object:1'}
    assert first(plan([damage('p1',None)]),cond,info) is None
    assert first(plan([damage('p1',None),damage('p2','p1',batch=2)]),cond,info) is False


def test_delayed_watch_uses_its_fixed_controller_even_after_physical_source_changes():
    assert first(plan([damage('p2','p2')]), {'subject':'self','combat_recipient':'opponent'},
                 {'batch':2,'oid':'object:1'}, fixed_controller='p1') is False


def test_other_incarnations_noncombat_and_same_batch_do_not_count():
    facts=[damage('p2','p1',oid='object:old'),damage('p2','p1',combat=False),damage('p2','p1',batch=2)]
    assert first(plan(facts), {'subject':'self','combat_recipient':'opponent'},
                 {'batch':2,'oid':'object:1'}) is True




def test_collection_quarantines_unknown_history_and_retains_both_controllers_notices(cards):
    from app.rules import triggers
    from app.rules.plan import Plan
    from tests.test_rules_designations import build, put

    s=build(cards,['Goblin Festival'])
    original=put(s,'Goblin Festival','battlefield')
    p=Plan(s.state,'p1',cards,None)
    source=p.state.cards[original.id]
    oid=p.oid(source)
    p.rules.turn_log=TurnLog(turn=p.state.turn.number,facts=[damage('p2',None,oid=oid)])
    condition={'event':'deal_combat_damage_player','subject':'self','combat_recipient':'opponent','first_each_turn':True}
    def collect(recipient,batch):
        source=p.state.cards[original.id]
        ch=p.ch(source)
        fact=('deal_combat_damage_player',source,ch,source.controller,
              {'oid':oid,'batch':batch,'recipient':recipient,'amount':2,'combat':True})
        triggers._fire_generic(p,[fact],batch,{},watchers=[((source,ch,0,{'cond':condition}),-1,-1)])
    collect('p2',2)
    assert not p.rules.pending_triggers and not p.rules.once_per_turn
    assert len(p.rules.combat_history_notices)==1
    p.do({'type':'set_controller','card_ids':[source.id],'player':'p2'})
    collect('p1',3)
    notices=p.rules.combat_history_notices
    assert [n.controller for n in notices]==['p1','p2']
    assert all(n.source_object==oid and n.ability==0 and not n.notified for n in notices)
    assert not p.rules.pending_triggers and not p.rules.once_per_turn
    # A native departure and return gives an independent OID, never this quarantine.
    p.do({'type':'move','card_ids':[source.id],'to':{'zone':'graveyard','player':'p1'}})
    p.do({'type':'move','card_ids':[source.id],'to':{'zone':'battlefield','player':'p1'}})
    from app.rules import combat_player_scope43 as helper
    fresh=p.state.cards[source.id]
    assert p.oid(fresh)!=oid
    info={'oid':p.oid(fresh),'batch':4,'recipient':'p2','amount':2,'combat':True}
    assert helper.printed_verdict(p,condition,fresh,('deal_combat_damage_player',fresh,p.ch(fresh),'p1',info),
                                  source_oid=p.oid(fresh),index=0,name='new object')
    assert len(p.rules.combat_history_notices)==2
    p.state.turn.number+=1
    assert not helper.ask_pending(p) and not p.rules.combat_history_notices


@pytest.mark.parametrize('paused',[False,True])
def test_printed_history_notices_survive_control_change_and_true_cold(cards,tmp_path,paused):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.rules import triggers
    from app.rules.plan import Plan
    from tests.game_helpers import act
    from tests.test_rules_designations import build, put

    s=build(cards,['Goblin Festival'])
    obj=put(s,'Goblin Festival','battlefield')
    p=Plan(s.state,'p1',cards,None)
    oid=p.oid(p.state.cards[obj.id])
    p.rules.turn_log=TurnLog(turn=p.state.turn.number,facts=[damage('p2',None,oid=oid)])
    cond={'event':'deal_combat_damage_player','subject':'self','combat_recipient':'opponent','first_each_turn':True}
    for controller,recipient,batch in [('p1','p2',2),('p2','p1',3)]:
        if controller=='p2':
            p.do({'type':'set_controller','card_ids':[obj.id],'player':'p2'})
        source=p.state.cards[obj.id]
        ch=p.ch(source)
        fact=('deal_combat_damage_player',source,ch,controller,
              {'oid':oid,'batch':batch,'recipient':recipient,'amount':2,'combat':True})
        triggers._fire_generic(p,[fact],batch,{},watchers=[((source,ch,0,{'cond':cond}),-1,-1)])
    p.rules.priority='p2'
    s=GameSession(p.state,cards=cards)
    if paused:
        act(s,'p2',type='pass_priority')
        assert s.state.rules.decision.player=='p1'
    saved=tmp_path/'printed-notices.json'
    saved.write_text(s.state.model_dump_json())
    worker=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import roundtrip
from tests.test_rules_wave30m_durations import to_phase
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert [n.controller for n in s.state.rules.combat_history_notices]==['p1','p2']
assert s.state.cards[sys.argv[3]].controller=='p2'
turn=s.state.turn.number
before={p:len(s.state.zones.get(p+':hand',[])) for p in ('p1','p2')}
if s.state.rules.decision is None:
 s.perform('p2',{'type':'pass_priority'})
for owner in ('p1','p2'):
 d=s.state.rules.decision
 assert d is not None and d.player==owner and d.kind=='manual_resolution'
 assert d.resume['priority']=='p1'
 s.perform(owner,{'type':'choose','decision_id':d.id,'option_ids':['done']})
assert s.state.rules.decision is None and s.state.rules.priority=='p1'
assert all(n.notified for n in s.state.rules.combat_history_notices)
assert not s.state.rules.pending_triggers and not s.state.zones.get('stack')
assert {p:len(s.state.zones.get(p+':hand',[])) for p in ('p1','p2')}==before
roundtrip(s)
to_phase(s,'main1',turn=turn+1)
assert not s.state.rules.combat_history_notices
roundtrip(s);repo.close()
'''
    result=subprocess.run([sys.executable,'-c',worker,str(saved),str(cards.db_path),obj.id],
                          capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
