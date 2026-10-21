"""Unimported45 leaf staging through actual native casts and trigger decisions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import effects, engine, scripts
from app.rules import exile_cast_outcomes45 as leaf
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for filename in ('exile_outcomes42_cards.json','exile_cast_outcomes45_cards.json'):
        for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures'/filename).read_text())):
            base[c['name']]=card(c['name'],set_code='ec45',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.fixture(autouse=True)
def staged(monkeypatch):
    native=scripts.define
    native_parse=scripts.parse_effects
    monkeypatch.setattr(scripts,'parse_effects',lambda body,*args,**kw:leaf.parse(body) or native_parse(body,*args,**kw))
    monkeypatch.setattr(scripts,'define',lambda ability,ch:leaf.definition(ability,ch) or native(ability,ch))
    scripts._cached.cache_clear()
    for name,callback in leaf.PRIMITIVES.items():
        monkeypatch.setitem(effects.PRIMITIVES,name,callback)
    for name,callback in leaf.RESUME.items():
        monkeypatch.setitem(engine.RESUME,name,callback)
    yield
    scripts._cached.cache_clear()


def setup(cards,*extra):
    names=['Grizzly Bears','Divination','Giant Growth',"Ashnod's Altar",'Rivaz of the Claw',*extra]
    s=table(cards,names,names,names)
    to_phase(s,'main1',turn=1)
    act(s,'p1',type='set_prefs',hold_priority=True)
    return s


def test_mindclaw_actual_target_hand_cast_is_not_exile_and_spell_returns_to_owner_graveyard(cards):
    s=setup(cards,'Mindclaw Shaman')
    foreign=put(s,'Divination','hand',pid='p2')
    bear=put(s,'Grizzly Bears','hand',pid='p2')
    cast(s,'Mindclaw Shaman')
    assert s.state.rules.decision.resume['step']=='trigger_target'
    answer(s,['p2'])
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    assert foreign.id in [o.id for o in d.options]
    assert bear.id not in [o.id for o in d.options]
    answer(s,[foreign.id])
    assert s.state.cards[foreign.id].zone=='p2:graveyard'
    assert s.state.cards[bear.id].zone=='p2:hand'
    roundtrip(s)


@pytest.mark.parametrize('zone',['hand','graveyard'])
def test_anrakyr_actual_attack_cast_artifact_pays_life_not_mana(cards,zone):
    s=setup(cards,'Anrakyr the Traveller')
    source=put(s,'Anrakyr the Traveller','battlefield')
    altar=put(s,"Ashnod's Altar",zone)
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    life=s.state.players['p1'].life
    answer(s,[altar.id])
    assert s.state.players['p1'].life==life-3
    assert s.state.cards[altar.id].zone=='p1:battlefield'
    roundtrip(s)


def test_reinterpret_actual_counter_then_free_cast_target_mana_value(cards):
    s=setup(cards,'Reinterpret')
    target=put(s,'Divination','hand')
    mana(s,U=1,C=2)
    act(s,'p1',type='cast_spell',card_id=target.id)
    bear=put(s,'Grizzly Bears','hand')
    cast(s,'Reinterpret',targets=[target.id])
    assert s.state.cards[target.id].zone=='p1:graveyard'
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[bear.id])
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('choice',['discard','cast'])
def test_great_intelligence_actual_draw_first_then_opponent_makes_villainous_choice(cards,choice):
    s=setup(cards,"Great Intelligence's Plan")
    foreign=[put(s,name,'hand',pid='p2') for name in ('Grizzly Bears','Divination','Giant Growth')]
    bear=put(s,'Grizzly Bears','hand')
    before=len(s.state.zones['p1:hand'])
    cast(s,"Great Intelligence's Plan",targets=['p2'])
    d=s.state.rules.decision
    assert d.player=='p2' and d.resume['step']=='exile_cast_outcome45'
    assert len(s.state.zones['p1:hand'])==before+3
    answer(s,[choice])
    if choice=='discard':
        d=s.state.rules.decision
        if d is not None:
            answer(s,[c.id for c in foreign])
        assert all(s.state.cards[c.id].zone=='p2:graveyard' for c in foreign)
        assert s.state.cards[bear.id].zone=='p1:hand'
    else:
        assert s.state.rules.decision.resume['step']=='free_cast_pick'
        answer(s,[bear.id])
        assert s.state.cards[bear.id].zone=='p1:battlefield'
        assert all(s.state.cards[c.id].zone=='p2:hand' for c in foreign)
    roundtrip(s)


def test_press_enemy_actual_bounce_nonland_then_only_low_enough_instant_sorcery(cards):
    s=setup(cards,'Press the Enemy')
    target=put(s,"Ashnod's Altar",'battlefield',pid='p2')
    spell=put(s,'Divination','hand')
    bear=put(s,'Grizzly Bears','hand')
    cast(s,'Press the Enemy',targets=[target.id])
    assert s.state.cards[target.id].zone=='p2:hand'
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    assert spell.id in [o.id for o in d.options] and bear.id not in [o.id for o in d.options]
    answer(s,[spell.id])
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    roundtrip(s)


def test_diluvian_actual_per_opponent_announced_targets_cast_once_each_with_exile_rider(cards):
    s=setup(cards,'Diluvian Primordial')
    first=put(s,'Divination','graveyard',pid='p2')
    second=put(s,'Giant Growth','graveyard',pid='p3')
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Diluvian Primordial')
    assert s.state.rules.decision.resume['step']=='trigger_group'
    answer(s,[first.id])
    answer(s,[second.id])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert first.id in [o.id for o in s.state.rules.decision.options]
    assert second.id not in [o.id for o in s.state.rules.decision.options]
    answer(s,[first.id])
    assert s.state.cards[first.id].zone=='stack'
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[second.id])
    if s.state.rules.decision is not None:
        answer(s,[bear.id])
    settle(s)
    assert s.state.cards[first.id].zone=='p2:exile'
    assert s.state.cards[second.id].zone=='p3:exile'
    roundtrip(s)


def test_geode_actual_combat_damage_casts_one_commander_from_command_zone(cards):
    s=setup(cards,'Geode Golem')
    source=put(s,'Geode Golem','battlefield')
    commander=put(s,'Rivaz of the Claw','command')
    act(s,'p1',type='set_commander',card_id=commander.id)
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    for _ in range(50):
        d=s.state.rules.decision
        if d is not None:
            if d.kind=='declare_blockers':
                act(s,d.player,type='declare_blockers',blocks=[])
                continue
            assert d.resume['step']=='free_cast_pick',d
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[commander.id])
    assert s.state.cards[commander.id].zone=='p1:battlefield'
    assert s.state.players['p2'].life==35
    roundtrip(s)


def test_sorcerous_actual_mill_nine_then_can_cast_preexisting_graveyard_spell_with_exile_rider(cards):
    s=setup(cards,'Sorcerous Squall')
    spell=put(s,'Divination','graveyard',pid='p2')
    before=len(s.state.zones['p2:library'])
    cast(s,'Sorcerous Squall',targets=['p2'])
    assert len(s.state.zones['p2:library'])==before-9
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert spell.id in [o.id for o in s.state.rules.decision.options]
    answer(s,[spell.id])
    assert s.state.cards[spell.id].zone=='p2:exile'
    roundtrip(s)


@pytest.mark.parametrize('name',['Geode Golem','Diluvian Primordial','Mindclaw Shaman','Press the Enemy',
    "Great Intelligence's Plan",'Anrakyr the Traveller','Sorcerous Squall','Reinterpret'])
def test_staged_all_printed_lines_compile_without_fallback(cards,name):
    from app.rules import coverage
    result=coverage.of_card_data(cards.resolve(name))
    assert result.level=='FULL',result


@pytest.mark.parametrize('zone',['hand','graveyard'])
def test_anrakyr_actual_life_alternative_can_decline_and_cannot_afford_three_at_two_life(cards,zone):
    s=setup(cards,'Anrakyr the Traveller')
    source=put(s,'Anrakyr the Traveller','battlefield')
    altar=put(s,"Ashnod's Altar",zone)
    act(s,'p1',type='set_life',player='p1',value=2)
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    d=s.state.rules.decision
    if d is not None:
        assert altar.id not in [o.id for o in d.options]
        answer(s,[])
    assert s.state.players['p1'].life==2
    assert s.state.cards[altar.id].zone=='p1:'+zone
    roundtrip(s)


@pytest.mark.parametrize('name',['Reinterpret','Press the Enemy'])
def test_counter_or_bounce_actual_announced_x_is_included_in_frozen_target_stack_value(cards,name):
    s=setup(cards,name,'Earthquake')
    to_phase(s,'main1',turn=2)
    target=put(s,'Earthquake','hand',pid='p2')
    mana(s,R=1,C=3,pid='p2')
    act(s,'p2',type='set_prefs',hold_priority=True)
    act(s,'p2',type='cast_spell',card_id=target.id,x_value=3)
    for _ in range(3):
        if s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    spell=put(s,'Divination','hand')
    cast(s,name,targets=[target.id])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert spell.id in [o.id for o in s.state.rules.decision.options]
    answer(s,[spell.id])
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert s.state.cards[target.id].zone==('p2:hand' if name=='Press the Enemy' else 'p2:graveyard')
    roundtrip(s)


def test_reinterpret_uncounterable_target_still_allows_native_free_cast(cards):
    s=setup(cards,'Reinterpret','Supreme Verdict')
    target=put(s,'Supreme Verdict','hand')
    mana(s,W=2,U=1,C=1)
    act(s,'p1',type='cast_spell',card_id=target.id)
    spell=put(s,'Divination','hand')
    cast(s,'Reinterpret',targets=[target.id])
    assert s.state.cards[target.id].zone=='stack'
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[spell.id])
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert s.state.cards[target.id].zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('mode',['counter','sourcegone','decline'])
def test_anrakyr_actual_trigger_counter_source_departure_or_optional_decline(cards,mode):
    s=setup(cards,'Anrakyr the Traveller','Stifle','Murder')
    source=put(s,'Anrakyr the Traveller','battlefield')
    altar=put(s,"Ashnod's Altar",'graveyard')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    if mode=='counter':
        trigger=next(k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_card==source.id)
        cast(s,'Stifle',targets=[trigger])
        assert s.state.rules.decision is None
    elif mode=='sourcegone':
        cast(s,'Murder',targets=[source.id])
        assert s.state.cards[source.id].zone=='p1:graveyard'
        assert s.state.rules.decision.resume['step']=='free_cast_pick'
        answer(s,[altar.id])
        assert s.state.cards[altar.id].zone=='p1:battlefield'
    else:
        settle(s)
        answer(s,[])
    if mode!='sourcegone':
        assert s.state.cards[altar.id].zone=='p1:graveyard'
    assert not s.state.rules.permissions and s.state.rules.free_cast_then is None
    roundtrip(s)


def test_anrakyr_actual_hand_artifact_x_forced_zero_and_artifact_land_is_not_a_spell(cards):
    s=setup(cards,'Anrakyr the Traveller','Hangarback Walker','Darksteel Citadel')
    source=put(s,'Anrakyr the Traveller','battlefield')
    walker=put(s,'Hangarback Walker','hand')
    land=put(s,'Darksteel Citadel','hand')
    bear=put(s,'Grizzly Bears','hand')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    d=s.state.rules.decision
    ids=[o.id for o in d.options]
    assert walker.id in ids and land.id not in ids and bear.id not in ids
    life=s.state.players['p1'].life
    answer(s,[walker.id])
    assert s.state.players['p1'].life==life
    assert s.state.cards[walker.id].zone=='p1:graveyard'
    assert not any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize('name,face,life_cost',[
    ('Two-Handed Axe // Sweeping Cleave',0,3),
    ('Cosima, God of the Voyage // The Omenkeel',1,2),
])
def test_anrakyr_actual_artifact_spell_face_not_physical_card_front_controls_eligibility_and_life(cards,name,face,life_cost):
    s=setup(cards,'Anrakyr the Traveller',name)
    source=put(s,'Anrakyr the Traveller','battlefield')
    spell=put(s,name,'hand')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    d=s.state.rules.decision
    ids=[o.id for o in d.options if o.card_id==spell.id]
    assert ids==[spell.id+'@'+str(face)]
    life=s.state.players['p1'].life
    answer(s,ids)
    assert s.state.players['p1'].life==life-life_cost
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name',['Angel of Jubilation','Platinum Emperion'])
def test_anrakyr_actual_prohibition_on_paying_or_changing_life_does_not_offer_artifact(cards,name):
    s=setup(cards,'Anrakyr the Traveller',name)
    source=put(s,'Anrakyr the Traveller','battlefield')
    put(s,name,'battlefield')
    altar=put(s,"Ashnod's Altar",'hand')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    d=s.state.rules.decision
    if d is not None:
        assert altar.id not in [o.card_id for o in d.options]
        answer(s,[])
    assert s.state.cards[altar.id].zone=='p1:hand'
    roundtrip(s)


def test_anrakyr_actual_life_alternative_preserves_optional_additional_mana_kicker(cards):
    s=setup(cards,'Anrakyr the Traveller','Everflowing Chalice')
    source=put(s,'Anrakyr the Traveller','battlefield')
    spell=put(s,'Everflowing Chalice','hand')
    to_phase(s,'declare_attackers',turn=4)
    mana(s,C=2)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    life=s.state.players['p1'].life
    answer(s,[spell.id])
    assert 'kicker:1' in [o.id for o in s.state.rules.decision.options]
    answer(s,['kicker:1'])
    assert s.state.players['p1'].life==life
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert s.state.cards[spell.id].counters.get('charge')==1
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


@pytest.mark.parametrize('cast_it',[True,False])
def test_greatness_actual_upkeep_other_permanent_value_and_cast_or_scry(cards,cast_it):
    s=setup(cards,'In Search of Greatness','Geode Golem')
    put(s,'In Search of Greatness','battlefield')
    put(s,'Grizzly Bears','battlefield')
    put(s,'Geode Golem','battlefield',pid='p2')
    altar=put(s,"Ashnod's Altar",'hand')
    divination=put(s,'Divination','hand')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    assert altar.id in [o.id for o in d.options]
    assert divination.id not in [o.id for o in d.options]
    answer(s,[altar.id] if cast_it else [])
    if cast_it:
        assert s.state.cards[altar.id].zone=='p1:battlefield'
        assert s.state.rules.decision is None
    else:
        assert s.state.cards[altar.id].zone=='p1:hand'
        assert s.state.rules.decision is not None
        assert 'scry' in s.state.rules.decision.prompt.lower()
    roundtrip(s)


@pytest.mark.parametrize('mastery',[False,True])
def test_talent_actual_revealed_library_casts_one_or_two_before_putting_rest_in_owner_graveyard(cards,mastery):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Talent of the Telepath','Murder','Earthquake')
    if mastery:
        put(s,'Murder','graveyard')
        put(s,'Earthquake','graveyard')
    packet=stack_library(s,['Divination','Giant Growth','Grizzly Bears'],pid='p2')
    bear=put(s,'Grizzly Bears','battlefield')
    before=len(s.state.zones['p2:library'])
    cast(s,'Talent of the Telepath',targets=['p2'])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert s.state.cards[packet[0]].zone=='p2:library'
    answer(s,[packet[0]])
    if mastery:
        assert s.state.rules.decision.resume['step']=='free_cast_pick'
        assert s.state.cards[packet[0]].zone=='stack'
        answer(s,[packet[1]])
        if s.state.rules.decision is not None:
            answer(s,[bear.id])
    settle(s)
    assert len(s.state.zones['p2:library'])==before-7
    assert all(s.state.cards[cid].zone=='p2:graveyard' for cid in packet)
    assert s.state.cards[packet[2]].revealed_to==[]
    roundtrip(s)


@pytest.mark.parametrize('finished',[False,True])
def test_mindclaw_actual_public_reveal_rest_websocket_and_end_of_resolution_cleanup(cards,settings,finished):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s=setup(cards,'Mindclaw Shaman')
    spell=put(s,'Divination','hand',pid='p2')
    remaining=put(s,'Grizzly Bears','hand',pid='p2')
    hidden=put(s,'Giant Growth','hand',pid='p3')
    cast(s,'Mindclaw Shaman')
    answer(s,['p2'])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    if finished:
        answer(s,[spell.id])
    with TestClient(create_app(settings)) as client:
        room=client.app.state.services.hub.create_room(s,mode='lan')
        for player,seat in room.seats.items():
            seat.token='mindclaw45-'+player
        room.spectator_tokens.add('mindclaw45-spectator')
        for viewer in ['p1','p2','p3','spectator']:
            token='mindclaw45-'+viewer
            payload=client.get(f'/api/games/{room.id}/view',headers={'X-Seat-Token':token}).json()
            with client.websocket_connect(f'/ws/games/{room.id}?token={token}') as ws:
                frame=ws.receive_json()
            for view in [payload,frame['view']]:
                assert ('name' in view['cards'].get(remaining.id,{}))==(not finished or viewer=='p2')
                assert ('name' in view['cards'].get(hidden.id,{}))==(viewer=='p3')
    roundtrip(s)


@pytest.mark.parametrize('can_pay',[False,True])
def test_mindclaw_foreign_additional_discard_is_paid_by_caster_not_hand_owner(cards,can_pay):
    s=setup(cards,'Mindclaw Shaman','Cathartic Reunion')
    own_hand=list(s.state.zones['p1:hand'])
    if own_hand:
        act(s,'p1',type='move',card_ids=own_hand,to={'player':'p1','zone':'graveyard'})
    foreign=put(s,'Cathartic Reunion','hand',pid='p2')
    fillers=[put(s,name,'hand') for name in ('Grizzly Bears','Giant Growth')] if can_pay else []
    cast(s,'Mindclaw Shaman')
    answer(s,['p2'])
    d=s.state.rules.decision
    if not can_pay:
        from app.game.errors import ActionError

        # Hidden hand costs remain offered; the attempted native cast must refuse.
        assert foreign.id in [o.card_id for o in d.options]
        with pytest.raises(ActionError):
            answer(s,[foreign.id])
        answer(s,[])
        assert s.state.cards[foreign.id].zone=='p2:hand'
    else:
        answer(s,[foreign.id])
        d=s.state.rules.decision
        if d is not None:
            answer(s,[next(o.id for o in d.options if o.card_id==c.id) for c in fillers])
        assert all(s.state.cards[c.id].zone=='p1:graveyard' for c in fillers)
        assert s.state.cards[foreign.id].zone=='p2:graveyard'
        assert len(s.state.zones['p1:hand'])==3
    roundtrip(s)


def test_mindclaw_actual_artifact_adventure_card_offers_only_instant_spell_face(cards):
    name='Two-Handed Axe // Sweeping Cleave'
    s=setup(cards,'Mindclaw Shaman',name)
    spell=put(s,name,'hand',pid='p2')
    source=cast(s,'Mindclaw Shaman')
    answer(s,['p2'])
    d=s.state.rules.decision
    assert [o.id for o in d.options if o.card_id==spell.id]==[spell.id+'@1']
    answer(s,[spell.id+'@1'])
    answer(s,[source.id])
    assert s.state.cards[spell.id].zone=='p2:exile'
    roundtrip(s)


@pytest.mark.parametrize('mode',['counter','sourcegone','decline'])
def test_mindclaw_actual_trigger_counter_source_departure_and_decline_end_hand_authority(cards,mode):
    s=setup(cards,'Mindclaw Shaman','Stifle','Murder')
    spell=put(s,'Divination','hand',pid='p2')
    source=cast(s,'Mindclaw Shaman')
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['p2'])
    if mode=='counter':
        trigger=next(k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_card==source.id)
        cast(s,'Stifle',targets=[trigger])
        assert not s.state.cards[spell.id].revealed_to
    elif mode=='sourcegone':
        cast(s,'Murder',targets=[source.id])
        assert s.state.cards[source.id].zone=='p1:graveyard'
        answer(s,[spell.id])
        assert s.state.cards[spell.id].zone=='p2:graveyard'
    else:
        settle(s)
        answer(s,[])
        assert not s.state.cards[spell.id].revealed_to
    if mode!='sourcegone':
        assert s.state.cards[spell.id].zone=='p2:hand'
    assert not s.state.rules.permissions and s.state.rules.free_cast_then is None
    roundtrip(s)


def test_mindclaw_actual_target_cannot_be_controller_and_foreign_x_spell_uses_zero(cards):
    from app.game.errors import ActionError

    s=setup(cards,'Mindclaw Shaman','Earthquake')
    spell=put(s,'Earthquake','hand',pid='p2')
    cast(s,'Mindclaw Shaman')
    d=s.state.rules.decision
    with pytest.raises(ActionError):
        act(s,d.player,type='choose',decision_id=d.id,option_ids=['p1'])
    answer(s,['p2'])
    life={pid:p.life for pid,p in s.state.players.items()}
    answer(s,[spell.id])
    assert {pid:p.life for pid,p in s.state.players.items()}==life
    assert s.state.cards[spell.id].zone=='p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('choice',['discard','cast'])
def test_great_intelligence_impossible_discard_still_legal_and_free_cast_can_decline(cards,choice):
    s=setup(cards,"Great Intelligence's Plan")
    hand=list(s.state.zones['p2:hand'])
    if hand:
        act(s,'p2',type='move',card_ids=hand,to={'player':'p2','zone':'graveyard'})
    cast(s,"Great Intelligence's Plan",targets=['p2'])
    assert s.state.rules.decision.player=='p2'
    answer(s,[choice])
    if choice=='cast' and s.state.rules.decision is not None:
        assert s.state.rules.decision.player=='p1'
        answer(s,[])
    assert s.state.rules.decision is None and not s.state.rules.permissions
    roundtrip(s)


def test_great_intelligence_can_cast_newly_drawn_card_and_illegal_target_aborts_all_effects(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,"Great Intelligence's Plan")
    top=stack_library(s,['Grizzly Bears'])[0]
    cast(s,"Great Intelligence's Plan",targets=['p2'])
    assert s.state.cards[top].zone=='p1:hand'
    answer(s,['cast'])
    answer(s,[top])
    assert s.state.cards[top].zone=='p1:battlefield'
    source=put(s,"Great Intelligence's Plan",'hand')
    before=len(s.state.zones['p1:hand'])
    mana(s,U=2,C=5)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'])
    act(s,'p2',type='concede')
    settle(s)
    assert len(s.state.zones['p1:hand'])==before-1
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_reinterpret_actual_mdfc_only_affordable_artifact_back_face_is_offered(cards):
    name='Cosima, God of the Voyage // The Omenkeel'
    s=setup(cards,'Reinterpret','Twincast',name)
    original=put(s,'Divination','hand')
    mana(s,U=1,C=2)
    act(s,'p1',type='cast_spell',card_id=original.id)
    target=put(s,'Twincast','hand')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=target.id,targets=[original.id])
    spell=put(s,name,'hand')
    cast(s,'Reinterpret',targets=[target.id])
    d=s.state.rules.decision
    assert [o.id for o in d.options if o.card_id==spell.id]==[spell.id+'@1']
    answer(s,[spell.id+'@1'])
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert s.state.cards[target.id].zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name',['Reinterpret','Press the Enemy'])
def test_counter_or_bounce_illegal_target_after_actual_response_has_no_free_cast(cards,name):
    s=setup(cards,name,'Memory Lapse')
    to_phase(s,'main1',turn=2)
    target=put(s,'Divination','hand',pid='p2')
    mana(s,U=1,C=2,pid='p2')
    act(s,'p2',type='set_prefs',hold_priority=True)
    act(s,'p2',type='cast_spell',card_id=target.id)
    for _ in range(3):
        if s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    spell=put(s,'Divination','hand')
    source=put(s,name,'hand')
    mana(s,U=5,R=1,C=5)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[target.id])
    cast(s,'Memory Lapse',targets=[target.id])
    assert s.state.cards[spell.id].zone=='p1:hand'
    assert s.state.cards[target.id].zone=='p2:library'
    assert s.state.zones['p2:library'][0]==target.id
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.decision is None and not s.state.rules.permissions
    roundtrip(s)


@pytest.mark.parametrize('name',['Reinterpret','Press the Enemy'])
@pytest.mark.parametrize('pay',[False,True])
def test_counter_or_bounce_free_cast_still_pays_real_thalia_tax_and_cancellation_closes_offer(cards,name,pay):
    s=setup(cards,name,'Thalia, Guardian of Thraben')
    to_phase(s,'main1',turn=2)
    target=put(s,'Divination','hand',pid='p2')
    mana(s,U=1,C=2,pid='p2')
    act(s,'p2',type='set_prefs',hold_priority=True)
    act(s,'p2',type='cast_spell',card_id=target.id)
    for _ in range(3):
        if s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    put(s,'Thalia, Guardian of Thraben','battlefield')
    spell=put(s,'Divination','hand')
    cast(s,name,targets=[target.id])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[spell.id])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    if pay:
        mana(s,C=1)
    answer(s,['pay' if pay else 'cancel'])
    assert s.state.cards[spell.id].zone==('p1:graveyard' if pay else 'p1:hand')
    assert not s.state.rules.permissions and s.state.rules.free_cast_then is None
    assert s.state.rules.decision is None
    roundtrip(s)


def test_press_enemy_actual_adventure_spell_filter_and_opponent_only_target(cards):
    from app.game.errors import ActionError

    name='Two-Handed Axe // Sweeping Cleave'
    s=setup(cards,'Press the Enemy',name)
    own=put(s,"Ashnod's Altar",'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    target=put(s,'Rivaz of the Claw','battlefield',pid='p2')
    spell=put(s,name,'hand')
    source=put(s,'Press the Enemy','hand')
    mana(s,U=2,C=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=[own.id])
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[target.id])
    settle(s)
    d=s.state.rules.decision
    assert [o.id for o in d.options if o.card_id==spell.id]==[spell.id+'@1']
    answer(s,[spell.id+'@1'])
    answer(s,[bear.id])
    assert s.state.cards[spell.id].zone=='p1:exile'
    assert s.state.cards[target.id].zone=='p2:hand'
    roundtrip(s)


def geode_offer(s,source,blocker=None,*,stop_trigger=False):
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    for _ in range(50):
        if stop_trigger and any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values()):
            return None
        d=s.state.rules.decision
        if d is not None:
            if d.kind=='declare_blockers':
                blocks=[{'blocker_id':blocker.id,'attacker_id':source.id}] if blocker else []
                act(s,d.player,type='declare_blockers',blocks=blocks)
                continue
            if d.kind=='divide':
                assert blocker is not None and [o.id for o in d.options]==[blocker.id,'p2']
                act(s,d.player,type='choose',decision_id=d.id,amounts=[3,2])
                continue
            assert d.resume['step']=='free_cast_pick',d
            return d
        act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('Combat never reached actual Geode cast offer')


def test_geode_actual_lethal_trample_trigger_and_two_legal_partners_still_one_commander_cast(cards):
    s=setup(cards,'Geode Golem','Tana, the Bloodsower','Tymna the Weaver')
    source=put(s,'Geode Golem','battlefield')
    blocker=put(s,'Rivaz of the Claw','battlefield',pid='p2')
    for c in list(s.state.cards.values()):
        if c.owner=='p1' and c.commander_key:
            act(s,'p1',type='set_commander',card_id=c.id,value=False)
    first=put(s,'Tana, the Bloodsower','command')
    second=put(s,'Tymna the Weaver','command')
    for c in (first,second):
        act(s,'p1',type='set_commander',card_id=c.id)
    to_phase(s,'declare_attackers',turn=4)
    d=geode_offer(s,source,blocker)
    assert {first.id,second.id}.issubset({o.card_id for o in d.options})
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.players['p2'].life==38
    answer(s,[first.id])
    assert s.state.cards[first.id].zone=='p1:battlefield'
    assert s.state.cards[second.id].zone=='p1:command'
    assert s.state.rules.decision is None and not s.state.rules.permissions
    roundtrip(s)


@pytest.mark.parametrize('pay',[False,True])
def test_geode_actual_free_commander_still_requires_prior_cast_commander_tax(cards,pay):
    s=setup(cards,'Geode Golem')
    commander=put(s,'Rivaz of the Claw','command')
    act(s,'p1',type='set_commander',card_id=commander.id)
    mana(s,C=1,B=1,R=1)
    act(s,'p1',type='cast_spell',card_id=commander.id)
    settle(s)
    assert s.state.cards[commander.id].zone=='p1:battlefield'
    commander=put(s,'Rivaz of the Claw','command')
    source=put(s,'Geode Golem','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    geode_offer(s,source)
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[commander.id])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    if pay:
        mana(s,C=2)
    answer(s,['pay' if pay else 'cancel'])
    assert s.state.cards[commander.id].zone==('p1:battlefield' if pay else 'p1:command')
    assert not s.state.rules.permissions and s.state.rules.free_cast_then is None
    roundtrip(s)


def test_geode_actual_commander_can_enter_command_zone_after_combat_trigger_occurs(cards):
    s=setup(cards,'Geode Golem','Murder')
    commander=put(s,'Rivaz of the Claw','battlefield')
    act(s,'p1',type='set_commander',card_id=commander.id)
    source=put(s,'Geode Golem','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    geode_offer(s,source,stop_trigger=True)
    assert s.state.cards[commander.id].zone=='p1:battlefield'
    cast(s,'Murder',targets=[commander.id])
    assert 'commander' in s.state.rules.decision.resume['step']
    answer(s,['yes'])
    assert s.state.cards[commander.id].zone=='p1:command'
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[commander.id])
    assert s.state.cards[commander.id].zone=='p1:battlefield'
    roundtrip(s)


def test_geode_actual_optional_decline_does_not_leave_later_free_commander_permission(cards):
    from app.game.errors import ActionError
    s=setup(cards,'Geode Golem')
    commander=put(s,'Rivaz of the Claw','command')
    act(s,'p1',type='set_commander',card_id=commander.id)
    source=put(s,'Geode Golem','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    geode_offer(s,source)
    answer(s,[])
    assert s.state.cards[commander.id].zone=='p1:command'
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=commander.id,free=True)
    assert not s.state.rules.permissions and s.state.rules.free_cast_then is None
    roundtrip(s)


def test_native_free_multikicker_seventh_chalice_kick_uses_exact_numeric_count(cards):
    s=setup(cards,'Anrakyr the Traveller','Everflowing Chalice')
    source=put(s,'Anrakyr the Traveller','battlefield')
    spell=put(s,'Everflowing Chalice','hand')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    answer(s,[spell.id])
    answer(s,['kicker:other'])
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,name='7')
    mana(s,C=14)
    answer(s,['pay'])
    assert s.state.cards[spell.id].counters.get('charge',0)==7
    roundtrip(s)


def test_greatness_actual_no_other_permanents_excludes_self_and_offers_mana_value_one(cards):
    s=setup(cards,'In Search of Greatness','Sol Ring')
    put(s,'In Search of Greatness','battlefield')
    ring=put(s,'Sol Ring','hand')
    bear=put(s,'Grizzly Bears','hand')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    d=s.state.rules.decision
    assert ring.id in [o.card_id for o in d.options]
    assert bear.id not in [o.card_id for o in d.options]
    answer(s,[ring.id])
    assert s.state.cards[ring.id].zone=='p1:battlefield'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_greatness_actual_source_blink_new_enchantment_incarnation_counts_as_other_permanent(cards):
    s=setup(cards,'In Search of Greatness','Flicker of Fate','Sol Ring')
    source=put(s,'In Search of Greatness','battlefield')
    old=s.state.rules.object_id(source.id)
    altar=put(s,"Ashnod's Altar",'hand')
    ring=put(s,'Sol Ring','hand')
    to_phase(s,'upkeep',turn=4)
    cast(s,'Flicker of Fate',targets=[source.id])
    assert s.state.rules.object_id(source.id)!=old
    d=s.state.rules.decision
    assert altar.id in [o.card_id for o in d.options]
    assert ring.id not in [o.card_id for o in d.options]
    answer(s,[altar.id])
    assert s.state.cards[altar.id].zone=='p1:battlefield'
    roundtrip(s)


def test_greatness_actual_current_permanent_type_includes_battle_spell(cards):
    name='Invasion of Belenon // Belenon War Anthem'
    s=setup(cards,'In Search of Greatness',name)
    put(s,'In Search of Greatness','battlefield')
    put(s,'Grizzly Bears','battlefield')
    battle=put(s,name,'hand')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    d=s.state.rules.decision
    selected=next(o.id for o in d.options if o.card_id==battle.id)
    answer(s,[selected])
    if s.state.rules.decision is not None:
        answer(s,['p2'])
    assert s.state.cards[battle.id].zone=='p1:battlefield'
    assert s.state.cards[battle.id].counters.get('defense')==5
    assert any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


def extract_ready(cards,names,x,*extra):
    s=setup(cards,'Extract Brain','Forest',*extra)
    hand=list(s.state.zones['p2:hand'])
    if hand:
        act(s,'p2',type='move',card_ids=hand,to={'player':'p2','zone':'graveyard'})
    selected=[put(s,name,'hand',pid='p2') for name in names]
    cast(s,'Extract Brain',targets=['p2'],x_value=x)
    return s,selected


@pytest.mark.parametrize('name',['Grizzly Bears','Divination'])
def test_extract_actual_opponent_chooses_only_x_then_caster_privately_looks_and_casts_selected_spell(cards,name):
    s,hand=extract_ready(cards,['Grizzly Bears','Divination'],1)
    spell=next(c for c in hand if c.name==name)
    other=next(c for c in hand if c.id!=spell.id)
    d=s.state.rules.decision
    assert d.player=='p2' and d.min_choices==d.max_choices==1
    assert 'name' not in s.view('p1')['cards'].get(spell.id,{})
    answer(s,[spell.id])
    d=s.state.rules.decision
    assert d.player=='p1' and d.resume['stage']=='view'
    assert s.view('p1')['cards'][spell.id]['name']==name
    assert 'name' not in s.view('p1')['cards'].get(other.id,{})
    assert 'name' not in s.view('p3')['cards'].get(spell.id,{})
    answer(s,['ok'])
    assert {o.card_id for o in s.state.rules.decision.options}=={spell.id}
    answer(s,[spell.id])
    assert s.state.cards[spell.id].zone==('p1:battlefield' if name=='Grizzly Bears' else 'p2:graveyard')
    assert s.state.cards[spell.id].owner=='p2'
    assert s.state.cards[other.id].zone=='p2:hand' and not s.state.cards[other.id].revealed_to
    roundtrip(s)


@pytest.mark.parametrize('x',[0,5])
def test_extract_actual_zero_or_more_than_hand_uses_exact_feasible_count_and_land_is_inspected_not_cast(cards,x):
    s,hand=extract_ready(cards,['Forest'],x)
    land=hand[0]
    if x:
        d=s.state.rules.decision
        assert d.player=='p2' and d.min_choices==d.max_choices==1
        answer(s,[land.id])
        assert s.view('p1')['cards'][land.id]['name']=='Forest'
        answer(s,['ok'])
    assert s.state.rules.decision is None
    assert s.state.cards[land.id].zone=='p2:hand' and not s.state.cards[land.id].revealed_to
    assert not s.state.rules.permissions
    roundtrip(s)


@pytest.mark.parametrize('prior',[[],['p1'],['p3'],['*']])
def test_extract_actual_decline_removes_only_new_private_caster_right_and_preserves_previous_rights(cards,prior):
    s,hand=extract_ready(cards,['Grizzly Bears','Divination'],1)
    spell=hand[0]
    if prior:
        act(s,'p2',type='reveal',card_ids=[spell.id],**({} if prior==['*'] else {'to':prior}))
    answer(s,[spell.id])
    answer(s,['ok'])
    answer(s,[])
    assert s.state.cards[spell.id].revealed_to==prior
    assert s.state.cards[spell.id].zone=='p2:hand'
    assert not s.state.rules.permissions
    roundtrip(s)


def test_private_hide_named_viewer_validation_is_atomic_preserves_all_and_ordinary_schema(cards):
    from app.game import actions as A
    from app.game.errors import ActionError

    s=setup(cards)
    spell=put(s,'Divination','hand',pid='p2')
    act(s,'p2',type='reveal',card_ids=[spell.id],to=['p1','p3'])
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='hide',card_ids=[spell.id],viewers=['p1','missing'])
    assert s.state.model_dump_json()==before
    act(s,'p2',type='hide',card_ids=[spell.id],viewers=['p1'])
    assert s.state.cards[spell.id].revealed_to==['p3']
    act(s,'p2',type='reveal',card_ids=[spell.id])
    act(s,'p2',type='hide',card_ids=[spell.id],viewers=['p1','p3'])
    assert s.state.cards[spell.id].revealed_to==['*']
    act(s,'p2',type='hide',card_ids=[spell.id])
    assert not s.state.cards[spell.id].revealed_to
    assert 'viewers' not in A.Hide(card_ids=[spell.id]).model_dump(mode='json')
    roundtrip(s)


@pytest.mark.parametrize('stage',['owner','view','done'])
def test_extract_actual_private_owner_and_caster_rest_websocket_views(cards,settings,stage):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s,hand=extract_ready(cards,['Grizzly Bears','Divination'],1)
    chosen,hidden=hand
    if stage!='owner':
        answer(s,[chosen.id])
    if stage=='done':
        answer(s,['ok'])
        answer(s,[])
    with TestClient(create_app(settings)) as client:
        room=client.app.state.services.hub.create_room(s,mode='lan')
        for player,seat in room.seats.items():
            seat.token='extract45-'+player
        room.spectator_tokens.add('extract45-spectator')
        for viewer in ['p1','p2','p3','spectator']:
            token='extract45-'+viewer
            payload=client.get(f'/api/games/{room.id}/view',headers={'X-Seat-Token':token}).json()
            with client.websocket_connect(f'/ws/games/{room.id}?token={token}') as ws:
                frame=ws.receive_json()
            for view in [payload,frame['view']]:
                assert ('name' in view['cards'].get(chosen.id,{}))==(viewer=='p2' or (stage=='view' and viewer=='p1'))
                assert ('name' in view['cards'].get(hidden.id,{}))==(viewer=='p2')
    roundtrip(s)


def test_extract_native_selected_object_reincarnation_cannot_cast_or_hide_new_hand_object(cards):
    s,hand=extract_ready(cards,['Grizzly Bears'],1)
    spell=hand[0]
    answer(s,[spell.id])
    original=s.state.rules.object_id(spell.id)
    act(s,'p2',type='move',card_ids=[spell.id],to={'player':'p2','zone':'graveyard'})
    act(s,'p2',type='move',card_ids=[spell.id],to={'player':'p2','zone':'hand'})
    assert s.state.rules.object_id(spell.id)!=original
    act(s,'p2',type='reveal',card_ids=[spell.id],to=['p3'])
    answer(s,['ok'])
    assert s.state.rules.decision is None
    assert s.state.cards[spell.id].zone=='p2:hand'
    assert s.state.cards[spell.id].revealed_to==['p3']
    assert 'name' not in s.view('p1')['cards'].get(spell.id,{})
    roundtrip(s)


def test_extract_actual_free_foreign_spell_extra_tax_cancel_closes_private_right_and_offer(cards):
    s,hand=extract_ready(cards,['Divination'],1,'Thalia, Guardian of Thraben')
    spell=hand[0]
    put(s,'Thalia, Guardian of Thraben','battlefield')
    answer(s,[spell.id])
    answer(s,['ok'])
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[spell.id])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    answer(s,['cancel'])
    assert s.state.cards[spell.id].zone=='p2:hand' and not s.state.cards[spell.id].revealed_to
    assert s.state.rules.free_cast_then is None and not s.state.rules.permissions
    roundtrip(s)


def test_extract_whole_canonical_staged(cards):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve('Extract Brain'))
    assert result.level=='FULL',result


def test_extract_actual_illegal_opponent_target_aborts_without_looking_at_other_opponent_hand(cards):
    s=setup(cards,'Extract Brain')
    hidden=put(s,'Divination','hand',pid='p3')
    source=put(s,'Extract Brain','hand')
    mana(s,U=1,B=1,C=3)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'],x_value=3)
    act(s,'p2',type='concede')
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.decision is None and not s.state.rules.permissions
    assert not s.state.cards[hidden.id].revealed_to
    assert 'name' not in s.view('p1')['cards'].get(hidden.id,{})
    roundtrip(s)


def test_greatness_actual_no_hand_and_opponent_upkeep_then_own_upkeep_scry_fallback(cards):
    s=setup(cards,'In Search of Greatness')
    put(s,'In Search of Greatness','battlefield')
    hand=list(s.state.zones['p1:hand'])
    if hand:
        act(s,'p1',type='move',card_ids=hand,to={'player':'p1','zone':'graveyard'})
    to_phase(s,'upkeep',turn=2)
    settle(s)
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert 'scry' in s.state.rules.decision.prompt.lower()
    assert not s.state.zones.get('p1:hand')
    roundtrip(s)


def test_greatness_actual_canceled_optional_cast_payment_takes_scry_fallback(cards):
    s=setup(cards,'In Search of Greatness','Thalia, Guardian of Thraben')
    put(s,'In Search of Greatness','battlefield')
    put(s,'Thalia, Guardian of Thraben','battlefield')
    altar=put(s,"Ashnod's Altar",'hand')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[altar.id])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    answer(s,['cancel'])
    assert s.state.cards[altar.id].zone=='p1:hand'
    assert 'scry' in s.state.rules.decision.prompt.lower()
    roundtrip(s)


def test_greatness_whole_canonical_staged(cards):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve('In Search of Greatness'))
    assert result.level=='FULL',result


def test_extract_actual_two_chosen_cards_both_mdfc_spell_faces_but_only_one_cast_and_other_rights_expire(cards):
    name='Cosima, God of the Voyage // The Omenkeel'
    s=setup(cards,'Extract Brain',name)
    hand=list(s.state.zones['p2:hand'])
    if hand:
        act(s,'p2',type='move',card_ids=hand,to={'player':'p2','zone':'graveyard'})
    spell=put(s,name,'hand',pid='p2')
    other=put(s,'Grizzly Bears','hand',pid='p2')
    hidden=put(s,'Divination','hand',pid='p2')
    cast(s,'Extract Brain',targets=['p2'],x_value=2)
    assert s.state.rules.decision.min_choices==s.state.rules.decision.max_choices==2
    answer(s,[spell.id,other.id])
    assert s.view('p1')['cards'][spell.id]['name']==name
    assert s.view('p1')['cards'][other.id]['name']=='Grizzly Bears'
    assert 'name' not in s.view('p1')['cards'].get(hidden.id,{})
    answer(s,['ok'])
    d=s.state.rules.decision
    assert {o.id for o in d.options if o.card_id==spell.id}=={spell.id+'@0',spell.id+'@1'}
    answer(s,[spell.id+'@1'])
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert s.state.cards[other.id].zone=='p2:hand' and not s.state.cards[other.id].revealed_to
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    roundtrip(s)


def test_greatness_actual_mdfc_value_applies_to_chosen_permanent_spell_face(cards):
    name='Cosima, God of the Voyage // The Omenkeel'
    s=setup(cards,'In Search of Greatness','Sol Ring',name)
    put(s,'In Search of Greatness','battlefield')
    put(s,'Sol Ring','battlefield')
    spell=put(s,name,'hand')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    d=s.state.rules.decision
    assert [o.id for o in d.options if o.card_id==spell.id]==[spell.id+'@1']
    answer(s,[spell.id+'@1'])
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_extract_cleanup_never_restores_other_viewer_right_removed_during_inspection(cards):
    s,hand=extract_ready(cards,['Grizzly Bears'],1)
    spell=hand[0]
    act(s,'p2',type='reveal',card_ids=[spell.id],to=['p3'])
    answer(s,[spell.id])
    assert s.state.cards[spell.id].revealed_to==['p1','p3']
    act(s,'p2',type='hide',card_ids=[spell.id],viewers=['p3'])
    answer(s,['ok'])
    answer(s,[])
    assert not s.state.cards[spell.id].revealed_to
    roundtrip(s)


def test_greatness_actual_cast_countered_after_commit_does_not_take_scry_fallback(cards):
    s=setup(cards,'In Search of Greatness','Counterspell')
    put(s,'In Search of Greatness','battlefield')
    put(s,'Grizzly Bears','battlefield')
    altar=put(s,"Ashnod's Altar",'hand')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[altar.id])
    assert s.state.cards[altar.id].zone=='stack' and s.state.rules.decision is None
    cast(s,'Counterspell',targets=[altar.id])
    assert s.state.cards[altar.id].zone=='p1:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


def squall_fuel(s):
    return [put(s,name,'graveyard') for name in ('Grizzly Bears','Divination','Giant Growth',"Ashnod's Altar",'Rivaz of the Claw','Forest')]


def test_squall_actual_delve_six_pays_only_generic_keeps_printed_value_nine_and_casts_preexisting_graveyard(cards):
    from tests.test_rules_wave4h_activation_costs import ch
    s=setup(cards,'Sorcerous Squall')
    fuel=squall_fuel(s)
    spell=put(s,'Divination','graveyard',pid='p2')
    source=put(s,'Sorcerous Squall','hand')
    mana(s,U=3)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'],contributions=[{'kind':'delve','card':c.id} for c in fuel])
    assert ch(s,s.state.cards[source.id]).mana_value==9
    assert all(s.state.cards[c.id].zone=='p1:exile' for c in fuel)
    assert not any(s.state.players['p1'].mana.values())
    settle(s)
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[spell.id])
    assert s.state.cards[spell.id].zone=='p2:exile'
    roundtrip(s)


def test_squall_actual_cannot_delve_seventh_card_or_pay_blue_requirement_with_delve(cards):
    from app.game.errors import ActionError
    s=setup(cards,'Sorcerous Squall','Murder')
    fuel=[*squall_fuel(s),put(s,'Murder','graveyard')]
    source=put(s,'Sorcerous Squall','hand')
    mana(s,U=3)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'],contributions=[{'kind':'delve','card':c.id} for c in fuel])
    assert all(s.state.cards[c.id].zone=='p1:graveyard' for c in fuel)
    assert s.state.cards[source.id].zone=='p1:hand'
    act(s,'p1',type='clear_mana',player='p1')
    mana(s,U=2)
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'],contributions=[{'kind':'delve','card':c.id} for c in fuel[:6]])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    assert all(s.state.cards[c.id].zone=='p1:graveyard' for c in fuel)
    answer(s,['cancel'])
    assert s.state.cards[source.id].zone=='p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('counter',['Counterspell','Memory Lapse'])
def test_squall_actual_cast_spell_exiles_if_countered_to_graveyard_but_not_other_destination(cards,counter):
    s=setup(cards,'Sorcerous Squall',counter)
    spell=put(s,'Divination','graveyard',pid='p2')
    cast(s,'Sorcerous Squall',targets=['p2'])
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[spell.id])
    assert s.state.cards[spell.id].zone=='stack'
    cast(s,counter,targets=[spell.id])
    if counter=='Counterspell':
        assert s.state.cards[spell.id].zone=='p2:exile'
    else:
        assert s.state.cards[spell.id].zone=='p2:library'
        assert s.state.zones['p2:library'][0]==spell.id
    roundtrip(s)


def test_squall_actual_mill_nine_replacement_to_exile_does_not_offer_the_diverted_cards(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Sorcerous Squall','Rest in Peace')
    put(s,'Rest in Peace','battlefield')
    settle(s)
    top=stack_library(s,['Divination','Giant Growth','Grizzly Bears'],pid='p2')
    before=len(s.state.zones['p2:library'])
    source=cast(s,'Sorcerous Squall',targets=['p2'])
    assert len(s.state.zones['p2:library'])==before-9
    assert all(s.state.cards[cid].zone=='p2:exile' for cid in top)
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.rules.decision is None and not s.state.rules.permissions
    roundtrip(s)


def test_squall_actual_can_cast_instant_adventure_of_artifact_card_from_graveyard(cards):
    name='Two-Handed Axe // Sweeping Cleave'
    s=setup(cards,'Sorcerous Squall',name)
    spell=put(s,name,'graveyard',pid='p2')
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Sorcerous Squall',targets=['p2'])
    d=s.state.rules.decision
    assert [o.id for o in d.options if o.card_id==spell.id]==[spell.id+'@1']
    answer(s,[spell.id+'@1'])
    answer(s,[bear.id])
    assert s.state.cards[spell.id].zone=='p2:exile'
    roundtrip(s)


def test_squall_actual_optional_decline_has_no_later_graveyard_permission(cards):
    from app.game.errors import ActionError
    s=setup(cards,'Sorcerous Squall')
    spell=put(s,'Divination','graveyard',pid='p2')
    cast(s,'Sorcerous Squall',targets=['p2'])
    answer(s,[])
    assert s.state.cards[spell.id].zone=='p2:graveyard'
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,free=True)
    assert not s.state.rules.permissions and s.state.rules.free_cast_then is None
    roundtrip(s)


def test_squall_actual_newly_milled_spell_is_available_from_current_target_graveyard(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards,'Sorcerous Squall')
    spell=stack_library(s,['Divination'],pid='p2')[0]
    cast(s,'Sorcerous Squall',targets=['p2'])
    assert s.state.cards[spell].zone=='p2:graveyard'
    assert spell in [o.card_id for o in s.state.rules.decision.options]
    answer(s,[spell])
    assert s.state.cards[spell].zone=='p2:exile'
    roundtrip(s)


def test_squall_actual_illegal_opponent_target_does_not_mill_other_opponent(cards):
    s=setup(cards,'Sorcerous Squall')
    source=put(s,'Sorcerous Squall','hand')
    before=len(s.state.zones['p3:library'])
    mana(s,U=3,C=6)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'])
    act(s,'p2',type='concede')
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert len(s.state.zones['p3:library'])==before
    assert s.state.rules.decision is None
    roundtrip(s)


def test_squall_actual_generic_tax_increase_can_be_paid_by_seventh_delve_card(cards):
    s=setup(cards,'Sorcerous Squall','Murder','Thalia, Guardian of Thraben')
    put(s,'Thalia, Guardian of Thraben','battlefield')
    fuel=[*squall_fuel(s),put(s,'Murder','graveyard')]
    put(s,'Divination','graveyard',pid='p2')
    source=put(s,'Sorcerous Squall','hand')
    mana(s,U=3)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'],contributions=[{'kind':'delve','card':c.id} for c in fuel])
    assert all(s.state.cards[c.id].zone=='p1:exile' for c in fuel)
    assert not any(s.state.players['p1'].mana.values())
    settle(s)
    answer(s,[])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_talent_actual_first_spell_additional_discard_cannot_retroactively_enable_mastery(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Talent of the Telepath','Cathartic Reunion','Murder','Earthquake')
    packet=stack_library(s,['Cathartic Reunion','Divination','Grizzly Bears'],pid='p2')
    murder=put(s,'Murder','hand')
    quake=put(s,'Earthquake','hand')
    cast(s,'Talent of the Telepath',targets=['p2'])
    answer(s,[packet[0]])
    assert s.state.rules.decision.resume["step"]=="ability_cost"
    answer(s,[murder.id,quake.id])
    assert s.state.rules.decision is None
    assert s.state.cards[murder.id].zone=='p1:graveyard'
    assert s.state.cards[quake.id].zone=='p1:graveyard'
    assert s.state.cards[packet[1]].zone=='p2:graveyard'
    assert s.state.cards[packet[0]].zone=='p2:graveyard'
    roundtrip(s)


def test_talent_actual_one_graveyard_spell_does_not_count_resolving_talent_as_second(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Talent of the Telepath','Murder')
    put(s,'Murder','graveyard')
    packet=stack_library(s,['Divination','Giant Growth','Grizzly Bears'],pid='p2')
    cast(s,'Talent of the Telepath',targets=['p2'])
    answer(s,[packet[0]])
    assert s.state.rules.decision is None
    assert s.state.cards[packet[1]].zone=='p2:graveyard'
    roundtrip(s)


def test_talent_actual_decline_puts_entire_revealed_packet_into_graveyard_without_future_permission(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Talent of the Telepath','Murder','Earthquake')
    put(s,'Murder','graveyard')
    put(s,'Earthquake','graveyard')
    packet=stack_library(s,['Divination','Giant Growth','Grizzly Bears'],pid='p2')
    old=list(s.state.zones['p2:library'])
    cast(s,'Talent of the Telepath',targets=['p2'])
    answer(s,[])
    assert len(set(old)&set(s.state.zones['p2:graveyard']))==7
    assert all(s.state.cards[cid].zone=='p2:graveyard' for cid in packet)
    assert not s.state.rules.permissions and s.state.rules.free_cast_then is None
    roundtrip(s)


def test_talent_actual_remaining_revealed_cards_use_native_graveyard_replacement(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Talent of the Telepath','Rest in Peace')
    put(s,'Rest in Peace','battlefield')
    packet=stack_library(s,['Divination','Giant Growth','Grizzly Bears'],pid='p2')
    old=list(s.state.zones['p2:library'])
    cast(s,'Talent of the Telepath',targets=['p2'])
    answer(s,[])
    assert len(set(old)&set(s.state.zones['p2:exile']))==7
    assert all(s.state.cards[cid].zone=='p2:exile' for cid in packet)
    roundtrip(s)


def test_talent_actual_short_library_reveals_only_available_cards_and_empty_has_no_offer(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Talent of the Telepath')
    packet=stack_library(s,['Divination','Grizzly Bears'],pid='p2')
    for cid in list(s.state.zones['p2:library']):
        if cid not in packet:
            act(s,'p1',type='move',card_ids=[cid],to={'player':'p2','zone':'exile'})
    cast(s,'Talent of the Telepath',targets=['p2'])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[])
    assert not s.state.zones['p2:library']
    assert all(s.state.cards[cid].zone=='p2:graveyard' for cid in packet)
    source=put(s,'Talent of the Telepath','hand')
    cast(s,source.name,targets=['p2'])
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('finished',[False,True])
def test_talent_actual_public_seven_rest_and_websocket_do_not_expose_eighth_card(cards,settings,finished):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Talent of the Telepath')
    packet=stack_library(s,['Divination','Giant Growth','Grizzly Bears'],pid='p2')
    cast(s,'Talent of the Telepath',targets=['p2'])
    library=list(s.state.zones['p2:library'])
    shown={cid for cid in library if s.state.cards[cid].revealed_to}
    assert len(shown)==7 and packet[0] in shown
    hidden=next(cid for cid in library if cid not in shown)
    if finished:
        answer(s,[])
    with TestClient(create_app(settings)) as client:
        room=client.app.state.services.hub.create_room(s,mode='lan')
        for player,seat in room.seats.items():
            seat.token='talent46-'+player
        room.spectator_tokens.add('talent46-spectator')
        for viewer in ['p1','p2','p3','spectator']:
            token='talent46-'+viewer
            payload=client.get(f'/api/games/{room.id}/view',headers={'X-Seat-Token':token}).json()
            with client.websocket_connect(f'/ws/games/{room.id}?token={token}') as ws:
                frame=ws.receive_json()
            for view in [payload,frame['view']]:
                assert all('name' in view['cards'].get(cid,{}) for cid in shown)
                assert 'name' not in view['cards'].get(hidden,{})
    roundtrip(s)


def test_talent_actual_mastery_is_checked_at_resolution_after_response_spell_enters_graveyard(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Talent of the Telepath','Murder','Opt')
    put(s,'Murder','graveyard')
    packet=stack_library(s,['Divination','Giant Growth','Grizzly Bears'],pid='p2')
    bear=put(s,'Grizzly Bears','battlefield')
    source=put(s,'Talent of the Telepath','hand')
    mana(s,U=2,C=2)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'])
    cast(s,'Opt')
    if s.state.rules.decision is not None and 'scry' in s.state.rules.decision.prompt.lower():
        answer(s,[])
    settle(s)
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[packet[0]])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    answer(s,[packet[1]])
    if s.state.rules.decision is not None:
        answer(s,[bear.id])
    assert all(s.state.cards[cid].zone=='p2:graveyard' for cid in packet)
    roundtrip(s)


def combat_optional_offer(s,source,*,stop_trigger=False):
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    for _ in range(60):
        if stop_trigger and any(e.kind=='trigger' and e.source_card==source.id for e in s.state.rules.stack.values()):
            return None
        if s.state.rules.permissions:
            return None
        d=s.state.rules.decision
        if d is not None:
            if d.kind=='declare_blockers':
                act(s,d.player,type='declare_blockers',blocks=[])
                continue
            return d
        act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('Combat never reached optional resolution payment')


@pytest.mark.parametrize('pay',[False,True])
def test_widow_actual_combat_prefix_optional_counter_cost_or_paid_exile_cast(cards,pay):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Black Widow, Super Spy','Forest')
    source=put(s,'Black Widow, Super Spy','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Forest','Divination','Grizzly Bears'],pid='p2')
    combat_optional_offer(s,source)
    assert s.state.cards[packet[0]].zone=='p2:exile'
    assert s.state.cards[packet[1]].zone=='p2:exile'
    assert s.state.cards[packet[2]].zone=='p2:library'
    answer(s,['pay' if pay else 'decline'])
    assert s.state.cards[source.id].counters.get('+1/+1',0)==int(pay)
    if pay:
        assert not s.state.rules.permissions
    else:
        assert s.state.rules.permissions
        to_phase(s,'main2',turn=4)
        mana(s,G=3)
        act(s,'p1',type='cast_spell',card_id=packet[1])
        settle(s)
        assert s.state.cards[packet[1]].zone=='p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('replacement',['Solemnity','Vorinclex, Monstrous Raider'])
def test_widow_actual_forbidden_counter_differs_from_chosen_counter_replaced_to_zero(cards,replacement):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Black Widow, Super Spy',replacement)
    source=put(s,'Black Widow, Super Spy','battlefield')
    put(s,replacement,'battlefield',pid='p2')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Divination','Grizzly Bears'],pid='p2')
    d=combat_optional_offer(s,source)
    if replacement=='Solemnity':
        assert d is None or 'pay' not in [o.id for o in d.options]
        if d is not None:
            answer(s,['decline'])
        assert s.state.rules.permissions
    else:
        assert 'pay' in [o.id for o in d.options]
        answer(s,['pay'])
        assert not s.state.rules.permissions
    assert s.state.cards[source.id].counters.get('+1/+1',0)==0
    assert s.state.cards[packet[0]].zone=='p2:exile'
    roundtrip(s)


@pytest.mark.parametrize('change',['blink','control'])
def test_widow_actual_source_counter_cost_requires_original_object_but_not_control(cards,change):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Black Widow, Super Spy')
    source=put(s,'Black Widow, Super Spy','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    stack_library(s,['Divination','Grizzly Bears'],pid='p2')
    combat_optional_offer(s,source)
    if change=='blink':
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'exile'})
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'battlefield'})
        answer(s,['pay'])
        assert s.state.rules.permissions
        assert s.state.cards[source.id].counters.get('+1/+1',0)==0
    else:
        act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
        answer(s,['pay'])
        assert s.state.cards[source.id].counters.get('+1/+1',0)==1
        assert not s.state.rules.permissions
    roundtrip(s)


def test_widow_actual_any_type_permission_pays_real_colorless_requirement_with_green(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Black Widow, Super Spy','Matter Reshaper')
    source=put(s,'Black Widow, Super Spy','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Matter Reshaper','Grizzly Bears'],pid='p2')
    combat_optional_offer(s,source)
    answer(s,['decline'])
    to_phase(s,'main2',turn=4)
    mana(s,G=3)
    act(s,'p1',type='cast_spell',card_id=packet[0])
    settle(s)
    assert s.state.cards[packet[0]].zone=='p1:battlefield'
    assert s.state.cards[packet[0]].owner=='p2'
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_widow_actual_source_dies_in_response_then_exiled_nonland_remains_castable(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Black Widow, Super Spy','Murder')
    source=put(s,'Black Widow, Super Spy','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Divination','Grizzly Bears'],pid='p2')
    combat_optional_offer(s,source,stop_trigger=True)
    cast(s,'Murder',targets=[source.id])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[packet[0]].zone=='p2:exile'
    assert s.state.rules.decision is None and s.state.rules.permissions
    to_phase(s,'main2',turn=4)
    mana(s,G=3)
    act(s,'p1',type='cast_spell',card_id=packet[0])
    settle(s)
    assert s.state.cards[packet[0]].zone=='p2:graveyard'
    roundtrip(s)


def test_widow_actual_permission_expires_at_end_of_turn_and_cannot_cast_exiled_lands(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Black Widow, Super Spy','Forest')
    source=put(s,'Black Widow, Super Spy','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Forest','Divination','Grizzly Bears'],pid='p2')
    combat_optional_offer(s,source)
    answer(s,['decline'])
    to_phase(s,'main2',turn=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='play_land',card_id=packet[0])
    to_phase(s,'main1',turn=7)
    mana(s,U=1,C=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=packet[1])
    assert s.state.cards[packet[1]].zone=='p2:exile'
    roundtrip(s)


def test_widow_actual_printed_menace_forbids_single_blocker_and_accepts_two(cards):
    from app.game.errors import ActionError

    s=setup(cards,'Black Widow, Super Spy')
    source=put(s,'Black Widow, Super Spy','battlefield')
    first=put(s,'Grizzly Bears','battlefield',pid='p2')
    second=put(s,'Rivaz of the Claw','battlefield',pid='p2')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    to_phase(s,'declare_blockers',turn=4)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':first.id,'attacker_id':source.id}])
    act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':c.id,'attacker_id':source.id} for c in (first,second)])
    roundtrip(s)


def test_widow_actual_all_land_prefix_exiles_entire_library_and_still_offers_counter(cards):
    s=setup(cards,'Black Widow, Super Spy','Forest')
    source=put(s,'Black Widow, Super Spy','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    library=list(s.state.zones['p2:library'])
    for cid in library:
        if s.state.cards[cid].name!='Forest':
            act(s,'p1',type='move',card_ids=[cid],to={'player':'p2','zone':'exile'})
    forest=put(s,'Forest','library',pid='p2')
    d=combat_optional_offer(s,source)
    assert d is not None and 'pay' in [o.id for o in d.options]
    assert not s.state.zones['p2:library']
    assert s.state.cards[forest.id].zone=='p2:exile'
    answer(s,['pay'])
    assert s.state.cards[source.id].counters.get('+1/+1',0)==1
    assert not s.state.rules.permissions
    roundtrip(s)


def test_widow_actual_foreign_exile_cast_pays_normal_additional_discard_cost(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Black Widow, Super Spy','Cathartic Reunion','Murder','Earthquake')
    source=put(s,'Black Widow, Super Spy','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Cathartic Reunion','Grizzly Bears'],pid='p2')
    combat_optional_offer(s,source)
    answer(s,['decline'])
    to_phase(s,'main2',turn=4)
    murder=put(s,'Murder','hand')
    quake=put(s,'Earthquake','hand')
    mana(s,G=2)
    act(s,'p1',type='cast_spell',card_id=packet[0])
    assert s.state.rules.decision.resume['step']=='ability_cost'
    answer(s,[murder.id,quake.id])
    assert s.state.cards[packet[0]].zone=='p2:graveyard'
    assert all(s.state.cards[c.id].zone=='p1:graveyard' for c in (murder,quake))
    roundtrip(s)


@pytest.mark.parametrize('pay',[False,True])
def test_reno_actual_combat_exile_then_another_artifact_sacrifice_gates_normal_paid_cast(cards,pay):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Reno and Rude')
    source=put(s,'Reno and Rude','battlefield')
    altar=put(s,"Ashnod's Altar",'battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Divination','Grizzly Bears'],pid='p2')
    d=combat_optional_offer(s,source)
    ids=[o.id for o in d.options]
    if 'pay' in ids:
        answer(s,['pay' if pay else 'decline'])
        if pay and s.state.rules.decision is not None:
            answer(s,[altar.id])
    else:
        assert altar.id in ids and source.id not in ids
        answer(s,[altar.id] if pay else [])
    assert s.state.cards[packet[0]].zone=='p2:exile'
    if pay:
        assert s.state.cards[altar.id].zone=='p1:graveyard'
        to_phase(s,'main2',turn=4)
        mana(s,G=3)
        act(s,'p1',type='cast_spell',card_id=packet[0])
        settle(s)
        assert s.state.cards[packet[0]].zone=='p2:graveyard'
    else:
        assert not s.state.rules.permissions
        assert s.state.cards[altar.id].zone=='p1:battlefield'
    roundtrip(s)


def test_reno_actual_sacrifice_replacement_still_pays_resolution_cost_and_allows_land_play(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Reno and Rude','Forest','Rest in Peace','Angel of Jubilation')
    source=put(s,'Reno and Rude','battlefield')
    altar=put(s,"Ashnod's Altar",'battlefield')
    put(s,'Rest in Peace','battlefield')
    put(s,'Angel of Jubilation','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Forest','Divination'],pid='p2')
    d=combat_optional_offer(s,source)
    if 'pay' in [o.id for o in d.options]:
        answer(s,['pay'])
    if s.state.rules.decision is not None:
        answer(s,[altar.id])
    assert s.state.cards[altar.id].zone=='p1:exile'
    to_phase(s,'main2',turn=4)
    act(s,'p1',type='play_land',card_id=packet[0])
    assert s.state.cards[packet[0]].zone=='p1:battlefield'
    assert s.state.cards[packet[0]].owner=='p2'
    roundtrip(s)


def test_reno_actual_source_blink_new_incarnation_is_another_creature_for_old_trigger_cost(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Reno and Rude','Flicker of Fate')
    source=put(s,'Reno and Rude','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Divination','Grizzly Bears'],pid='p2')
    original=s.state.rules.object_id(source.id)
    combat_optional_offer(s,source,stop_trigger=True)
    cast(s,'Flicker of Fate',targets=[source.id])
    assert s.state.rules.object_id(source.id)!=original
    d=s.state.rules.decision
    if 'pay' in [o.id for o in d.options]:
        answer(s,['pay'])
    if s.state.rules.decision is not None:
        assert source.id in [o.id for o in s.state.rules.decision.options]
        answer(s,[source.id])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[packet[0]].zone=='p2:exile'
    assert s.state.rules.permissions
    roundtrip(s)


def test_reno_actual_countered_combat_trigger_exiles_nothing_and_offers_no_sacrifice(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Reno and Rude','Stifle')
    source=put(s,'Reno and Rude','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Divination','Grizzly Bears'],pid='p2')
    combat_optional_offer(s,source,stop_trigger=True)
    trigger=next(k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_card==source.id)
    cast(s,'Stifle',targets=[trigger])
    assert s.state.cards[packet[0]].zone=='p2:library'
    assert s.state.rules.decision is None and not s.state.rules.permissions
    roundtrip(s)


def test_reno_actual_play_permission_uses_normal_land_limit_and_expires(cards):
    from app.game.errors import ActionError
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Reno and Rude','Forest')
    source=put(s,'Reno and Rude','battlefield')
    altar=put(s,"Ashnod's Altar",'battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Forest','Divination'],pid='p2')
    d=combat_optional_offer(s,source)
    if 'pay' in [o.id for o in d.options]:
        answer(s,['pay'])
    if s.state.rules.decision is not None:
        answer(s,[altar.id])
    to_phase(s,'main2',turn=4)
    own=put(s,'Forest','hand')
    act(s,'p1',type='play_land',card_id=own.id)
    with pytest.raises(ActionError):
        act(s,'p1',type='play_land',card_id=packet[0])
    to_phase(s,'main1',turn=7)
    with pytest.raises(ActionError):
        act(s,'p1',type='play_land',card_id=packet[0])
    assert s.state.cards[packet[0]].zone=='p2:exile'
    roundtrip(s)


def test_reno_actual_source_dies_before_resolution_sacrifice_still_grants_paid_colorless_spell(cards):
    from tests.test_rules_refused_look import stack_library

    s=setup(cards,'Reno and Rude','Murder','Matter Reshaper')
    source=put(s,'Reno and Rude','battlefield')
    altar=put(s,"Ashnod's Altar",'battlefield')
    to_phase(s,'declare_attackers',turn=4)
    packet=stack_library(s,['Matter Reshaper','Grizzly Bears'],pid='p2')
    combat_optional_offer(s,source,stop_trigger=True)
    cast(s,'Murder',targets=[source.id])
    d=s.state.rules.decision
    if 'pay' in [o.id for o in d.options]:
        answer(s,['pay'])
    if s.state.rules.decision is not None:
        answer(s,[altar.id])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[altar.id].zone=='p1:graveyard'
    to_phase(s,'main2',turn=4)
    act(s,'p1',type='clear_mana',player='p1')
    mana(s,G=3)
    act(s,'p1',type='cast_spell',card_id=packet[0])
    settle(s)
    assert s.state.cards[packet[0]].zone=='p1:battlefield'
    assert s.state.cards[packet[0]].owner=='p2'
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_reno_actual_printed_menace_forbids_single_blocker_and_accepts_two(cards):
    from app.game.errors import ActionError

    s=setup(cards,'Reno and Rude')
    source=put(s,'Reno and Rude','battlefield')
    first=put(s,'Grizzly Bears','battlefield',pid='p2')
    second=put(s,'Rivaz of the Claw','battlefield',pid='p2')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    to_phase(s,'declare_blockers',turn=4)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':first.id,'attacker_id':source.id}])
    act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':c.id,'attacker_id':source.id} for c in (first,second)])
    roundtrip(s)


def test_reno_actual_empty_library_still_allows_optional_sacrifice_without_minting_permission(cards):
    s=setup(cards,'Reno and Rude')
    source=put(s,'Reno and Rude','battlefield')
    altar=put(s,"Ashnod's Altar",'battlefield')
    to_phase(s,'declare_attackers',turn=4)
    library=list(s.state.zones['p2:library'])
    act(s,'p1',type='move',card_ids=library,to={'player':'p2','zone':'exile'})
    d=combat_optional_offer(s,source)
    if 'pay' in [o.id for o in d.options]:
        answer(s,['pay'])
    if s.state.rules.decision is not None:
        answer(s,[altar.id])
    assert s.state.cards[altar.id].zone=='p1:graveyard'
    assert not s.state.rules.permissions
    roundtrip(s)


def test_reno_whole_canonical_staged(cards):
    test_staged_all_printed_lines_compile_without_fallback(cards,'Reno and Rude')


@pytest.mark.parametrize('choose_first',[False,True])
def test_diluvian_actual_target_card_types_opponent_groups_and_up_to_zero(cards,choose_first):
    s=setup(cards,'Diluvian Primordial','Two-Handed Axe // Sweeping Cleave')
    own=put(s,'Divination','graveyard')
    first=put(s,'Divination','graveyard',pid='p2')
    adventure=put(s,'Two-Handed Axe // Sweeping Cleave','graveyard',pid='p2')
    second=put(s,'Giant Growth','graveyard',pid='p3')
    cast(s,'Diluvian Primordial')
    ids=[o.id for o in s.state.rules.decision.options]
    assert first.id in ids and all(c.id not in ids for c in (own,adventure,second))
    answer(s,[first.id] if choose_first else [])
    assert second.id in [o.id for o in s.state.rules.decision.options]
    answer(s,[])
    if choose_first:
        assert s.state.rules.decision.resume['step']=='free_cast_pick'
        answer(s,[first.id])
    assert s.state.cards[first.id].zone==('p2:exile' if choose_first else 'p2:graveyard')
    assert s.state.cards[second.id].zone=='p3:graveyard'
    assert s.state.cards[own.id].zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('response',['Stifle','Cremate','Murder'])
def test_diluvian_actual_announced_targets_response_recheck_and_source_departure(cards,response):
    s=setup(cards,'Diluvian Primordial',response)
    first=put(s,'Divination','graveyard',pid='p2')
    second=put(s,'Giant Growth','graveyard',pid='p3')
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Diluvian Primordial')
    source=next(c for c in s.state.cards.values() if c.name=='Diluvian Primordial' and c.zone=='p1:battlefield')
    answer(s,[first.id])
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[second.id])
    trigger=next(k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_card==source.id)
    cast(s,response,targets=[trigger if response=='Stifle' else first.id if response=='Cremate' else source.id])
    if response=='Stifle':
        assert s.state.rules.decision is None
        assert s.state.cards[first.id].zone=='p2:graveyard'
        assert s.state.cards[second.id].zone=='p3:graveyard'
    else:
        if response=='Murder':
            assert s.state.cards[source.id].zone=='p1:graveyard'
            answer(s,[first.id])
        assert s.state.rules.decision.resume['step']=='free_cast_pick'
        assert second.id in [o.id for o in s.state.rules.decision.options]
        answer(s,[second.id])
        if s.state.rules.decision is not None:
            answer(s,[bear.id])
        assert s.state.cards[first.id].zone=='p2:exile'
        assert s.state.cards[second.id].zone=='p3:exile'
    roundtrip(s)


@pytest.mark.parametrize('counter',['Counterspell','Memory Lapse'])
def test_diluvian_actual_cast_spell_countered_exiles_only_if_actual_destination_is_graveyard(cards,counter):
    s=setup(cards,'Diluvian Primordial',counter)
    spell=put(s,'Divination','graveyard',pid='p2')
    put(s,'Giant Growth','graveyard',pid='p3')
    cast(s,'Diluvian Primordial')
    answer(s,[spell.id])
    answer(s,[])
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[spell.id])
    assert s.state.cards[spell.id].zone=='stack'
    cast(s,counter,targets=[spell.id])
    assert s.state.cards[spell.id].zone==('p2:exile' if counter=='Counterspell' else 'p2:library')
    roundtrip(s)


def test_diluvian_actual_foreign_x_spell_uses_zero_and_mandatory_discard_is_paid_by_caster(cards):
    s=setup(cards,'Diluvian Primordial','Earthquake','Cathartic Reunion','Murder')
    first=put(s,'Earthquake','graveyard',pid='p2')
    second=put(s,'Cathartic Reunion','graveyard',pid='p3')
    murder=put(s,'Murder','hand')
    spare=put(s,'Grizzly Bears','hand')
    before={p:s.state.players[p].life for p in ('p1','p2','p3')}
    cast(s,'Diluvian Primordial')
    answer(s,[first.id])
    answer(s,[second.id])
    answer(s,[first.id])
    answer(s,[second.id])
    if s.state.rules.decision is not None:
        assert s.state.rules.decision.resume['step']=='ability_cost'
        answer(s,[murder.id,spare.id])
    assert all(s.state.players[p].life==n for p,n in before.items())
    assert all(s.state.cards[c.id].zone=='p1:graveyard' for c in (murder,spare))
    assert s.state.cards[first.id].zone=='p2:exile'
    assert s.state.cards[second.id].zone=='p3:exile'
    roundtrip(s)


@pytest.mark.parametrize('pay',[False,True])
def test_diluvian_actual_free_spell_still_pays_cost_increase_or_cancellation_leaves_card_in_graveyard(cards,pay):
    s=setup(cards,'Diluvian Primordial','Thalia, Guardian of Thraben')
    put(s,'Thalia, Guardian of Thraben','battlefield')
    spell=put(s,'Divination','graveyard',pid='p2')
    put(s,'Giant Growth','graveyard',pid='p3')
    cast(s,'Diluvian Primordial')
    answer(s,[spell.id])
    answer(s,[])
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[spell.id])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    if pay:
        mana(s,C=1)
    answer(s,['pay' if pay else 'cancel'])
    assert s.state.cards[spell.id].zone==('p2:exile' if pay else 'p2:graveyard')
    assert s.state.rules.free_cast_then is None and not s.state.rules.permissions
    roundtrip(s)


def test_diluvian_actual_printed_flying_forbids_ground_blocker_and_accepts_flying_blocker(cards):
    from app.game.errors import ActionError

    s=setup(cards,'Diluvian Primordial','Serra Angel')
    source=put(s,'Diluvian Primordial','battlefield')
    ground=put(s,'Grizzly Bears','battlefield',pid='p2')
    flyer=put(s,'Serra Angel','battlefield',pid='p2')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    to_phase(s,'declare_blockers',turn=4)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':ground.id,'attacker_id':source.id}])
    act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':flyer.id,'attacker_id':source.id}])
    roundtrip(s)


def test_diluvian_actual_targeted_uncastable_counterspell_stays_in_graveyard_and_can_decline_legal_spell(cards):
    s=setup(cards,'Diluvian Primordial','Counterspell')
    counter=put(s,'Counterspell','graveyard',pid='p2')
    second=put(s,'Giant Growth','graveyard',pid='p3')
    cast(s,'Diluvian Primordial')
    answer(s,[counter.id])
    answer(s,[second.id])
    d=s.state.rules.decision
    if d is not None and d.resume.get('step')=='free_cast_pick' and second.id not in [o.id for o in d.options]:
        assert counter.id not in [o.id for o in d.options]
        answer(s,[])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert second.id in [o.id for o in s.state.rules.decision.options]
    answer(s,[])
    assert s.state.cards[counter.id].zone=='p2:graveyard'
    assert s.state.cards[second.id].zone=='p3:graveyard'
    assert s.state.rules.free_cast_then is None and not s.state.rules.permissions
    roundtrip(s)


def test_jetsam_actual_all_opponents_mill_before_any_cast_then_one_preexisting_spell_from_each_graveyard(cards):
    from tests.test_rules_refused_look import stack_library

    name='Flotsam // Jetsam'
    s=setup(cards,name,'Disenchant')
    first=put(s,"Ashnod's Altar",'graveyard',pid='p2')
    second=put(s,'Divination','graveyard',pid='p3')
    top2=stack_library(s,['Grizzly Bears','Giant Growth','Rivaz of the Claw'],pid='p2')
    top3=stack_library(s,['Grizzly Bears','Giant Growth','Rivaz of the Claw'],pid='p3')
    source=put(s,name,'hand')
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    settle(s)
    assert all(s.state.cards[cid].zone==f'{pid}:graveyard' for pid,packet in [('p2',top2),('p3',top3)] for cid in packet)
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert first.id in [o.id for o in s.state.rules.decision.options]
    assert second.id not in [o.id for o in s.state.rules.decision.options]
    answer(s,[first.id])
    assert s.state.cards[first.id].zone=='stack'
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert second.id in [o.id for o in s.state.rules.decision.options]
    assert all(o.card_id!=first.id for o in s.state.rules.decision.options)
    answer(s,[second.id])
    assert s.state.cards[first.id].zone=='p1:battlefield'
    assert s.state.cards[first.id].owner=='p2'
    assert s.state.cards[second.id].zone=='p3:exile'
    cast(s,'Disenchant',targets=[first.id])
    assert s.state.cards[first.id].zone=='p2:graveyard'
    roundtrip(s)


def test_flotsam_actual_paid_front_mills_three_then_creates_real_clue_with_paid_sacrifice_draw(cards):
    s=setup(cards,'Flotsam // Jetsam')
    source=put(s,'Flotsam // Jetsam','hand')
    library=list(s.state.zones['p1:library'])
    mana(s,G=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id,face=0)
    settle(s)
    assert len(set(library)&set(s.state.zones['p1:graveyard']))==3
    clue=next(c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield' and c.name=='Clue')
    before=len(s.state.zones['p1:hand'])
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=clue.id,ability=0)
    settle(s)
    assert clue.id not in s.state.cards or s.state.cards[clue.id].zone!='p1:battlefield'
    assert len(s.state.zones['p1:hand'])==before+1
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_flotsam_jetsam_whole_canonical_staged(cards):
    test_staged_all_printed_lines_compile_without_fallback(cards,'Flotsam // Jetsam')


@pytest.mark.parametrize('face',[0,1])
def test_flotsam_jetsam_actual_cast_half_characteristics_and_cannot_fuse(cards,face):
    from app.game.errors import ActionError
    from app.rules import stack_interaction
    from app.rules.plan import Plan

    s=setup(cards,'Flotsam // Jetsam')
    source=put(s,'Flotsam // Jetsam','hand')
    plan=Plan(s.state,'p1',cards,None)
    assert stack_interaction.mana_value(source,plan.ch(source))==8
    mana(s,U=4,G=1,C=8)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,fuse=True)
    act(s,'p1',type='cast_spell',card_id=source.id,face=face)
    actual=s.state.cards[source.id]
    ch=Plan(s.state,'p1',cards,None).ch(actual)
    assert ('Instant' in ch.types)==(face==0)
    assert ('Sorcery' in ch.types)==(face==1)
    assert stack_interaction.mana_value(actual,ch)==(2 if face==0 else 6)
    roundtrip(s)


@pytest.mark.parametrize('face',[0,1])
def test_flotsam_jetsam_actual_mill_replacement_to_exile_preserves_front_investigate_and_no_back_gy_offer(cards,face):
    s=setup(cards,'Flotsam // Jetsam','Rest in Peace')
    put(s,'Rest in Peace','battlefield')
    source=put(s,'Flotsam // Jetsam','hand')
    before={p:set(s.state.zones[p+':exile']) for p in ('p1','p2','p3')}
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id,face=face)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone=='p1:exile'
    if face==0:
        assert len(set(s.state.zones['p1:exile'])-before['p1'])==4
        assert any(c.is_token and c.name=='Clue' and c.zone=='p1:battlefield' for c in s.state.cards.values())
    else:
        assert all(len(set(s.state.zones[p+':exile'])-before[p])==3 for p in ('p2','p3'))
        assert s.state.rules.free_cast_then is None and not s.state.rules.permissions
    roundtrip(s)


def test_jetsam_actual_each_graveyard_chosen_spell_face_can_be_permanent_or_adventure_instant(cards):
    s=setup(cards,'Flotsam // Jetsam','Cosima, God of the Voyage // The Omenkeel','Two-Handed Axe // Sweeping Cleave')
    first=put(s,'Cosima, God of the Voyage // The Omenkeel','graveyard',pid='p2')
    second=put(s,'Two-Handed Axe // Sweeping Cleave','graveyard',pid='p3')
    bear=put(s,'Grizzly Bears','battlefield')
    source=put(s,'Flotsam // Jetsam','hand')
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    settle(s)
    assert all(first.id+suffix in [o.id for o in s.state.rules.decision.options] for suffix in ('@0','@1'))
    answer(s,[first.id+'@1'])
    assert all(second.id+suffix in [o.id for o in s.state.rules.decision.options] for suffix in ('@0','@1'))
    answer(s,[second.id+'@1'])
    if s.state.rules.decision is not None:
        answer(s,[bear.id])
    assert s.state.cards[first.id].zone=='p1:battlefield'
    assert s.state.cards[first.id].face==1
    assert s.state.cards[second.id].zone=='p3:exile'
    roundtrip(s)


def test_jetsam_actual_first_cast_additional_cost_can_supply_next_opponents_current_graveyard(cards):
    s=setup(cards,'Flotsam // Jetsam','Shrapnel Blast')
    first=put(s,'Shrapnel Blast','graveyard',pid='p2')
    altar=put(s,"Ashnod's Altar",'battlefield',pid='p3')
    act(s,'p1',type='set_controller',card_ids=[altar.id],player='p1')
    source=put(s,'Flotsam // Jetsam','hand')
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    settle(s)
    answer(s,[first.id])
    if s.state.rules.decision is not None and s.state.rules.decision.resume['step']!='free_cast_pick':
        assert 'p3' in [o.id for o in s.state.rules.decision.options]
        answer(s,['p3'])
    if s.state.rules.decision is not None and s.state.rules.decision.resume['step']=='ability_cost':
        answer(s,[altar.id])
    assert s.state.cards[altar.id].zone=='p3:graveyard'
    assert s.state.cards[first.id].zone=='stack'
    assert s.state.players['p3'].life==40
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert altar.id in [o.id for o in s.state.rules.decision.options]
    answer(s,[altar.id])
    assert s.state.cards[altar.id].zone=='p1:battlefield'
    assert s.state.cards[first.id].zone=='p2:exile'
    assert s.state.players['p3'].life==35
    roundtrip(s)


@pytest.mark.parametrize('counter',['Counterspell','Memory Lapse'])
def test_jetsam_actual_free_spell_counter_uses_exact_stack_departure_destination(cards,counter):
    s=setup(cards,'Flotsam // Jetsam',counter)
    first=put(s,'Divination','graveyard',pid='p2')
    put(s,'Giant Growth','graveyard',pid='p3')
    source=put(s,'Flotsam // Jetsam','hand')
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    settle(s)
    answer(s,[first.id])
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    assert s.state.cards[first.id].zone=='stack'
    cast(s,counter,targets=[first.id])
    assert s.state.cards[first.id].zone==('p2:exile' if counter=='Counterspell' else 'p2:library')
    roundtrip(s)


def test_jetsam_actual_countering_source_prevents_all_mill_and_cast_choices(cards):
    s=setup(cards,'Flotsam // Jetsam','Counterspell')
    before={p:list(s.state.zones[p+':library']) for p in ('p2','p3')}
    source=put(s,'Flotsam // Jetsam','hand')
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    cast(s,'Counterspell',targets=[source.id])
    assert all(s.state.zones[p+':library']==ids for p,ids in before.items())
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    roundtrip(s)


def test_jetsam_actual_free_off_turn_cast_uses_active_player_opponent_graveyard_first(cards):
    s=setup(cards,'Flotsam // Jetsam','Mindclaw Shaman','Flicker of Fate')
    host=put(s,'Mindclaw Shaman','battlefield')
    to_phase(s,'main1',turn=3)
    source=put(s,'Flotsam // Jetsam','hand',pid='p3')
    first=put(s,'Divination','graveyard',pid='p3')
    second=put(s,"Ashnod's Altar",'graveyard',pid='p2')
    for _ in range(3):
        if s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    cast(s,'Flicker of Fate',targets=[host.id])
    answer(s,['p3'])
    answer(s,[source.id+'@1'])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert first.id in [o.id for o in s.state.rules.decision.options]
    assert second.id not in [o.id for o in s.state.rules.decision.options]
    answer(s,[first.id])
    assert s.state.cards[first.id].zone=='stack'
    assert second.id in [o.id for o in s.state.rules.decision.options]
    answer(s,[second.id])
    assert s.state.cards[first.id].zone=='p3:exile'
    assert s.state.cards[second.id].zone=='p1:battlefield'
    assert s.state.cards[source.id].zone=='p3:graveyard'
    roundtrip(s)


def test_jetsam_actual_optional_decline_keeps_all_graveyard_cards_without_later_permission(cards):
    s=setup(cards,'Flotsam // Jetsam','Forest')
    put(s,'Grizzly Bears','battlefield')
    first=put(s,'Divination','graveyard',pid='p2')
    land=put(s,'Forest','graveyard',pid='p2')
    second=put(s,'Giant Growth','graveyard',pid='p3')
    own=put(s,"Ashnod's Altar",'graveyard')
    source=put(s,'Flotsam // Jetsam','hand')
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    settle(s)
    ids=[o.card_id for o in s.state.rules.decision.options]
    assert first.id in ids and land.id not in ids and own.id not in ids and second.id not in ids
    answer(s,[])
    assert second.id in [o.card_id for o in s.state.rules.decision.options]
    answer(s,[])
    assert s.state.cards[first.id].zone=='p2:graveyard'
    assert s.state.cards[second.id].zone=='p3:graveyard'
    assert s.state.rules.free_cast_then is None and not s.state.rules.permissions
    roundtrip(s)


def test_jetsam_actual_x_zero_and_mandatory_additional_discard_are_native_cast_costs(cards):
    s=setup(cards,'Flotsam // Jetsam','Earthquake','Cathartic Reunion','Murder')
    first=put(s,'Earthquake','graveyard',pid='p2')
    second=put(s,'Cathartic Reunion','graveyard',pid='p3')
    murder=put(s,'Murder','hand')
    bear=put(s,'Grizzly Bears','hand')
    before={p:s.state.players[p].life for p in ('p1','p2','p3')}
    source=put(s,'Flotsam // Jetsam','hand')
    mana(s,U=2,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    settle(s)
    answer(s,[first.id])
    assert s.state.cards[first.id].zone=='stack'
    answer(s,[second.id])
    if s.state.rules.decision is not None:
        assert s.state.rules.decision.resume['step']=='ability_cost'
        answer(s,[murder.id,bear.id])
    assert all(s.state.players[p].life==value for p,value in before.items())
    assert all(s.state.cards[c.id].zone=='p1:graveyard' for c in (murder,bear))
    assert s.state.cards[first.id].zone=='p2:exile'
    assert s.state.cards[second.id].zone=='p3:exile'
    roundtrip(s)


@pytest.mark.parametrize('pay',[False,True])
def test_jetsam_actual_free_spell_cost_increase_pay_or_cancel_continues_other_opponent_cursor(cards,pay):
    s=setup(cards,'Flotsam // Jetsam','Thalia, Guardian of Thraben')
    put(s,'Thalia, Guardian of Thraben','battlefield')
    first=put(s,'Divination','graveyard',pid='p2')
    second=put(s,'Giant Growth','graveyard',pid='p3')
    source=put(s,'Flotsam // Jetsam','hand')
    mana(s,U=2,C=5)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    settle(s)
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[first.id])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    if pay:
        mana(s,C=1)
    answer(s,['pay' if pay else 'cancel'])
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert second.id in [o.id for o in s.state.rules.decision.options]
    answer(s,[])
    assert s.state.cards[first.id].zone==('p2:exile' if pay else 'p2:graveyard')
    assert s.state.cards[second.id].zone=='p3:graveyard'
    assert s.state.rules.free_cast_then is None and not s.state.rules.permissions
    roundtrip(s)


def founding_chapter(cards,chapter,*,first_hand=None,third_graveyard=None,battlefield=None,generic=1):
    s=setup(cards,'Founding the Third Path',*(first_hand or []),*(third_graveyard or []),*(battlefield or []))
    for name in first_hand or []:
        put(s,name,'hand')
    for name in third_graveyard or []:
        put(s,name,'graveyard')
    for name in battlefield or []:
        put(s,name,'battlefield')
    put(s,'Grizzly Bears','battlefield')
    source=put(s,'Founding the Third Path','hand')
    mana(s,U=1,C=generic)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    assert 'chapter number' in d.prompt
    answer(s,[str(chapter)])
    return s,source


def test_founding_actual_read_ahead_one_free_hand_spell_then_next_turn_chapter_two_mills_four(cards):
    s,source=founding_chapter(cards,1,first_hand=['Giant Growth','Divination'])
    growth=next(c for c in s.state.cards.values() if c.name=='Giant Growth' and c.zone=='p1:hand')
    divination=next(c for c in s.state.cards.values() if c.name=='Divination' and c.zone=='p1:hand')
    assert s.state.rules.decision.resume['step']=='free_cast_pick'
    assert divination.id not in [o.card_id for o in s.state.rules.decision.options]
    # A legal creature target is chosen before this native spell is committed.
    bear=next(c for c in s.state.cards.values() if c.name=='Grizzly Bears' and c.zone=='p1:battlefield')
    answer(s,[growth.id])
    if s.state.rules.decision is not None:
        answer(s,[bear.id])
    assert s.state.cards[growth.id].zone=='p1:graveyard'
    before=len(s.state.zones['p2:library'])
    to_phase(s,'draw',turn=4)
    for _ in range(20):
        if s.state.rules.decision is not None:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert 'p2' in [o.id for o in s.state.rules.decision.options]
    answer(s,['p2'])
    settle(s)
    assert len(s.state.zones['p2:library'])==before-4-1
    assert s.state.cards[source.id].counters.get('lore',0)==2
    roundtrip(s)


def test_founding_actual_read_ahead_three_exiles_original_then_copy_requires_ordinary_mana(cards):
    s,source=founding_chapter(cards,3,third_graveyard=['Divination'])
    original=next(c for c in s.state.cards.values() if c.name=='Divination' and c.zone=='p1:graveyard')
    mana(s,U=1,C=2)
    answer(s,[original.id])
    assert s.state.cards[original.id].zone=='p1:exile'
    d=s.state.rules.decision
    assert d.resume['step']=='free_cast_pick'
    copies=[o.card_id for o in d.options if o.card_id!=original.id]
    assert len(copies)==1
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[copies[0]])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    mana(s,U=1,C=2)
    answer(s,['pay'])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[original.id].zone=='p1:exile'
    roundtrip(s)


def test_native_self_cast_can_pay_announced_x_using_non_tap_altar_mana_ability(cards):
    s=setup(cards,'Earthquake')
    altar=put(s,"Ashnod's Altar",'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    spell=put(s,'Earthquake','hand')
    act(s,'p1',type='set_prefs',payment='self')
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,x_value=2)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    act(s,'p1',type='activate_ability',card_id=altar.id,ability=0)
    if s.state.rules.decision is not None and s.state.rules.decision.resume['step']=='ability_cost':
        answer(s,[bear.id])
    if s.state.rules.decision is not None:
        assert s.state.rules.decision.resume['step']=='pay_mana'
        answer(s,['pay'])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert all(s.state.players[p].life==38 for p in ('p1','p2','p3'))
    roundtrip(s)


@pytest.mark.xfail(not hasattr(engine.casting,'resume_paid_x_number'),strict=True,reason='Paid immediate X picker currently treats AUTO mana approximation as legal numeric bound')
def test_founding_paid_copy_x_choice_must_allow_legal_self_altar_mana(cards):
    s,_=founding_chapter(cards,3,third_graveyard=['Earthquake'])
    put(s,"Ashnod's Altar",'battlefield')
    original=next(c for c in s.state.cards.values() if c.name=='Earthquake' and c.zone=='p1:graveyard')
    mana(s,R=1)
    answer(s,[original.id])
    copy=s.state.rules.decision.options[0].id
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[copy])
    assert s.state.rules.decision.resume['step']=='free_x'
    ids=[o.id for o in s.state.rules.decision.options]
    assert 'x:2' in ids or 'x:other' in ids


def test_founding_actual_read_ahead_two_skips_hand_cast_and_can_target_self_for_four_card_mill(cards):
    s,source=founding_chapter(cards,2,first_hand=['Divination'])
    before=list(s.state.zones['p1:library'])
    assert all(p in [o.id for o in s.state.rules.decision.options] for p in ('p1','p2','p3'))
    answer(s,['p1'])
    assert len(set(before)&set(s.state.zones['p1:graveyard']))==4
    assert any(c.name=='Divination' and c.zone=='p1:hand' for c in s.state.cards.values())
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.cards[source.id].counters.get('lore',0)==2
    assert s.state.rules.decision is None
    roundtrip(s)


def test_founding_actual_first_chapter_exact_one_or_two_actual_spell_face_from_own_hand(cards):
    s,_=founding_chapter(cards,1,first_hand=['Ancestral Vision','Divination','Giant Growth','Two-Handed Axe // Sweeping Cleave','Forest'])
    byname={c.name:c for c in s.state.cards.values() if c.zone=='p1:hand'}
    ids=[o.id for o in s.state.rules.decision.options]
    assert byname['Giant Growth'].id in ids
    axe=byname['Two-Handed Axe // Sweeping Cleave']
    assert axe.id+'@1' in ids and axe.id+'@0' not in ids
    assert all(byname[name].id not in ids for name in ('Ancestral Vision','Divination','Forest'))
    bear=next(c for c in s.state.cards.values() if c.name=='Grizzly Bears' and c.zone=='p1:battlefield')
    answer(s,[axe.id+'@1'])
    if s.state.rules.decision is not None:
        answer(s,[bear.id])
    assert s.state.cards[axe.id].zone=='p1:exile'
    assert s.state.cards[byname['Giant Growth'].id].zone=='p1:hand'
    roundtrip(s)


def test_founding_actual_third_chapter_targets_only_own_instant_sorcery_card_and_decline_keeps_original_exiled(cards):
    s,source=founding_chapter(cards,3,third_graveyard=['Divination','Two-Handed Axe // Sweeping Cleave','Forest'])
    original=next(c for c in s.state.cards.values() if c.name=='Divination' and c.zone=='p1:graveyard')
    ids=[o.card_id or o.id for o in s.state.rules.decision.options]
    assert original.id in ids
    assert all(c.id not in ids for c in s.state.cards.values() if c.zone=='p1:graveyard' and c.name in ('Forest','Two-Handed Axe // Sweeping Cleave'))
    mana(s,U=1,C=2)
    answer(s,[original.id])
    copies=[o.card_id for o in s.state.rules.decision.options]
    answer(s,[])
    assert s.state.cards[original.id].zone=='p1:exile'
    assert all(cid not in s.state.cards for cid in copies)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.free_cast_then is None
    roundtrip(s)
