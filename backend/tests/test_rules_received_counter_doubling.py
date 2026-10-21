"""Fangs of Kalonia uses actual counter recipients, including its overloaded text."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Fangs of Kalonia'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/received_counter_doubling_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='rcd', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, overload=False, initial=0, permanent=None, opponent=False, second=None):
    s = table(cards, [NAME, 'Grizzly Bears', 'Centaur Courser', 'Doubling Season', 'Hardened Scales', 'Solemnity',
                      'Vorinclex, Monstrous Raider'], ['Grizzly Bears', 'Vorinclex, Monstrous Raider'])
    source = put(s, NAME, 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    courser = put(s, 'Centaur Courser', 'battlefield')
    theirs = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    for cid in (bear.id, courser.id, theirs.id):
        act(s, 'p1', type='set_counter', card_id=cid, kind='+1/+1', value=initial)
    if permanent:
        put(s, permanent, 'battlefield', pid='p2' if opponent else 'p1')
    if second:
        put(s, second, 'battlefield')
    mana(s, C=4 if overload else 1, G=2 if overload else 1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[] if overload else [bear.id],
        alt_cost=f'{source.id}:1' if overload else None, sources=[])
    settle(s)
    roundtrip(s)
    return s, bear, courser, theirs


def test_canonical_and_overloaded_text_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('overload', [False, True])
@pytest.mark.parametrize('initial', [0, 3])
def test_native_normal_and_overload_add_then_double_only_own_affected_creatures(cards, overload, initial):
    s, bear, courser, theirs = setup(cards, overload, initial)
    assert s.state.cards[bear.id].counters['+1/+1'] == 2 * (initial + 1)
    assert s.state.cards[courser.id].counters.get('+1/+1', 0) == (2 * (initial + 1) if overload else initial)
    assert s.state.cards[theirs.id].counters.get('+1/+1', 0) == initial


@pytest.mark.parametrize('overload', [False, True])
@pytest.mark.parametrize('permanent,expected', [('Doubling Season', 6), ('Hardened Scales', 5)])
def test_replacement_applies_independently_to_both_put_instructions(cards, overload, permanent, expected):
    s, bear, courser, theirs = setup(cards, overload, permanent=permanent)
    assert s.state.cards[bear.id].counters['+1/+1'] == expected
    assert s.state.cards[courser.id].counters.get('+1/+1', 0) == (expected if overload else 0)
    assert not s.state.cards[theirs.id].counters


@pytest.mark.parametrize('permanent,opponent', [('Solemnity', False), ('Vorinclex, Monstrous Raider', True)])
def test_no_actual_counter_put_does_not_double_existing_counters(cards, permanent, opponent):
    s, bear, courser, theirs = setup(cards, True, initial=3, permanent=permanent, opponent=opponent)
    assert all(s.state.cards[c.id].counters['+1/+1'] == 3 for c in (bear, courser, theirs))
    assert s.state.rules.decision is None


def test_counter_replacement_pause_between_both_instructions_preserves_binding(cards):
    s, bear, courser, theirs = setup(cards, permanent='Doubling Season', second='Hardened Scales')
    stages = 0
    while (d := s.state.rules.decision) is not None:
        stages += 1
        roundtrip(s)
        choice = next(o for o in d.options if 'Doubling Season' in o.label)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[choice.id])
        settle(s)
    assert stages == 2
    assert s.state.cards[bear.id].counters['+1/+1'] == 10
    assert not s.state.cards[courser.id].counters and not s.state.cards[theirs.id].counters
    roundtrip(s)


def test_cold_process_resumes_counter_binding_and_independent_second_order_choice(cards, tmp_path):
    s, bear, _, _ = setup(cards, permanent='Doubling Season', second='Hardened Scales')
    assert s.state.rules.decision is not None
    saved = tmp_path / 'pending-fangs.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state_path, database, target = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state_path).read_text()), cards=repo)
choices = 0
for _ in range(50):
    d = s.state.rules.decision
    if d is not None:
        choice = next(o for o in d.options if 'Doubling Season' in o.label)
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [choice.id]})
        choices += 1
    elif s.state.rules.stack:
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
assert choices == 2
assert s.state.cards[target].counters['+1/+1'] == 10
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), bear.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_opposite_counters_cancel_only_after_both_instructions(cards):
    s = table(cards, [NAME, 'Grizzly Bears'], [])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='-1/-1', value=1)
    source = put(s, NAME, 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bear.id], sources=[])
    settle(s)
    assert s.state.cards[bear.id].counters == {'+1/+1': 1}
    roundtrip(s)


def test_overload_can_affect_own_protection_from_green_creature(cards):
    from app.game.errors import ActionError

    s = table(cards, [NAME, 'Mirran Crusader'], [])
    creature = put(s, 'Mirran Crusader', 'battlefield')
    source = put(s, NAME, 'hand')
    mana(s, C=4, G=2)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[creature.id], sources=[])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=f'{source.id}:1', sources=[])
    settle(s)
    assert s.state.cards[creature.id].counters['+1/+1'] == 2
    roundtrip(s)
