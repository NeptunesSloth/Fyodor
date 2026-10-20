"""Canonical revealed picks preserve exact original library objects and entry counters."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_discard_outcomes import cold_run
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_mana_delayed_effects import answer, cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA=Path(__file__).parent/'fixtures/revealed_two_stage_picks_cards.json'
NAMES=[c['name'] for c in json.loads(DATA.read_text())][:3]

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads(DATA.read_text())):
        fields={k:v for k,v in c.items() if k not in ['name','id','oracle_id','set_code','collector_number']}
        if 'faces' in fields:
            fields['card_faces']=fields.pop('faces')
        base[c['name']]=card(c['name'],set_code='rts36',number=str(i),**fields)
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    r=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield r
    r.close()

def game(cards,top):
    names=[c['name'] for c in json.loads(DATA.read_text())]
    s=table(cards,names,names,names)
    for p in ['p1','p2','p3']:
        act(s,p,type='set_prefs',hold_priority=True)
    to_phase(s,'main1',4)
    # Exactly the requested top cards remain in the library; no accidental matches.
    for cid in list(s.state.zones['p1:library']):
        act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'exile'})
    ids=[]
    for name in reversed(top):
        c=put(s,name,'library')
        act(s,'p1',type='move',card_ids=[c.id],to={'player':'p1','zone':'library'},position='top')
        ids.insert(0,c.id)
    return s,ids

@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'

@pytest.mark.parametrize('x,dest',[(2,'hand'),(5,'hand'),(5,'battlefield')])
def test_green_mandatory_one_or_two_shared_destination(cards,x,dest):
    s,ids=game(cards,['Trained Armodon','Forest','Sol Ring'])
    cast(s,"Green Sun's Twilight",{'G':1,'C':x},x_value=x)
    settle(s)
    d=s.state.rules.decision
    assert d.min_choices==1 and d.max_choices==2
    with pytest.raises(ActionError):
        choose(s,[])
    choose(s,ids[:2])
    settle(s)
    if x>=5:
        choose(s,[dest])
    answer(s)
    roundtrip(s)
    assert all(s.state.cards[c].zone=='p1:'+dest for c in ids[:2])
    assert s.state.cards[ids[2]].zone=='p1:library'
    assert not s.state.cards[ids[2]].revealed_to


def test_green_only_one_category_can_choose_one(cards):
    s,ids=game(cards,['Trained Armodon','Llanowar Elves'])
    cast(s,"Green Sun's Twilight",{'G':1,'C':2},x_value=2)
    settle(s)
    with pytest.raises(ActionError):
        choose(s,ids)
    choose(s,ids[:1])
    answer(s)
    assert s.state.cards[ids[0]].zone=='p1:hand'
    roundtrip(s)


def test_green_no_matches_bottoms_all(cards):
    s,ids=game(cards,['Sol Ring'])
    cast(s,"Green Sun's Twilight",{'G':1},x_value=0)
    answer(s)
    roundtrip(s)
    assert s.state.cards[ids[0]].zone=='p1:library' and not s.state.cards[ids[0]].revealed_to


def test_bounty_land_tapped_and_elf_hand(cards):
    s,ids=game(cards,['Forest','Llanowar Elves','Sol Ring'])
    cast(s,'Bounty of Skemfar',{'G':1,'C':2})
    settle(s)
    choose(s,[ids[0]])
    settle(s)
    choose(s,[ids[1]])
    answer(s)
    roundtrip(s)
    assert s.state.cards[ids[0]].zone=='p1:battlefield' and s.state.cards[ids[0]].tapped
    assert s.state.cards[ids[1]].zone=='p1:hand'
    assert s.state.cards[ids[2]].zone=='p1:library' and not s.state.cards[ids[2]].revealed_to


def test_wakanda_entry_counter_before_entry_and_second_hand(cards):
    s,ids=game(cards,['Trained Armodon','Forest','Sol Ring'])
    put(s,'Doubling Season','battlefield')
    cast(s,'Wakanda Forever!',{'G':2,'C':4})
    settle(s)
    choose(s,[ids[0]])
    settle(s)
    choose(s,[ids[1]])
    answer(s)
    roundtrip(s)
    assert s.state.cards[ids[0]].zone=='p1:battlefield'
    assert s.state.cards[ids[0]].counters.get('indestructible')==2
    assert s.state.cards[ids[1]].zone=='p1:hand' and s.state.cards[ids[2]].zone=='p1:graveyard'


def test_wakanda_failed_entry_remains_available_for_hand(cards):
    s,ids=game(cards,['Trained Armodon','Sol Ring'])
    put(s,"Grafdigger's Cage",'battlefield')
    cast(s,'Wakanda Forever!',{'G':2,'C':4})
    settle(s)
    choose(s,[ids[0]])
    settle(s)
    assert ids[0] in {o.id for o in s.state.rules.decision.options}
    choose(s,[ids[0]])
    answer(s)
    roundtrip(s)
    assert s.state.cards[ids[0]].zone=='p1:hand' and s.state.cards[ids[0]].counters.get('indestructible',0)==0
    assert s.state.cards[ids[1]].zone=='p1:graveyard'


def test_bounty_decline_first_accept_elf_cold(cards,tmp_path):
    s,ids=game(cards,['Forest','Llanowar Elves'])
    cast(s,'Bounty of Skemfar',{'G':1,'C':2})
    settle(s)
    choose(s,[])
    settle(s)
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_hidden_card_facts import choose
choose(s,[args[0]])
answer(s)
assert s.state.cards[args[0]].zone=='p1:hand'
assert s.state.cards[args[1]].zone=='p1:library'
""",ids[1],ids[0])


def test_green_chosen_shared_destination_cold(cards,tmp_path):
    s,ids=game(cards,['Forest','Trained Armodon'])
    cast(s,"Green Sun's Twilight",{'G':1,'C':5},x_value=5)
    settle(s)
    choose(s,ids)
    settle(s)
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_hidden_card_facts import choose
choose(s,['battlefield'])
answer(s)
assert all(s.state.cards[c].zone=='p1:battlefield' for c in args)
""",*ids)


def test_wakanda_replaced_original_library_object_is_not_followed(cards):
    from app.rules.plan import Plan
    s,ids=game(cards,['Trained Armodon','Sol Ring'])
    put(s,"Grafdigger's Cage",'battlefield')
    cast(s,'Wakanda Forever!',{'G':2,'C':4})
    settle(s)
    choose(s,[ids[0]])
    settle(s)
    old=Plan(s.state,'p1',s.cards,None).oid(ids[0])
    act(s,'p1',type='move',card_ids=[ids[0]],to={'player':'p1','zone':'hand'})
    act(s,'p1',type='move',card_ids=[ids[0]],to={'player':'p1','zone':'library'})
    assert Plan(s.state,'p1',s.cards,None).oid(ids[0])!=old
    # The saved decision names the old library incarnation, not this new one.
    choose(s,[ids[0]])
    answer(s)
    roundtrip(s)
    assert s.state.cards[ids[0]].zone=='p1:library'
    assert s.state.cards[ids[1]].zone=='p1:graveyard'
