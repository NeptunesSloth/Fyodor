"""Actual revealed-card outcomes, rather than parser-only claims."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/qualified_look_outcomes_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='qlo', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def mana(s, pid='p1'):
    act(s, pid, type='add_mana', player=pid, mana={'C': 30, 'W': 8, 'U': 8, 'B': 8, 'R': 8, 'G': 8})


def cast(s, name, targets=(), pid='p1'):
    from tests.test_rules_bandmate_references import wait_priority

    source = put(s, name, 'hand', pid)
    mana(s, pid)
    wait_priority(s, pid)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[],
        **({'target_counts': [len(targets)]} if name == 'Kaboom!' else {}))
    settle(s)
    return source


def test_mantle_actual_equip_attack_selects_shared_type(cards):
    s = table(cards, ["Conjurer's Mantle", 'Grizzly Bears', 'Runeclaw Bear', 'Llanowar Elves', 'Fervor'])
    mantle = put(s, "Conjurer's Mantle", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    found = put(s, 'Runeclaw Bear', 'library')
    elf = put(s, 'Llanowar Elves', 'library')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=mantle.id, ability=2, targets=[bear.id])
    settle(s)
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and found.id in {o.id for o in d.options}
    assert elf.id not in {o.id for o in d.options}
    assert not s.view('p2')['cards'].get(found.id, {}).get('name')
    pick(s, [found.id])
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:hand'
    assert s.state.cards[elf.id].zone == 'p1:library'
    assert not s.state.cards[elf.id].revealed_to
    roundtrip(s)


@pytest.mark.parametrize('name', ['Delver of Secrets // Insectile Aberration', 'Bala Ged Recovery // Bala Ged Sanctuary', 'Bruna, the Fading Light'])
def test_pest_all_three_physical_double_faced_kinds_are_eligible(cards, name):
    s = table(cards, ['Overgrown Pest', name, 'Grizzly Bears'])
    found = put(s, name, 'library')
    bear = put(s, 'Grizzly Bears', 'library')
    cast(s, 'Overgrown Pest')
    d = s.state.rules.decision
    assert d is not None and found.id in {o.id for o in d.options}
    assert bear.id not in {o.id for o in d.options}
    pick(s, [found.id])
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:hand'
    assert s.state.cards[bear.id].zone == 'p1:library'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Bonecrusher Giant // Stomp', 'Fire // Ice'])
def test_pest_adventure_and_split_are_not_double_faced(cards, name):
    s = table(cards, ['Overgrown Pest', name])
    found = put(s, name, 'library')
    cast(s, 'Overgrown Pest')
    d = s.state.rules.decision
    assert d is not None and found.id not in {o.id for o in d.options}
    pick(s, [])
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:library'
    roundtrip(s)


def test_radagast_actual_cast_looks_own_mana_value_and_disjoint_type(cards):
    s = table(cards, ['Radagast the Brown', 'Grizzly Bears'])
    found = put(s, 'Grizzly Bears', 'library')
    cast(s, 'Radagast the Brown')
    d = s.state.rules.decision
    assert d is not None and found.id in {o.id for o in d.options}
    assert not s.state.cards[found.id].revealed_to
    pick(s, [found.id])
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('gained', [False, True])
def test_lumarets_gain_history_not_net_life_selects_one_or_two(cards, gained):
    s = table(cards, ['Follow the Lumarets', 'Grizzly Bears', 'Llanowar Elves', 'Revitalize', 'Lightning Bolt'])
    if gained:
        cast(s, 'Revitalize')
        cast(s, 'Lightning Bolt', ['p1'])
        assert s.state.players['p1'].life == 40
    bear = put(s, 'Grizzly Bears', 'library')
    elf = put(s, 'Llanowar Elves', 'library')
    cast(s, 'Follow the Lumarets')
    d = s.state.rules.decision
    assert d is not None and d.max_choices == (2 if gained else 1)
    pick(s, [bear.id, elf.id] if gained else [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:hand'
    assert s.state.cards[elf.id].zone == ('p1:hand' if gained else 'p1:library')
    roundtrip(s)


@pytest.mark.parametrize('name', ['Overgrown Pest', 'Radagast the Brown', 'Follow the Lumarets'])
def test_private_qualified_choice_survives_fresh_process(cards, tmp_path, name):
    from tests.test_rules_reveal_outcomes import cold_answer

    s = table(cards, [name, 'Grizzly Bears', 'Bala Ged Recovery // Bala Ged Sanctuary'])
    found = put(s, 'Bala Ged Recovery // Bala Ged Sanctuary' if name == 'Overgrown Pest' else 'Grizzly Bears', 'library')
    cast(s, name)
    assert s.state.rules.decision is not None
    assert found.id in {o.id for o in s.state.rules.decision.options}
    assert not s.view('p2')['cards'].get(found.id, {}).get('name')
    s = cold_answer(s, cards, tmp_path, [found.id])
    assert s.state.cards[found.id].zone == 'p1:hand'
    assert s.history.rebuild() == s.state


def test_mantle_can_find_noncreature_kindred_card(cards):
    s = table(cards, ["Conjurer's Mantle", 'Llanowar Elves', 'Elvish Promenade', 'Fervor'])
    mantle = put(s, "Conjurer's Mantle", 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    found = put(s, 'Elvish Promenade', 'library')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=mantle.id, ability=2, targets=[elf.id])
    settle(s)
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': elf.id, 'target': 'p2'}])
    settle(s)
    assert s.state.rules.decision is not None
    assert found.id in {o.id for o in s.state.rules.decision.options}
    pick(s, [found.id])
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:hand'
    roundtrip(s)


def test_radagast_self_token_triggers_but_other_token_does_not(cards):
    s = table(cards, ['Radagast the Brown', 'Mirror Box', 'Cackling Counterpart', 'Grizzly Bears'])
    original = put(s, 'Radagast the Brown', 'battlefield')
    put(s, 'Mirror Box', 'battlefield')
    found = put(s, 'Grizzly Bears', 'library')
    cast(s, 'Cackling Counterpart', [original.id])
    assert s.state.rules.decision is not None
    assert found.id in {o.id for o in s.state.rules.decision.options}
    pick(s, [found.id])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[found.id].zone == 'p1:hand'
    assert len([c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.token]) == 1
    roundtrip(s)


def test_mantle_dead_attacker_uses_exact_last_creature_types_and_cold_resume(cards, tmp_path):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_reveal_outcomes import cold_answer

    s = table(cards, ["Conjurer's Mantle", 'Grizzly Bears', 'Runeclaw Bear', 'Fervor'], ['Murder'])
    mantle = put(s, "Conjurer's Mantle", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    found = put(s, 'Runeclaw Bear', 'library')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=mantle.id, ability=2, targets=[bear.id])
    settle(s)
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    murder = put(s, 'Murder', 'hand', 'p2')
    mana(s, 'p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=murder.id, targets=[bear.id], sources=[])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    assert s.state.rules.decision is not None
    assert found.id in {o.id for o in s.state.rules.decision.options}
    s = cold_answer(s, cards, tmp_path, [found.id])
    assert s.state.cards[found.id].zone == 'p1:hand'


def test_radagast_filters_against_all_current_creature_types(cards):
    s = table(cards, ['Radagast the Brown', 'Llanowar Elves', 'Grizzly Bears', 'Runeclaw Bear'])
    put(s, 'Grizzly Bears', 'battlefield')
    bear = put(s, 'Runeclaw Bear', 'library')
    elf = put(s, 'Llanowar Elves', 'library')
    cast(s, 'Radagast the Brown')
    assert s.state.rules.decision is not None
    options = {o.id for o in s.state.rules.decision.options}
    assert elf.id in options and bear.id not in options
    pick(s, [])
    settle(s)
    assert s.state.cards[elf.id].zone == 'p1:library'
    assert s.state.cards[bear.id].zone == 'p1:library'
    roundtrip(s)
