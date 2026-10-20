"""Wild Magic Surge snapshots types and preserves native reveal/entry continuations."""
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
    raw=json.loads((Path(__file__).parent/'fixtures/destroy_type_reveal_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='dtr',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/destroy_type_reveal_cards.json').read_text())]
    return table(cards,names,names,names)


def library(s,names,pid='p2'):
    for cid in list(s.state.zones[pid+':library']):
        act(s,pid,type='move',card_ids=[cid],to={'player':pid,'zone':'exile'})
    found=[]
    for name in names:
        c=next(c for c in s.state.cards.values() if c.name==name and c.owner==pid and c.id not in found)
        act(s,pid,type='move',card_ids=[c.id],to={'player':pid,'zone':'library'},position='bottom')
        found.append(c.id)
    return found


def cast(s,target):
    source=put(s,'Wild Magic Surge','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'R':2})
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[target.id])
    roundtrip(s)
    settle(s)
    return source


def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Wild Magic Surge')).level=='FULL'


@pytest.mark.parametrize(('target_name','top','match'),[
    ('Grizzly Bears',['Lightning Bolt','Sol Ring','Ornithopter','Forest'],2),
    ('Sol Ring',['Lightning Bolt','Grizzly Bears','Ornithopter','Forest'],2),
    ('Ornithopter',['Lightning Bolt','Grizzly Bears','Sol Ring','Forest'],1),
    ('Darksteel Ingot',['Lightning Bolt','Grizzly Bears','Sol Ring','Forest'],2),
])
def test_snapshot_types_even_when_indestructible_and_any_shared_type(cards,target_name,top,match):
    s=setup(cards)
    target=put(s,target_name,'battlefield',pid='p2')
    found=library(s,top)
    objects={cid:s.state.rules.object_id(cid) for cid in found}
    cast(s,target)
    assert s.state.cards[target.id].zone==('p2:battlefield' if target_name=='Darksteel Ingot' else 'p2:graveyard')
    assert s.state.cards[found[match]].zone=='p2:battlefield'
    assert s.state.rules.decision is None
    remaining=[s.state.cards[c].name for c in s.state.zones['p2:library']]
    assert remaining[:len(top)-match-1]==top[match+1:]
    assert sorted(remaining[len(top)-match-1:])==sorted(top[:match])
    assert len(remaining)==len(top)-1
    assert all(s.state.rules.object_id(cid)==objects[cid] for cid in found if cid!=found[match])
    assert not s.view('p1')['zones']['p2:library']['known']
    roundtrip(s)


@pytest.mark.parametrize('top',[[],['Lightning Bolt','Counterspell']])
def test_no_matching_card_randomly_bottoms_all_revealed_without_draw_or_shuffle(cards,top):
    s=setup(cards)
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    library(s,top)
    before=s.state.rules.turn_log.drew.get('p2',0)
    cast(s,target)
    assert sorted(s.state.cards[c].name for c in s.state.zones['p2:library'])==sorted(top)
    assert s.state.rules.turn_log.drew.get('p2',0)==before
    assert not any(step.get('type')=='shuffle' for a in s.history.actions
                   if isinstance(getattr(a,'r',None),list) for step in a.r)
    assert s.state.rules.decision is None
    assert not s.view('p1')['zones']['p2:library']['known']
    roundtrip(s)


def test_target_own_permanent_is_illegal(cards):
    s=setup(cards)
    target=put(s,'Sol Ring','battlefield')
    with pytest.raises(ActionError):
        cast(s,target)
    roundtrip(s)


def test_entry_choice_pauses_before_random_bottom_and_publicly_reveals_only_prefix(cards):
    s=setup(cards)
    target=put(s,'Sol Ring','battlefield',pid='p2')
    found=library(s,['Lightning Bolt','Phyrexian Revoker','Forest'])
    cast(s,target)
    d=s.state.rules.decision
    assert d is not None and d.player=='p2'
    assert s.state.cards[found[1]].zone=='p2:library'
    public=s.view('p3')['cards']
    assert all(c in public for c in found[:2]) and found[2] not in public
    roundtrip(s)
    act(s,'p2',type='choose',decision_id=d.id,name='Sol Ring')
    settle(s)
    assert s.state.cards[found[1]].zone=='p2:battlefield'
    assert [s.state.cards[c].name for c in s.state.zones['p2:library']]==['Forest','Lightning Bolt']
    assert not s.view('p3')['zones']['p2:library']['known']
    roundtrip(s)


def test_kindred_shares_card_type_but_kindred_sorcery_is_not_permanent(cards):
    s=setup(cards)
    target=put(s,'Bitterblossom','battlefield',pid='p2')
    found=library(s,['All Is Dust','Thornbite Staff','Abundant Growth'])
    cast(s,target)
    assert s.state.cards[found[1]].zone=='p2:battlefield'
    assert [s.state.cards[c].name for c in s.state.zones['p2:library']]==['Abundant Growth','All Is Dust']
    roundtrip(s)


def test_token_target_types_survive_disappearance(cards):
    s=setup(cards)
    old=set(s.state.cards)
    act(s,'p2',type='create_token',player='p2',token={'name':'Test creature token','type_line':'Token Creature — Soldier','power':'2','toughness':'2','text':''})
    target=next(c for cid,c in s.state.cards.items() if cid not in old)
    found=library(s,['Sol Ring','Grizzly Bears','Forest'])
    cast(s,target)
    assert target.id not in s.state.cards
    assert s.state.cards[found[1]].zone=='p2:battlefield'
    roundtrip(s)


def test_uses_last_controller_library_instead_of_owner(cards):
    s=setup(cards)
    target=put(s,'Sol Ring','battlefield',pid='p1')
    act(s,'p1',type='set_controller',card_ids=[target.id],player='p2')
    found=library(s,['Lightning Bolt','Ornithopter','Forest'])
    cast(s,target)
    assert s.state.cards[target.id].zone=='p1:graveyard'
    assert s.state.cards[found[1]].zone=='p2:battlefield'
    roundtrip(s)


def test_cage_blocked_found_card_stays_above_randomly_bottomed_rest(cards):
    s=setup(cards)
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    put(s,"Grafdigger's Cage",'battlefield')
    library(s,['Lightning Bolt','Ornithopter','Forest'])
    cast(s,target)
    assert [s.state.cards[c].name for c in s.state.zones['p2:library']]==['Ornithopter','Forest','Lightning Bolt']
    roundtrip(s)


def test_snapshot_uses_live_added_card_types_before_destruction(cards):
    s=setup(cards)
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    coating=put(s,'Liquimetal Coating','battlefield')
    act(s,'p1',type='activate_ability',card_id=coating.id,ability=0,targets=[target.id])
    settle(s)
    found=library(s,['Sol Ring','Ornithopter','Forest'])
    cast(s,target)
    assert s.state.cards[found[0]].zone=='p2:battlefield'
    roundtrip(s)


def test_illegal_target_on_resolution_never_reveals_or_reorders_library(cards):
    s=setup(cards)
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    found=library(s,['Lightning Bolt','Sol Ring','Ornithopter'])
    spell=put(s,'Wild Magic Surge','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'R':2})
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[target.id])
    act(s,'p2',type='move',card_ids=[target.id],to={'player':'p2','zone':'graveyard'})
    settle(s)
    assert s.state.zones['p2:library']==found
    assert not s.view('p1')['zones']['p2:library']['known']
    roundtrip(s)
