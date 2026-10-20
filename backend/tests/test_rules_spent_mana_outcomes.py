"""Actual Oracle paid-mana outcomes preserve target decisions and native events."""
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
from tests.test_rules_discard_outcomes import clear_hand, cold_run
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_mana_delayed_effects import answer, cast, drawn
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA=Path(__file__).parent/'fixtures/spent_mana_outcomes_cards.json'
NAMES=[c['name'] for c in json.loads(DATA.read_text())][:15]

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads(DATA.read_text())):
        base[c['name']]=card(c['name'],set_code='smo36',number=str(i),**{k:v for k,v in c.items() if k!='name'})
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

def ch(s,c):
    return Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c.id])

@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'

@pytest.mark.parametrize('both',[False,True])
def test_dawnglow_one_gain_event(cards,both):
    s=game(cards)
    bear=put(s,"Ajani's Pridemate",'battlefield')
    life=s.state.players['p1'].life
    cast(s,'Dawnglow Infusion',{'G':1,'W':1,'C':2} if both else {'G':1,'C':3},x_value=3)
    answer(s)
    roundtrip(s)
    assert s.state.players['p1'].life==life+(6 if both else 3)
    assert s.state.cards[bear.id].counters.get('+1/+1')==1

@pytest.mark.parametrize('both',[False,True])
def test_nethroi_noncreature_target_legal_without_bonus(cards,both):
    s=game(cards)
    target=put(s,'Sol Ring','battlefield','p2')
    cast(s,'Mythos of Nethroi',{'B':1,'G':1,'W':1} if both else {'B':1,'C':2},[target.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[target.id].zone==('p2:graveyard' if both else 'p2:battlefield')

def test_torrent_returns_then_pumps_same_creature(cards):
    s=game(cards)
    c=put(s,'Trained Armodon','graveyard')
    cast(s,'Torrent of Souls',{'B':1,'R':1,'C':3},[c.id,'p1'],target_counts=[1,1])
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone=='p1:battlefield'
    assert ch(s,c).pt==(5,3) and 'haste' in ch(s,c).keywords

@pytest.mark.parametrize('name,colors', [('Invert the Skies',{'G':1,'U':1,'C':2}),('Unnerving Assault',{'U':1,'R':1,'C':1})])
def test_conditional_sets_frozen(cards,name,colors):
    s=game(cards)
    mine=put(s,'Trained Armodon','battlefield')
    theirs=put(s,'Shivan Dragon','battlefield','p2')
    cast(s,name,colors)
    answer(s)
    later=put(s,'Llanowar Elves','battlefield')
    if name=='Invert the Skies':
        assert 'flying' in ch(s,mine).keywords and 'flying' not in ch(s,theirs).keywords
        assert 'flying' not in ch(s,later).keywords
    else:
        assert ch(s,mine).pt==(4,3) and ch(s,theirs).pt==(4,5)
        assert ch(s,later).pt==(1,1)
    roundtrip(s)

def test_cankerous_two_required_targets_independent_optional_actions(cards):
    s=game(cards)
    a=put(s,'Shivan Dragon','battlefield','p2')
    b=put(s,'Trained Armodon','battlefield')
    cast(s,'Cankerous Thirst',{'B':1,'G':1,'C':2},[a.id,b.id],target_counts=[1,1])
    answer(s)
    roundtrip(s)
    assert ch(s,a).pt==(2,2) and ch(s,b).pt==(6,6)

def test_rivers_grasp_return_precedes_revealed_hand_choice(cards):
    s=game(cards)
    clear_hand(s,'p2')
    c=put(s,'Trained Armodon','battlefield','p2')
    cast(s,"River's Grasp",{'U':1,'B':1,'C':2},[c.id,'p2'],target_counts=[1,1])
    settle(s)
    assert s.state.cards[c.id].zone=='p2:hand'
    choose(s,[c.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone=='p2:graveyard'

def test_bladecoil_all_pair_effects(cards):
    s=game(cards)
    clear_hand(s,'p2')
    clear_hand(s,'p3')
    a=put(s,'Forest','hand','p2')
    b=put(s,'Forest','hand','p3')
    before=drawn(s)
    c=cast(s,'Bladecoil Serpent',{'U':2,'B':2,'R':2},x_value=0)
    answer(s)
    roundtrip(s)
    assert drawn(s)==before+1
    assert s.state.cards[a.id].zone=='p2:graveyard' and s.state.cards[b.id].zone=='p3:graveyard'
    assert ch(s,c).pt==(6,4) and {'haste','trample'}<=set(ch(s,c).keywords)

def test_flash_conscripting_granted_combat_life(cards):
    s=game(cards)
    c=put(s,'Trained Armodon','battlefield','p2')
    cast(s,'Flash Conscription',{'R':1,'W':1,'C':4},[c.id])
    answer(s)
    assert s.state.cards[c.id].controller=='p1'
    before=s.state.players['p1'].life
    to_phase(s,'declare_attackers',4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':c.id,'target':'p2'}])
    to_phase(s,'main2',4)
    answer(s)
    roundtrip(s)
    assert s.state.players['p1'].life==before+3

def test_batwing_attackers_loss_and_prevention(cards):
    s=game(cards)
    c=put(s,'Trained Armodon','battlefield')
    to_phase(s,'declare_attackers',7)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':c.id,'target':'p2'}])
    before=s.state.players['p2'].life
    mine=s.state.players['p1'].life
    cast(s,'Batwing Brume',{'W':1,'B':1})
    answer(s)
    to_phase(s,'main2',7)
    roundtrip(s)
    assert s.state.players['p1'].life==mine-1 and s.state.players['p2'].life==before

def test_boros_fury_shield_spell_deals_power(cards):
    s=game(cards)
    c=put(s,'Trained Armodon','battlefield')
    to_phase(s,'declare_attackers',7)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':c.id,'target':'p2'}])
    mine=s.state.players['p1'].life
    theirs=s.state.players['p2'].life
    cast(s,'Boros Fury-Shield',{'W':1,'R':1,'C':1},[c.id])
    answer(s)
    to_phase(s,'main2',7)
    roundtrip(s)
    assert s.state.players['p1'].life==mine-3 and s.state.players['p2'].life==theirs

def test_vadrok_damage_prevented_still_restricts(cards):
    s=game(cards)
    c=put(s,'Darksteel Myr','battlefield','p2')
    cast(s,'Mythos of Vadrok',{'R':2,'W':1,'U':1},[c.id],target_counts=[1])
    answer(s)
    roundtrip(s)
    assert {'cant_attack_or_block','cant_activate'}<=set(ch(s,c).imposed)

def test_moonhold_both_limits(cards):
    s=game(cards)
    cast(s,'Moonhold',{'R':1,'W':1,'C':1},['p2'])
    answer(s)
    from app.rules import cast_limits
    p=Plan(s.state,'p2',s.cards,None)
    put(s,'Trained Armodon','hand','p2')
    land=put(s,'Forest','hand','p2')
    assert cast_limits.land_problem(s.state,'p2',p.ch(land),p.info)
    assert any(x.get('filter') for x in s.state.rules.cast_limits)
    roundtrip(s)

def test_devour_treasure_replaces_discard(cards):
    s=game(cards)
    clear_hand(s,'p2')
    a=put(s,'Forest','hand','p2')
    b=put(s,'Sol Ring','hand','p2')
    treasure=put(s,'Treasure','battlefield')
    spell=put(s,'Devour Intellect','hand')
    from tests.test_rules_bandmate_references import wait_priority
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=['p2'],sources=[treasure.id])
    settle(s)
    d=s.state.rules.decision
    assert d.player=='p1' and b.id in {o.id for o in d.options} and a.id not in {o.id for o in d.options}
    choose(s,[b.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[b.id].zone=='p2:graveyard'

@pytest.mark.parametrize('colorless',[False,True])
def test_wumpus_actual_spent_colorless_gate(cards,colorless):
    s=game(cards)
    clear_hand(s,'p2')
    c=put(s,'Trained Armodon','hand','p2')
    spell=cast(s,'Wumpus Aberration',{'G':1,'C':3} if colorless else {'G':1,'R':3})
    settle(s)
    if not colorless:
        choose(s,['p2'])
        settle(s)
        assert s.state.rules.decision.player=='p2'
        choose(s,[c.id])
        answer(s)
        assert s.state.cards[c.id].zone=='p2:battlefield'
    else:
        assert not s.state.rules.decision
        answer(s)
        assert s.state.cards[c.id].zone=='p2:hand'
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    roundtrip(s)


def test_dawnglow_copy_keeps_x_but_no_paid_colors(cards):
    s=game(cards)
    before=s.state.players['p1'].life
    spell=cast(s,'Dawnglow Infusion',{'G':1,'W':1,'C':2},x_value=3)
    cast(s,'Reverberate',{'R':2},[spell.id])
    answer(s)
    roundtrip(s)
    assert s.state.players['p1'].life==before+6


def test_nethroi_as_though_does_not_change_actual_paid_colors(cards):
    s=game(cards)
    put(s,'Mycosynth Lattice','battlefield')
    c=put(s,'Sol Ring','battlefield','p2')
    cast(s,'Mythos of Nethroi',{'C':3},[c.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone=='p2:battlefield'


def test_vadrok_prevention_still_restricts_and_expires_next_turn(cards):
    s=game(cards)
    put(s,'Mark of Asylum','battlefield','p2')
    c=put(s,'Trained Armodon','battlefield','p2')
    cast(s,'Mythos of Vadrok',{'R':2,'U':1,'W':1},[c.id],target_counts=[1])
    answer(s)
    assert s.state.cards[c.id].damage==0
    assert {'cant_attack_or_block','cant_activate'}<=set(ch(s,c).imposed)
    to_phase(s,'main1',7)
    roundtrip(s)
    assert 'cant_activate' not in ch(s,c).imposed


def test_vadrok_partial_illegal_preserves_other_division_and_restriction(cards):
    s=game(cards)
    a=put(s,'Darksteel Myr','battlefield','p2')
    b=put(s,'Shivan Dragon','battlefield','p2')
    cast(s,'Mythos of Vadrok',{'R':2,'U':1,'W':1},[a.id,b.id],target_counts=[2],division=[2,3])
    act(s,'p2',type='move',card_ids=[a.id],to={'player':'p2','zone':'hand'})
    answer(s)
    roundtrip(s)
    assert s.state.cards[b.id].damage==3 and 'cant_activate' in ch(s,b).imposed
    assert 'cant_activate' not in ch(s,a).imposed


def test_cankerous_decline_first_accept_second_cold(cards,tmp_path):
    s=game(cards)
    a=put(s,'Shivan Dragon','battlefield','p2')
    b=put(s,'Trained Armodon','battlefield')
    cast(s,'Cankerous Thirst',{'B':1,'G':1,'C':2},[a.id,b.id],target_counts=[1,1])
    settle(s)
    choose(s,['no'])
    settle(s)
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_spent_mana_outcomes import ch
answer(s)
assert ch(s,s.state.cards[args[0]]).pt==(5,5)
assert ch(s,s.state.cards[args[1]]).pt==(6,6)
""",a.id,b.id)


def test_river_private_choice_cold_resume(cards,tmp_path):
    s=game(cards)
    clear_hand(s,'p2')
    c=put(s,'Sol Ring','hand','p2')
    cast(s,"River's Grasp",{'B':1,'C':3},['p2'],target_counts=[0,1])
    settle(s)
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_hidden_card_facts import choose
choose(s,[args[0]])
answer(s)
assert s.state.cards[args[0]].zone=='p2:graveyard'
""",c.id)


def test_dawnglow_paid_stack_cold_resume(cards,tmp_path):
    s=game(cards)
    before=s.state.players['p1'].life
    cast(s,'Dawnglow Infusion',{'G':1,'W':1,'C':2},x_value=3)
    cold_run(s,cards,tmp_path,"answer(s)\nassert s.state.players['p1'].life==int(args[0])+6\n",str(before))


def test_wumpus_trigger_survives_countered_source_cold(cards,tmp_path):
    s=game(cards)
    clear_hand(s,'p2')
    creature=put(s,'Trained Armodon','hand','p2')
    spell=cast(s,'Wumpus Aberration',{'G':1,'R':3})
    settle(s)
    choose(s,['p2'])
    cast(s,'Counterspell',{'U':2},[spell.id])
    # Resolve Counterspell, leaving the independently targeted cast trigger.
    while s.state.cards[spell.id].zone=='stack':
        act(s,s.state.rules.priority,type='pass_priority')
    settle(s)
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_hidden_card_facts import choose
choose(s,[args[0]])
answer(s)
assert s.state.cards[args[0]].zone=='p2:battlefield'
assert s.state.cards[args[1]].zone=='p1:graveyard'
""",creature.id,spell.id)


def test_devour_filter_input_treasure_does_not_pay_spell(cards):
    s=game(cards)
    clear_hand(s,'p2')
    a=put(s,'Forest','hand','p2')
    put(s,'Sol Ring','hand','p2')
    treasure=put(s,'Treasure','battlefield')
    signet=put(s,'Dimir Signet','battlefield')
    spell=put(s,'Devour Intellect','hand')
    from tests.test_rules_bandmate_references import wait_priority
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=treasure.id,ability=0,mana_choice='R')
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=['p2'],sources=[signet.id])
    settle(s)
    d=s.state.rules.decision
    assert d.player=='p2' and a.id in {o.id for o in d.options}
    choose(s,[a.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[a.id].zone=='p2:graveyard'


def test_cankerous_unpaid_black_still_requires_first_target(cards):
    from app.game.errors import ActionError
    s=game(cards)
    a=put(s,'Trained Armodon','battlefield')
    spell=put(s,'Cankerous Thirst','hand')
    from tests.test_rules_bandmate_references import wait_priority
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'G':1,'C':3})
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,targets=[a.id],target_counts=[0,1],sources=[])
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[a.id,a.id],target_counts=[1,1],sources=[])
    answer(s)
    roundtrip(s)
    assert ch(s,a).pt==(6,6)


def test_bladecoil_odd_mana_pairs_round_down(cards):
    s=game(cards)
    before=drawn(s)
    spell=cast(s,'Bladecoil Serpent',{'U':3,'R':3},x_value=0)
    answer(s)
    roundtrip(s)
    assert drawn(s)==before+1 and ch(s,spell).pt==(6,4)


def test_nethroi_resolves_creature_type_even_without_green_white(cards):
    s=game(cards)
    c=put(s,'Trained Armodon','battlefield','p2')
    cast(s,'Mythos of Nethroi',{'B':1,'C':2},[c.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone=='p2:graveyard'


def test_boros_without_red_only_prevents(cards):
    s=game(cards)
    c=put(s,'Trained Armodon','battlefield')
    to_phase(s,'declare_attackers',7)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':c.id,'target':'p2'}])
    before=[s.state.players[p].life for p in ['p1','p2']]
    cast(s,'Boros Fury-Shield',{'W':1,'C':2},[c.id])
    answer(s)
    to_phase(s,'main2',7)
    roundtrip(s)
    assert [s.state.players[p].life for p in ['p1','p2']]==before
