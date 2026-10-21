"""CR 508.1b/603.2: conditional defender prohibition and equipped-host damage loyalty."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import combat, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle
from tests.test_rules_wave34b_activated import attack, block, next_turn, priority_to, stops, to_phase

DATA = Path(__file__).parent / 'fixtures/aetherspark_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='asp', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def spark(s, pid='p1'):
    c = put(s, 'The Aetherspark', 'battlefield', pid)
    act(s, pid, type='counter', card_ids=[c.id], kind='loyalty', delta=4)
    return c


def attach(s, equipment, host):
    act(s, equipment.controller, type='attach', card_ids=[equipment.id], to=host.id)


def test_canonical_aetherspark_is_supported(cards):
    assert coverage.of_card_data(cards.resolve('The Aetherspark')).level == 'FULL'


@pytest.mark.parametrize('attached', [False, True])
def test_only_unattached_aetherspark_can_be_declared_as_a_defender(cards, attached):
    s = build(cards, ['Grizzly Bears'], bob=[(1, 'The Aetherspark'), (1, 'Grizzly Bears'), (10, 'Island')])
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    defender = spark(s, 'p2')
    host = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if attached:
        attach(s, defender, host)
    stops(s)
    next_turn(s)
    to_phase(s, 'declare_attackers')
    assert (defender.id in combat.attack_targets(s.state, 'p1', cards)) == (not attached)
    assert (f't:{defender.id}' in {o.id for o in s.state.rules.decision.options}) == (not attached)
    if attached:
        before = s.state.model_dump(mode='json')
        with pytest.raises(ActionError):
            act(s, 'p1', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': defender.id}])
        assert s.state.model_dump(mode='json') == before
    else:
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': defender.id}])
    roundtrip(s)


def test_current_prohibition_is_checked_again_when_submitting_a_declaration(cards):
    s = build(cards, ['Grizzly Bears'], bob=[(1, 'The Aetherspark'), (1, 'Grizzly Bears'), (10, 'Island')])
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    defender = spark(s, 'p2')
    host = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    stops(s)
    next_turn(s)
    to_phase(s, 'declare_attackers')
    assert f't:{defender.id}' in {o.id for o in s.state.rules.decision.options}
    attach(s, defender, host)
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': defender.id}])
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p2'}])
    roundtrip(s)


def test_attaching_after_declaration_does_not_stop_the_existing_attack(cards):
    from tests.test_rules_bandmate_references import mana

    s = build(cards, ['Grizzly Bears', 'Magnetic Theft'], bob=[(1, 'The Aetherspark'), (10, 'Island')])
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    defender = spark(s, 'p2')
    theft = put(s, 'Magnetic Theft', 'hand')
    stops(s)
    next_turn(s)
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': defender.id}])
    priority_to(s, 'p1')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=theft.id, targets=[defender.id, attacker.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[defender.id].attached_to == attacker.id
    assert s.state.cards[attacker.id].attacking.id == defender.id
    to_phase(s, 'main2')
    assert s.state.cards[defender.id].counters['loyalty'] == 2
    assert s.state.cards[defender.id].zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('host_name,expected', [('Grizzly Bears', 2), ('Fencing Ace', 2)])
def test_equipped_host_combat_damage_adds_actual_loyalty_in_each_damage_step(cards, host_name, expected):
    s = build(cards, ['The Aetherspark', host_name])
    source = spark(s)
    host = put(s, host_name, 'battlefield')
    attach(s, source, host)
    stops(s)
    next_turn(s)
    attack(s, host)
    to_phase(s, 'main2')
    assert s.state.players['p2'].life == 40 - expected
    assert s.state.cards[source.id].counters['loyalty'] == 4 + expected
    roundtrip(s)


def test_combat_damage_to_a_creature_triggers_even_when_the_host_dies(cards):
    s = build(cards, ['The Aetherspark', 'Grizzly Bears'], bob=[(1, 'Grizzly Bears'), (10, 'Island')])
    source = spark(s)
    host = put(s, 'Grizzly Bears', 'battlefield')
    defender = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attach(s, source, host)
    stops(s)
    next_turn(s)
    attack(s, host)
    block(s, (defender, host))
    to_phase(s, 'main2')
    assert s.state.cards[host.id].zone == 'p1:graveyard'
    assert s.state.cards[defender.id].zone == 'p2:graveyard'
    assert s.state.cards[source.id].counters['loyalty'] == 6
    assert s.state.cards[source.id].attached_to is None
    roundtrip(s)


def test_noncombat_damage_by_the_equipped_creature_does_not_add_loyalty(cards):
    s = build(cards, ['The Aetherspark', 'Goblin Fireslinger'])
    source = spark(s)
    host = put(s, 'Goblin Fireslinger', 'battlefield')
    attach(s, source, host)
    stops(s)
    next_turn(s)
    act(s, 'p1', type='activate_ability', card_id=host.id, ability=0, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 39
    assert s.state.cards[source.id].counters['loyalty'] == 4
    roundtrip(s)


def test_combat_damage_during_an_opponents_turn_does_not_add_loyalty(cards):
    s = build(cards, ['The Aetherspark', 'Grizzly Bears'], bob=[(1, 'Grizzly Bears'), (10, 'Island')])
    source = spark(s)
    host = put(s, 'Grizzly Bears', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attach(s, source, host)
    stops(s)
    turn = s.state.turn.number + 1
    to_phase(s, 'declare_attackers', turn=turn)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': enemy.id, 'target': 'p1'}])
    to_phase(s, 'declare_blockers', turn=turn)
    act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': host.id, 'attacker_id': enemy.id}])
    to_phase(s, 'main2', turn=turn)
    assert s.state.cards[host.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].counters['loyalty'] == 4
    roundtrip(s)


def test_your_turn_refers_to_equipment_controller_even_with_an_opponents_host(cards):
    s = build(cards, ['The Aetherspark', 'Grizzly Bears'], bob=[(1, 'Grizzly Bears'), (10, 'Island')])
    source = spark(s)
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    host = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attach(s, source, host)
    stops(s)
    next_turn(s)
    attack(s, attacker)
    block(s, (host, attacker))
    to_phase(s, 'main2')
    assert s.state.cards[host.id].zone == 'p2:graveyard'
    assert s.state.cards[source.id].counters['loyalty'] == 6
    roundtrip(s)


@pytest.mark.parametrize('change', ['blink', 'control'])
def test_pending_damage_trigger_keeps_its_original_source_object_and_controller(cards, change):
    s = build(cards, ['The Aetherspark', 'Grizzly Bears'])
    source = spark(s)
    host = put(s, 'Grizzly Bears', 'battlefield')
    attach(s, source, host)
    stops(s)
    next_turn(s)
    attack(s, host)
    to_phase(s, 'combat_damage')
    assert s.state.players['p2'].life == 38
    assert s.state.cards[source.id].counters['loyalty'] == 4
    assert any(e.source_card == source.id for e in s.state.rules.stack.values())
    if change == 'blink':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
        act(s, 'p1', type='counter', card_ids=[source.id], kind='loyalty', delta=4)
    else:
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    roundtrip(s)
    settle(s)
    assert s.state.cards[source.id].counters['loyalty'] == (4 if change == 'blink' else 6)
    roundtrip(s)


def test_prevented_combat_damage_does_not_create_loyalty_trigger(cards):
    from tests.test_rules_bandmate_references import mana

    s = build(cards, ['The Aetherspark', 'Grizzly Bears', 'Holy Day'])
    source = spark(s)
    host = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, 'Holy Day', 'hand')
    attach(s, source, host)
    stops(s)
    next_turn(s)
    attack(s, host)
    priority_to(s, 'p1')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    to_phase(s, 'main2')
    assert s.state.players['p2'].life == 40
    assert s.state.cards[source.id].counters['loyalty'] == 4
    roundtrip(s)


@pytest.mark.parametrize('target', [False, True])
def test_plus_one_ability_attaches_and_counters_only_a_chosen_target(cards, target):
    s = build(cards, ['The Aetherspark', 'Grizzly Bears'])
    source = spark(s)
    host = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[host.id] if target else [], target_counts=[1 if target else 0])
    settle(s)
    assert s.state.cards[source.id].counters['loyalty'] == 5
    assert s.state.cards[source.id].attached_to == (host.id if target else None)
    assert s.state.cards[host.id].counters == ({'+1/+1': 1} if target else {})
    roundtrip(s)


def test_loyalty_counters_from_damage_apply_counter_replacements(cards):
    s = build(cards, ['The Aetherspark', 'Grizzly Bears', 'Doubling Season'])
    source = spark(s)
    host = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    attach(s, source, host)
    stops(s)
    next_turn(s)
    attack(s, host)
    to_phase(s, 'main2')
    assert s.state.players['p2'].life == 38
    assert s.state.cards[source.id].counters['loyalty'] == 8
    roundtrip(s)
