"""CR 106.3, 201.5, 400.7, 601.2i: cast triggers read mana's exact source."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditionals import settle as choose_all
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

TECUTLAN="Brass's Tunnel-Grinder"
BARRACKS='Thousand Moons Smithy'
POOLS='The Everflowing Well'


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/mana_source_cast_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='sdc',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,name=TECUTLAN,*,pid='p1'):
    names=[TECUTLAN,BARRACKS,POOLS,"Thespian's Stage",'Grizzly Bears','Sol Ring','Lightning Bolt','Walking Ballista',
           'Solemn Simulacrum','Ruby Medallion','Goblin Piker','Forgotten Cave','Twiddle','Counterspell','Marwyn, the Nurturer',
           'Doubling Cube','Dark Ritual','Geosurge','Willbender','Dog Walker','Phyrexian Fleshgorger','Firebending Student','Elvish Spirit Guide','Horizon Stone','Sungrass Prairie','Kalonian Tusker','Forest','Island','Hall of the Bandit Lord','Rain of Riches']
    s=table(cards,names,names,[])
    printing=cards.resolve(name)['id']
    src=next(c for c in s.state.cards.values() if c.card_id==printing and c.owner==pid)
    act(s,pid,type='move',card_ids=[src.id],to={'player':pid,'zone':'battlefield'})
    act(s,pid,type='set_face',card_id=src.id,face=1)
    return s,src


def triggers(s,src):
    return [e for e in s.state.rules.stack.values() if e.kind=='trigger' and e.source_card==src.id]


def bear(s,src,*,floating=False):
    if floating:
        act(s,'p1',type='activate_ability',card_id=src.id,ability=0)
    b=put(s,'Grizzly Bears','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=b.id,**({} if floating else {'sources':[src.id]}))
    return b


@pytest.mark.parametrize('name',[TECUTLAN,BARRACKS,POOLS])
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('floating',[False,True])
def test_tecutlan_exact_mana_source_is_recorded_for_actual_spending(cards,floating):
    s,src=setup(cards)
    b=bear(s,src,floating=floating)
    assert len(triggers(s,src))==1
    paid=s.state.rules.payments[s.state.rules.object_id(b.id)]
    assert paid.mana_sources==[s.state.rules.object_id(src.id)]
    assert paid.mana_spent=={'R':1,'G':1}
    roundtrip(s)
    choose_all(s)
    roundtrip(s)


def test_unspent_floating_source_mana_does_not_trigger(cards):
    s,src=setup(cards)
    act(s,'p1',type='activate_ability',card_id=src.id,ability=0)
    mana(s,C=1,G=1)
    b=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='cast_spell',card_id=b.id)
    assert not triggers(s,src)
    assert s.state.players['p1'].mana_units[0].src==s.state.rules.object_id(src.id)
    assert not s.state.rules.payments[s.state.rules.object_id(b.id)].mana_sources
    choose_all(s)
    roundtrip(s)


def test_other_cave_mana_does_not_trigger(cards):
    s,src=setup(cards)
    cave=put(s,'Forgotten Cave','battlefield')
    mana(s,G=1)
    b=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='cast_spell',card_id=b.id,sources=[cave.id])
    assert not triggers(s,src)
    choose_all(s)
    roundtrip(s)


def test_spending_source_mana_on_nonpermanent_spell_does_not_trigger(cards):
    s,src=setup(cards)
    b=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=b.id,targets=['p2'],sources=[src.id])
    assert not triggers(s,src)
    choose_all(s)
    assert s.state.players['p2'].life==37
    roundtrip(s)


@pytest.mark.parametrize('change',['blink','gone','front','front_and_back','control'])
def test_source_identity_and_current_ability_after_floating_mana(cards,change):
    s,src=setup(cards)
    act(s,'p1',type='activate_ability',card_id=src.id,ability=0)
    if change in ['blink','gone']:
        act(s,'p1',type='move',card_ids=[src.id],to={'player':'p1','zone':'exile'})
        if change=='blink':
            act(s,'p1',type='move',card_ids=[src.id],to={'player':'p1','zone':'battlefield'})
            act(s,'p1',type='set_face',card_id=src.id,face=1)
    elif change in ['front','front_and_back']:
        act(s,'p1',type='set_face',card_id=src.id,face=0)
        if change=='front_and_back':
            act(s,'p1',type='set_face',card_id=src.id,face=1)
    else:
        act(s,'p1',type='set_controller',card_ids=[src.id],player='p2')
    b=put(s,'Grizzly Bears','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=b.id)
    assert len(triggers(s,src))==(1 if change=='front_and_back' else 0)
    choose_all(s)
    roundtrip(s)


def test_barracks_creates_gnome_from_white_mana_already_floated(cards):
    s,src=setup(cards,BARRACKS)
    act(s,'p1',type='activate_ability',card_id=src.id,ability=0)
    b=put(s,'Sol Ring','hand')
    act(s,'p1',type='cast_spell',card_id=b.id)
    assert len(triggers(s,src))==1
    choose_all(s)
    gnomes=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield' and c.name=='Gnome Soldier']
    assert len(gnomes)==1
    roundtrip(s)


@pytest.mark.parametrize('take',[False,True])
def test_myriad_pools_may_copy_cast_spell_until_end_of_turn(cards,take):
    from tests.test_rules_wave6c_tokens_pumps import chars

    s,src=setup(cards,POOLS)
    ring=put(s,'Sol Ring','battlefield')
    act(s,'p1',type='activate_ability',card_id=src.id,ability=0)
    b=put(s,'Grizzly Bears','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=b.id)
    d=s.state.rules.decision
    assert d is not None and ring.id in {o.id for o in d.options} and d.min_choices==0
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[ring.id] if take else [])
    choose_all(s)
    assert chars(s,ring).name==('Grizzly Bears' if take else 'Sol Ring')
    roundtrip(s)
    to_phase(s,'main1',turn=2)
    assert chars(s,ring).name=='Sol Ring'
    roundtrip(s)


@pytest.mark.parametrize('name',[TECUTLAN,POOLS])
def test_stage_mana_made_before_copying_the_trigger_source_keeps_its_identity(cards,name):
    s,original=setup(cards,name,pid='p2')
    stage=put(s,"Thespian's Stage",'battlefield')
    act(s,'p1',type='activate_ability',card_id=stage.id,ability=0)
    old=s.state.rules.object_id(stage.id)
    # Actual Twiddle untaps Stage, then Stage's printed copy ability keeps its
    # object identity. The {C} it made before gaining the trigger must qualify.
    twiddle=put(s,'Twiddle','hand')
    mana(s,U=1)
    act(s,'p1',type='cast_spell',card_id=twiddle.id,targets=[stage.id])
    for _ in range(30):
        d=s.state.rules.decision
        if d is not None:
            pick=next((o.id for o in d.options if 'untap' in o.label.lower()),d.options[0].id)
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[pick])
        elif s.state.zones.get('stack'):
            act(s,s.state.rules.priority,type='pass_priority')
        else:
            break
    assert not s.state.cards[stage.id].tapped
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=stage.id,ability=1,targets=[original.id])
    choose_all(s)
    assert s.state.rules.object_id(stage.id)==old
    assert any(u.src==old and u.sym=='C' for u in s.state.players['p1'].mana_units)
    b=put(s,'Grizzly Bears','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=b.id)
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    assert len(triggers(s,stage))==1 and not triggers(s,original)
    choose_all(s)
    roundtrip(s)


def test_large_real_mana_producer_retains_and_spends_more_than_one_thousand_units(cards):
    s,_=setup(cards)
    marwyn=put(s,'Marwyn, the Nurturer','battlefield')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='set_counter',card_id=marwyn.id,kind='+1/+1',value=1000)
    act(s,'p1',type='activate_ability',card_id=marwyn.id,ability=1)
    units=s.state.players['p1'].mana_units
    assert len(units)==1001 and all(u.src==s.state.rules.object_id(marwyn.id) for u in units)
    from app.game.views import OMNISCIENT, SPECTATOR, build_view

    for viewer in ('p1','p2',SPECTATOR):
        shown=next(p for p in build_view(s.state,viewer)['players'] if p['id']=='p1')
        assert shown['mana']=={'G':1001} and not shown['mana_units']
    raw=next(p for p in build_view(s.state,OMNISCIENT)['players'] if p['id']=='p1')
    assert len(raw['mana_units'])==1001
    b=put(s,'Walking Ballista','hand')
    act(s,'p1',type='cast_spell',card_id=b.id,x_value=500)
    assert len(s.state.players['p1'].mana_units)==1
    assert len(s.state.rules.payments[s.state.rules.object_id(b.id)].mana_sources)==1000
    choose_all(s)
    assert s.state.cards[b.id].counters['+1/+1']==500
    roundtrip(s)


@pytest.mark.parametrize('countered',[False,True])
def test_discover_reads_stack_x_mana_value_even_after_the_cast_spell_is_countered(cards,countered):
    from tests.test_rules_bandmate_references import wait_priority

    s,src=setup(cards)
    hit=put(s,'Solemn Simulacrum','library')
    act(s,'p1',type='move',card_ids=[hit.id],to={'player':'p1','zone':'library'},position='top')
    b=put(s,'Walking Ballista','hand')
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,C=3)
    act(s,'p1',type='cast_spell',card_id=b.id,x_value=2,sources=[src.id])
    if countered:
        wait_priority(s,'p1')
        counter=put(s,'Counterspell','hand')
        mana(s,U=2)
        act(s,'p1',type='cast_spell',card_id=counter.id,targets=[b.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and 'Discover 4' in d.prompt
    assert s.state.cards[hit.id].zone=='p1:exile'
    assert s.state.cards[b.id].zone==('p1:graveyard' if countered else 'stack')
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['no'])
    choose_all(s)
    assert s.state.cards[hit.id].zone=='p1:hand'
    roundtrip(s)


def test_discover_uses_mana_value_instead_of_reduced_cost_actually_paid(cards):
    s,src=setup(cards)
    put(s,'Ruby Medallion','battlefield')
    hit=put(s,'Grizzly Bears','library')
    act(s,'p1',type='move',card_ids=[hit.id],to={'player':'p1','zone':'library'},position='top')
    b=put(s,'Goblin Piker','hand')
    act(s,'p1',type='cast_spell',card_id=b.id,sources=[src.id])
    paid=s.state.rules.payments[s.state.rules.object_id(b.id)]
    assert paid.mana_spent=={'R':1}
    settle(s)
    d=s.state.rules.decision
    assert d is not None and 'Discover 2' in d.prompt and s.state.cards[hit.id].zone=='p1:exile'
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['no'])
    choose_all(s)
    roundtrip(s)


@pytest.mark.parametrize('name,ward',[('Willbender',False),('Dog Walker',True)])
@pytest.mark.parametrize('countered',[False,True])
def test_pools_copies_only_public_face_down_spell_characteristics(cards,name,ward,countered):
    from app.game.views import build_view
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave6c_tokens_pumps import chars

    s,src=setup(cards,POOLS)
    ring=put(s,'Sol Ring','battlefield')
    b=put(s,name,'hand')
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,C=2)
    act(s,'p1',type='cast_spell',card_id=b.id,face_down=True,sources=[src.id])
    face_down=next(c for c in s.state.cards.values() if c.zone=='stack' and c.face_down)
    d=s.state.rules.decision
    assert d is not None and ring.id in {o.id for o in d.options}
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[ring.id])
    if countered:
        wait_priority(s,'p1')
        counter=put(s,'Counterspell','hand')
        mana(s,U=2)
        act(s,'p1',type='cast_spell',card_id=counter.id,targets=[face_down.id])
    choose_all(s)
    ch=chars(s,ring)
    assert ch.name=='' and ch.pt==(2,2) and ch.colors==frozenset() and ch.mana_value==0
    assert ch.types==frozenset({'Creature'}) and not ch.subtypes
    assert bool(ch.abilities)==ward
    assert not s.state.cards[ring.id].face_down  # copying a face-down spell stays face up
    recipe=next(e.copy_recipe for e in s.state.rules.effects if e.layer=='1' and s.state.rules.object_id(ring.id) in e.affected)
    assert recipe is not None and recipe.printing is None and recipe.token is not None
    assert name not in json.dumps(recipe.model_dump(mode='json'))
    assert name not in json.dumps(build_view(s.state,'p2')['cards'][ring.id])
    roundtrip(s)


@pytest.mark.parametrize('countered',[False,True])
def test_pools_copies_prototype_characteristics_from_live_or_countered_spell(cards,countered):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave6c_tokens_pumps import chars

    s,src=setup(cards,POOLS)
    ring=put(s,'Sol Ring','battlefield')
    b=put(s,'Phyrexian Fleshgorger','hand')
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,B=2)
    act(s,'p1',type='cast_spell',card_id=b.id,prototype=True,sources=[src.id])
    d=s.state.rules.decision
    assert d is not None and ring.id in {o.id for o in d.options}
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[ring.id])
    if countered:
        wait_priority(s,'p1')
        counter=put(s,'Counterspell','hand')
        mana(s,U=2)
        act(s,'p1',type='cast_spell',card_id=counter.id,targets=[b.id])
    choose_all(s)
    ch=chars(s,ring)
    assert ch.name=='Phyrexian Fleshgorger' and ch.pt==(3,3) and ch.mana_value==3 and ch.colors==frozenset({'B'})
    roundtrip(s)


def test_firebending_retains_its_source_through_combat_then_empties(cards):
    from tests.game_helpers import mana_pool
    from tests.test_rules_banding import declare_only

    s,_=setup(cards)
    student=put(s,'Firebending Student','battlefield')
    oid=s.state.rules.object_id(student.id)
    declare_only(s,[student],[])
    settle(s)
    assert mana_pool(s)=={'R':1}
    assert [u.src for u in s.state.players['p1'].mana_units]==[oid]
    roundtrip(s)
    to_phase(s,'end_combat',turn=4)
    assert mana_pool(s)=={'R':1}
    to_phase(s,'main2',turn=4)
    assert mana_pool(s)=={} and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_horizon_stone_converts_color_but_keeps_the_original_mana_source(cards):
    s,src=setup(cards)
    put(s,'Horizon Stone','battlefield')
    oid=s.state.rules.object_id(src.id)
    act(s,'p1',type='activate_ability',card_id=src.id,ability=0)
    to_phase(s,'main2',turn=1)
    assert [(u.sym,u.src) for u in s.state.players['p1'].mana_units]==[('C',oid)]
    b=put(s,'Grizzly Bears','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=b.id)
    assert len(triggers(s,src))==1
    choose_all(s)
    roundtrip(s)


def test_spirit_guide_mana_remembers_the_source_object_before_exiling_it(cards):
    from tests.game_helpers import mana_pool

    s,_=setup(cards)
    guide=put(s,'Elvish Spirit Guide','hand')
    oid=s.state.rules.object_id(guide.id)
    act(s,'p1',type='activate_ability',card_id=guide.id,ability=0)
    assert s.state.cards[guide.id].zone=='p1:exile' and s.state.rules.object_id(guide.id)!=oid
    assert mana_pool(s)=={'G':1}
    assert [(u.sym,u.src) for u in s.state.players['p1'].mana_units]==[('G',oid)]
    roundtrip(s)


@pytest.mark.parametrize('manual',[False,True])
def test_mana_used_for_filter_activation_is_not_mana_spent_on_the_spell(cards,manual):
    s,src=setup(cards)
    prairie=put(s,'Sungrass Prairie','battlefield')
    if manual:
        act(s,'p1',type='activate_ability',card_id=prairie.id,ability=0)
    b=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='cast_spell',card_id=b.id,**({} if manual else {'sources':[src.id,prairie.id]}))
    assert not triggers(s,src)
    paid=s.state.rules.payments[s.state.rules.object_id(b.id)]
    assert paid.mana_spent=={'G':1,'W':1}
    assert paid.mana_sources==[s.state.rules.object_id(prairie.id)]*2
    roundtrip(s)
    choose_all(s)
    roundtrip(s)


def test_filter_payment_separates_activation_input_and_preserves_unspent_output(cards):
    from tests.game_helpers import mana_pool

    s,_=setup(cards)
    ring=put(s,'Sol Ring','battlefield')
    prairie=put(s,'Sungrass Prairie','battlefield')
    b=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='cast_spell',card_id=b.id,sources=[ring.id,prairie.id])
    paid=s.state.rules.payments[s.state.rules.object_id(b.id)]
    assert paid.mana_spent=={'C':1,'G':1}
    assert sorted(paid.mana_sources)==sorted([s.state.rules.object_id(ring.id),s.state.rules.object_id(prairie.id)])
    assert mana_pool(s)=={'W':1}
    assert s.state.cards[ring.id].tapped and s.state.cards[prairie.id].tapped
    roundtrip(s)
    choose_all(s)
    roundtrip(s)


def test_two_filters_have_separate_activation_payments_and_real_output_accounting(cards):
    from tests.game_helpers import mana_pool

    s,_=setup(cards)
    ring=put(s,'Sol Ring','battlefield')
    first=put(s,'Sungrass Prairie','battlefield')
    second=put(s,'Sungrass Prairie','battlefield',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[second.id],player='p1')
    b=put(s,'Solemn Simulacrum','hand')
    act(s,'p1',type='cast_spell',card_id=b.id,sources=[ring.id,first.id,second.id])
    paid=s.state.rules.payments[s.state.rules.object_id(b.id)]
    assert sum(paid.mana_spent.values())==4
    assert sorted(paid.mana_sources)==sorted([s.state.rules.object_id(first.id)]*2+[s.state.rules.object_id(second.id)]*2)
    assert not mana_pool(s)
    assert all(s.state.cards[c.id].tapped for c in (ring,first,second))
    roundtrip(s)
    choose_all(s)
    roundtrip(s)


@pytest.mark.parametrize('manual',[False,True])
def test_filter_activation_reserves_forest_for_double_green_spell(cards,manual):
    s,_=setup(cards)
    prairie=put(s,'Sungrass Prairie','battlefield')
    forest=put(s,'Forest','battlefield')
    island=put(s,'Island','battlefield')
    b=put(s,'Kalonian Tusker','hand')
    options={'sources':[prairie.id,forest.id,island.id]} if manual else {}
    act(s,'p1',type='cast_spell',card_id=b.id,**options)
    paid=s.state.rules.payments[s.state.rules.object_id(b.id)]
    assert paid.mana_spent=={'G':2}
    assert sorted(paid.mana_sources)==sorted([s.state.rules.object_id(prairie.id),s.state.rules.object_id(forest.id)])
    assert all(s.state.cards[c.id].tapped for c in (prairie,forest,island))
    roundtrip(s)
    choose_all(s)
    roundtrip(s)


@pytest.mark.parametrize('floating',[False,True])
def test_treasure_spent_activating_filter_does_not_grant_rain_cascade(cards,floating):
    from tests.test_rules_first_mana_source_spell import treasure
    from tests.test_rules_wave10b_spell_cascade import cascades

    s,_=setup(cards)
    put(s,'Rain of Riches','battlefield')
    prairie=put(s,'Sungrass Prairie','battlefield')
    t=treasure(s,floating=floating)
    b=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='cast_spell',card_id=b.id,sources=[prairie.id]+([] if floating else [t.id]))
    assert cascades(s)==0
    paid=s.state.rules.payments[s.state.rules.object_id(b.id)]
    assert not any('Treasure' in tags for tags in paid.mana_tags)
    assert paid.mana_spent=={'G':1,'W':1}
    assert t.id not in s.state.cards  # sacrificed token ceases to exist
    roundtrip(s)
    choose_all(s)
    roundtrip(s)
    # The activation input must not consume Rain's first qualifying cast for
    # the turn, including its historical CastNote after the Bear resolved.
    later=treasure(s)
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=['p2'],sources=[later.id])
    assert cascades(s)==1
    roundtrip(s)
    choose_all(s)
    roundtrip(s)


def test_filter_activation_pays_life_without_transferring_input_haste_rider(cards):
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    s,_=setup(cards)
    hall=put(s,'Hall of the Bandit Lord','battlefield')
    prairie=put(s,'Sungrass Prairie','battlefield')
    b=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='cast_spell',card_id=b.id,sources=[hall.id,prairie.id])
    paid=s.state.rules.payments[s.state.rules.object_id(b.id)]
    assert s.state.players['p1'].life==37
    assert not paid.mana_riders
    assert paid.mana_sources==[s.state.rules.object_id(prairie.id)]*2
    assert s.state.cards[hall.id].tapped
    roundtrip(s)
    choose_all(s)
    current=s.state.cards[b.id]
    ch=derive(s.state,current,chars.of(current,cards),cards)
    assert 'haste' not in ch.keywords
    assert s.state.players['p1'].life==37
    roundtrip(s)
