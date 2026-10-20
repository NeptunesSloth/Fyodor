"""Existing admitted Goblin Festival: frozen damage controller survives later control instruction."""
import pytest

from app.rules import coverage
from tests.combat_scope43_kit import cards as cards
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import attack
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import build, pick, put, roundtrip, settle
from tests.test_rules_life_total_damage43 import game
from tests.test_rules_wave7r_promotions import flips
from tests.test_rules_wave30m_durations import to_phase


def test_actual_festival_history_retains_damage_time_controller(cards,monkeypatch):
    flips(monkeypatch,False)
    s=build(cards,['Goblin Festival'])
    obj=put(s,'Goblin Festival','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='activate_ability',card_id=obj.id,ability=0,targets=['p2'])
    settle(s)
    if s.state.rules.decision:
        pick(s,['p2'])
        settle(s)
    assert s.state.cards[obj.id].controller=='p2'
    facts=[f for f in s.state.rules.turn_log.facts if f.kind=='damage']
    assert len(facts)==1 and facts[0].source_controller=='p1'
    roundtrip(s)


def quarantined(s, obj, controller='p1', ident='legacy-watch'):
    from app.game.rules_state import DelayedTrigger
    from app.rules.plan import Plan

    watch = DelayedTrigger(id=ident, controller=controller, source_card=obj.id,
        source_object=Plan(s.state,controller,s.cards,None).oid(obj),name='Legacy original condition',
        when={'kind':'watch','cond':{'event':'deal_combat_damage_player','subject':'self'},
              'manual_combat_scope':True,'manual_combat_notice':True,'since':0},
        effects=[{'do':'draw','who':'you','n':1}],turn=s.state.turn.number,until_turn=s.state.turn.number)
    s.state.rules.delayed.append(watch)
    return watch


def test_quarantined_watch_notifies_at_native_safe_boundary_and_restores_priority(cards):
    s=build(cards,['Goblin Festival'])
    obj=put(s,'Goblin Festival','battlefield')
    watch=quarantined(s,obj)
    s.state.rules.priority='p2'
    before=len(s.state.zones['p1:hand'])
    act(s,'p2',type='pass_priority')
    watch=s.state.rules.delayed[0]
    d=s.state.rules.decision
    assert d is not None and d.kind=='manual_resolution' and d.player=='p1'
    assert d.resume=={'step':'combat_scope_legacy_done','priority':'p1'}
    assert watch.once and not watch.when['manual_combat_notice']
    assert not s.state.rules.pending_triggers and not s.state.zones.get('stack')
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['done'])
    assert s.state.rules.decision is None and s.state.rules.priority=='p1'
    assert len(s.state.zones['p1:hand'])==before and watch in s.state.rules.delayed
    roundtrip(s)




@pytest.mark.parametrize('paused',[False,True])
def test_saved_quarantined_watch_notice_native_registry_true_cold(cards,tmp_path,paused):
    import subprocess
    import sys

    s=build(cards,['Goblin Festival'])
    obj=put(s,'Goblin Festival','battlefield')
    quarantined(s,obj)
    s.state.rules.priority='p2'
    if paused:
        act(s,'p2',type='pass_priority')
        assert s.state.rules.decision.kind=='manual_resolution'
    saved=tmp_path/'quarantined.json'
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
before=len(s.state.zones['p1:hand'])
turn=s.state.turn.number
if s.state.rules.decision is None:
 s.perform('p2',{'type':'pass_priority'})
d=s.state.rules.decision
assert d is not None and d.kind=='manual_resolution' and d.player=='p1'
assert d.resume=={'step':'combat_scope_legacy_done','priority':'p1'}
assert not s.state.rules.pending_triggers and not s.state.zones.get('stack')
assert not s.state.rules.delayed[0].when['manual_combat_notice']
s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['done']})
assert s.state.rules.decision is None and s.state.rules.priority=='p1'
assert len(s.state.zones['p1:hand'])==before
assert s.state.rules.delayed[0].once and s.state.rules.delayed[0].when['manual_combat_scope']
roundtrip(s)
to_phase(s,'main1',turn=turn+1)
assert not s.state.rules.delayed
roundtrip(s)
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',worker,str(saved),str(cards.db_path)],
                          capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


def test_manual_notices_preserve_other_controllers_pending_notification(cards):
    s=build(cards,['Goblin Festival'])
    obj=put(s,'Goblin Festival','battlefield')
    quarantined(s,obj,controller='p2',ident='second')
    quarantined(s,obj,controller='p1',ident='first')
    s.state.rules.priority='p2'
    before={p:len(s.state.zones.get(p+':hand',[])) for p in ('p1','p2')}
    act(s,'p2',type='pass_priority')
    first=s.state.rules.decision
    assert first is not None and first.player=='p1'
    watches={w.controller:w for w in s.state.rules.delayed}
    assert not watches['p1'].when['manual_combat_notice'] and watches['p2'].when['manual_combat_notice']
    act(s,'p1',type='choose',decision_id=first.id,option_ids=['done'])
    second=s.state.rules.decision
    assert second is not None and second.player=='p2' and second.resume['priority']=='p1'
    act(s,'p2',type='choose',decision_id=second.id,option_ids=['done'])
    assert s.state.rules.decision is None and s.state.rules.priority=='p1'
    assert {p:len(s.state.zones.get(p+':hand',[])) for p in ('p1','p2')}==before
    assert all(w.once and not w.when['manual_combat_notice'] for w in s.state.rules.delayed)
    roundtrip(s)




def test_native_scroll_thief_redirected_own_player_damage_still_draws(cards):
    assert coverage.of_card_data(cards.resolve('Scroll Thief')).level == 'FULL'
    s = game(cards)
    thief = put(s, 'Scroll Thief', 'battlefield')
    start(s)
    cast(s, "Captain's Maneuver", ['p2', 'p1'], x_value=1, target_counts=[1, 1])
    before = len(s.state.zones['p1:hand'])
    attack(s, [thief])
    to_phase(s, 'combat_damage')
    settle(s)
    assert s.state.players['p1'].life == 39 and s.state.players['p2'].life == 40
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)


def test_native_opponent_is_relative_to_aura_controller_not_creature_controller(cards):
    assert coverage.of_card_data(cards.resolve("Sleeper's Robe")).level == 'FULL'
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, "Sleeper's Robe", [bear.id])
    start(s, turn=5)
    before = len(s.state.zones['p1:hand'])
    attack(s, [bear], pid='p2', target='p1', turn=5)
    to_phase(s, 'combat_damage')
    assert s.state.players['p1'].life == 38
    assert not [entry for entry in s.state.rules.stack.values() if entry.event]
    settle(s)
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


def scope_scene(cards):
    from tests.test_rules_shared_damage_choices import table
    names=['Coastal Piracy',"Sleeper's Robe",'Grizzly Bears',"Captain's Maneuver",'Lightning Bolt','Holy Day']
    s=table(cards,names,names,names)
    for player in ('p1','p2','p3'):
        act(s,player,type='set_prefs',auto_resolve_own_triggers='off',hold_priority=True)
    return s


def test_actual_coastal_piracy_does_not_draw_for_redirected_own_player_combat(cards):
    s=scope_scene(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Coastal Piracy')
    start(s)
    cast(s,"Captain's Maneuver",['p2','p1'],x_value=2,target_counts=[1,1])
    before=len(s.state.zones['p1:hand'])
    attack(s,[bear])
    to_phase(s,'combat_damage')
    settle(s)
    assert s.state.players['p1'].life==38 and s.state.players['p2'].life==40
    assert len(s.state.zones['p1:hand'])==before and s.state.rules.decision is None
    assert not [entry for entry in s.state.rules.stack.values() if entry.event]
    roundtrip(s)


def test_actual_foreign_creature_hitting_another_opponent_draws_for_aura_controller(cards):
    from tests.test_rules_designations import resolve
    s=scope_scene(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,"Sleeper's Robe",[bear.id])
    start(s,turn=5)
    before={p:len(s.state.zones[p+':hand']) for p in ('p1','p2','p3')}
    attack(s,[bear],pid='p2',target='p3',turn=5)
    to_phase(s,'combat_damage')
    settle(s)
    if s.state.rules.decision is not None:
        resolve(s,'yes')
    assert s.state.players['p3'].life==38
    assert len(s.state.zones['p1:hand'])==before['p1']+1
    assert all(len(s.state.zones[p+':hand'])==before[p] for p in ('p2','p3'))
    roundtrip(s)


def test_actual_spiritualize_draws_and_merges_split_source_damage_into_one_life_trigger(cards):
    s=build(cards,['Hill Giant','Spiritualize',"Captain's Maneuver"])
    giant=put(s,'Hill Giant','battlefield')
    start(s,turn=3)
    act(s,'p1',type='set_prefs',auto_resolve_own_triggers='off',hold_priority=True)
    spell=put(s,'Spiritualize','hand')
    assert coverage.of_card_data(cards.resolve('Spiritualize')).level=='FULL'
    before=len(s.state.zones['p1:hand'])
    cast(s,'Spiritualize',[giant.id])
    assert s.state.cards[spell.id].zone=='p1:graveyard' and len(s.state.zones['p1:hand'])==before
    cast(s,"Captain's Maneuver",['p2','p1'],x_value=1,target_counts=[1,1])
    attack(s,[giant],turn=3)
    to_phase(s,'combat_damage')
    triggers=[entry for entry in s.state.rules.stack.values() if entry.event and entry.event.kind=='deal_damage']
    assert len(triggers)==1 and triggers[0].event.amount==3 and triggers[0].event.count==2
    assert s.state.players['p1'].life==39 and s.state.players['p2'].life==38
    settle(s)
    assert s.state.players['p1'].life==42 and s.state.players['p2'].life==38
    roundtrip(s)
