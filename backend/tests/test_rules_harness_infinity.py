"""CR 701.64/702.186: actual Harness costs and conditional Infinity grants."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import characteristics as chars
from app.rules import coverage
from app.rules.layers import derive
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_conditionals import settle as choose_all
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import stops, to_phase

SOUL='The Soul Stone'
MIND='The Mind Stone'


@pytest.fixture()
def cards(settings):
    raw=json.loads((Path(__file__).parent/'fixtures/harness_infinity_cards.json').read_text())
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='hin',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,name=MIND,pid='p1'):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/harness_infinity_cards.json').read_text())]
    s=table(cards,names,names,[])
    source=put(s,name,'battlefield',pid=pid)
    stops(s,'upkeep','end')
    return s,source


def ch(s,c):
    c=s.state.cards[c.id]
    return derive(s.state,c,chars.of(c,s.cards),s.cards)


def infinity(s,c):
    return [a for a in ch(s,c).abilities if a.kind=='triggered' and 'beginning of your' in a.text]


def harness(s,source,creature=None):
    name=ch(s,source).name
    act(s,source.controller,type='add_mana',player=source.controller,mana={'C':6 if name==SOUL else 5,'B' if name==SOUL else 'W':1})
    act(s,source.controller,type='activate_ability',card_id=source.id,ability=2)
    d=s.state.rules.decision
    if d is not None:
        assert creature is not None and creature.id in {o.id for o in d.options}
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[creature.id])
    roundtrip(s)


@pytest.mark.parametrize('name',[SOUL,MIND])
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('name',[SOUL,MIND])
def test_harness_activates_static_grant_after_native_costs_and_resolution(cards,name):
    s,source=setup(cards,name)
    creature=put(s,'Grizzly Bears','battlefield') if name==SOUL else None
    assert not infinity(s,source) and source.choices.get('Harnessed') is None
    harness(s,source,creature)
    assert not infinity(s,source) and source.choices.get('Harnessed') is None
    assert s.state.cards[source.id].tapped
    if creature:
        assert s.state.cards[creature.id].zone=='p1:exile'
    choose_all(s)
    assert s.state.cards[source.id].choices['Harnessed']=='Yes'
    assert len(infinity(s,source))==1 and not mana_pool(s)
    roundtrip(s)


def test_mind_stone_blinks_other_nonland_under_its_owners_control(cards):
    s,source=setup(cards)
    other=put(s,'Solemn Simulacrum','battlefield',pid='p2')
    land=put(s,'Forest','battlefield')
    act(s,'p1',type='set_controller',card_ids=[other.id],player='p1')
    old=s.state.rules.object_id(other.id)
    harness(s,source)
    choose_all(s)
    to_phase(s,'end',turn=1)
    d=s.state.rules.decision
    assert d is not None
    assert source.id not in {o.id for o in d.options}
    assert land.id not in {o.id for o in d.options}
    assert other.id in {o.id for o in d.options}
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[other.id])
    choose_all(s)
    assert s.state.cards[other.id].controller=='p2' and s.state.rules.object_id(other.id)!=old
    roundtrip(s)


def test_mind_stone_can_choose_no_target(cards):
    s,source=setup(cards)
    other=put(s,'Sol Ring','battlefield')
    old=s.state.rules.object_id(other.id)
    harness(s,source)
    choose_all(s)
    to_phase(s,'end',turn=1)
    d=s.state.rules.decision
    assert d is not None and d.min_choices==0
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    choose_all(s)
    assert s.state.rules.object_id(other.id)==old
    roundtrip(s)


def test_soul_stone_reanimates_on_its_controllers_upkeep(cards):
    s,source=setup(cards,SOUL)
    payment=put(s,'Grizzly Bears','battlefield')
    target=put(s,'Solemn Simulacrum','graveyard')
    harness(s,source,payment)
    choose_all(s)
    to_phase(s,'upkeep',turn=4)
    d=s.state.rules.decision
    assert d is not None and target.id in {o.id for o in d.options}
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    choose_all(s)
    assert s.state.cards[target.id].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('departure',['graveyard','blink'])
def test_original_object_must_still_exist_when_harness_resolves(cards,departure):
    s,source=setup(cards)
    harness(s,source)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    if departure=='blink':
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'battlefield'})
    choose_all(s)
    assert s.state.cards[source.id].choices.get('Harnessed') is None
    assert not infinity(s,source)
    roundtrip(s)


def test_harness_designation_survives_control_change_and_resets_on_blink(cards):
    s,source=setup(cards)
    harness(s,source)
    choose_all(s)
    old=s.state.rules.object_id(source.id)
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    assert s.state.rules.object_id(source.id)==old and infinity(s,source)
    act(s,'p2',type='move',card_ids=[source.id],to={'player':'p2','zone':'exile'})
    act(s,'p2',type='move',card_ids=[source.id],to={'player':'p2','zone':'battlefield'})
    assert not infinity(s,source) and source.choices.get('Harnessed') is None
    roundtrip(s)


def test_null_rod_stops_harness_activation_but_not_existing_infinity_grant(cards):
    s,source=setup(cards)
    harness(s,source)
    choose_all(s)
    put(s,'Null Rod','battlefield')
    assert infinity(s,source)
    act(s,'p1',type='tap',card_ids=[source.id],tapped=False)
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    assert s.state.model_dump(mode='json')==before
    roundtrip(s)


def test_repeated_harness_activation_pays_costs_without_resetting_designation(cards):
    s,source=setup(cards)
    harness(s,source)
    choose_all(s)
    act(s,'p1',type='tap',card_ids=[source.id],tapped=False)
    harness(s,source)
    choose_all(s)
    assert s.state.cards[source.id].tapped and len(infinity(s,source))==1 and not mana_pool(s)
    roundtrip(s)


@pytest.mark.parametrize('name',[SOUL,MIND])
def test_native_harness_costs_must_be_payable(cards,name):
    s,source=setup(cards,name)
    if name==SOUL:
        put(s,'Grizzly Bears','battlefield')
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    assert s.state.model_dump(mode='json')==before


def test_soul_harness_requires_exile_creature_cost(cards):
    s,source=setup(cards,SOUL)
    act(s,'p1',type='add_mana',player='p1',mana={'C':6,'B':1})
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    assert s.state.model_dump(mode='json')==before


def test_countered_harness_keeps_paid_costs_without_harnessing(cards):
    s,source=setup(cards,SOUL)
    creature=put(s,'Grizzly Bears','battlefield')
    harness(s,source,creature)
    ability=s.state.zones['stack'][-1]
    wait_priority(s,'p2')
    counter=put(s,'Stifle','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    act(s,'p2',type='cast_spell',card_id=counter.id,targets=[ability])
    choose_all(s)
    assert not infinity(s,source) and s.state.cards[source.id].choices.get('Harnessed') is None
    assert s.state.cards[source.id].tapped and s.state.cards[creature.id].zone=='p1:exile'
    roundtrip(s)


def test_harnessed_designation_survives_phasing_but_infinity_is_inactive_while_phased(cards):
    s,source=setup(cards)
    harness(s,source)
    choose_all(s)
    old=s.state.rules.object_id(source.id)
    act(s,'p1',type='phase_shift',card_ids=[source.id],out=True)
    assert s.state.cards[source.id].choices['Harnessed']=='Yes'
    assert not infinity(s,source)
    roundtrip(s)
    act(s,'p1',type='phase_shift',card_ids=[source.id],out=False)
    assert s.state.rules.object_id(source.id)==old and infinity(s,source)
    roundtrip(s)


def test_phased_source_cannot_become_harnessed_until_new_activation(cards):
    s,source=setup(cards)
    harness(s,source)
    act(s,'p1',type='phase_shift',card_ids=[source.id],out=True)
    choose_all(s)
    act(s,'p1',type='phase_shift',card_ids=[source.id],out=False)
    assert s.state.cards[source.id].choices.get('Harnessed') is None
    assert not infinity(s,source)
    roundtrip(s)


def test_harnessed_designation_survives_ability_removal_and_restoration(cards):
    s,source=setup(cards)
    harness(s,source)
    choose_all(s)
    aura=put(s,'Song of the Dryads','battlefield',pid='p2')
    act(s,'p2',type='attach',card_ids=[aura.id],to=source.id)
    assert not infinity(s,source) and ch(s,source).types==frozenset({'Land'})
    assert s.state.cards[source.id].choices['Harnessed']=='Yes'
    roundtrip(s)
    act(s,'p2',type='move',card_ids=[aura.id],to={'player':'p2','zone':'graveyard'})
    assert infinity(s,source)
    roundtrip(s)


def test_unharnessed_copy_does_not_copy_designation_and_harnessed_object_keeps_it_across_copies(cards):
    s,source=setup(cards)
    harness(s,source)
    choose_all(s)
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    mirror=put(s,'Mirage Mirror','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='activate_ability',card_id=mirror.id,ability=0,targets=[source.id])
    choose_all(s)
    assert ch(s,mirror).name==MIND and not infinity(s,mirror)
    assert s.state.cards[mirror.id].choices.get('Harnessed') is None
    harness(s,s.state.cards[mirror.id])
    choose_all(s)
    assert infinity(s,mirror)
    act(s,'p2',type='move',card_ids=[source.id],to={'player':'p2','zone':'graveyard'})
    to_phase(s,'main1',turn=4)
    assert ch(s,mirror).name=='Mirage Mirror' and s.state.cards[mirror.id].choices['Harnessed']=='Yes'
    other=put(s,SOUL,'battlefield',pid='p2')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='activate_ability',card_id=mirror.id,ability=0,targets=[other.id])
    choose_all(s)
    assert ch(s,mirror).name==SOUL and infinity(s,mirror)
    assert s.state.cards[other.id].choices.get('Harnessed') is None
    roundtrip(s)


def test_soul_stone_reanimation_obeys_entry_restrictions(cards):
    s,source=setup(cards,SOUL)
    payment=put(s,'Grizzly Bears','battlefield')
    target=put(s,'Solemn Simulacrum','graveyard')
    put(s,"Grafdigger's Cage",'battlefield',pid='p2')
    harness(s,source,payment)
    choose_all(s)
    to_phase(s,'upkeep',turn=4)
    d=s.state.rules.decision
    assert d is not None
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    choose_all(s)
    assert s.state.cards[target.id].zone=='p1:graveyard'
    roundtrip(s)


def test_infinity_trigger_already_on_stack_survives_source_ability_loss(cards):
    s,source=setup(cards)
    target=put(s,'Sol Ring','battlefield')
    old=s.state.rules.object_id(target.id)
    harness(s,source)
    choose_all(s)
    to_phase(s,'end',turn=1)
    d=s.state.rules.decision
    assert d is not None
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    aura=put(s,'Song of the Dryads','battlefield',pid='p2')
    act(s,'p2',type='attach',card_ids=[aura.id],to=source.id)
    assert not infinity(s,source)
    roundtrip(s)
    choose_all(s)
    assert s.state.rules.object_id(target.id)!=old
    roundtrip(s)


def test_harnessing_after_beginning_of_end_step_does_not_create_missed_trigger(cards):
    s,source=setup(cards)
    target=put(s,'Sol Ring','battlefield')
    old=s.state.rules.object_id(target.id)
    to_phase(s,'end',turn=1)
    assert s.state.rules.decision is None
    harness(s,source)
    choose_all(s)
    assert s.state.rules.object_id(target.id)==old and infinity(s,source)
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_infinity_trigger_uses_new_controllers_turn_and_targets(cards):
    s,source=setup(cards)
    target=put(s,'Sol Ring','battlefield',pid='p2')
    old=s.state.rules.object_id(target.id)
    harness(s,source)
    choose_all(s)
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    to_phase(s,'end',turn=2)
    d=s.state.rules.decision
    assert d is not None and d.player=='p2' and target.id in {o.id for o in d.options}
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    choose_all(s)
    assert s.state.rules.object_id(target.id)!=old and s.state.cards[target.id].controller=='p2'
    roundtrip(s)


def test_animated_soul_stone_can_exile_itself_as_cost_but_cannot_harness_departed_object(cards):
    s,source=setup(cards,SOUL)
    put(s,'March of the Machines','battlefield')
    to_phase(s,'main1',turn=4)
    assert ch(s,source).is_creature
    harness(s,source,source)
    assert s.state.cards[source.id].zone=='p1:exile'
    choose_all(s)
    assert s.state.cards[source.id].choices.get('Harnessed') is None
    assert not infinity(s,source)
    roundtrip(s)
