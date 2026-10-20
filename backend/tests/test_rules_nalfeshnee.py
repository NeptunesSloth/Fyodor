"""Nalfeshnee: copy every exile-cast spell, conditionally grant noncopiable permanent abilities."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
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
    raw=json.loads((Path(__file__).parent/'fixtures/nalfeshnee_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='nal',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME='Nalfeshnee'


def setup(cards,extras=()):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/nalfeshnee_cards.json').read_text())]
    s=table(cards,names,names,names)
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True)
    source=put(s,NAME,'battlefield')
    for name in extras:
        put(s,name,'battlefield')
    return s,source


def cast(s,c,pid='p1',targets=(),**options):
    wait_priority(s,pid)
    act(s,pid,type='add_mana',player=pid,mana={'C':12,'R':6,'U':6,'G':6})
    act(s,pid,type='cast_spell',card_id=c.id,targets=list(targets),**options)


def offer(s,name,pid='p1'):
    c=next(c for c in s.state.cards.values() if c.name==name and c.owner==pid and c.zone!='p1:battlefield')
    land=next(c for c in s.state.cards.values() if c.name=='Forest' and c.owner==pid)
    act(s,pid,type='move',card_ids=[land.id],to={'player':pid,'zone':'library'},position='top')
    act(s,pid,type='move',card_ids=[c.id],to={'player':pid,'zone':'library'},position='top')
    impulse=put(s,'Reckless Impulse','hand',pid=pid)
    cast(s,impulse,pid)
    settle(s)
    assert s.state.cards[c.id].zone==pid+':exile'
    roundtrip(s)
    return s.state.cards[c.id],land


def made(s,name,zone=None):
    return [c for c in s.state.cards.values() if c.name==name and c.is_token and (zone is None or c.zone==zone)]


def answer_copy(s,target='keep'):
    settle(s)
    for _ in range(20):
        d=s.state.rules.decision
        if d is None:
            return
        step=d.resume.get('step')
        assert step in ('copy_target','copy_order')
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[target if step=='copy_target' else 'original'])
    raise AssertionError('Copy did not finish')


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


@pytest.mark.parametrize('name',['Grizzly Bears','Sol Ring'])
def test_exile_permanent_spell_copy_gets_haste_and_self_sacrifice(cards,name):
    s,_=setup(cards)
    original,_=offer(s,name)
    cast(s,original)
    answer_copy(s)
    settle(s)
    copies=made(s,name,'p1:battlefield')
    assert len(copies)==1
    token=copies[0]
    assert 'haste' in Plan(s.state,'p1',s.cards,None).ch(token).keywords
    assert 'haste' not in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[original.id]).keywords
    roundtrip(s)
    to_phase(s,'end',turn=1)
    settle(s)
    assert token.id not in s.state.cards
    assert s.state.cards[original.id].zone=='p1:battlefield'
    roundtrip(s)


def test_instant_is_copied_and_retargeted_without_receiving_permanent_grants(cards):
    s,_=setup(cards)
    original,_=offer(s,'Lightning Bolt')
    cast(s,original,targets=['p3'])
    answer_copy(s,'p2')
    copies=made(s,'Lightning Bolt','stack')
    assert len(copies)==1
    assert 'haste' not in Plan(s.state,'p1',s.cards,None).ch(copies[0]).keywords
    assert s.state.rules.stack[copies[0].id].targets[0].id=='p2'
    assert s.state.rules.stack[original.id].targets[0].id=='p3'
    settle(s)
    assert s.state.players['p2'].life==s.state.players['p3'].life==37
    roundtrip(s)


def test_casting_from_hand_and_playing_land_from_exile_do_not_copy(cards):
    s,_=setup(cards)
    bear=put(s,'Grizzly Bears','hand')
    cast(s,bear)
    settle(s)
    assert not made(s,'Grizzly Bears')
    _,land=offer(s,'Sol Ring')
    act(s,'p1',type='play_land',card_id=land.id)
    settle(s)
    assert not made(s,'Forest')
    roundtrip(s)


@pytest.mark.parametrize('extra',['Twinning Staff','Parallel Lives'])
def test_staff_adds_copies_but_token_creation_doubler_does_not(cards,extra):
    s,_=setup(cards,[extra])
    original,_=offer(s,'Grizzly Bears')
    cast(s,original)
    answer_copy(s)
    settle(s)
    copies=made(s,'Grizzly Bears','p1:battlefield')
    assert len(copies)==(2 if extra=='Twinning Staff' else 1)
    assert all('haste' in Plan(s.state,'p1',s.cards,None).ch(c).keywords for c in copies)
    to_phase(s,'end',turn=1)
    settle(s)
    assert all(c.id not in s.state.cards for c in copies)
    assert s.state.cards[original.id].zone=='p1:battlefield'
    roundtrip(s)


def test_countered_original_permanent_is_copied_from_stack_last_known_values(cards):
    s,_=setup(cards)
    original,_=offer(s,'Grizzly Bears')
    cast(s,original)
    counter=put(s,'Counterspell','hand',pid='p2')
    cast(s,counter,'p2',targets=[original.id])
    answer_copy(s)
    settle(s)
    assert s.state.cards[original.id].zone=='p1:graveyard'
    copies=made(s,'Grizzly Bears','p1:battlefield')
    assert len(copies)==1 and 'haste' in Plan(s.state,'p1',s.cards,None).ch(copies[0]).keywords
    roundtrip(s)


def test_countered_uncopyable_spell_remains_uncopyable_as_last_known_spell(cards):
    s,_=setup(cards)
    original,_=offer(s,'Display of Power')
    cast(s,original,target_counts=[0])
    counter=put(s,'Counterspell','hand',pid='p2')
    cast(s,counter,'p2',targets=[original.id])
    settle(s)
    assert s.state.cards[original.id].zone=='p1:graveyard'
    assert not made(s,'Display of Power') and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('departure',['graveyard','control'])
def test_trigger_survives_source_departure_and_uses_original_trigger_controller(cards,departure):
    s,source=setup(cards)
    original,_=offer(s,'Grizzly Bears')
    cast(s,original)
    if departure=='graveyard':
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    else:
        act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    answer_copy(s)
    settle(s)
    copies=made(s,'Grizzly Bears','p1:battlefield')
    assert len(copies)==1 and copies[0].controller=='p1'
    assert 'haste' in Plan(s.state,'p1',s.cards,None).ch(copies[0]).keywords
    roundtrip(s)


def test_opponent_casting_from_exile_does_not_trigger_your_nalfeshnee(cards):
    s,_=setup(cards)
    to_phase(s,'main1',turn=2)
    original,_=offer(s,'Lightning Bolt',pid='p2')
    cast(s,original,'p2',targets=['p3'])
    settle(s)
    assert s.state.players['p3'].life==37 and not made(s,'Lightning Bolt')
    roundtrip(s)


def test_conditional_grants_are_not_copied_by_a_later_clone(cards):
    s,_=setup(cards)
    original,_=offer(s,'Grizzly Bears')
    cast(s,original)
    answer_copy(s)
    settle(s)
    token=made(s,'Grizzly Bears','p1:battlefield')[0]
    clone=put(s,'Clone','hand')
    cast(s,clone)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and token.id in {o.id for o in d.options}
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[token.id])
    settle(s)
    assert 'haste' not in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[clone.id]).keywords
    to_phase(s,'end',turn=1)
    settle(s)
    assert token.id not in s.state.cards
    assert s.state.cards[clone.id].zone=='p1:battlefield'
    roundtrip(s)


def test_countered_back_face_sorcery_is_not_mistaken_for_front_face_permanent(cards):
    s,_=setup(cards)
    original,_=offer(s,'Pestilent Cauldron // Restorative Burst')
    cast(s,original,face=1,target_counts=[0])
    counter=put(s,'Counterspell','hand',pid='p2')
    cast(s,counter,'p2',targets=[original.id])
    for _ in range(80):
        copies=[c for c in s.state.cards.values() if c.is_token and c.zone=='stack' and c.ability is None]
        if copies:
            break
        assert s.state.rules.decision is None
        act(s,s.state.rules.priority,type='pass_priority')
    else:
        raise AssertionError('No spell copy appeared')
    assert s.state.cards[original.id].zone=='p1:graveyard' and s.state.cards[original.id].face==0
    copied=Plan(s.state,'p1',s.cards,None).ch(copies[0])
    assert copied.name=='Restorative Burst' and copied.is_instant_or_sorcery
    assert 'haste' not in copied.keywords
    assert not any('sacrifice' in a.text.lower() for a in copied.abilities)
    roundtrip(s)
    settle(s)
    roundtrip(s)
