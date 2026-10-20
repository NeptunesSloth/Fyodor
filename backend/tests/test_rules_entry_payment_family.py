"""Actual cast payments control entry counters for the exact entering incarnation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave18b_mana import treasure
from tests.test_rules_wave30m_durations import settle as answer

NAMES=['Kalain, Reclusive Painter','Wildgrowth Archaic','Steel Exemplar','Freestrider Commando','Clay Champion']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/entry_payment_family_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='epf',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards,extras=()):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/entry_payment_family_cards.json').read_text())]
    s=table(cards,names,names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    for name in extras:
        put(s,name,'battlefield')
    return s


def mana(s,**pool):
    act(s,'p1',type='add_mana',player='p1',mana=pool)


def use_treasure(s,color):
    before=set(s.state.cards)
    treasure(s)
    token=next(c for cid,c in s.state.cards.items() if cid not in before and c.name=='Treasure')
    act(s,'p1',type='activate_ability',card_id=token.id,ability=0,mana_choice=color)
    return token


def cast(s,name,pool=None,**extra):
    source=put(s,name,'hand')
    if pool:
        mana(s,**pool)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],**extra)
    roundtrip(s)
    return source


def counters(s,c):
    return s.state.cards[c.id].counters.get('+1/+1',0)


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('count',[0,1,2])
def test_kalain_counts_actual_treasure_mana_for_entering_creature(cards,count):
    s=game(cards,['Kalain, Reclusive Painter'])
    for color in ('G','R')[:count]:
        use_treasure(s,color)
    source=cast(s,'Grizzly Bears',{'G':1,'C':1} if count==0 else {'C':1} if count==1 else None)
    settle(s)
    assert counters(s,source)==count
    roundtrip(s)


def test_real_kalain_etb_treasure_does_not_put_counters_on_kalain_itself(cards):
    s=game(cards)
    use_treasure(s,'R')
    source=cast(s,'Kalain, Reclusive Painter',{'B':1})
    settle(s)
    assert counters(s,source)==0
    token=next(c for c in s.state.cards.values() if c.name=='Treasure' and c.zone=='p1:battlefield')
    act(s,'p1',type='activate_ability',card_id=token.id,ability=0,mana_choice='G')
    bear=cast(s,'Grizzly Bears',{'C':1})
    settle(s)
    assert counters(s,bear)==1
    roundtrip(s)


def test_kalain_does_not_reuse_old_incarnation_treasure_payment_on_reanimation(cards):
    s=game(cards,['Kalain, Reclusive Painter'])
    use_treasure(s,'G')
    source=cast(s,'Grizzly Bears',{'C':1})
    settle(s)
    assert counters(s,source)==1
    old=s.state.rules.object_id(source.id)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    assert old in s.state.rules.payments  # Retained LKI must not be mistaken for the new object.
    cast(s,'Reanimate',{'B':1},targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield' and counters(s,source)==0
    roundtrip(s)


@pytest.mark.parametrize(('pool','expected'),[({'G':5},2),({'W':1,'U':1,'B':1,'R':1,'G':1},0),({'G':4,'C':1},2)])
def test_steel_exemplar_uses_distinct_actual_colors(cards,pool,expected):
    s=game(cards)
    source=cast(s,'Steel Exemplar',pool)
    settle(s)
    assert counters(s,source)==expected
    roundtrip(s)


@pytest.mark.parametrize('name',['Steel Exemplar','Freestrider Commando'])
def test_uncast_entry_gets_conditional_counters(cards,name):
    s=game(cards)
    source=put(s,name,'graveyard')
    cast(s,'Reanimate',{'B':1},targets=[source.id])
    settle(s)
    assert counters(s,source)==2
    roundtrip(s)


@pytest.mark.parametrize('free',[False,True])
def test_freestrider_paid_cast_vs_free_cast(cards,free):
    s=game(cards,['Omniscience'] if free else [])
    source=cast(s,'Freestrider Commando',None if free else {'C':2,'G':1},**({'free':True} if free else {}))
    settle(s)
    assert counters(s,source)==(2 if free else 0)
    roundtrip(s)


def test_wildgrowth_uses_creature_spell_payment_not_its_own_payment(cards):
    s=game(cards)
    archaic=cast(s,'Wildgrowth Archaic',{'G':2})
    settle(s)
    assert counters(s,archaic)==1
    source=cast(s,'Grizzly Bears',{'G':1,'U':1})
    settle(s)
    assert counters(s,source)==2
    roundtrip(s)


def test_wildgrowth_trigger_survives_source_departure(cards):
    s=game(cards)
    archaic=cast(s,'Wildgrowth Archaic',{'G':2})
    settle(s)
    source=cast(s,'Grizzly Bears',{'G':1,'U':1})
    act(s,'p1',type='move',card_ids=[archaic.id],to={'player':'p1','zone':'graveyard'})
    settle(s)
    assert counters(s,source)==2
    roundtrip(s)


@pytest.mark.parametrize(('green','white','expected'),[(4,0,6),(3,1,3),(2,2,3),(0,4,0)])
def test_clay_champion_counts_complete_pairs_of_actual_mana(cards,green,white,expected):
    s=game(cards)
    source=cast(s,'Clay Champion',{'G':green,'W':white},x_value=0)
    answer(s)
    assert counters(s,source)==expected
    roundtrip(s)


@pytest.mark.parametrize('expected',[3,4])
def test_kalain_native_counter_replacement_order_is_saved_and_replayed(cards,expected):
    s=game(cards,['Kalain, Reclusive Painter','Hardened Scales','Doubling Season'])
    use_treasure(s,'G')
    source=cast(s,'Grizzly Bears',{'C':1})
    settle(s)
    d=s.state.rules.decision
    assert d is not None and '616.1' in d.prompt
    option=next(o.id for o in d.options if f'{expected} +1/+1' in o.label)
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[option])
    settle(s)
    assert counters(s,source)==expected
    roundtrip(s)


def test_kalain_counter_prohibition_prevents_treasure_entry_counters(cards):
    s=game(cards,['Kalain, Reclusive Painter','Solemnity'])
    use_treasure(s,'G')
    source=cast(s,'Grizzly Bears',{'C':1})
    settle(s)
    assert counters(s,source)==0
    roundtrip(s)


@pytest.mark.parametrize('x',[0,4])
def test_clay_white_pairs_apply_to_each_actual_selected_target(cards,x):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    beast=put(s,'Hollowhenge Beast','battlefield')
    source=cast(s,'Clay Champion',{'W':4,**({'G':4} if x else {})},x_value=x)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and {bear.id,beast.id}<={o.id for o in d.options}
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id,beast.id])
    settle(s)
    assert counters(s,bear)==2 and counters(s,beast)==2
    assert counters(s,source)==(6 if x else 0)
    roundtrip(s)


def test_freestrider_actual_plot_spends_mana_on_plot_not_on_later_cast(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s=game(cards)
    source=put(s,'Freestrider Commando','hand')
    mana(s,C=3,G=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[])
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)
    to_phase(s,'main1',4)
    act(s,'p1',type='cast_spell',card_id=source.id,free=True,sources=[])
    settle(s)
    assert counters(s,source)==2
    roundtrip(s)


@pytest.mark.parametrize('name',['Steel Exemplar','Freestrider Commando'])
def test_actual_token_copy_was_not_cast_and_gets_conditional_entry_counters(cards,name):
    s=game(cards)
    source=cast(s,name,{'G':2,'U':3} if name=='Steel Exemplar' else {'G':1,'C':2})
    settle(s)
    assert counters(s,source)==0
    cast(s,'Twinflame',{'C':1,'R':1},targets=[source.id],target_counts=[1])
    settle(s)
    copied=next(c for c in s.state.cards.values() if c.is_token and c.name==name and c.zone=='p1:battlefield')
    assert counters(s,copied)==2
    roundtrip(s)


def test_kalain_actual_token_copy_does_not_inherit_original_treasure_payment(cards):
    s=game(cards,['Kalain, Reclusive Painter'])
    use_treasure(s,'G')
    source=cast(s,'Grizzly Bears',{'C':1})
    settle(s)
    assert counters(s,source)==1
    cast(s,'Twinflame',{'C':1,'R':1},targets=[source.id],target_counts=[1])
    settle(s)
    copied=next(c for c in s.state.cards.values() if c.is_token and c.name=='Grizzly Bears' and c.zone=='p1:battlefield')
    assert counters(s,copied)==0
    roundtrip(s)


def test_wildgrowth_actual_cast_trigger_can_be_countered_without_entry_bonus(cards):
    s=game(cards)
    archaic=cast(s,'Wildgrowth Archaic',{'G':2})
    settle(s)
    source=cast(s,'Grizzly Bears',{'G':1,'U':1})
    trigger=next(cid for cid,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_card==archaic.id)
    cast(s,'Stifle',{'U':1},targets=[trigger])
    settle(s)
    assert counters(s,source)==0
    roundtrip(s)


def test_clay_etb_resolves_for_remaining_legal_target(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    beast=put(s,'Hollowhenge Beast','battlefield')
    cast(s,'Clay Champion',{'W':4},x_value=0)
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id,beast.id])
    act(s,'p1',type='move',card_ids=[bear.id],to={'player':'p1','zone':'graveyard'})
    settle(s)
    assert counters(s,beast)==2 and counters(s,bear)==0
    roundtrip(s)


def test_steel_exemplar_spend_as_permission_uses_actual_colors_not_mana_symbols(cards):
    s=game(cards,['Mycosynth Lattice'])
    source=cast(s,'Steel Exemplar',{'U':5})
    settle(s)
    assert counters(s,source)==2
    roundtrip(s)
