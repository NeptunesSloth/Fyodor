"""Intuition's exact unrestricted search and announced opponent's public split."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    raw=json.loads((Path(__file__).parent/'fixtures/intuition_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='int',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,names=('Island','Forest','Sol Ring')):
    all_names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/intuition_cards.json').read_text())]
    s=table(cards,[*all_names,*names],all_names,all_names)
    source=put(s,'Intuition','hand')
    for cid in list(s.state.zones['p1:library']):
        act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'exile'})
    found=[]
    for name in names:
        c=next(c for c in s.state.cards.values() if c.name==name and c.owner=='p1' and c.id not in found)
        act(s,'p1',type='move',card_ids=[c.id],to={'player':'p1','zone':'library'})
        found.append(c.id)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'U':1})
    return s,source,found


def cast(s,source,target='p3'):
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[target])
    roundtrip(s)
    settle(s)


def answer(s,ids):
    d=s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s,d.decider or d.player,type='choose',decision_id=d.id,option_ids=list(ids))
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Intuition')).level=='FULL'


def test_targeted_opponent_picks_one_publicly_revealed_card_for_hand(cards):
    s,source,found=setup(cards)
    hidden=put(s,'Gifts Ungiven','hand')
    cast(s,source)
    d=s.state.rules.decision
    assert d.player=='p1' and d.min_choices==d.max_choices==3
    assert s.view('p2')['rules']['decision']['kind']=='waiting'
    answer(s,found)
    d=s.state.rules.decision
    assert d.player=='p3' and d.min_choices==d.max_choices==1
    assert {o.card_id for o in d.options}==set(found)
    for viewer in ('p2','p3'):
        public=s.view(viewer)['cards']
        assert all(public[c]['name']==s.state.cards[c].name for c in found)
        assert hidden.id not in public
    answer(s,[found[1]])
    assert [s.state.cards[c].zone for c in found]==['p1:graveyard','p1:hand','p1:graveyard']
    assert s.state.rules.decision is None
    assert hidden.id not in s.view('p2')['cards']
    roundtrip(s)


def test_unrestricted_search_cannot_fail_to_find_and_allows_duplicate_names(cards):
    s,source,found=setup(cards,('Island','Island','Island','Forest'))
    cast(s,source)
    d=s.state.rules.decision
    assert d.min_choices==d.max_choices==3
    with pytest.raises(ActionError):
        act(s,'p1',type='choose',decision_id=d.id,option_ids=found[:2])
    answer(s,found[:3])
    answer(s,[found[0]])
    assert s.state.cards[found[0]].zone=='p1:hand'
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in found[1:3])
    assert [s.state.cards[c].name for c in s.state.zones['p1:library']]==['Forest']
    roundtrip(s)


@pytest.mark.parametrize('n',[0,1,2])
def test_short_library_requires_all_available_cards_then_one_to_hand(cards,n):
    s,source,found=setup(cards,('Island','Forest')[:n])
    cast(s,source)
    d=s.state.rules.decision
    if d is not None:
        assert d.player=='p1' and d.min_choices==d.max_choices==n
        answer(s,found)
    if n==2:
        assert s.state.rules.decision.player=='p3'
        answer(s,[found[1]])
    assert s.state.rules.decision is None
    assert sum(s.state.cards[c].zone=='p1:hand' for c in found)==min(n,1)
    assert sum(s.state.cards[c].zone=='p1:graveyard' for c in found)==max(n-1,0)
    roundtrip(s)


def test_target_is_opponent_and_player_hexproof_prevents_announcement(cards):
    s,source,_=setup(cards)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=['p1'])
    put(s,'Leyline of Sanctity','battlefield',pid='p3')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=['p3'])
    assert source.zone=='p1:hand'
    roundtrip(s)


def test_sole_target_illegal_on_resolution_does_not_search_or_shuffle(cards):
    s,source,found=setup(cards)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p3'])
    put(s,'Leyline of Sanctity','battlefield',pid='p3')
    before=len(s.history.actions)
    settle(s)
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone=='p1:library' for c in found)
    assert not any(step.get('type')=='shuffle' for a in s.history.actions[before:]
                   if isinstance(getattr(a,'r',None),list) for step in a.r)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_search_prohibition_finds_nothing_but_still_shuffles(cards):
    s,source,found=setup(cards)
    put(s,'Stranglehold','battlefield',pid='p2')
    cast(s,source)
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        assert d.min_choices==d.max_choices==0
        answer(s,[])
    assert s.state.rules.decision is None
    assert sorted(s.state.cards[c].name for c in s.state.zones['p1:library'])==['Forest','Island','Sol Ring']
    assert any(step.get('type')=='shuffle' for a in s.history.actions
               if isinstance(getattr(a,'r',None),list) for step in a.r)
    roundtrip(s)


def test_opposition_agent_controls_exact_search_and_exiles_the_found_cards(cards):
    s,source,found=setup(cards)
    put(s,'Opposition Agent','battlefield',pid='p2')
    cast(s,source)
    d=s.state.rules.decision
    assert d.player=='p1' and d.decider=='p2' and d.min_choices==d.max_choices==3
    answer(s,found)
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone=='p1:exile' for c in found)
    roundtrip(s)



def test_mindcensor_limits_exact_search_to_top_four(cards):
    s,source,found=setup(cards,('Island','Island','Island','Forest','Sol Ring'))
    put(s,'Aven Mindcensor','battlefield',pid='p2')
    top=list(s.state.zones['p1:library'])[:4]
    cast(s,source)
    d=s.state.rules.decision
    assert d.min_choices==d.max_choices==3
    assert {o.card_id for o in d.options}==set(top)
    answer(s,top[:3])
    answer(s,[top[0]])
    assert len(s.state.zones['p1:library'])==2
    roundtrip(s)
