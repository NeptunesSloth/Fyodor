"""Canonical collateral: literal card names remain fixed in counters and token grants."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Pious Kitsune','Sound the Call','Eight-and-a-Half-Tails','Song of the Dryads','Doubling Season','Solemnity','Call of the Conclave','Grizzly Bears']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/named_counter_collateral_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='ncc',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    return table(cards,NAMES,NAMES,NAMES)


def cast(s,name,pid='p1',targets=()):
    c=put(s,name,'hand',pid)
    pay(s,pid,name)
    for _ in range(12):
        if s.state.rules.priority==pid:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    act(s,pid,type='cast_spell',card_id=c.id,targets=list(targets),sources=[])
    settle(s)
    return c


def ch(s,c):
    return Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c.id])


def tokens(s):
    return [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(':battlefield')]


@pytest.mark.parametrize('name',['Pious Kitsune','Sound the Call'])
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('tails_pid',[None,'p1','p2','p3'])
def test_pious_real_upkeep_requires_exact_named_creature_any_controller(cards,tails_pid):
    s=game(cards)
    c=cast(s,'Pious Kitsune')
    if tails_pid:
        put(s,'Eight-and-a-Half-Tails','battlefield',tails_pid)
    else:
        put(s,'Eight-and-a-Half-Tails','graveyard','p2')
        put(s,'Grizzly Bears','battlefield','p3')
    act(s,'p1',type='set_counter',card_id=c.id,kind='devotion',value=2)
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[c.id].counters['devotion']==3
    assert s.state.players['p1'].life==(43 if tails_pid else 40)
    roundtrip(s)


def test_pious_named_permanent_that_is_no_longer_a_creature_does_not_qualify(cards):
    s=game(cards)
    c=cast(s,'Pious Kitsune')
    other=put(s,'Eight-and-a-Half-Tails','battlefield','p2')
    cast(s,'Song of the Dryads',targets=[other.id])
    assert ch(s,other).name=='Eight-and-a-Half-Tails' and not ch(s,other).is_creature
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[c.id].counters['devotion']==1
    assert s.state.players['p1'].life==40
    roundtrip(s)


@pytest.mark.parametrize('block',[False,True])
def test_pious_counts_actual_post_replacement_counters_even_if_no_counter_added(cards,block):
    s=game(cards)
    c=cast(s,'Pious Kitsune')
    put(s,'Eight-and-a-Half-Tails','battlefield','p2')
    act(s,'p1',type='set_counter',card_id=c.id,kind='devotion',value=2)
    put(s,'Solemnity' if block else 'Doubling Season','battlefield')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[c.id].counters['devotion']==(2 if block else 4)
    assert s.state.players['p1'].life==(42 if block else 44)
    roundtrip(s)


def test_pious_actual_activated_cost_removes_one_devotion_and_gains_one(cards):
    s=game(cards)
    c=put(s,'Pious Kitsune','battlefield')
    act(s,'p1',type='set_counter',card_id=c.id,kind='devotion',value=3)
    to_phase(s,'main1',turn=4)
    # Its upkeep adds one counter without the named creature; the tap cost is now legal.
    assert s.state.cards[c.id].counters['devotion']==4
    act(s,'p1',type='activate_ability',card_id=c.id,ability=ability_index(s,c,'You gain 1 life'),sources=[])
    settle(s)
    assert s.state.cards[c.id].tapped and s.state.cards[c.id].counters['devotion']==3
    assert s.state.players['p1'].life==41
    roundtrip(s)


def test_sound_resolving_spell_joins_graveyard_then_dynamic_token_updates(cards):
    s=game(cards)
    spell=cast(s,'Sound the Call')
    wolf=tokens(s)[0]
    assert ch(s,wolf).pt==(2,2) and ch(s,wolf).base_pt==(1,1)
    assert ch(s,wolf).colors=={'G'} and 'Wolf' in ch(s,wolf).subtypes
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    put(s,'Sound the Call','exile')
    assert ch(s,wolf).pt==(1,1)
    put(s,'Sound the Call','graveyard')
    assert ch(s,wolf).pt==(2,2)
    roundtrip(s)


def test_sound_counts_exact_name_in_all_graveyards_not_controller_or_other_calls(cards):
    s=game(cards)
    a=cast(s,'Sound the Call')
    wolf=tokens(s)[0]
    put(s,'Sound the Call','graveyard','p2')
    put(s,'Sound the Call','graveyard','p3')
    put(s,'Call of the Conclave','graveyard','p2')
    put(s,'Pious Kitsune','graveyard','p3')
    assert ch(s,wolf).pt==(4,4) and ch(s,wolf).base_pt==(1,1)
    act(s,'p1',type='set_controller',card_ids=[wolf.id],player='p2')
    assert ch(s,wolf).pt==(4,4)
    put(s,'Sound the Call','hand','p3')
    assert ch(s,wolf).pt==(3,3)
    assert s.state.cards[a.id].zone=='p1:graveyard'
    roundtrip(s)


def test_sound_second_actual_cast_updates_tokens_created_by_both_players(cards):
    s=game(cards)
    cast(s,'Sound the Call')
    first=tokens(s)[0]
    to_phase(s,'main1',turn=2)
    cast(s,'Sound the Call','p2')
    wolves=tokens(s)
    assert len(wolves)==2 and {x.controller for x in wolves}=={'p1','p2'}
    assert all(ch(s,x).pt==(3,3) and ch(s,x).base_pt==(1,1) for x in wolves)
    put(s,'Sound the Call','exile','p1')
    assert all(ch(s,x).pt==(2,2) for x in wolves)
    assert first.id in {x.id for x in wolves}
    roundtrip(s)
