"""Display of Power: arbitrary spell-copy order and native retarget continuations."""
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
    raw=json.loads((Path(__file__).parent/'fixtures/display_of_power_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='dop',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAME='Display of Power'


def setup(cards,staff=False):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/display_of_power_cards.json').read_text())]
    s=table(cards,[*names,NAME],names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    if staff:
        put(s,'Twinning Staff','battlefield')
    return s


def cast(s,name,pid='p1',targets=()):
    wait_priority(s,pid)
    source=next(c for c in s.state.cards.values() if c.name==name and c.owner==pid and c.zone!='stack')
    act(s,pid,type='move',card_ids=[source.id],to={'player':pid,'zone':'hand'})
    act(s,pid,type='add_mana',player=pid,mana={'R':5,'U':2,'C':3})
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),**({'target_counts':[len(targets)]} if name==NAME else {}))
    return source


def originals(s):
    bolt=cast(s,'Lightning Bolt',targets=['p3'])
    opt=cast(s,'Opt',pid='p2')
    return bolt,opt


def copies(s):
    return [cid for cid in s.state.zones.get('stack',[]) if s.state.cards[cid].is_token and s.state.cards[cid].ability is None]


def create(s,order=(),target='keep'):
    sequence=list(order)
    settle(s)
    for _ in range(40):
        d=s.state.rules.decision
        if d is None:
            return
        step=d.resume.get('step')
        if step=='copy_source_order':
            choice=sequence.pop(0) if sequence else d.options[0].id
        elif step=='copy_order':
            choice='original'
        elif step=='copy_target':
            choice=target
        else:
            raise AssertionError((d.kind,step,d.prompt))
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[choice])
    raise AssertionError('Copying did not finish')


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


def test_zero_targets_is_legal_and_makes_no_copies(cards):
    s=setup(cards)
    source=cast(s,NAME)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert not copies(s)
    roundtrip(s)


@pytest.mark.parametrize('reverse',[False,True])
def test_copy_order_is_chosen_for_own_and_opponent_spells(cards,reverse):
    s=setup(cards)
    bolt,opt=originals(s)
    cast(s,NAME,targets=[bolt.id,opt.id])
    order=[opt.id,bolt.id] if reverse else [bolt.id,opt.id]
    create(s,order)
    made=copies(s)
    assert [s.state.cards[c].name for c in made]==(['Opt','Lightning Bolt'] if reverse else ['Lightning Bolt','Opt'])
    assert all(s.state.cards[c].controller=='p1' for c in made)
    assert bolt.id in s.state.zones['stack'] and opt.id in s.state.zones['stack']
    roundtrip(s)


def test_retargeted_copy_keeps_original_targets_unchanged(cards):
    s=setup(cards)
    bolt=cast(s,'Lightning Bolt',targets=['p3'])
    cast(s,NAME,targets=[bolt.id])
    create(s,target='p2')
    made=copies(s)
    assert len(made)==1 and s.state.rules.stack[made[0]].targets[0].id=='p2'
    assert s.state.rules.stack[bolt.id].targets[0].id=='p3'
    settle(s)
    assert s.state.players['p2'].life==37 and s.state.players['p3'].life==37
    roundtrip(s)


@pytest.mark.parametrize('remove_all',[False,True])
def test_illegal_targets_are_skipped_and_all_illegal_stops_resolution(cards,remove_all):
    s=setup(cards)
    bolt,opt=originals(s)
    source=cast(s,NAME,targets=[bolt.id,opt.id])
    for c in ([bolt,opt] if remove_all else [opt]):
        act(s,c.owner,type='move',card_ids=[c.id],to={'player':c.owner,'zone':'graveyard'})
    create(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert len(copies(s))==int(not remove_all)
    roundtrip(s)


def test_uncopyable_target_does_not_block_copying_other_targets(cards):
    s=setup(cards)
    bolt=cast(s,'Lightning Bolt',targets=['p3'])
    first=cast(s,NAME)
    cast(s,NAME,targets=[first.id,bolt.id])
    create(s,[first.id,bolt.id])
    assert [s.state.cards[c].name for c in copies(s)]==['Lightning Bolt']
    roundtrip(s)


def test_creature_and_ability_are_not_legal_targets(cards):
    s=setup(cards)
    permanent=cast(s,'Sol Ring')
    with pytest.raises(ActionError):
        cast(s,NAME,targets=[permanent.id])
    roundtrip(s)


def test_staff_extra_copies_can_interleave_across_different_spells(cards):
    s=setup(cards,staff=True)
    bolt,opt=originals(s)
    cast(s,NAME,targets=[bolt.id,opt.id])
    create(s,[bolt.id,opt.id,bolt.id,opt.id])
    assert [s.state.cards[c].name for c in copies(s)]==['Lightning Bolt','Opt','Lightning Bolt','Opt']
    roundtrip(s)


def test_later_counterspell_copy_can_target_an_earlier_created_copy(cards):
    s=setup(cards)
    bolt=cast(s,'Lightning Bolt',targets=['p3'])
    counter=cast(s,'Counterspell',pid='p2',targets=[bolt.id])
    cast(s,NAME,targets=[counter.id,bolt.id])
    settle(s)
    d=s.state.rules.decision
    assert d.resume['step']=='copy_source_order'
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[bolt.id])
    d=s.state.rules.decision
    assert d.resume['step']=='copy_target'
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['keep'])
    d=s.state.rules.decision
    assert d.resume['step']=='copy_target'
    made=copies(s)
    bolt_copy=next(c for c in made if s.state.cards[c].name=='Lightning Bolt')
    assert bolt_copy in {o.id for o in d.options}
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[bolt_copy])
    counter_copy=next(c for c in copies(s) if s.state.cards[c].name=='Counterspell')
    assert s.state.rules.stack[counter_copy].targets[0].id==bolt_copy
    assert s.state.rules.stack[counter.id].targets[0].id==bolt.id
    roundtrip(s)


def test_activated_ability_is_not_a_legal_target(cards):
    s=setup(cards,staff=True)
    bolt=cast(s,'Lightning Bolt',targets=['p3'])
    staff=next(c for c in s.state.cards.values() if c.name=='Twinning Staff' and c.zone=='p1:battlefield')
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'C':7})
    act(s,'p1',type='activate_ability',card_id=staff.id,ability=1,targets=[bolt.id])
    ability=next(cid for cid in s.state.zones['stack'] if s.state.cards[cid].ability is not None)
    with pytest.raises(ActionError):
        cast(s,NAME,targets=[ability])
    roundtrip(s)


def test_no_copy_restriction_does_not_block_copying_the_card_from_exile(cards):
    s=setup(cards)
    display=put(s,NAME,'graveyard')
    mastery=cast(s,"Mizzix's Mastery",targets=[display.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='free_cast_pick' and len(d.options)==1
    copy_id=d.options[0].id
    assert s.state.cards[copy_id].name==NAME and s.state.cards[copy_id].zone=='p1:exile'
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[copy_id])
    for _ in range(5):
        d=s.state.rules.decision
        if d is None:
            break
        assert d.min_choices==0
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    assert s.state.cards[copy_id].zone=='stack'
    from app.rules.copying import uncopyable
    from app.rules.plan import Plan
    assert uncopyable(Plan(s.state,'p1',s.cards,None),s.state.cards[copy_id])==''
    settle(s)
    assert s.state.cards[mastery.id].zone=='p1:exile'
    assert s.state.cards[display.id].zone=='p1:exile'
    assert copy_id not in s.state.cards
    roundtrip(s)
