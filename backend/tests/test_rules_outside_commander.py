"""CR 903.11: ordinary outside-game permissions cannot import traditional Commander cards."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.state import CollectionCard
from app.rules import coverage, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/outside_commander_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='ocg',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def owned(s, name="Environmental Sciences"):
    c=s.cards.resolve(name)
    s.state.collections['p1']=[CollectionCard(printing_id=c['id'],oracle_id=c['oracle_id'],name=c['name'],quantity=2)]
    # Collections are part of the initial saved/replay state, as in a real lobby-created game.
    from app.game.session import GameSession
    return GameSession(s.state,cards=s.cards)


def mana(s):
    act(s,'p1',type='add_mana',player='p1',mana={k:20 for k in ['C','W','U','B','R','G']})


@pytest.mark.parametrize('name,zone',[(n,'exile') for n in ['Burning Wish','Cunning Wish','Living Wish','Glittering Wish','Golden Wish','Death Wish']]+[('Wish','graveyard'),("Mastermind's Acquisition",'graveyard')])
def test_wish_cannot_take_even_an_owned_card_but_the_rest_of_the_spell_resolves(cards,name,zone):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'
    candidate={"Cunning Wish":"Lightning Bolt", "Living Wish":"Grizzly Bears", "Golden Wish":"Sol Ring", "Glittering Wish":"Atraxa, Praetors' Voice"}.get(name,"Environmental Sciences")
    s=owned(build(cards,[name]),candidate)
    before=dict(s.state.cards)
    spell=put(s,name,'hand')
    mana(s)
    act(s,'p1',type='cast_spell',card_id=spell.id,**({'modes':[1]} if name=="Mastermind's Acquisition" else {}))
    roundtrip(s)
    settle(s)
    assert s.state.cards[spell.id].zone==f'p1:{zone}'
    assert set(s.state.cards)==set(before)
    assert s.state.collections['p1'][0].quantity==2
    assert s.state.players['p1'].life==(20 if name=='Death Wish' else 40)
    assert 'collections' not in s.view('p2')
    roundtrip(s)


def test_legion_angel_outside_permission_is_unavailable_in_commander(cards):
    assert coverage.of_card_data(cards.resolve('Legion Angel')).level=='FULL'
    s=owned(build(cards,['Legion Angel']),'Legion Angel')
    source=put(s,'Legion Angel','hand')
    mana(s)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert len([c for c in s.state.cards.values() if c.name=='Legion Angel'])==1
    roundtrip(s)


def test_spawnsire_outside_casting_permission_does_not_bring_in_cards(cards):
    assert coverage.of_card_data(cards.resolve('Spawnsire of Ulamog')).level=='FULL'
    s=owned(build(cards,['Spawnsire of Ulamog']))
    source=put(s,'Spawnsire of Ulamog','battlefield')
    mana(s)
    ab=next(a for a in Plan(s.state,'p1',cards,None).ch(source).abilities if a.cost=='{20}')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ab.index)
    settle(s)
    assert not s.state.zones['stack'] and s.state.collections['p1'][0].quantity==2
    roundtrip(s)


def test_unrecognized_outside_wording_is_not_guessed():
    assert scripts.parse_effects('You may reveal seven cards you own from outside the game and put them onto the battlefield.') is None


def test_granted_adventure_exiles_then_the_creature_can_be_cast_and_bounce_for_its_cost(cards):
    assert coverage.of_card_data(cards.resolve("Fae of Wishes // Granted")).level=='FULL'
    s=owned(build(cards,["Fae of Wishes // Granted"]))
    source=put(s,"Fae of Wishes // Granted",'hand')
    mana(s)
    act(s,'p1',type='cast_spell',card_id=source.id,face=1)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)
    act(s,'p1',type='cast_spell',card_id=source.id,face=0)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    discard=[c.id for c in s.state.cards.values() if c.name=='Forest'][:2]
    act(s,'p1',type='move',card_ids=discard,to={'player':'p1','zone':'hand'})
    ab=next(a for a in Plan(s.state,'p1',cards,None).ch(s.state.cards[source.id]).abilities if a.cost and 'Discard two' in a.cost)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ab.index,cost_choices=[{'component':1,'cards':discard}])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:hand'
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in discard)
    roundtrip(s)


@pytest.mark.parametrize('cast',[True,False])
def test_north_wind_avatar_does_not_offer_an_impossible_import_even_when_its_cast_condition_holds(cards,cast):
    assert coverage.of_card_data(cards.resolve('North Wind Avatar')).level=='FULL'
    s=owned(build(cards,['North Wind Avatar']))
    source=put(s,'North Wind Avatar','hand' if cast else 'battlefield')
    if cast:
        mana(s)
        act(s,'p1',type='cast_spell',card_id=source.id)
    else:
        act(s,'p1',type='pass_priority')
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert not s.state.zones.get('stack') and s.state.rules.decision is None
    assert s.state.collections['p1'][0].quantity==2
    roundtrip(s)


def test_masterminds_library_mode_still_searches_and_shuffles(cards):
    s=owned(build(cards,["Mastermind's Acquisition",'Sol Ring']))
    source=put(s,"Mastermind's Acquisition",'hand')
    target=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Sol Ring')
    mana(s)
    act(s,'p1',type='cast_spell',card_id=source.id,modes=[0])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and target.id in [o.id for o in d.options]
    assert 'Sol Ring' not in json.dumps(s.view('p2'))
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone=='p1:hand'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_spawnsire_spawn_tokens_can_pay_their_sacrifice_mana_ability(cards):
    s=owned(build(cards,['Spawnsire of Ulamog']))
    source=put(s,'Spawnsire of Ulamog','battlefield')
    mana(s)
    ab=next(a for a in Plan(s.state,'p1',cards,None).ch(source).abilities if a.cost=='{4}')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ab.index)
    settle(s)
    made=[c for c in s.state.cards.values() if c.is_token and c.name=='Eldrazi Spawn']
    assert len(made)==2
    token=made[0]
    ab=next(a for a in Plan(s.state,'p1',cards,None).ch(token).abilities if a.cost and 'Sacrifice' in a.cost)
    before=mana_pool(s,'p1').get('C',0)
    act(s,'p1',type='activate_ability',card_id=token.id,ability=ab.index)
    settle(s)
    assert mana_pool(s,'p1').get('C',0)==before+1
    assert token.id not in s.state.cards
    roundtrip(s)


@pytest.mark.parametrize('pay',[True,False])
def test_learn_can_rummage_but_cannot_take_an_owned_lesson_in_commander(cards,pay):
    s=owned(build(cards,['Pop Quiz']))
    source=put(s,'Pop Quiz','hand')
    mana(s)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and {o.id for o in d.options}=={'pay','decline'}
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['pay' if pay else 'decline'])
    settle(s)
    assert len(s.state.zones['p1:hand'])==1
    assert len(s.state.zones['p1:graveyard'])==(2 if pay else 1)
    assert not any(c.name=='Environmental Sciences' for c in s.state.cards.values())
    assert s.state.collections['p1'][0].quantity==2
    roundtrip(s)


def test_death_wish_rounds_the_life_loss_up_from_an_odd_total(cards):
    s=owned(build(cards,['Death Wish']))
    source=put(s,'Death Wish','hand')
    act(s,'p1',type='set_life',player='p1',value=39)
    mana(s)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.players['p1'].life==19 and s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)
