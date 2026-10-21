"""Conditional inspected-card replacements preserve one verdict through native choices."""
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
from tests.test_rules_library_look import answer, settle
from tests.test_rules_refused_look import stack_library, thin_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/land_or_cast_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Omen Machine','Wild Evocation','Unexpected Results','Audacious Swap','Rona, Herald of Invasion // Rona, Tolarian Obliterator']

@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'




def setup(cards):
    data=json.loads((Path(__file__).parent/'fixtures/land_or_cast_cards.json').read_text())
    names=[c['name'] for c in data]
    s=table(cards,names,names,names)
    to_phase(s,'main1',turn=1)
    return s


@pytest.mark.parametrize('accept',[False,True])
def test_unexpected_land_acceptance_returns_source_only_when_accepted(cards,accept):
    s=setup(cards)
    source=put(s,'Unexpected Results','hand')
    thin_library(s,['Forest'])
    mana(s,C=2,U=1,G=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    answer(s,['pay' if accept else 'decline'])
    assert s.state.cards[source.id].zone==('p1:hand' if accept else 'p1:graveyard')
    assert any(c.name=='Forest' and c.zone==('p1:battlefield' if accept else 'p1:library') for c in s.state.cards.values())
    roundtrip(s)


def test_unexpected_nonland_native_optional_cast(cards):
    s=setup(cards)
    source=put(s,'Unexpected Results','hand')
    thin_library(s,['Grizzly Bears'])
    mana(s,C=2,U=1,G=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='free_cast_pick'
    answer(s,[d.options[0].id])
    assert any(c.name=='Grizzly Bears' and c.zone=='p1:battlefield' for c in s.state.cards.values())
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name,phase',[('Omen Machine','draw'),('Wild Evocation','upkeep')])
@pytest.mark.parametrize('land',[True,False])
def test_other_players_mandatory_branch_uses_their_controller(cards,name,phase,land):
    s=setup(cards)
    put(s,name,'battlefield')
    if name=='Omen Machine':
        top=stack_library(s,['Island' if land else 'Grizzly Bears'],pid='p2')[0]
    else:
        # A single-card hand makes the mandatory random reveal deterministic.
        for cid in list(s.state.zones['p2:hand']):
            act(s,'p2',type='move',card_ids=[cid],to={'zone':'graveyard'})
        top=put(s,'Island' if land else 'Grizzly Bears','hand',pid='p2').id
    to_phase(s,phase,turn=2)
    settle(s)
    if not land:
        d=s.state.rules.decision
        assert d is not None and d.player=='p2' and d.min_choices==1
        answer(s,[d.options[0].id])
    assert s.state.cards[top].zone=='p2:battlefield'
    assert s.state.cards[top].controller=='p2'
    roundtrip(s)


def test_unexpected_accepted_land_replacement_still_returns_spell(cards):
    s=setup(cards)
    moon=put(s,'Hallowed Moonlight','hand')
    mana(s,C=1,W=1)
    act(s,'p1',type='cast_spell',card_id=moon.id)
    settle(s)
    thin_library(s,['Dryad Arbor'])
    source=put(s,'Unexpected Results','hand')
    mana(s,C=2,U=1,G=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    answer(s,['pay'])
    assert s.state.cards[source.id].zone=='p1:hand'
    assert any(c.name=='Dryad Arbor' and c.zone=='p1:exile' for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize('land',[True,False])
def test_audacious_swap_uses_target_owner_not_controller(cards,land):
    s=setup(cards)
    target=put(s,'Sol Ring','battlefield',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[target.id],player='p3')
    keep=stack_library(s,['Island' if land else 'Grizzly Bears'],pid='p2')[0]
    for cid in list(s.state.zones['p2:library']):
        if cid!=keep:
            act(s,'p2',type='move',card_ids=[cid],to={'zone':'exile'})
    source=put(s,'Audacious Swap','hand')
    mana(s,C=3,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[target.id])
    settle(s)
    # The shuffled target is also eligible; either deterministic random outcome
    # still belongs to p2, and the cast decision goes to its owner.
    d=s.state.rules.decision
    if d is not None:
        assert d.player=='p2' and d.min_choices==0
        answer(s,[d.options[0].id])
    assert any(c.owner=='p2' and c.controller=='p2' and c.zone=='p2:battlefield' for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize('land',[True,False])
def test_rona_damage_uses_source_controller_hand_but_rona_controller_casts(cards,land):
    s=setup(cards)
    rona=put(s,NAMES[4],'battlefield')
    mana(s,C=5,B=1)
    act(s,'p1',type='activate_ability',card_id=rona.id,ability=2)
    settle(s)
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        answer(s,[d.options[0].id])
    assert s.state.cards[rona.id].face==1
    for cid in list(s.state.zones['p2:hand']):
        act(s,'p2',type='move',card_ids=[cid],to={'zone':'graveyard'})
    bolt=put(s,'Lightning Bolt','hand',pid='p2')
    chosen=put(s,'Island' if land else 'Grizzly Bears','hand',pid='p2')
    mana(s,pid='p2',R=1)
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=bolt.id,targets=[rona.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player=='p1'
    answer(s,['pay'] if land else [d.options[0].id])
    assert s.state.cards[chosen.id].zone=='p1:battlefield'
    assert s.state.cards[chosen.id].owner=='p2'
    roundtrip(s)


@pytest.mark.parametrize('floating',[False,True])
def test_wild_mandatory_tax_floating_mana_vs_optional_mana_activation(cards,floating):
    s=setup(cards)
    put(s,'Wild Evocation','battlefield')
    put(s,'Sphere of Resistance','battlefield')
    put(s,'Sol Ring','battlefield',pid='p2')
    for cid in list(s.state.zones['p2:hand']):
        act(s,'p2',type='move',card_ids=[cid],to={'zone':'graveyard'})
    bears=put(s,'Grizzly Bears','hand',pid='p2')
    to_phase(s,'upkeep',turn=2)
    if floating:
        mana(s,pid='p2',C=1)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player=='p2' and d.min_choices==1
    answer(s,[d.options[0].id])
    if not floating:
        d=s.state.rules.decision
        assert d is not None and d.resume.get('required_mana_decline')
        answer(s,['cancel'])
    assert s.state.cards[bears.id].zone==('p2:battlefield' if floating else 'p2:hand')
    roundtrip(s)


@pytest.mark.parametrize('name',['Grizzly Bears','Kazandu Mammoth // Kazandu Valley'])
def test_unexpected_decline_leaves_card_on_library_without_land_option(cards,name):
    s=setup(cards)
    source=put(s,'Unexpected Results','hand')
    thin_library(s,[name])
    mana(s,C=2,U=1,G=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='free_cast_pick'
    assert all('Valley' not in o.label for o in d.options)
    answer(s,[])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert any(c.name==name and c.zone=='p1:library' and not c.revealed_to for c in s.state.cards.values())
    roundtrip(s)


def test_unexpected_free_x_spell_is_zero_and_uses_normal_state_based_actions(cards):
    s=setup(cards)
    source=put(s,'Unexpected Results','hand')
    thin_library(s,['Shivan Devastator'])
    mana(s,C=2,U=1,G=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    answer(s,[d.options[0].id])
    if s.state.rules.decision is not None:
        d=s.state.rules.decision
        assert d.resume['step']=='free_x'
        answer(s,['x:0'])
    assert any(c.name=='Shivan Devastator' and c.zone=='p1:graveyard' for c in s.state.cards.values())
    roundtrip(s)


def test_omen_mandatory_cast_prohibition_keeps_exact_exiled_card(cards):
    s=setup(cards)
    put(s,'Omen Machine','battlefield')
    put(s,"Grafdigger's Cage",'battlefield')
    top=stack_library(s,['Grizzly Bears'],pid='p2')[0]
    # Cage prohibits casting from libraries, but Omen first exiles the card,
    # so its cast is permitted and its creature resolves from the stack.
    to_phase(s,'draw',turn=2)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player=='p2'
    answer(s,[d.options[0].id])
    assert s.state.cards[top].zone=='p2:battlefield'
    roundtrip(s)


def test_unexpected_exact_library_object_cannot_cast_departed_and_returned_card(cards):
    s=setup(cards)
    source=put(s,'Unexpected Results','hand')
    thin_library(s,['Grizzly Bears'])
    mana(s,C=2,U=1,G=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    d=s.state.rules.decision
    selected=d.options[0].id
    cid=d.options[0].card_id
    act(s,'p1',type='move',card_ids=[cid],to={'zone':'exile'})
    act(s,'p1',type='move',card_ids=[cid],to={'zone':'library'},position='top')
    answer(s,[selected])
    assert not any(c.name=='Grizzly Bears' and c.zone=='p1:battlefield' for c in s.state.cards.values())
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name,phase',[('Omen Machine','draw'),('Wild Evocation','upkeep')])
def test_empty_library_or_hand_finishes_without_choice_or_controller_leak(cards,name,phase):
    s=setup(cards)
    put(s,name,'battlefield')
    zone='p2:library' if name=='Omen Machine' else 'p2:hand'
    for cid in list(s.state.zones[zone]):
        act(s,'p2',type='move',card_ids=[cid],to={'zone':'exile'})
    to_phase(s,phase,turn=2)
    settle(s)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_wild_unpayable_additional_cost_leaves_revealed_card_in_hand_hidden_again(cards):
    s=setup(cards)
    put(s,'Wild Evocation','battlefield')
    for cid in list(s.state.zones['p2:hand']):
        act(s,'p2',type='move',card_ids=[cid],to={'zone':'graveyard'})
    fling=put(s,'Fling','hand',pid='p2')
    to_phase(s,'upkeep',turn=2)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[fling.id].zone=='p2:hand'
    assert not s.state.cards[fling.id].revealed_to
    roundtrip(s)
