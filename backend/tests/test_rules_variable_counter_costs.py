"""CR 601.2b/h, 118.3: variable counter costs are announced and paid in full."""
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
from tests.test_rules_designations import build as base_build
from tests.test_rules_designations import put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/variable_counter_cost_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='vcc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['The Astonishing Ant-Man', 'Geistflame Reservoir', 'Rasputin, the Oneiromancer', 'Simic Manipulator', 'Ooze Flux', 'Loot, the Pathfinder', 'The Filigree Sylex'])
def test_variable_counter_cost_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def build(*args, **kwargs):
    s = base_build(*args, **kwargs)
    for pid in ['p1', 'p2']:
        act(s, pid, type='set_prefs', response='on')
    return s


def counter(s, card, kind, n):
    act(s, 'p1', type='set_counter', card_id=card.id, kind=kind, value=n)


@pytest.mark.parametrize('n', [0, 2, 3])
def test_ant_man_announces_and_pays_the_counter_number_then_creates_that_many_tokens(cards, n):
    from tests.test_rules_wave5j_token_copies import tokens
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ['The Astonishing Ant-Man'])
    source = put(s, 'The Astonishing Ant-Man', 'battlefield')
    next_turn(s)
    counter(s, source, '+1/+1', 3)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'G': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, x_value=n)
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == 3 - n
    assert s.state.cards[source.id].tapped
    roundtrip(s)
    settle(s)
    made = tokens(s)
    assert len(made) == n and all(c.name == 'Insect' for c in made)
    roundtrip(s)


def test_ant_man_cannot_remove_more_counters_than_it_has(cards):
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ['The Astonishing Ant-Man'])
    source = put(s, 'The Astonishing Ant-Man', 'battlefield')
    next_turn(s)
    counter(s, source, '+1/+1', 1)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'G': 1})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, x_value=2)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


@pytest.mark.parametrize('n', [0, 2])
def test_reservoir_uses_counters_paid_even_after_source_leaves(cards, n):
    s = build(cards, ['Geistflame Reservoir'])
    source = put(s, 'Geistflame Reservoir', 'battlefield')
    counter(s, source, 'charge', 3)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'R': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, x_value=n, targets=['p2'])
    assert s.state.cards[source.id].counters.get('charge', 0) == 3 - n
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    roundtrip(s)
    settle(s)
    assert s.state.players['p2'].life == 40 - n
    roundtrip(s)


def test_one_or_more_rejects_zero_without_paying_any_cost(cards):
    s = build(cards, ['Ooze Flux', 'Grizzly Bears'])
    source = put(s, 'Ooze Flux', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    counter(s, bear, '+1/+1', 2)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=0)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_ooze_flux_removes_the_announced_total_across_multiple_creatures(cards):
    from app.rules.plan import Plan
    from tests.test_rules_designations import pick
    from tests.test_rules_wave5j_token_copies import tokens

    s = build(cards, ['Ooze Flux', 'Grizzly Bears', 'Llanowar Elves'])
    source = put(s, 'Ooze Flux', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    counter(s, bear, '+1/+1', 3)
    counter(s, elf, '+1/+1', 2)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=3)
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 5
    roundtrip(s)
    chosen = [o.id for o in d.options if o.card_id == bear.id][:2] + [o.id for o in d.options if o.card_id == elf.id][:1]
    pick(s, chosen)
    assert s.state.cards[bear.id].counters.get('+1/+1') == 1
    assert s.state.cards[elf.id].counters.get('+1/+1') == 1
    roundtrip(s)
    settle(s)
    made = tokens(s)
    assert len(made) == 1 and made[0].name == 'Ooze'
    ch = Plan(s.state, 'p1', cards, None).ch(made[0])
    assert ch.power == '3' and ch.toughness == '3'
    roundtrip(s)


@pytest.mark.parametrize('grow_target', [False, True])
def test_manipulator_targets_use_announced_payment_and_recheck_power_on_resolution(cards, grow_target):
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ['Simic Manipulator'], bob=((1, 'Grizzly Bears'), (10, 'Island')))
    source = put(s, 'Simic Manipulator', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    next_turn(s)
    counter(s, source, '+1/+1', 3)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, x_value=1, targets=[bear.id])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, x_value=2, targets=[bear.id])
    assert s.state.cards[source.id].counters.get('+1/+1') == 1
    counter(s, source, '+1/+1', 5)
    if grow_target:
        counter(s, bear, '+1/+1', 1)
    from app.rules.plan import Plan
    from app.rules.sba import power
    actual_power = power(s.state.cards[bear.id], Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]))
    assert actual_power == (3 if grow_target else 2)
    assert next(iter(s.state.rules.stack.values())).x == 2
    roundtrip(s)
    settle(s)
    assert s.state.cards[bear.id].controller == ('p2' if grow_target else 'p1')
    roundtrip(s)


def test_ooze_flux_hints_require_at_least_one_counter(cards):
    from app.rules.casting import activatable

    s = build(cards, ['Ooze Flux', 'Grizzly Bears'])
    source = put(s, 'Ooze Flux', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    assert not any(h['card_id'] == source.id for h in activatable(s.state, 'p1', cards))
    counter(s, bear, '+1/+1', 1)
    hint = next(h for h in activatable(s.state, 'p1', cards) if h['card_id'] == source.id)
    assert hint.get('x')
    roundtrip(s)


def test_rasputin_named_self_cost_produces_the_chosen_amount_without_the_stack(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave5j_token_copies import tokens
    from tests.test_rules_wave30m_durations import three, to_phase

    s = three(cards, ['Rasputin, the Oneiromancer'])
    source = put(s, 'Rasputin, the Oneiromancer', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'W': 1, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].counters.get('dream') == 2
    assert len(tokens(s, 'p2')) == 1 and len(tokens(s, 'p3')) == 1
    for pid in ['p1', 'p2', 'p3']:
        act(s, pid, type='set_prefs', response='on')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='clear_mana', player='p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 2
    assert all(o.label != '{0}' for o in d.options)
    roundtrip(s)
    pick(s, ['1'])
    assert mana_pool(s).get('C') == 2
    assert not s.state.cards[source.id].counters.get('dream')
    assert s.state.cards[source.id].tapped
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_named_mana_counter_cost_requires_the_actual_source_name(cards):
    from app.rules.mana import parse_mana_ability

    text = '{T}, Remove one or more dream counters from Rasputin: Add that much {C}.'
    assert parse_mana_ability(text) is None
    assert parse_mana_ability(text, card_name='Grizzly Bears') is None
    assert parse_mana_ability(text, card_name='Rasputin, the Oneiromancer') is not None


def test_ooze_flux_refuses_a_total_larger_than_all_available_counters(cards):
    s = build(cards, ['Ooze Flux', 'Grizzly Bears'])
    source = put(s, 'Ooze Flux', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    counter(s, bear, '+1/+1', 2)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=3)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_zero_is_a_legal_any_number_payment_even_without_counters(cards):
    from tests.test_rules_wave5j_token_copies import tokens
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ['The Astonishing Ant-Man'])
    source = put(s, 'The Astonishing Ant-Man', 'battlefield')
    next_turn(s)
    counter(s, source, '+1/+1', 0)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'G': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, x_value=0)
    assert s.state.cards[source.id].tapped
    roundtrip(s)
    settle(s)
    assert not tokens(s)
    roundtrip(s)


def test_independent_variable_costs_remain_unsupported():
    from app.rules.costs import parse_ability_cost

    cost = parse_ability_cost('{X}, Remove any number of charge counters from this artifact')
    assert cost.unsupported


def test_counter_reference_must_match_the_counter_paid():
    from app.rules import removed_all
    from app.rules.costs import parse_ability_cost

    cost = parse_ability_cost('Remove one or more +1/+1 counters from this creature')
    assert removed_all.rewrite('Create an X/X green Ooze creature token, where X is the number of charge counters removed this way.', cost) is None


def loot_mana(s, source):
    from tests.test_rules_designations import pick

    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    d = s.state.rules.decision
    assert d is not None
    red = next(o.id for o in d.options if o.label == '{R}{R}{R}')
    roundtrip(s)
    pick(s, [red])


def test_loots_mana_exhaust_pays_green_and_each_ability_has_its_own_limit(cards):
    s = build(cards, ['Loot, the Pathfinder', 'The Filigree Sylex'])
    source = put(s, 'Loot, the Pathfinder', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1})
    loot_mana(s, source)
    assert mana_pool(s).get('R') == 3
    assert not mana_pool(s).get('G')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'U': 1})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert s.state.model_dump(mode='json') == before
    hand = len(s.state.zones.get('p1:hand', []))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == hand + 3
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=3, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_loots_mana_exhaust_becomes_usable_again_as_a_new_object(cards):
    s = build(cards, ['Loot, the Pathfinder', 'The Filigree Sylex'])
    source = put(s, 'Loot, the Pathfinder', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 2})
    loot_mana(s, source)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    loot_mana(s, source)
    assert mana_pool(s).get('R') == 6
    assert not mana_pool(s).get('G')
    roundtrip(s)


@pytest.mark.parametrize('source_counters', [0, 4, 10])
def test_sylex_can_remove_oil_before_sacrificing_the_same_source(cards, source_counters):
    s = build(cards, ['The Filigree Sylex', 'Sol Ring'])
    source = put(s, 'The Filigree Sylex', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    counter(s, source, 'oil', source_counters)
    counter(s, ring, 'oil', 10 - source_counters)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, targets=['p2'])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert not s.state.cards[ring.id].counters.get('oil')
    roundtrip(s)
    settle(s)
    assert s.state.players['p2'].life == 30
    roundtrip(s)


def test_sylex_refuses_nine_counters_without_tapping_or_sacrificing(cards):
    s = build(cards, ['The Filigree Sylex'])
    source = put(s, 'The Filigree Sylex', 'battlefield')
    counter(s, source, 'oil', 9)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, targets=['p2'])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)
