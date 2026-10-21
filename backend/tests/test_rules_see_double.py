"""See Double collateral: conditional mode selection is locked at announcement."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    raw=json.loads((Path(__file__).parent/'fixtures/see_double_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='see',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME='See Double'


def setup(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/see_double_cards.json').read_text())]
    names += ['Forest']*8
    s=table(cards,names,names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    return s


def graveyard(s,pid,n):
    for c in [c for c in s.state.cards.values() if c.owner==pid and c.name=='Forest'][:n]:
        act(s,pid,type='move',card_ids=[c.id],to={'player':pid,'zone':'graveyard'})


def bolt(s):
    source=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p3'])
    return source


def cast(s,modes,targets):
    wait_priority(s,'p1')
    source=put(s,NAME,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'U':2})
    act(s,'p1',type='cast_spell',card_id=source.id,modes=modes,targets=targets,
        **({'target_counts':[1,1]} if len(modes)==2 else {}))
    roundtrip(s)
    return source


def finish_copy(s,target='keep'):
    settle(s)
    d=s.state.rules.decision
    if d is not None:
        assert d.resume['step']=='copy_target'
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[target])


def copies(s):
    return [c for c in s.state.cards.values() if c.is_token and c.zone=='stack' and c.ability is None]


def bears(s):
    return [c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield' and c.name=='Grizzly Bears']


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


@pytest.mark.parametrize(('p1','p2','p3','allowed'),[(8,7,0,False),(0,8,0,True),(0,0,8,True),(0,4,4,False)])
def test_choose_both_requires_one_opponent_graveyard_with_eight(cards,p1,p2,p3,allowed):
    s=setup(cards)
    for pid,n in [('p1',p1),('p2',p2),('p3',p3)]:
        graveyard(s,pid,n)
    target=bolt(s)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    if not allowed:
        with pytest.raises(ActionError):
            cast(s,[0,1],[target.id,bear.id])
        assert not copies(s) and not bears(s)
    else:
        cast(s,[0,1],[target.id,bear.id])
        finish_copy(s)
        assert len(copies(s))==len(bears(s))==1
        assert s.state.rules.stack[copies(s)[0].id].targets[0].id=='p3'
    roundtrip(s)


def test_mode_one_native_spell_copy_retargets_without_changing_original(cards):
    s=setup(cards)
    target=bolt(s)
    cast(s,[0],[target.id])
    finish_copy(s,'p2')
    made=copies(s)
    assert len(made)==1 and s.state.rules.stack[made[0].id].targets[0].id=='p2'
    assert s.state.rules.stack[target.id].targets[0].id=='p3'
    assert not bears(s)
    roundtrip(s)


def test_mode_two_copies_opponent_creature_without_needing_a_spell(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,[1],[bear.id])
    settle(s)
    assert len(bears(s))==1 and not copies(s)
    assert s.state.cards[bear.id].controller=='p2'
    roundtrip(s)


def test_both_is_optional_even_when_opponent_has_eight(cards):
    s=setup(cards)
    graveyard(s,'p2',8)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,[1],[bear.id])
    settle(s)
    assert len(bears(s))==1 and not copies(s)
    roundtrip(s)


def test_announced_both_remains_both_after_crypt_empties_opponent_graveyard(cards):
    s=setup(cards)
    graveyard(s,'p2',8)
    target=bolt(s)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    crypt=put(s,"Tormod's Crypt",'battlefield',pid='p2')
    cast(s,[0,1],[target.id,bear.id])
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=crypt.id,ability=0,targets=['p2'])
    finish_copy(s)
    assert s.state.cards[crypt.id].zone=='p2:exile'  # it was sacrificed before the graveyard was exiled
    assert not s.state.zones['p2:graveyard']
    assert len(copies(s))==len(bears(s))==1
    roundtrip(s)


def test_see_double_cannot_itself_be_copied_on_stack(cards):
    from app.rules.copying import uncopyable
    from app.rules.plan import Plan

    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    source=cast(s,[1],[bear.id])
    assert uncopyable(Plan(s.state,'p1',s.cards,None),s.state.cards[source.id])==''
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    assert uncopyable(Plan(s.state,'p1',s.cards,None),s.state.cards[source.id]) is None
    roundtrip(s)


def test_mode_one_copies_permanent_spell_as_token_on_resolution(cards):
    s=setup(cards)
    ring=put(s,'Sol Ring','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    act(s,'p1',type='cast_spell',card_id=ring.id)
    cast(s,[0],[ring.id])
    settle(s)
    rings=[c for c in s.state.cards.values() if c.name=='Sol Ring' and c.zone=='p1:battlefield']
    assert len(rings)==2 and sum(c.is_token for c in rings)==1
    roundtrip(s)
