"""Returned permanents charge their hand owner, preserving native choices."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_hand_owner50_cards.json').read_text())


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
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Sol Ring', 'Forest', 'Island']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, 'Warped Devotion', 'hand')
    mana(s, C=2, B=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    put(s, 'Forest', 'hand')
    put(s, 'Island', 'hand')
    return s, source


def cast(s, name, targets=()):
    spell = put(s, name, 'hand')
    mana(s, C=3, U=2, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[], targets=list(targets))
    return spell


def test_complete_canonical(cards):
    assert coverage.of_card_data(cards.resolve('Warped Devotion')).level == 'FULL'


@pytest.mark.parametrize('owner,controller', [('p1', 'p1'), ('p2', 'p3'), ('p3', 'p1')])
def test_native_bounce_charges_only_hand_owner(cards, owner, controller):
    s, _ = setup(cards)
    creature = put(s, 'Grizzly Bears', 'battlefield', owner)
    act(s, 'p1', type='set_controller', card_ids=[creature.id], player=controller)
    cast(s, 'Boomerang', [creature.id])
    settle(s)
    d = s.state.rules.decision
    assert creature.zone == owner + ':hand'
    assert d is not None and d.player == owner and d.resume['step'] == 'discard'
    act(s, owner, type='choose', decision_id=d.id, option_ids=[creature.id])
    settle(s)
    assert creature.zone == owner + ':graveyard' and s.state.rules.decision is None
    roundtrip(s)


def test_can_trigger_on_its_own_return_under_foreign_control(cards):
    s, source = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    cast(s, 'Boomerang', [source.id])
    settle(s)
    d = s.state.rules.decision
    assert source.zone == 'p1:hand' and d is not None and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[source.id])
    settle(s)
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


def test_card_returned_from_graveyard_is_not_a_permanent_returned(cards):
    s, _ = setup(cards)
    creature = put(s, 'Grizzly Bears', 'graveyard')
    cast(s, 'Raise Dead', [creature.id])
    before = len(s.state.zones['p1:hand'])
    settle(s)
    assert creature.zone == 'p1:hand' and s.state.rules.decision is None
    assert len(s.state.zones['p1:hand']) == before + 1


def test_simultaneous_native_returns_trigger_separately_for_each_owner(cards):
    s, _ = setup(cards)
    creatures = [put(s, 'Grizzly Bears', 'battlefield', p) for p in ('p1', 'p2', 'p3')]
    cast(s, 'Evacuation')
    settle(s)
    seen = set()
    while (d := s.state.rules.decision) is not None:
        assert d.resume['step'] == 'discard' and d.player not in seen
        chosen = next(c for c in creatures if c.owner == d.player)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[chosen.id])
        seen.add(d.player)
        settle(s)
    assert seen == {'p1', 'p2', 'p3'}
    assert all(c.zone == c.owner + ':graveyard' for c in creatures)
    roundtrip(s)


def test_self_return_under_other_controller_survives_cold_discard_prompt(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, source = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    cast(s, 'Boomerang', [source.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    before = len(s.state.zones['p1:hand'])
    p2hand = len(s.state.zones['p2:hand'])
    saved = tmp_path / 'hand-owner.json'
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
assert d is not None and d.player=='p1'
act(s,'p1',type='choose',decision_id=d.id,option_ids=[sys.argv[3]])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
assert len(s.state.zones['p1:hand'])==int(sys.argv[4])-1
assert len(s.state.zones['p2:hand'])==int(sys.argv[5])
assert s.state.rules.decision is None
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, str(before), str(p2hand)],
        cwd=Path(app.__file__).resolve().parents[1],
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
