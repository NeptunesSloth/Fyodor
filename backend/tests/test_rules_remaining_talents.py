"""Enchanted planeswalker activation and damage events for the Talent Aura family."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/remaining_talent_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()





NAMES = ["Elspeth's Talent", "Rowan's Talent", "Liliana's Talent"]


def pay(s, player, name):
    from collections import Counter

    from app.rules import mana
    cost = mana.parse_cost(s.cards.resolve(name)['mana_cost'])
    pool = dict(Counter(cost.colored))
    if cost.generic:
        pool['C'] = cost.generic
    act(s, player, type='add_mana', player=player, mana=pool)


def setup(cards, name):
    s = table(cards, ['Jace Beleren', name, 'Koth of the Hammer', 'Grizzly Bears', 'Shock'],
              ['Grizzly Bears', 'Prodigal Pyromancer', 'Stifle', 'Shock', 'Disenchant'], ['Grizzly Bears'])
    walker = put(s, 'Jace Beleren', 'hand')
    pay(s, 'p1', 'Jace Beleren')
    act(s, 'p1', type='cast_spell', card_id=walker.id, sources=[])
    settle(s)
    aura = put(s, name, 'hand')
    pay(s, 'p1', name)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[walker.id], sources=[])
    settle(s)
    assert s.state.cards[aura.id].attached_to == walker.id
    return s, walker, aura


def stats(s, c):
    from app.rules.plan import Plan
    return Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_elspeth_pump_resolves_before_activated_ability_creates_soldiers(cards):
    from tests.test_rules_wave7b_activation import ability_index
    s, walker, _ = setup(cards, "Elspeth's Talent")
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Create three'))
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    assert stats(s, bear).pt == (4, 4) and 'vigilance' in stats(s, bear).keywords
    soldiers = [c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.token and c.token.name == 'Soldier']
    assert len(soldiers) == 3
    assert all(stats(s, c).pt == (1, 1) and 'vigilance' not in stats(s, c).keywords for c in soldiers)
    roundtrip(s)


def test_rowan_copies_loyalty_ability_without_paying_or_activating_again(cards):
    from tests.test_rules_wave7b_activation import ability_index
    s, walker, _ = setup(cards, "Rowan's Talent")
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Up to one target'),
        targets=[bear.id], target_counts=[1])
    for _ in range(30):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        ids = {o.id for o in d.options}
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep'] if 'keep' in ids else [bear.id])
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    assert stats(s, bear).pt == (6, 2)
    assert {'first strike', 'trample'} <= stats(s, bear).keywords
    assert not s.state.rules.stack
    roundtrip(s)


def test_liliana_destroys_creature_that_deals_damage_to_host(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index
    s, walker, _ = setup(cards, "Liliana's Talent")
    creature = put(s, 'Prodigal Pyromancer', 'battlefield', pid='p2')
    act(s, 'p1', type='next_turn', player='p2', force=True)  # the Pyromancer has begun its controller's turn
    act(s, 'p2', type='pass_priority')
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=creature.id, ability=ability_index(s, creature, 'deals 1 damage'), targets=[walker.id])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 2
    assert s.state.cards[creature.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_elspeth_does_not_trigger_for_another_planeswalkers_loyalty(cards):
    from tests.test_rules_wave7b_activation import ability_index
    s, _, _ = setup(cards, "Elspeth's Talent")
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Koth of the Hammer', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=other.id, kind='loyalty', value=3)
    act(s, 'p1', type='activate_ability', card_id=other.id, ability=ability_index(s, other, 'Add {R}'))
    settle(s)
    assert stats(s, bear).pt == (2, 2) and 'vigilance' not in stats(s, bear).keywords
    roundtrip(s)


@pytest.mark.parametrize('aura_controller,walker_controller', [('p2', 'p1'), ('p1', 'p2'), ('p2', 'p2')])
def test_elspeth_matches_both_activator_and_host_identity(cards, aura_controller, walker_controller):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    s, walker, aura = setup(cards, "Elspeth's Talent")
    mine = put(s, 'Grizzly Bears', 'battlefield')
    theirs = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    if aura_controller != 'p1':
        act(s, 'p1', type='set_controller', card_ids=[aura.id], player=aura_controller)
    if walker_controller != 'p1':
        act(s, 'p1', type='set_controller', card_ids=[walker.id], player=walker_controller)
        to_phase(s, 'main1', turn=2)
        wait_priority(s, walker_controller)
    act(s, walker_controller, type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Create three'))
    settle(s)
    assert stats(s, mine).pt == (2, 2)
    assert stats(s, theirs).pt == ((4, 4) if aura_controller == walker_controller else (2, 2))
    roundtrip(s)


def test_rowan_copy_can_choose_different_target_and_shares_only_original_cost(cards):
    from tests.test_rules_wave7b_activation import ability_index
    s, walker, _ = setup(cards, "Rowan's Talent")
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Up to one target'),
        targets=[first.id], target_counts=[1])
    settle(s)
    d = s.state.rules.decision
    assert d and second.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[second.id])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    assert stats(s, first).pt == (4, 2) and stats(s, second).pt == (4, 2)
    assert {'first strike', 'trample'} <= stats(s, first).keywords & stats(s, second).keywords
    roundtrip(s)


def test_stifling_rowan_trigger_prevents_copy_but_not_original_ability(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index
    s, walker, aura = setup(cards, "Rowan's Talent")
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Up to one target'),
        targets=[bear.id], target_counts=[1])
    trigger = next(sid for sid, e in s.state.rules.stack.items() if e.source_card == aura.id)
    counter = put(s, 'Stifle', 'hand', pid='p2')
    pay(s, 'p2', 'Stifle')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[trigger], sources=[])
    settle(s)
    assert stats(s, bear).pt == (4, 2)
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    roundtrip(s)


def pyromancer_ready(s):
    from tests.test_rules_bandmate_references import wait_priority
    creature = put(s, 'Prodigal Pyromancer', 'battlefield', pid='p2')
    act(s, 'p1', type='next_turn', player='p2', force=True)
    act(s, 'p2', type='pass_priority')
    wait_priority(s, 'p2')
    return creature


def pyro_damage(s, creature, target):
    from tests.test_rules_wave7b_activation import ability_index
    act(s, 'p2', type='activate_ability', card_id=creature.id, ability=ability_index(s, creature, 'deals 1 damage'), targets=[target.id])


def test_liliana_does_not_watch_another_planeswalker(cards):
    s, walker, _ = setup(cards, "Liliana's Talent")
    other = put(s, 'Koth of the Hammer', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=other.id, kind='loyalty', value=3)
    creature = pyromancer_ready(s)
    pyro_damage(s, creature, other)
    settle(s)
    assert s.state.cards[creature.id].zone == 'p2:battlefield'
    assert s.state.cards[other.id].counters['loyalty'] == 2
    assert s.state.cards[walker.id].counters['loyalty'] == 3
    roundtrip(s)


def test_liliana_triggers_even_when_damage_kills_the_host_and_aura(cards):
    s, walker, aura = setup(cards, "Liliana's Talent")
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=1)
    creature = pyromancer_ready(s)
    pyro_damage(s, creature, walker)
    settle(s)
    assert s.state.cards[walker.id].zone == 'p1:graveyard'
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    assert s.state.cards[creature.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_liliana_granted_ultimate_returns_all_players_creatures_under_your_control(cards):
    from tests.test_rules_wave7b_activation import ability_index
    s, walker, aura = setup(cards, "Liliana's Talent")
    dead = [put(s, 'Grizzly Bears', 'graveyard', pid=p) for p in ('p1', 'p2', 'p3')]
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=8)
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=ability_index(s, walker, 'Put all creature'))
    assert s.state.cards[walker.id].zone == 'p1:graveyard'
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:battlefield' and s.state.cards[c.id].controller == 'p1' for c in dead)
    roundtrip(s)


def test_elspeth_also_watches_printed_loyalty_ability(cards):
    from tests.test_rules_wave7b_activation import ability_index
    s, walker, _ = setup(cards, "Elspeth's Talent")
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=walker.id,
        ability=ability_index(s, walker, 'Target player draws a card'), targets=['p1'])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 2
    assert stats(s, bear).pt == (4, 4)
    roundtrip(s)


def test_liliana_ignores_noncreature_damage_source(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s, walker, _ = setup(cards, "Liliana's Talent")
    shock = put(s, 'Shock', 'hand', pid='p2')
    pay(s, 'p2', 'Shock')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=shock.id, targets=[walker.id], sources=[])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 1
    assert not s.state.rules.stack
    roundtrip(s)


def test_liliana_watches_actual_combat_damage_to_host(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s, walker, _ = setup(cards, "Liliana's Talent")
    attacker = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='next_turn', player='p2', force=True)
    act(s, 'p2', type='pass_priority')
    to_phase(s, 'declare_attackers')
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': walker.id}])
    to_phase(s, 'end_combat')
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 1
    assert s.state.cards[attacker.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_rowan_copies_original_ability_even_after_original_is_countered(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index
    s, walker, _ = setup(cards, "Rowan's Talent")
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=walker.id,
        ability=ability_index(s, walker, 'Up to one target'), targets=[bear.id], target_counts=[1])
    original = next(sid for sid, e in s.state.rules.stack.items() if e.source_card == walker.id)
    counter = put(s, 'Stifle', 'hand', pid='p2')
    pay(s, 'p2', 'Stifle')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[original], sources=[])
    for _ in range(20):
        if original not in s.state.rules.stack:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert original not in s.state.rules.stack
    roundtrip(s)
    for _ in range(30):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        ids = {o.id for o in d.options}
        assert 'keep' in ids or bear.id in ids, (d.kind, d.prompt, [(o.id, o.label) for o in d.options])
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep'] if 'keep' in ids else [bear.id])
    assert stats(s, bear).pt == (4, 2)
    assert s.state.cards[walker.id].counters['loyalty'] == 4
    roundtrip(s)
