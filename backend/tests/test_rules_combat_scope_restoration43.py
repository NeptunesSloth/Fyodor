"""Native exact parser compatibility against saved watch/LKI models."""
import pytest

from app.game.rules_state import DelayedTrigger
from app.rules import combat_player_scope43 as helper
from app.rules import events
from app.rules.plan import Plan
from tests.combat_scope43_kit import cards as cards
from tests.test_rules_declaration_requirements33 import cast
from tests.test_rules_designations import build, put, settle


def game(cards):
    return build(cards,['Hill Giant',"Fire Giant's Fury"])


@pytest.mark.parametrize('scope,phrase',[('player','a player'),('opponent','an opponent')])
def test_authoritative_original_when_text_restores_exact_scope(cards,scope,phrase):
    s=game(cards)
    obj=put(s,'Hill Giant','battlefield')
    p=Plan(s.state,'p1',cards,None)
    text=f'~ deals combat damage to {phrase}'
    cond=events.parse_condition(text)
    cond.pop('combat_recipient')
    watch=DelayedTrigger(id='legacy',controller='p1',source_card=obj.id,source_object=p.oid(obj),
                         when={'kind':'watch','text':text,'cond':cond})
    assert helper.restore(p,watch)['combat_recipient']==scope


def test_original_spell_stack_lki_recovers_scope_after_physical_card_moved(cards):
    s=game(cards)
    giant=put(s,'Hill Giant','battlefield')
    cast(s,"Fire Giant's Fury",[giant.id])
    settle(s)
    assert len(s.state.rules.delayed)==1
    watch=s.state.rules.delayed[0]
    watch.when.pop('text',None)
    watch.when['cond'].pop('combat_recipient')
    assert s.state.rules.lki[watch.source_object].zone=='stack'
    p=Plan(s.state,'p1',cards,None)
    restored=helper.restore(p,p.rules.delayed[0])
    assert restored['combat_recipient']=='player'
    # Without the exact old spell snapshot, even the matching physical spell is not evidence.
    watch=p.rules.delayed[0]
    watch.when['cond'].pop('combat_recipient')
    p.rules.lki.pop(watch.source_object)
    assert 'combat_recipient' not in helper.restore(p,watch)


def test_text_with_different_subject_is_not_authoritative_for_saved_condition(cards):
    s=game(cards)
    obj=put(s,'Hill Giant','battlefield')
    p=Plan(s.state,'p1',cards,None)
    watch=DelayedTrigger(id='legacy',controller='p1',source_card=obj.id,source_object=p.oid(obj),
       when={'kind':'watch','text':'a creature you control deals combat damage to a player',
             'cond':{'event':'deal_combat_damage_player','subject':'self'}})
    assert 'combat_recipient' not in helper.restore(p,watch)


@pytest.mark.parametrize('recipient,manual',[('p1',True),('p2',False)])
def test_unknown_watch_scope_uses_native_predicates_without_consuming_ambiguous_once(cards,recipient,manual):
    from app.rules import watches
    s=game(cards)
    obj=put(s,'Hill Giant','battlefield')
    p=Plan(s.state,'p1',cards,None)
    oid=p.oid(p.state.cards[obj.id])
    watch=DelayedTrigger(id='legacy',controller='p1',source_card=obj.id,source_object=oid,name='old watch',once=True,
        until_turn=p.state.turn.number,when={'kind':'watch','cond':{'event':'deal_combat_damage_player','subject':'self'},'since':0},
        effects=[{'do':'draw','who':'you','n':1}])
    p.rules.delayed.append(watch)
    source=p.state.cards[obj.id]
    fact=('deal_combat_damage_player',source,p.ch(source),'p1',
          {'oid':oid,'recipient':recipient,'amount':2,'combat':True,'batch':2})
    watches.on_facts(p,[fact],2,{})
    if manual:
        assert watch.when['manual_combat_scope'] and watch.when['manual_combat_notice']
        assert watch in p.rules.delayed and watch.once and not p.rules.pending_triggers
        watches.on_facts(p,[fact],3,{})
        assert not p.rules.pending_triggers and len(p.rules.delayed)==1
    else:
        assert watch not in p.rules.delayed and len(p.rules.pending_triggers)==1
        assert not watch.when.get('manual_combat_scope')


def test_delayed_first_qualification_uses_fixed_creating_controller_not_physical_source(cards):
    from app.game.rules_state import TurnFact, TurnLog
    from app.rules import watches
    s=game(cards)
    obj=put(s,'Hill Giant','battlefield')
    p=Plan(s.state,'p1',cards,None)
    source=p.state.cards[obj.id]
    oid=p.oid(source)
    p.do({'type':'set_controller','card_ids':[source.id],'player':'p2'})
    source=p.state.cards[obj.id]
    # This old hit was to the fixed watch controller itself, so it was not an opponent hit.
    p.rules.turn_log=TurnLog(turn=p.state.turn.number,facts=[TurnFact(kind='damage',player='p1',source_controller='p2',
                            amount=2,combat=True,object_id=oid,batch=1)])
    watch=DelayedTrigger(id='fixed',controller='p1',source_card=source.id,source_object=oid,once=True,
       when={'kind':'watch','cond':{'event':'deal_combat_damage_player','subject':'self',
                                  'combat_recipient':'opponent','first_each_turn':True},'since':0},
       effects=[{'do':'draw','who':'you','n':1}])
    p.rules.delayed.append(watch)
    fact=('deal_combat_damage_player',source,p.ch(source),'p2',
          {'oid':oid,'recipient':'p2','amount':2,'combat':True,'batch':2})
    watches.on_facts(p,[fact],2,{})
    assert len(p.rules.pending_triggers)==1 and watch not in p.rules.delayed


@pytest.mark.parametrize('receipt',['original_text','original_stack_lki'])
def test_saved_actual_fury_restores_player_scope_and_counts_redirected_own_damage_true_cold(cards,tmp_path,receipt):
    import subprocess
    import sys

    from tests.test_rules_declaration_requirements33 import start

    s=build(cards,['Hill Giant',"Fire Giant's Fury","Captain's Maneuver"])
    giant=put(s,'Hill Giant','battlefield')
    start(s,turn=3)
    cast(s,"Fire Giant's Fury",[giant.id])
    cast(s,"Captain's Maneuver",['p2','p1'],x_value=1,target_counts=[1,1])
    watch=s.state.rules.delayed[0]
    watch.when['cond'].pop('combat_recipient')
    if receipt=='original_stack_lki':
        watch.when.pop('text',None)
    saved=tmp_path/'fury-legacy.json'
    saved.write_text(s.state.model_dump_json())
    worker=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_conditional_prevention import attack
from tests.test_rules_designations import roundtrip,settle
from tests.test_rules_wave30m_durations import to_phase
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert 'combat_recipient' not in s.state.rules.delayed[0].when['cond']
attack(s,[s.state.cards[sys.argv[3]]],turn=s.state.turn.number)
to_phase(s,'combat_damage');settle(s)
assert s.state.players['p1'].life==39 and s.state.players['p2'].life==36
assert len(s.state.zones.get('p1:exile',[]))==5
assert s.state.rules.decision is None
assert s.state.rules.delayed[0].when['cond']['combat_recipient']=='player'
assert not s.state.rules.delayed[0].when.get('manual_combat_scope')
roundtrip(s);repo.close()
'''
    result=subprocess.run([sys.executable,'-c',worker,str(saved),str(cards.db_path),giant.id],
                          capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
