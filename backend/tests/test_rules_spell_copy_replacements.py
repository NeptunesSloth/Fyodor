"""CR 614.5, 707.10: additional copies replace the entire copying event."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table

NAME='Twinning Staff'


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/spell_copy_replacement_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='sdc',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, *, own=1, opponent=0, extra=(), opponent_extra=()):
    s=table(cards,[NAME]*own+['Lightning Bolt','Reverberate','Grapeshot','Sol Ring','Opt',*extra],[NAME]*opponent+list(opponent_extra),[])
    staff=[]
    for pid in ['p1','p2']:
        for c in list(s.state.cards.values()):
            if c.owner==pid and c.name==NAME:
                act(s,pid,type='move',card_ids=[c.id],to={'player':pid,'zone':'battlefield'})
                staff.append(c)
    return s,staff


def finish(s, *, order=(), extra_target=None, observed=None):
    sequence=list(order)
    seen=[]
    for _ in range(120):
        d=s.state.rules.decision
        if d:
            step=(d.resume or {}).get('step')
            seen.append(step)
            options={o.id for o in d.options}
            if step=='copy_order':
                option=sequence.pop(0) if sequence else 'original'
            elif step=='copy_each' and sequence:
                kind=sequence.pop(0)
                option='__additional__' if kind=='additional' else next(o.id for o in d.options if o.id!='__additional__')
            elif step=='copy_target' and extra_target is not None:
                option=extra_target
            else:
                option=next((o for o in ['same','keep','original','done'] if o in options),d.options[0].id)
            roundtrip(s)
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[option])
        elif s.state.zones.get('stack'):
            if observed is not None:
                stack=s.state.zones['stack']
                if all(s.state.cards[c].name=='Lightning Bolt' and s.state.cards[c].ability is None for c in stack):
                    observed.append([s.state.rules.stack[c].targets[0].id for c in stack if s.state.cards[c].is_token])
            act(s,s.state.rules.priority,type='pass_priority')
        else:
            return seen
    raise AssertionError('copying did not settle')


def reverberate(s):
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,R=3)
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=['p2'])
    wait_priority(s,'p1')
    echo=put(s,'Reverberate','hand')
    act(s,'p1',type='cast_spell',card_id=echo.id,targets=[bolt.id])
    return bolt


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


@pytest.mark.parametrize('own,opponent',[(0,1),(1,0),(2,0)])
def test_each_own_modifier_adds_once_and_opponents_modifiers_do_not_apply(cards,own,opponent):
    s,_=setup(cards,own=own,opponent=opponent)
    reverberate(s)
    finish(s)
    assert s.state.players['p2'].life==40-3*(2+own)
    roundtrip(s)


@pytest.mark.parametrize('prior',[0,1,3])
def test_storm_is_one_copy_event_and_zero_copies_are_not_replaced(cards,prior):
    s,_=setup(cards,extra=('Sol Ring',)*prior)
    # Casting Opt repeatedly is unnecessary: distinct actual Sol Ring spells
    # give the storm count while their costs and resolutions remain ordinary.
    rings=[c for c in s.state.cards.values() if c.name=='Sol Ring' and c.owner=='p1']
    for _i in range(prior):
        ring=rings[_i]
        act(s,'p1',type='move',card_ids=[ring.id],to={'player':'p1','zone':'hand'})
        mana(s,C=1)
        act(s,'p1',type='cast_spell',card_id=ring.id)
        finish(s)
    spell=put(s,'Grapeshot','hand')
    mana(s,C=1,R=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=['p2'])
    finish(s)
    assert s.state.players['p2'].life==40-(1+prior+(1 if prior else 0))
    roundtrip(s)


def test_activated_copy_ability_itself_benefits_from_the_static(cards):
    s,staff=setup(cards)
    bolt=put(s,'Lightning Bolt','hand')
    mana(s,R=1,C=7)
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=['p2'])
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=staff[0].id,ability=1,targets=[bolt.id])
    finish(s)
    assert s.state.players['p2'].life==31
    assert s.state.cards[staff[0].id].tapped
    roundtrip(s)


@pytest.mark.parametrize('order',[['additional'],['original']])
def test_extra_copy_can_be_put_before_or_after_the_original(cards,order):
    s,_=setup(cards)
    reverberate(s)
    seen=finish(s,order=order)
    assert 'copy_order' in seen
    assert s.state.players['p2'].life==31
    roundtrip(s)


@pytest.mark.parametrize('order',[[],['additional'],['original','additional']])
def test_zada_original_copies_are_constrained_but_additional_copy_may_target_a_player(cards,order):
    s,_=setup(cards,extra=('Zada, Hedron Grinder','Grizzly Bears','Llanowar Elves'))
    zada=put(s,'Zada, Hedron Grinder','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    elf=put(s,'Llanowar Elves','battlefield')
    bolt=put(s,'Lightning Bolt','hand')
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=[zada.id])
    observed=[]
    finish(s,order=order,extra_target='p2',observed=observed)
    completed=next(targets for targets in observed if len(targets)==3)
    assert completed.index('p2') == (2 if not order else 0 if order[0]=='additional' else 1)
    assert s.state.players['p2'].life==37
    assert all(s.state.cards[c.id].zone=='p1:graveyard' for c in [zada,bear,elf])
    roundtrip(s)


def test_zada_with_no_other_eligible_creatures_makes_no_additional_copy(cards):
    s,_=setup(cards,extra=('Zada, Hedron Grinder',))
    zada=put(s,'Zada, Hedron Grinder','battlefield')
    spell=put(s,'Lightning Bolt','hand')
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[zada.id])
    finish(s)
    assert s.state.players['p2'].life==40
    roundtrip(s)


def test_casualty_x_additional_permanent_spell_copy_keeps_loyalty_exception(cards):
    from tests.test_rules_wave6c_tokens_pumps import chars

    s,_=setup(cards,extra=('Ob Nixilis, the Adversary','Grizzly Bears'))
    put(s,'Grizzly Bears','battlefield')
    spell=put(s,'Ob Nixilis, the Adversary','hand')
    mana(s,C=1,B=1,R=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,x_value=2,optional_costs=[f'{spell.id}:casualty'])
    finish(s)
    copies=[c for c in s.state.cards.values() if c.name=='Ob Nixilis, the Adversary' and c.is_token and c.zone=='p1:battlefield']
    assert len(copies)==2
    assert all(c.counters['loyalty']==2 and chars(s,c).loyalty=='2' and 'Legendary' not in chars(s,c).supertypes for c in copies)
    roundtrip(s)


def test_copying_an_ability_does_not_add_another_ability_copy(cards):
    s,staff=setup(cards,extra=('Lithoform Engine',))
    engine=put(s,'Lithoform Engine','battlefield')
    bolt=put(s,'Lightning Bolt','hand')
    mana(s,R=1,C=9)
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=['p2'])
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=staff[0].id,ability=1,targets=[bolt.id])
    ability=next(c for c in s.state.cards.values() if c.zone=='stack' and c.ability is not None and c.id!=bolt.id)
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=engine.id,ability=0,targets=[ability.id])
    finish(s)
    # Two resolutions each copy the spell twice; the ability was copied once.
    assert s.state.players['p2'].life==25
    roundtrip(s)


def test_copying_a_permanent_spell_creates_additional_token_permanent(cards):
    s,_=setup(cards,extra=('Lithoform Engine','Grizzly Bears'))
    engine=put(s,'Lithoform Engine','battlefield')
    bear=put(s,'Grizzly Bears','hand')
    mana(s,C=5,G=1)
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='cast_spell',card_id=bear.id)
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=engine.id,ability=2,targets=[bear.id])
    finish(s)
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.name=='Grizzly Bears' and c.is_token])==2
    roundtrip(s)


def test_modifier_must_still_be_present_when_copy_event_occurs(cards):
    s,staff=setup(cards)
    reverberate(s)
    act(s,'p1',type='move',card_ids=[staff[0].id],to={'player':'p1','zone':'graveyard'})
    finish(s)
    assert s.state.players['p2'].life==34
    roundtrip(s)


def test_scepter_copies_a_card_and_casts_it_without_extra_spell_copy(cards):
    s,_=setup(cards,extra=('Isochron Scepter',))
    bolt=put(s,'Lightning Bolt','hand')
    scepter=put(s,'Isochron Scepter','hand')
    mana(s,C=2)
    act(s,'p1',type='cast_spell',card_id=scepter.id)
    finish(s)
    assert s.state.cards[bolt.id].zone=='p1:exile'
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=scepter.id,ability=1)
    finish(s)
    assert sum(s.state.players[p].life for p in ['p1','p2','p3'])==117
    assert s.state.cards[bolt.id].zone=='p1:exile'
    roundtrip(s)


def test_additional_copy_can_be_inserted_between_storm_copies(cards):
    s,_=setup(cards,extra=('Sol Ring',)*3)
    rings=[c for c in s.state.cards.values() if c.name=='Sol Ring' and c.owner=='p1']
    for _i in range(3):
        ring=rings[_i]
        act(s,'p1',type='move',card_ids=[ring.id],to={'player':'p1','zone':'hand'})
        mana(s,C=1)
        act(s,'p1',type='cast_spell',card_id=ring.id)
        finish(s)
    spell=put(s,'Grapeshot','hand')
    mana(s,C=1,R=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=['p2'])
    seen=finish(s,order=['original','additional'])
    assert seen.count('copy_order') >= 2
    assert s.state.players['p2'].life==35
    roundtrip(s)


def test_countered_storm_spell_is_copied_from_last_known_values_with_an_additional_copy(cards):
    s,_=setup(cards,extra=('Counterspell',))
    ring=put(s,'Sol Ring','hand')
    mana(s,C=1)
    act(s,'p1',type='cast_spell',card_id=ring.id)
    finish(s)
    spell=put(s,'Grapeshot','hand')
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,C=1,R=1,U=2)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=['p2'])
    wait_priority(s,'p1')
    counter=put(s,'Counterspell','hand')
    act(s,'p1',type='cast_spell',card_id=counter.id,targets=[spell.id])
    finish(s)
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert s.state.players['p2'].life==38
    roundtrip(s)


@pytest.mark.parametrize('own,opponent',[(1,0),(0,1)])
def test_mirrorwing_uses_the_spell_casters_staff_not_the_trigger_controllers(cards,own,opponent):
    s,_=setup(cards,own=own,opponent=opponent,extra=('Grizzly Bears','Llanowar Elves'),opponent_extra=('Mirrorwing Dragon',))
    dragon=put(s,'Mirrorwing Dragon','battlefield',pid='p2')
    bear=put(s,'Grizzly Bears','battlefield')
    elf=put(s,'Llanowar Elves','battlefield')
    spell=put(s,'Lightning Bolt','hand')
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[dragon.id])
    finish(s,extra_target='p2')
    assert s.state.players['p2'].life==40-3*own
    assert all(s.state.cards[c.id].zone=='p1:graveyard' for c in [bear,elf])
    assert s.state.cards[dragon.id].zone=='p2:battlefield' and s.state.cards[dragon.id].damage==3
    roundtrip(s)
