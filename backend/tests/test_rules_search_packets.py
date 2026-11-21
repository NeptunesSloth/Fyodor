"""Native qualified-search packets retain privacy, selection constraints and continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import answer, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.conftest import claim_host


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/search_packets_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Burning-Rune Demon','Threats Undetected','Ecological Appreciation','Emergent Ultimatum','Signal the Clans']

@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, extra=()):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/search_packets_cards.json').read_text())]
    s=table(cards,[*names,*extra],names,names)
    to_phase(s,'main1',turn=1)
    return s


def cast(s,name,x=None):
    source=put(s,name,'hand')
    mana(s,C=20,W=10,U=10,B=10,R=10,G=10)
    act(s,'p1',type='cast_spell',card_id=source.id,**({'x_value':x} if x is not None else {}))
    settle(s)
    return source


def named_options(s,names):
    out=[]
    for name in names:
        out.append(next(o.id for o in s.state.rules.decision.options if s.state.cards[o.id].name==name and o.id not in out))
    return out


def choose_search(s,names):
    assert s.state.rules.decision.resume['step']=='gifts_found'
    found=named_options(s,names)
    answer(s,found)
    return found


def test_threats_distinct_power_then_opponent_two_shuffle_rest_hand(cards):
    s=setup(cards)
    cast(s,'Threats Undetected')
    found=choose_search(s,['Ornithopter','Llanowar Elves','Grizzly Bears','Shivan Dragon'])
    assert s.state.rules.decision.player=='p1'
    answer(s,['p3'])
    assert s.state.rules.decision.player=='p3'
    answer(s,found[:2])
    assert all(c not in s.state.cards for c in found[:2])
    assert all(s.state.cards[c].zone=='p1:hand' for c in found[2:])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_threats_rejects_same_numeric_power_without_mutation(cards):
    s=setup(cards)
    cast(s,'Threats Undetected')
    found=named_options(s,['Grizzly Bears','Snapcaster Mage'])
    seq=s.state.seq
    with pytest.raises(ActionError,match='different powers'):
        answer(s,found)
    assert s.state.seq==seq
    choose_search(s,['Llanowar Elves','Grizzly Bears'])
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('accept',[True,False])
def test_burning_rune_optional_search_and_fixed_name_exclusion(cards,accept):
    s=setup(cards,extra=['Burning-Rune Demon'])
    source=cast(s,'Burning-Rune Demon')
    assert s.state.rules.decision.kind=='confirm'
    answer(s,['yes' if accept else 'no'])
    if accept:
        assert all(s.state.cards[o.id].name!='Burning-Rune Demon' for o in s.state.rules.decision.options)
        found=choose_search(s,['Grizzly Bears','Forest'])
        answer(s,['p2'])
        answer(s,[found[0]])
        assert s.state.cards[found[0]].zone=='p1:hand'
        assert s.state.cards[found[1]].zone=='p1:graveyard'
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert len([e for e in s.state.rules.events if e.kind=='library_shuffled' and not e.manual])==int(accept)
    roundtrip(s)


@pytest.mark.parametrize('n',[0,1,2,3,4])
def test_ecological_mixed_sources_and_limited_found(cards,n):
    s=setup(cards)
    gy=put(s,'Grizzly Bears','graveyard')
    source=cast(s,'Ecological Appreciation',x=6)
    found=choose_search(s,['Ornithopter','Llanowar Elves','Grizzly Bears','Shivan Dragon'][:n])
    if n>2:
        answer(s,['p2'])
        answer(s,found[:2])
    assert s.state.cards[source.id].zone=='p1:exile'
    for cid in found[2:]:
        assert s.state.cards[cid].zone=='p1:battlefield'
        assert s.state.cards[cid].controller=='p1'
    assert s.state.rules.decision is None
    if n>=3:
        assert gy.id in found
    roundtrip(s)


@pytest.mark.parametrize('names',[['Grizzly Bears','Llanowar Elves','Shivan Dragon'],['Grizzly Bears','Grizzly Bears','Shivan Dragon'],['Grizzly Bears'],[]])
def test_signal_random_only_exact_three_distinct(cards,names):
    s=setup(cards,extra=['Grizzly Bears'])
    source=cast(s,'Signal the Clans')
    hand=set(s.state.zones.get('p1:hand',[]))
    found=choose_search(s,names)
    new=set(s.state.zones.get('p1:hand',[]))-hand
    expected=int(len(names)==3 and len(set(names))==3)
    assert len(new)==expected
    if expected:
        assert new.issubset(set(found))
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('n',[0,1,2,3])
def test_emergent_physically_exiles_then_native_cast_window(cards,n):
    s=setup(cards)
    source=cast(s,'Emergent Ultimatum')
    found=choose_search(s,['Grizzly Bears','Llanowar Elves','Shivan Dragon'][:n])
    if n>1:
        assert all(s.state.cards[c].zone=='p1:exile' for c in found)
        answer(s,['p3'])
        answer(s,[found[0]])
        d=s.state.rules.decision
        assert d.resume['step']=='free_cast_pick'
        assert {o.id for o in d.options}==set(found[1:])
        answer(s,[])  # Decline all remaining casts.
        assert all(s.state.cards[c].zone=='p1:exile' for c in found[1:])
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_threats_characteristic_defining_power_in_library_is_numeric(cards):
    from app.rules.plan import Plan
    s=setup(cards)
    put(s,'Lightning Bolt','graveyard')
    put(s,'Forest','graveyard')
    cast(s,'Threats Undetected')
    ids=named_options(s,['Tarmogoyf','Grizzly Bears'])
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[ids[0]]).pt==(2,3)
    with pytest.raises(ActionError,match='different powers'):
        answer(s,ids)
    choose_search(s,['Tarmogoyf','Llanowar Elves'])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_ecological_x_bound_and_distinct_name_search_validation(cards):
    s=setup(cards,extra=['Grizzly Bears'])
    cast(s,'Ecological Appreciation',x=2)
    d=s.state.rules.decision
    assert all(s.state.cards[o.id].name!='Shivan Dragon' for o in d.options)
    ids=named_options(s,['Grizzly Bears','Grizzly Bears'])
    with pytest.raises(ActionError,match='different names'):
        answer(s,ids)
    choose_search(s,['Grizzly Bears','Llanowar Elves'])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_emergent_monocolored_excludes_colorless_and_original_multicolor(cards):
    s=setup(cards)
    cast(s,'Emergent Ultimatum')
    names={s.state.cards[o.id].name for o in s.state.rules.decision.options}
    assert 'Ornithopter' not in names
    assert 'Signal the Clans' not in names
    assert 'Grizzly Bears' in names
    choose_search(s,[])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_emergent_actual_free_creatures_order_and_original_exile(cards):
    s=setup(cards)
    source=cast(s,'Emergent Ultimatum')
    found=choose_search(s,['Grizzly Bears','Llanowar Elves','Shivan Dragon'])
    answer(s,['p2'])
    answer(s,[found[0]])
    assert s.state.cards[source.id].zone=='stack'
    answer(s,[found[2]])
    # The first cast is on the stack, while the original spell is still resolving.
    assert s.state.cards[found[2]].zone=='stack'
    assert s.state.cards[source.id].zone=='stack'
    answer(s,[found[1]])
    assert s.state.cards[source.id].zone=='p1:exile'
    assert all(s.state.cards[c].zone=='p1:battlefield' for c in found[1:])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_opposition_agent_controls_find_and_diverts_emergent_packet(cards):
    from app.game.state import GameState
    s=setup(cards)
    put(s,'Opposition Agent','battlefield',pid='p2')
    source=cast(s,'Emergent Ultimatum')
    d=s.state.rules.decision
    assert d.player=='p1' and d.decider=='p2'
    found=named_options(s,['Grizzly Bears','Llanowar Elves','Shivan Dragon'])
    roundtrip(s)
    s.state=GameState.model_validate(s.state.model_dump(mode='json'))
    act(s,'p2',type='choose',decision_id=d.id,option_ids=found)
    settle(s)
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone=='p1:exile' for c in found)
    assert {p.card for p in s.state.rules.permissions if p.player=='p2'}==set(found)
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)


def test_mindcensor_limits_library_packet_to_top_four(cards):
    from tests.test_rules_refused_look import stack_library
    s=setup(cards)
    put(s,'Aven Mindcensor','battlefield',pid='p2')
    top=stack_library(s,['Ornithopter','Llanowar Elves','Grizzly Bears','Shivan Dragon'])
    cast(s,'Threats Undetected')
    assert {o.id for o in s.state.rules.decision.options}==set(top)
    choose_search(s,[])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_search_prohibition_leaves_ecological_graveyard_search_available(cards):
    s=setup(cards)
    put(s,'Stranglehold','battlefield',pid='p2')
    gy=put(s,'Grizzly Bears','graveyard')
    source=cast(s,'Ecological Appreciation',x=2)
    assert [o.id for o in s.state.rules.decision.options]==[gy.id]
    choose_search(s,['Grizzly Bears'])
    assert gy.id not in s.state.cards  # It was put into the library and shuffled.
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_ecological_clone_enters_under_original_caster_control(cards):
    from app.rules.plan import Plan
    s=setup(cards)
    dragon=put(s,'Shivan Dragon','battlefield')
    clone=put(s,'Clone','graveyard')
    source=cast(s,'Ecological Appreciation',x=4)
    found=choose_search(s,['Ornithopter','Llanowar Elves','Clone'])
    answer(s,['p3'])
    assert s.state.rules.decision.player=='p3'
    answer(s,found[:2])
    assert s.state.rules.decision.player=='p1'
    answer(s,[dragon.id])
    assert s.state.cards[clone.id].zone=='p1:battlefield'
    assert s.state.cards[clone.id].controller=='p1'
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[clone.id]).name=='Shivan Dragon'
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_emergent_zero_x_native_cast(cards):
    s=setup(cards)
    source=cast(s,'Emergent Ultimatum')
    found=choose_search(s,['Grizzly Bears','Shivan Devastator'])
    answer(s,['p2'])
    answer(s,[found[0]])
    answer(s,[found[1]])
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.cards[found[1]].zone=='p1:graveyard'  # X=0, then 0/0 SBA.
    assert not s.state.cards[found[1]].counters
    roundtrip(s)


def test_emergent_mandatory_additional_cost_not_waived(cards):
    s=setup(cards)
    source=cast(s,'Emergent Ultimatum')
    found=choose_search(s,['Llanowar Elves','Deprive','Grizzly Bears'])
    answer(s,['p2'])
    answer(s,[found[0]])
    assert {o.id for o in s.state.rules.decision.options}=={found[2]}
    answer(s,[found[2]])
    assert s.state.rules.decision is None
    assert s.state.cards[found[1]].zone=='p1:exile'
    assert s.state.cards[found[2]].zone=='p1:battlefield'
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)


def test_emergent_counterspell_can_target_resolving_original_then_fizzles(cards):
    s=setup(cards)
    source=cast(s,'Emergent Ultimatum')
    found=choose_search(s,['Grizzly Bears','Counterspell'])
    answer(s,['p2'])
    answer(s,[found[0]])
    answer(s,[found[1]])
    d=s.state.rules.decision
    assert d is not None
    assert source.id in [o.id for o in d.options]
    answer(s,[source.id])
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.cards[found[1]].zone=='p1:graveyard'
    roundtrip(s)


def test_search_private_packet_public_hand_hidden_in_rest_and_websocket(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s=setup(cards)
    cast(s,'Threats Undetected')
    found=named_options(s,['Ornithopter','Llanowar Elves','Grizzly Bears','Shivan Dragon'])
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        deck_id=client.post('/api/decks',json={'text':'Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest'}).json()['id']
        game=client.post('/api/games',json={'mode':'lan','players':[{'name':'Alice','deck_id':deck_id},{'name':'Bob','deck_id':deck_id}]}).json()
        gid=game['game']['id']
        bob=client.post('/api/join',json={'code':game['game']['code'],'name':'Bob'}).json()['token']
        spec=client.post('/api/join',json={'code':game['game']['code'],'spectate':True}).json()['token']
        client.app.state.services.hub.get(gid).game=s
        for stage in ['search','reveal','hand']:
            if stage=='reveal':
                answer(s,found)
            elif stage=='hand':
                answer(s,['p3'])
                answer(s,found[:2])
            for token in [bob,spec]:
                response=client.get(f'/api/games/{gid}/view',headers={'X-Seat-Token':token})
                assert response.status_code==200
                assert all((cid in response.text)==(stage=='reveal') for cid in found[2:])
                with client.websocket_connect(f'/ws/games/{gid}?token={token}') as ws:
                    frame=ws.receive_json()
                    assert frame['type']=='state'
                    assert all((cid in json.dumps(frame))==(stage=='reveal') for cid in found[2:])
    roundtrip(s)


def test_emergent_departed_and_returned_exile_object_is_not_castable(cards):
    from app.rules.plan import Plan
    s=setup(cards)
    source=cast(s,'Emergent Ultimatum')
    found=choose_search(s,['Grizzly Bears','Llanowar Elves'])
    answer(s,['p2'])
    answer(s,[found[0]])
    old=Plan(s.state,'p1',s.cards,None).oid(s.state.cards[found[1]])
    act(s,'p1',type='move',card_ids=[found[1]],to={'zone':'graveyard'})
    act(s,'p1',type='move',card_ids=[found[1]],to={'zone':'exile'})
    assert Plan(s.state,'p1',s.cards,None).oid(s.state.cards[found[1]])!=old
    answer(s,[found[1]])  # Native exact-ref guard treats a stale offer as no cast.
    if s.state.rules.decision is not None:
        answer(s,[])
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.cards[found[1]].zone=='p1:exile'
    assert s.state.rules.decision is None
    roundtrip(s)
