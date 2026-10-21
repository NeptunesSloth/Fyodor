"""Choreographed Sparks grants noncopiable abilities through the spell-to-token transition."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    raw=json.loads((Path(__file__).parent/'fixtures/choreographed_sparks_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='csp',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME='Choreographed Sparks'


def setup(cards,extras=()):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/choreographed_sparks_cards.json').read_text())]
    s=table(cards,names,names,names)
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True)
    for name in extras:
        put(s,name,'battlefield')
    return s


def cast(s,name,pid='p1',targets=(),modes=None,x=None):
    wait_priority(s,pid)
    source=put(s,name,'hand',pid=pid)
    act(s,pid,type='add_mana',player=pid,mana={'C':12,'R':6,'U':4,'G':4,'B':2,'W':2})
    extra={}
    if modes is not None:
        extra['modes']=modes
        if len(modes)>1:
            extra['target_counts']=[1]*len(modes)
    if x is not None:
        extra['x_value']=x
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),**extra)
    return source


def finish_copy(s,target='keep'):
    settle(s)
    for _ in range(30):
        d=s.state.rules.decision
        if d is None:
            return
        step=d.resume.get('step')
        assert step in ('copy_target','copy_order')
        choice=target if step=='copy_target' else 'original'
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[choice])
    raise AssertionError('Copying did not finish')


def creature_copy(cards,name='Grizzly Bears',extras=()):
    s=setup(cards,extras)
    original=cast(s,name)
    source=cast(s,NAME,targets=[original.id],modes=[1])
    finish_copy(s)
    settle(s)
    made=[c for c in s.state.cards.values() if c.is_token and c.name==name and c.zone=='p1:battlefield']
    return s,original,source,made


def ch(s,c):
    return Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c.id])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


def test_creature_copy_gains_haste_can_attack_and_sacrifices_only_itself(cards):
    s,original,_,made=creature_copy(cards)
    assert len(made)==1
    token=made[0]
    assert 'haste' in ch(s,token).keywords and 'haste' not in ch(s,original).keywords
    roundtrip(s)
    to_phase(s,'declare_attackers',turn=1)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':token.id,'target':'p2'}])
    to_phase(s,'end',turn=1)
    settle(s)
    assert token.id not in s.state.cards
    assert s.state.cards[original.id].zone=='p1:battlefield'
    assert s.state.players['p2'].life==38
    roundtrip(s)


def test_both_modes_copy_instant_and_creature_and_retarget_only_spell_copy(cards):
    s=setup(cards)
    bear=cast(s,'Grizzly Bears')
    bolt=cast(s,'Lightning Bolt',targets=['p3'])
    cast(s,NAME,targets=[bolt.id,bear.id],modes=[0,1])
    finish_copy(s,'p2')
    assert s.state.rules.stack[bolt.id].targets[0].id=='p3'
    settle(s)
    assert s.state.players['p2'].life==37 and s.state.players['p3'].life==37
    made=[c for c in s.state.cards.values() if c.is_token and c.name=='Grizzly Bears' and c.zone=='p1:battlefield']
    assert len(made)==1 and 'haste' in ch(s,made[0]).keywords
    roundtrip(s)


def test_modes_cannot_copy_opponents_spells(cards):
    s=setup(cards)
    bolt=cast(s,'Lightning Bolt',pid='p2',targets=['p3'])
    with pytest.raises(ActionError):
        cast(s,NAME,targets=[bolt.id],modes=[0])
    roundtrip(s)


def test_parallel_lives_does_not_double_a_resolving_permanent_spell_copy(cards):
    s,_,_,made=creature_copy(cards,extras=['Parallel Lives'])
    assert len(made)==1
    roundtrip(s)


def test_staff_additional_creature_copy_also_gets_the_grant(cards):
    s,original,_,made=creature_copy(cards,extras=['Twinning Staff'])
    assert len(made)==2 and all('haste' in ch(s,c).keywords for c in made)
    to_phase(s,'end',turn=1)
    settle(s)
    assert all(c.id not in s.state.cards for c in made)
    assert s.state.cards[original.id].zone=='p1:battlefield'
    roundtrip(s)


def test_granted_abilities_are_not_copiable_values(cards):
    s,original,_,made=creature_copy(cards)
    token=made[0]
    clone=cast(s,'Clone')
    settle(s)
    d=s.state.rules.decision
    assert d is not None and token.id in {o.id for o in d.options}
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[token.id])
    settle(s)
    assert 'haste' not in ch(s,clone).keywords
    assert not any('sacrifice' in a.text.lower() for a in ch(s,clone).abilities)
    to_phase(s,'end',turn=1)
    settle(s)
    assert token.id not in s.state.cards
    assert s.state.cards[clone.id].zone==s.state.cards[original.id].zone=='p1:battlefield'
    roundtrip(s)


def test_x_creature_copy_keeps_x_and_entry_counters_but_is_not_cast(cards):
    s=setup(cards)
    before=s.state.rules.turn_log.drew.get('p1',0)
    original=cast(s,'Hydroid Krasis',x=3)
    cast(s,NAME,targets=[original.id],modes=[1])
    finish_copy(s)
    settle(s)
    hydras=[c for c in s.state.cards.values() if c.name=='Hydroid Krasis' and c.zone=='p1:battlefield']
    assert len(hydras)==2 and all(c.counters.get('+1/+1')==3 for c in hydras)
    assert sum('haste' in ch(s,c).keywords for c in hydras)==1
    assert s.state.players['p1'].life==41
    assert s.state.rules.turn_log.drew.get('p1',0)==before+1
    roundtrip(s)


def test_instant_sorcery_mode_preserves_x_and_retargets(cards):
    s=setup(cards)
    original=cast(s,'Blaze',targets=['p3'],x=4)
    cast(s,NAME,targets=[original.id],modes=[0])
    finish_copy(s,'p2')
    copied=next(c for c in s.state.cards.values() if c.is_token and c.zone=='stack')
    assert s.state.rules.stack[copied.id].x==4
    settle(s)
    assert s.state.players['p2'].life==s.state.players['p3'].life==36
    roundtrip(s)


def test_instant_sorcery_mode_preserves_original_chosen_mode(cards):
    s=setup(cards)
    a=put(s,'Grizzly Bears','battlefield',pid='p2')
    b=put(s,'Grizzly Bears','battlefield',pid='p3')
    original=cast(s,'Abrade',targets=[a.id],modes=[0])
    cast(s,NAME,targets=[original.id],modes=[0])
    finish_copy(s,b.id)
    copied=next(c for c in s.state.cards.values() if c.is_token and c.zone=='stack')
    assert s.state.rules.stack[copied.id].modes==[0]
    settle(s)
    assert s.state.cards[a.id].zone=='p2:graveyard' and s.state.cards[b.id].zone=='p3:graveyard'
    roundtrip(s)


def test_departed_copy_does_not_sacrifice_original_at_end_step(cards):
    s,original,_,made=creature_copy(cards)
    token=made[0]
    act(s,'p1',type='move',card_ids=[token.id],to={'player':'p1','zone':'graveyard'})
    to_phase(s,'end',turn=1)
    settle(s)
    assert token.id not in s.state.cards
    assert s.state.cards[original.id].zone=='p1:battlefield'
    roundtrip(s)


def test_end_step_trigger_uses_tokens_current_controller(cards):
    s,original,_,made=creature_copy(cards)
    token=made[0]
    act(s,'p1',type='set_controller',card_ids=[token.id],player='p2')
    to_phase(s,'end',turn=1)
    assert any(c.ability is not None and c.controller=='p2' and c.ability.source_id==token.id for c in s.state.cards.values() if c.zone=='stack')
    settle(s)
    assert token.id not in s.state.cards and s.state.cards[original.id].zone=='p1:battlefield'
    roundtrip(s)


def test_removing_abilities_for_first_end_step_does_not_consume_a_delayed_trigger(cards):
    s,original,_,made=creature_copy(cards)
    token=made[0]
    down=cast(s,'Dress Down')
    settle(s)
    assert 'haste' not in ch(s,token).keywords
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[down.id].zone=='p1:graveyard'
    assert s.state.cards[token.id].zone=='p1:battlefield'
    assert 'haste' in ch(s,token).keywords
    roundtrip(s)
    to_phase(s,'end',turn=2)
    settle(s)
    assert token.id not in s.state.cards and s.state.cards[original.id].zone=='p1:battlefield'
    roundtrip(s)


def test_countering_end_step_trigger_leaves_ability_to_trigger_next_turn(cards):
    s,original,_,made=creature_copy(cards)
    token=made[0]
    to_phase(s,'end',turn=1)
    trigger=next(c for c in s.state.cards.values() if c.zone=='stack' and c.ability is not None and c.ability.source_id==token.id)
    cast(s,'Stifle',targets=[trigger.id])
    settle(s)
    assert s.state.cards[token.id].zone=='p1:battlefield'
    roundtrip(s)
    to_phase(s,'end',turn=2)
    settle(s)
    assert token.id not in s.state.cards and s.state.cards[original.id].zone=='p1:battlefield'
    roundtrip(s)


def test_leaving_after_end_trigger_does_not_make_it_sacrifice_the_original(cards):
    s,original,_,made=creature_copy(cards)
    token=made[0]
    to_phase(s,'end',turn=1)
    assert s.state.zones.get('stack')
    act(s,'p1',type='move',card_ids=[token.id],to={'player':'p1','zone':'exile'})
    roundtrip(s)
    settle(s)
    assert token.id not in s.state.cards and s.state.cards[original.id].zone=='p1:battlefield'
    roundtrip(s)


def test_sparks_on_stack_cannot_be_copied_by_reverberate(cards):
    s=setup(cards)
    original=cast(s,'Grizzly Bears')
    sparks=cast(s,NAME,targets=[original.id],modes=[1])
    cast(s,'Reverberate',targets=[sparks.id])
    finish_copy(s)
    settle(s)
    assert not any(c.is_token and c.name==NAME for c in s.state.cards.values())
    made=[c for c in s.state.cards.values() if c.is_token and c.name=='Grizzly Bears' and c.zone=='p1:battlefield']
    assert len(made)==1 and 'haste' in ch(s,made[0]).keywords
    roundtrip(s)


def test_sparks_card_can_be_copied_from_exile_and_cast_with_new_modes(cards):
    s=setup(cards)
    sparks=put(s,NAME,'graveyard')
    mastery=cast(s,"Mizzix's Mastery",targets=[sparks.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='free_cast_pick' and len(d.options)==1
    copy_id=d.options[0].id
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[copy_id])
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='cast_modes'
    mode=next(o.id for o in d.options if o.id.split(':')[0]=='0')
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[mode])
    d=s.state.rules.decision
    assert d is not None and mastery.id in {o.id for o in d.options}
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[mastery.id])
    assert s.state.cards[copy_id].zone=='stack'
    assert s.state.rules.stack[copy_id].modes==[0]
    settle(s)
    assert copy_id not in s.state.cards  # Mastery has left the stack, so its targeted copy is illegal.
    assert s.state.cards[sparks.id].zone==s.state.cards[mastery.id].zone=='p1:exile'
    roundtrip(s)
