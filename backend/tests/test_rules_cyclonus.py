"""Cyclonus: actual combat conversion and the additional beginning phase."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import alt_costs, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_banding import declare_only
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    raw=json.loads((Path(__file__).parent/'fixtures/cyclonus_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='cyc',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAME='Cyclonus, the Saboteur // Cyclonus, Cybertronian Fighter'


def setup(cards,converted=False):
    s=table(cards,[NAME,'Sol Ring','Phyrexian Arena','Island'],[],[])
    source=put(s,NAME,'hand' if converted else 'battlefield')
    rock=put(s,'Sol Ring','battlefield')
    if converted:
        act(s,'p1',type='add_mana',player='p1',mana={'C':5,'U':1,'B':1})
        offer=alt_costs.converted_offers(s.state,'p1',source,s.cards)[0]
        act(s,'p1',type='cast_spell',card_id=source.id,alt_cost=offer.key)
        settle(s)
        assert s.state.cards[source.id].face==1
    to_phase(s,'main1',turn=4)
    return s,source,rock


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


def test_back_face_combat_conversion_adds_beginning_after_whole_combat(cards):
    s,source,rock=setup(cards,converted=True)
    put(s,'Phyrexian Arena','battlefield')
    declare_only(s,[source],[])
    to_phase(s,'end_combat',turn=4)
    settle(s)
    assert s.state.players['p2'].life==35
    assert s.state.cards[source.id].face==0
    assert s.state.cards[source.id].tapped
    assert s.state.rules.extra_phases==['untap','main2']
    before=len(s.state.zones['p1:hand'])
    life=s.state.players['p1'].life
    roundtrip(s)
    to_phase(s,'main2',turn=4)
    settle(s)
    assert not s.state.cards[source.id].tapped
    assert len(s.state.zones['p1:hand'])==before+2
    assert s.state.players['p1'].life==life-1
    assert s.state.turn.number==4
    roundtrip(s)


def test_living_metal_only_on_controllers_turn(cards):
    s,source,_=setup(cards,converted=True)
    assert 'Creature' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).types
    to_phase(s,'main1',turn=5)
    assert 'Creature' not in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).types
    roundtrip(s)


@pytest.mark.parametrize(('counters','discard_name','face'),[(0,'Sol Ring',0),(2,'Sol Ring',1),(2,'Island',0),(3,'Island',1)])
def test_front_connive_finishes_before_power_threshold_conversion(cards,counters,discard_name,face):
    s,source,_=setup(cards)
    discard=put(s,discard_name,'hand')
    act(s,'p1',type='set_counter',card_id=source.id,kind='+1/+1',value=counters)
    declare_only(s,[source],[])
    for _ in range(100):
        d=s.state.rules.decision
        if d is not None and d.prompt.startswith('Connive: discard'):
            break
        if d is not None and d.kind=='declare_blockers':
            act(s,d.player,type='declare_blockers',blocks=[])
        elif d is not None and d.kind=='order':
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
        else:
            assert d is None
            act(s,s.state.rules.priority,type='pass_priority')
    else:
        raise AssertionError('No connive discard decision')
    assert s.state.cards[source.id].face==0
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[discard.id])
    settle(s)
    assert s.state.cards[source.id].face==face
    assert s.state.cards[source.id].counters.get('+1/+1',0)==counters+(discard_name!='Island')
    assert not s.state.rules.extra_phases  # converting to Vehicle never creates its damage trigger retroactively
    roundtrip(s)


def test_back_trigger_requires_successful_conversion_of_original_object(cards):
    s,source,_=setup(cards,converted=True)
    declare_only(s,[source],[])
    to_phase(s,'combat_damage',turn=4)
    assert s.state.players['p2'].life==35
    assert s.state.cards[source.id].face==1
    assert s.state.zones.get('stack')
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'battlefield'})
    roundtrip(s)
    settle(s)
    assert s.state.cards[source.id].face==0
    assert not s.state.rules.extra_phases
    roundtrip(s)
