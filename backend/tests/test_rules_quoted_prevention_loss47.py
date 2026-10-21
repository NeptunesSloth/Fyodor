"""Isolated candidate proofs for typed exact quoted prevention-ability loss."""
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
from tests.test_rules_combat_prevention_variants47 import DATA
from tests.test_rules_damage_redirection import activate, cast
from tests.test_rules_designations import put, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    rows = [*DATA, *json.loads((Path(__file__).parent / 'fixtures/prevention47_copy_support.json').read_text())]
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(rows):
        base[row['name']] = card(row['name'], set_code='q47', number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names = ['Glittering Lynx', 'Glittering Lion', 'Lightning Bolt', 'Dawn Elemental', 'Mirrorweave']
    return table(cards, names, names, names)


@pytest.mark.parametrize('name', ['Glittering Lynx', 'Glittering Lion'])
def test_native_opponent_pays_activation_and_exact_quoted_loss_retains_other_ability(cards, name):
    s = game(cards)
    source = put(s, name, 'battlefield')
    cast(s, 'Lightning Bolt', [source.id], pid='p2')
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].damage == 0
    activate(s, source, 'loses', pid='p2')
    assert any(a.kind == 'activated' for a in chars(s, source).abilities)
    assert not any(a.kind == 'static' and 'Prevent all damage' in a.text for a in chars(s, source).abilities)
    cast(s, 'Lightning Bolt', [source.id], pid='p2')
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('timing', ['before_resolution', 'after_resolution'])
def test_native_source_blink_preserves_new_incarnation_ability(cards, timing):
    s = game(cards)
    source = put(s, 'Glittering Lynx', 'battlefield')
    original = s.state.rules.object_id(source.id)
    activate(s, source, 'loses', pid='p2', resolve=timing == 'after_resolution')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert s.state.rules.object_id(source.id) != original
    if timing == 'before_resolution':
        assert not any(e.lose_quoted_ability for e in s.state.rules.effects)
    cast(s, 'Lightning Bolt', [source.id], pid='p2')
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].damage == 0


def test_native_quoted_loss_cleanup_restores_prevention(cards):
    s = game(cards)
    source = put(s, 'Glittering Lion', 'battlefield')
    activate(s, source, 'loses', pid='p2')
    to_phase(s, 'main1', turn=2)
    cast(s, 'Lightning Bolt', [source.id], pid='p2')
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].damage == 0


def test_real_mirrorweave_after_loss_changes_printed_index_but_keeps_flying_and_removes_matching_ability(cards):
    s = game(cards)
    source = put(s, 'Glittering Lynx', 'battlefield')
    model = put(s, 'Dawn Elemental', 'battlefield')
    original = s.state.rules.object_id(source.id)
    activate(s, source, 'loses', pid='p2')
    cast(s, 'Mirrorweave', [model.id])
    current = chars(s, source)
    assert current.name == 'Dawn Elemental' and 'flying' in current.keywords
    assert s.state.rules.object_id(source.id) == original
    assert not any(a.kind == 'static' and 'Prevent all damage' in a.text for a in current.abilities)
    cast(s, 'Lightning Bolt', [source.id], pid='p2')
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    cast(s, 'Lightning Bolt', [model.id])
    assert s.state.cards[model.id].zone == 'p1:battlefield' and s.state.cards[model.id].damage == 0


@pytest.mark.parametrize('later', [False, True])
def test_native_multiple_matching_grants_obey_loss_timestamp_without_changing_grant_policy(cards, later):
    """Native layer input only: no claim that a new printed quoted-grant producer is admitted."""
    from app.game.session import GameSession
    from app.rules import layers
    from app.rules import quoted_prevention_loss47 as loss
    from app.rules.plan import Plan

    s = game(cards)
    source = put(s, 'Glittering Lynx', 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    layers.add_effect(plan, affected=[plan.oid(source.id)], layer='6', source=plan.oid(source.id),
                      controller='p1', add_abilities=[loss.ABILITY, loss.ABILITY])
    s = GameSession(plan.state, cards=cards)
    assert sum(loss.matches(a.text, chars(s, source).name) for a in chars(s, source).abilities) == 3
    activate(s, s.state.cards[source.id], 'loses', pid='p2')
    if later:
        plan = Plan(s.state, 'p1', cards, None)
        layers.add_effect(plan, affected=[plan.oid(source.id)], layer='6', source=plan.oid(source.id),
                          controller='p1', add_abilities=[loss.ABILITY])
        s = GameSession(plan.state, cards=cards)
    current = chars(s, s.state.cards[source.id])
    assert sum(loss.matches(a.text, current.name) for a in current.abilities) == int(later)
    cast(s, 'Lightning Bolt', [source.id], pid='p2')
    assert s.state.cards[source.id].zone == ('p1:battlefield' if later else 'p1:graveyard')


@pytest.mark.parametrize('stage', ['announced', 'resolved'])
def test_real_fresh_process_native_quoted_loss_and_definition_rediscovery(cards, tmp_path, stage):
    import subprocess
    import sys

    s = game(cards)
    source = put(s, 'Glittering Lynx', 'battlefield')
    activate(s, source, 'loses', pid='p2', resolve=stage == 'resolved')
    save = tmp_path / f'quoted-loss-{stage}.json'
    save.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_damage_redirection import cast
from tests.test_rules_designations import settle,roundtrip
from tests.test_rules_wave6c_tokens_pumps import chars
save,db,source=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
settle(s)
assert len([e for e in s.state.rules.effects if e.lose_quoted_ability])==1
assert any(a.kind=='activated' for a in chars(s,s.state.cards[source]).abilities)
assert not any(a.kind=='static' and 'Prevent all damage' in a.text for a in chars(s,s.state.cards[source]).abilities)
roundtrip(s)
cast(s,'Lightning Bolt',[source],pid='p2')
assert s.state.cards[source].zone=='p1:graveyard'
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), source.id],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('later', [False, True])
def test_low_level_native_static_matching_grant_filters_by_actual_source_timestamp(cards, monkeypatch, later):
    """A native Static input tests the consumer; it does not admit a quoted-grant card."""
    from app.rules import layers, statics
    from app.rules import quoted_prevention_loss47 as loss

    names = ['Glittering Lynx', 'Lightning Bolt', 'Fervor']
    s = table(cards, names, names, names)
    source = put(s, 'Glittering Lynx', 'battlefield')
    granter = put(s, 'Fervor', 'battlefield')
    recipe = statics.parse('Creatures you control have flying.')
    assert recipe is not None
    recipe = {**recipe, 'keywords': [], 'grants': [loss.ABILITY]}
    native_table = layers.statics

    def native_static_input(state, info):
        found = native_table(state, info)
        actual = state.cards[granter.id]
        if actual.zone.endswith(':battlefield'):
            return [*found, layers.Static(actual.id, actual.controller, recipe, layers.timestamp(state, actual.id))]
        return found

    monkeypatch.setattr(layers, 'statics', native_static_input)
    activate(s, source, 'loses', pid='p2')
    if later:
        act(s, 'p1', type='move', card_ids=[granter.id], to={'player': 'p1', 'zone': 'graveyard'})
        act(s, 'p1', type='move', card_ids=[granter.id], to={'player': 'p1', 'zone': 'battlefield'})
    current = chars(s, source)
    assert 'haste' in current.keywords
    assert sum(loss.matches(a.text, current.name) for a in current.abilities) == int(later)
    cast(s, 'Lightning Bolt', [source.id], pid='p2')
    assert s.state.cards[source.id].zone == ('p1:battlefield' if later else 'p1:graveyard')


@pytest.mark.parametrize('grant_after_wipe', [False, True])
def test_native_actual_all_ability_loss_orders_with_specific_loss_and_resolved_grants(cards, grant_after_wipe):
    """Only the native grant input is low-level; Turn to Frog and loss activation are printed."""
    from app.game.session import GameSession
    from app.rules import layers
    from app.rules import quoted_prevention_loss47 as loss
    from app.rules.plan import Plan

    names = ['Glittering Lynx', 'Lightning Bolt', 'Turn to Frog']
    s = table(cards, names, names, names)
    source = put(s, 'Glittering Lynx', 'battlefield')
    activate(s, source, 'loses', pid='p2')
    if not grant_after_wipe:
        plan = Plan(s.state, 'p1', cards, None)
        layers.add_effect(plan, affected=[plan.oid(source.id)], layer='6', source=plan.oid(source.id),
                          controller='p1', add_abilities=[loss.ABILITY])
        s = GameSession(plan.state, cards=cards)
    cast(s, 'Turn to Frog', [source.id])
    if grant_after_wipe:
        plan = Plan(s.state, 'p1', cards, None)
        layers.add_effect(plan, affected=[plan.oid(source.id)], layer='6', source=plan.oid(source.id),
                          controller='p1', add_abilities=[loss.ABILITY])
        s = GameSession(plan.state, cards=cards)
    current = chars(s, s.state.cards[source.id])
    assert not any(a.kind == 'activated' for a in current.abilities)
    assert sum(loss.matches(a.text, current.name) for a in current.abilities) == int(grant_after_wipe)
    cast(s, 'Lightning Bolt', [source.id], pid='p2')
    assert s.state.cards[source.id].zone == ('p1:battlefield' if grant_after_wipe else 'p1:graveyard')


@pytest.mark.parametrize('name', ['Glittering Lynx', 'Glittering Lion'])
def test_native_countered_loss_ability_keeps_prevention_and_actual_opponent_cost_paid(cards, name):
    names = [name, 'Lightning Bolt', 'Stifle']
    s = table(cards, names, names, names)
    source = put(s, name, 'battlefield')
    activate(s, source, 'loses', pid='p2', resolve=False)
    entry = next(reversed(s.state.rules.stack))
    receipt = s.state.rules.payments[s.state.rules.object_id(entry)]
    assert receipt.controller == 'p2' and sum(receipt.mana_spent.values()) == (2 if name == 'Glittering Lynx' else 3)
    cast(s, 'Stifle', [entry])
    assert not any(e.lose_quoted_ability for e in s.state.rules.effects)
    cast(s, 'Lightning Bolt', [source.id], pid='p2')
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].damage == 0


@pytest.mark.parametrize('name', ['Glittering Lynx', 'Glittering Lion'])
def test_native_unpreventable_damage_ignores_original_prevention_ability(cards, name):
    names = [name, 'Lightning Bolt', 'Skullcrack']
    s = table(cards, names, names, names)
    source = put(s, name, 'battlefield')
    cast(s, 'Skullcrack', ['p1'], pid='p2')
    cast(s, 'Lightning Bolt', [source.id], pid='p2')
    assert s.state.cards[source.id].zone == 'p1:graveyard'


@pytest.mark.parametrize('text,expected', [
    ('Prevent all damage that would be dealt to ~.', True),
    ('Prevent all damage that would be dealt to this creature.', True),
    ('Prevent all damage that would be dealt to this permanent', True),
    ('Prevent all damage that would be dealt to Dawn Elemental.', True),
    ('Prevent all combat damage that would be dealt to this creature.', False),
    ('Prevent all damage that would be dealt by this creature.', False),
    ('Prevent all damage that would be dealt to you.', False),
    ('As long as you control a Plains, prevent all damage that would be dealt to this creature.', False),
])
def test_exact_specific_ability_identity_and_distinct_abilities(text, expected):
    from app.rules import quoted_prevention_loss47 as loss

    assert loss.matches(text, 'Dawn Elemental') is expected


def test_unknown_loss_descriptor_is_rejected_by_native_saved_state_schema(cards):
    from pydantic import ValidationError

    from app.game.state import GameState

    s = game(cards)
    source = put(s, 'Glittering Lynx', 'battlefield')
    activate(s, source, 'loses', pid='p2')
    data = s.state.model_dump(mode='json')
    effect = next(e for e in data['rules']['effects'] if e.get('lose_quoted_ability'))
    effect['lose_quoted_ability'] = 'flying'
    with pytest.raises(ValidationError, match='lose_quoted_ability'):
        GameState.model_validate(data)
