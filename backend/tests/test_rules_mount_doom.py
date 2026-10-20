"""CR 608.2d, 701.8: choose creatures on resolution and destroy the complement."""
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
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Mount Doom'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/mount_doom_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, *, count=4, phase=True):
    s = table(cards, [NAME,'Shadowspear','Grizzly Bears','Lightning Bolt'],
              ['Grizzly Bears','Darksteel Myr','Scythe Tiger','Sol Ring'], ['Grizzly Bears'])
    source = put(s, NAME, 'battlefield')
    payment = put(s, 'Shadowspear', 'battlefield')
    creatures = []
    if count >= 1:
        creatures.append(put(s, 'Grizzly Bears', 'battlefield'))
    if count >= 2:
        creatures.append(put(s, 'Scythe Tiger', 'battlefield',pid='p2'))
    if count >= 3:
        creatures.append(put(s, 'Grizzly Bears', 'battlefield',pid='p3'))
    if count >= 4:
        creatures.append(put(s, 'Darksteel Myr', 'battlefield',pid='p2'))
    ring = put(s, 'Sol Ring', 'battlefield',pid='p2')
    if phase:
        to_phase(s, 'main1', turn=1)
    return s, source, payment, creatures, ring


def activate(s, source, payment, *, generic=5):
    wait_priority(s, 'p1')
    mana(s,C=generic,B=1,R=1)
    act(s,'p1',type='activate_ability',card_id=source.id,
        ability=ability_index(s,source,'Choose up to two'),
        cost_choices=[{'component':3,'cards':[payment.id]}])


def choice(s):
    from tests.test_rules_designations import settle as settle_choices

    settle_choices(s)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'choose_cards' and d.player == 'p1'
    assert d.min_choices == 0
    roundtrip(s)
    return d


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('kept',[[],[0],[0,1],[1,2]])
def test_choose_zero_one_or_two_across_players_without_targeting(cards, kept):
    s,source,payment,creatures,ring = setup(cards)
    activate(s,source,payment)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[payment.id].zone == 'p1:graveyard'
    assert not any(s.state.players['p1'].mana.values())
    d=choice(s)
    assert d.max_choices == 2
    assert {o.id for o in d.options} == {c.id for c in creatures}
    # Scythe Tiger has shroud, but a resolution choice doesn't target.
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[creatures[i].id for i in kept])
    settle(s)
    for i,c in enumerate(creatures):
        assert s.state.cards[c.id].zone == f'{c.owner}:' + ('battlefield' if i in kept or i==3 else 'graveyard')
    assert s.state.cards[ring.id].zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('count',[1,2])
def test_up_to_choice_stays_optional_when_every_creature_could_be_kept(cards,count):
    s,source,payment,creatures,_=setup(cards,count=count)
    activate(s,source,payment)
    d=choice(s)
    assert d.max_choices == count
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[])
    settle(s)
    assert all(s.state.cards[c.id].zone.endswith(':graveyard') for c in creatures)
    roundtrip(s)


def test_empty_battlefield_resolves_without_a_choice(cards):
    s,source,payment,_,ring=setup(cards,count=0)
    activate(s,source,payment)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[ring.id].zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('problem',['mana','missing_artifact','not_legendary','opponent_artifact','wrong_turn','stack'])
def test_illegal_activation_keeps_every_cost_unpaid(cards,problem):
    s,source,payment,_,ring=setup(cards)
    if problem=='missing_artifact':
        act(s,'p1',type='move',card_ids=[payment.id],to={'player':'p1','zone':'graveyard'})
    elif problem=='not_legendary':
        payment=ring
        act(s,'p1',type='set_controller',card_ids=[ring.id],player='p1')
    elif problem=='opponent_artifact':
        act(s,'p1',type='set_controller',card_ids=[payment.id],player='p2')
    elif problem=='wrong_turn':
        to_phase(s,'main1',turn=2)
    elif problem=='stack':
        spell=put(s,'Lightning Bolt','hand')
        act(s,'p1',type='set_prefs',hold_priority=True)
        mana(s,R=1)
        act(s,'p1',type='cast_spell',card_id=spell.id,targets=['p2'])
    wait_priority(s,'p1')
    mana(s,C=4 if problem=='mana' else 5,B=1,R=1)
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,
            ability=ability_index(s,source,'Choose up to two'),cost_choices=[{'component':3,'cards':[payment.id]}])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_other_damage_ability_and_life_payment_mana_ability(cards):
    s,source,payment,_,_=setup(cards,count=0)
    life={p:s.state.players[p].life for p in ['p1','p2','p3']}
    mana(s,C=1,B=1,R=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'deals 1 damage'))
    settle(s)
    assert s.state.players['p2'].life==life['p2']-1 and s.state.players['p3'].life==life['p3']-1
    assert s.state.cards[payment.id].zone=='p1:battlefield'
    act(s,'p1',type='tap',card_ids=[source.id],tapped=False)
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'Pay 1 life'))
    settle(s)
    assert s.state.players['p1'].life==life['p1']-1
    assert s.state.cards[source.id].tapped
    assert sum(mana_pool(s).values()) == 1
    roundtrip(s)
