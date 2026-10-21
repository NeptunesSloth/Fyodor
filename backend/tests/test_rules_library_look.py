"""Private library inspection preserves owner, viewer and chooser across native continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/library_look_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Dimir Charm', "Tahngarth's Glare", 'Ransack', 'Wand of Denial', 'Psychic Surgery']

@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def settle(s):
    for _ in range(60):
        d=s.state.rules.decision
        if d is not None:
            if d.kind == 'order' and d.resume.get('step') != 'order_library':
                act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
            else:
                return
        elif s.state.zones.get('stack'):
            act(s,s.state.rules.priority,type='pass_priority')
        else:
            return


def answer(s, ids):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    s.state = GameState.model_validate(s.state.model_dump(mode='json'))
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def setup(cards):
    from tests.test_rules_refused_look import stack_library
    s = table(cards, [*NAMES, 'Island', 'Mountain', 'Rest in Peace'], ['Forest','Grizzly Bears','Lightning Bolt','Island','Mountain', "Feldon's Cane", 'Disenchant'], [])
    to_phase(s, 'main1', turn=1)
    top = stack_library(s, ['Forest', 'Grizzly Bears', 'Lightning Bolt', 'Island', 'Mountain'], pid='p2')
    return s, top


def cast_spell(s, name, **kwargs):
    source = put(s, name, 'hand')
    mana(s, U=5, B=5, R=5, C=5)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'], **kwargs)
    settle(s)
    return source


def private(s, viewer, ids):
    assert s.state.rules.decision.player == viewer
    for pid in ['p1', 'p2', 'p3']:
        if pid != viewer:
            data = s.view(pid)['rules']['decision']
            assert not any(cid in json.dumps(data) for cid in ids)


def test_dimir_choose_one_remainder_graveyard(cards):
    s, top = setup(cards)
    cast_spell(s, 'Dimir Charm', modes=[2])
    private(s, 'p1', top[:3])
    answer(s, [top[1]])
    assert s.state.zones['p2:library'][0] == top[1]
    assert all(s.state.cards[c].zone == 'p2:graveyard' for c in [top[0],top[2]])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_ransack_independent_bottom_and_top_order(cards):
    s, top = setup(cards)
    cast_spell(s, 'Ransack')
    private(s, 'p1', top)
    answer(s, [top[0],top[2]])
    answer(s, [top[2],top[0]])
    answer(s, [top[4],top[1],top[3]])
    assert s.state.zones['p2:library'][:3] == [top[4],top[1],top[3]]
    assert s.state.zones['p2:library'][-2:] == [top[0],top[2]]
    assert s.state.rules.decision is None
    roundtrip(s)


def test_tahngarth_reciprocal_viewer(cards):
    from tests.test_rules_refused_look import stack_library
    s, top = setup(cards)
    mine = stack_library(s, ['Island','Forest','Mountain'])
    cast_spell(s, "Tahngarth's Glare")
    private(s, 'p1',top[:3])
    answer(s, top[:3][::-1])
    private(s, 'p2',mine)
    answer(s,mine[::-1])
    assert s.state.zones['p2:library'][:3] == top[:3][::-1]
    assert s.state.zones['p1:library'][:3] == mine[::-1]
    roundtrip(s)


@pytest.mark.parametrize('pay',[True,False])
def test_wand_nonland_life_cost(cards,pay):
    from tests.test_rules_refused_look import stack_library
    s, _ = setup(cards)
    top = stack_library(s,['Grizzly Bears'],pid='p2')[0]
    wand = put(s,'Wand of Denial','battlefield')
    act(s,'p1',type='activate_ability',card_id=wand.id,targets=['p2'],ability=0)
    settle(s)
    assert wand.tapped
    d = s.state.rules.decision
    assert d.resume['step'] == 'pay_or_sacrifice'
    private(s,'p1',[top])
    answer(s,['pay' if pay else 'decline'])
    assert s.state.players['p1'].life == (38 if pay else 40)
    assert s.state.cards[top].zone == ('p2:graveyard' if pay else 'p2:library')
    assert s.state.rules.decision is None
    roundtrip(s)


def test_wand_land_never_offers_payment(cards):
    s,top=setup(cards)
    wand=put(s,'Wand of Denial','battlefield')
    act(s,'p1',type='activate_ability',card_id=wand.id,targets=['p2'],ability=0)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.zones['p2:library'][0] == top[0]
    assert s.state.players['p1'].life ==40
    roundtrip(s)


@pytest.mark.parametrize('exile',[True,False])
def test_psychic_shuffle_native_event_and_optional_exile(cards,exile):
    s,_=setup(cards)
    put(s,'Psychic Surgery','battlefield')
    cane=put(s,"Feldon's Cane",'battlefield',pid='p2')
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=cane.id,ability=0)
    settle(s)
    assert s.state.rules.decision is not None
    # Native trigger optionality asks before giving access to the hidden cards.
    if s.state.rules.decision.kind == 'confirm':
        answer(s,['yes'])
    d=s.state.rules.decision
    assert d is not None
    top=s.state.zones['p2:library'][:2]
    private(s,'p1',top)
    answer(s,[top[0]] if exile else [])
    if not exile:
        answer(s,top[::-1])
        assert s.state.zones['p2:library'][:2] == top[::-1]
    else:
        assert s.state.cards[top[0]].zone == 'p2:exile'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_psychic_own_shuffle_does_not_trigger(cards):
    s,_=setup(cards)
    put(s,'Psychic Surgery','battlefield')
    act(s,'p2',type='shuffle',player='p1',zone='library')
    settle(s)
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('chosen',[[],[0],[0,1,2,3,4]])
def test_ransack_empty_single_all_subsets(cards,chosen):
    s,top=setup(cards)
    cast_spell(s,'Ransack')
    ids=[top[i] for i in chosen]
    answer(s,ids)
    if len(ids)>1:
        answer(s,ids)
    rest=[c for c in top if c not in ids]
    if len(rest)>1:
        answer(s,rest)
    assert s.state.rules.decision is None
    assert s.state.zones['p2:library'][:len(rest)] == rest
    if ids:
        assert s.state.zones['p2:library'][-len(ids):] == ids[::-1]
    roundtrip(s)


def test_wand_insufficient_life_cannot_pay(cards):
    from tests.test_rules_refused_look import stack_library
    s,_=setup(cards)
    top=stack_library(s,['Grizzly Bears'],pid='p2')[0]
    act(s,'p1',type='set_life',player='p1',value=1)
    wand=put(s,'Wand of Denial','battlefield')
    act(s,'p1',type='activate_ability',card_id=wand.id,ability=0,targets=['p2'])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[top].zone == 'p2:library'
    assert s.state.players['p1'].life == 1
    roundtrip(s)


def test_library_decision_rest_and_websocket_redact_other_seats(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s,top=setup(cards)
    cast_spell(s,'Ransack')
    with TestClient(create_app(settings)) as client:
        deck_text="Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest"
        deck_id=client.post('/api/decks',json={'text':deck_text}).json()['id']
        game=client.post('/api/games',json={'mode':'lan','players':[{'name':'Alice','deck_id':deck_id},{'name':'Bob','deck_id':deck_id}]}).json()
        gid=game['game']['id']
        bob=client.post('/api/join',json={'code':game['game']['code'],'name':'Bob'}).json()['token']
        spec=client.post('/api/join',json={'code':game['game']['code'],'spectate':True}).json()['token']
        client.app.state.services.hub.get(gid).game=s
        for token in [bob,spec]:
            response=client.get(f'/api/games/{gid}/view',headers={'X-Seat-Token':token})
            assert response.status_code ==200
            assert not any(cid in response.text for cid in top)
            with client.websocket_connect(f'/ws/games/{gid}?token={token}') as ws:
                frame=ws.receive_json()
                assert frame['type']=='state'
                assert not any(cid in json.dumps(frame) for cid in top)


def test_wand_source_destroyed_before_payment(cards):
    from tests.test_rules_refused_look import stack_library
    s,_=setup(cards)
    top=stack_library(s,['Grizzly Bears'],pid='p2')[0]
    # The response is a real Disenchant; the original ability retains its controller.
    wand=put(s,'Wand of Denial','battlefield')
    response=put(s,'Disenchant','hand',pid='p2')
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='activate_ability',card_id=wand.id,ability=0,targets=['p2'])
    wait_priority(s,'p2')
    mana(s,pid='p2',W=1,C=1)
    act(s,'p2',type='cast_spell',card_id=response.id,targets=[wand.id])
    settle(s)
    assert s.state.cards[wand.id].zone == 'p1:graveyard'
    answer(s,['pay'])
    assert s.state.cards[top].zone == 'p2:graveyard'
    assert s.state.players['p1'].life ==38
    roundtrip(s)


def test_psychic_decline_look_leaves_library_private(cards):
    s,_=setup(cards)
    put(s,'Psychic Surgery','battlefield')
    cane=put(s,"Feldon's Cane",'battlefield',pid='p2')
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=cane.id,ability=0)
    settle(s)
    top=list(s.state.zones['p2:library'])
    assert s.state.rules.decision.kind == 'confirm'
    answer(s,['no'])
    assert s.state.zones['p2:library'] ==top
    assert s.state.rules.decision is None
    assert not any(c in json.dumps(s.view('p1')['cards']) for c in top)
    roundtrip(s)


def test_wand_native_graveyard_replacement(cards):
    from tests.test_rules_refused_look import stack_library
    s,_=setup(cards)
    put(s,'Rest in Peace','battlefield')
    settle(s)
    top=stack_library(s,['Grizzly Bears'],pid='p2')[0]
    wand=put(s,'Wand of Denial','battlefield')
    act(s,'p1',type='activate_ability',card_id=wand.id,ability=0,targets=['p2'])
    settle(s)
    answer(s,['pay'])
    assert s.state.cards[top].zone == 'p2:exile'
    assert s.state.players['p1'].life ==38
    roundtrip(s)
