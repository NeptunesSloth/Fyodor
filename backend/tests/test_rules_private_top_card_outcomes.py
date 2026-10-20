"""Canonical Biblioplex and Delver private looks, public reveals, and native timing."""
from __future__ import annotations

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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_discard_outcomes import cold_run
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_mana_delayed_effects import answer
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA=Path(__file__).parent/'fixtures/private_top_card_outcomes_cards.json'
NAMES=['The Biblioplex','Delver of Secrets // Insectile Aberration']

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads(DATA.read_text())):
        fields={k:v for k,v in c.items() if k not in ['name','id','oracle_id','set_code','collector_number']}
        if 'faces' in fields:
            fields['card_faces']=fields.pop('faces')
        base[c['name']]=card(c['name'],set_code='ptc36',number=str(i),**fields)
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    r=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield r
    r.close()

def game(cards):
    names=[c['name'] for c in json.loads(DATA.read_text())]
    s=table(cards,names,names,names)
    for p in ['p1','p2','p3']:
        act(s,p,type='set_prefs',hold_priority=True)
    to_phase(s,'main1',4)
    return s

def top(s,name):
    c=put(s,name,'library')
    act(s,'p1',type='move',card_ids=[c.id],to={'player':'p1','zone':'library'},position='top')
    return c

def hand(s,n,exclude=()):
    for cid in list(s.state.zones['p1:hand']):
        act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'exile'})
    for c in [c for c in s.state.cards.values() if c.owner=='p1' and c.id not in exclude and c.zone not in ['p1:battlefield','stack']][:n]:
        act(s,'p1',type='move',card_ids=[c.id],to={'player':'p1','zone':'hand'})
    assert len(s.state.zones['p1:hand'])==n

def activate(s,c):
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='activate_ability',card_id=c.id,ability=1,sources=[])

@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'

@pytest.mark.parametrize('n',[0,7])
def test_biblioplex_paid_private_look_revealed_spell_to_hand(cards,n):
    s=game(cards)
    source=put(s,'The Biblioplex','battlefield')
    c=top(s,'Lightning Bolt')
    hand(s,n,[c.id,source.id])
    activate(s,source)
    settle(s)
    assert not s.view('p2')['cards'].get(c.id,{}).get('name')
    assert s.state.cards[source.id].tapped
    assert s.state.players['p1'].mana.get('C',0)==0
    choose(s,[c.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone=='p1:hand'
    assert any(step.get('type')=='reveal' and c.id in step.get('card_ids',[])
               for a in s.history.actions if isinstance(getattr(a,'r',None),list) for step in a.r)

@pytest.mark.parametrize('name,graveyard',[('Forest',True),('Sol Ring',False),('Lightning Bolt',True)])
def test_biblioplex_optional_graveyard_or_stays_top(cards,name,graveyard):
    s=game(cards)
    source=put(s,'The Biblioplex','battlefield')
    c=top(s,name)
    hand(s,0,[c.id,source.id])
    activate(s,source)
    settle(s)
    choose(s,[])
    settle(s)
    assert not s.view('p2')['cards'].get(c.id,{}).get('name')
    choose(s,[c.id] if graveyard else [])
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone==('p1:graveyard' if graveyard else 'p1:library')
    if not graveyard:
        assert s.state.zones['p1:library'][0]==c.id and not s.state.cards[c.id].revealed_to

@pytest.mark.parametrize('n',[1,6,8])
def test_biblioplex_rejects_other_hand_sizes(cards,n):
    s=game(cards)
    source=put(s,'The Biblioplex','battlefield')
    hand(s,n,[source.id])
    with pytest.raises(ActionError):
        activate(s,source)
    assert not s.state.cards[source.id].tapped


def test_biblioplex_hand_gate_not_rechecked_on_resolution(cards):
    s=game(cards)
    source=put(s,'The Biblioplex','battlefield')
    c=top(s,'Lightning Bolt')
    hand(s,0,[source.id,c.id])
    activate(s,source)
    put(s,'Sol Ring','hand')
    settle(s)
    choose(s,[c.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone=='p1:hand'


def test_biblioplex_second_choice_cold_resume(cards,tmp_path):
    s=game(cards)
    source=put(s,'The Biblioplex','battlefield')
    c=top(s,'Lightning Bolt')
    hand(s,0,[source.id,c.id])
    activate(s,source)
    settle(s)
    choose(s,[])
    settle(s)
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_hidden_card_facts import choose
choose(s,[args[0]])
answer(s)
assert s.state.cards[args[0]].zone=='p1:graveyard'
""",c.id)

@pytest.mark.parametrize('name,reveal,transformed',[('Lightning Bolt',True,True),('Counterspell',True,True),('Forest',True,False),('Sol Ring',True,False),('Lightning Bolt',False,False)])
def test_delver_optional_reveal_any_card_only_spells_transform(cards,name,reveal,transformed):
    s=game(cards)
    source=put(s,NAMES[1],'battlefield')
    to_phase(s,'end',6)
    c=top(s,name)
    to_phase(s,'upkeep',7)
    settle(s)
    assert not s.view('p2')['cards'].get(c.id,{}).get('name')
    choose(s,[c.id] if reveal else [])
    answer(s)
    roundtrip(s)
    assert s.state.cards[source.id].face==int(transformed)
    assert s.state.zones['p1:library'][0]==c.id
    assert bool(s.state.cards[c.id].revealed_to)==reveal


def test_delver_original_source_left_does_not_transform_new_incarnation(cards):
    s=game(cards)
    source=put(s,NAMES[1],'battlefield')
    to_phase(s,'end',6)
    c=top(s,'Lightning Bolt')
    to_phase(s,'upkeep',7)
    settle(s)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'hand'})
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'battlefield'})
    choose(s,[c.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[source.id].face==0


def test_delver_reveal_pending_cold_resume(cards,tmp_path):
    s=game(cards)
    source=put(s,NAMES[1],'battlefield')
    to_phase(s,'end',6)
    c=top(s,'Lightning Bolt')
    to_phase(s,'upkeep',7)
    settle(s)
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_hidden_card_facts import choose
choose(s,[args[0]])
answer(s)
assert s.state.cards[args[1]].face==1
assert s.state.zones['p1:library'][0]==args[0]
""",c.id,source.id)
