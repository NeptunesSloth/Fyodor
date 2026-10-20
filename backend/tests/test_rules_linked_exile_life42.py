"""Production exact native linked-exile and nominal-life game proofs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for index,c in enumerate(json.loads((Path(__file__).parent/'fixtures/linked_exile_life42_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='lel',number=str(index),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names=['Bronzebeak Foragers','Luminate Primordial','Grizzly Bears','Sol Ring','Giant Growth','Murder','Rest in Peace','Downsize','Cloudshift','Containment Priest','Raise Dead']
    s=table(cards,names,names,names)
    to_phase(s,'main1',turn=1)
    return s


def enter(s,name,targets):
    source=put(s,name,'hand')
    mana(s,C=5,W=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    for _ in range(5):
        d=s.state.rules.decision
        if d is None:
            break
        matches=[o.id for o in d.options if o.card_id in targets]
        assert matches or d.min_choices==0,d
        answer(s,matches[:d.max_choices])
        settle(s)
    assert s.state.rules.decision is None
    return source


def test_bronzebeak_actual_per_opponent_until_source_and_x_exact_linked_card_payment(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    ring=put(s,'Sol Ring','battlefield','p3')
    source=enter(s,'Bronzebeak Foragers',[bear.id,ring.id])
    assert s.state.cards[bear.id].zone=='p2:exile' and s.state.cards[ring.id].zone=='p3:exile'
    act(s,'p1',type='clear_mana',player='p1')
    mana(s,C=2,W=1)
    life=s.state.players['p1'].life
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{X}'),x_value=1,targets=[bear.id])
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{X}'),x_value=2,targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone=='p2:graveyard'
    assert s.state.players['p1'].life==life+2
    from tests.test_rules_ordered_tutor_continuations import cast
    cast(s,'Murder',targets=[source.id])
    assert s.state.cards[ring.id].zone=='p3:battlefield'
    assert s.state.cards[bear.id].zone=='p2:graveyard'
    roundtrip(s)


def test_luminate_actual_per_opponent_exile_uses_last_battlefield_power_and_vigilance(cards):
    from tests.test_rules_wave4h_activation_costs import ch
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    other=put(s,'Grizzly Bears','battlefield','p3')
    growth=put(s,'Giant Growth','hand')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bear.id])
    settle(s)
    source=enter(s,'Luminate Primordial',[bear.id,other.id])
    assert s.state.cards[bear.id].zone=='p2:exile' and s.state.cards[other.id].zone=='p3:exile'
    assert s.state.players['p2'].life==45 and s.state.players['p3'].life==42
    assert 'vigilance' in ch(s,source).keywords
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


def test_bronzebeak_gain_is_announced_x_even_when_graveyard_move_is_replaced(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    source=enter(s,'Bronzebeak Foragers',[bear.id])
    # Native static exile replacement, not a test movement adapter.
    put(s,'Rest in Peace','battlefield')
    act(s,'p1',type='clear_mana',player='p1')
    mana(s,C=2,W=1)
    before=s.state.players['p1'].life
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{X}'),x_value=2,targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone=='p2:exile'
    assert s.state.players['p1'].life==before+2
    roundtrip(s)


def test_luminate_negative_actual_power_gains_zero_not_printed_or_mana_value(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    shrink=put(s,'Downsize','hand')
    mana(s,U=1)
    act(s,'p1',type='cast_spell',card_id=shrink.id,targets=[bear.id])
    settle(s)
    enter(s,'Luminate Primordial',[bear.id])
    assert s.state.cards[bear.id].zone=='p2:exile'
    assert s.state.players['p2'].life==40
    roundtrip(s)


@pytest.mark.parametrize('name', ['Bronzebeak Foragers','Luminate Primordial'])
def test_etb_source_departure_before_resolution_preserves_only_printed_duration(cards,name):
    s=setup(cards)
    act(s,'p1',type='set_prefs',hold_priority=True)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    source=put(s,name,'hand')
    mana(s,C=5,W=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    for _ in range(5):
        d=s.state.rules.decision
        if d is None:
            break
        matches=[o.id for o in d.options if o.card_id==bear.id]
        act(s,d.decider or d.player,type='choose',decision_id=d.id,option_ids=matches[:d.max_choices])
        if s.state.rules.decision is None:
            break
    assert s.state.rules.stack
    for _ in range(4):
        if s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    murder=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=murder.id,targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    expected='p2:battlefield' if name=='Bronzebeak Foragers' else 'p2:exile'
    assert s.state.cards[bear.id].zone==expected
    assert s.state.players['p2'].life==(40 if name=='Bronzebeak Foragers' else 42)
    roundtrip(s)


def test_bronzebeak_activation_target_returned_by_source_departure_fizzles_without_life(cards):
    s=setup(cards)
    act(s,'p1',type='set_prefs',hold_priority=True)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    source=enter(s,'Bronzebeak Foragers',[bear.id])
    mana(s,C=2,W=1)
    before=s.state.players['p1'].life
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{X}'),x_value=2,targets=[bear.id])
    murder=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=murder.id,targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[bear.id].zone=='p2:battlefield'
    assert s.state.players['p1'].life==before
    roundtrip(s)


def test_luminate_partial_illegal_targets_still_exiles_other_opponent_and_gains_only_their_power(cards):
    s=setup(cards)
    act(s,'p1',type='set_prefs',hold_priority=True)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    other=put(s,'Grizzly Bears','battlefield','p3')
    source=put(s,'Luminate Primordial','hand')
    mana(s,C=5,W=2)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    for _ in range(5):
        d=s.state.rules.decision
        if d is None:
            break
        matches=[o.id for o in d.options if o.card_id in {bear.id,other.id}]
        act(s,d.decider or d.player,type='choose',decision_id=d.id,option_ids=matches[:d.max_choices])
    assert s.state.rules.decision is None
    for _ in range(4):
        if s.state.rules.priority=='p1':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    murder=put(s,'Murder','hand')
    mana(s,C=1,B=2)
    act(s,'p1',type='cast_spell',card_id=murder.id,targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone=='p2:graveyard'
    assert s.state.cards[other.id].zone=='p3:exile'
    assert s.state.players['p2'].life==40 and s.state.players['p3'].life==42
    roundtrip(s)


@pytest.mark.parametrize('name',['Bronzebeak Foragers','Luminate Primordial'])
def test_actual_exile_token_ceases_without_phantom_return_or_lost_nominal_power(cards,name):
    s=setup(cards)
    act(s,'p2',type='create_token',player='p2',token={'name':'Bear Token','type_line':'Token Creature — Bear','power':'2','toughness':'2','colors':['G']})
    token=next(c for c in s.state.cards.values() if c.is_token and c.owner=='p2')
    source=enter(s,name,[token.id])
    assert token.id not in s.state.cards or s.state.cards[token.id].zone is None
    assert s.state.players['p2'].life==(42 if name=='Luminate Primordial' else 40)
    from tests.test_rules_ordered_tutor_continuations import cast
    cast(s,'Murder',targets=[source.id])
    assert not any(c.is_token and c.name=='Bear Token' and c.zone=='p2:battlefield' for c in s.state.cards.values())
    roundtrip(s)


def test_bronzebeak_new_source_incarnation_cannot_target_old_source_exile_when_native_return_is_prevented(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    source=enter(s,'Bronzebeak Foragers',[bear.id])
    old_source=s.state.rules.object_id(source.id)
    put(s,'Containment Priest','battlefield')
    from tests.test_rules_ordered_tutor_continuations import cast
    cast(s,'Murder',targets=[source.id])
    assert s.state.cards[bear.id].zone=='p2:exile'
    cast(s,'Raise Dead',targets=[source.id])
    assert s.state.cards[source.id].zone=='p1:hand'
    act(s,'p1',type='clear_mana',player='p1')
    mana(s,C=3,W=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    for _ in range(4):
        d=s.state.rules.decision
        if d is None:
            break
        assert d.min_choices==0
        answer(s,[])
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.rules.object_id(source.id)!=old_source
    mana(s,C=2,W=1)
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{X}'),x_value=2,targets=[bear.id])
    roundtrip(s)


def test_bronzebeak_native_blink_returns_old_packet_and_new_etb_may_decline_new_packet(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    source=enter(s,'Bronzebeak Foragers',[bear.id])
    old=s.state.rules.object_id(source.id)
    from tests.test_rules_ordered_tutor_continuations import cast
    cast(s,'Cloudshift',targets=[source.id])
    for _ in range(4):
        d=s.state.rules.decision
        if d is None:
            break
        assert d.min_choices==0
        answer(s,[])
    assert s.state.cards[source.id].zone=='p1:battlefield' and s.state.rules.object_id(source.id)!=old
    assert s.state.cards[bear.id].zone=='p2:battlefield'
    mana(s,C=2,W=1)
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=ability(s,source,'{X}'),x_value=2,targets=[bear.id])
    roundtrip(s)
