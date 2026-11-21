"""Private library inspection preserves owner, viewer and chooser across native continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.conftest import claim_host
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import answer, settle
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/opponent_looked_choice_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Murmurs from Beyond','Animal Magnetism','Thran Tome','Karn, Scion of Urza','Phyrexian Grimoire','Guided Passage']

@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_murmurs_original_controller_hand_opponent_selection(cards):
    s=table(cards,[*NAMES,'Forest','Island','Mountain','Grizzly Bears','Shivan Dragon'],['Grizzly Bears'],[])
    to_phase(s,'main1',turn=1)
    top=stack_library(s,['Forest','Grizzly Bears','Island'])
    spell=put(s,NAMES[0],'hand')
    mana(s,U=1,C=2)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    assert s.state.rules.decision.player=='p1'  # Choose the opponent, not a target.
    answer(s,['p3'])
    assert s.state.rules.decision.player=='p3'
    answer(s,[top[1]])
    assert s.state.cards[top[1]].zone=='p1:graveyard'
    assert all(s.state.cards[c].zone=='p1:hand' for c in [top[0],top[2]])
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('creature',[True,False])
def test_animal_original_controller_not_selector_gets_permanent(cards,creature):
    s=table(cards,[*NAMES,'Forest','Island','Mountain','Grizzly Bears','Shivan Dragon'],[],[])
    to_phase(s,'main1',turn=1)
    top=stack_library(s,['Grizzly Bears' if creature else 'Forest','Shivan Dragon' if creature else 'Forest','Island','Mountain','Forest'])
    spell=put(s,'Animal Magnetism','hand')
    mana(s,G=1,C=4)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    answer(s,['p2'])
    if creature:
        assert s.state.rules.decision.player=='p2'
        answer(s,[top[0]])
        assert s.state.cards[top[0]].zone=='p1:battlefield'
        assert s.state.cards[top[0]].controller=='p1'
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in top[1:])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_thran_choice_then_actual_two_draws(cards):
    s=table(cards,[*NAMES,'Forest','Island','Mountain','Grizzly Bears','Shivan Dragon'],[],[])
    to_phase(s,'main1',turn=1)
    top=stack_library(s,['Forest','Grizzly Bears','Island'])
    tome=put(s,'Thran Tome','battlefield')
    before_draws=s.state.rules.draws_this_turn.get('p1',0)
    mana(s,C=5)
    act(s,'p1',type='activate_ability',card_id=tome.id,ability=0,targets=['p2'])
    settle(s)
    assert s.state.rules.decision.player=='p2'
    answer(s,[top[1]])
    assert s.state.cards[top[1]].zone=='p1:graveyard'
    assert all(s.state.cards[c].zone=='p1:hand' for c in [top[0],top[2]])
    assert s.state.rules.draws_this_turn.get('p1') == before_draws + 2
    roundtrip(s)


def test_karn_silver_exile_then_recover_with_another_karn(cards):
    s=table(cards,[*NAMES,'Grizzly Bears','Island'],[],[])
    to_phase(s,'main1',turn=1)
    top=stack_library(s,['Grizzly Bears','Island'])
    karn=put(s,'Karn, Scion of Urza','hand')
    mana(s,C=4)
    act(s,'p1',type='cast_spell',card_id=karn.id)
    settle(s)
    act(s,'p1',type='activate_ability',card_id=karn.id,ability=0)
    settle(s)
    answer(s,['p2'])
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:hand'
    assert s.state.cards[top[1]].zone=='p1:exile'
    assert s.state.cards[top[1]].counters.get('silver')==1
    # A new incarnation of Karn has no link to the previous source; only ownership/counter matter.
    act(s,'p1',type='move',card_ids=[karn.id],to={'zone':'graveyard'})
    act(s,'p1',type='move',card_ids=[karn.id],to={'zone':'hand'})
    mana(s,C=4)
    act(s,'p1',type='cast_spell',card_id=karn.id)
    settle(s)
    act(s,'p1',type='activate_ability',card_id=karn.id,ability=1)
    settle(s)
    if s.state.rules.decision is not None:
        answer(s,[top[1]])
    assert s.state.cards[top[1]].zone=='p1:hand'
    assert not s.state.cards[top[1]].counters
    roundtrip(s)


def test_grimoire_top_two_exile_other_to_hand(cards):
    s=table(cards,[*NAMES,'Grizzly Bears','Island','Mountain'],[],[])
    to_phase(s,'main1',turn=1)
    bottom=put(s,'Mountain','graveyard')
    other=put(s,'Island','graveyard')
    top=put(s,'Grizzly Bears','graveyard')
    book=put(s,'Phyrexian Grimoire','battlefield')
    mana(s,C=4)
    act(s,'p1',type='activate_ability',card_id=book.id,ability=0,targets=['p2'])
    settle(s)
    d=s.state.rules.decision
    assert d.player=='p2'
    assert {o.id for o in d.options}=={top.id,other.id}
    answer(s,[top.id])
    assert s.state.cards[top.id].zone=='p1:exile'
    assert s.state.cards[other.id].zone=='p1:hand'
    assert s.state.cards[bottom.id].zone=='p1:graveyard'
    roundtrip(s)


def test_guided_passage_opponent_picks_each_disjoint_category(cards):
    s=table(cards,[*NAMES,'Grizzly Bears','Shivan Dragon','Island','Mountain'],[],[])
    to_phase(s,'main1',turn=1)
    spell=put(s,'Guided Passage','hand')
    mana(s,U=1,R=1,G=1)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    answer(s,['p3'])
    selected=[]
    for name in ['Grizzly Bears','Island','Thran Tome']:
        d=s.state.rules.decision
        assert d is not None and d.player=='p3'
        cid=next(o.id for o in d.options if s.state.cards[o.id].name==name)
        selected.append(cid)
        answer(s,[cid])
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone=='p1:hand' for c in selected)
    assert len([e for e in s.state.rules.events if e.kind=='library_shuffled' and not e.manual])==1
    assert all(not c.revealed_to for c in s.state.cards.values() if c.zone=='p1:library')
    roundtrip(s)


def test_thran_actual_draw_prohibition_hides_remaining_revealed_cards(cards):
    s=table(cards,[*NAMES,'Spirit of the Labyrinth','Grizzly Bears','Island'],[],[])
    to_phase(s,'main1',turn=1)  # The normal turn draw has already occurred.
    put(s,'Spirit of the Labyrinth','battlefield')
    top=stack_library(s,['Forest','Grizzly Bears','Island'])
    tome=put(s,'Thran Tome','battlefield')
    count=s.state.rules.draws_this_turn.get('p1',0)
    mana(s,C=5)
    act(s,'p1',type='activate_ability',card_id=tome.id,ability=0,targets=['p2'])
    settle(s)
    answer(s,[top[1]])
    assert s.state.cards[top[1]].zone=='p1:graveyard'
    assert s.state.zones['p1:library'][:2]==[top[0],top[2]]
    assert all(not s.state.cards[c].revealed_to for c in [top[0],top[2]])
    assert s.state.rules.draws_this_turn.get('p1',0)==count
    assert not any(c in json.dumps(s.view('p3')['cards']) for c in [top[0],top[2]])
    roundtrip(s)


@pytest.mark.parametrize('n',[0,1])
def test_grimoire_short_graveyard(cards,n):
    s=table(cards,[*NAMES,'Grizzly Bears'],[],[])
    to_phase(s,'main1',turn=1)
    card_=put(s,'Grizzly Bears','graveyard') if n else None
    book=put(s,'Phyrexian Grimoire','battlefield')
    mana(s,C=4)
    act(s,'p1',type='activate_ability',card_id=book.id,ability=0,targets=['p2'])
    settle(s)
    if n:
        assert s.state.rules.decision.player=='p2'
        answer(s,[card_.id])
        assert s.state.cards[card_.id].zone=='p1:exile'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_murmurs_graveyard_replacement_still_puts_rest_in_hand(cards):
    s=table(cards,[*NAMES,'Rest in Peace','Grizzly Bears','Island'],[],[])
    to_phase(s,'main1',turn=1)
    put(s,'Rest in Peace','battlefield')
    settle(s)
    top=stack_library(s,['Forest','Grizzly Bears','Island'])
    spell=put(s,'Murmurs from Beyond','hand')
    mana(s,U=1,C=2)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    answer(s,['p2'])
    answer(s,[top[1]])
    assert s.state.cards[top[1]].zone=='p1:exile'
    assert all(s.state.cards[c].zone=='p1:hand' for c in [top[0],top[2]])
    roundtrip(s)


def test_thran_source_destroyed_before_opponent_selects(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s=table(cards,[*NAMES,'Grizzly Bears','Island'],['Disenchant'],[])
    to_phase(s,'main1',turn=1)
    top=stack_library(s,['Forest','Grizzly Bears','Island'])
    tome=put(s,'Thran Tome','battlefield')
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,C=5)
    act(s,'p1',type='activate_ability',card_id=tome.id,ability=0,targets=['p2'])
    wait_priority(s,'p2')
    response=put(s,'Disenchant','hand',pid='p2')
    mana(s,pid='p2',W=1,C=1)
    act(s,'p2',type='cast_spell',card_id=response.id,targets=[tome.id])
    settle(s)
    assert s.state.cards[tome.id].zone=='p1:graveyard'
    assert s.state.rules.decision.player=='p2'
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:graveyard'
    assert all(s.state.cards[c].zone=='p1:hand' for c in top[1:])
    roundtrip(s)


def test_animal_nested_entry_copy_choice_is_original_controller(cards):
    from app.rules.plan import Plan
    s=table(cards,[*NAMES,'Clone','Grizzly Bears','Island','Mountain','Shivan Dragon'],[],[])
    to_phase(s,'main1',turn=1)
    dragon=put(s,'Shivan Dragon','battlefield')
    top=stack_library(s,['Clone','Grizzly Bears','Forest','Island','Mountain'])
    spell=put(s,'Animal Magnetism','hand')
    mana(s,C=4,G=1)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    answer(s,['p3'])
    assert s.state.rules.decision.player=='p3'
    answer(s,[top[0]])
    assert s.state.rules.decision.player=='p1'
    answer(s,[dragon.id])
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    assert s.state.cards[top[0]].controller=='p1'
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[top[0]]).name=='Shivan Dragon'
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in top[1:])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_karn_negative_ability_checks_current_controllers_card_ownership(cards):
    s=table(cards,[*NAMES,'Grizzly Bears','Island'],['Mountain'],[])
    to_phase(s,'main1',turn=1)
    top=stack_library(s,['Grizzly Bears','Island'])
    karn=put(s,'Karn, Scion of Urza','hand')
    mana(s,C=4)
    act(s,'p1',type='cast_spell',card_id=karn.id)
    settle(s)
    act(s,'p1',type='activate_ability',card_id=karn.id,ability=0)
    settle(s)
    answer(s,['p2'])
    answer(s,[top[0]])
    assert s.state.cards[top[1]].counters.get('silver')==1
    other=put(s,'Mountain','exile',pid='p2')
    act(s,'p2',type='counter',card_ids=[other.id],kind='silver',delta=1)
    act(s,'p1',type='set_controller',card_ids=[karn.id],player='p2')
    to_phase(s,'main1',turn=2)
    act(s,'p2',type='activate_ability',card_id=karn.id,ability=1)
    settle(s)
    d=s.state.rules.decision
    if d is not None:
        assert d.player=='p2'
        assert [o.id for o in d.options]==[other.id]
        answer(s,[other.id])
    assert s.state.cards[other.id].zone=='p2:hand'
    assert s.state.cards[top[1]].zone=='p1:exile'
    roundtrip(s)


def test_karn_construct_loyalty_ability_native(cards):
    from app.rules.plan import Plan
    s=table(cards,NAMES,[],[])
    to_phase(s,'main1',turn=1)
    put(s,'Thran Tome','battlefield')
    karn=put(s,'Karn, Scion of Urza','hand')
    mana(s,C=4)
    act(s,'p1',type='cast_spell',card_id=karn.id)
    settle(s)
    act(s,'p1',type='activate_ability',card_id=karn.id,ability=2)
    settle(s)
    token=next(c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield')
    assert Plan(s.state,'p1',s.cards,None).ch(token).pt==(2,2)
    assert s.state.cards[karn.id].counters['loyalty']==3
    roundtrip(s)


def test_public_reveal_then_hidden_hand_rest_and_websocket(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s=table(cards,[*NAMES,'Island','Grizzly Bears'],[],[])
    to_phase(s,'main1',turn=1)
    top=stack_library(s,['Forest','Grizzly Bears','Island'])
    spell=put(s,'Murmurs from Beyond','hand')
    mana(s,C=2,U=1)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    answer(s,['p2'])
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        deck_id=client.post('/api/decks',json={'text':'Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest'}).json()['id']
        game=client.post('/api/games',json={'mode':'lan','players':[{'name':'Alice','deck_id':deck_id},{'name':'Bob','deck_id':deck_id}]}).json()
        gid=game['game']['id']
        bob=client.post('/api/join',json={'code':game['game']['code'],'name':'Bob'}).json()['token']
        spec=client.post('/api/join',json={'code':game['game']['code'],'spectate':True}).json()['token']
        client.app.state.services.hub.get(gid).game=s
        for hidden in [False,True]:
            if hidden:
                answer(s,[top[0]])
            for token in [bob,spec]:
                response=client.get(f'/api/games/{gid}/view',headers={'X-Seat-Token':token})
                assert response.status_code==200
                for cid in top[1:]:
                    assert (cid not in response.text) if hidden else (cid in response.text)
                with client.websocket_connect(f'/ws/games/{gid}?token={token}') as ws:
                    frame=ws.receive_json()
                    assert frame['type']=='state'
                    for cid in top[1:]:
                        assert (cid not in json.dumps(frame)) if hidden else (cid in json.dumps(frame))
    roundtrip(s)


def test_guided_passage_missing_creature_and_nonland_categories(cards):
    from tests.test_rules_refused_look import thin_library
    s=table(cards,[*NAMES,'Island'],[],[])
    to_phase(s,'main1',turn=1)
    spell=put(s,'Guided Passage','hand')
    top=thin_library(s,['Island','Forest'])
    mana(s,U=1,R=1,G=1)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    answer(s,['p2'])
    assert s.state.rules.decision.player=='p2'
    assert {o.id for o in s.state.rules.decision.options}==set(top)
    picked=next(c for c in top if s.state.cards[c].name=='Island')
    answer(s,[picked])
    assert s.state.cards[picked].zone=='p1:hand'
    assert len(s.state.zones['p1:library'])==1
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('count',[0,1])
def test_murmurs_short_library_does_not_require_unavailable_cards(cards,count):
    from tests.test_rules_refused_look import thin_library
    s=table(cards,NAMES,[],[])
    to_phase(s,'main1',turn=1)
    spell=put(s,'Murmurs from Beyond','hand')
    top=thin_library(s,['Forest'] if count else [])
    mana(s,U=1,C=2)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    answer(s,['p2'])
    if count:
        answer(s,top)
        assert s.state.cards[top[0]].zone=='p1:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)
