"""Conditional inspected-card replacements preserve one verdict through native choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.conftest import claim_host, connect_game
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import answer, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/search_partition_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ["Nissa's Pilgrimage",'Viewpoint Synchronization','Boreas Charger','Verdant Mastery','Druid of the Emerald Grove']

@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'




def setup(cards):
    data=json.loads((Path(__file__).parent/'fixtures/search_partition_cards.json').read_text())
    names=[c['name'] for c in data]
    s=table(cards,names,names,names)
    to_phase(s,'main1',turn=1)
    return s


def cast(s,name,**kwargs):
    source=put(s,name,'hand')
    mana(s,C=12,G=6,W=6,U=6)
    act(s,'p1',type='cast_spell',card_id=source.id,**kwargs)
    settle(s)
    return source


@pytest.mark.parametrize('n',[0,1,2])
def test_pilgrimage_fewer_found_goes_to_battlefield_first(cards,n):
    s=setup(cards)
    source=cast(s,"Nissa's Pilgrimage")
    d=s.state.rules.decision
    assert d.resume['step']=='search' and d.max_choices==2
    found=[o.id for o in d.options[:n]]
    answer(s,found)
    if n==2:
        d=s.state.rules.decision
        assert d.resume['step']=='search_partition_cards'
        answer(s,[found[1]])
    assert sum(s.state.cards[c].zone=='p1:battlefield' for c in found)==min(n,1)
    assert sum(s.state.cards[c].zone=='p1:hand' for c in found)==max(0,n-1)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert all(s.state.cards[c].tapped for c in found if s.state.cards[c].zone=='p1:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('n',[0,1,2,3])
def test_viewpoint_puts_as_many_as_two_found_onto_battlefield(cards,n):
    s=setup(cards)
    cast(s,'Viewpoint Synchronization')
    d=s.state.rules.decision
    assert d.max_choices==3
    found=[o.id for o in d.options[:n]]
    answer(s,found)
    if n==3:
        answer(s,found[:2])
    assert sum(s.state.cards[c].zone=='p1:battlefield' for c in found)==min(n,2)
    assert sum(s.state.cards[c].zone=='p1:hand' for c in found)==max(0,n-2)
    roundtrip(s)


@pytest.mark.parametrize('graveyard',[[],['Discovery // Dispersal'],['Lightning Bolt','Divination']])
def test_pilgrimage_mastery_counts_cards_and_is_judged_before_search(cards,graveyard):
    s=setup(cards)
    for name in graveyard:
        put(s,name,'graveyard')
    cast(s,"Nissa's Pilgrimage")
    d=s.state.rules.decision
    assert d.max_choices==(3 if len(graveyard)==2 else 2)
    found=[o.id for o in d.options[:d.max_choices]]
    answer(s,found)
    answer(s,[found[0]])
    assert sum(s.state.cards[c].zone=='p1:hand' for c in found)==len(found)-1
    roundtrip(s)


@pytest.mark.parametrize('alternative',[False,True])
@pytest.mark.parametrize('n',[0,1,2,3,4])
def test_verdant_ordered_partition_obeys_alternative_cost_and_recipient(cards,alternative,n):
    s=setup(cards)
    source=put(s,'Verdant Mastery','hand')
    mana(s,C=10,G=2)
    act(s,'p1',type='cast_spell',card_id=source.id,**({'alt_cost':f'{source.id}:0'} if alternative else {}))
    settle(s)
    d=s.state.rules.decision
    assert d.max_choices==4
    found=[o.id for o in d.options[:n]]
    answer(s,found)
    recipient=None
    if alternative and n:
        d=s.state.rules.decision
        assert d.resume['step']=='search_partition_recipient'
        answer(s,['p3'])
        recipient=found[-1]
        if n>1:
            answer(s,[recipient])
    d=s.state.rules.decision
    if d is not None:
        assert d.resume['step']=='search_partition_cards'
        answer(s,[c for c in found if c!=recipient][:2])
    assert sum(s.state.cards[c].zone=='p3:battlefield' for c in found)==int(alternative and n>0)
    own=min(2,n-int(alternative and n>0))
    assert sum(s.state.cards[c].zone=='p1:battlefield' for c in found)==own
    assert sum(s.state.cards[c].zone=='p1:hand' for c in found)==n-own-int(alternative and n>0)
    assert all(s.state.cards[c].owner=='p1' for c in found)
    roundtrip(s)


@pytest.mark.parametrize('more',[False,True])
def test_boreas_leaves_chooses_eligible_opponent_and_searches_difference(cards,more):
    s=setup(cards)
    charger=put(s,'Boreas Charger','battlefield')
    put(s,'Forest','battlefield')
    if more:
        ids=[c.id for c in s.state.cards.values() if c.owner=='p2' and c.name=='Island'][:4]
        act(s,'p2',type='move',card_ids=ids,to={'zone':'battlefield'})
    cast(s,'Swords to Plowshares',targets=[charger.id])
    d=s.state.rules.decision
    if more:
        assert d.resume['step']=='search_partition_opponent'
        assert [o.id for o in d.options]==['p2']
        answer(s,['p2'])
        d=s.state.rules.decision
    assert d.resume['step']=='search' and d.resume['e']['max']==(3 if more else 0)
    # Finding fewer Plains than the land difference is legal.
    found=[o.id for o in d.options[:1]] if more else []
    answer(s,found)
    assert all(s.state.cards[c].zone=='p1:battlefield' for c in found)
    assert s.state.cards[charger.id].zone=='p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('result,expected',[(1,0),(9,0),(10,1),(19,1),(20,2)])
def test_druid_rolls_after_search_then_uses_native_row(cards,monkeypatch,result,expected):
    from tests.test_rules_wave12a_counters_keywords import rolls
    rolls(monkeypatch,result)
    s=setup(cards)
    cast(s,'Druid of the Emerald Grove')
    d=s.state.rules.decision
    assert d.resume['step']=='search'
    found=[o.id for o in d.options[:2]]
    answer(s,found)
    if expected==1:
        d=s.state.rules.decision
        assert d.resume['step']=='search_partition_cards'
        answer(s,[found[1]])
    assert sum(s.state.cards[c].zone=='p1:battlefield' for c in found)==expected
    assert sum(s.state.cards[c].zone=='p1:hand' for c in found)==2-expected
    roundtrip(s)


def test_druid_rolls_even_when_search_finds_nothing(cards,monkeypatch):
    from tests.test_rules_wave12a_counters_keywords import rolls
    rolls(monkeypatch,20)
    s=setup(cards)
    cast(s,'Druid of the Emerald Grove')
    answer(s,[])
    assert s.state.rules.decision is None
    from app.game.rules_state import turn_log_now
    assert turn_log_now(s.state).rolled.get('p1')==1
    roundtrip(s)


@pytest.mark.parametrize('result',[5,15,20])
def test_druid_prohibited_search_still_rolls_and_finishes(cards,monkeypatch,result):
    from app.game.rules_state import turn_log_now
    from tests.test_rules_wave12a_counters_keywords import rolls
    rolls(monkeypatch,result)
    s=setup(cards)
    put(s,'Stranglehold','battlefield',pid='p2')
    cast(s,'Druid of the Emerald Grove')
    assert s.state.rules.decision is None
    assert turn_log_now(s.state).rolled.get('p1')==1
    roundtrip(s)


def test_druid_native_extra_die_uses_kept_result(cards,monkeypatch):
    from app.game.rules_state import turn_log_now
    from tests.test_rules_wave12a_counters_keywords import rolls
    rolls(monkeypatch,3,20)
    s=setup(cards)
    put(s,'Wyll, Blade of Frontiers','battlefield')
    cast(s,'Druid of the Emerald Grove')
    d=s.state.rules.decision
    found=[o.id for o in d.options[:2]]
    answer(s,found)
    assert all(s.state.cards[c].zone=='p1:battlefield' for c in found)
    assert turn_log_now(s.state).rolled.get('p1')==1
    roundtrip(s)


@pytest.mark.parametrize('name',["Nissa's Pilgrimage",'Viewpoint Synchronization','Verdant Mastery'])
def test_partition_search_opposition_agent_diverts_all_found_cards(cards,name):
    s=setup(cards)
    put(s,'Opposition Agent','battlefield',pid='p2')
    cast(s,name)
    d=s.state.rules.decision
    assert d.decider=='p2'
    found=[o.id for o in d.options[:2]]
    roundtrip(s)
    act(s,'p2',type='choose',decision_id=d.id,option_ids=found)
    settle(s)
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone=='p1:exile' for c in found)
    assert not any(s.state.cards[c].zone.endswith(':battlefield') for c in found)
    roundtrip(s)


def test_search_private_then_revealed_packet_then_hidden_hand_rest_over_http_and_ws(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s=setup(cards)
    cast(s,"Nissa's Pilgrimage")
    found=[o.id for o in s.state.rules.decision.options[:2]]
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        deck_id=client.post('/api/decks',json={'text':'Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest'}).json()['id']
        game=client.post('/api/games',json={'mode':'lan','players':[{'name':'Alice','deck_id':deck_id},{'name':'Bob','deck_id':deck_id}]}).json()
        gid=game['game']['id']
        bob=client.post('/api/join',json={'code':game['game']['code'],'name':'Bob'}).json()['token']
        spec=client.post('/api/join',json={'code':game['game']['code'],'spectate':True}).json()['token']
        client.app.state.services.hub.get(gid).game=s
        for stage in range(3):
            if stage==1:
                answer(s,found)
            elif stage==2:
                answer(s,[found[0]])
            for token in [bob,spec]:
                response=client.get(f'/api/games/{gid}/view',headers={'X-Seat-Token':token})
                assert response.status_code==200
                with connect_game(client, gid, token) as ws:
                    frame=ws.receive_json()
                    assert frame['type']=='state'
                for raw in [response.text,json.dumps(frame)]:
                    assert (found[1] in raw)==(stage==1)
                    assert (found[0] in raw)==(stage>0)
    roundtrip(s)


@pytest.mark.parametrize('replacement',['Containment Priest','Hallowed Moonlight',"Grafdigger's Cage"])
def test_partition_land_entry_uses_creature_replacement_before_entry(cards,replacement):
    s=setup(cards)
    put(s,'Life and Limb','battlefield')
    if replacement=='Hallowed Moonlight':
        cast(s,replacement)
    else:
        put(s,replacement,'battlefield')
    cast(s,"Nissa's Pilgrimage")
    d=s.state.rules.decision
    found=[o.id for o in d.options[:2]]
    answer(s,found)
    answer(s,[found[0]])
    assert s.state.cards[found[1]].zone=='p1:hand'
    if replacement!="Grafdigger's Cage":
        assert not any(c.name=='Forest' and c.zone=='p1:battlefield' for c in s.state.cards.values())
        assert s.state.cards[found[0]].zone=='p1:exile'
    else:
        # Cage refers to creature CARDS in the library. This Forest only
        # becomes a creature as a permanent; it isn't a creature card there.
        assert s.state.cards[found[0]].zone=='p1:battlefield'
    roundtrip(s)


def test_search_partition_exact_object_does_not_move_a_returned_incarnation(cards):
    s=setup(cards)
    cast(s,"Nissa's Pilgrimage")
    found=[o.id for o in s.state.rules.decision.options[:2]]
    answer(s,found)
    act(s,'p1',type='move',card_ids=[found[0]],to={'zone':'exile'})
    act(s,'p1',type='move',card_ids=[found[0]],to={'zone':'library'},position='top')
    answer(s,[found[0]])
    assert not any(c.name=='Forest' and c.zone=='p1:battlefield' for c in s.state.cards.values())
    assert s.state.cards[found[1]].zone=='p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('alternative',[False,True])
def test_verdant_actual_spell_copy_keeps_alternative_payment_decision(cards,alternative):
    s=setup(cards)
    source=put(s,'Verdant Mastery','hand')
    rev=put(s,'Reverberate','hand')
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,C=8,G=2,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id,**({'alt_cost':f'{source.id}:0'} if alternative else {}))
    act(s,'p1',type='cast_spell',card_id=rev.id,targets=[source.id])
    settle(s)
    for original in [False,True]:
        d=s.state.rules.decision
        assert d.resume['step']=='search'
        assert (d.resume['ctx']['source_card']==source.id)==original
        found=[d.options[0].id]
        answer(s,found)
        if alternative:
            d=s.state.rules.decision
            assert d.resume['step']=='search_partition_recipient'
            answer(s,['p2'])
        assert s.state.cards[found[0]].zone==('p2:battlefield' if alternative else 'p1:battlefield')
        assert s.state.cards[found[0]].owner=='p1'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_partition_search_preserves_mindcensor_native_depth(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards)
    put(s,'Aven Mindcensor','battlefield',pid='p2')
    top=stack_library(s,['Lightning Bolt','Divination','Island','Plains','Forest'])
    cast(s,'Viewpoint Synchronization')
    d=s.state.rules.decision
    assert {o.id for o in d.options}==set(top[2:4])
    answer(s,[o.id for o in d.options])
    assert all(s.state.cards[c].zone=='p1:battlefield' for c in top[2:4])
    roundtrip(s)


def test_druid_agent_diversion_does_not_skip_native_die_roll(cards,monkeypatch):
    from app.game.rules_state import turn_log_now
    from tests.test_rules_wave12a_counters_keywords import rolls
    rolls(monkeypatch,20)
    s=setup(cards)
    put(s,'Opposition Agent','battlefield',pid='p2')
    cast(s,'Druid of the Emerald Grove')
    d=s.state.rules.decision
    found=[o.id for o in d.options[:2]]
    assert d.decider=='p2'
    from app.rules import dice
    native_roll=dice.roll
    def roll_after_exile(plan,ctx,e):
        assert all(plan.state.cards[c].zone=='p1:exile' for c in found)
        assert all(any(p.player=='p2' and p.card==c and p.object_id==plan.oid(c)
                       for p in plan.rules.permissions) for c in found)
        return native_roll(plan,ctx,e)
    monkeypatch.setattr(dice,'roll',roll_after_exile)
    act(s,'p2',type='choose',decision_id=d.id,option_ids=found)
    settle(s)
    assert turn_log_now(s.state).rolled.get('p1')==1
    assert all(s.state.cards[c].zone=='p1:exile' for c in found)
    roundtrip(s)


def test_boreas_departed_foreign_owned_source_uses_trigger_controller_library(cards):
    s=setup(cards)
    charger=put(s,'Boreas Charger','battlefield',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[charger.id],player='p1')
    ids=[c.id for c in s.state.cards.values() if c.owner=='p2' and c.name=='Island'][:3]
    act(s,'p2',type='move',card_ids=ids,to={'zone':'battlefield'})
    cast(s,'Swords to Plowshares',targets=[charger.id])
    d=s.state.rules.decision
    assert d.player=='p1'
    answer(s,['p2'])
    d=s.state.rules.decision
    assert d.player=='p1'
    chosen=next(o.id for o in d.options if s.state.cards[o.id].name=='Mistveil Plains')
    answer(s,[chosen])
    assert s.state.cards[chosen].zone=='p1:battlefield'
    assert s.state.cards[chosen].owner=='p1'
    assert s.state.cards[charger.id].zone=='p2:exile'
    roundtrip(s)
