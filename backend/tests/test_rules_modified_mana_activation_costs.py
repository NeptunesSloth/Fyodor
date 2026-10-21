"""Mana-ability cost modifiers reuse native input payment and filter continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.payment_rider_injection import inject_mana_draw_rider
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/modified_mana_activation_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='mmc',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/modified_mana_activation_cards.json').read_text())]
    s=table(cards,names,names,names)
    elf=put(s,'Llanowar Elves','battlefield')
    aura=put(s,'Oppressive Rays','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'W':1})
    act(s,'p1',type='cast_spell',card_id=aura.id,targets=[elf.id],sources=[])
    settle(s)
    to_phase(s,'main1',4)
    act(s,'p1',type='set_prefs',hold_priority=True)
    return s,elf,aura


def test_explicit_taxed_mana_activation_uses_other_untapped_sources(cards):
    s,elf,_=game(cards)
    forests=[c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Forest'][:3]
    act(s,'p1',type='move',card_ids=[c.id for c in forests],to={'player':'p1','zone':'battlefield'})
    act(s,'p1',type='activate_ability',card_id=elf.id,ability=0)
    assert all(s.state.cards[c.id].tapped for c in [elf,*forests])
    assert mana_pool(s,'p1')=={'G':1}
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_auto_spell_payment_uses_taxed_elf_as_existing_filter(cards):
    s,elf,_=game(cards)
    bear=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':4})
    act(s,'p1',type='cast_spell',card_id=bear.id)
    assert s.state.cards[elf.id].tapped and not mana_pool(s,'p1')
    assert s.state.zones['stack']==[bear.id]
    paid=s.state.rules.payments[s.state.rules.object_id(bear.id)]
    assert paid.mana_spent=={'C':1,'G':1}  # Three inputs paid the ability, not the spell.
    roundtrip(s)
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    roundtrip(s)


def test_self_payment_can_activate_taxed_mana_source_while_paying_spell(cards):
    s,elf,_=game(cards)
    act(s,'p1',type='set_prefs',payment='self')
    bear=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':4})
    act(s,'p1',type='cast_spell',card_id=bear.id)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    roundtrip(s)
    act(s,'p1',type='activate_ability',card_id=elf.id,ability=0)
    assert s.state.rules.decision is None and s.state.cards[elf.id].tapped
    assert not mana_pool(s,'p1') and s.state.zones['stack']==[bear.id]
    roundtrip(s)


def test_tax_is_locked_before_paused_input_rider_and_not_repaid_after_aura_leaves(cards,monkeypatch):
    # Explicit low-level continuation injection; CR605.1a does not classify a draw effect as a mana ability.
    inject_mana_draw_rider(monkeypatch,{'Basalt Monolith'})
    s,elf,aura=game(cards)
    monolith=put(s,'Basalt Monolith','battlefield')
    put(s,'Abundance','battlefield')
    act(s,'p1',type='activate_ability',card_id=elf.id,ability=0)
    d=s.state.rules.decision
    assert d is not None and 'decline' in {o.id for o in d.options}
    assert s.state.cards[monolith.id].tapped and not s.state.cards[elf.id].tapped
    assert mana_pool(s,'p1')=={'C':3}  # Input production paused before the locked cost commits.
    roundtrip(s)
    act(s,'p1',type='move',card_ids=[aura.id],to={'player':'p1','zone':'graveyard'})
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['decline'])
    assert s.state.rules.decision is None and s.state.cards[elf.id].tapped
    assert mana_pool(s,'p1')=={'G':1}
    roundtrip(s)


def test_reduction_applies_after_mana_ability_tax_and_preserves_minimum(cards):
    s,elf,_=game(cards)
    put(s,'Training Grounds','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'U':1})
    act(s,'p1',type='activate_ability',card_id=elf.id,ability=0)
    assert s.state.cards[elf.id].tapped and mana_pool(s,'p1')=={'G':1}
    roundtrip(s)


def test_taxed_colored_input_cost_honors_actual_spend_as_permission(cards):
    s,_,aura=game(cards)
    act(s,'p1',type='move',card_ids=[aura.id],to={'player':'p1','zone':'hand'})
    agent=put(s,'Agent of Stromgald','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'W':1})
    act(s,'p1',type='cast_spell',card_id=aura.id,targets=[agent.id],sources=[])
    settle(s)
    put(s,'Mycosynth Lattice','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'U':4})
    act(s,'p1',type='activate_ability',card_id=agent.id,ability=0)
    assert mana_pool(s,'p1')=={'B':1}  # Actual U paid the modified {3}{R}; output is actual B.
    roundtrip(s)
