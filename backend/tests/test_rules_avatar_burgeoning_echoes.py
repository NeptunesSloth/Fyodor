"""Canonical Avatar collateral: empower and granted loyalty use native timing and SBA."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index

NAME='Avatar of Burgeoning Echoes'

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/avatar_burgeoning_echoes_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='abe',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s=table(cards,[NAME,'Forest','Island','Grizzly Bears','Jace Beleren','Lightning Bolt'],['Jace Beleren'],[])
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    source=put(s,NAME,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'G':1,'U':1})
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    land=put(s,'Forest','hand')
    act(s,'p1',type='play_land',card_id=land.id)
    settle(s)
    jace=next(c for c in s.state.cards.values() if c.name=='Jace' and c.is_token)
    bear=put(s,'Grizzly Bears','battlefield')
    roundtrip(s)
    return s,source,jace,bear


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


def test_actual_landfall_creates_blue_jace_with_two_loyalty_and_native_abilities(cards):
    s,source,jace,_=setup(cards)
    ch=Plan(s.state,'p1',s.cards,None).ch(jace)
    assert jace.counters['loyalty']==2 and set(ch.colors)=={'U'}
    assert 'Planeswalker' in ch.types and 'Jace' in ch.subtypes
    assert all(any(text in a.text for a in ch.abilities) for text in ('Surveil 1','Draw a card','Put a +1/+1 counter'))
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert not s.state.cards[source.id].counters.get('loyalty')
    roundtrip(s)


@pytest.mark.parametrize('depart',[False,True])
def test_granted_minus_ten_pays_host_and_resolves_after_zero_loyalty_sba_and_donor_departure(cards,depart):
    s,source,jace,bear=setup(cards)
    act(s,'p1',type='set_counter',card_id=jace.id,kind='loyalty',value=10)
    index=ability_index(s,jace,'Put a +1/+1 counter')
    act(s,'p1',type='activate_ability',card_id=jace.id,ability=index,targets=[bear.id])
    assert jace.id not in s.state.cards
    assert s.state.cards[source.id].zone=='p1:battlefield'
    if depart:
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    roundtrip(s)
    settle(s)
    assert s.state.cards[bear.id].counters.get('+1/+1')==1
    roundtrip(s)


def test_granted_and_native_loyalty_abilities_share_once_per_turn_limit(cards):
    s,_,jace,bear=setup(cards)
    act(s,'p1',type='set_counter',card_id=jace.id,kind='loyalty',value=11)
    act(s,'p1',type='activate_ability',card_id=jace.id,ability=ability_index(s,jace,'Put a +1/+1 counter'),targets=[bear.id])
    settle(s)
    assert s.state.cards[jace.id].counters['loyalty']==1
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=jace.id,ability=ability_index(s,jace,'Surveil'))
    roundtrip(s)


def test_normal_loyalty_timing_and_grant_only_owned_planeswalkers(cards):
    s,_,jace,bear=setup(cards)
    act(s,'p1',type='set_counter',card_id=jace.id,kind='loyalty',value=11)
    other=put(s,'Jace Beleren','battlefield',pid='p2')
    assert not any('Put a +1/+1 counter' in a.text for a in Plan(s.state,'p1',s.cards,None).ch(other).abilities)
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=['p3'])
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=jace.id,ability=ability_index(s,jace,'Put a +1/+1 counter'),targets=[bear.id])
    roundtrip(s)


def test_empowered_jaces_native_draw_pays_its_cost_and_draws_after_zero_loyalty_sba(cards):
    s,source,jace,_=setup(cards)
    act(s,'p1',type='set_counter',card_id=jace.id,kind='loyalty',value=3)
    hand=len(s.state.zones.get('p1:hand',[]))
    act(s,'p1',type='activate_ability',card_id=jace.id,ability=ability_index(s,jace,'Draw a card'))
    assert jace.id not in s.state.cards
    roundtrip(s)
    settle(s)
    assert len(s.state.zones.get('p1:hand',[]))==hand+1
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


def test_different_hosts_have_independent_loyalty_activation_limits(cards):
    s,_,jace,bear=setup(cards)
    walker=put(s,'Jace Beleren','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'U':2,'C':1})
    act(s,'p1',type='cast_spell',card_id=walker.id)
    settle(s)
    act(s,'p1',type='set_counter',card_id=walker.id,kind='loyalty',value=11)
    act(s,'p1',type='activate_ability',card_id=walker.id,ability=ability_index(s,walker,'Put a +1/+1 counter'),targets=[bear.id])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty']==1
    act(s,'p1',type='activate_ability',card_id=jace.id,ability=ability_index(s,jace,'Surveil'))
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[d.options[0].id])
    settle(s)
    assert s.state.cards[jace.id].counters['loyalty']==1
    roundtrip(s)
