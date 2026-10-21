"""CR 603.4, 608.2c/d/h: optional catch-up searches recheck live land counts."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME='Claim Jumper'


@pytest.fixture()
def cards(settings):
    raw=json.loads((Path(__file__).parent/'fixtures/claim_jumper_cards.json').read_text())
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='cjr',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,counts=(1,2,3)):
    names=[NAME,'Plains','Plains','Mistveil Plains','Ashiok, Dream Render','Aven Mindcensor','Panharmonicon','Grizzly Bears']
    s=table(cards,names,names,[])
    for pid,n in zip(('p1','p2','p3'),counts,strict=True):
        name='Forest' if pid=='p1' else 'Island'
        ids=[c.id for c in s.state.cards.values() if c.owner==pid and c.name==name and c.zone.endswith(':library')][:n]
        assert len(ids)==n
        if ids:
            act(s,pid,type='move',card_ids=ids,to={'player':pid,'zone':'battlefield'})
    return s


def cast(s):
    source=put(s,NAME,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'W':1})
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    return source


def answer(s,ids):
    d=s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
    settle(s)


def confirm(s,yes):
    d=s.state.rules.decision
    assert d is not None and d.kind=='confirm'
    answer(s,['yes' if yes else 'no'])


def find(s,name='Plains'):
    d=s.state.rules.decision
    assert d is not None and d.kind=='choose_cards'
    option=next(o for o in d.options if o.card_id and s.state.cards[o.card_id].name==name)
    cid=option.card_id
    answer(s,[option.id])
    return cid


def shuffles(s):
    return [step for a in s.history.actions if isinstance(getattr(a,'r',None),list)
            for step in a.r if step.get('type')=='shuffle' and step.get('player')=='p1']


def lands(s,pid='p1'):
    return [c for c in s.state.cards.values() if c.controller==pid and c.zone.endswith(':battlefield')
            and s.cards.get(c.card_id)['type_line'].startswith(('Land','Basic Land','Snow Land','Basic Snow Land'))]


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


def test_two_searches_recheck_against_different_opponents_and_shuffle_once(cards):
    s=setup(cards)
    cast(s)
    confirm(s,True)
    first=find(s)
    assert s.state.cards[first].tapped and len(lands(s))==2 and not shuffles(s)
    confirm(s,True)
    second=find(s,'Mistveil Plains')
    assert s.state.cards[second].tapped and len(lands(s))==3
    assert s.state.rules.decision is None and len(shuffles(s))==1
    roundtrip(s)


def test_first_land_catches_up_and_skips_second_search(cards):
    s=setup(cards,(1,2,0))
    cast(s)
    confirm(s,True)
    find(s)
    assert len(lands(s))==2 and s.state.rules.decision is None and len(shuffles(s))==1
    roundtrip(s)


def test_decline_first_then_accept_second_search(cards):
    s=setup(cards,(1,2,0))
    cast(s)
    confirm(s,False)
    assert not shuffles(s)
    confirm(s,True)
    find(s)
    assert len(lands(s))==2 and len(shuffles(s))==1
    roundtrip(s)


def test_declining_both_searches_does_not_shuffle(cards):
    s=setup(cards)
    before=list(s.state.zones['p1:library'])
    cast(s)
    confirm(s,False)
    confirm(s,False)
    assert s.state.zones['p1:library']==before and not shuffles(s)
    roundtrip(s)


def test_failed_find_still_counts_as_search_and_shuffles_once(cards):
    s=setup(cards)
    cast(s)
    confirm(s,True)
    answer(s,[])
    confirm(s,True)
    answer(s,[])
    assert len(lands(s))==1 and len(shuffles(s))==1
    roundtrip(s)


def test_search_then_decline_second_still_shuffles_once(cards):
    s=setup(cards)
    cast(s)
    confirm(s,True)
    find(s)
    assert not shuffles(s)
    confirm(s,False)
    assert len(lands(s))==2 and len(shuffles(s))==1
    roundtrip(s)


@pytest.mark.parametrize('counts',[(1,1,0),(2,1,1)])
def test_intervening_if_false_at_entry_does_not_trigger(cards,counts):
    s=setup(cards,counts)
    cast(s)
    assert s.state.rules.decision is None and not s.state.zones.get('stack') and not shuffles(s)
    roundtrip(s)


def test_intervening_if_rechecked_before_resolution(cards):
    s=setup(cards,(1,2,0))
    source=put(s,NAME,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'W':1})
    act(s,'p1',type='cast_spell',card_id=source.id)
    # Resolve the creature, but leave its ETB trigger above the next priority pass.
    for _ in range(3):
        act(s,s.state.rules.priority,type='pass_priority')
        if s.state.cards[source.id].zone=='p1:battlefield':
            break
    assert s.state.cards[source.id].zone=='p1:battlefield'
    enemy=[c.id for c in lands(s,'p2')]
    act(s,'p2',type='move',card_ids=enemy,to={'player':'p2','zone':'graveyard'})
    settle(s)
    assert s.state.rules.decision is None and not shuffles(s)
    roundtrip(s)


def test_search_prohibition_skips_both_searches_and_does_not_shuffle(cards):
    s=setup(cards)
    ashiok=put(s,'Ashiok, Dream Render','battlefield',pid='p2')
    act(s,'p2',type='set_counter',card_id=ashiok.id,kind='loyalty',value=5)
    before=list(s.state.zones['p1:library'])
    cast(s)
    assert s.state.rules.decision is None and len(lands(s))==1
    assert s.state.zones['p1:library']==before and not shuffles(s)
    roundtrip(s)


def test_repeat_is_bounded_to_once_even_when_still_far_behind(cards):
    s=setup(cards,(1,6,0))
    cast(s)
    confirm(s,True)
    find(s)
    confirm(s,True)
    find(s)
    assert len(lands(s))==3 and len(lands(s,'p2'))==6
    assert s.state.rules.decision is None and len(shuffles(s))==1
    roundtrip(s)


def test_source_departure_after_trigger_does_not_cancel_search_process(cards):
    s=setup(cards,(1,2,0))
    source=cast(s)
    confirm(s,True)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    find(s,'Mistveil Plains')
    assert len(lands(s))==2 and len(shuffles(s))==1
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_actual_search_cannot_find_non_plains_land(cards):
    from app.game.errors import ActionError

    s=setup(cards,(1,2,0))
    cast(s)
    confirm(s,True)
    d=s.state.rules.decision
    assert d is not None
    forest=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Forest' and c.zone=='p1:library')
    assert forest.id not in {o.id for o in d.options}
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='choose',decision_id=d.id,option_ids=[forest.id])
    assert s.state.model_dump(mode='json')==before
    find(s)
    assert len(shuffles(s))==1
    roundtrip(s)
