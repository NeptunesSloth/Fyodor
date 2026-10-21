"""Tamiyo watches chosen objects until her controller's next turn, including damage to blockers."""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import through_combat, token_of
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave33a_turn_triggers import attack, hand
from tests.test_rules_wrenn_emblem import cards as emblem_cards


@pytest.fixture()
def cards(settings):
    yield from emblem_cards.__wrapped__(settings)


NAME = 'Tamiyo, Field Researcher'


def setup(cards):
    s = table(cards, [NAME, 'Grizzly Bears', 'Sol Ring', 'Lightning Bolt'], ['Counterspell', 'Sol Ring'])
    source = put(s, NAME, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'W': 1, 'U': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[])
    settle(s)
    return s, source


def watch(s, source, creatures):
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
        targets=[c.id for c in creatures], target_counts=[len(creatures)])
    settle(s)
    roundtrip(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('count', [0, 1, 2])
def test_zero_one_two_targets_draw_per_creature(cards, count):
    s, source = setup(cards)
    creatures = [token_of(s, 'p1', f'Creature{i}', 'Token Creature — Bear', '2/2', 'Haste') for i in range(2)]
    watch(s, source, creatures[:count])
    before = hand(s)
    attack(s, *creatures)
    through_combat(s)
    assert hand(s) == before + count
    roundtrip(s)


def test_trample_across_two_blockers_and_player_is_one_event_per_damage_step(cards):
    s, source = setup(cards)
    attacker = token_of(s, 'p1', 'Striker', 'Token Creature — Bear', '8/8', 'Haste, trample, double strike')
    blockers = [token_of(s, 'p2', f'Blocker{i}', 'Token Creature — Bear', '2/2') for i in range(2)]
    watch(s, source, [attacker])
    before = hand(s)
    attack(s, attacker)
    for _ in range(40):
        d = s.state.rules.decision
        if d and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[{'blocker_id': c.id, 'attacker_id': attacker.id} for c in blockers])
            break
        act(s, s.state.rules.priority, type='pass_priority')
    for _ in range(80):
        d = s.state.rules.decision
        if d and d.kind == 'divide':
            total = d.resume['total']
            amounts = [2 if o.id != 'p2' else 0 for o in d.options]
            amounts[next(i for i, o in enumerate(d.options) if o.id == 'p2')] = total - sum(amounts)
            act(s, d.player, type='choose', decision_id=d.id, amounts=amounts)
        elif d:
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options][:max(1, d.min_choices)])
        elif s.state.turn.phase == 'main2' and not s.state.zones.get('stack'):
            break
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    else:
        raise AssertionError('combat did not finish')
    assert hand(s) == before + 2  # First strike: three recipients; regular damage: player only.
    assert s.state.players['p2'].life == 28
    roundtrip(s)


def test_watch_survives_tamiyo_leaving_and_chosen_creature_control_change(cards):
    s, source = setup(cards)
    creature = token_of(s, 'p1', 'Chosen', 'Token Creature — Bear', '2/2', 'Haste')
    watch(s, source, [creature])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='set_controller', card_ids=[creature.id], player='p2')
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'main1', turn=2)
    before1, before2 = hand(s), hand(s, 'p2')
    for _ in range(40):
        d = s.state.rules.decision
        if d and d.kind == 'declare_attackers':
            act(s, 'p2', type='declare_attackers', attackers=[{'card_id': creature.id, 'target': 'p1'}])
            break
        act(s, s.state.rules.priority, type='pass_priority')
    through_combat(s)
    assert hand(s) == before1 + 1 and hand(s, 'p2') == before2
    assert s.state.players['p1'].life == 38
    assert any(t.when.get('source_batch') or t.when.get('cond', {}).get('source_batch') for t in s.state.rules.delayed)
    to_phase(s, 'main1', turn=4)
    assert not [t for t in s.state.rules.delayed if t.when.get('kind') == 'watch']
    roundtrip(s)


def test_watch_does_not_follow_new_object_after_blink(cards):
    s, source = setup(cards)
    creature = put(s, 'Grizzly Bears', 'battlefield')
    watch(s, source, [creature])
    old = s.state.rules.object_id(creature.id)
    act(s, 'p1', type='move', card_ids=[creature.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[creature.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert s.state.rules.object_id(creature.id) != old
    refs = [o['object_id'] for t in s.state.rules.delayed for o in t.refs.get('watch', {}).get('objects', [])]
    assert old in refs and s.state.rules.object_id(creature.id) not in refs
    roundtrip(s)
