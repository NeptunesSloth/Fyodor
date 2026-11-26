"""Actual staged42 casts prove bounded server-side snapshots and ability transfer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import effects, engine, scripts
from app.rules import exile_outcomes42 as leaf
from app.rules import exile_packet_continuations as packets
from tests.conftest import connect_game
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ch
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/exile_outcomes42_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='eo42',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.fixture(autouse=True)
def staged(monkeypatch):
    native=scripts.define
    native_parse=scripts.parse_effects
    monkeypatch.setattr(scripts,'parse_effects',lambda body,*args,**kwargs:leaf.parse(body) or native_parse(body,*args,**kwargs))
    scripts._cached.cache_clear()
    monkeypatch.setattr(scripts,'define',lambda ability,ch:leaf.definition(ability,ch) or native(ability,ch))
    for name,callback in leaf.PRIMITIVES.items():
        monkeypatch.setitem(effects.PRIMITIVES,name,callback)
    for name,callback in leaf.RESUME.items():
        monkeypatch.setitem(engine.RESUME,name,callback)
    yield
    scripts._cached.cache_clear()


def setup(cards,*extra):
    names=["Lifestream's Blessing",'Rivaz of the Claw','Dragon Whelp','Twincast','Grizzly Bears','Murder','Giant Growth',"Ashnod's Altar",*extra]
    s=table(cards,names,names,names)
    to_phase(s,'main1',turn=1)
    act(s,'p1',type='set_prefs',hold_priority=True)
    return s


def test_lifestream_frozen_as_cast_power_survives_response_and_spell_copy_without_copy_exile_cast(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    source=put(s,"Lifestream's Blessing",'hand')
    mana(s,C=4,G=2)
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=99)
    assert s.state.rules.stack[source.id].x==2
    record=next(p for p in s.state.rules.payments.values() if p.card==source.id)
    assert record.cast_greatest_power==2
    copied=put(s,'Twincast','hand')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=copied.id,targets=[source.id])
    # Respond to Twincast with a native actual pump: neither original nor copy may recompute5.
    growth=put(s,'Giant Growth','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    before=len(s.state.zones.get('p1:hand',[]))
    settle(s)
    assert len(s.state.zones.get('p1:hand',[]))==before+4
    assert s.state.players['p1'].life==40
    roundtrip(s)


def test_rivaz_actual_graveyard_dragon_gains_visible_death_ability_and_keeps_it_on_battlefield(cards):
    s=setup(cards)
    put(s,'Rivaz of the Claw','battlefield')
    dragon=put(s,'Dragon Whelp','graveyard')
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    # Native trigger resolves before its Dragon spell.
    settle(s)
    assert s.state.cards[dragon.id].zone=='p1:battlefield'
    assert any(a.text=='When this creature dies, exile it.' for a in ch(s,s.state.cards[dragon.id]).abilities)
    cast(s,'Murder',targets=[dragon.id])
    assert s.state.cards[dragon.id].zone=='p1:exile'
    roundtrip(s)


def test_lifestream_manual_mana_window_keeps_snapshot_when_power_source_is_sacrificed(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    altar=put(s,"Ashnod's Altar",'battlefield')
    growth=put(s,'Giant Growth','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    settle(s)
    source=put(s,"Lifestream's Blessing",'hand')
    act(s,'p1',type='set_prefs',payment='self')
    mana(s,C=2,G=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    assert s.state.rules.decision.resume['cast_greatest_power']==5
    roundtrip(s)
    act(s,'p1',type='activate_ability',card_id=altar.id,ability=0,
        cost_choices=[{'component':0,'cards':[bear.id]}])
    if s.state.rules.decision is not None:
        answer(s,['pay'])
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    record=next(p for p in s.state.rules.payments.values() if p.card==source.id)
    assert record.cast_greatest_power==5
    settle(s)
    roundtrip(s)


@pytest.mark.parametrize('mode',['zero','safe','bust'])
def test_dance_actual_public_cursor_stop_zero_safe_or_continue_after_bust(cards,mode):
    extras=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/exile_outcomes42_cards.json').read_text())]
    s=setup(cards,*extras)
    cast(s,'Dance with Calamity')
    assert s.state.rules.decision.resume['step']=='exile_outcomes42_dance'
    chosen=[]
    total=0
    if mode=='safe':
        cid=s.state.zones['p1:library'][0]
        chosen.append(cid)
        answer(s,['yes'])
        total=ch(s,s.state.cards[cid]).mana_value
        assert total<=13
    elif mode=='bust':
        for _ in range(len(s.state.zones['p1:library'])):
            cid=s.state.zones['p1:library'][0]
            chosen.append(cid)
            answer(s,['yes'])
            total+=ch(s,s.state.cards[cid]).mana_value
            if total>13:
                break
        assert total>13
        # Bust does not force a stop; one more legal cursor choice is still offered.
        if s.state.zones['p1:library']:
            cid=s.state.zones['p1:library'][0]
            chosen.append(cid)
            answer(s,['yes'])
    if s.state.rules.decision is not None and s.state.rules.decision.resume['step']=='exile_outcomes42_dance':
        answer(s,['no'])
    if mode=='safe' and s.state.rules.decision is not None:
        assert s.state.rules.decision.resume['step']=='free_cast_pick'
        answer(s,[])
    settle(s)
    assert all(s.state.cards[cid].zone=='p1:exile' for cid in chosen)
    assert s.state.rules.free_cast_then is None
    roundtrip(s)


@pytest.mark.parametrize('immediate',[False,True])
def test_lifestream_exile_cast_uses_frozen_value_and_copy_is_not_an_exile_cast(cards,immediate):
    import random

    from app.game.session import GameSession
    from app.rules import context, permissions
    from app.rules.plan import Plan
    s=setup(cards,'Allure of the Unknown')
    put(s,'Grizzly Bears','battlefield')
    if immediate:
        put(s,'Grizzly Bears','battlefield','p2')
        act(s,'p2',type='set_prefs',hold_priority=True)
        source=put(s,"Lifestream's Blessing",'library')
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'library'},position='top')
        cast(s,'Allure of the Unknown')
        answer(s,['p2'])
        d=s.state.rules.decision
        answer(s,[next(o.id for o in d.options if o.card_id==source.id)])
        d=s.state.rules.decision
        act(s,'p2',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==source.id)])
        for _ in range(3):
            if s.state.rules.priority=='p1':
                break
            act(s,s.state.rules.priority,type='pass_priority')
    else:
        source=put(s,"Lifestream's Blessing",'exile')
        plan=Plan(s.state,'p1',cards,random.Random(3))
        ctx={'controller':'p1','name':'Native resolving exile authority'}
        context.bind_objects(plan,ctx,'packet',[source.id])
        permissions.grant_play(plan,ctx,{'who':'ref:packet','from_exile':True,'play':False,'cast':True,'until':'end_of_turn'})
        s=GameSession(plan.state,cards=cards)
        mana(s,C=4,G=2)
        act(s,'p1',type='cast_spell',card_id=source.id)
    assert s.state.rules.stack[source.id].x==2
    copy=put(s,'Twincast','hand')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=copy.id,targets=[source.id])
    settle(s)
    assert s.state.players['p1'].life==(40 if immediate else 44)
    assert s.state.players['p2'].life==(44 if immediate else 40)
    roundtrip(s)


def test_dance_actual_two_spells_cast_before_either_resolves(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Dance with Calamity','Memnite','Memnite')
    source=put(s,'Dance with Calamity','hand')
    ids=stack_library(s,['Memnite','Memnite'])
    other=[cid for cid in s.state.zones['p1:library'] if cid not in ids]
    if other:
        act(s,'p1',type='move',card_ids=other,to={'player':'p1','zone':'graveyard'})
    mana(s,C=7,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    answer(s,['yes'])
    answer(s,['yes'])
    ids=[c.id for c in s.state.cards.values() if c.owner=='p1' and c.name=='Memnite' and c.zone=='p1:exile']
    assert len(ids)==2
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    first=next(o for o in d.options if o.card_id in ids)
    answer(s,[first.id])
    assert s.state.cards[first.card_id].zone=='stack'
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    second=next(o for o in d.options if o.card_id in ids and o.card_id!=first.card_id)
    answer(s,[second.id])
    settle(s)
    assert all(s.state.cards[cid].zone=='p1:battlefield' for cid in ids)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_rivaz_copied_trigger_grants_two_distinct_native_abilities_and_source_departure_does_not_remove_them(cards):
    s=setup(cards,'Strionic Resonator','Murder')
    rivaz=put(s,'Rivaz of the Claw','battlefield')
    resonator=put(s,'Strionic Resonator','battlefield')
    dragon=put(s,'Dragon Whelp','graveyard')
    mana(s,C=4,R=2)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    trigger=next(sid for sid,entry in s.state.rules.stack.items() if entry.kind=='trigger' and entry.source_card==rivaz.id)
    act(s,'p1',type='activate_ability',card_id=resonator.id,ability=0,targets=[trigger])
    settle(s)
    abilities=[a for a in ch(s,s.state.cards[dragon.id]).abilities if a.text=='When this creature dies, exile it.']
    assert len(abilities)==2 and len({a.index for a in abilities})==2, ([(e.id,e.affected,e.add_abilities) for e in s.state.rules.effects], [(k,p.mana_riders) for k,p in s.state.rules.payments.items() if p.card==dragon.id])
    cast(s,'Murder',targets=[rivaz.id])
    assert len([a for a in ch(s,s.state.cards[dragon.id]).abilities if a.text=='When this creature dies, exile it.'])==2
    second=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Murder' and c.zone!='p1:graveyard')
    act(s,'p1',type='move',card_ids=[second.id],to={'player':'p1','zone':'hand'})
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=second.id,targets=[dragon.id])
    settle(s)
    assert s.state.cards[dragon.id].zone=='p1:exile'
    roundtrip(s)


def test_rivaz_granted_stack_death_ability_is_not_copied_by_double_major(cards):
    s=setup(cards,'Double Major')
    put(s,'Rivaz of the Claw','battlefield')
    dragon=put(s,'Dragon Whelp','graveyard')
    mana(s,C=2,R=2,G=1,U=1)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    for _ in range(12):
        if all(entry.kind=='spell' for entry in s.state.rules.stack.values()) and s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    else:
        pytest.fail('Rivaz trigger did not resolve before the Dragon spell')
    assert any(a.text=='When this creature dies, exile it.' for a in ch(s,s.state.cards[dragon.id]).abilities)
    copy=put(s,'Double Major','hand')
    act(s,'p1',type='cast_spell',card_id=copy.id,targets=[dragon.id])
    settle(s)
    token=next(c for c in s.state.cards.values() if c.is_token and c.name=='Dragon Whelp' and c.zone=='p1:battlefield')
    assert any(a.text=='When this creature dies, exile it.' for a in ch(s,s.state.cards[dragon.id]).abilities)
    assert not any(a.text=='When this creature dies, exile it.' for a in ch(s,token).abilities)
    roundtrip(s)


def test_lifestream_empty_creature_snapshot_zero_survives_later_creature_entry(cards):
    s=setup(cards)
    source=put(s,"Lifestream's Blessing",'hand')
    mana(s,C=4,G=2)
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=99)
    assert s.state.rules.stack[source.id].x==0
    assert next(p for p in s.state.rules.payments.values() if p.card==source.id).cast_greatest_power==0
    put(s,'Grizzly Bears','battlefield')
    before=len(s.state.zones.get('p1:hand',[]))
    settle(s)
    assert len(s.state.zones.get('p1:hand',[]))==before
    roundtrip(s)


def test_theorist_actual_discard_exiles_exact_card_and_allows_paid_cast(cards):
    s=setup(cards,'Conspiracy Theorist','Merfolk Looter')
    put(s,'Conspiracy Theorist','battlefield')
    looter=put(s,'Merfolk Looter','battlefield')
    dragon=put(s,'Dragon Whelp','hand')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    d=s.state.rules.decision
    assert d.resume['step']=='exile_outcomes42_discard'
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    assert s.state.cards[dragon.id].zone=='p1:exile'
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    settle(s)
    assert s.state.cards[dragon.id].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('decline',[False,True])
def test_theorist_discard_trigger_survives_source_departure_and_may_decline(cards,decline):
    s=setup(cards,'Conspiracy Theorist','Merfolk Looter')
    theorist=put(s,'Conspiracy Theorist','battlefield')
    looter=put(s,'Merfolk Looter','battlefield')
    dragon=put(s,'Dragon Whelp','hand')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    act(s,d.decider or d.player,type='choose',decision_id=d.id,
        option_ids=[next(o.id for o in d.options if o.card_id==dragon.id)])
    # Native destroy before the already-triggered permission ability resolves.
    for _ in range(4):
        if s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    murder=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=murder.id,targets=[theorist.id])
    settle(s)
    assert s.state.cards[theorist.id].zone=='p1:graveyard'
    d=s.state.rules.decision
    assert d.resume['step']=='exile_outcomes42_discard'
    answer(s,[] if decline else [next(o.id for o in d.options if o.card_id==dragon.id)])
    assert s.state.cards[dragon.id].zone==('p1:graveyard' if decline else 'p1:exile')
    roundtrip(s)


def test_theorist_attack_payment_line_has_native_definition(cards):
    s=setup(cards,'Conspiracy Theorist')
    source=put(s,'Conspiracy Theorist','battlefield')
    ability=next(a for a in ch(s,source).abilities if a.text.startswith('Whenever this creature attacks'))
    assert scripts.define(ability,ch(s,source)) is not None


def test_theorist_actual_attack_declines_payment_without_draw_or_discard(cards):
    s=setup(cards,'Conspiracy Theorist')
    source=put(s,'Conspiracy Theorist','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    put(s,'Dragon Whelp','hand')
    mana(s,C=1)
    before=len(s.state.zones.get('p1:hand',[]))
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    assert any(o.id=='decline' for o in d.options),d
    answer(s,['decline'])
    assert len(s.state.zones.get('p1:hand',[]))==before
    assert s.state.rules.decision is None
    roundtrip(s)


def test_theorist_attack_pays_mana_and_discard_once_then_draws_and_exiles(cards):
    s=setup(cards,'Conspiracy Theorist')
    source=put(s,'Conspiracy Theorist','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    dragon=put(s,'Dragon Whelp','hand')
    mana(s,C=1)
    before=len(s.state.zones.get('p1:hand',[]))
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    answer(s,['pay'])
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    d=s.state.rules.decision
    assert d.resume['step']=='exile_outcomes42_discard'
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    assert len(s.state.zones.get('p1:hand',[]))==before
    assert s.state.cards[dragon.id].zone=='p1:exile'
    assert not s.state.rules.decision
    roundtrip(s)


def test_theorist_simultaneous_two_card_discard_has_one_optional_exile_choice(cards):
    s=setup(cards,'Conspiracy Theorist','Cathartic Reunion')
    put(s,'Conspiracy Theorist','battlefield')
    dragon=put(s,'Dragon Whelp','hand')
    bear=put(s,'Grizzly Bears','hand')
    reunion=put(s,'Cathartic Reunion','hand')
    mana(s,C=1,R=1)
    act(s,'p1',type='cast_spell',card_id=reunion.id)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id),next(o.id for o in d.options if o.card_id==bear.id)])
    d=s.state.rules.decision
    assert d.resume['step']=='exile_outcomes42_discard'
    assert d.max_choices==1 and {o.card_id for o in d.options}=={dragon.id,bear.id}
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    assert s.state.rules.decision is None
    assert s.state.cards[dragon.id].zone=='p1:exile' and s.state.cards[bear.id].zone=='p1:graveyard'
    roundtrip(s)


def test_theorist_discard_redirected_to_exile_does_not_grant_cast_authority(cards):
    from app.game.errors import ActionError

    s=setup(cards,'Conspiracy Theorist','Merfolk Looter','Rest in Peace')
    put(s,'Conspiracy Theorist','battlefield')
    looter=put(s,'Merfolk Looter','battlefield')
    put(s,'Rest in Peace','battlefield')
    dragon=put(s,'Dragon Whelp','hand')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    assert s.state.cards[dragon.id].zone=='p1:exile'
    assert s.state.rules.decision is None
    mana(s,C=2,R=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon.id)
    roundtrip(s)


def test_theorist_exact_exile_cast_authority_expires_after_turn(cards):
    from app.game.errors import ActionError

    s=setup(cards,'Conspiracy Theorist','Merfolk Looter')
    put(s,'Conspiracy Theorist','battlefield')
    looter=put(s,'Merfolk Looter','battlefield')
    dragon=put(s,'Dragon Whelp','hand')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    to_phase(s,'main1',turn=7)
    mana(s,C=2,R=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon.id)
    assert s.state.cards[dragon.id].zone=='p1:exile'
    roundtrip(s)


def test_kingpin_actual_simultaneous_one_damage_each_opponent_triggers_once(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Ob Nixilis, Captive Kingpin','Spear Spewer','Forest')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    spear=put(s,'Spear Spewer','battlefield')
    to_phase(s,'main1',turn=4)
    top=stack_library(s,['Forest'])[0]
    act(s,'p1',type='activate_ability',card_id=spear.id,ability=next(a.index for a in ch(s,spear).abilities if a.text.startswith('{T}')))
    settle(s)
    assert s.state.cards[kingpin.id].counters.get('+1/+1')==1
    assert s.state.cards[top].zone=='p1:exile'
    assert len([p for p in s.state.rules.permissions if p.card==top])==1
    act(s,'p1',type='play_land',card_id=top)
    assert s.state.cards[top].zone=='p1:battlefield'
    roundtrip(s)


def test_kingpin_actual_three_damage_loss_does_not_trigger(cards):
    s=setup(cards,'Ob Nixilis, Captive Kingpin','Lightning Bolt')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    bolt=put(s,'Lightning Bolt','hand')
    before=list(s.state.zones['p1:library'])
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life==37
    assert not s.state.cards[kingpin.id].counters.get('+1/+1')
    assert s.state.zones['p1:library']==before
    roundtrip(s)


@pytest.mark.parametrize('damage,expected',[(1,0),(2,1)])
def test_kingpin_actual_mixed_prevented_damage_cohort_uses_each_opponents_loss(cards,damage,expected):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Ob Nixilis, Captive Kingpin','Earthquake',"Urza's Armor",'Forest')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    put(s,"Urza's Armor",'battlefield','p2')
    if damage==1:
        put(s,"Urza's Armor",'battlefield','p3')
    top=stack_library(s,['Forest'])[0]
    spell=put(s,'Earthquake','hand')
    mana(s,C=damage,R=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,x_value=damage)
    settle(s)
    assert s.state.players['p2'].life==40-max(0,damage-1)
    assert s.state.players['p3'].life==40-(0 if damage==1 else 2)
    assert s.state.cards[kingpin.id].counters.get('+1/+1',0)==expected
    assert s.state.cards[top].zone==('p1:exile' if expected else 'p1:library')
    roundtrip(s)


def test_kingpin_simultaneous_combat_three_one_power_attackers_is_loss_three(cards):
    s=setup(cards,'Ob Nixilis, Captive Kingpin','Memnite','Memnite','Memnite')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    attackers=[c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Memnite']
    assert len(attackers)==3
    for c in attackers:
        act(s,'p1',type='move',card_ids=[c.id],to={'player':'p1','zone':'battlefield'})
    to_phase(s,'declare_attackers',turn=4)
    before=len(s.state.zones['p1:exile'])
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':c.id,'target':'p2'} for c in attackers])
    to_phase(s,'main2',turn=4)
    settle(s)
    assert s.state.players['p2'].life==37
    assert not s.state.cards[kingpin.id].counters.get('+1/+1')
    assert len(s.state.zones['p1:exile'])==before
    roundtrip(s)


def test_kingpin_actual_opponent_pay_one_life_mana_ability_triggers(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s=setup(cards,'Ob Nixilis, Captive Kingpin','Blood Celebrant')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    celebrant=put(s,'Blood Celebrant','battlefield','p2')
    mana(s,'p2',B=1)
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=celebrant.id,ability=0)
    settle(s)
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        answer(s,[d.options[0].id])
    settle(s)
    assert s.state.players['p2'].life==39
    assert s.state.cards[kingpin.id].counters.get('+1/+1')==1
    roundtrip(s)


def test_kingpin_source_departure_keeps_original_controller_packet_until_next_endstep(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Ob Nixilis, Captive Kingpin','Spear Spewer','Memnite')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    spear=put(s,'Spear Spewer','battlefield')
    to_phase(s,'main1',turn=4)
    top=stack_library(s,['Memnite'])[0]
    act(s,'p1',type='activate_ability',card_id=spear.id,ability=next(a.index for a in ch(s,spear).abilities if a.text.startswith('{T}')))
    for _ in range(9):
        if any(e.kind=='trigger' and e.source_card==kingpin.id for e in s.state.rules.stack.values()) and s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    else:
        pytest.fail('Kingpin life loss trigger did not reach priority')
    murder=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=murder.id,targets=[kingpin.id])
    settle(s)
    assert s.state.cards[kingpin.id].zone=='p1:graveyard'
    assert s.state.cards[top].zone=='p1:exile'
    assert any(p.card==top and p.player=='p1' for p in s.state.rules.permissions)
    to_phase(s,'main2',turn=4)
    assert any(p.card==top and p.player=='p1' for p in s.state.rules.permissions)
    to_phase(s,'end',turn=4)
    settle(s)
    assert not any(p.card==top for p in s.state.rules.permissions)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=top)
    roundtrip(s)


def test_tinybones_actual_discard_stash_foreign_card_can_cast_with_wrong_color_mana(cards):
    s=setup(cards,'Tinybones, Bauble Burglar','Merfolk Looter')
    put(s,'Tinybones, Bauble Burglar','battlefield')
    looter=put(s,'Merfolk Looter','battlefield','p2')
    dragon=put(s,'Dragon Whelp','hand','p2')
    to_phase(s,'main1',turn=4)
    from tests.test_rules_bandmate_references import wait_priority
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    assert s.state.cards[dragon.id].zone=='p2:exile'
    assert s.state.cards[dragon.id].counters.get('stash')==1
    wait_priority(s,'p1')
    mana(s,C=4)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    settle(s)
    assert s.state.cards[dragon.id].zone=='p1:battlefield'
    roundtrip(s)


def test_tinybones_actual_sorcery_activation_discards_each_opponent_and_plays_stashed_land(cards):
    s=setup(cards,'Tinybones, Bauble Burglar','Forest')
    source=put(s,'Tinybones, Bauble Burglar','battlefield')
    dragon=put(s,'Dragon Whelp','hand','p2')
    forest=put(s,'Forest','hand','p3')
    to_phase(s,'main1',turn=4)
    mana(s,C=3,B=1)
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{3}'))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index)
    settle(s)
    for _ in range(4):
        d=s.state.rules.decision
        if d is None:
            break
        allowed={dragon.id,forest.id}
        answer(s,[next(o.id for o in d.options if o.card_id in allowed)])
    assert s.state.rules.decision is None
    assert all(s.state.cards[cid].zone.endswith(':exile') and s.state.cards[cid].counters.get('stash')==1 for cid in [dragon.id,forest.id])
    assert s.state.cards[source.id].tapped
    act(s,'p1',type='play_land',card_id=forest.id)
    assert s.state.cards[forest.id].zone=='p1:battlefield'
    roundtrip(s)


def test_tinybones_source_departure_and_native_reentry_restore_only_actual_stash_objects(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority

    s=setup(cards,'Tinybones, Bauble Burglar','Merfolk Looter','Unearth')
    source=put(s,'Tinybones, Bauble Burglar','battlefield')
    original=s.state.rules.object_id(source.id)
    looter=put(s,'Merfolk Looter','battlefield','p2')
    dragon=put(s,'Dragon Whelp','hand','p2')
    other=put(s,'Grizzly Bears','exile','p2')
    to_phase(s,'main1',turn=4)
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    wait_priority(s,'p1')
    cast(s,'Murder',targets=[source.id])
    mana(s,C=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon.id)
    unearth=put(s,'Unearth','hand')
    mana(s,B=1)
    act(s,'p1',type='cast_spell',card_id=unearth.id,targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.rules.object_id(source.id)!=original
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=other.id)
    mana(s,C=4)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    settle(s)
    assert s.state.cards[dragon.id].zone=='p1:battlefield'
    roundtrip(s)


def test_tinybones_own_stashed_card_is_excluded_even_with_another_tinybones(cards):
    from app.game.errors import ActionError

    s=setup(cards,'Tinybones, Bauble Burglar','Merfolk Looter')
    put(s,'Tinybones, Bauble Burglar','battlefield')
    put(s,'Tinybones, Bauble Burglar','battlefield','p2')
    looter=put(s,'Merfolk Looter','battlefield')
    dragon=put(s,'Dragon Whelp','hand')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    assert s.state.cards[dragon.id].zone=='p1:exile'
    assert s.state.cards[dragon.id].counters.get('stash')==1
    mana(s,C=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon.id)
    roundtrip(s)


def test_grolnok_actual_frog_attack_mills_three_exiles_only_permanents_and_plays_them(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Grolnok, the Omnivore','Forest','Memnite')
    source=put(s,'Grolnok, the Omnivore','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    ids=stack_library(s,['Forest','Memnite','Murder'])
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    assert all(s.state.cards[cid].zone=='p1:exile' and s.state.cards[cid].counters.get('croak')==1 for cid in ids[:2]), [(s.state.cards[cid].name,s.state.cards[cid].zone,s.state.cards[cid].counters) for cid in ids]
    assert s.state.cards[ids[2]].zone=='p1:graveyard'
    to_phase(s,'main2',turn=4)
    act(s,'p1',type='play_land',card_id=ids[0])
    act(s,'p1',type='cast_spell',card_id=ids[1])
    settle(s)
    assert all(s.state.cards[cid].zone=='p1:battlefield' for cid in ids[:2])
    roundtrip(s)


def test_tinybones_any_type_authority_pays_actual_colorless_requirement_with_red_units(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s=setup(cards,'Tinybones, Bauble Burglar','Merfolk Looter','Spatial Contortion')
    put(s,'Tinybones, Bauble Burglar','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    looter=put(s,'Merfolk Looter','battlefield','p2')
    spell=put(s,'Spatial Contortion','hand','p2')
    to_phase(s,'main1',turn=4)
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==spell.id)])
    wait_priority(s,'p1')
    mana(s,R=2)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[bear.id])
    settle(s)
    assert s.state.cards[spell.id].zone=='p2:graveyard'
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    roundtrip(s)


def test_grolnok_source_departure_disables_croak_cards_and_new_source_restores_authority(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Grolnok, the Omnivore','Grolnok, the Omnivore','Memnite')
    source=put(s,'Grolnok, the Omnivore','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    top=stack_library(s,['Memnite'])[0]
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    to_phase(s,'main2',turn=4)
    assert s.state.cards[top].zone=='p1:exile' and s.state.cards[top].counters.get('croak')==1
    cast(s,'Murder',targets=[source.id])
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=top)
    second=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Grolnok, the Omnivore' and c.id!=source.id)
    act(s,'p1',type='move',card_ids=[second.id],to={'player':'p1','zone':'hand'})
    mana(s,C=2,G=1,U=1)
    act(s,'p1',type='cast_spell',card_id=second.id)
    settle(s)
    act(s,'p1',type='cast_spell',card_id=top)
    settle(s)
    assert s.state.cards[top].zone=='p1:battlefield'
    roundtrip(s)


def test_grolnok_hand_discard_permanent_is_not_library_to_graveyard_event(cards):
    s=setup(cards,'Grolnok, the Omnivore','Merfolk Looter')
    put(s,'Grolnok, the Omnivore','battlefield')
    looter=put(s,'Merfolk Looter','battlefield')
    dragon=put(s,'Dragon Whelp','hand')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    assert s.state.cards[dragon.id].zone=='p1:graveyard' and not s.state.cards[dragon.id].counters
    assert s.state.rules.decision is None
    roundtrip(s)


def test_lobelia_actual_face_down_packet_optional_free_play_mode_has_shared_one_card_limit(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Lobelia, Defender of Bag End','Memnite')
    to_phase(s,'main1',turn=4)
    stack_library(s,['Dragon Whelp'],pid='p2')
    stack_library(s,['Grizzly Bears'],pid='p3')
    source=put(s,'Lobelia, Defender of Bag End','hand')
    assert scripts.definitions(ch(s,source))[0]['effects'][0]['do']=='exile_outcomes42_lobelia_enter', [(a.text,packets.normalize(scripts.self_text(a.text,ch(s,source).name))) for a in ch(s,source).abilities]
    mana(s,C=2,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    for _ in range(3):
        d=s.state.rules.decision
        if d is None:
            break
        answer(s,[o.id for o in d.options][:d.max_choices])
    packet=[c for c in s.state.cards.values() if c.owner in {'p2','p3'} and c.zone.endswith(':exile')]
    assert len(packet)==2 and all(c.face_down for c in packet)
    # Its tap cost needs an actual later own turn.
    to_phase(s,'main1',turn=7)
    artifact=put(s,'Memnite','battlefield')
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{T}'))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,modes=[0])
    d=s.state.rules.decision
    if d is not None:
        answer(s,[next(o.id for o in d.options if o.card_id==artifact.id)])
    settle(s)
    assert s.state.cards[artifact.id].zone=='p1:graveyard'
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='cast_spell',card_id=packet[0].id,free=True)
    settle(s)
    assert s.state.cards[packet[0].id].zone=='p1:battlefield'
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=packet[1].id,free=True)
    roundtrip(s)


def test_lobelia_actual_second_mode_sacrifices_artifact_each_opponent_loses_two_gain_two_once(cards):
    s=setup(cards,'Lobelia, Defender of Bag End','Memnite')
    source=put(s,'Lobelia, Defender of Bag End','battlefield')
    artifact=put(s,'Memnite','battlefield')
    to_phase(s,'main1',turn=4)
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{T}'))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,modes=[1])
    d=s.state.rules.decision
    if d is not None:
        answer(s,[next(o.id for o in d.options if o.card_id==artifact.id)])
    settle(s)
    assert s.state.cards[source.id].tapped and s.state.cards[artifact.id].zone=='p1:graveyard'
    assert [s.state.players[p].life for p in ['p1','p2','p3']]==[42,38,38]
    roundtrip(s)


def test_intellect_actual_opponents_choose_private_hand_cards_linked_cast_and_source_return(cards):
    s=setup(cards,'Intellect Devourer','Forest')
    dragon=put(s,'Dragon Whelp','hand','p2')
    forest=put(s,'Forest','hand','p3')
    source=put(s,'Intellect Devourer','hand')
    mana(s,C=3,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    assert d.player=='p2'
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    assert s.state.cards[dragon.id].zone=='p2:hand'
    d=s.state.rules.decision
    assert d.player=='p3'
    answer(s,[next(o.id for o in d.options if o.card_id==forest.id)])
    assert s.state.cards[dragon.id].zone=='p2:exile' and s.state.cards[forest.id].zone=='p3:exile'
    mana(s,C=4)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    settle(s)
    assert s.state.cards[dragon.id].zone=='p1:battlefield'
    cast(s,'Murder',targets=[source.id])
    assert s.state.cards[forest.id].zone=='p3:hand'
    assert s.state.cards[dragon.id].zone=='p1:battlefield'
    roundtrip(s)


def test_intellect_source_departure_before_etb_resolution_does_not_choose_or_exile_hand_cards(cards):
    s=setup(cards,'Intellect Devourer','Forest')
    dragon=put(s,'Dragon Whelp','hand','p2')
    forest=put(s,'Forest','hand','p3')
    source=put(s,'Intellect Devourer','hand')
    mana(s,C=3,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    for _ in range(9):
        if any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values()) and s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    else:
        pytest.fail('Intellect ETB did not reach priority')
    murder=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=murder.id,targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[dragon.id].zone=='p2:hand' and s.state.cards[forest.id].zone=='p3:hand'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_lobelia_actual_face_down_packet_rest_websocket_privacy_and_look_survive_source_departure(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.test_rules_linked_exile_look import assert_look
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Lobelia, Defender of Bag End')
    stack_library(s,['Dragon Whelp'],pid='p2')
    stack_library(s,['Grizzly Bears'],pid='p3')
    source=put(s,'Lobelia, Defender of Bag End','hand')
    mana(s,C=2,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    packet=[c for c in s.state.cards.values() if c.owner in {'p2','p3'} and c.zone.endswith(':exile')]
    assert len(packet)==2
    cast(s,'Murder',targets=[source.id])
    for exiled in packet:
        assert_look(s,exiled.id,['p1'])
    with TestClient(create_app(settings)) as client:
        room=client.app.state.services.hub.create_room(s,mode='lan')
        for player,seat in room.seats.items():
            seat.token='lobelia42-'+player
        room.spectator_tokens.add('lobelia42-spectator')
        for viewer in ['p1','p2','p3','spectator']:
            token='lobelia42-'+viewer
            payload=client.get(f'/api/games/{room.id}/view',headers={'X-Seat-Token':token}).json()
            with connect_game(client, room.id, token) as ws:
                frame=ws.receive_json()
            for exiled in packet:
                for view in [payload,frame['view']]:
                    if viewer=='p1':
                        assert view['cards'][exiled.id]['name']==exiled.name
                    else:
                        assert 'name' not in view['cards'][exiled.id]
                        assert 'card_id' not in view['cards'][exiled.id]
    roundtrip(s)


def monk_level_three(s):
    source=put(s,'Monk Class','hand')
    mana(s,W=1,U=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    target=put(s,'Grizzly Bears','battlefield','p2')
    mana(s,W=1,U=1)
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{W}{U}'))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index)
    settle(s)
    for _ in range(3):
        d=s.state.rules.decision
        if d is None:
            break
        answer(s,[next(o.id for o in d.options if o.card_id==target.id)])
    assert s.state.cards[target.id].zone=='p2:hand'
    mana(s,C=1,W=1,U=1)
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{1}{W}{U}'))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index)
    settle(s)
    # The Class was the first spell; levels are abilities. The second spell costs G.
    bear=put(s,'Grizzly Bears','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=bear.id)
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    return source


def test_monk_actual_levels_and_exiled_card_has_visible_conditional_self_cast_ability(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Monk Class','Disenchant','Double Major','Rest in Peace')
    source=monk_level_three(s)
    top=stack_library(s,['Dragon Whelp'])[0]
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[top].zone=='p1:exile'
    assert any(a.text==leaf.MONK_ABILITY for a in ch(s,s.state.cards[top]).abilities)
    assert any(a['text']==leaf.MONK_ABILITY for a in s.view('p1')['rules']['stats'][top]['abilities'])
    assert not any(p.card==top for p in s.state.rules.permissions)
    from app.rules import layers
    assert not any(a.text==leaf.MONK_ABILITY for a in layers.copiable(s.state,s.state.cards[top],cards).abilities)
    exile_oid=s.state.rules.object_id(top)
    to_phase(s,'main1',turn=4)
    mana(s,C=2,R=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=top)
    disenchant=put(s,'Disenchant','hand')
    mana(s,C=1,W=1)
    act(s,'p1',type='cast_spell',card_id=disenchant.id,targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert any(a.text==leaf.MONK_ABILITY for a in ch(s,s.state.cards[top]).abilities)
    act(s,'p1',type='cast_spell',card_id=top)
    assert not any(a.text==leaf.MONK_ABILITY for a in ch(s,s.state.cards[top]).abilities)
    major=put(s,'Double Major','hand')
    mana(s,G=1,U=1)
    act(s,'p1',type='cast_spell',card_id=major.id,targets=[top])
    settle(s)
    token=next(c for c in s.state.cards.values() if c.is_token and c.name=='Dragon Whelp')
    assert not any(a.text==leaf.MONK_ABILITY for a in ch(s,token).abilities)
    assert not any(a.text==leaf.MONK_ABILITY for a in ch(s,s.state.cards[top]).abilities)
    put(s,'Rest in Peace','battlefield')
    cast(s,'Murder',targets=[top])
    assert s.state.cards[top].zone=='p1:exile'
    assert s.state.rules.object_id(top)!=exile_oid
    assert not any(a.text==leaf.MONK_ABILITY for a in ch(s,s.state.cards[top]).abilities)
    mana(s,C=2,R=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=top)
    roundtrip(s)


def test_monk_upkeep_exile_ability_is_unavailable_before_level_three(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Monk Class','Memnite')
    source=put(s,'Monk Class','hand')
    mana(s,W=1,U=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    top=stack_library(s,['Memnite'])[0]
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[top].zone=='p1:library'
    assert not any(a.text==leaf.MONK_ABILITY for a in ch(s,s.state.cards[top]).abilities)
    roundtrip(s)


def test_explicit_exile_ability_zone_never_exposes_pt_type_keyword_or_ability_removal_fields(cards):
    from app.rules import layers
    from app.rules.plan import Plan

    s=setup(cards,'Memnite')
    target=put(s,'Memnite','exile')
    plan=Plan.view(s.state,'p1',cards)
    layers.add_effect(plan,affected=[plan.oid(target.id)],layer='6',source=None,controller='p1',
                      add_abilities=[leaf.MONK_ABILITY],ability_zone='exile',duration='permanent',
                      power=99,toughness=99,add_types=('Enchantment',),add_keywords=('flying',),remove_abilities=True)
    now=ch(s,s.state.cards[target.id])
    assert now.pt==(1,1)
    assert now.types==frozenset({'Artifact','Creature'})
    assert 'flying' not in now.keywords
    assert any(a.text==leaf.MONK_ABILITY for a in now.abilities)
    from app.game.state import GameState
    s.state=GameState.model_validate_json(s.state.model_dump_json())
    assert any(a.text==leaf.MONK_ABILITY for a in ch(s,s.state.cards[target.id]).abilities)


def test_narfi_actual_three_chapters_choose_each_graveyard_then_paid_cast_after_saga_sacrifice(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,"King Narfi's Betrayal",'Forest','Memnite')
    old=put(s,'Grizzly Bears','graveyard')
    piles={pid:stack_library(s,['Dragon Whelp','Murder','Forest','Memnite'],pid=pid) for pid in ['p1','p2','p3']}
    source=put(s,"King Narfi's Betrayal",'hand')
    mana(s,C=1,U=1,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    choices=[old.id,piles['p2'][0],piles['p3'][3]]
    for cid in choices:
        d=s.state.rules.decision
        assert d.resume['step']=='exile_outcomes42_narfi'
        assert all(s.state.cards[o.card_id].name!='Murder' for o in d.options)
        answer(s,[next(o.id for o in d.options if o.card_id==cid)])
    assert all(s.state.cards[cid].zone.endswith(':exile') for cid in choices)
    assert s.state.cards[piles['p1'][0]].zone=='p1:graveyard'
    to_phase(s,'main1',turn=4)
    settle(s)
    mana(s,C=4)
    act(s,'p1',type='cast_spell',card_id=choices[1])
    settle(s)
    assert s.state.cards[choices[1]].zone=='p1:battlefield'
    to_phase(s,'main1',turn=7)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    act(s,'p1',type='cast_spell',card_id=choices[2])
    settle(s)
    assert s.state.cards[choices[2]].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('result,limit',[(9,1),(10,2),(20,3)])
def test_wand_actual_native_die_table_exiles_and_shuffles_all_opponents_before_cast_window(cards,monkeypatch,result,limit):
    from tests.test_rules_random_consequences import faces
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Wand of Wonder','Lightning Bolt','Forest')
    source=put(s,'Wand of Wonder','battlefield')
    stack_library(s,['Forest','Dragon Whelp','Lightning Bolt'],pid='p2')
    stack_library(s,['Grizzly Bears','Lightning Bolt'],pid='p3')
    faces(monkeypatch,[result])
    mana(s,C=4)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    exiled=[c for c in s.state.cards.values() if c.zone.endswith(':exile')]
    assert len(exiled)==2 and all(c.name=='Lightning Bolt' for c in exiled)
    assert len([step for step in s.history.actions[-1].r if step['type']=='shuffle'])==2
    assert d.resume['e']['n']==limit,d.resume
    answer(s,[])
    assert s.state.cards[source.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('result,count',[(1,1),(19,2)])
def test_wand_actual_immediate_free_cast_limit_and_sequential_native_stack(cards,monkeypatch,result,count):
    from app.game.errors import ActionError
    from tests.test_rules_random_consequences import faces
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Wand of Wonder','Divination')
    source=put(s,'Wand of Wonder','battlefield')
    stack_library(s,['Divination'],pid='p2')
    stack_library(s,['Divination'],pid='p3')
    faces(monkeypatch,[result])
    mana(s,C=4)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0)
    settle(s)
    ids=[c.id for c in s.state.cards.values() if c.name=='Divination' and c.zone.endswith(':exile')]
    assert len(ids)==2
    before=len(s.state.zones.get('p1:hand',[]))
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==ids[0])])
    if count==2:
        assert s.state.cards[ids[0]].zone=='stack'
        assert len(s.state.zones.get('p1:hand',[]))==before
        d=s.state.rules.decision
        assert d.resume['step']=='free_cast_pick'
        answer(s,[next(o.id for o in d.options if o.card_id==ids[1])])
    else:
        assert s.state.rules.decision is None
        with pytest.raises(ActionError):
            act(s,'p1',type='cast_spell',card_id=ids[1],free=True)
    assert len(s.state.zones.get('p1:hand',[]))==before+2*count
    assert sum(s.state.cards[cid].zone.endswith(':graveyard') for cid in ids)==count
    roundtrip(s)


@pytest.mark.parametrize('natural,direction,limit',[(9,'plus',2),(19,'plus',3),(20,'plus',0),(1,'minus',0)])
def test_wand_uses_actual_native_paid_numeric_modified_kept_result_including_no_table_row(cards,monkeypatch,natural,direction,limit):
    from tests.test_rules_numeric_roll_finalization42 import accept
    from tests.test_rules_random_consequences import faces
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Wand of Wonder','Divination','Night Shift of the Living Dead')
    source=put(s,'Wand of Wonder','battlefield')
    put(s,'Night Shift of the Living Dead','battlefield')
    stack_library(s,['Divination'],pid='p2')
    stack_library(s,['Divination'],pid='p3')
    faces(monkeypatch,[natural])
    mana(s,C=4)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0)
    settle(s)
    accept(s,direction=direction)
    assert s.state.players['p1'].life==39
    assert len([c for c in s.state.cards.values() if c.zone.endswith(':exile') and c.name=='Divination'])==2
    if limit:
        d=s.state.rules.decision
        assert d.resume['step']=='free_cast_pick' and d.resume['e']['n']==limit
        answer(s,[])
    else:
        assert s.state.rules.decision is None
    roundtrip(s)


def test_rivaz_actual_tap_two_colors_restricted_to_dragon_creature_spell_and_survive_mana_source_departure(cards):
    from app.game.errors import ActionError

    s=setup(cards)
    source=put(s,'Rivaz of the Claw','battlefield')
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{T}'))
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=index)
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index)
    d=s.state.rules.decision
    assert all('{C}' not in o.label for o in d.options)
    assert {'{R}{R}','{R}{G}','{G}{G}'} <= {o.label for o in d.options}
    answer(s,[next(o.id for o in d.options if o.label=='{R}{G}')])
    assert sorted(u.sym for u in s.state.players['p1'].mana_units)==['G','R']
    assert all(u.only for u in s.state.players['p1'].mana_units)
    bear=put(s,'Grizzly Bears','hand')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=bear.id)
    old=s.state.rules.object_id(source.id)
    altar=put(s,"Ashnod's Altar",'battlefield')
    act(s,'p1',type='activate_ability',card_id=altar.id,ability=0)
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        answer(s,[next(o.id for o in d.options if o.card_id==source.id)])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    mana(s,R=1)
    dragon=put(s,'Dragon Whelp','hand')
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    settle(s)
    assert s.state.cards[dragon.id].zone=='p1:battlefield'
    assert any(old in p.mana_sources for p in s.state.rules.payments.values() if p.card==dragon.id)
    roundtrip(s)


def test_rivaz_native_graveyard_cast_once_own_turn_resets_and_opponent_turn_is_excluded(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority

    s=setup(cards,'Dragon Whelp')
    put(s,'Rivaz of the Claw','battlefield')
    dragons=[c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Dragon Whelp']
    assert len(dragons)==2
    for c in dragons:
        act(s,'p1',type='move',card_ids=[c.id],to={'player':'p1','zone':'graveyard'})
    mana(s,C=4,R=4)
    act(s,'p1',type='cast_spell',card_id=dragons[0].id)
    settle(s)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragons[1].id)
    to_phase(s,'main1',turn=2)
    wait_priority(s,'p1')
    mana(s,C=2,R=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragons[1].id)
    to_phase(s,'main1',turn=4)
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=dragons[1].id)
    settle(s)
    assert s.state.cards[dragons[1].id].zone=='p1:battlefield'
    roundtrip(s)


def test_rivaz_granted_stack_ability_does_not_exile_countered_spell_or_follow_new_cast_incarnation(cards):
    s=setup(cards,'Counterspell')
    put(s,'Rivaz of the Claw','battlefield')
    dragon=put(s,'Dragon Whelp','graveyard')
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    for _ in range(12):
        if all(entry.kind=='spell' for entry in s.state.rules.stack.values()) and s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert any(a.text=='When this creature dies, exile it.' for a in ch(s,s.state.cards[dragon.id]).abilities)
    counter=put(s,'Counterspell','hand')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=counter.id,targets=[dragon.id])
    settle(s)
    assert s.state.cards[dragon.id].zone=='p1:graveyard'
    assert not any(a.text=='When this creature dies, exile it.' for a in ch(s,s.state.cards[dragon.id]).abilities)
    to_phase(s,'main1',turn=4)
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    settle(s)
    assert len([a for a in ch(s,s.state.cards[dragon.id]).abilities if a.text=='When this creature dies, exile it.'])==1
    roundtrip(s)


def test_rivaz_actual_menace_requires_two_blockers(cards):
    from app.game.errors import ActionError
    from tests.test_rules_banding import block, until_block

    s=setup(cards,'Grizzly Bears')
    source=put(s,'Rivaz of the Claw','battlefield')
    blockers=[c for c in s.state.cards.values() if c.owner=='p2' and c.name=='Grizzly Bears']
    for c in blockers:
        act(s,'p2',type='move',card_ids=[c.id],to={'player':'p2','zone':'battlefield'})
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    until_block(s)
    with pytest.raises(ActionError,match='menace'):
        block(s,[(blockers[0],source)])
    block(s,[(c,source) for c in blockers])
    roundtrip(s)


def test_lifestream_actual_foretell_special_action_privacy_later_alternative_cost_and_exile_life(cards):
    from app.game.errors import ActionError
    from tests.test_rules_linked_exile_look import assert_look

    s=setup(cards)
    put(s,'Grizzly Bears','battlefield')
    source=put(s,"Lifestream's Blessing",'hand')
    mana(s,C=2)
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('Foretell'))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index)
    assert s.state.cards[source.id].zone=='p1:foretell'
    assert_look(s,source.id,['p1'])
    mana(s,C=4,G=1)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id)
    to_phase(s,'main1',turn=4)
    mana(s,C=4,G=1)
    before=len(s.state.zones.get('p1:hand',[]))
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=99)
    assert s.state.rules.stack[source.id].x==2
    record=next(p for p in s.state.rules.payments.values() if p.card==source.id)
    assert record.cast_from=='exile' and record.cast_greatest_power==2
    assert record.mana_spent=={'C':4,'G':1}
    settle(s)
    assert len(s.state.zones.get('p1:hand',[]))==before+2
    assert s.state.players['p1'].life==44
    roundtrip(s)


def test_dance_free_cast_still_requires_actual_additional_discard_cost(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Dance with Calamity','Cathartic Reunion')
    source=put(s,'Dance with Calamity','hand')
    ids=stack_library(s,['Cathartic Reunion'])
    other=[cid for cid in s.state.zones['p1:library'] if cid not in ids]
    act(s,'p1',type='move',card_ids=other,to={'player':'p1','zone':'graveyard'})
    mana(s,C=7,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    answer(s,['yes'])
    # The packet picker cannot waive the actual mandatory discard-two cost.
    from app.game.errors import ActionError
    d=s.state.rules.decision
    option=next(o for o in d.options if o.card_id is not None)
    with pytest.raises(ActionError):
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[option.id])
    answer(s,[])
    assert s.state.rules.decision is None
    assert any(c.name=='Cathartic Reunion' and c.zone=='p1:exile' for c in s.state.cards.values())
    assert s.state.rules.free_cast_then is None
    roundtrip(s)


def test_dance_free_cast_pays_actual_mandatory_discard_two(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Dance with Calamity','Cathartic Reunion')
    source=put(s,'Dance with Calamity','hand')
    discard=[put(s,name,'hand').id for name in ['Dragon Whelp','Murder']]
    ids=stack_library(s,['Cathartic Reunion'])
    other=[cid for cid in s.state.zones['p1:library'] if cid not in ids]
    act(s,'p1',type='move',card_ids=other,to={'player':'p1','zone':'graveyard'})
    mana(s,C=7,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    answer(s,['yes'])
    d=s.state.rules.decision
    option=next(o for o in d.options if o.card_id is not None)
    answer(s,[option.id])
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        answer(s,[o.id for o in d.options if o.card_id in discard])
    settle(s)
    assert all(s.state.cards[cid].zone=='p1:graveyard' for cid in discard)
    assert s.state.cards[option.card_id].zone=='p1:graveyard'
    roundtrip(s)


def test_theorist_native_graveyard_exile_in_response_prevents_later_permission(cards):
    s=setup(cards,'Conspiracy Theorist','Merfolk Looter','Cremate')
    put(s,'Conspiracy Theorist','battlefield')
    looter=put(s,'Merfolk Looter','battlefield')
    dragon=put(s,'Dragon Whelp','hand')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==dragon.id)])
    for _ in range(9):
        if s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    cremate=put(s,'Cremate','hand')
    mana(s,B=1)
    act(s,'p1',type='cast_spell',card_id=cremate.id,targets=[dragon.id])
    settle(s)
    assert s.state.cards[dragon.id].zone=='p1:exile'
    assert s.state.rules.decision is None
    assert not any(p.card==dragon.id for p in s.state.rules.permissions)
    from app.game.errors import ActionError
    mana(s,C=2,R=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon.id)
    roundtrip(s)


def test_theorist_land_discard_does_not_trigger_and_mixed_discard_offers_only_nonland(cards):
    s=setup(cards,'Conspiracy Theorist','Merfolk Looter','Cathartic Reunion','Forest','Forest')
    put(s,'Conspiracy Theorist','battlefield')
    looter=put(s,'Merfolk Looter','battlefield')
    forest=put(s,'Forest','hand')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==forest.id)])
    assert s.state.rules.decision is None and s.state.cards[forest.id].zone=='p1:graveyard'
    dragon=put(s,'Dragon Whelp','hand')
    second=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Forest' and c.id!=forest.id)
    act(s,'p1',type='move',card_ids=[second.id],to={'player':'p1','zone':'hand'})
    reunion=put(s,'Cathartic Reunion','hand')
    mana(s,C=1,R=1)
    act(s,'p1',type='cast_spell',card_id=reunion.id)
    d=s.state.rules.decision
    answer(s,[o.id for o in d.options if o.card_id in {dragon.id,second.id}])
    d=s.state.rules.decision
    assert d.resume['step']=='exile_outcomes42_discard'
    assert {o.card_id for o in d.options}=={dragon.id}
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    assert s.state.cards[second.id].zone=='p1:graveyard'
    assert s.state.cards[dragon.id].zone=='p1:exile'
    roundtrip(s)


def test_intellect_foreign_owned_immediate_cast_preserves_apnap_and_actual_controller_land_authority(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Intellect Devourer','Allure of the Unknown','Forest')
    dragon=put(s,'Dragon Whelp','hand')
    forest=put(s,'Forest','hand','p3')
    top=stack_library(s,['Intellect Devourer'])[0]
    cast(s,'Allure of the Unknown')
    answer(s,['p2'])
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==top)])
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==top)])
    d=s.state.rules.decision
    assert d.player=='p1'
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    d=s.state.rules.decision
    assert d.player=='p3'
    answer(s,[next(o.id for o in d.options if o.card_id==forest.id)])
    assert s.state.cards[top].controller=='p2' and s.state.cards[top].owner=='p1'
    to_phase(s,'main1',turn=2)
    act(s,'p2',type='play_land',card_id=forest.id)
    assert s.state.cards[forest.id].zone=='p2:battlefield'
    roundtrip(s)


def test_intellect_pending_private_hand_choice_rest_websocket_hides_other_hands(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s=setup(cards,'Intellect Devourer','Forest')
    dragon=put(s,'Dragon Whelp','hand','p2')
    put(s,'Forest','hand','p3')
    source=put(s,'Intellect Devourer','hand')
    mana(s,C=3,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.rules.decision.player=='p2'
    with TestClient(create_app(settings)) as client:
        room=client.app.state.services.hub.create_room(s,mode='lan')
        for player,seat in room.seats.items():
            seat.token='intellect42-'+player
        room.spectator_tokens.add('intellect42-spectator')
        for viewer in ['p1','p2','p3','spectator']:
            token='intellect42-'+viewer
            payload=client.get(f'/api/games/{room.id}/view',headers={'X-Seat-Token':token}).json()
            with connect_game(client, room.id, token) as ws:
                frame=ws.receive_json()
            for view in [payload,frame['view']]:
                if viewer=='p2':
                    assert view['cards'].get(dragon.id,{})['name']=='Dragon Whelp'
                else:
                    assert 'name' not in view['cards'].get(dragon.id,{})
                    assert 'card_id' not in view['cards'].get(dragon.id,{})
                    assert 'Dragon Whelp' not in json.dumps(view)
    roundtrip(s)


def test_gale_actual_hand_instant_targets_only_sorcery_and_casts_paid_with_exile_rider(cards):
    s=setup(cards,'Gale, Waterdeep Prodigy','Divination','Lightning Bolt')
    put(s,'Gale, Waterdeep Prodigy','battlefield')
    sorcery=put(s,'Divination','graveyard')
    instant=put(s,'Lightning Bolt','graveyard')
    growth=put(s,'Giant Growth','hand')
    bear=put(s,'Grizzly Bears','battlefield')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    d=s.state.rules.decision
    assert sorcery.id in {o.card_id for o in d.options}
    assert instant.id not in {o.card_id for o in d.options}
    answer(s,[next(o.id for o in d.options if o.card_id==sorcery.id)])
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    mana(s,C=2,U=1)
    answer(s,[next(o.id for o in d.options if o.card_id==sorcery.id)])
    settle(s)
    assert s.state.cards[sorcery.id].zone=='p1:exile'
    assert s.state.cards[instant.id].zone=='p1:graveyard'
    roundtrip(s)


def test_kingpin_actual_nondamage_effect_life_loss_one_each_triggers_once(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Ob Nixilis, Captive Kingpin','Pulse Tracker','Forest')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    tracker=put(s,'Pulse Tracker','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    top=stack_library(s,['Forest'])[0]
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':tracker.id,'target':'p2'}])
    settle(s)
    assert s.state.players['p2'].life==39 and s.state.players['p3'].life==39
    assert s.state.cards[kingpin.id].counters.get('+1/+1')==1
    assert s.state.cards[top].zone=='p1:exile'
    assert len([p for p in s.state.rules.permissions if p.card==top])==1
    roundtrip(s)


@pytest.mark.parametrize('mode',['mixed','sequential'])
def test_kingpin_effect_loss_vector_replacement_and_separate_trigger_instructions(cards,mode):
    from tests.test_rules_bandmate_references import wait_priority
    s=setup(cards,'Ob Nixilis, Captive Kingpin','Pulse Tracker','Pulse Tracker','Bloodletter of Aclazotz',"Bontu's Monument",'Spectral Sailor')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    if mode=='mixed':
        put(s,'Bloodletter of Aclazotz','battlefield','p3')
        put(s,"Bontu's Monument",'battlefield')
        sailor=put(s,'Spectral Sailor','hand')
        to_phase(s,'main1',turn=3)
        wait_priority(s,'p1')
        mana(s,U=1)
        act(s,'p1',type='cast_spell',card_id=sailor.id)
    else:
        trackers=[c.id for c in s.state.cards.values() if c.owner=='p1' and c.name=='Pulse Tracker']
        for cid in trackers:
            act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'battlefield'})
        to_phase(s,'declare_attackers',turn=4)
        act(s,'p1',type='declare_attackers',attackers=[{'card_id':cid,'target':'p2'} for cid in trackers])
    settle(s)
    if mode=='mixed':
        assert s.state.players['p2'].life==38 and s.state.players['p3'].life==39
        assert s.state.cards[kingpin.id].counters.get('+1/+1')==1
    else:
        assert s.state.players['p2'].life==38 and s.state.players['p3'].life==38
        assert s.state.cards[kingpin.id].counters.get('+1/+1')==2
    roundtrip(s)


def test_gale_adventure_hand_spell_uses_actual_instant_face_but_graveyard_adventure_is_creature(cards):
    s=setup(cards,'Gale, Waterdeep Prodigy','Divination','Brazen Borrower // Petty Theft','Fae of Wishes // Granted')
    put(s,'Gale, Waterdeep Prodigy','battlefield')
    divination=put(s,'Divination','graveyard')
    fae=put(s,'Fae of Wishes // Granted','graveyard')
    borrower=put(s,'Brazen Borrower // Petty Theft','hand')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    mana(s,C=1,U=1)
    act(s,'p1',type='cast_spell',card_id=borrower.id,face=1,targets=[bear.id])
    d=s.state.rules.decision
    assert divination.id in {o.card_id for o in d.options}
    assert fae.id not in {o.card_id for o in d.options}
    answer(s,[next(o.id for o in d.options if o.card_id==divination.id)])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[])
    assert s.state.cards[divination.id].zone=='p1:graveyard'
    assert s.state.cards[bear.id].zone=='p2:hand'
    roundtrip(s)


def test_gale_split_card_target_uses_combined_gy_types_and_can_cast_same_type_half(cards):
    s=setup(cards,'Gale, Waterdeep Prodigy','Commit // Memory')
    put(s,'Gale, Waterdeep Prodigy','battlefield')
    split=put(s,'Commit // Memory','graveyard')
    bear=put(s,'Grizzly Bears','battlefield')
    growth=put(s,'Giant Growth','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==split.id)])
    d=s.state.rules.decision
    assert {o.label for o in d.options}=={'Commit','Memory'}
    mana(s,C=3,U=1)
    answer(s,[next(o.id for o in d.options if o.label=='Commit')])
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        answer(s,[next(o.id for o in d.options if o.card_id==bear.id)])
    settle(s)
    assert s.state.cards[split.id].zone=='p1:exile'
    assert s.state.cards[bear.id].zone=='p1:library'
    roundtrip(s)


@pytest.mark.parametrize('mode',['zero','illegal'])
def test_gale_up_to_zero_target_or_native_exile_response_gives_no_cast(cards,mode):
    from tests.test_rules_bandmate_references import wait_priority
    s=setup(cards,'Gale, Waterdeep Prodigy','Divination','Cremate')
    gale=put(s,'Gale, Waterdeep Prodigy','battlefield')
    sorcery=put(s,'Divination','graveyard')
    bear=put(s,'Grizzly Bears','battlefield')
    growth=put(s,'Giant Growth','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    d=s.state.rules.decision
    if mode=='zero':
        answer(s,[])
        assert s.state.cards[sorcery.id].zone=='p1:graveyard'
    else:
        act(s,'p1',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==sorcery.id)])
        wait_priority(s,'p2')
        cremate=put(s,'Cremate','hand','p2')
        mana(s,'p2',B=1)
        act(s,'p2',type='cast_spell',card_id=cremate.id,targets=[sorcery.id])
        settle(s)
        assert s.state.cards[sorcery.id].zone=='p1:exile'
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    assert not any(e.kind=='trigger' and e.source_card==gale.id for e in s.state.rules.stack.values())
    roundtrip(s)


def test_gale_real_foretold_exile_spell_does_not_trigger_hand_only_ability(cards):
    s=setup(cards,'Gale, Waterdeep Prodigy','Lightning Bolt')
    gale=put(s,'Gale, Waterdeep Prodigy','battlefield')
    put(s,'Lightning Bolt','graveyard')
    source=put(s,"Lifestream's Blessing",'hand')
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=next(a.index for a in ch(s,source).abilities if a.text.startswith('Foretell')))
    to_phase(s,'main1',turn=4)
    mana(s,C=4,G=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    assert not any(e.kind=='trigger' and e.source_card==gale.id for e in s.state.rules.stack.values())
    settle(s)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_gale_trigger_can_be_countered_without_graveyard_cast_authority(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s=setup(cards,'Gale, Waterdeep Prodigy','Divination','Stifle')
    gale=put(s,'Gale, Waterdeep Prodigy','battlefield')
    sorcery=put(s,'Divination','graveyard')
    bear=put(s,'Grizzly Bears','battlefield')
    growth=put(s,'Giant Growth','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    d=s.state.rules.decision
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==sorcery.id)])
    trigger=next(k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_card==gale.id)
    wait_priority(s,'p2')
    stifle=put(s,'Stifle','hand','p2')
    mana(s,'p2',U=1)
    act(s,'p2',type='cast_spell',card_id=stifle.id,targets=[trigger])
    settle(s)
    assert s.state.cards[sorcery.id].zone=='p1:graveyard'
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    assert not s.state.rules.permissions
    roundtrip(s)


def test_gale_paid_immediate_cast_pays_mana_and_actual_additional_discard(cards):
    s=setup(cards,'Gale, Waterdeep Prodigy','Cathartic Reunion')
    put(s,'Gale, Waterdeep Prodigy','battlefield')
    reunion=put(s,'Cathartic Reunion','graveyard')
    bear=put(s,'Grizzly Bears','battlefield')
    growth=put(s,'Giant Growth','hand')
    discard=[put(s,n,'hand').id for n in ['Dragon Whelp','Murder']]
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==reunion.id)])
    d=s.state.rules.decision
    mana(s,C=1,R=1)
    answer(s,[next(o.id for o in d.options if o.card_id==reunion.id)])
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        answer(s,[o.id for o in d.options if o.card_id in discard])
    settle(s)
    assert all(s.state.cards[cid].zone=='p1:graveyard' for cid in discard)
    assert s.state.cards[reunion.id].zone=='p1:exile'
    roundtrip(s)


def test_gale_official_choose_background_configuration_accepts_background_and_rejects_unpaired_creature(cards):
    from app.rules import commander
    gale=cards.resolve('Gale, Waterdeep Prodigy')
    background=cards.resolve('Candlekeep Sage')
    other=cards.resolve('Rivaz of the Claw')
    assert commander.configuration_problems([gale,background])==[]
    assert commander.pair_problem(gale,background) is None
    assert commander.pair_problem(gale,other) is not None


@pytest.mark.parametrize('mode',['counter','sourcegone'])
def test_gale_original_controller_paid_cast_rider_survives_source_or_countered_spell(cards,mode):
    from tests.test_rules_bandmate_references import wait_priority
    s=setup(cards,'Gale, Waterdeep Prodigy','Divination','Counterspell')
    gale=put(s,'Gale, Waterdeep Prodigy','battlefield')
    sorcery=put(s,'Divination','graveyard')
    bear=put(s,'Grizzly Bears','battlefield')
    growth=put(s,'Giant Growth','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    d=s.state.rules.decision
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==sorcery.id)])
    if mode=='sourcegone':
        wait_priority(s,'p2')
        murder=put(s,'Murder','hand','p2')
        mana(s,'p2',C=1,B=2)
        act(s,'p2',type='cast_spell',card_id=murder.id,targets=[gale.id])
    settle(s)
    d=s.state.rules.decision
    assert d.player=='p1' and d.resume['step']=='free_cast_pick'
    mana(s,C=2,U=1)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==sorcery.id)])
    if mode=='counter':
        wait_priority(s,'p2')
        counter=put(s,'Counterspell','hand','p2')
        mana(s,'p2',U=2)
        act(s,'p2',type='cast_spell',card_id=counter.id,targets=[sorcery.id])
    settle(s)
    assert s.state.cards[sorcery.id].zone=='p1:exile'
    if mode=='sourcegone':
        assert s.state.cards[gale.id].zone=='p1:graveyard'
    roundtrip(s)


def test_wand_no_instant_sorcery_library_returns_all_cards_and_empty_library_offers_nothing(cards,monkeypatch):
    from tests.test_rules_random_consequences import faces
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Wand of Wonder','Forest','Brazen Borrower // Petty Theft')
    source=put(s,'Wand of Wonder','battlefield')
    keep=stack_library(s,['Forest','Brazen Borrower // Petty Theft'],pid='p2')
    for pid in ['p2','p3']:
        others=[cid for cid in s.state.zones[pid+':library'] if pid=='p3' or cid not in keep]
        act(s,'p1',type='move',card_ids=others,to={'player':pid,'zone':'graveyard'})
    faces(monkeypatch,[20])
    mana(s,C=4)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0)
    settle(s)
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    assert not any(c.zone.endswith(':exile') for c in s.state.cards.values())
    assert sorted(s.state.cards[cid].name for cid in s.state.zones['p2:library'])==['Brazen Borrower // Petty Theft','Forest']
    assert not s.state.zones['p3:library']
    roundtrip(s)


def test_kingpin_original_simultaneous_gain_vector_replaced_to_loss_is_one_cohort(cards):
    s=setup(cards,'Ob Nixilis, Captive Kingpin','Triskaidekaphobia','Tainted Remedy')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    put(s,'Triskaidekaphobia','battlefield')
    put(s,'Tainted Remedy','battlefield')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    d=s.state.rules.decision
    option=next(o for o in d.options if 'gains 1 life' in o.label.lower())
    answer(s,[option.id])
    assert s.state.players['p1'].life==41, s.state.rules.decision
    assert s.state.players['p2'].life==39 and s.state.players['p3'].life==39
    assert s.state.cards[kingpin.id].counters.get('+1/+1')==1
    roundtrip(s)


@pytest.mark.parametrize('mode',['gain','lose'])
@pytest.mark.parametrize('loser',[None,'p2','p1'])
def test_triskaidekaphobia_actual_upkeep_both_modes_explicit_all_players_after_elimination(cards,mode,loser):
    s=setup(cards,'Triskaidekaphobia')
    put(s,'Triskaidekaphobia','battlefield')
    if loser is not None:
        act(s,'p1',type='set_life',player=loser,value=13)
    to_phase(s,'upkeep',turn=4)
    settle(s)
    d=s.state.rules.decision
    text='gains 1 life' if mode=='gain' else 'loses 1 life'
    answer(s,[next(o.id for o in d.options if text in o.label.lower())])
    for player in ['p1','p2','p3']:
        if player==loser:
            assert player in s.state.rules.lost
        else:
            assert player not in s.state.rules.lost
            assert s.state.players[player].life==(41 if mode=='gain' else 39)
    roundtrip(s)


@pytest.mark.parametrize('phase,turn',[('main1',1),('declare_attackers',4),('main1',2)])
def test_tinybones_real_activation_rejects_sickness_combat_and_opponent_turn_without_costs(cards,phase,turn):
    from app.game.errors import ActionError
    s=setup(cards,'Tinybones, Bauble Burglar')
    source=put(s,'Tinybones, Bauble Burglar','battlefield')
    to_phase(s,phase,turn=turn)
    mana(s,C=3,B=1)
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{3}'))
    before=dict(s.state.players['p1'].mana)
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=index)
    assert not s.state.cards[source.id].tapped and s.state.players['p1'].mana==before
    roundtrip(s)


def test_tinybones_actual_control_magic_moves_current_foreign_stash_authority_to_new_controller(cards):
    from app.game.errors import ActionError
    s=setup(cards,'Tinybones, Bauble Burglar','Control Magic','Forest')
    source=put(s,'Tinybones, Bauble Burglar','battlefield')
    forest=put(s,'Forest','hand','p2')
    dragon=put(s,'Dragon Whelp','hand','p3')
    to_phase(s,'main1',turn=4)
    mana(s,C=3,B=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=next(a.index for a in ch(s,source).abilities if a.text.startswith('{3}')))
    settle(s)
    for cid in [forest.id,dragon.id]:
        d=s.state.rules.decision
        answer(s,[next(o.id for o in d.options if o.card_id==cid)])
    to_phase(s,'main1',turn=5)
    control=put(s,'Control Magic','hand','p2')
    mana(s,'p2',C=2,U=2)
    act(s,'p2',type='cast_spell',card_id=control.id,targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].controller=='p2'
    mana(s,'p2',G=4)
    act(s,'p2',type='cast_spell',card_id=dragon.id)
    settle(s)
    assert s.state.cards[dragon.id].zone=='p2:battlefield'
    to_phase(s,'main1',turn=7)
    with pytest.raises(ActionError):
        act(s,'p1',type='play_land',card_id=forest.id)
    roundtrip(s)


def test_grolnok_actual_opponents_library_mill_and_croak_cards_do_not_grant_foreign_authority(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Grolnok, the Omnivore','Forest','Memnite')
    put(s,'Grolnok, the Omnivore','battlefield')
    other=put(s,'Grolnok, the Omnivore','battlefield','p2')
    to_phase(s,'declare_attackers',turn=2)
    top=stack_library(s,['Forest','Memnite','Murder'],pid='p2')
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':other.id,'target':'p3'}])
    settle(s)
    assert all(s.state.cards[cid].counters.get('croak')==1 for cid in top[:2])
    to_phase(s,'main1',turn=4)
    for verb,cid in [('play_land',top[0]),('cast_spell',top[1])]:
        with pytest.raises(ActionError):
            act(s,'p1',type=verb,card_id=cid)
    to_phase(s,'main1',turn=5)
    act(s,'p2',type='cast_spell',card_id=top[1])
    settle(s)
    assert s.state.cards[top[1]].zone=='p2:battlefield'
    roundtrip(s)


def test_grolnok_actual_rest_in_peace_mill_exiles_have_no_croak_authority(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Grolnok, the Omnivore','Forest','Memnite','Rest in Peace')
    source=put(s,'Grolnok, the Omnivore','battlefield')
    put(s,'Rest in Peace','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    top=stack_library(s,['Forest','Memnite','Murder'])
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    assert all(s.state.cards[cid].zone=='p1:exile' and not s.state.cards[cid].counters.get('croak') for cid in top)
    to_phase(s,'main2',turn=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='play_land',card_id=top[0])
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=top[1])
    roundtrip(s)


def test_grolnok_cannot_use_actual_stash_counter_card_instead_of_croak(cards):
    from app.game.errors import ActionError
    s=setup(cards,'Grolnok, the Omnivore','Tinybones, Bauble Burglar','Merfolk Looter')
    put(s,'Grolnok, the Omnivore','battlefield')
    put(s,'Tinybones, Bauble Burglar','battlefield','p2')
    looter=put(s,'Merfolk Looter','battlefield')
    dragon=put(s,'Dragon Whelp','hand')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=looter.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    assert s.state.cards[dragon.id].zone=='p1:exile' and s.state.cards[dragon.id].counters.get('stash')==1
    assert not s.state.cards[dragon.id].counters.get('croak')
    mana(s,C=2,R=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon.id)
    roundtrip(s)


def test_ruinous_staged_actual_random_upkeep_paid_foreign_spell_queues_owner_mv_loss(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'The Ruinous Powers')
    source=put(s,'The Ruinous Powers','battlefield')
    to_phase(s,'main2',turn=3)
    stack_library(s,['Dragon Whelp'],pid='p2')
    stack_library(s,['Dragon Whelp'],pid='p3')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    permission=next(p for p in s.state.rules.permissions if p.use_trigger is not None)
    dragon=s.state.cards[permission.card]
    assert dragon.zone==dragon.owner+':exile' and dragon.owner in {'p2','p3'}
    assert permission.use_trigger.source.object_id==s.state.rules.object_id(source.id)
    to_phase(s,'main1',turn=4)
    mana(s,W=4)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    assert any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values())
    settle(s)
    assert s.state.players[dragon.owner].life==36
    assert s.state.players['p3' if dragon.owner=='p2' else 'p2'].life==40
    assert s.state.cards[dragon.id].zone=='p1:battlefield'
    roundtrip(s)


def test_share_staged_actual_etb_foreign_land_shared_spell_limit_and_refill_trigger(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Share the Spoils','Forest')
    forest=stack_library(s,['Forest'],pid='p2')[0]
    dragon=stack_library(s,['Dragon Whelp'],pid='p3')[0]
    own=stack_library(s,['Grizzly Bears'])[0]
    source=put(s,'Share the Spoils','hand')
    mana(s,C=1,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert all(s.state.cards[cid].zone.endswith(':exile') for cid in [forest,dragon,own])
    next_card=stack_library(s,['Murder'])[0]
    act(s,'p1',type='play_land',card_id=forest)
    assert any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values())
    settle(s)
    assert s.state.cards[next_card].zone=='p1:exile'
    mana(s,C=2,R=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon)
    roundtrip(s)


@pytest.mark.parametrize('before',[True,False])
def test_lobelia_actual_source_departure_activation_keeps_one_land_or_spell_packet_this_turn(cards,before):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Lobelia, Defender of Bag End','Forest','Memnite')
    to_phase(s,'main1',turn=4)
    forest=stack_library(s,['Forest'],pid='p2')[0]
    dragon=stack_library(s,['Dragon Whelp'],pid='p3')[0]
    source=put(s,'Lobelia, Defender of Bag End','hand')
    mana(s,C=2,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    forest=next(c.id for c in s.state.cards.values() if c.owner=='p2' and c.name=='Forest' and c.zone=='p2:exile')
    dragon=next(c.id for c in s.state.cards.values() if c.owner=='p3' and c.name=='Dragon Whelp' and c.zone=='p3:exile')
    to_phase(s,'main1',turn=7)
    put(s,'Memnite','battlefield')
    act(s,'p1',type='activate_ability',card_id=source.id,
        ability=next(a.index for a in ch(s,source).abilities if a.text.startswith('{T}')),modes=[0])
    if not before:
        settle(s)
    murder=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=murder.id,targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    act(s,'p1',type='play_land',card_id=forest)
    assert s.state.cards[forest].zone=='p1:battlefield'
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon,free=True)
    roundtrip(s)


@pytest.mark.parametrize('concede',[False,True])
@pytest.mark.parametrize('borrowed',[False,True])
def test_share_current_cr_borrowed_owner_life_zero_and_concession_both_look_back(cards,concede,borrowed):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Share the Spoils','Confiscate','Memnite','Lightning Bolt')
    player='p2' if borrowed else 'p1'
    to_phase(s,'main1',turn=2 if borrowed else 1)
    source=put(s,'Share the Spoils','hand',player)
    mana(s,player,C=1,R=1)
    act(s,player,type='cast_spell',card_id=source.id)
    settle(s)
    to_phase(s,'main1',turn=4)
    if borrowed:
        confiscate=put(s,'Confiscate','hand')
        mana(s,C=4,U=2)
        act(s,'p1',type='cast_spell',card_id=confiscate.id,targets=[source.id])
        settle(s)
    assert s.state.cards[source.id].controller=='p1' and s.state.cards[source.id].owner==player
    tops=[stack_library(s,['Memnite'])[0],stack_library(s,['Dragon Whelp'],pid='p3')[0]]
    if concede:
        act(s,'p2',type='concede')
    else:
        act(s,'p1',type='set_life',player='p2',value=3)
        bolt=put(s,'Lightning Bolt','hand')
        mana(s,R=1)
        act(s,'p1',type='cast_spell',card_id=bolt.id,targets=['p2'])
    settle(s)
    assert 'p2' in (s.state.rules.conceded if concede else s.state.rules.lost)
    # 603.9: a "loses the game" trigger triggers when a player loses or leaves the game, and 603.10f looks back to just
    # before that event, so a Share the Spoils the loser owns still triggers for its controller even when a concession
    # takes it away as the player leaves (104.3a, 800.4a). (The 2021-07-23 ruling that it won't predates 603.10f.)
    assert all(s.state.cards[cid].zone.endswith(':exile') for cid in tops)
    roundtrip(s)


def ruinous_ready(s, name="Dragon Whelp"):
    from tests.test_rules_refused_look import stack_library
    source=put(s,'The Ruinous Powers','battlefield')
    to_phase(s,'main2',turn=3)
    stack_library(s,[name],pid='p2')
    stack_library(s,[name],pid='p3')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    permission=next(p for p in s.state.rules.permissions if p.use_trigger is not None)
    to_phase(s,'main1',turn=4)
    return source,permission.card


@pytest.mark.parametrize('rider',[False,True])
def test_native_competing_unlimited_authorities_only_selected_receipt_queues_owner_loss(cards,rider):
    import random

    from app.game.session import GameSession
    from app.rules import context, permissions
    from app.rules.plan import Plan
    s=setup(cards,'The Ruinous Powers')
    source,cid=ruinous_ready(s)
    owner=s.state.cards[cid].owner
    plan=Plan(s.state,'p1',cards,random.Random(44))
    ctx={'controller':'p1','source_card':source.id,'source_object':plan.oid(source.id),'name':'Other native authority'}
    context.bind_objects(plan,ctx,'other',[cid])
    permissions.grant_play(plan,ctx,{'who':'ref:other','from_exile':True,'play':False,'cast':True,
                                   'until':'end_of_turn','spend':'color'})
    s=GameSession(plan.state,cards=cards)
    mana(s,W=4)
    act(s,'p1',type='cast_spell',card_id=cid)
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='slot'
    option=next(o for o in d.options if ('The Ruinous Powers' in o.label)==rider)
    answer(s,[option.id])
    assert s.state.cards[cid].zone=='p1:battlefield'
    assert s.state.players[owner].life==(36 if rider else 40)
    roundtrip(s)


def test_ruinous_native_cost_cancellation_has_no_use_trigger_and_keeps_exact_authority(cards):
    s=setup(cards,'The Ruinous Powers')
    source,cid=ruinous_ready(s)
    owner=s.state.cards[cid].owner
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='cast_spell',card_id=cid)
    d=s.state.rules.decision
    assert d.resume['step']=='pay_mana'
    assert not any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values())
    answer(s,['cancel'])
    assert s.state.cards[cid].zone==owner+':exile'
    assert s.state.players[owner].life==40
    assert any(p.card==cid and p.use_trigger is not None for p in s.state.rules.permissions)
    mana(s,W=4)
    act(s,'p1',type='cast_spell',card_id=cid)
    d=s.state.rules.decision
    if d is not None:
        answer(s,['pay'])
    settle(s)
    assert s.state.players[owner].life==36 and s.state.cards[cid].zone=='p1:battlefield'
    roundtrip(s)


def test_narfi_optional_each_graveyard_choice_can_decline_every_card(cards):
    s=setup(cards,"King Narfi's Betrayal")
    source=put(s,"King Narfi's Betrayal",'hand')
    mana(s,C=1,U=1,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    for _ in range(3):
        d=s.state.rules.decision
        assert d.resume['step']=='exile_outcomes42_narfi' and d.min_choices==0 and d.max_choices==1
        answer(s,[])
    assert s.state.rules.decision is None
    assert not any(c.zone.endswith(':exile') for c in s.state.cards.values())
    to_phase(s,'main1',turn=4)
    settle(s)
    assert not s.state.rules.permissions
    roundtrip(s)


def test_narfi_blink_old_chapter_grants_old_packet_only_this_turn_new_source_has_no_old_link(cards):
    from app.game.errors import ActionError
    s=setup(cards,"King Narfi's Betrayal",'Flicker of Fate','Memnite','Forest')
    dragon=put(s,'Dragon Whelp','graveyard','p2')
    source=put(s,"King Narfi's Betrayal",'hand')
    mana(s,C=1,U=1,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    answer(s,[])
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==dragon.id)])
    answer(s,[])
    old=s.state.rules.object_id(source.id)
    assert s.state.cards[dragon.id].zone=='p2:exile'
    to_phase(s,'main1',turn=4)
    assert any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values())
    flicker=put(s,'Flicker of Fate','hand')
    mana(s,C=1,W=1)
    act(s,'p1',type='cast_spell',card_id=flicker.id,targets=[source.id])
    settle(s)
    assert s.state.rules.object_id(source.id)!=old
    for _ in range(3):
        d=s.state.rules.decision
        assert d.resume['step']=='exile_outcomes42_narfi'
        answer(s,[])
    assert any(p.card==dragon.id for p in s.state.rules.permissions)
    to_phase(s,'main1',turn=5)
    assert not any(p.card==dragon.id for p in s.state.rules.permissions)
    to_phase(s,'main1',turn=7)
    settle(s)
    mana(s,C=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon.id)
    roundtrip(s)


def test_lobelia_unused_free_packet_expires_and_sick_activation_does_not_sacrifice(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Lobelia, Defender of Bag End','Memnite')
    stack_library(s,['Dragon Whelp'],pid='p2')
    source=put(s,'Lobelia, Defender of Bag End','hand')
    mana(s,C=2,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    artifact=put(s,'Memnite','battlefield')
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{T}'))
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=index,modes=[0])
    assert s.state.cards[artifact.id].zone=='p1:battlefield' and not s.state.cards[source.id].tapped
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,modes=[0])
    settle(s)
    dragon=next(c.id for c in s.state.cards.values() if c.owner=='p2' and c.name=='Dragon Whelp' and c.zone=='p2:exile')
    to_phase(s,'main1',turn=7)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=dragon,free=True)
    assert s.state.cards[dragon].zone=='p2:exile'


def test_ruinous_actual_x_spell_uses_announced_stack_value_and_copy_does_not_consume(cards):
    s=setup(cards,'The Ruinous Powers','Earthquake','Twincast')
    source,cid=ruinous_ready(s,'Earthquake')
    owner=s.state.cards[cid].owner
    mana(s,W=3)
    act(s,'p1',type='cast_spell',card_id=cid,x_value=2)
    triggers=[e for e in s.state.rules.stack.values() if e.kind=='trigger' and e.source_card==source.id]
    assert len(triggers)==1
    assert s.state.players[owner].life==40
    copy=put(s,'Twincast','hand')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=copy.id,targets=[cid])
    settle(s)
    assert s.state.players[owner].life==33  # real cast MV3, two Earthquakes damage2 each
    assert s.state.players['p1'].life==36
    roundtrip(s)


def test_ruinous_actual_land_play_never_queues_cast_receipt_and_permission_expires(cards):
    from app.game.errors import ActionError
    s=setup(cards,'The Ruinous Powers','Forest')
    source,cid=ruinous_ready(s,'Forest')
    act(s,'p1',type='play_land',card_id=cid)
    assert s.state.cards[cid].zone=='p1:battlefield'
    assert not any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values())
    assert all(p.life==40 for p in s.state.players.values())
    to_phase(s,'main2',turn=6)
    from tests.test_rules_refused_look import stack_library
    stack_library(s,['Dragon Whelp'],pid='p2')
    stack_library(s,['Dragon Whelp'],pid='p3')
    to_phase(s,'upkeep',turn=7)
    settle(s)
    permission=next(p for p in s.state.rules.permissions if p.use_trigger is not None)
    to_phase(s,'main1',turn=8)
    mana(s,C=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=permission.card)


@pytest.mark.parametrize('countered',[False,True])
def test_quintorius_actual_endstep_spirit_cost_free_cast_spell_bottom_on_resolve_or_counter(cards,countered):
    s=setup(cards,'Quintorius, Loremaster','Counterspell')
    source=put(s,'Quintorius, Loremaster','battlefield')
    spell=put(s,'Giant Growth','graveyard')
    bear=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'end',turn=1)
    d=s.state.rules.decision
    assert d is not None
    answer(s,[next(o.id for o in d.options if o.card_id==spell.id)])
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:exile'
    spirit=next(c for c in s.state.cards.values() if c.is_token and 'Spirit' in ch(s,c).subtypes)
    assert (int(ch(s,spirit).power),int(ch(s,spirit).toughness))==(3,2)
    assert set(ch(s,spirit).colors)=={'R','W'}
    to_phase(s,'main1',turn=4)
    mana(s,C=1,R=1,W=1)
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{1}'))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=[spell.id])
    settle(s)
    assert spirit.id not in s.state.cards
    assert any(p.card==spell.id and p.free for p in s.state.rules.permissions), (s.state.rules.permissions, scripts.definitions(ch(s,source)))
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='cast_spell',card_id=spell.id,free=True,targets=[bear.id])
    oid=s.state.rules.object_id(spell.id)
    assert oid in s.state.rules.bottom_if_graveyard
    if countered:
        counter=put(s,'Counterspell','hand')
        mana(s,U=2)
        act(s,'p1',type='cast_spell',card_id=counter.id,targets=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:library'
    assert s.state.zones['p1:library'][-1]==spell.id
    assert oid not in s.state.rules.bottom_if_graveyard
    assert ch(s,bear).pt==((2,2) if countered else (5,5))


def test_ruinous_actual_source_blink_preserves_original_receipt_and_countered_spell_owner_loss(cards):
    s=setup(cards,'The Ruinous Powers','Flicker of Fate','Counterspell')
    source,cid=ruinous_ready(s)
    owner=s.state.cards[cid].owner
    old=s.state.rules.object_id(source.id)
    blink=put(s,'Flicker of Fate','hand')
    mana(s,C=1,W=1)
    act(s,'p1',type='cast_spell',card_id=blink.id,targets=[source.id])
    settle(s)
    assert s.state.rules.object_id(source.id)!=old
    mana(s,W=4)
    act(s,'p1',type='cast_spell',card_id=cid)
    trigger=next(e for e in s.state.rules.stack.values() if e.kind=='trigger' and e.source_card==source.id)
    assert trigger.source_object==old
    counter=put(s,'Counterspell','hand')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=counter.id,targets=[cid])
    settle(s)
    assert s.state.cards[cid].zone==owner+':graveyard'
    assert s.state.players[owner].life==36


def test_ruinous_empty_selected_library_grants_no_card_or_owner_loss(cards):
    s=setup(cards,'The Ruinous Powers')
    source=put(s,'The Ruinous Powers','battlefield')
    to_phase(s,'main2',turn=3)
    for player in ('p2','p3'):
        act(s,'p1',type='move',card_ids=list(s.state.zones[player+':library']),to={'player':player,'zone':'graveyard'})
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert not s.state.rules.permissions
    assert not any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values())
    assert all(p.life==40 for p in s.state.players.values())


def quintorius_ready(s,name='Giant Growth'):
    source=put(s,'Quintorius, Loremaster','battlefield')
    spell=put(s,name,'graveyard')
    to_phase(s,'end',turn=1)
    d=s.state.rules.decision
    answer(s,[next(o.id for o in d.options if o.card_id==spell.id)])
    to_phase(s,'main1',turn=4)
    return source,spell


def quintorius_activate(s,source,spell):
    mana(s,C=1,R=1,W=1)
    index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{1}'))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=[spell.id])
    settle(s)


@pytest.mark.parametrize('bottom',[False,True])
def test_quintorius_actual_spell_bottom_and_rest_in_peace_native_616_orders(cards,bottom):
    s=setup(cards,'Quintorius, Loremaster','Rest in Peace')
    source,spell=quintorius_ready(s)
    bear=put(s,'Grizzly Bears','battlefield')
    quintorius_activate(s,source,spell)
    put(s,'Rest in Peace','battlefield')
    act(s,'p1',type='cast_spell',card_id=spell.id,free=True,targets=[bear.id])
    oid=s.state.rules.object_id(spell.id)
    settle(s)
    d=s.state.rules.decision
    assert d.resume['step']=='zone_replace_order'
    assert oid in s.state.rules.bottom_if_graveyard
    answer(s,[next(o.id for o in d.options if ('bottom' in o.label.lower())==bottom)])
    assert s.state.cards[spell.id].zone==('p1:library' if bottom else 'p1:exile')
    assert oid not in s.state.rules.bottom_if_graveyard


def test_quintorius_actual_permanent_enters_and_later_destroyed_normally_without_old_spell_receipt(cards):
    s=setup(cards,'Quintorius, Loremaster','Disenchant')
    source,spell=quintorius_ready(s,"Ashnod's Altar")
    quintorius_activate(s,source,spell)
    act(s,'p1',type='cast_spell',card_id=spell.id,free=True)
    oid=s.state.rules.object_id(spell.id)
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert oid not in s.state.rules.bottom_if_graveyard
    removal=put(s,'Disenchant','hand')
    mana(s,C=1,W=1)
    act(s,'p1',type='cast_spell',card_id=removal.id,targets=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:graveyard'


def test_quintorius_actual_memory_lapse_custom_counter_destination_bypasses_bottom_and_cleans_receipt(cards):
    s=setup(cards,'Quintorius, Loremaster','Memory Lapse')
    source,spell=quintorius_ready(s)
    bear=put(s,'Grizzly Bears','battlefield')
    quintorius_activate(s,source,spell)
    act(s,'p1',type='cast_spell',card_id=spell.id,free=True,targets=[bear.id])
    oid=s.state.rules.object_id(spell.id)
    counter=put(s,'Memory Lapse','hand')
    mana(s,C=1,U=1)
    act(s,'p1',type='cast_spell',card_id=counter.id,targets=[spell.id])
    settle(s)
    assert s.state.zones['p1:library'][0]==spell.id
    assert oid not in s.state.rules.bottom_if_graveyard


def share_ready(s,name='Dragon Whelp'):
    from tests.test_rules_refused_look import stack_library
    cards=[stack_library(s,[name],pid=p)[0] for p in ('p1','p2','p3')]
    source=put(s,'Share the Spoils','hand')
    mana(s,C=1,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    return source,cards


def test_share_actual_each_active_player_one_total_use_and_next_turn_reset(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Share the Spoils','Memnite')
    source,packet=share_ready(s)
    own=stack_library(s,['Memnite'])[0]
    mana(s,W=4)
    act(s,'p1',type='cast_spell',card_id=packet[1])
    settle(s)
    assert s.state.cards[own].zone=='p1:exile'
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=own)
    to_phase(s,'main1',turn=2)
    next_card=stack_library(s,['Memnite'],pid='p2')[0]
    mana(s,'p2',W=4)
    act(s,'p2',type='cast_spell',card_id=packet[2])
    settle(s)
    assert s.state.cards[next_card].zone=='p2:exile'
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=next_card)
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='cast_spell',card_id=own)
    settle(s)
    assert s.state.cards[own].zone=='p1:battlefield'
    assert s.state.cards[source.id].zone=='p1:battlefield'


def test_share_actual_refill_from_old_source_survives_departure_but_no_old_packet_authority(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Share the Spoils','Disenchant','Memnite')
    source,packet=share_ready(s,'Giant Growth')
    bear=put(s,'Grizzly Bears','battlefield')
    refill=stack_library(s,['Memnite'])[0]
    mana(s,W=1)
    act(s,'p1',type='cast_spell',card_id=packet[1],targets=[bear.id])
    assert any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values())
    removal=put(s,'Disenchant','hand')
    mana(s,C=1,W=1)
    act(s,'p1',type='cast_spell',card_id=removal.id,targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[refill].zone=='p1:exile'
    assert ch(s,bear).pt==(5,5)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=refill)


def test_share_actual_cost_cancel_does_not_consume_shared_limit_or_queue_refill(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Share the Spoils','Memnite')
    source,packet=share_ready(s)
    refill=stack_library(s,['Memnite'])[0]
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='cast_spell',card_id=packet[1])
    d=s.state.rules.decision
    assert d.resume['step']=='pay_mana'
    answer(s,['cancel'])
    assert s.state.cards[refill].zone=='p1:library'
    assert not any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values())
    mana(s,W=4)
    act(s,'p1',type='cast_spell',card_id=packet[2])
    settle(s)
    assert s.state.cards[refill].zone=='p1:exile'


def test_mara_actual_apnap_first_freecast_fully_commits_before_next_opponents_choice(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Ensnared by the Mara','Forest','Memnite')
    first=stack_library(s,['Forest','Dragon Whelp'],pid='p2')
    second=stack_library(s,['Dragon Whelp','Memnite','Forest','Giant Growth'],pid='p3')
    source=put(s,'Ensnared by the Mara','hand')
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    assert d.player=='p2' and d.resume['step']=='exile_outcomes44_mara'
    answer(s,['cast'])
    d=s.state.rules.decision
    assert d.player=='p1' and d.resume['step']=='free_cast_pick'
    assert s.state.cards[first[0]].zone=='p2:exile' and s.state.cards[first[1]].zone=='p2:exile'
    assert all(s.state.cards[cid].zone=='p3:library' for cid in second)
    answer(s,[next(o.id for o in d.options if o.card_id==first[1])])
    d=s.state.rules.decision
    assert d.player=='p3' and d.resume['step']=='exile_outcomes44_mara'
    assert s.state.cards[first[1]].zone=='stack'
    answer(s,['damage'])
    assert all(s.state.cards[cid].zone=='p3:exile' for cid in second)
    assert s.state.players['p3'].life==35
    assert s.state.cards[first[1]].zone=='p1:battlefield'


def test_share_actual_spell_copy_refills_once_and_blinked_source_new_scope_has_fresh_use(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Share the Spoils','Flicker of Fate','Forest','Memnite')
    source,packet=share_ready(s,'Giant Growth')
    bear=put(s,'Grizzly Bears','battlefield')
    refill,following=stack_library(s,['Memnite','Forest'])
    mana(s,W=1)
    act(s,'p1',type='cast_spell',card_id=packet[1],targets=[bear.id])
    copy=put(s,'Twincast','hand')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=copy.id,targets=[packet[1]])
    settle(s)
    assert ch(s,bear).pt==(8,8)
    assert s.state.cards[refill].zone=='p1:exile' and s.state.cards[following].zone=='p1:library'
    old=s.state.rules.object_id(source.id)
    fresh_card=stack_library(s,['Memnite'],pid='p2')[0]
    blink=put(s,'Flicker of Fate','hand')
    mana(s,C=1,W=1)
    act(s,'p1',type='cast_spell',card_id=blink.id,targets=[source.id])
    settle(s)
    assert s.state.rules.object_id(source.id)!=old
    assert s.state.cards[fresh_card].zone=='p2:exile'
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=refill)
    act(s,'p1',type='cast_spell',card_id=fresh_card)
    settle(s)
    assert s.state.cards[fresh_card].zone=='p1:battlefield'


def test_quintorius_actual_endstep_target_filter_and_illegal_target_creates_no_spirit_or_link(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s=setup(cards,'Quintorius, Loremaster','Cremate','Forest')
    source=put(s,'Quintorius, Loremaster','battlefield')
    spell=put(s,'Giant Growth','graveyard')
    put(s,'Grizzly Bears','graveyard')
    put(s,'Forest','graveyard')
    put(s,'Murder','graveyard','p2')
    to_phase(s,'end',turn=1)
    d=s.state.rules.decision
    assert {o.card_id for o in d.options}=={spell.id}
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==spell.id)])
    wait_priority(s,'p2')
    response=put(s,'Cremate','hand','p2')
    mana(s,'p2',B=1)
    act(s,'p2',type='cast_spell',card_id=response.id,targets=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:exile'
    assert not any(c.is_token and 'Spirit' in ch(s,c).subtypes for c in s.state.cards.values())
    from app.rules import exiled_with
    from app.rules.plan import Plan
    assert exiled_with.cards(Plan(s.state,'p1',cards,None),{'source_object':s.state.rules.object_id(source.id)})==[]


def test_quintorius_actual_vigilance_attack_then_free_spell_still_requires_two_discard_cost(cards):
    from app.game.errors import ActionError
    s=setup(cards,'Quintorius, Loremaster','Cathartic Reunion')
    source,spell=quintorius_ready(s,'Cathartic Reunion')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    assert not s.state.cards[source.id].tapped
    to_phase(s,'main2',turn=4)
    quintorius_activate(s,source,spell)
    assert s.state.cards[source.id].tapped
    hand=list(s.state.zones['p1:hand'])
    if hand:
        act(s,'p1',type='move',card_ids=hand,to={'player':'p1','zone':'graveyard'})
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,free=True)
    assert s.state.cards[spell.id].zone=='p1:exile' and not s.state.rules.bottom_if_graveyard
    first=put(s,'Grizzly Bears','hand')
    second=put(s,'Dragon Whelp','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,free=True)
    d=s.state.rules.decision
    if d is not None:
        answer(s,[next(o.id for o in d.options if o.card_id==cid) for cid in (first.id,second.id)])
    settle(s)
    assert s.state.cards[first.id].zone=='p1:graveyard' and s.state.cards[second.id].zone=='p1:graveyard'
    assert s.state.zones['p1:library'][-1]==spell.id


def test_quintorius_actual_spell_copy_has_no_original_stack_replacement_receipt(cards):
    s=setup(cards,'Quintorius, Loremaster')
    source,spell=quintorius_ready(s)
    bear=put(s,'Grizzly Bears','battlefield')
    quintorius_activate(s,source,spell)
    act(s,'p1',type='cast_spell',card_id=spell.id,free=True,targets=[bear.id])
    original=s.state.rules.object_id(spell.id)
    copy=put(s,'Twincast','hand')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=copy.id,targets=[spell.id])
    for _ in range(10):
        copies=[c for c in s.state.cards.values() if c.zone=='stack' and c.is_token]
        if copies:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert copies
    assert original in s.state.rules.bottom_if_graveyard
    assert all(s.state.rules.object_id(c.id) not in s.state.rules.bottom_if_graveyard for c in copies)
    settle(s)
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        answer(s,[next(o.id for o in d.options if 'keep' in o.label.lower())])
    assert ch(s,bear).pt==(8,8)
    assert s.state.zones['p1:library'][-1]==spell.id and not s.state.rules.bottom_if_graveyard


def test_mara_all_land_empty_hit_then_short_four_packet_uses_actual_exiled_nominal_values(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Ensnared by the Mara','Forest','Forest')
    first=stack_library(s,['Forest','Forest'],pid='p2')
    second=stack_library(s,['Dragon Whelp','Giant Growth'],pid='p3')
    for player,keep in [('p2',first),('p3',second)]:
        act(s,'p1',type='move',card_ids=[cid for cid in s.state.zones[player+':library'] if cid not in keep],to={'player':player,'zone':'graveyard'})
    source=put(s,'Ensnared by the Mara','hand')
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    answer(s,['cast'])
    d=s.state.rules.decision
    assert d.player=='p3' and d.resume['step']=='exile_outcomes44_mara'
    assert all(s.state.cards[cid].zone=='p2:exile' for cid in first)
    answer(s,['damage'])
    assert s.state.players['p3'].life==35 and s.state.players['p2'].life==40
    assert all(s.state.cards[cid].zone=='p3:exile' for cid in second)
    assert not s.state.rules.permissions


def test_mara_optional_free_cast_can_decline_then_no_later_authority_and_all_players_finish(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Ensnared by the Mara')
    first=stack_library(s,['Dragon Whelp'],pid='p2')[0]
    stack_library(s,['Dragon Whelp'],pid='p3')
    source=put(s,'Ensnared by the Mara','hand')
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    answer(s,['cast'])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[])
    assert s.state.rules.decision.player=='p3'
    answer(s,['cast'])
    answer(s,[])
    assert s.state.rules.decision is None
    mana(s,C=2,R=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=first)
    assert s.state.cards[first].zone=='p2:exile'


def test_mara_free_cast_cannot_waive_actual_additional_discard_two_and_next_choice_continues(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Ensnared by the Mara','Cathartic Reunion')
    first=stack_library(s,['Cathartic Reunion'],pid='p2')[0]
    source=put(s,'Ensnared by the Mara','hand')
    others=[cid for cid in s.state.zones['p1:hand'] if cid!=source.id]
    if others:
        act(s,'p1',type='move',card_ids=others,to={'player':'p1','zone':'graveyard'})
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    answer(s,['cast'])
    d=s.state.rules.decision
    with pytest.raises(ActionError):
        act(s,'p1',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==first)])
    answer(s,[])
    assert s.state.rules.decision.player=='p3'
    answer(s,['damage'])
    assert s.state.rules.decision is None and s.state.cards[first].zone=='p2:exile'


@pytest.mark.parametrize('command',[False,True])
def test_quintorius_actual_commander_countered_spell_bottom_native_owner_choice(cards,command):
    s=setup(cards,'Quintorius, Loremaster','Daretti, Scrap Savant','Counterspell')
    source,spell=quintorius_ready(s,'Daretti, Scrap Savant')
    act(s,'p1',type='set_commander',card_id=spell.id)
    if s.state.rules.decision is not None:
        answer(s,['no'])
    quintorius_activate(s,source,spell)
    if s.state.rules.decision is not None:
        answer(s,['no'])
    act(s,'p1',type='cast_spell',card_id=spell.id,free=True)
    oid=s.state.rules.object_id(spell.id)
    counter=put(s,'Counterspell','hand')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=counter.id,targets=[spell.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and 'commander' in d.resume['step']
    answer(s,['yes' if command else 'no'])
    assert s.state.cards[spell.id].zone==('p1:command' if command else 'p1:library')
    assert oid not in s.state.rules.bottom_if_graveyard
    if not command:
        assert s.state.zones['p1:library'][-1]==spell.id


def test_native_competing_free_authority_does_not_inherit_quintorius_graveyard_destination(cards):
    import random

    from app.game.session import GameSession
    from app.rules import context, permissions
    from app.rules.plan import Plan
    s=setup(cards,'Quintorius, Loremaster')
    source,spell=quintorius_ready(s)
    bear=put(s,'Grizzly Bears','battlefield')
    quintorius_activate(s,source,spell)
    plan=Plan(s.state,'p1',cards,random.Random(44))
    ctx={'controller':'p1','source_card':source.id,'source_object':plan.oid(source.id),'name':'Other free native authority'}
    context.bind_objects(plan,ctx,'other',[spell.id])
    permissions.grant_play(plan,ctx,{'who':'ref:other','from_exile':True,'play':False,'cast':True,'free':True,'until':'end_of_turn'})
    s=GameSession(plan.state,cards=cards)
    act(s,'p1',type='cast_spell',card_id=spell.id,free=True,targets=[bear.id])
    d=s.state.rules.decision
    assert d.resume['step']=='slot'
    answer(s,[next(o.id for o in d.options if 'Other free native authority' in o.label)])
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert not s.state.rules.bottom_if_graveyard and ch(s,bear).pt==(5,5)


@pytest.mark.parametrize('activated',[False,True])
def test_quintorius_actual_source_blink_old_link_cannot_target_but_resolved_permission_survives(cards,activated):
    from app.game.errors import ActionError
    s=setup(cards,'Quintorius, Loremaster','Flicker of Fate')
    source,spell=quintorius_ready(s)
    bear=put(s,'Grizzly Bears','battlefield')
    old=s.state.rules.object_id(source.id)
    if activated:
        quintorius_activate(s,source,spell)
    blink=put(s,'Flicker of Fate','hand')
    mana(s,C=1,W=1)
    act(s,'p1',type='cast_spell',card_id=blink.id,targets=[source.id])
    settle(s)
    assert s.state.rules.object_id(source.id)!=old
    if activated:
        act(s,'p1',type='cast_spell',card_id=spell.id,free=True,targets=[bear.id])
        settle(s)
        assert s.state.zones['p1:library'][-1]==spell.id
    else:
        mana(s,C=1,R=1,W=1)
        index=next(a.index for a in ch(s,source).abilities if a.text.startswith('{1}'))
        with pytest.raises(ActionError):
            act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=[spell.id])
        assert not s.state.cards[source.id].tapped
        assert any(c.is_token and 'Spirit' in ch(s,c).subtypes for c in s.state.cards.values())


def test_season_actual_mode_two_packet_and_future_optional_creature_damage_before_cast_spell(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Season of the Bold','Memnite','Forest')
    packet=stack_library(s,['Memnite','Forest'])
    target=put(s,'Grizzly Bears','battlefield','p2')
    source=put(s,'Season of the Bold','hand')
    mana(s,C=3,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[1,2])
    assert s.state.rules.decision is None
    settle(s)
    assert all(s.state.cards[cid].zone=='p1:exile' for cid in packet)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    act(s,'p1',type='cast_spell',card_id=packet[0])
    d=s.state.rules.decision
    assert d is not None and d.min_choices==0 and d.max_choices==1
    assert s.state.cards[packet[0]].zone=='stack'
    answer(s,[next(o.id for o in d.options if o.card_id==target.id)])
    assert s.state.cards[target.id].zone=='p2:graveyard'
    assert s.state.cards[packet[0]].zone=='p1:battlefield'
    act(s,'p1',type='play_land',card_id=packet[1])
    assert s.state.cards[packet[1]].zone=='p1:battlefield'


def test_quintorius_unused_exact_free_permission_expires_at_turn_cleanup(cards):
    from app.game.errors import ActionError
    s=setup(cards,'Quintorius, Loremaster')
    source,spell=quintorius_ready(s)
    bear=put(s,'Grizzly Bears','battlefield')
    quintorius_activate(s,source,spell)
    to_phase(s,'main1',turn=5)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,free=True,targets=[bear.id])
    assert s.state.cards[spell.id].zone=='p1:exile' and not s.state.rules.bottom_if_graveyard


def test_season_reviewed_native_zero_mode_then_manual_payment_keeps_announced_receipt(cards):
    s=setup(cards,'Season of the Bold')
    source=put(s,'Season of the Bold','hand')
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[])
    d=s.state.rules.decision
    assert d.resume['step']=='cast_modes' and d.min_choices==0
    original=s.state.rules.object_id(source.id)
    answer(s,[])
    d=s.state.rules.decision
    assert d.resume['step']=='pay_mana' and d.resume['zero_modes_object']==original
    mana(s,C=3,R=2)
    answer(s,['pay'])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert not s.state.rules.delayed and not s.state.rules.permissions
    assert not any(c.is_token for c in s.state.cards.values())


def test_season_reviewed_native_pre_mode_authority_choice_still_prompts_and_zero_additional_discard_resumes(cards):
    from app.game.rules_state import Permission
    s=setup(cards,'Season of the Bold','Memnite')
    source=put(s,'Season of the Bold','exile')
    first=put(s,'Dragon Whelp','hand')
    second=put(s,'Memnite','hand')
    # Explicit native permission prerequisite: the exact cast authority imposes an actual additional discard cost.
    for key,extra in [('plain',''),('discard','discard a card')]:
        s.state.rules.permissions.append(Permission(id=key,player='p1',card=source.id,object_id=s.state.rules.object_id(source.id),zone='any',
            cast=True,free=True,once=True,extra=extra,until='end_of_turn',turn=1,label=key))
    act(s,'p1',type='cast_spell',card_id=source.id,free=True)
    d=s.state.rules.decision
    assert d.resume['step']=='slot'
    answer(s,[next(o.id for o in d.options if 'discard' in o.label)])
    d=s.state.rules.decision
    assert d.resume['step']=='cast_modes' and d.min_choices==0
    answer(s,[])
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='ability_cost' and 'zero_modes_object' in d.resume
    answer(s,[next(o.id for o in d.options if o.card_id==first.id)])
    assert s.state.cards[first.id].zone=='p1:graveyard'
    assert s.state.cards[second.id].zone=='p1:hand'
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_season_actual_repeated_tapped_treasure_mode_and_budget_limit_then_native_mana(cards):
    from app.game.errors import ActionError
    s=setup(cards,'Season of the Bold')
    source=put(s,'Season of the Bold','hand')
    mana(s,C=3,R=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,modes=[1,1,1])
    assert s.state.cards[source.id].zone=='p1:hand'
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[0,0,0,0,0])
    settle(s)
    treasures=[c for c in s.state.cards.values() if c.is_token and 'Treasure' in ch(s,c).subtypes]
    assert len(treasures)==5 and all(c.tapped for c in treasures)
    token=treasures[0]
    index=0
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=token.id,ability=index,mana_choice='R')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=token.id,ability=index,mana_choice='R')
    d=s.state.rules.decision
    if d is not None:
        answer(s,[next(o.id for o in d.options if o.id=='R' or o.label=='Red')])
    assert token.id not in s.state.cards
    # The actual red Treasure unit pays a red spell, retaining native source provenance.
    dragon=put(s,'Dragon Whelp','hand')
    mana(s,C=2,R=1)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    record=s.state.rules.payments[s.state.rules.object_id(dragon.id)]
    assert any('Treasure' in tags for tags in record.mana_tags)
    settle(s)
    assert s.state.cards[dragon.id].zone=='p1:battlefield'


def test_season_actual_watch_optional_zero_and_packet_play_survive_until_own_next_cleanup_only(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Season of the Bold','Memnite','Forest')
    packet=stack_library(s,['Memnite','Forest'])
    put(s,'Grizzly Bears','battlefield','p2')
    source=put(s,'Season of the Bold','hand')
    mana(s,C=3,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[1,2])
    settle(s)
    watch=s.state.rules.delayed[0].id
    to_phase(s,'main1',turn=4)
    assert any(t.id==watch for t in s.state.rules.delayed)
    act(s,'p1',type='cast_spell',card_id=packet[0])
    d=s.state.rules.decision
    assert d is not None and d.min_choices==0
    answer(s,[])
    assert s.state.cards[packet[0]].zone=='p1:battlefield'
    to_phase(s,'main1',turn=7)
    assert not any(t.id==watch for t in s.state.rules.delayed)
    with pytest.raises(ActionError):
        act(s,'p1',type='play_land',card_id=packet[1])
    dragon=put(s,'Dragon Whelp','hand')
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=dragon.id)
    settle(s)
    assert s.state.rules.decision is None


def test_season_departed_controller_watch_survives_until_exact_native_skipped_turn_receipt(cards):
    s=setup(cards,'Season of the Bold')
    source=put(s,'Season of the Bold','hand')
    mana(s,C=3,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[2])
    settle(s)
    watch=s.state.rules.delayed[0].id
    act(s,'p1',type='concede')
    assert any(t.id==watch for t in s.state.rules.delayed)
    to_phase(s,'main1',turn=2)
    assert any(t.id==watch for t in s.state.rules.delayed)
    to_phase(s,'main1',turn=3)
    assert any(t.id==watch for t in s.state.rules.delayed)
    to_phase(s,'main1',turn=5)
    assert s.state.turn.active_player=='p2'
    assert not any(t.id==watch for t in s.state.rules.delayed)


def test_season_actual_repeated_top_two_modes_keep_distinct_exact_paid_packets(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Season of the Bold','Memnite','Forest')
    packet=stack_library(s,['Forest','Memnite','Dragon Whelp','Giant Growth'])
    source=put(s,'Season of the Bold','hand')
    mana(s,C=3,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[1,1])
    settle(s)
    assert all(s.state.cards[cid].zone=='p1:exile' for cid in packet)
    act(s,'p1',type='play_land',card_id=packet[0])
    act(s,'p1',type='cast_spell',card_id=packet[1])
    settle(s)
    to_phase(s,'main1',turn=4)
    mana(s,W=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=packet[2])
    act(s,'p1',type='clear_mana',player='p1')
    mana(s,C=2,R=2)
    act(s,'p1',type='cast_spell',card_id=packet[2])
    settle(s)
    assert s.state.cards[packet[2]].zone=='p1:battlefield'
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=packet[3],targets=[packet[1]])
    settle(s)
    assert ch(s,s.state.cards[packet[1]]).pt==(4,4)


def test_season_actual_copied_paw_mode_creates_two_independent_future_targets_from_original_sources(cards):
    s=setup(cards,'Season of the Bold','Memnite')
    first=put(s,'Grizzly Bears','battlefield','p2')
    second=put(s,'Grizzly Bears','battlefield','p3')
    source=put(s,'Season of the Bold','hand')
    mana(s,C=3,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[2])
    copy=put(s,'Twincast','hand')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=copy.id,targets=[source.id])
    settle(s)
    assert len(s.state.rules.delayed)==2
    assert len({t.source_object for t in s.state.rules.delayed})==2
    spell=put(s,'Memnite','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    for target in [first,second]:
        d=s.state.rules.decision
        assert d is not None and d.min_choices==0 and d.max_choices==1
        answer(s,[next(o.id for o in d.options if o.card_id==target.id)])
    assert s.state.cards[first.id].zone=='p2:graveyard' and s.state.cards[second.id].zone=='p3:graveyard'
    assert s.state.cards[spell.id].zone=='p1:battlefield'


def test_season_reverse_announced_indices_still_create_treasure_before_exiling_top_packet(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Season of the Bold','Memnite','Forest')
    packet=stack_library(s,['Memnite','Forest'])
    source=put(s,'Season of the Bold','hand')
    mana(s,C=3,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[1,0])
    settle(s)
    steps=s.history.actions[-1].r
    created=next(i for i,step in enumerate(steps) if step['type']=='create_token')
    exiled=next(i for i,step in enumerate(steps) if step['type']=='mill' and step.get('to')=='exile')
    assert created<exiled
    assert all(s.state.cards[cid].zone=='p1:exile' for cid in packet)
    assert sum(c.is_token and c.name=='Treasure' and c.tapped for c in s.state.cards.values())==1


def test_season_future_target_illegal_on_resolution_does_not_rechoose_or_block_original_spell(cards):
    s=setup(cards,'Season of the Bold','Memnite')
    first=put(s,'Grizzly Bears','battlefield','p2')
    other=put(s,'Grizzly Bears','battlefield','p3')
    source=put(s,'Season of the Bold','hand')
    mana(s,C=3,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[2])
    settle(s)
    spell=put(s,'Memnite','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id)
    d=s.state.rules.decision
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==first.id)])
    removal=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=removal.id,targets=[first.id])
    d=s.state.rules.decision
    assert d is not None and d.min_choices==0
    answer(s,[])
    assert s.state.cards[first.id].zone=='p2:graveyard'
    assert s.state.cards[other.id].zone=='p3:battlefield' and s.state.cards[other.id].damage==0
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert s.state.rules.decision is None


def test_season_zero_mode_payment_cancel_does_not_announce_zero_on_a_later_new_cast(cards):
    s=setup(cards,'Season of the Bold')
    source=put(s,'Season of the Bold','hand')
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='cast_spell',card_id=source.id)
    answer(s,[])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    answer(s,['cancel'])
    assert s.state.cards[source.id].zone=='p1:hand'
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[])
    d=s.state.rules.decision
    assert d.resume['step']=='cast_modes' and d.min_choices==0
    answer(s,[next(o.id for o in d.options if o.id=='0:0')])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    mana(s,C=3,R=2)
    answer(s,['pay'])
    assert sum(c.is_token and c.name=='Treasure' for c in s.state.cards.values())==1
    assert not s.state.rules.delayed
