"""A Spirit or disturb card is one discard event, including when it is both."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/discard_counter_union66_cards.json').read_text())
NAMES = [c['name'] for c in DATA] + ['Grizzly Bears']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, discard='Grizzly Bears', rest_in_peace=False):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    if rest_in_peace:
        put(s, 'Rest in Peace', 'battlefield')
        settle(s)
    chosen = put(s, discard, 'hand')
    source = put(s, 'Shipwreck Sifters', 'hand')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield'
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    return s, source, chosen


def discard_choice(s, card):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[card.id])
    settle(s)


def test_complete_canonical_supported(cards):
    assert coverage.of_card_data(cards.resolve('Shipwreck Sifters')).level == 'FULL'


@pytest.mark.parametrize('name,expected', [
    ('Spectral Sailor', 1),
    ('Malevolent Hermit // Benevolent Geist', 1),
    ("Lantern Bearer // Lanterns' Lift", 1),
    ('Grizzly Bears', 0),
    ('Ponder', 0),
])
def test_paid_source_draws_then_discards_union_once(cards, name, expected):
    s, source, chosen = setup(cards, name)
    before = len(s.state.zones['p1:hand'])
    discard_choice(s, chosen)
    assert len(s.state.zones['p1:hand']) == before - 1
    assert chosen.zone == 'p1:graveyard'
    assert source.counters.get('+1/+1', 0) == expected
    assert not s.state.zones['stack'] and s.state.rules.decision is None
    roundtrip(s)


def test_opponent_native_loot_discard_is_not_your_discard(cards):
    s, source, chosen = setup(cards)
    discard_choice(s, chosen)
    looter = put(s, 'Merfolk Looter', 'battlefield', 'p2')
    other = put(s, 'Spectral Sailor', 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=looter.id, ability=0, sources=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2'
    discard_choice(s, other)
    assert other.zone == 'p2:graveyard' and not source.counters
    roundtrip(s)


def test_true_cold_pending_qualified_discard_retains_union(cards, tmp_path):
    import subprocess
    import sys

    s, source, chosen = setup(cards, "Lantern Bearer // Lanterns' Lift")
    saved = tmp_path / 'discard66.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d and d.player=='p1'
act(s,'p1',type='choose',decision_id=d.id,option_ids=[sys.argv[4]])
settle(s)
assert s.state.cards[sys.argv[3]].counters.get('+1/+1')==1
assert s.state.cards[sys.argv[4]].zone=='p1:graveyard'
assert not s.state.zones['stack']
roundtrip(s)
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, chosen.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_discard_replaced_to_exile_still_uses_the_qualified_card(cards):
    s, source, chosen = setup(cards, "Spectral Sailor", rest_in_peace=True)
    discard_choice(s, chosen)
    assert chosen.zone == "p1:exile"
    assert source.counters.get("+1/+1") == 1
    roundtrip(s)
