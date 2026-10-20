"""Canonical controller-relative tutor and actual-movement compensation proofs."""
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
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast, choose_named
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA=Path(__file__).parent/'fixtures/controller_tutor_cards.json'
NAMES=[c['name'] for c in json.loads(DATA.read_text())][:10]


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads(DATA.read_text())):
        base[c['name']]=card(c['name'],set_code='ctu',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names=[c['name'] for c in json.loads(DATA.read_text())]
    s=table(cards,[*names,'Plains','Island','Mountain','Command Tower','Grizzly Bears'],
            [*names,'Plains','Island','Mountain','Command Tower'],names)
    to_phase(s,'main1',turn=1)
    return s


def answer(s, ids):
    from app.game.state import GameState

    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    s.state = GameState.model_validate(s.state.model_dump(mode='json'))
    act(s, d.decider or d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def yes(s):
    if s.state.rules.decision.resume['step']=='search_may':
        answer(s,['yes'])


def find(s,name):
    yes(s)
    cid=choose_named(s,name)
    answer(s,[cid])
    return cid


@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    got=coverage.of_card_data(cards.resolve(name))
    assert got.level=='FULL',got


def test_arcum_search_by_target_controller(cards):
    s=setup(cards)
    source=put(s,'Arcum Dagsson','battlefield')
    target=put(s,'Memnite','battlefield','p2')
    s.state.rules.controlled_since[source.id].turn=0
    mana(s,C=10)
    from tests.test_rules_wave4h_activation_costs import ability
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{T}'),targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone=='p2:graveyard'
    assert s.state.rules.decision.player=='p2'
    cid=find(s,'Sol Ring')
    assert s.state.cards[cid].zone=='p2:battlefield'
    roundtrip(s)


def test_hellkite_actual_controller_search_stun_before_entry(cards):
    s=setup(cards)
    target=put(s,'Command Tower','battlefield','p2')
    cast(s,'Magmatic Hellkite')
    answer(s,[target.id])
    assert s.state.cards[target.id].zone=='p2:graveyard'
    assert s.state.rules.decision.player=='p2'
    cid=find(s,'Island')
    assert s.state.cards[cid].zone=='p2:battlefield' and s.state.cards[cid].tapped
    assert s.state.cards[cid].counters.get('stun')==1
    roundtrip(s)


def test_rootweaver_opponents_partition_and_final_shuffle(cards):
    s=setup(cards)
    cast(s,'Rootweaver Druid')
    assert s.state.rules.decision.player=='p2'
    yes(s)
    ids=[choose_named(s,n) for n in ['Plains','Island','Forest']]
    answer(s,ids)
    assert s.state.rules.decision.player=='p2'
    answer(s,[ids[0]])
    assert s.state.cards[ids[0]].controller=='p1'
    assert all(s.state.cards[c].controller=='p2' for c in ids[1:])
    assert all(s.state.cards[c].tapped for c in ids)
    assert s.state.rules.decision.player=='p3'
    one=find(s,'Plains')
    assert s.state.cards[one].controller=='p1'
    roundtrip(s)


def test_buzzcrusher_nontarget_choices_then_actual_compensation(cards):
    s=setup(cards)
    a=put(s,'Command Tower','battlefield')
    b=put(s,'Darksteel Citadel','battlefield','p2')
    cast(s,"Krenko's Buzzcrusher")
    answer(s,[a.id])
    answer(s,[b.id])
    assert s.state.cards[a.id].zone=='p1:graveyard'
    assert s.state.cards[b.id].zone=='p2:battlefield'
    assert s.state.rules.decision.player=='p1'
    cid=find(s,'Plains')
    assert s.state.cards[cid].tapped
    assert s.state.rules.decision is None
    roundtrip(s)


def test_ashes_counts_actual_destroyed_by_controller(cards):
    s=setup(cards)
    a=put(s,'Command Tower','battlefield')
    b=put(s,'Great Furnace','battlefield','p2')
    safe=put(s,'Darksteel Citadel','battlefield','p2')
    cast(s,'From the Ashes')
    assert s.state.cards[a.id].zone=='p1:graveyard' and s.state.cards[b.id].zone=='p2:graveyard'
    assert s.state.cards[safe.id].zone=='p2:battlefield'
    a_new=find(s,'Plains')
    b_new=find(s,'Island')
    assert s.state.cards[a_new].controller=='p1' and not s.state.cards[a_new].tapped
    assert s.state.cards[b_new].controller=='p2' and not s.state.cards[b_new].tapped
    roundtrip(s)


def test_vitriol_sacrifices_union_once_and_counts_artifact_lands(cards):
    s=setup(cards)
    a=put(s,'Great Furnace','battlefield')
    b=put(s,'Darksteel Citadel','battlefield','p2')
    ring=put(s,'Sol Ring','battlefield')
    cast(s,'Wave of Vitriol')
    assert all(s.state.cards[c.id].zone.endswith(':graveyard') for c in [a,b,ring])
    found=[find(s,'Plains'),find(s,'Island')]
    assert all(s.state.cards[c].tapped for c in found)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_balance_keep_five_then_fill_low_players(cards):
    s=setup(cards)
    names=['Plains','Island','Mountain','Forest','Command Tower','Great Furnace']
    lands=[put(s,n,'battlefield').id for n in names]
    put(s,'Island','battlefield','p2')
    cast(s,'Natural Balance')
    assert {o.id for o in s.state.rules.decision.options}==set(lands)
    answer(s,lands[:5])
    assert s.state.cards[lands[5]].zone=='p1:graveyard'
    assert s.state.rules.decision.player=='p2'
    found=find(s,'Forest')
    assert s.state.cards[found].controller=='p2' and not s.state.cards[found].tapped
    assert s.state.rules.decision.player=='p3'
    answer(s,['no'])
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.id in lands])==5
    roundtrip(s)


def test_tracks_multiple_targets_search_own_libraries(cards):
    s=setup(cards)
    cast(s,'Turtle Tracks',targets=['p1','p2'],target_counts=[2])
    a=find(s,'Plains')
    b=find(s,'Island')
    assert s.state.cards[a].controller=='p1' and not s.state.cards[a].tapped
    assert s.state.cards[b].controller=='p2' and not s.state.cards[b].tapped
    roundtrip(s)


def test_vizier_tutor_then_actual_embalm_trigger_before_token(cards):
    s=setup(cards)
    source=cast(s,'Vizier of the Anointed')
    target=find(s,'Aven Wind Guide')
    assert s.state.cards[target].zone=='p1:graveyard'
    mana(s,C=30,W=10,U=10)
    before=len(s.state.zones['p1:hand'])
    from tests.test_rules_wave4h_activation_costs import ability
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='activate_ability',card_id=target,ability=ability(s,s.state.cards[target],'Embalm'))
    for _ in range(12):
        if len(s.state.zones['p1:hand']) == before + 1:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert len(s.state.zones['p1:hand']) == before + 1
    assert not any(c.is_token and c.zone=='p1:battlefield' and c.name=='Aven Wind Guide' for c in s.state.cards.values())
    assert s.state.zones['stack']
    settle(s)
    assert len(s.state.zones['p1:hand'])==before+1
    assert any(c.is_token and c.zone=='p1:battlefield' and c.name=='Aven Wind Guide' for c in s.state.cards.values())
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


def test_transmute_actual_resolution_sacrifice_then_difference_payment(cards):
    s=setup(cards)
    artifact=put(s,'Sol Ring','battlefield')
    spell=cast(s,'Transmute Artifact')
    if s.state.rules.decision.resume['step']=='sacrifice_choice':
        answer(s,[artifact.id])
    assert s.state.cards[artifact.id].zone=='p1:graveyard'
    cid=find(s,'Darksteel Ingot')
    assert s.state.rules.decision is not None
    answer(s,['pay'])
    assert s.state.cards[cid].zone=='p1:battlefield'
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('forbidden',[False,True])
def test_arcum_search_even_when_sacrifice_forbidden_and_agent_authority(cards,forbidden):
    from tests.test_rules_wave4h_activation_costs import ability

    s=setup(cards)
    source=put(s,'Arcum Dagsson','battlefield')
    target=put(s,'Memnite','battlefield','p2')
    if forbidden:
        put(s,'Sigarda, Host of Herons','battlefield','p2')
    else:
        put(s,'Opposition Agent','battlefield')
    s.state.rules.controlled_since[source.id].turn=0
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{T}'),targets=[target.id])
    settle(s)
    yes(s)
    assert s.state.rules.decision.player=='p2'
    assert (s.state.rules.decision.decider or s.state.rules.decision.player)==('p2' if forbidden else 'p1')
    cid=choose_named(s,'Sol Ring')
    answer(s,[cid])
    assert s.state.cards[target.id].zone==('p2:battlefield' if forbidden else 'p2:graveyard')
    assert s.state.cards[cid].zone==('p2:battlefield' if forbidden else 'p2:exile')
    if not forbidden:
        assert any(p.card==cid and p.player=='p1' for p in s.state.rules.permissions)
    roundtrip(s)


@pytest.mark.parametrize('solemn',[False,True])
def test_hellkite_indestructible_target_still_searches_and_entry_counter_replacement(cards,solemn):
    s=setup(cards)
    target=put(s,'Darksteel Citadel','battlefield','p2')
    if solemn:
        put(s,'Solemnity','battlefield')
    cast(s,'Magmatic Hellkite')
    answer(s,[target.id])
    cid=find(s,'Plains')
    assert s.state.cards[target.id].zone=='p2:battlefield'
    assert s.state.cards[cid].zone=='p2:battlefield'
    assert s.state.cards[cid].counters.get('stun',0)==(0 if solemn else 1)
    roundtrip(s)


def test_rootweaver_agent_finds_unavailable_to_partition_cold(cards):
    from tests.test_rules_qualified_attached_tutors import cold

    s=setup(cards)
    put(s,'Opposition Agent','battlefield')
    cast(s,'Rootweaver Druid')
    yes(s)
    cid=choose_named(s,'Plains')
    s=cold(s,cards)
    assert s.state.rules.decision.decider=='p1'
    answer(s,[cid])
    assert s.state.cards[cid].zone=='p2:exile'
    assert any(p.card==cid and p.player=='p1' for p in s.state.rules.permissions)
    assert s.state.rules.decision.player=='p3'
    answer(s,['no'])
    roundtrip(s)


@pytest.mark.parametrize('accept',[False,True])
def test_transmute_higher_value_optional_payment_cold(cards,accept):
    from tests.test_rules_qualified_attached_tutors import cold

    s=setup(cards)
    artifact=put(s,'Sol Ring','battlefield')
    cast(s,'Transmute Artifact')
    assert s.state.cards[artifact.id].zone=='p1:graveyard'
    cid=find(s,'Darksteel Ingot')
    assert s.state.cards[cid].zone=='p1:library'
    s=cold(s,cards)
    answer(s,['pay' if accept else 'decline'])
    assert s.state.cards[cid].zone==('p1:battlefield' if accept else 'p1:graveyard')
    roundtrip(s)


def test_transmute_agent_cannot_follow_diverted_artifact(cards):
    s=setup(cards)
    put(s,'Opposition Agent','battlefield','p2')
    artifact=put(s,'Sol Ring','battlefield')
    cast(s,'Transmute Artifact')
    assert s.state.cards[artifact.id].zone=='p1:graveyard'
    assert s.state.rules.decision.decider=='p2'
    cid=choose_named(s,'Darksteel Ingot')
    answer(s,[cid])
    assert s.state.cards[cid].zone=='p1:exile'
    assert any(p.card==cid and p.player=='p2' for p in s.state.rules.permissions)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_transmute_lower_value_no_payment_and_no_artifact_no_search(cards):
    s=setup(cards)
    expensive=put(s,'Darksteel Ingot','battlefield')
    cast(s,'Transmute Artifact')
    assert s.state.cards[expensive.id].zone=='p1:graveyard'
    cid=find(s,'Sol Ring')
    assert s.state.cards[cid].zone=='p1:battlefield'
    assert s.state.rules.decision is None
    act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'graveyard'})
    cast(s,'Transmute Artifact')
    assert s.state.rules.decision is None
    roundtrip(s)


def test_hellkite_target_becomes_illegal_no_search(cards):
    s=setup(cards)
    target=put(s,'Dryad Arbor','battlefield','p2')
    spell=put(s,'Magmatic Hellkite','hand')
    mana(s,C=10,R=10)
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    for _ in range(15):
        if s.state.rules.decision is not None:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    d=s.state.rules.decision
    roundtrip(s)
    act(s,d.player,type="choose",decision_id=d.id,option_ids=[target.id])
    # Holding priority leaves the targeted ability on the stack.
    assert s.state.zones['stack']
    flicker=put(s,'Pongify','hand')
    mana(s,U=2,C=5)
    act(s,'p1',type='cast_spell',card_id=flicker.id,targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone=='p2:graveyard'
    assert s.state.cards[target.id].counters.get('stun',0)==0
    assert s.state.rules.decision is None
    roundtrip(s)


def test_vitriol_prohibited_opponent_sacrifices_give_no_compensation(cards):
    s=setup(cards)
    protected=put(s,'Great Furnace','battlefield','p2')
    sigarda=put(s,'Sigarda, Host of Herons','battlefield','p2')
    own=put(s,'Command Tower','battlefield')
    cast(s,'Wave of Vitriol')
    assert s.state.cards[protected.id].zone=='p2:battlefield'
    assert s.state.cards[sigarda.id].zone=='p2:battlefield'
    assert s.state.cards[own.id].zone=='p1:graveyard'
    find(s,'Plains')
    assert s.state.rules.decision is None
    roundtrip(s)


def test_arcum_foreign_library_search_rest_ws_privacy(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.test_rules_wave4h_activation_costs import ability

    s=setup(cards)
    source=put(s,'Arcum Dagsson','battlefield')
    target=put(s,'Memnite','battlefield','p2')
    s.state.rules.controlled_since[source.id].turn=0
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{T}'),targets=[target.id])
    settle(s)
    yes(s)
    hidden=[o.id for o in s.state.rules.decision.options]
    found=choose_named(s,'Sol Ring')
    with TestClient(create_app(settings)) as client:
        deck=client.post('/api/decks',json={'text':'Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest'}).json()['id']
        game=client.post('/api/games',json={'mode':'lan','players':[{'name':'Alice','deck_id':deck},{'name':'Bob','deck_id':deck}]}).json()
        gid=game['game']['id']
        alice=game['seat']['token']
        bob=client.post('/api/join',json={'code':game['game']['code'],'name':'Bob'}).json()['token']
        spec=client.post('/api/join',json={'code':game['game']['code'],'spectate':True}).json()['token']
        client.app.state.services.hub.get(gid).game=s
        for stage in range(2):
            if stage:
                answer(s,[found])
            for token in [alice,bob,spec]:
                response=client.get(f'/api/games/{gid}/view',headers={'X-Seat-Token':token})
                assert response.status_code==200
                with client.websocket_connect(f'/ws/games/{gid}?token={token}') as ws:
                    frame=ws.receive_json()
                    assert frame['type']=='state'
                for raw in [response.text,json.dumps(frame)]:
                    if not stage:
                        assert all((cid in raw)==(token==bob) for cid in hidden)
                    else:
                        assert found in raw
                        assert all(cid not in raw for cid in hidden if cid!=found)
    roundtrip(s)
