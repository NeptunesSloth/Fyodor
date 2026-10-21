"""Adventure copying reads the spell face and uses native copy continuations."""

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
from tests.test_rules_copy import copies, resolve_top
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/lucky_clover50_cards.json').read_text())


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
    names = [c['name'] for c in DATA] + ['Lightning Bolt', 'Counterspell']
    s = table(cards, names, names, names)
    start(s)
    source = put(s, 'Lucky Clover', 'hand')
    mana(s, C=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    return s, source


def cast_adventure(s, name, targets=(), pid='p1'):
    source = put(s, name, 'hand', pid)
    mana(s, pid=pid, C=1, R=1, U=1)
    act(s, pid, type='set_prefs', hold_priority=True)
    act(s, pid, type='cast_spell', card_id=source.id, face=1, targets=list(targets), sources=[])
    return source


def finish_copy(s, target='keep'):
    settle(s)
    d = s.state.rules.decision
    assert d is not None, 'copy must ask whether to change its target'
    assert target in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target])
    settle(s)


def test_complete_canonical_clover(cards):
    assert coverage.of_card_data(cards.resolve('Lucky Clover')).level == 'FULL'


def test_instant_adventure_is_copied_with_new_target(cards):
    s, _ = setup(cards)
    before = {p: s.state.players[p].life for p in ['p2', 'p3']}
    source = cast_adventure(s, 'Bonecrusher Giant // Stomp', ['p2'])
    finish_copy(s, 'p3')
    assert all(s.state.players[p].life == before[p] - 2 for p in before)
    assert source.zone == 'p1:exile'
    assert not copies(s)
    assert not any(c.is_token and c.name in ('Stomp', 'Bonecrusher Giant // Stomp') for c in s.state.cards.values())
    roundtrip(s)


def test_sorcery_adventure_is_copied_and_copy_is_not_cast(cards):
    s, _ = setup(cards)
    before = len(s.state.zones['p2:library'])
    prior_casts = s.state.rules.spells_this_turn('p1', s.state.turn.number)
    source = cast_adventure(s, 'Merfolk Secretkeeper // Venture Deeper', ['p2'])
    finish_copy(s)
    assert len(s.state.zones['p2:library']) == before - 8
    assert source.zone == 'p1:exile' and not copies(s)
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == prior_casts + 1
    roundtrip(s)


def test_creature_front_and_ordinary_instant_do_not_trigger(cards):
    s, _ = setup(cards)
    creature = put(s, 'Bonecrusher Giant // Stomp', 'hand')
    mana(s, C=2, R=1)
    act(s, 'p1', type='cast_spell', card_id=creature.id, face=0, sources=[])
    settle(s)
    assert creature.zone == 'p1:battlefield' and not copies(s)
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    before = s.state.players['p2'].life
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'], sources=[])
    settle(s)
    assert s.state.players['p2'].life == before - 3
    roundtrip(s)


def test_opponents_adventure_does_not_trigger_our_clover(cards):
    s, _ = setup(cards)
    to_phase(s, 'main1', turn=5)
    before = s.state.players['p1'].life
    source = cast_adventure(s, 'Bonecrusher Giant // Stomp', ['p1'], pid='p2')
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == before - 2
    assert source.zone == 'p2:exile'
    roundtrip(s)


def test_original_countered_before_clover_trigger_still_has_copied_lki(cards):
    s, _ = setup(cards)
    before = s.state.players['p3'].life
    source = cast_adventure(s, 'Bonecrusher Giant // Stomp', ['p2'])
    wait_priority(s, 'p2')
    counter = put(s, 'Counterspell', 'hand', 'p2')
    mana(s, pid='p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[source.id], sources=[])
    resolve_top(s)
    assert source.zone == 'p1:graveyard'
    finish_copy(s, 'p3')
    assert s.state.players['p3'].life == before - 2
    assert source.zone == 'p1:graveyard' and not copies(s)
    roundtrip(s)


def test_targetless_adventure_copy_runs_both_scry_draws(cards):
    s, _ = setup(cards)
    source = put(s, 'Young Blue Dragon // Sand Augury', 'hand')
    before = len(s.state.zones['p1:hand']) - 1
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, face=1, sources=[])
    n = 0
    for _ in range(8):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        assert d.resume.get('step') == 'look'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        n += 1
    assert n == 2
    assert len(s.state.zones['p1:hand']) == before + 2
    assert source.zone == 'p1:exile' and not copies(s)
    roundtrip(s)


def test_true_cold_copy_uses_countered_original_last_known_spell(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, clover = setup(cards)
    before = s.state.players['p3'].life
    source = cast_adventure(s, 'Bonecrusher Giant // Stomp', ['p2'])
    wait_priority(s, 'p2')
    counter = put(s, 'Counterspell', 'hand', 'p2')
    mana(s, pid='p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[source.id], sources=[])
    resolve_top(s)
    assert source.zone == 'p1:graveyard'
    act(s, 'p1', type='move', card_ids=[clover.id], to={'player': 'p1', 'zone': 'graveyard'})
    saved = tmp_path / 'clover50.json'
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
settle(s)
d=s.state.rules.decision
assert d is not None and 'p3' in {o.id for o in d.options}
act(s,d.player,type='choose',decision_id=d.id,option_ids=['p3'])
settle(s)
assert s.state.players['p3'].life==int(sys.argv[4])-2
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
assert not s.state.zones['stack']
assert not any(c.is_token and c.name in ('Stomp','Bonecrusher Giant // Stomp') for c in s.state.cards.values())
roundtrip(s)
"""
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, str(before)],
        cwd=Path(app.__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
