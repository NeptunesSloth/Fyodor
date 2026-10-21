"""Volatile Stormdrake draft: exact exchange gate, energy payment and source-kind hexproof."""
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


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    raw=json.loads((Path(__file__).parent/'fixtures/volatile_stormdrake_cards.json').read_text())
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='vsd',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME='Volatile Stormdrake'


def setup(cards,target='Grizzly Bears'):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/volatile_stormdrake_cards.json').read_text())]
    s=table(cards,names,names,names)
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True)
    if target=='token':
        before=set(s.state.cards)
        act(s,'p2',type='create_token',player='p2',token={'name':'Exchange victim','type_line':'Token Creature — Soldier','power':'2','toughness':'2','text':''})
        victim=next(c for cid,c in s.state.cards.items() if cid not in before)
    else:
        victim=put(s,target,'battlefield',pid='p2')
    source=put(s,NAME,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'U':1})
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and victim.id in {o.id for o in d.options}
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[victim.id])
    return s,source,victim


def energy(s):
    return s.state.players['p1'].resources.get('energy',0)


def answer(s,choice):
    d=s.state.rules.decision
    assert d is not None and d.player=='p1'
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[choice])
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


@pytest.mark.parametrize('accept',[False,True])
def test_successful_exchange_gets_four_energy_then_optional_exact_payment(cards,accept):
    s,drake,victim=setup(cards)
    before={c.id:s.state.rules.object_id(c.id) for c in (drake,victim)}
    settle(s)
    assert s.state.cards[drake.id].controller=='p2'
    assert s.state.cards[victim.id].controller=='p1'
    assert energy(s)==4
    assert all(s.state.rules.object_id(cid)==oid for cid,oid in before.items())
    answer(s,'pay' if accept else 'decline')
    assert energy(s)==(2 if accept else 4)
    assert s.state.cards[victim.id].zone==('p1:battlefield' if accept else 'p2:graveyard')
    assert s.state.cards[drake.id].controller=='p2'
    roundtrip(s)


def test_unaffordable_mana_value_is_not_partially_paid(cards):
    s,drake,victim=setup(cards,'Serra Angel')
    settle(s)
    if s.state.rules.decision is not None:
        assert 'pay' not in {o.id for o in s.state.rules.decision.options}
        answer(s,'decline')
    assert energy(s)==4 and s.state.cards[victim.id].zone=='p2:graveyard'
    assert s.state.cards[drake.id].controller=='p2'
    roundtrip(s)


@pytest.mark.parametrize('which',['drake','target'])
def test_missing_exchange_object_means_no_energy_or_payment(cards,which):
    s,drake,victim=setup(cards)
    gone=drake if which=='drake' else victim
    act(s,gone.owner,type='move',card_ids=[gone.id],to={'player':gone.owner,'zone':'graveyard'})
    settle(s)
    assert energy(s)==0 and s.state.rules.decision is None
    if which=='drake':
        assert s.state.cards[victim.id].controller=='p2'
    else:
        assert s.state.cards[drake.id].controller=='p1'
    roundtrip(s)


def test_source_and_target_already_same_controller_cannot_partially_exchange(cards):
    s,drake,victim=setup(cards)
    act(s,'p1',type='set_controller',card_ids=[drake.id],player='p2')
    settle(s)
    assert energy(s)==0 and s.state.rules.decision is None
    assert s.state.cards[victim.id].controller==s.state.cards[drake.id].controller=='p2'
    roundtrip(s)


def test_source_controlled_by_third_player_can_exchange_but_caster_cannot_sacrifice_acquired_card(cards):
    s,drake,victim=setup(cards)
    act(s,'p1',type='set_controller',card_ids=[drake.id],player='p3')
    settle(s)
    assert s.state.cards[drake.id].controller=='p2'
    assert s.state.cards[victim.id].controller=='p3'
    assert energy(s)==4
    answer(s,'decline')
    assert s.state.cards[victim.id].zone=='p3:battlefield'
    roundtrip(s)




def protected(cards):
    from tests.test_rules_wave30m_durations import to_phase

    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/volatile_stormdrake_cards.json').read_text())]
    s=table(cards,names,names,names)
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True)
    drake=put(s,NAME,'battlefield')
    settle(s)  # no opponent creature existed, so the ETB has no legal target
    mine=put(s,'Prodigal Pyromancer','battlefield')
    theirs=put(s,'Prodigal Pyromancer','battlefield',pid='p2')
    to_phase(s,'main1',turn=4)
    return s,drake,mine,theirs


def test_opponent_activated_ability_cannot_target_but_own_ability_can(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority

    s,drake,mine,theirs=protected(cards)
    wait_priority(s,'p2')
    with pytest.raises(ActionError):
        act(s,'p2',type='activate_ability',card_id=theirs.id,ability=0,targets=[drake.id])
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=mine.id,ability=0,targets=[drake.id])
    settle(s)
    assert s.state.cards[drake.id].damage==1
    roundtrip(s)


def test_opponent_spell_can_target_drake(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s,drake,_,_=protected(cards)
    wait_priority(s,'p2')
    spell=put(s,'Lightning Bolt','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'R':1})
    act(s,'p2',type='cast_spell',card_id=spell.id,targets=[drake.id])
    settle(s)
    assert s.state.cards[drake.id].zone=='p1:graveyard'
    roundtrip(s)


def test_opponent_triggered_ability_target_choice_excludes_drake(cards):
    s,drake,_,_=protected(cards)
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s,'main1',turn=5)
    kavu=put(s,'Flametongue Kavu','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'C':3,'R':1})
    act(s,'p2',type='cast_spell',card_id=kavu.id)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player=='p2' and drake.id not in {o.id for o in d.options}, [(c.name,c.zone,c.controller) for c in s.state.cards.values() if c.zone.endswith(':battlefield')]
    roundtrip(s)
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[d.options[0].id])
    settle(s)
    assert s.state.cards[drake.id].zone=='p1:battlefield'
    roundtrip(s)


def test_cast_trigger_is_an_ability_even_when_its_source_is_still_a_spell(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s,drake,mine,theirs=protected(cards)
    wait_priority(s,'p2')
    ulamog=put(s,'Ulamog, the Ceaseless Hunger','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'C':10})
    # Cast in Bob's main phase; the existing drake is controlled by Alice.
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s,'main1',turn=5)
    act(s,'p2',type='add_mana',player='p2',mana={'C':10})
    act(s,'p2',type='cast_spell',card_id=ulamog.id)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player=='p2' and drake.id not in {o.id for o in d.options}
    assert s.state.cards[ulamog.id].zone=='stack'
    assert {mine.id,theirs.id}<={o.id for o in d.options}
    roundtrip(s)
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[mine.id,theirs.id])
    settle(s)
    assert s.state.cards[drake.id].zone=='p1:battlefield'
    roundtrip(s)


def test_source_kind_flags_are_explicit_mutually_exclusive_and_preserve_lki(cards):
    from dataclasses import replace

    from app.rules.plan import Plan
    from app.rules.protection import hexproof
    from app.rules.targets import as_spell, source_of

    assert hexproof('Hexproof from activated abilities') is None
    assert hexproof('Hexproof from triggered abilities') is None
    s,drake,_,source=protected(cards)
    p=Plan(s.state,'p1',s.cards,None)
    ability=source_of(p,source.id)
    assert ability is not None and ability.is_ability and not ability.is_spell
    spell=as_spell(ability)
    assert spell.is_spell and not spell.is_ability
    assert as_spell(replace(spell,is_ability=True)).is_ability is False
    oid=s.state.rules.object_id(source.id)
    act(s,'p2',type='move',card_ids=[source.id],to={'player':'p2','zone':'graveyard'})
    p=Plan(s.state,'p1',s.cards,None)
    remembered=source_of(p,source.id,object_id=oid)
    assert remembered is not None and remembered.is_ability and not remembered.is_spell
    assert source_of(p,source.id,True,object_id=oid).is_ability is False
    roundtrip(s)


@pytest.mark.parametrize('target',['Ornithopter','token'])
@pytest.mark.parametrize('accept',[False,True])
def test_mana_value_zero_is_optional_and_costs_no_energy(cards,target,accept):
    s,drake,victim=setup(cards,target)
    settle(s)
    assert energy(s)==4
    answer(s,'pay' if accept else 'decline')
    assert energy(s)==4
    if target=='token' and not accept:
        assert victim.id not in s.state.cards
    else:
        assert s.state.cards[victim.id].zone==('p1:battlefield' if accept else 'p2:graveyard')
    assert s.state.cards[drake.id].controller=='p2'
    roundtrip(s)


def test_energy_replacement_is_applied_before_retention_payment(cards):
    s,drake,victim=setup(cards,'Serra Angel')
    put(s,'Vorinclex, Monstrous Raider','battlefield')
    settle(s)
    assert energy(s)==8
    answer(s,'pay')
    assert energy(s)==3 and s.state.cards[victim.id].zone=='p1:battlefield'
    assert s.state.cards[drake.id].controller=='p2'
    roundtrip(s)


@pytest.mark.parametrize('ignore',['Glaring Spotlight','Arcane Lighthouse','Dress Down'])
def test_ignoring_or_removing_hexproof_permits_opponent_ability(cards,ignore):
    from tests.test_rules_bandmate_references import wait_priority

    s,drake,_,source=protected(cards)
    tool=put(s,ignore,'battlefield',pid='p2')
    if ignore=='Dress Down':
        source=put(s,'Rod of Ruin','battlefield',pid='p2')
    settle(s)
    if ignore=='Arcane Lighthouse':
        wait_priority(s,'p2')
        act(s,'p2',type='add_mana',player='p2',mana={'C':1})
        act(s,'p2',type='activate_ability',card_id=tool.id,ability=1)
        settle(s)
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'C':3})
    act(s,'p2',type='activate_ability',card_id=source.id,ability=0,targets=[drake.id])
    settle(s)
    assert s.state.cards[drake.id].damage==1
    roundtrip(s)


def test_ability_source_lki_is_still_an_ability_when_hexproof_returns(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s,drake,_,source=protected(cards)
    down=put(s,'Dress Down','battlefield')
    source=put(s,'Rod of Ruin','battlefield',pid='p2')
    settle(s)
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'C':3})
    act(s,'p2',type='activate_ability',card_id=source.id,ability=0,targets=[drake.id])
    act(s,'p2',type='move',card_ids=[source.id],to={'player':'p2','zone':'graveyard'})
    act(s,'p1',type='move',card_ids=[down.id],to={'player':'p1','zone':'graveyard'})
    roundtrip(s)
    settle(s)
    assert s.state.cards[drake.id].damage==0
    roundtrip(s)


def test_new_drake_object_cannot_complete_old_exchange_after_cloudshift(cards):
    s,drake,victim=setup(cards)
    other=put(s,'Ornithopter','battlefield',pid='p3')
    old=s.state.rules.object_id(drake.id)
    shift=put(s,'Cloudshift','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'W':1})
    act(s,'p1',type='cast_spell',card_id=shift.id,targets=[drake.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and other.id in {o.id for o in d.options}
    assert s.state.rules.object_id(drake.id)!=old
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[other.id])
    settle(s)
    answer(s,'pay')
    assert energy(s)==4
    assert s.state.cards[drake.id].controller=='p3'
    assert s.state.cards[other.id].controller=='p1'
    assert s.state.cards[victim.id].controller=='p2'
    roundtrip(s)


def test_exchange_persists_when_drake_later_leaves(cards):
    s,drake,victim=setup(cards)
    settle(s)
    answer(s,'pay')
    act(s,'p2',type='move',card_ids=[drake.id],to={'player':'p1','zone':'graveyard'})
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s,'main1',turn=2)
    assert s.state.cards[victim.id].controller=='p1' and s.state.cards[victim.id].zone=='p1:battlefield'
    roundtrip(s)


def test_own_preserver_does_not_prevent_own_exchange_ability_sacrifice(cards):
    s,drake,victim=setup(cards)
    put(s,'Tajuru Preserver','battlefield')
    settle(s)
    answer(s,'decline')
    assert s.state.cards[victim.id].zone=='p2:graveyard' and energy(s)==4
    assert s.state.cards[drake.id].controller=='p2'
    roundtrip(s)


def test_assault_suit_prevents_sacrifice_without_undoing_exchange(cards):
    s,drake,victim=setup(cards)
    suit=put(s,'Assault Suit','battlefield',pid='p2')
    act(s,'p2',type='attach',card_ids=[suit.id],to=victim.id)
    settle(s)
    answer(s,'decline')
    assert s.state.cards[victim.id].zone=='p1:battlefield' and energy(s)==4
    assert s.state.cards[drake.id].controller=='p2'
    roundtrip(s)
