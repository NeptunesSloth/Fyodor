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
from tests.test_rules_refused_look import stack_library, thin_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/conditional_look_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Flow State','Accumulate Wisdom','See the Truth','Gather the Pack',"Rowan's Grim Search"]

@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards,extra=()):
    data=json.loads((Path(__file__).parent/'fixtures/conditional_look_cards.json').read_text())
    names=[c['name'] for c in data if 'Token' not in c['type_line']]
    s=table(cards,[*names,*extra],names,names)
    to_phase(s,'main1',turn=1)
    return s


def cast(s,name,**kwargs):
    source=put(s,name,'hand')
    mana(s,C=10,U=10,B=10,R=10,G=10,W=10)
    act(s,'p1',type='cast_spell',card_id=source.id,**kwargs)
    settle(s)
    return source


def finish_order(s):
    d=s.state.rules.decision
    if d is not None:
        assert d.resume['step']=='order_library'
        answer(s,[o.id for o in d.options])
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('instant,sorcery',[(False,False),(True,False),(False,True),(True,True)])
def test_flow_state_conjunction_and_pick_count(cards,instant,sorcery):
    s=setup(cards)
    if instant:
        put(s,'Lightning Bolt','graveyard')
    if sorcery:
        put(s,'Divination','graveyard')
    source=put(s,'Flow State','hand')
    top=stack_library(s,['Forest','Grizzly Bears','Shivan Dragon'])
    mana(s,U=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    n=2 if instant and sorcery else 1
    assert s.state.rules.decision.max_choices==n
    answer(s,top[:n])
    finish_order(s)
    assert all(s.state.cards[c].zone=='p1:hand' for c in top[:n])
    assert all(s.state.cards[c].zone=='p1:library' for c in top[n:])


def test_flow_one_instant_sorcery_split_card_satisfies_both(cards):
    s=setup(cards)
    put(s,'Discovery // Dispersal','graveyard')
    source=put(s,'Flow State','hand')
    top=stack_library(s,['Forest','Grizzly Bears','Shivan Dragon'])
    mana(s,U=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.rules.decision.max_choices==2
    answer(s,top[:2])
    finish_order(s)


@pytest.mark.parametrize('n',[0,2,3])
def test_accumulate_lessons_threshold_excludes_resolving_spell(cards,n):
    s=setup(cards)
    for name in ['Environmental Sciences','Introduction to Annihilation','Expanded Anatomy'][:n]:
        put(s,name,'graveyard')
    source=put(s,'Accumulate Wisdom','hand')
    top=stack_library(s,['Forest','Grizzly Bears','Shivan Dragon'])
    mana(s,U=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    if n<3:
        assert s.state.rules.decision.max_choices==1
        answer(s,[top[0]])
        finish_order(s)
    else:
        assert s.state.rules.decision is None
        assert all(s.state.cards[c].zone=='p1:hand' for c in top)
        roundtrip(s)


@pytest.mark.parametrize('mastery',[False,True])
def test_gather_mastery_chooses_once_before_milling_rest(cards,mastery):
    s=setup(cards)
    put(s,'Lightning Bolt','graveyard')
    if mastery:
        put(s,'Divination','graveyard')
    source=put(s,'Gather the Pack','hand')
    top=stack_library(s,['Grizzly Bears','Shivan Dragon','Opt','Environmental Sciences','Forest'])
    mana(s,G=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.rules.decision.max_choices==(2 if mastery else 1)
    n=2 if mastery else 1
    answer(s,top[:n])
    assert s.state.rules.decision is None  # Milling instant/sorcery cards doesn't create another pick.
    assert all(s.state.cards[c].zone=='p1:hand' for c in top[:n])
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in top[n:])
    roundtrip(s)


def test_gather_split_instant_sorcery_counts_as_one_card(cards):
    s=setup(cards)
    put(s,'Discovery // Dispersal','graveyard')
    source=put(s,'Gather the Pack','hand')
    top=stack_library(s,['Grizzly Bears','Shivan Dragon','Opt','Environmental Sciences','Forest'])
    mana(s,G=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.rules.decision.max_choices==1
    answer(s,[])
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in top)
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('bargain',[False,True])
def test_rowan_actual_bargain_keep_order_then_draw_and_life(cards,bargain):
    from app.rules.view import hints
    s=setup(cards)
    ring=put(s,'Sol Ring','battlefield')
    source=put(s,"Rowan's Grim Search",'hand')
    top=stack_library(s,['Forest','Grizzly Bears','Shivan Dragon','Opt'])
    mana(s,C=2,B=1)
    opt=hints(s.state,'p1',s.cards)['optional_costs'][source.id][0]
    act(s,'p1',type='cast_spell',card_id=source.id,optional_costs=[opt['id']] if bargain else [])
    settle(s)
    if bargain:
        assert s.state.rules.decision.resume['step']=='pick_looked'
        assert s.state.rules.decision.max_choices==2
        answer(s,[top[0],top[2]])
        assert s.state.rules.decision.resume['step']=='order_library'
        answer(s,[top[2],top[0]])
        assert all(s.state.cards[c].zone=='p1:graveyard' for c in [top[1],top[3]])
        assert all(s.state.cards[c].zone=='p1:hand' for c in [top[0],top[2]])
    else:
        assert all(s.state.cards[c].zone=='p1:hand' for c in top[:2])
        assert s.state.zones['p1:library'][:2]==top[2:]
    assert s.state.cards[ring.id].zone==('p1:graveyard' if bargain else 'p1:battlefield')
    assert s.state.players['p1'].life==38
    assert s.state.rules.decision is None
    roundtrip(s)


def prepare_flashback_truth(s):
    source=put(s,'See the Truth','graveyard')
    flames=put(s,'Past in Flames','hand')
    mana(s,C=3,R=1)
    act(s,'p1',type='cast_spell',card_id=flames.id)
    settle(s)
    assert s.state.rules.decision is None
    return source


def test_see_truth_hand_cast_looks_three_keeps_one(cards):
    s=setup(cards)
    source=put(s,'See the Truth','hand')
    top=stack_library(s,['Forest','Grizzly Bears','Shivan Dragon'])
    mana(s,U=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.rules.decision.max_choices==1
    answer(s,[top[1]])
    finish_order(s)
    assert s.state.cards[top[1]].zone=='p1:hand'
    assert all(s.state.cards[c].zone=='p1:library' for c in [top[0],top[2]])


def test_see_truth_real_granted_flashback_takes_all_three(cards):
    s=setup(cards)
    source=prepare_flashback_truth(s)
    top=stack_library(s,['Forest','Grizzly Bears','Shivan Dragon'])
    mana(s,U=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone=='p1:hand' for c in top)
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)


def test_copy_of_nonhand_truth_was_not_cast_and_gets_one(cards):
    s=setup(cards)
    source=prepare_flashback_truth(s)
    rev=put(s,'Reverberate','hand')
    top=stack_library(s,['Forest','Grizzly Bears','Shivan Dragon','Opt','Llanowar Elves','Sol Ring'])
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,U=1,C=1,R=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    act(s,'p1',type='cast_spell',card_id=rev.id,targets=[source.id])
    settle(s)
    d=s.state.rules.decision
    assert d.resume['step']=='pick_looked' and d.max_choices==1
    assert d.resume['ctx']['source_card']!=source.id
    answer(s,[top[0]])
    assert s.state.rules.decision.resume['step']=='order_library'
    answer(s,top[1:3])
    assert s.state.rules.decision is None
    assert s.state.cards[top[0]].zone=='p1:hand'
    assert all(s.state.cards[c].zone=='p1:library' for c in top[1:3])
    assert all(s.state.cards[c].zone=='p1:hand' for c in top[3:])
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('bargain',[False,True])
def test_actual_rowan_copy_retains_bargain_decision(cards,bargain):
    from app.rules.view import hints
    s=setup(cards)
    ring=put(s,'Sol Ring','battlefield')
    source=put(s,"Rowan's Grim Search",'hand')
    rev=put(s,'Reverberate','hand')
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,C=2,B=1,R=2)
    opt=hints(s.state,'p1',s.cards)['optional_costs'][source.id][0]
    act(s,'p1',type='cast_spell',card_id=source.id,optional_costs=[opt['id']] if bargain else [])
    act(s,'p1',type='cast_spell',card_id=rev.id,targets=[source.id])
    settle(s)
    if bargain:
        d=s.state.rules.decision
        assert d.resume['step']=='pick_looked' and d.max_choices==2
        assert d.resume['ctx']['source_card']!=source.id
        answer(s,[])
        d=s.state.rules.decision
        assert d.resume['step']=='pick_looked' and d.resume['ctx']['source_card']==source.id
        answer(s,[])
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life==36
    assert s.state.cards[ring.id].zone==('p1:graveyard' if bargain else 'p1:battlefield')
    roundtrip(s)


def test_flow_condition_read_at_resolution_after_actual_crypt_response(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s=setup(cards)
    put(s,'Lightning Bolt','graveyard')
    put(s,'Divination','graveyard')
    crypt=put(s,"Tormod's Crypt",'battlefield',pid='p2')
    source=put(s,'Flow State','hand')
    top=stack_library(s,['Forest','Grizzly Bears','Shivan Dragon'])
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,U=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=crypt.id,ability=0,targets=['p1'])
    settle(s)
    assert s.state.rules.decision.max_choices==1
    answer(s,[top[0]])
    finish_order(s)


@pytest.mark.parametrize('name',NAMES[:4])
@pytest.mark.parametrize('n',[0,1])
def test_short_library_resolves_without_requiring_unavailable_cards(cards,name,n):
    s=setup(cards)
    source=put(s,name,'hand')
    top=thin_library(s,['Grizzly Bears'] if n else [])
    mana(s,U=3,G=3,C=3)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    if s.state.rules.decision is not None:
        assert s.state.rules.decision.max_choices<=1
        answer(s,top)
    assert s.state.rules.decision is None
    if n:
        assert s.state.cards[top[0]].zone=='p1:hand'
    roundtrip(s)


def test_gather_no_creature_options_still_private_and_can_decline(cards):
    s=setup(cards)
    source=put(s,'Gather the Pack','hand')
    top=stack_library(s,['Forest','Opt','Environmental Sciences','Divination','Lightning Bolt'])
    mana(s,G=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.rules.decision.options==[]
    answer(s,[])
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in top)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_gather_graveyard_replacement_and_rowan_draw_prohibition_are_native(cards):
    from app.rules.view import hints
    s=setup(cards)
    put(s,'Rest in Peace','battlefield')
    settle(s)
    source=put(s,'Gather the Pack','hand')
    top=stack_library(s,['Grizzly Bears','Shivan Dragon','Opt','Environmental Sciences','Forest'])
    mana(s,G=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    answer(s,[top[0]])
    assert all(s.state.cards[c].zone=='p1:exile' for c in top[1:])
    ring=put(s,'Sol Ring','battlefield')
    put(s,'Spirit of the Labyrinth','battlefield')
    rowan=put(s,"Rowan's Grim Search",'hand')
    mana(s,B=1,C=2)
    opt=hints(s.state,'p1',s.cards)['optional_costs'][rowan.id][0]
    act(s,'p1',type='cast_spell',card_id=rowan.id,optional_costs=[opt['id']])
    settle(s)
    if s.state.rules.decision.resume['step']!='pick_looked':
        assert ring.id in [o.id for o in s.state.rules.decision.options]
        answer(s,[ring.id])
    selected=[o.id for o in s.state.rules.decision.options][:2]
    answer(s,selected)
    answer(s,selected[::-1])
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone=='p1:library' for c in selected)
    assert s.state.zones['p1:library'][:2]==selected[::-1]
    assert s.state.cards[ring.id].zone=='p1:exile'
    assert s.state.players['p1'].life==38
    roundtrip(s)


def test_private_pick_and_order_redact_hidden_library_in_rest_and_websocket(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s=setup(cards)
    source=put(s,'Flow State','hand')
    top=stack_library(s,['Forest','Grizzly Bears','Shivan Dragon'])
    mana(s,U=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        deck_id=client.post('/api/decks',json={'text':'Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest'}).json()['id']
        game=client.post('/api/games',json={'mode':'lan','players':[{'name':'Alice','deck_id':deck_id},{'name':'Bob','deck_id':deck_id}]}).json()
        gid=game['game']['id']
        bob=client.post('/api/join',json={'code':game['game']['code'],'name':'Bob'}).json()['token']
        spec=client.post('/api/join',json={'code':game['game']['code'],'spectate':True}).json()['token']
        client.app.state.services.hub.get(gid).game=s
        for stage in ['pick','order','done']:
            if stage=='order':
                answer(s,[top[0]])
                assert s.state.rules.decision.resume['step']=='order_library'
            elif stage=='done':
                answer(s,top[1:])
                assert s.state.rules.decision is None
            for token in [bob,spec]:
                response=client.get(f'/api/games/{gid}/view',headers={'X-Seat-Token':token})
                assert response.status_code==200
                assert not any(cid in response.text for cid in top)
                with connect_game(client, gid, token) as ws:
                    frame=ws.receive_json()
                    assert frame['type']=='state'
                    assert not any(cid in json.dumps(frame) for cid in top)
    roundtrip(s)
