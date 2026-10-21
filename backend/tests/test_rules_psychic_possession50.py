"""Enchanted-opponent events retain the existing Aura/player rules."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import stops, to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/psychic_possession50_cards.json').read_text())


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
    names = ['Psychic Possession', 'Grizzly Bears', 'Divination']
    s = table(cards, names, names, names)
    start(s)
    stops(s, 'upkeep', 'main1')
    source = put(s, 'Psychic Possession', 'hand')
    mana(s, C=2, U=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'], sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield' and source.attached_player == 'p2'
    return s, source


def divination(s, pid):
    source = put(s, 'Divination', 'hand', pid)
    mana(s, pid=pid, C=2, U=1)
    act(s, pid, type='set_prefs', hold_priority=True)
    act(s, pid, type='cast_spell', card_id=source.id, sources=[])


def respond(s, answers):
    for answer in answers:
        settle(s)
        d = s.state.rules.decision
        assert d is not None and answer in {o.id for o in d.options}
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[answer])
    settle(s)
    assert s.state.rules.decision is None


def test_complete_canonical_possession(cards):
    assert coverage.of_card_data(cards.resolve('Psychic Possession')).level == 'FULL'


def test_only_enchanted_opponents_draws_generate_optional_draws(cards):
    s, _ = setup(cards)
    before = len(s.state.zones['p1:hand'])
    to_phase(s, 'main1', turn=5)
    before = len(s.state.zones['p1:hand'])
    divination(s, 'p2')
    respond(s, ['yes', 'no'])
    assert len(s.state.zones['p1:hand']) == before + 1
    to_phase(s, 'main1', turn=6)
    divination(s, 'p3')
    settle(s)
    assert s.state.rules.decision is None
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)


def test_controller_skips_draw_step_without_skipping_enchanted_player(cards):
    s, _ = setup(cards)
    to_phase(s, 'upkeep', turn=5)
    before = len(s.state.zones['p2:hand'])
    to_phase(s, 'main1', turn=5)
    assert len(s.state.zones['p2:hand']) == before + 1
    to_phase(s, 'upkeep', turn=7)
    before = len(s.state.zones['p1:hand'])
    to_phase(s, 'main1', turn=7)
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


def test_aura_cannot_target_self_or_a_permanent(cards):
    s = table(cards, ['Psychic Possession', 'Grizzly Bears'], ['Grizzly Bears'], [])
    start(s)
    source = put(s, 'Psychic Possession', 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    mana(s, C=2, U=2)
    for target in ['p1', bear.id]:
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target], sources=[])
        assert s.state.model_dump_json() == before


def test_control_change_makes_attachment_illegal_but_trigger_retains_controller(cards):
    s, source = setup(cards)
    to_phase(s, 'main1', turn=5)
    before = {p: len(s.state.zones[p + ':hand']) for p in ['p1', 'p2']}
    divination(s, 'p2')
    before['p2'] = len(s.state.zones['p2:hand'])
    from tests.test_rules_copy import resolve_top

    resolve_top(s)
    d = s.state.rules.decision
    if d is not None and d.kind == 'order':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    respond(s, ['yes', 'no'])
    assert source.zone == 'p1:graveyard'
    assert len(s.state.zones['p1:hand']) == before['p1'] + 1
    assert len(s.state.zones['p2:hand']) == before['p2'] + 2
    roundtrip(s)


def test_enchanted_opponent_departure_puts_aura_in_owners_graveyard(cards):
    s, source = setup(cards)
    act(s, 'p2', type='concede')
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


def test_true_cold_pending_optional_triggers_keep_original_controller(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app
    from tests.test_rules_copy import resolve_top

    s, source = setup(cards)
    to_phase(s, 'main1', turn=5)
    before = len(s.state.zones['p1:hand'])
    divination(s, 'p2')
    resolve_top(s)
    d = s.state.rules.decision
    if d is not None and d.kind == 'order':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    saved = tmp_path / 'psychic50.json'
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
for answer in ['yes','no']:
 settle(s)
 d=s.state.rules.decision
 assert d is not None and d.player=='p1' and answer in {o.id for o in d.options}
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[answer])
settle(s)
assert len(s.state.zones['p1:hand'])==int(sys.argv[3])+1
assert s.state.cards[sys.argv[4]].zone=='p1:graveyard'
roundtrip(s)
"""
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), str(before), source.id],
        cwd=Path(app.__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
