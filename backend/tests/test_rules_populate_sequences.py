"""CR 701.36: each populate chooses independently and remembers its created tokens."""
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
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/populate_sequences_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='pps', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Full Flowering', 'Determined Iteration'])
def test_populate_sequence_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def cast_flowering(s, x):
    spell = put(s, 'Full Flowering', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2 * x, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=x)
    settle(s)


@pytest.mark.parametrize('x', [0, 2])
def test_flowering_makes_independent_choices_and_can_copy_a_new_copy(cards, x):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave5j_token_copies import token, tokens

    s = build(cards, ['Full Flowering', 'Grizzly Bears'])
    bear = token(s, 'p1', 'Bear', '2/2', 'Token Creature — Bear')
    elf = token(s, 'p1', 'Elf', '1/1', 'Token Creature — Elf')
    treasure = token(s, 'p1', 'Treasure', '', 'Token Artifact — Treasure')
    put(s, 'Grizzly Bears', 'battlefield')
    before = {c.id for c in tokens(s)}
    cast_flowering(s, x)
    if x:
        d = s.state.rules.decision
        assert d is not None and {o.id for o in d.options} == {bear.id, elf.id}
        roundtrip(s)
        pick(s, [bear.id])
        settle(s)
        created = {c.id for c in tokens(s)} - before
        assert len(created) == 1
        d = s.state.rules.decision
        assert d is not None and {o.id for o in d.options} == {bear.id, elf.id, *created}
        assert treasure.id not in {o.id for o in d.options}
        roundtrip(s)
        pick(s, list(created))
        settle(s)
    assert s.state.rules.decision is None
    assert len(tokens(s)) == 3 + x
    assert len([c for c in tokens(s) if c.name == 'Bear']) == 1 + x
    roundtrip(s)


def test_flowering_with_no_creature_tokens_does_not_create_anything(cards):
    from tests.test_rules_wave5j_token_copies import token, tokens

    s = build(cards, ['Full Flowering'])
    treasure = token(s, 'p1', 'Treasure', '', 'Token Artifact — Treasure')
    cast_flowering(s, 3)
    assert s.state.rules.decision is None
    assert [c.id for c in tokens(s)] == [treasure.id]
    roundtrip(s)


@pytest.mark.parametrize('doublers', [0, 1, 2])
def test_iteration_only_gives_haste_and_delayed_sacrifice_to_its_new_tokens(cards, doublers):
    from app.rules.plan import Plan
    from tests.test_rules_designations import pick
    from tests.test_rules_review_combat import stops
    from tests.test_rules_wave5j_token_copies import token, tokens
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ['Determined Iteration', 'Parallel Lives', 'Doubling Season'])
    source = put(s, 'Determined Iteration', 'battlefield')
    original = token(s, 'p1', 'Bear', '2/2', 'Token Creature — Bear')
    for name in ['Parallel Lives', 'Doubling Season'][:doublers]:
        put(s, name, 'battlefield')
    stops(s)
    to_phase(s, 'begin_combat', turn=1)
    settle(s)
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            break
        roundtrip(s)
        pick(s, [d.options[0].id])
        settle(s)
    created = {c.id for c in tokens(s)} - {original.id}
    assert len(created) == 2 ** doublers
    plan = Plan(s.state, 'p1', cards, None)
    assert 'haste' not in plan.ch(s.state.cards[original.id]).keywords
    assert all('haste' in plan.ch(s.state.cards[c]).keywords for c in created)
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    to_phase(s, 'end', turn=1)
    settle(s)
    assert [c.id for c in tokens(s)] == [original.id]
    roundtrip(s)


def test_iteration_without_tokens_does_not_give_haste_or_sacrifice_another_creature(cards):
    from app.rules.plan import Plan
    from tests.test_rules_review_combat import stops
    from tests.test_rules_wave5j_token_copies import tokens
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ['Determined Iteration', 'Grizzly Bears'])
    put(s, 'Determined Iteration', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    stops(s)
    to_phase(s, 'begin_combat', turn=1)
    settle(s)
    assert not tokens(s)
    assert 'haste' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).keywords
    roundtrip(s)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[bear.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_iteration_remembers_the_selected_tokens_after_a_choice_and_source_departure(cards):
    from app.rules.plan import Plan
    from tests.test_rules_designations import pick
    from tests.test_rules_review_combat import stops
    from tests.test_rules_wave5j_token_copies import token, tokens
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ['Determined Iteration'])
    source = put(s, 'Determined Iteration', 'battlefield')
    bear = token(s, 'p1', 'Bear', '2/2', 'Token Creature — Bear')
    elf = token(s, 'p1', 'Elf', '1/1', 'Token Creature — Elf')
    before = {bear.id, elf.id}
    stops(s)
    to_phase(s, 'begin_combat', turn=1)
    assert s.state.zones.get('stack')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == before
    roundtrip(s)
    pick(s, [elf.id])
    settle(s)
    created = {c.id for c in tokens(s)} - before
    assert len(created) == 1
    new = s.state.cards[next(iter(created))]
    assert new.name == 'Elf'
    assert 'haste' in Plan(s.state, 'p1', cards, None).ch(new).keywords
    roundtrip(s)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert {c.id for c in tokens(s)} == before
    roundtrip(s)


def test_each_repeated_populate_gets_its_own_token_replacement(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave5j_token_copies import token, tokens

    s = build(cards, ['Full Flowering', 'Parallel Lives'])
    original = token(s, 'p1', 'Bear', '2/2', 'Token Creature — Bear')
    put(s, 'Parallel Lives', 'battlefield')
    cast_flowering(s, 2)
    created = {c.id for c in tokens(s)} - {original.id}
    assert len(created) == 2
    assert s.state.rules.decision is not None
    roundtrip(s)
    pick(s, [sorted(created)[0]])
    settle(s)
    assert len(tokens(s)) == 5
    roundtrip(s)
