"""The monarch's step is checked when triggering; its player is retained."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditional_prevention import attack, damage
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import stops, to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/monarch_steps50_cards.json').read_text())


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


def setup(cards):
    names = ['Archivist of Gondor', 'Grizzly Bears', 'Llanowar Elves']
    s = table(cards, names, names, names)
    start(s)
    stops(s, 'main1', 'end', 'declare_attackers', 'declare_blockers', 'combat_damage')
    source = put(s, 'Archivist of Gondor', 'hand')
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    return s, source


def ready(s, monarch, turn=4):
    to_phase(s, 'main1', turn=turn)
    if monarch is not None:
        act(s, 'p1', type='set_monarch', player=monarch)
    return {p: len(s.state.zones[p + ':hand']) for p in ['p1', 'p2', 'p3']}


def test_complete_canonical_archivist(cards):
    assert coverage.of_card_data(cards.resolve('Archivist of Gondor')).level == 'FULL'


@pytest.mark.parametrize('monarch,turn', [('p1', 4), ('p2', 5)])
def test_own_or_opponent_monarch_gets_additional_draw(cards, monarch, turn):
    s, _ = setup(cards)
    before = ready(s, monarch, turn)
    to_phase(s, 'end', turn=turn)
    settle(s)
    assert len(s.state.zones[monarch + ':hand']) == before[monarch] + 2
    assert all(len(s.state.zones[p + ':hand']) == before[p] for p in before if p != monarch)
    roundtrip(s)


@pytest.mark.parametrize('monarch', [None, 'p2'])
def test_absent_monarch_or_nonmonarch_active_player_does_not_trigger(cards, monarch):
    s, _ = setup(cards)
    before = ready(s, monarch)
    to_phase(s, 'end', turn=4)
    settle(s)
    assert all(len(s.state.zones[p + ':hand']) == before[p] for p in before)
    roundtrip(s)


def test_monarch_changes_and_source_leaves_after_trigger_without_redirecting_draw(cards):
    s, source = setup(cards)
    before = ready(s, 'p2', 5)
    to_phase(s, 'end', turn=5)
    d = s.state.rules.decision
    if d is not None:
        assert d.kind == 'order'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
    act(s, 'p1', type='set_monarch', player='p3')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert len(s.state.zones['p2:hand']) == before['p2'] + 2
    assert len(s.state.zones['p3:hand']) == before['p3']
    roundtrip(s)


def test_commander_damage_creates_monarch_only_when_none_exists(cards):
    s, _ = setup(cards)
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    attack(s, [commander], target='p2', turn=7)
    damage(s)
    assert s.state.table.monarch == 'p1'
    act(s, 'p1', type='set_monarch', player='p3')
    attack(s, [commander], target='p2', turn=10)
    damage(s)
    assert s.state.table.monarch == 'p3'
    roundtrip(s)


def test_true_cold_trigger_retains_original_monarch_player(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, _ = setup(cards)
    before = ready(s, 'p2', 5)
    to_phase(s, 'end', turn=5)
    saved = tmp_path / 'monarch50.json'
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
if d is not None:
 assert d.kind=='order'
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
act(s,'p1',type='set_monarch',player='p3')
settle(s)
assert len(s.state.zones['p2:hand'])==int(sys.argv[3])+2
assert len(s.state.zones['p3:hand'])==int(sys.argv[4])
roundtrip(s)
"""
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), str(before['p2']), str(before['p3'])],
        cwd=Path(app.__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
