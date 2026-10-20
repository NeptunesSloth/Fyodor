"""Canonical Moxite declared-X one-holder native cost proofs."""
import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests import test_rules_sacrifice_entry_outcomes43 as fixtures
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_linked_aggregates import activate, cast
from tests.test_rules_shared_damage_choices import table

NAME = 'Moxite Refinery'


@pytest.fixture()
def cards(settings):
    yield from fixtures.cards.__wrapped__(settings)


def scene(cards):
    names = [c['name'] for c in fixtures.DATA] + ['Grizzly Bears']
    s = table(cards, names, names, names)
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s, source


def test_full_canonical_production(cards):
    q = coverage.of_card_data(cards.resolve(NAME))
    assert q.level == 'FULL', [(f.label, f.supported) for f in q.features]


@pytest.mark.parametrize('mode,kind', [(0, 'charge'), (1, '+1/+1')])
def test_actual_declared_mixed_counter_cost_on_one_holder_feeds_both_modes(cards, mode, kind):
    from app.rules import cost_payment

    s, source = scene(cards)
    holder = put(s, 'Sol Ring', 'battlefield')
    target = put(s, 'Sol Ring' if mode == 0 else 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='charge', delta=2)
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='stun', delta=1)
    p = Plan(s.state, 'p1', cards, None)
    tokens = list(cost_payment.counter_tokens(p, [holder.id]))
    activate(s, source, ability=0, x_value=3, modes=[mode], targets=[target.id],
             cost_choices=[{'component': 2, 'cards': tokens}])
    assert s.state.cards[source.id].tapped
    assert not s.state.cards[holder.id].counters
    record = s.state.rules.payments[s.state.rules.object_id(s.state.zones['stack'][-1])]
    assert record.x == 3 and record.activation_cost_has_x is False
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[target.id].counters == {kind: 3}
    roundtrip(s)


def test_actual_declared_zero_needs_no_counters_but_pays_fixed_mana_and_tap(cards):
    from app.rules import mana_units
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, source = scene(cards)
    act(s, 'p1', type='clear_mana', player='p1')
    mana(s, C=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=0,
        modes=[0], targets=[source.id], cost_choices=[{'component': 2, 'cards': []}])
    settle(s)
    assert s.state.cards[source.id].tapped and not s.state.cards[source.id].counters
    assert not mana_units.visible_pool(s.state, 'p1') and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('modifier,expected', [('Doubling Season', 6), ('Vorinclex, Monstrous Raider', 1)])
def test_actual_cost_removal_and_declared_x_are_independent_of_replaced_put(cards, modifier, expected):
    from app.rules import cost_payment

    s, source = scene(cards)
    holder = put(s, 'Sol Ring', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='charge', delta=3)
    put(s, modifier, 'battlefield', pid='p2' if modifier.startswith('Vorinclex') else 'p1')
    tokens = list(cost_payment.counter_tokens(Plan(s.state, 'p1', cards, None), [holder.id]))
    activate(s, source, x_value=3, modes=[1], targets=[target.id], cost_choices=[{'component': 2, 'cards': tokens}])
    record = s.state.rules.payments[s.state.rules.object_id(s.state.zones['stack'][-1])]
    assert record.x == 3 and record.activation_cost_has_x is False
    assert not s.state.cards[holder.id].counters
    settle(s)
    assert s.state.cards[target.id].counters == {'+1/+1': expected}
    roundtrip(s)


@pytest.mark.parametrize('failure', ['split', 'too_many', 'barred', 'opponent'])
def test_actual_whole_counter_cost_preflight_rejects_atomically(cards, failure):
    from app.game.errors import ActionError
    from app.rules import cost_payment
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, source = scene(cards)
    one = put(s, 'Sol Ring', 'battlefield', pid='p2' if failure == 'opponent' else 'p1')
    two = put(s, 'Grizzly Bears', 'battlefield')
    kind = 'stun' if failure == 'barred' else 'charge'
    act(s, 'p1', type='counter', card_ids=[one.id, two.id], kind=kind, delta=2)
    if failure == 'barred':
        put(s, 'Fear of Sleep Paralysis', 'battlefield', pid='p2')
        settle(s)
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
            settle(s)
    p = Plan(s.state, 'p1', cards, None)
    tokens = list(cost_payment.counter_tokens(p, [one.id, two.id]))
    act(s, 'p1', type='clear_mana', player='p1')
    mana(s, C=2)
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=3 if failure != 'too_many' else 5,
            modes=[0], targets=[source.id], cost_choices=[{'component': 2, 'cards': tokens[:3]}])
    assert s.state.model_dump(mode='json') == before


@pytest.mark.parametrize('failure', ['other_turn', 'stack', 'tapped'])
def test_actual_sorcery_activation_and_tap_cost_boundaries(cards, failure):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s, source = scene(cards)
    if failure == 'other_turn':
        to_phase(s, 'main1', turn=2)
    elif failure == 'stack':
        spell = put(s, 'Swords to Plowshares', 'hand')
        bear = put(s, 'Grizzly Bears', 'battlefield')
        cast(s, spell, targets=[bear.id])
        assert s.state.zones.get('stack')
    else:
        act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    mana(s, C=2)
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
            x_value=0, modes=[0], targets=[source.id], cost_choices=[{'component': 2, 'cards': []}])
    assert s.state.model_dump(mode='json') == before


def test_actual_saved_counter_kind_choice_keeps_declared_x_and_exact_holder_true_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, source = scene(cards)
    holder = put(s, 'Sol Ring', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='charge', delta=2)
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='stun', delta=2)
    activate(s, source, x_value=3, modes=[1], targets=[target.id])
    d = s.state.rules.decision
    assert d is not None and d.resume['amount'] == 3
    offered = d.resume['counter_objects'][holder.id]
    assert offered['object_id'] == s.state.rules.object_id(holder.id)
    picked = [o.id for o in d.options][:3]
    s = cold_choose(s, cards, tmp_path, picked)
    assert sum(s.state.cards[holder.id].counters.values()) == 1
    record = s.state.rules.payments[s.state.rules.object_id(s.state.zones['stack'][-1])]
    assert record.x == 3 and record.activation_cost_has_x is False
    settle(s)
    assert s.state.cards[target.id].counters == {'+1/+1': 3}
    roundtrip(s)


@pytest.mark.parametrize('departure', ['source', 'creature_target', 'artifact_target'])
def test_actual_paid_cost_x_survives_source_departure_and_illegal_targets_fizzle(cards, departure):
    from app.rules import cost_payment

    s, source = scene(cards)
    holder = put(s, 'Sol Ring', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='charge', delta=3)
    tokens = list(cost_payment.counter_tokens(Plan(s.state, 'p1', cards, None), [holder.id]))
    artifact = departure == 'artifact_target'
    target = source if artifact else bear
    activate(s, source, x_value=3, modes=[0 if artifact else 1], targets=[target.id],
             cost_choices=[{'component': 2, 'cards': tokens}])
    assert not s.state.cards[holder.id].counters and s.state.cards[source.id].tapped
    if departure == 'creature_target':
        spell = put(s, 'Swords to Plowshares', 'hand')
        cast(s, spell, targets=[bear.id])
    else:
        spell = put(s, 'Naturalize', 'hand')
        cast(s, spell, targets=[source.id])
    settle(s)
    if departure == 'source':
        assert s.state.cards[source.id].zone == 'p1:graveyard'
        assert s.state.cards[bear.id].counters == {'+1/+1': 3}
    elif departure == 'creature_target':
        assert s.state.cards[bear.id].zone == 'p1:exile'
        assert not s.state.cards[bear.id].counters
    else:
        assert s.state.cards[source.id].zone == 'p1:graveyard'
        assert not s.state.cards[source.id].counters
    assert not s.state.cards[holder.id].counters and s.state.rules.decision is None
    roundtrip(s)


def test_actual_saved_cost_menu_rejects_same_physical_holder_new_incarnation(cards, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    from app.game.errors import ActionError

    s, source = scene(cards)
    holder = put(s, 'Sol Ring', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='charge', delta=2)
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='stun', delta=2)
    activate(s, source, x_value=3, modes=[1], targets=[target.id])
    d = s.state.rules.decision
    assert d is not None
    picked = [o.id for o in d.options][:3]
    original = s.state.rules.object_id(holder.id)
    act(s, 'p1', type='move', card_ids=[holder.id], to={'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[holder.id], to={'zone': 'battlefield'})
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='charge', delta=2)
    act(s, 'p1', type='counter', card_ids=[holder.id], kind='stun', delta=2)
    assert s.state.rules.object_id(holder.id) != original
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='original object'):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=picked)
    assert s.state.model_dump(mode='json') == before
    assert not s.state.cards[source.id].tapped
    saved = tmp_path / 'moxite43-stale-holder.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
saved, db, picked = sys.argv[1:]
repo = CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
before = s.state.model_dump(mode='json')
d = s.state.rules.decision
try:
    s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':json.loads(picked)})
except ActionError as exc:
    assert 'original object' in str(exc)
else:
    raise AssertionError('stale counter holder was accepted')
assert s.state.model_dump(mode='json') == before
repo.close()
'''
    import json

    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), json.dumps(picked)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
