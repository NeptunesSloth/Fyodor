"""Historical controller acquisitions retain frozen source identity."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

NAMES = ['Mad Dog', 'Erg Raiders', 'Keldon Twilight', 'Grizzly Bears']
DATA = json.loads((Path(__file__).parent / 'fixtures/controller_turn_history69_cards.json').read_text())


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
    s = table(cards, [*NAMES, 'Slip Out the Back', 'Llanowar Elves'], [*NAMES, 'Slip Out the Back', 'Llanowar Elves'], [*NAMES, 'Slip Out the Back', 'Llanowar Elves'])
    start(s, turn=1)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s


def manual(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck

    decks = [deck(cards, 'Krenko, Mob Boss', [*((1, name) for name in NAMES), (20, 'Forest')]) for _ in range(3)]
    return GameSession(new_game([PlayerSetup(name, cards=d) for name, d in
                               zip(('Alice', 'Bob', 'Carol'), decks, strict=True)], shuffle=False), cards=cards)


def cast(s, name):
    c = put(s, name, 'hand')
    pool = {'Mad Dog': {'C': 1, 'R': 1}, 'Erg Raiders': {'C': 1, 'B': 1},
            'Keldon Twilight': {'C': 1, 'R': 1, 'B': 1}}[name]
    mana(s, **pool)
    act(s, 'p1', type='cast_spell', card_id=c.id, sources=[])
    settle(s)
    assert c.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    return c


@pytest.mark.parametrize('name', NAMES[:3])
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', NAMES[:2])
def test_entry_turn_exempts_source_then_next_own_end_enforces(cards, name):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    c = cast(s, name)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert c.zone == 'p1:battlefield' and s.state.players['p1'].life == 40
    to_phase(s, 'end', turn=4)
    settle(s)
    if name == 'Mad Dog':
        assert c.zone == 'p1:graveyard'
    else:
        assert c.zone == 'p1:battlefield' and s.state.players['p1'].life == 38
    roundtrip(s)


def test_twilight_only_continuously_controlled_since_turn_start(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    cast(s, 'Keldon Twilight')
    old = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    new = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    to_phase(s, 'end', turn=2)
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert d.player == 'p2'
        assert [o.card_id for o in d.options if o.card_id] == [old.id]
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[old.id])
        settle(s)
    assert old.zone == 'p2:graveyard' and new.zone == 'p2:battlefield'
    roundtrip(s)


def test_twilight_losing_then_regaining_control_is_not_continuous(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    cast(s, 'Keldon Twilight')
    old = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    act(s, 'p2', type='set_controller', card_ids=[old.id], player='p1')
    act(s, 'p1', type='set_controller', card_ids=[old.id], player='p2')
    to_phase(s, 'end', turn=2)
    settle(s)
    assert s.state.rules.decision is None and old.zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES[:2])
def test_control_gain_after_trigger_uses_exact_historical_controller(cards, name):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    c = cast(s, name)
    to_phase(s, 'end', turn=4)
    assert s.state.zones['stack']
    act(s, 'p1', type='set_controller', card_ids=[c.id], player='p2')
    act(s, 'p2', type='set_controller', card_ids=[c.id], player='p1')
    settle(s)
    assert c.zone == 'p1:battlefield' and s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES[:2])
def test_declared_attack_exempts_original_object(cards, name):
    from tests.test_rules_conditional_prevention import attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    c = cast(s, name)
    attack(s, [c], turn=4)
    to_phase(s, 'end', turn=4)
    settle(s)
    assert c.zone == 'p1:battlefield' and s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES[:2])
def test_true_cold_control_acquisition_after_trigger(cards, tmp_path, name):
    import subprocess
    import sys

    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    c = cast(s, name)
    to_phase(s, 'end', turn=4)
    assert s.state.zones['stack']
    act(s, 'p1', type='set_controller', card_ids=[c.id], player='p2')
    act(s, 'p2', type='set_controller', card_ids=[c.id], player='p1')
    saved = tmp_path / 'control69.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:battlefield'
assert s.state.players['p1'].life==40
assert s.state.rules.decision is None
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), c.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_enable_midgame_observes_control_then_next_turn_qualifies(cards):
    from tests.game_helpers import turn_on
    from tests.test_rules_wave30m_durations import to_phase

    s = manual(cards)
    put(s, 'Keldon Twilight', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    turn_on(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    from tests.test_rules_wave30m_durations import stops
    stops(s, 'main1', 'end')
    mark = s.state.rules.controlled_since[bear.id]
    assert mark.turn == 0 and mark.observed_from_turn == 1
    to_phase(s, 'end', turn=1)
    settle(s)
    assert bear.zone == 'p1:battlefield' and s.state.rules.decision is None
    to_phase(s, 'end', turn=4)
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert d.player == 'p1'
        assert [o.card_id for o in d.options if o.card_id] == [bear.id]
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
        settle(s)
    assert bear.zone == 'p1:graveyard'
    roundtrip(s)


def test_actual_phase_out_and_in_preserves_continuous_control(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    cast(s, 'Keldon Twilight')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    mark = s.state.rules.controlled_since[bear.id].model_copy(deep=True)
    spell = put(s, 'Slip Out the Back', 'hand')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id], sources=[])
    settle(s)
    assert bear.zone == 'p2:phased'
    assert s.state.rules.controlled_since[bear.id] == mark
    to_phase(s, 'main1', turn=2)
    assert bear.zone == 'p2:battlefield'
    assert s.state.rules.controlled_since[bear.id] == mark
    to_phase(s, 'end', turn=2)
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert d.player == 'p2' and any(o.card_id == bear.id for o in d.options)
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[bear.id])
        settle(s)
    assert bear.zone == 'p2:graveyard'
    roundtrip(s)


def test_legacy_unknown_control_mark_observed_on_first_sync(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    from tests.game_helpers import turn_on
    from tests.test_rules_wave30m_durations import to_phase

    s = manual(cards)
    put(s, 'Keldon Twilight', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    turn_on(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    from tests.test_rules_wave30m_durations import stops
    stops(s, 'main1', 'end')
    raw = s.state.model_dump(mode='json')
    mark = raw['rules']['controlled_since'][bear.id]
    assert mark['turn'] == 0
    mark.pop('observed_from_turn')
    s = GameSession(GameState.model_validate(raw), cards=cards)
    assert s.state.rules.controlled_since[bear.id].observed_from_turn is None
    act(s, 'p1', type='set_prefs', hold_priority=True)
    assert s.state.rules.controlled_since[bear.id].observed_from_turn == 1
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield' and s.state.rules.decision is None
    to_phase(s, 'end', turn=4)
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert any(o.card_id == bear.id for o in d.options)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
        settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard'


@pytest.mark.parametrize('name,life', [('Mad Dog', 40), ('Erg Raiders', 38)])
def test_leaving_and_reentering_keeps_original_trigger_source_oid(cards, name, life):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    c = cast(s, name)
    to_phase(s, 'end', turn=4)
    assert s.state.zones['stack']
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert c.zone == 'p1:battlefield' and s.state.players['p1'].life == life
    roundtrip(s)


def test_true_cold_twilight_preserves_turn_start_eligibility(cards, tmp_path):
    import subprocess
    import sys

    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = cast(s, 'Keldon Twilight')
    old = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    new = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    to_phase(s, 'end', turn=2)
    assert s.state.zones['stack']
    saved = tmp_path / 'twilight69.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p2:graveyard'
assert s.state.cards[sys.argv[4]].zone=='p2:battlefield'
assert s.state.cards[sys.argv[5]].zone=='p1:battlefield'
assert s.state.rules.decision is None
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), old.id, new.id, source.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
