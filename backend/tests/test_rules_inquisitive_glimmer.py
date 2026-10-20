"""Unlock reductions apply to the special action without borrowing other cost modifiers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, rooms
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME='Inquisitive Glimmer'
ROOM='Grand Entryway // Elegant Rotunda'

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    raw=json.loads((Path(__file__).parent/'fixtures/inquisitive_glimmer_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='igc',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,n=1,extras=()):
    s=table(cards,[NAME]*max(3,n)+[ROOM,'Training Grounds','Starfield Mystic','Dress Down','Disenchant','Sol Ring','Payment Test Spring','Abundance','Forest'],[],[])
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    sources=[c for c in s.state.cards.values() if c.owner=='p1' and c.name==NAME][:n]
    if sources:
        act(s,'p1',type='move',card_ids=[c.id for c in sources],to={'player':'p1','zone':'battlefield'})
    for name in extras:
        put(s,name,'battlefield')
    room=put(s,ROOM,'battlefield')
    assert not rooms.doors_of(Plan(s.state,'p1',s.cards,None),room.id)
    return s,sources,room


def doors(s,room):
    return rooms.doors_of(Plan(s.state,'p1',s.cards,None),room.id)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


@pytest.mark.parametrize('n',[0,1,2,3])
def test_stacking_reduces_only_generic_and_unlocks_via_native_designation(cards,n):
    s,_,room=setup(cards,n)
    generic=max(0,2-n)
    act(s,'p1',type='add_mana',player='p1',mana={'C':generic,'W':1})
    act(s,'p1',type='unlock_door',card_id=room.id,door=2,sources=[])
    assert doors(s,room)==[2]
    assert sum(mana_pool(s,'p1').values())==0
    roundtrip(s)


def test_colored_mana_is_never_removed_even_after_generic_reaches_zero(cards):
    s,_,room=setup(cards,3)
    act(s,'p1',type='add_mana',player='p1',mana={'C':4})
    with pytest.raises(ActionError):
        act(s,'p1',type='unlock_door',card_id=room.id,door=1,sources=[])
    assert doors(s,room)==[] and mana_pool(s,'p1')['C']==4
    roundtrip(s)


@pytest.mark.parametrize('change',['leave','opponent','abilities'])
def test_reduction_tracks_live_controller_and_abilities(cards,change):
    s,sources,room=setup(cards)
    source=sources[0]
    if change=='leave':
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    elif change=='opponent':
        act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    else:
        put(s,'Dress Down','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'W':1})
    with pytest.raises(ActionError):
        act(s,'p1',type='unlock_door',card_id=room.id,door=1,sources=[])
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    act(s,'p1',type='unlock_door',card_id=room.id,door=1,sources=[])
    assert doors(s,room)==[1]
    roundtrip(s)


def test_spell_and_activated_reductions_do_not_apply_to_unlock(cards):
    s,_,room=setup(cards,0,extras=['Starfield Mystic','Training Grounds'])
    act(s,'p1',type='add_mana',player='p1',mana={'W':1})
    with pytest.raises(ActionError):
        act(s,'p1',type='unlock_door',card_id=room.id,door=1,sources=[])
    assert doors(s,room)==[]
    roundtrip(s)


def test_same_glimmer_reduces_actual_room_cast_and_later_unlock_once_each(cards):
    s,_,room=setup(cards)
    act(s,'p1',type='move',card_ids=[room.id],to={'player':'p1','zone':'hand'})
    act(s,'p1',type='add_mana',player='p1',mana={'W':1})
    act(s,'p1',type='cast_spell',card_id=room.id,face=0,sources=[])
    settle(s)
    assert doors(s,room)==[1]
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    act(s,'p1',type='unlock_door',card_id=room.id,door=2,sources=[])
    assert doors(s,room)==[1,2]
    assert sum(mana_pool(s,'p1').values())==0
    roundtrip(s)


@pytest.mark.parametrize('replace_draw',[False,True])
def test_reduced_unlock_keeps_native_paused_payment_terminal_exactly_once(cards,monkeypatch,replace_draw):
    from tests.payment_rider_injection import inject_mana_draw_rider
    from tests.test_rules_external_payment_continuations import paused_draw

    # Legal mana Oracle; the structured draw rider is deliberately injected below classification.
    inject_mana_draw_rider(monkeypatch, {'Payment Test Spring'})
    s,_,room=setup(cards)
    source=put(s,'Payment Test Spring','battlefield')
    put(s,'Abundance','battlefield')
    act(s,'p1',type='unlock_door',card_id=room.id,door=1)
    assert doors(s,room)==[] and s.state.cards[source.id].tapped
    paused_draw(s,replace_draw=replace_draw)
    settle(s)
    assert doors(s,room)==[1]
    assert len([c for c in s.state.cards.values() if c.is_token and c.name=='Glimmer'])==1
    roundtrip(s)
