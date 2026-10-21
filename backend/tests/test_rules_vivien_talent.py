"""Canonical Vivien Talent quoted loyalty and nontoken entry collateral."""
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
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/vivien_talent_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()





def setup(cards):
    s = table(cards, ['Jace Beleren', "Vivien's Talent", 'Grizzly Bears', 'Raise the Alarm', 'Forest', 'Mountain', 'Shock'],
              ['Grizzly Bears', 'Disenchant', 'Stifle'], ['Shock'])
    walker = put(s, 'Jace Beleren', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=walker.id, sources=[])
    settle(s)
    aura = put(s, "Vivien's Talent", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[walker.id], sources=[])
    settle(s)
    assert s.state.cards[aura.id].attached_to == walker.id
    assert s.state.cards[walker.id].counters['loyalty'] == 3
    return s, walker, aura


def activate(s, walker):
    from tests.test_rules_wave7b_activation import ability_index
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Look at the top four'))
    assert s.state.cards[walker.id].counters['loyalty'] == 4


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Vivien's Talent")).level == 'FULL'


@pytest.mark.parametrize('choice', ['Grizzly Bears', 'Forest', None])
def test_actual_granted_plus_one_looks_four_selects_optional_creature_or_land_and_bottoms_rest(cards, choice):
    from tests.test_rules_abundance import set_library
    from tests.test_rules_conditionals import until_asked
    s, walker, _ = setup(cards)
    set_library(s, ['Grizzly Bears', 'Shock', 'Forest', 'Mountain', 'Raise the Alarm'])
    top = list(s.state.zones['p1:library'])
    grave_before = list(s.state.zones.get('p1:graveyard', []))
    activate(s, walker)
    until_asked(s)
    d = s.state.rules.decision
    assert d
    assert {o.label for o in d.options} == {'Grizzly Bears', 'Forest', 'Mountain'}
    selected = [o.id for o in d.options if o.label == choice] if choice else []
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=selected)
    settle(s)
    assert len(s.state.zones['p1:library']) == 5 - len(selected)
    assert set(s.state.zones['p1:library']) == set(top) - set(selected)
    assert s.state.cards[s.state.zones['p1:library'][0]].name == 'Raise the Alarm'  # untouched fifth card stays above the random rest
    assert all(s.state.cards[cid].zone == 'p1:hand' for cid in selected)
    assert s.state.zones.get('p1:graveyard', []) == grave_before  # the ability does not mill
    roundtrip(s)


def test_nontoken_own_creature_entry_puts_loyalty_on_host(cards):
    s, walker, _ = setup(cards)
    bear = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=bear.id, sources=[])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    roundtrip(s)


def test_tokens_and_opponents_creatures_do_not_trigger(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s, walker, _ = setup(cards)
    spell = put(s, 'Raise the Alarm', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    settle(s)
    assert len([c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.token]) == 2
    bear = put(s, 'Grizzly Bears', 'hand', pid='p2')
    # A creature is a sorcery-speed spell, so use Bob's native main phase.
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'main1', turn=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'G': 1, 'C': 1})
    act(s, 'p2', type='cast_spell', card_id=bear.id, sources=[])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 3
    roundtrip(s)


def test_activated_loyalty_ability_persists_after_aura_leaves(cards):
    from tests.test_rules_abundance import set_library
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_conditionals import until_asked
    s, walker, aura = setup(cards)
    set_library(s, ['Grizzly Bears', 'Shock', 'Forest', 'Mountain'])
    activate(s, walker)
    spell = put(s, 'Disenchant', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'W': 1, 'C': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[aura.id], sources=[])
    until_asked(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    selected = next(o.id for o in d.options if o.label == 'Grizzly Bears')
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[selected])
    settle(s)
    assert s.state.cards[selected].zone == 'p1:hand'
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    roundtrip(s)


def test_aura_left_before_creature_entry_trigger_resolves_still_uses_original_host(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s, walker, aura = setup(cards)
    bear = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=bear.id, sources=[])
    for _ in range(12):
        if s.state.cards[bear.id].zone == 'p1:battlefield':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.rules.stack and s.state.cards[walker.id].counters['loyalty'] == 3
    aura_oid = s.state.rules.object_id(aura.id)
    host_oid = s.state.rules.object_id(walker.id)
    spell = put(s, 'Disenchant', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'W': 1, 'C': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[aura.id], sources=[])
    roundtrip(s)
    settle(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    assert s.state.rules.lki[aura_oid].attached_object == host_oid
    roundtrip(s)
