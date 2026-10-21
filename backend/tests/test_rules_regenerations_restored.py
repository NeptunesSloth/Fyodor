"""Canonical counter removal, conditional exile, reflexive extra turn and vanishing race."""
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

NAME='Regenerations Restored'

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/regenerations_restored_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='rgr',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/regenerations_restored_cards.json').read_text())]
    s=table(cards,names,names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    source=put(s,NAME,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'W':1,'U':1})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    assert s.state.cards[source.id].counters['time']==12
    roundtrip(s)
    return s,source


def remove(s,source,n):
    spell=put(s,'Timecrafting','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':n,'R':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,x_value=n,modes=[0],targets=[source.id],sources=[])
    for _ in range(40):
        if s.state.rules.decision is not None:
            return
        act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('no counter-removal decision')


def scry(s):
    d=s.state.rules.decision
    assert d is not None and d.kind=='choose_cards', (d.kind if d else None,d.prompt if d else None)
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


def test_removing_several_but_not_all_counters_scries_and_gains_once_without_exile(cards):
    s,source=setup(cards)
    remove(s,source,2)
    assert s.state.cards[source.id].counters['time']==10
    scry(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.players['p1'].life==41
    assert not s.state.rules.extra_turns and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('reverse',[False,True])
def test_last_counter_order_can_exile_for_extra_turn_or_sacrifice_first(cards,reverse):
    s,source=setup(cards)
    remove(s,source,12)
    d=s.state.rules.decision
    assert d is not None and d.kind=='order', (d.kind if d else None,d.prompt if d else None)
    roundtrip(s)
    ids=[o.id for o in d.options]
    act(s,d.player,type='choose',decision_id=d.id,option_ids=ids[::-1] if reverse else ids)
    settle(s)
    scry(s)
    zone=s.state.cards[source.id].zone
    assert zone==('p1:exile' if reverse else 'p1:graveyard')
    assert len(s.state.rules.extra_turns)==(1 if zone=='p1:exile' else 0)
    assert s.state.players['p1'].life==41
    roundtrip(s)
    if reverse:
        from tests.test_rules_wave30m_durations import to_phase

        to_phase(s,'main1',turn=2)
        assert s.state.turn.active_player=='p1' and s.state.rules.extra_turn
        roundtrip(s)


def exile_first(s):
    d=s.state.rules.decision
    assert d is not None and d.kind=='order'
    # Native queue order lists the card trigger before vanishing; stack order is reversed.
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options][::-1])


def test_counter_added_before_card_trigger_resolves_prevents_exile_and_extra_turn(cards):
    s,source=setup(cards)
    remove(s,source,12)
    exile_first(s)
    # Table counter mutation supplies the changed state while the real removal trigger is on stack.
    act(s,'p1',type='counter',card_ids=[source.id],kind='time',delta=1)
    settle(s)
    assert s.state.cards[source.id].counters['time']==1
    scry(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'  # Already-triggered vanishing still sacrifices it.
    assert not s.state.rules.extra_turns and s.state.players['p1'].life==41
    roundtrip(s)


def test_reflexive_extra_turn_uses_stack_and_can_be_stifled_after_exile(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s,source=setup(cards)
    remove(s,source,12)
    exile_first(s)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.kind=='choose_cards'
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
    assert s.state.cards[source.id].zone=='p1:exile'
    assert not s.state.rules.extra_turns
    trigger=next(cid for cid,e in s.state.rules.stack.items() if e.effects==[{'do':'extra_turn','who':'you','n':1}])
    stifle=put(s,'Stifle','hand',pid='p2')
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    act(s,'p2',type='cast_spell',card_id=stifle.id,targets=[trigger],sources=[])
    roundtrip(s)
    settle(s)
    assert not s.state.rules.extra_turns and s.state.cards[source.id].zone=='p1:exile'
    assert s.state.players['p1'].life==41
    roundtrip(s)


def test_other_counter_kind_never_triggers_card(cards):
    s,source=setup(cards)
    act(s,'p1',type='set_counter',card_id=source.id,kind='charge',value=1)
    act(s,'p1',type='counter',card_ids=[source.id],kind='charge',delta=-1)
    settle(s)
    assert s.state.rules.decision is None and s.state.players['p1'].life==40
    assert s.state.cards[source.id].counters['time']==12
    roundtrip(s)


def test_native_upkeep_vanishing_removes_one_then_scries_and_gains(cards):
    from tests.test_rules_conditionals import until

    s,source=setup(cards)
    until(s,lambda s:s.state.turn.number==4 and s.state.turn.phase=='upkeep' and bool(s.state.rules.stack))
    settle(s)
    assert s.state.cards[source.id].counters['time']==11
    scry(s)
    assert s.state.players['p1'].life==41 and s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)
