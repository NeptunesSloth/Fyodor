"""Canonical collateral: both Caught Stealing modes execute through native rules."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.visibility import can_see
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import stops, three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

NAME = "You've Been Caught Stealing"
DATA = Path(__file__).parent / 'fixtures/caught_stealing_collateral_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='csc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [NAME, 'Fervor', 'Ornithopter', 'Grizzly Bears', 'Lightning Bolt', 'Forest']
    s = three(cards, names, names, names)
    hold(s)
    return s


def treasures(s):
    return [c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone == 'p1:battlefield']


def blocking(s, flying=False, tapped=False, late=False):
    put(s, 'Fervor', 'battlefield')
    attacker = put(s, 'Ornithopter' if flying else 'Grizzly Bears', 'battlefield')
    if not late:
        blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    spell(s, NAME, {'R': 1, 'C': 1}, modes=[0])
    if late:
        blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if tapped:
        act(s, 'p2', type='tap', card_ids=[blocker.id], tapped=True)
    stops(s, 'declare_attackers', 'declare_blockers', 'main2')
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p2'}])
    to_phase(s, 'declare_blockers')
    return attacker, blocker


def test_canonical_is_full(cards):
    result = coverage.of_card_data(cards.resolve(NAME))
    assert result.level == 'FULL', result.manual_parts


@pytest.mark.parametrize('late', [False, True])
def test_merchant_requires_legal_blocks_even_for_later_entrants(cards, late):
    s = setup(cards)
    attacker, blocker = blocking(s, late=late)
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_blockers', blocks=[])
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    assert s.state.cards[blocker.id].blocking == attacker.id
    roundtrip(s)


@pytest.mark.parametrize('flying,tapped', [(True, False), (False, True)])
def test_merchant_never_requires_an_impossible_block(cards, flying, tapped):
    s = setup(cards)
    blocking(s, flying=flying, tapped=tapped)
    if s.state.rules.decision is not None:
        assert s.state.rules.decision.kind == 'declare_blockers'
        act(s, 'p2', type='declare_blockers', blocks=[])
    else:
        # With no untapped blockers the native engine declares no blocks itself.
        assert not any(c.blocking for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize('targets,expected', [([], 0), (['p1'], 0), (['p2'], 1), (['p2', 'p2'], 1), (['p2', 'p3'], 2)])
def test_guards_counts_distinct_damaged_opponents_not_events_or_self(cards, targets, expected):
    s = setup(cards)
    for target in targets:
        spell(s, 'Lightning Bolt', {'R': 1}, [target])
    # A life adjustment is not a damage event.
    act(s, 'p3', type='life', player='p3', delta=-2)
    hidden = put(s, 'Forest', 'hand', 'p2')
    spell(s, NAME, {'R': 1, 'C': 1}, modes=[1])
    assert len(treasures(s)) == expected
    assert not can_see(s.state, s.state.cards[hidden.id], 'p1')
    for token in treasures(s):
        assert all(can_see(s.state, token, pid) for pid in ('p1', 'p2', 'p3'))
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('kind', ['block', 'treasure'])
def test_both_modes_resume_in_a_fresh_process(cards, tmp_path, kind):
    s = setup(cards)
    args = []
    if kind == 'block':
        attacker, blocker = blocking(s)
        args = [attacker.id, blocker.id]
    else:
        spell(s, 'Lightning Bolt', {'R': 1}, ['p2'])
        spell(s, NAME, {'R': 1, 'C': 1}, modes=[1], finish=False)
    path = tmp_path / f'{kind}.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
path, database, kind, *ids = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
if kind == 'block':
    try:
        s.perform('p2', {'type': 'declare_blockers', 'blocks': []})
    except ActionError:
        pass
    else:
        raise AssertionError('required blocker was allowed to abstain')
    s.perform('p2', {'type': 'declare_blockers', 'blocks': [{'blocker_id': ids[1], 'attacker_id': ids[0]}]})
    assert s.state.cards[ids[1]].blocking == ids[0]
else:
    for _ in range(20):
        if not s.state.zones.get('stack'):
            break
        assert s.state.rules.decision is None
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    assert sum(c.name == 'Treasure' and c.zone == 'p1:battlefield' for c in s.state.cards.values()) == 1
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), kind, *args],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_guards_counts_damage_dealt_by_another_opponent(cards):
    s = setup(cards)
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p2')
    spell(s, NAME, {'R': 1, 'C': 1}, modes=[1])
    assert len(treasures(s)) == 1
    roundtrip(s)


def test_guards_does_not_count_damage_from_an_earlier_turn(cards):
    s = setup(cards)
    spell(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    stops(s, 'main1')
    to_phase(s, 'main1', turn=4)
    spell(s, NAME, {'R': 1, 'C': 1}, modes=[1])
    assert treasures(s) == []
    roundtrip(s)
