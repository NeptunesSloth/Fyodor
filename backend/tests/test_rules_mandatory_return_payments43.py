"""Canonical mandatory return costs, optional fallback and saved native choices."""
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
from tests.test_rules_linked_aggregates import cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/mandatory_return_payments43_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='mrt', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, other=False):
    names = ['Mistbreath Elder', 'Grizzly Bears', 'Llanowar Elves']
    s = table(cards, names, names, names)
    source = put(s, 'Mistbreath Elder', 'hand')
    cast(s, source)
    settle(s)
    creature = put(s, 'Grizzly Bears', 'battlefield') if other else None
    return s, source, creature


def test_full_canonical(cards):
    assert coverage.of_card_data(cards.resolve('Mistbreath Elder')).level == 'FULL'


def test_actual_mandatory_other_return_then_counter_without_decline(cards):
    s, source, other = setup(cards, True)
    assert other is not None
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[other.id].zone == 'p1:hand'
    assert s.state.cards[source.id].counters == {'+1/+1': 1}
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_actual_no_other_creature_has_optional_self_return(cards, pay):
    s, source, _ = setup(cards)
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay' if pay else 'decline'])
    settle(s)
    assert s.state.cards[source.id].zone == ('p1:hand' if pay else 'p1:battlefield')
    assert not s.state.cards[source.id].counters
    roundtrip(s)


def test_actual_new_source_incarnation_is_another_creature_for_old_trigger(cards):
    s, source, _ = setup(cards)
    to_phase(s, 'upkeep', turn=4)
    assert s.state.rules.stack
    old = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'battlefield'})
    assert s.state.rules.object_id(source.id) != old
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert s.state.rules.decision is None and not s.state.cards[source.id].counters
    roundtrip(s)


def test_actual_mandatory_choice_survives_cold_state_and_returns_only_chosen(cards):
    s, source, first = setup(cards, True)
    second = put(s, 'Llanowar Elves', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == d.max_choices == 1
    assert {o.card_id for o in d.options} == {first.id, second.id}
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[second.id])
    settle(s)
    assert s.state.cards[first.id].zone == 'p1:battlefield'
    assert s.state.cards[second.id].zone == 'p1:hand'
    assert s.state.cards[source.id].counters == {'+1/+1': 1}
    assert s.state.rules.decision is None
    roundtrip(s)


def test_actual_mandatory_choice_true_cold(cards, tmp_path):
    import subprocess
    import sys

    s, source, first = setup(cards, True)
    second = put(s, 'Llanowar Elves', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'mandatory43.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, db, source, first, second = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
d = s.state.rules.decision
assert d is not None
s.perform(d.player, {'type':'choose', 'decision_id':d.id, 'option_ids':[second]})
assert s.state.cards[source].counters == {'+1/+1':1}
assert s.state.cards[first].zone == 'p1:battlefield'
assert s.state.cards[second].zone == 'p1:hand'
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), source.id, first.id, second.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
