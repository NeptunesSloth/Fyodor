"""Upkeep payment and untargeted return belong to the active player."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Umbilicus', 'Blood Clock']
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_upkeep_pay_return71_cards.json').read_text())


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


def setup(cards, name, permanent=True):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    ring = put(s, 'Sol Ring', 'battlefield', 'p2') if permanent else None
    source = put(s, name, 'hand')
    mana(s, C=4)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    return s, source, ring


def begin(s):
    to_phase(s, 'upkeep', turn=5)
    settle(s)


def choose(s, answer):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[answer])
    settle(s)


def decline_return(s, card):
    d = s.state.rules.decision
    if d is not None and any(o.id == 'decline' for o in d.options):
        choose(s, 'decline')
    if card.zone.endswith(':battlefield'):
        choose(s, card.id)


@pytest.mark.parametrize('name', NAMES)
def test_whole_actual_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', NAMES)
def test_active_player_pays_two_life_and_keeps_permanent(cards, name):
    s, _, ring = setup(cards, name)
    begin(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2' and any(o.id == 'pay' for o in d.options)
    before = {p:s.state.players[p].life for p in s.state.players}
    choose(s, 'pay')
    assert s.state.players['p2'].life == before['p2'] - 2
    assert s.state.players['p1'].life == before['p1']
    assert ring.zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_declining_returns_own_permanent_and_does_not_pay_life(cards, name):
    s, source, ring = setup(cards, name)
    begin(s)
    before = s.state.players['p2'].life
    decline_return(s, ring)
    assert ring.zone == 'p2:hand' and source.zone == 'p1:battlefield'
    assert s.state.players['p2'].life == before
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_life_one_cannot_pay_and_must_return(cards, name):
    s, _, ring = setup(cards, name)
    act(s, 'p1', type='set_life', player='p2', value=1)
    begin(s)
    d = s.state.rules.decision
    assert d is None or all(o.id != 'pay' for o in d.options)
    decline_return(s, ring)
    assert ring.zone == 'p2:hand' and s.state.players['p2'].life == 1
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_no_permanents_still_allows_payment_but_does_not_require_it(cards, pay):
    s, _, _ = setup(cards, 'Blood Clock', False)
    begin(s)
    before = s.state.players['p2'].life
    choose(s, 'pay' if pay else 'decline')
    assert s.state.players['p2'].life == before - (2 if pay else 0)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_return_uses_owner_not_affected_controller(cards):
    s, _, _ = setup(cards, 'Umbilicus', False)
    foreign = put(s, 'Sol Ring', 'battlefield', 'p3')
    act(s, 'p1', type='set_controller', card_ids=[foreign.id], player='p2')
    begin(s)
    decline_return(s, foreign)
    assert foreign.zone == 'p3:hand'
    roundtrip(s)


def test_changing_source_controller_does_not_change_original_upkeep_player(cards):
    s, source, ring = setup(cards, 'Blood Clock')
    to_phase(s, 'upkeep', turn=5)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    settle(s)
    assert s.state.rules.decision.player == 'p2'
    decline_return(s, ring)
    assert ring.zone == 'p2:hand'
    roundtrip(s)


def test_departed_source_keeps_original_upkeep_payment_and_return(cards):
    s, source, ring = setup(cards, 'Umbilicus')
    to_phase(s, 'upkeep', turn=5)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player':'p1','zone':'graveyard'})
    settle(s)
    decline_return(s, ring)
    assert ring.zone == 'p2:hand'
    roundtrip(s)


def test_life_change_prohibition_cannot_pay_two_life(cards):
    s, _, ring = setup(cards, 'Blood Clock')
    put(s, 'Platinum Emperion', 'battlefield', 'p2')
    begin(s)
    d = s.state.rules.decision
    assert d is None or all(o.id != 'pay' for o in d.options)
    decline_return(s, ring)
    assert ring.zone == 'p2:hand' and s.state.players['p2'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_pending_payment_keeps_original_affected_player(cards, tmp_path, name):
    import app

    s, source, ring = setup(cards, name)
    begin(s)
    saved = tmp_path / 'upkeep.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
d=s.state.rules.decision
assert d is not None and d.player=='p2'
act(s,'p2',type='choose',decision_id=d.id,option_ids=['decline'])
settle(s)
if s.state.cards[sys.argv[3]].zone.endswith(':battlefield'):
 d=s.state.rules.decision
 assert d is not None and d.player=='p2'
 act(s,'p2',type='choose',decision_id=d.id,option_ids=[sys.argv[3]])
 settle(s)
assert s.state.cards[sys.argv[3]].zone=='p2:hand'
assert s.state.players['p2'].life==40
roundtrip(s)
'''
    p = subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),ring.id],capture_output=True,text=True,timeout=90,cwd=Path(app.__file__).resolve().parents[1])
    assert p.returncode == 0, p.stdout + p.stderr
