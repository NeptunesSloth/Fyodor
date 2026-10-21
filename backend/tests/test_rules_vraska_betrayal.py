"""Actual Oracle replays: Vraska's permanent Treasure and live poison difference."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME="Vraska, Betrayal's Sting"


@pytest.fixture()
def cards(settings):
    raw=json.loads((Path(__file__).parent/'fixtures/vraska_betrayal_cards.json').read_text())
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='vbs',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,loyalty=6):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/vraska_betrayal_cards.json').read_text())]
    s=table(cards,names,names,[])
    source=put(s,NAME,'battlefield')
    act(s,'p1',type='set_counter',card_id=source.id,kind='loyalty',value=loyalty)
    return s,source


def ch(s,c):
    c=s.state.cards[c.id]
    return derive(s.state,c,chars.of(c,s.cards),s.cards)


def activate(s,source,target,index=2):
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=[target])
    roundtrip(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


@pytest.mark.parametrize('name',['Grizzly Bears','Lion Sash','Ragavan, Nimble Pilferer'])
def test_creature_becomes_exact_treasure_retaining_other_characteristics(cards,name):
    s,source=setup(cards)
    c=put(s,name,'battlefield',pid='p2')
    before=ch(s,c)
    act(s,'p2',type='set_counter',card_id=c.id,kind='+1/+1',value=2)
    activate(s,source,c.id)
    assert s.state.cards[source.id].counters['loyalty']==4
    choose_all(s)
    after=ch(s,c)
    assert after.types==frozenset({'Artifact'})
    assert after.subtypes==frozenset({'Treasure'})
    assert after.colors==before.colors and after.supertypes==before.supertypes
    assert after.name==before.name and after.mana_value==before.mana_value
    assert s.state.cards[c.id].counters['+1/+1']==2
    assert len(after.abilities)==1 and 'Sacrifice this permanent' in after.abilities[0].text
    assert s.state.cards[c.id].controller=='p2'
    roundtrip(s)
    to_phase(s,'main1',turn=4)
    assert ch(s,c).types==frozenset({'Artifact'})
    # Its new noncreature mana ability works without the old creature's abilities.
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=c.id,ability=after.abilities[0].index,mana_choice='U')
    assert s.state.cards[c.id].zone=='p2:graveyard'
    assert mana_pool(s,'p2')=={'U':1}
    roundtrip(s)


def test_equipment_unattaches_and_creature_aura_goes_to_graveyard(cards):
    s,source=setup(cards)
    c=put(s,'Grizzly Bears','battlefield',pid='p2')
    sword=put(s,'Sword of the Animist','battlefield',pid='p2')
    aura=put(s,'Rancor','battlefield',pid='p2')
    act(s,'p2',type='attach',card_ids=[sword.id,aura.id],to=c.id)
    activate(s,source,c.id)
    choose_all(s)
    assert s.state.cards[sword.id].attached_to is None
    assert s.state.cards[aura.id].zone=='p2:hand'  # Rancor's normal dies trigger
    assert ch(s,c).types==frozenset({'Artifact'})
    roundtrip(s)


def test_effect_survives_source_departure_but_not_target_blink(cards):
    s,source=setup(cards)
    c=put(s,'Grizzly Bears','battlefield')
    activate(s,source,c.id)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    choose_all(s)
    assert ch(s,c).subtypes==frozenset({'Treasure'})
    act(s,'p1',type='move',card_ids=[c.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[c.id],to={'player':'p1','zone':'battlefield'})
    assert ch(s,c).is_creature and 'Bear' in ch(s,c).subtypes
    roundtrip(s)


@pytest.mark.parametrize('pid',['p1','p2','p3'])
@pytest.mark.parametrize('start',[0,3,8,9])
def test_poison_tops_up_any_target_player_to_nine(cards,pid,start):
    s,source=setup(cards,loyalty=9)
    act(s,pid,type='set_resource',player=pid,key='poison',value=start)
    activate(s,source,pid,index=3)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    choose_all(s)
    assert s.state.players[pid].resources['poison']==9
    roundtrip(s)


def test_poison_uses_resolution_count_instead_of_announced_count(cards):
    s,source=setup(cards,loyalty=10)
    activate(s,source,'p2',index=3)
    act(s,'p2',type='set_resource',player='p2',key='poison',value=7)
    choose_all(s)
    assert s.state.players['p2'].resources['poison']==9
    roundtrip(s)


@pytest.mark.parametrize('prevention',['Melira, Sylvok Outcast','Solemnity'])
def test_poison_top_up_uses_normal_counter_prevention(cards,prevention):
    s,source=setup(cards,loyalty=10)
    put(s,prevention,'battlefield',pid='p2')
    activate(s,source,'p2',index=3)
    choose_all(s)
    assert s.state.players['p2'].resources.get('poison',0)==0
    roundtrip(s)


@pytest.mark.parametrize('first',['Vorinclex','Winding Constrictor'])
def test_poison_replacement_order_is_chosen_by_affected_player_and_survives_save(cards,first):
    s,source=setup(cards,loyalty=10)
    put(s,'Vorinclex, Monstrous Raider','battlefield',pid='p2')
    put(s,'Winding Constrictor','battlefield',pid='p2')
    act(s,'p2',type='set_resource',player='p2',key='poison',value=1)
    activate(s,source,'p2',index=3)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player=='p2'
    roundtrip(s)
    pick=next(o.id for o in d.options if first in o.label)
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[pick])
    choose_all(s)
    assert s.state.players['p2'].resources['poison']==(6 if first=='Vorinclex' else 5)
    roundtrip(s)


def test_loyalty_cost_is_required_and_cannot_activate_again_this_turn(cards):
    s,source=setup(cards,loyalty=8)
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        activate(s,source,'p2',index=3)
    assert s.state.model_dump(mode='json')==before
    act(s,'p1',type='set_counter',card_id=source.id,kind='loyalty',value=20)
    c=put(s,'Grizzly Bears','battlefield')
    activate(s,source,c.id)
    choose_all(s)
    with pytest.raises(ActionError):
        activate(s,source,'p2',index=3)
    roundtrip(s)


def test_poison_above_nine_is_unchanged_when_player_cannot_lose(cards):
    s,source=setup(cards,loyalty=10)
    put(s,'Platinum Angel','battlefield',pid='p2')
    act(s,'p2',type='set_resource',player='p2',key='poison',value=12)
    activate(s,source,'p2',index=3)
    choose_all(s)
    assert s.state.players['p2'].resources['poison']==12
    roundtrip(s)


def test_treasure_ability_survives_its_own_wipe_and_later_grants_apply(cards):
    s,source=setup(cards)
    c=put(s,'Grizzly Bears','battlefield')
    leap=put(s,'Leap','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'U':1})
    act(s,'p1',type='cast_spell',card_id=leap.id,targets=[c.id])
    choose_all(s)
    assert 'flying' in ch(s,c).keywords
    activate(s,source,c.id)
    choose_all(s)
    assert 'flying' not in ch(s,c).keywords and len(ch(s,c).abilities)==1
    skill=put(s,"Blacksmith's Skill",'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'W':1})
    act(s,'p1',type='cast_spell',card_id=skill.id,targets=[c.id])
    choose_all(s)
    assert {'hexproof','indestructible'}<=ch(s,c).keywords
    assert len(ch(s,c).abilities)==1
    roundtrip(s)
    to_phase(s,'main1',turn=4)
    assert 'hexproof' not in ch(s,c).keywords and len(ch(s,c).abilities)==1
    roundtrip(s)


def test_later_ability_wipe_removes_treasure_grant_then_expiry_restores_it(cards):
    s,source=setup(cards)
    c=put(s,'Grizzly Bears','battlefield')
    activate(s,source,c.id)
    choose_all(s)
    put(s,'March of the Machines','battlefield')
    assert ch(s,c).is_creature and 'Artifact' in ch(s,c).types and len(ch(s,c).abilities)==1
    frog=put(s,'Turn to Frog','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'U':1,'C':1})
    act(s,'p1',type='cast_spell',card_id=frog.id,targets=[c.id])
    choose_all(s)
    assert not ch(s,c).abilities
    roundtrip(s)
    to_phase(s,'main1',turn=4)
    assert len(ch(s,c).abilities)==1 and ch(s,c).subtypes==frozenset({'Treasure'})
    roundtrip(s)


def test_creature_target_blinked_before_resolution_is_not_transformed(cards):
    s,source=setup(cards)
    c=put(s,'Grizzly Bears','battlefield',pid='p2')
    activate(s,source,c.id)
    act(s,'p2',type='move',card_ids=[c.id],to={'player':'p2','zone':'exile'})
    act(s,'p2',type='move',card_ids=[c.id],to={'player':'p2','zone':'battlefield'})
    choose_all(s)
    assert ch(s,c).is_creature and 'Artifact' not in ch(s,c).types
    assert s.state.cards[source.id].counters['loyalty']==4
    roundtrip(s)


def test_poison_difference_is_added_and_doubled_instead_of_setting_counter_total(cards):
    s,source=setup(cards,loyalty=10)
    put(s,'Vorinclex, Monstrous Raider','battlefield')
    put(s,'Platinum Angel','battlefield',pid='p2')
    act(s,'p2',type='set_resource',player='p2',key='poison',value=2)
    activate(s,source,'p2',index=3)
    choose_all(s)
    assert s.state.players['p2'].resources['poison']==16  # 2 + 2*(9-2)
    roundtrip(s)


@pytest.mark.parametrize('pay_life',[False,True])
def test_actual_compleated_cast_uses_mana_or_life_and_correct_initial_loyalty(cards,pay_life):
    s,source=setup(cards)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'hand'})
    act(s,'p1',type='add_mana',player='p1',mana={'C':4,'B':1 if pay_life else 2})
    act(s,'p1',type='cast_spell',card_id=source.id)
    roundtrip(s)
    choose_all(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.cards[source.id].counters['loyalty']==(4 if pay_life else 6)
    assert s.state.players['p1'].life==(38 if pay_life else 40)
    roundtrip(s)


def test_zero_ability_draws_loses_life_and_proliferates_actual_selected_counters(cards):
    s,source=setup(cards)
    act(s,'p2',type='set_resource',player='p2',key='poison',value=2)
    before=len(s.state.zones['p1:hand'])
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.kind=='choose_cards'
    assert s.state.players['p1'].life==39
    assert len(s.state.zones['p1:hand'])==before+1
    roundtrip(s)
    ids=[o.id for o in d.options if o.id==source.id or 'Bob' in o.label]
    assert len(ids)==2
    act(s,'p1',type='choose',decision_id=d.id,option_ids=ids)
    choose_all(s)
    assert s.state.cards[source.id].counters['loyalty']==7
    assert s.state.players['p2'].resources['poison']==3
    roundtrip(s)
