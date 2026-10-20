"""Canonical payment-dependent effects reuse native casts, triggers and choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, history
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Once and Future','Outmuscle',"Cauldron's Gift",'Sundering Stroke']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/adamant_entry_payment_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='sme',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/adamant_entry_payment_cards.json').read_text())]
    s=table(cards,names,names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    return s


def cast(s,name,pool,targets=(),pid='p1',**kwargs):
    wait_priority(s,pid)
    c=put(s,name,'hand',pid=pid)
    if pool:
        act(s,pid,type='add_mana',player=pid,mana=pool)
    act(s,pid,type='cast_spell',card_id=c.id,targets=list(targets),sources=[],**kwargs)
    return c


def answer(s,optional=True):
    for _ in range(100):
        settle(s)
        d=s.state.rules.decision
        if d is None:
            return
        ids={o.id for o in d.options}
        if 'keep' in ids:
            chosen=['keep']
        elif 'yes' in ids:
            chosen=['yes' if optional else 'no']
        elif 'p3' in ids:
            chosen=['p3']
        else:
            chosen=[o.id for o in d.options][:max(1,d.min_choices)]
        act(s,d.player,type='choose',decision_id=d.id,option_ids=chosen)
    raise AssertionError('Decisions did not finish')


def drawn(s,pid='p1'):
    return history.log_for(Plan(s.state,'p1',s.cards,None)).drew.get(pid,0)


def permanents(s,word,pid='p1'):
    plan=Plan(s.state,pid,s.cards,None)
    return [c for c in s.state.cards.values() if c.zone==pid+':battlefield' and word in plan.ch(c).subtypes]


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('red',[6,7])
def test_stroke_announced_division_versus_actual_red_payment(cards,red):
    s=game(cards)
    cast(s,'Sundering Stroke',{'R':red,'C':7-red},['p2','p3'],target_counts=[2],division=[3,4])
    answer(s)
    assert s.state.players['p2'].life==40-(7 if red==7 else 3)
    assert s.state.players['p3'].life==40-(7 if red==7 else 4)
    roundtrip(s)


@pytest.mark.parametrize('green',[2,3])
@pytest.mark.parametrize('extra',[False,True])
def test_once_and_future_destinations_keep_announced_distinct_groups(cards,green,extra):
    s=game(cards)
    first=put(s,'Grizzly Bears','graveyard')
    second=put(s,'Ornithopter','graveyard')
    spell=cast(s,'Once and Future',{'G':green,'C':4-green},[first.id,*([second.id] if extra else [])],target_counts=[1,int(extra)])
    answer(s)
    assert s.state.cards[first.id].zone=='p1:hand'
    assert s.state.cards[second.id].zone==('p1:hand' if extra and green==3 else 'p1:library' if extra else 'p1:graveyard')
    assert s.state.cards[spell.id].zone=='p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('green',[2,3])
@pytest.mark.parametrize('opponent_gone',[False,True])
def test_outmuscle_counter_then_fight_then_indestructible_saves_lethal(cards,green,opponent_gone):
    s=game(cards)
    ours=put(s,'Grizzly Bears','battlefield')
    theirs=put(s,'Colossal Dreadmaw','battlefield',pid='p2')
    cast(s,'Outmuscle',{'G':green,'C':4-green},[ours.id,theirs.id],target_counts=[1,1])
    if opponent_gone:
        act(s,'p2',type='move',card_ids=[theirs.id],to={'player':'p2','zone':'exile'})
    answer(s)
    assert s.state.cards[ours.id].zone==('p1:battlefield' if green==3 or opponent_gone else 'p1:graveyard')
    if s.state.cards[ours.id].zone=='p1:battlefield':
        assert s.state.cards[ours.id].counters.get('+1/+1')==1
        assert ('indestructible' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[ours.id]).keywords)==(green==3)
        if opponent_gone:
            to_phase(s,'upkeep',2)
            assert 'indestructible' not in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[ours.id]).keywords
    roundtrip(s)


@pytest.mark.parametrize('black',[2,3])
def test_cauldron_mill_is_compulsory_return_is_optional(cards,black):
    s=game(cards)
    before=len(s.state.zones['p1:library'])
    cast(s,"Cauldron's Gift",{'B':black,'C':5-black})
    settle(s)
    assert len(s.state.zones['p1:library'])==before-1-(4 if black==3 else 0)
    d=s.state.rules.decision
    if d is not None:
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    answer(s)
    roundtrip(s)


@pytest.mark.parametrize('suppression',[None,'Humility','Dress Down'])
@pytest.mark.parametrize('free',[False,True])
def test_primeval_paid_or_free_prospective_ability_suppression(cards,suppression,free):
    s=game(cards)
    if suppression:
        put(s,suppression,'battlefield')
    if free:
        put(s,'Omniscience','battlefield')
    spell=cast(s,'Primeval Spawn',{} if free else {'W':1,'U':1,'B':1,'R':1,'G':1,'C':5},free=free)
    roundtrip(s)
    answer(s)
    assert s.state.cards[spell.id].zone==('p1:exile' if free and suppression is None else 'p1:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('suppression',[None,'Humility'])
def test_primeval_reanimation_never_enters_unless_own_rule_suppressed(cards,suppression):
    s=game(cards)
    if suppression:
        put(s,suppression,'battlefield')
    target=put(s,'Primeval Spawn','graveyard')
    cast(s,'Reanimate',{'B':1},[target.id])
    answer(s)
    assert s.state.cards[target.id].zone==('p1:exile' if suppression is None else 'p1:battlefield')
    # A diverted creature never leaves the battlefield and cannot exile top ten.
    assert len([c for c in s.state.cards.values() if c.zone=='p1:exile'])==(1 if suppression is None else 0)
    roundtrip(s)


def test_primeval_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve('Primeval Spawn')).level=='FULL'


def test_paid_clone_applies_copy_then_uses_its_own_paid_cast_record(cards):
    s=game(cards)
    spawn=put(s,'Primeval Spawn','battlefield')
    clone=cast(s,'Clone',{'U':1,'C':3})
    settle(s)
    d=s.state.rules.decision
    assert d is not None and spawn.id in {o.id for o in d.options}
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[spawn.id])
    answer(s)
    assert s.state.cards[clone.id].zone=='p1:battlefield'
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[clone.id]).name=='Primeval Spawn'
    roundtrip(s)


@pytest.mark.parametrize('suppression',[None,'Humility'])
def test_quasiduplicate_spawn_recipe_diverts_before_etb_or_ltb(cards,suppression):
    s=game(cards)
    spawn=put(s,'Primeval Spawn','battlefield')
    if suppression:
        put(s,suppression,'battlefield')
    cast(s,'Quasiduplicate',{'U':2,'C':1},[spawn.id])
    answer(s)
    tokens=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield']
    assert len(tokens)==(1 if suppression else 0)
    assert not s.state.zones['p1:exile']
    roundtrip(s)


def test_double_major_spawn_spell_copy_was_not_cast_and_did_not_spend_mana(cards):
    s=game(cards)
    original=cast(s,'Primeval Spawn',{'W':1,'U':1,'B':1,'R':1,'G':1,'C':5})
    cast(s,'Double Major',{'U':1,'G':1},[original.id])
    answer(s)
    assert s.state.cards[original.id].zone=='p1:battlefield'
    assert not [c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield']
    assert not s.state.zones['p1:exile']
    roundtrip(s)


def test_cauldron_chooses_newly_milled_zero_toughness_creature_and_entry_counter(cards):
    s=game(cards)
    wait_priority(s,'p1')
    target=put(s,'Walking Ballista','library')
    act(s,'p1',type='move',card_ids=[target.id],to={'player':'p1','zone':'library'},index=0)
    # Keep the spell off the top before the first normal draw.
    put(s,"Cauldron's Gift",'hand')
    cast(s,"Cauldron's Gift",{'B':3,'C':2})
    settle(s)
    d=s.state.rules.decision
    assert d is not None and target.id in {o.id for o in d.options}
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    answer(s)
    assert s.state.cards[target.id].zone=='p1:battlefield'
    assert s.state.cards[target.id].counters.get('+1/+1')==1
    roundtrip(s)


def test_stroke_copy_keeps_announced_division_and_does_not_inherit_red_payment(cards):
    s=game(cards)
    original=cast(s,'Sundering Stroke',{'R':7},['p2','p3'],target_counts=[2],division=[3,4])
    cast(s,'Reverberate',{'R':2},[original.id])
    answer(s)
    assert s.state.players['p2'].life==30
    assert s.state.players['p3'].life==29
    roundtrip(s)


def test_stroke_invalid_target_does_not_redivide_ordinary_branch(cards):
    s=game(cards)
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,'Sundering Stroke',{'R':6,'C':1},[target.id,'p3'],target_counts=[2],division=[3,4])
    act(s,'p2',type='move',card_ids=[target.id],to={'player':'p2','zone':'exile'})
    answer(s)
    assert s.state.players['p3'].life==36
    roundtrip(s)


def test_spending_as_though_red_does_not_turn_colorless_into_actual_red(cards):
    s=game(cards)
    put(s,'Mycosynth Lattice','battlefield')
    cast(s,'Sundering Stroke',{'C':7},['p2','p3'],target_counts=[2],division=[3,4])
    answer(s)
    assert s.state.players['p2'].life==37 and s.state.players['p3'].life==36
    roundtrip(s)


@pytest.mark.parametrize('extra',[None,'Doubling Season',"Grafdigger's Cage"])
def test_cauldron_additional_entry_counter_and_native_entry_restriction(cards,extra):
    s=game(cards)
    wait_priority(s,'p1')
    target=put(s,'Grizzly Bears','graveyard')
    if extra:
        put(s,extra,'battlefield')
    cast(s,"Cauldron's Gift",{'B':1,'C':4})
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    answer(s)
    assert s.state.cards[target.id].zone==('p1:graveyard' if extra=="Grafdigger's Cage" else 'p1:battlefield')
    if extra!="Grafdigger's Cage":
        assert s.state.cards[target.id].counters.get('+1/+1')==(2 if extra=='Doubling Season' else 1)
    roundtrip(s)


def test_primeval_leaving_a_paid_permanent_uses_native_ten_card_permission(cards):
    s=game(cards)
    source=cast(s,'Primeval Spawn',{'W':1,'U':1,'B':1,'R':1,'G':1,'C':5})
    answer(s)
    before=len(s.state.zones['p1:library'])
    cast(s,'Swords to Plowshares',{'W':1},[source.id],pid='p2')
    settle(s)
    assert len(s.state.zones['p1:library'])==before-10, repr(s.state.rules.decision)
    d=s.state.rules.decision
    assert d is not None
    roundtrip(s)
    ids={o.id for o in d.options}
    # Declining the native optional cast does not return the exiled cards.
    stop=next((x for x in ('done','no','decline','skip') if x in ids),None)
    if stop is not None:
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[stop])
    else:
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    answer(s,optional=False)
    assert len([cid for cid in s.state.zones['p1:exile'] if cid!=source.id])==10
    roundtrip(s)
