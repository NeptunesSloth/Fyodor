"""Actual ninjutsu entry, intervening source state, and independently attacking copies."""
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
from tests.test_rules_conditionals import until
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6e_statics import attack_with

NAME='Thousand-Faced Shadow'

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    raw=json.loads((Path(__file__).parent/'fixtures/thousand_faced_shadow_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='tfs',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,*,double=False,other=True):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/thousand_faced_shadow_cards.json').read_text())]
    s=table(cards,names,names,names)
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True,stops_my_turn=['main1','declare_blockers','main2'])
    ninja=put(s,NAME,'hand')
    put(s,'Grizzly Bears','battlefield',pid='p2')
    put(s,'Ornithopter','battlefield',pid='p2')
    returned=put(s,'Ornithopter','battlefield')
    bear=put(s,'Grizzly Bears','battlefield') if other else None
    if double:
        put(s,'Parallel Lives','battlefield')
    until(s,lambda s:s.state.turn.number==4 and s.state.turn.phase=='main1' and s.state.rules.decision is None)
    attack_with(s,returned,*([bear] if bear else []))
    until(s,lambda s:s.state.rules.decision is not None and s.state.rules.decision.kind=='declare_blockers')
    act(s,'p2',type='declare_blockers',blocks=[])
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'U':2})
    act(s,'p1',type='activate_ability',card_id=ninja.id,ability=0)
    d=s.state.rules.decision
    if d is not None:
        assert returned.id in [o.id for o in d.options]
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[returned.id])
    settle(s)
    if bear:
        d=s.state.rules.decision
        assert d is not None and d.resume['step']=='trigger_target'
        assert ninja.id not in [o.id for o in d.options]
        assert bear.id in [o.id for o in d.options]
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    return s,ninja,bear


def tokens(s):
    return [c for c in s.state.cards.values() if c.name=='Grizzly Bears' and c.is_token]


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


@pytest.mark.parametrize('double',[False,True])
def test_native_ninjutsu_copy_enters_tapped_and_each_token_chooses_defender(cards,double):
    s,ninja,bear=setup(cards,double=double)
    assert s.state.cards[ninja.id].attacking.id=='p2'
    settle(s)
    for target in (['p3','p2'] if double else ['p3']):
        d=s.state.rules.decision
        assert d is not None and d.resume['step']=='token_attack'
        assert {'p2','p3'} <= {o.id for o in d.options}
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[target])
    made=tokens(s)
    assert len(made)==(2 if double else 1)
    assert all(c.tapped and c.attacking for c in made)
    assert {c.attacking.id for c in made}==({'p2','p3'} if double else {'p3'})
    assert s.state.cards[bear.id].attacking.id=='p2'
    roundtrip(s)


def test_no_other_attacker_means_no_target_and_no_copy(cards):
    s,ninja,_=setup(cards,other=False)
    assert s.state.cards[ninja.id].attacking is not None
    assert s.state.rules.decision is None and not tokens(s)
    roundtrip(s)


@pytest.mark.parametrize('remove',['target','source'])
def test_removing_attacker_from_combat_before_resolution_stops_copy(cards,remove):
    from tests.test_rules_bandmate_references import wait_priority

    s,ninja,bear=setup(cards)
    maze=put(s,'Reconnaissance','battlefield')
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=maze.id,ability=0,targets=[bear.id if remove=='target' else ninja.id])
    roundtrip(s)
    settle(s)
    assert not tokens(s) and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('depart',['target','source'])
def test_departed_target_is_illegal_but_departed_attacking_source_uses_lki(cards,depart):
    s,ninja,bear=setup(cards)
    act(s,'p1',type='move',card_ids=[bear.id if depart=='target' else ninja.id],to={'player':'p1','zone':'graveyard'})
    roundtrip(s)
    settle(s)
    if depart=='source':
        d=s.state.rules.decision
        assert d is not None and d.resume['step']=='token_attack'
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=['p3'])
        assert len(tokens(s))==1 and tokens(s)[0].attacking.id=='p3'
    else:
        assert not tokens(s) and s.state.rules.decision is None
    roundtrip(s)


def test_cast_from_hand_enters_from_stack_and_never_triggers(cards):
    s=table(cards,[NAME],[],[])
    ninja=put(s,NAME,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'U':1})
    act(s,'p1',type='cast_spell',card_id=ninja.id)
    settle(s)
    assert s.state.cards[ninja.id].zone=='p1:battlefield'
    assert not s.state.cards[ninja.id].attacking and not tokens(s)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_entering_attacking_does_not_pay_attack_tax(cards):
    s,_,_=setup(cards)
    put(s,'Ghostly Prison','battlefield',pid='p3')
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='token_attack'
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['p3'])
    assert len(tokens(s))==1 and tokens(s)[0].attacking.id=='p3'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_actual_hand_entry_without_attacking_does_not_trigger(cards):
    s=table(cards,[NAME,'Elvish Piper'],[],[])
    ninja=put(s,NAME,'hand')
    piper=put(s,'Elvish Piper','battlefield')
    until(s,lambda s:s.state.turn.number==4 and s.state.turn.phase=='main1' and s.state.rules.decision is None)
    act(s,'p1',type='add_mana',player='p1',mana={'G':1})
    act(s,'p1',type='activate_ability',card_id=piper.id,ability=0)
    settle(s)
    for _ in range(3):
        d=s.state.rules.decision
        if d is None:
            break
        roundtrip(s)
        ids=[o.id for o in d.options]
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[ninja.id if ninja.id in ids else 'yes' if 'yes' in ids else ids[0]])
        settle(s)
    assert s.state.cards[ninja.id].zone=='p1:battlefield'
    assert s.state.cards[ninja.id].attacking is None and not tokens(s)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_actual_graveyard_entry_does_not_trigger(cards):
    s=table(cards,[NAME,'Reanimate'],[],[])
    ninja=put(s,NAME,'graveyard')
    reanimate=put(s,'Reanimate','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'B':1})
    act(s,'p1',type='cast_spell',card_id=reanimate.id,targets=[ninja.id])
    settle(s)
    assert s.state.cards[ninja.id].zone=='p1:battlefield'
    assert s.state.cards[ninja.id].attacking is None and not tokens(s)
    assert s.state.rules.decision is None
    roundtrip(s)
