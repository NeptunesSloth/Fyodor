"""Fresh processes import only production registrations and restore actual games."""
from __future__ import annotations

import pytest

from tests import test_rules_exile_authority_continuations_staged as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put
from tests.test_rules_exile_packet_continuations_cold import fresh_action
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave30m_durations import to_phase

cards = gameplay.cards
staged = gameplay.staged


def cold(s, cards, path, actor, payload):
    return fresh_action(s, cards, path, actor, payload)


@pytest.mark.parametrize('mode', ['hex', 'mnemonic', 'xander', 'abstruse', 'relay'])
def test_staged_actual_packet_authority_cast_in_fresh_process(cards, tmp_path, mode):
    name = {'hex':'Hex Magic', 'mnemonic':'Mnemonic Betrayal', 'xander':"Xander's Pact",
            'abstruse':'Abstruse Appropriation', 'relay':'Galvanic Relay'}[mode]
    s = gameplay.setup(cards, name)
    if mode == 'hex':
        cid = put(s, 'Grizzly Bears', 'hand').id
        stack_library(s, ['Forest'])
        cast(s, name)
    elif mode == 'mnemonic':
        cid = put(s, 'Grizzly Bears', 'graveyard', 'p2').id
        cast(s, name)
    elif mode == 'abstruse':
        cid = put(s, 'Grizzly Bears', 'battlefield', 'p2').id
        cast(s, name, targets=[cid])
    else:
        cid = stack_library(s, ['Grizzly Bears'], pid='p2' if mode == 'xander' else 'p1')[0]
        cast(s, name)
        if mode == 'relay':
            to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='clear_mana', player='p1')
    mana(s, C=2, G=1)
    life = s.state.players['p1'].life
    s = cold(s, cards, tmp_path / (mode+'.json'), 'p1', {'type':'cast_spell','card_id':cid, **({'free':True} if mode=='xander' else {})})
    assert s.state.cards[cid].zone == 'p1:battlefield'
    if mode == 'xander':
        assert s.state.players['p1'].life == life-2


def test_staged_soulfire_cursor_resumes_native_damage_and_next_group_from_fresh_process(cards, tmp_path):
    s = gameplay.setup(cards, 'Soulfire Eruption', 'Hill Giant')
    target = put(s, 'Hill Giant', 'battlefield', 'p3')
    ids = stack_library(s, ['Lightning Bolt', 'Forest', 'Grizzly Bears'])
    source = put(s, 'Soulfire Eruption', 'hand')
    mana(s, C=6, R=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2','p3',target.id],target_counts=[3])
    settle(s)
    d = s.state.rules.decision
    assert d.resume['step'] == 'exile_authority41_soul'
    s = cold(s, cards, tmp_path/'soul.json','p1', {'type':'choose','decision_id':d.id,'option_ids':[target.id]})
    assert s.state.players['p2'].life == 39 and s.state.players['p3'].life == 38
    assert all(s.state.cards[c].zone == 'p1:exile' for c in ids)


@pytest.mark.parametrize('mode',['chiss','durnan','breeches','bismuth','cruelclaw','cannonade','visions','rocco'])
def test_staged_actual_trigger_packets_cast_or_play_in_fresh_process(cards,tmp_path,mode):
    names={'chiss':'Chiss-Goria, Forge Tyrant','durnan':'Durnan of the Yawning Portal','breeches':'Breeches, Brazen Plunderer',
           'bismuth':'Bismuth Mindrender','cruelclaw':'The Infamous Cruelclaw','cannonade':'Brazen Cannonade',
           'visions':'Visions of Phyrexia','rocco':'Rocco, Street Chef'}
    s=gameplay.setup(cards,names[mode])
    source=put(s,names[mode],'battlefield')
    actor='p1'
    payload=None
    if mode=='visions':
        cid=stack_library(s,['Memnite'])[0]
        to_phase(s,'upkeep',turn=4)
        settle(s)
        to_phase(s,'main1',turn=4)
    elif mode=='rocco':
        cid=stack_library(s,['Forest'],pid='p2')[0]
        to_phase(s,'end',turn=1)
        settle(s)
        to_phase(s,'main1',turn=2)
        actor='p2'
        payload={'type':'play_land','card_id':cid}
    else:
        attacker=put(s,'Grizzly Bears','battlefield') if mode=='cannonade' else source
        to_phase(s,'declare_attackers',turn=4)
        cid=stack_library(s,['Memnite' if mode in ('chiss','cannonade') else 'Grizzly Bears'],
                          pid='p2' if mode in ('breeches','bismuth') else 'p1')[0]
        if mode=='cruelclaw':
            put(s,'Lightning Bolt','hand')
        act(s,'p1',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p2'}])
        settle(s)
        if mode=='durnan':
            answer(s,[next(o.id for o in s.state.rules.decision.options if o.card_id==cid)])
            settle(s)
            if s.state.rules.decision is not None:
                answer(s,[o.id for o in s.state.rules.decision.options])
            settle(s)
        if mode in ('breeches','bismuth','cruelclaw'):
            to_phase(s,'combat_damage',turn=4)
            settle(s)
        if mode in ('bismuth','cruelclaw'):
            d=s.state.rules.decision
            payload={'type':'choose','decision_id':d.id,'option_ids':[next(o.id for o in d.options if o.card_id==cid)]}
        else:
            to_phase(s,'main2',turn=4)
            settle(s)
        if mode=='cannonade':
            to_phase(s,'main1',turn=7)
    if payload is None:
        act(s,'p1',type='clear_mana',player='p1')
        mana(s,G=1,C=2)
        payload={'type':'cast_spell','card_id':cid}
    s=cold(s,cards,tmp_path/(mode+'.json'),actor,payload)
    if mode=='cruelclaw' and s.state.rules.decision is not None:
        d=s.state.rules.decision
        discard=next(o.id for o in d.options if o.card_id is not None)
        s=cold(s,cards,tmp_path/(mode+'-discard.json'),'p1',{'type':'choose','decision_id':d.id,'option_ids':[discard]})
    assert s.state.cards[cid].zone==actor+':battlefield'


def test_staged_allure_opponent_selection_and_immediate_offer_restore_in_fresh_process(cards,tmp_path):
    s=gameplay.setup(cards,'Allure of the Unknown')
    ids=stack_library(s,['Memnite','Forest','Island'])
    cast(s,'Allure of the Unknown')
    d=s.state.rules.decision
    s=cold(s,cards,tmp_path/'allure-opponent.json','p1',{'type':'choose','decision_id':d.id,'option_ids':['p2']})
    d=s.state.rules.decision
    s=cold(s,cards,tmp_path/'allure-found.json','p2',{'type':'choose','decision_id':d.id,'option_ids':[next(o.id for o in d.options if o.card_id==ids[0])]})
    d=s.state.rules.decision
    assert all(s.state.cards[c].zone=='p1:hand' for c in ids[1:])
    s=cold(s,cards,tmp_path/'allure-cast.json','p2',{'type':'choose','decision_id':d.id,'option_ids':[next(o.id for o in d.options if o.card_id==ids[0])]})
    assert s.state.cards[ids[0]].zone=='p2:battlefield'


@pytest.mark.parametrize('mode',['mist','flameskull','feral','heist','fury'])
def test_staged_remaining_actual_packet_authorities_in_fresh_process(cards,tmp_path,mode):
    from tests.test_rules_wave4h_activation_costs import ability
    names={'mist':'Primordial Mist','flameskull':'Flameskull','feral':'Feral Encounter','heist':"Cruelclaw's Heist",'fury':"Fire Giant's Fury"}
    s=gameplay.setup(cards,names[mode],'Murder','Hill Giant')
    payload=None
    if mode=='mist':
        source=put(s,names[mode],'battlefield')
        stack_library(s,['Grizzly Bears'])
        to_phase(s,'end',turn=1)
        settle(s)
        answer(s,['yes'])
        cid=next(c.id for c in s.state.cards.values() if c.owner=='p1' and c.zone=='p1:battlefield' and c.face_down)
        to_phase(s,'main1',turn=4)
        act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'Exile'),cost_choices=[{'component':0,'cards':[cid]}])
        settle(s)
    elif mode=='flameskull':
        source=put(s,names[mode],'battlefield')
        cid=stack_library(s,['Forest'])[0]
        cast(s,'Murder',targets=[source.id])
        payload={'type':'play_land','card_id':cid}
    elif mode=='feral':
        cid=stack_library(s,['Grizzly Bears'])[0]
        cast(s,names[mode])
        answer(s,[next(o.id for o in s.state.rules.decision.options if o.card_id==cid)])
        settle(s)
    elif mode=='heist':
        cid=put(s,'Grizzly Bears','hand','p2').id
        source=put(s,names[mode],'hand')
        mana(s,B=2)
        act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'],optional_costs=[f'{source.id}:gift'])
        answer(s,['p3'])
        settle(s)
        answer(s,[next(o.id for o in s.state.rules.decision.options if o.card_id==cid)])
        settle(s)
    else:
        giant=put(s,'Hill Giant','battlefield')
        to_phase(s,'main1',turn=4)
        cast(s,names[mode],targets=[giant.id])
        cid=stack_library(s,['Grizzly Bears'])[0]
        to_phase(s,'declare_attackers',turn=4)
        act(s,'p1',type='declare_attackers',attackers=[{'card_id':giant.id,'target':'p2'}])
        to_phase(s,'main2',turn=4)
        settle(s)
    if payload is None:
        act(s,'p1',type='clear_mana',player='p1')
        mana(s,C=2,G=1)
        payload={'type':'cast_spell','card_id':cid}
    s=cold(s,cards,tmp_path/(mode+'.json'),'p1',payload)
    assert s.state.cards[cid].zone=='p1:battlefield'
