"""Native alternative and upkeep taxes retain actual payers and affected objects."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Lim-Dûl's Hex", 'Thrull Wizard', 'Erosion', 'Slow Motion', 'Soul Tithe', 'In the Eye of Chaos', 'Draco']
DATA = json.loads((Path(__file__).parent / 'fixtures/upkeep_tax79_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Lightning Bolt', 'Counterspell', 'Forest', 'Island', 'Mountain']


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


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids, resolve=True):
    d = s.state.rules.decision
    assert d
    result = act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    if resolve:
        settle(s)
    return result


def cast(s, name, targets=(), pid='p1', resolve=True, **extra):
    c = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana={'C': 30, 'W': 4, 'U': 5, 'R': 2, 'B': 3, 'G': 3})
    act(s, pid, type='cast_spell', card_id=c.id, targets=list(targets), sources=[], **extra)
    if resolve:
        settle(s)
    return c




@pytest.mark.parametrize('pay', [False, True])
def test_chaos_actual_world_cast_then_native_instant_cast_mana_value_tax(cards, pay):
    s = game(cards)
    cast(s, NAMES[5])
    target = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    settle(s)
    assert s.state.rules.decision.player == 'p2' and s.state.rules.decision.resume['opt']['cost'] == '{1}'
    choose(s, ['pay' if pay else 'decline'])
    assert s.state.cards[target.id].zone == 'p2:graveyard' and s.state.players['p1'].life == (37 if pay else 40)
    roundtrip(s)

def test_chaos_actual_x_instant_counts_x_then_original_event_spell_gone_does_not_ask_again(cards):
    s = game(cards)
    cast(s, NAMES[5])
    for pid in ('p2', 'p3'):
        act(s, pid, type='set_prefs', hold_priority=True)
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p3', resolve=False)
    counter = cast(s, 'Syncopate', [bolt.id], pid='p2', resolve=False, x_value=3)
    settle(s)
    assert s.state.rules.decision.player == 'p2' and s.state.rules.decision.resume['opt']['cost'] == '{4}'
    choose(s, ['pay'])
    assert s.state.rules.decision.player == 'p3'
    choose(s, ['decline'])
    assert s.state.rules.decision is None and s.state.cards[bolt.id].zone == 'p3:exile'
    assert s.state.cards[counter.id].zone == 'p2:graveyard' and s.state.players['p1'].life == 40
    roundtrip(s)

def test_chaos_cannot_counter_uncounterable_instant_but_it_can_still_decline_payment(cards):
    s = game(cards)
    cast(s, NAMES[5])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    target = cast(s, 'Sol Ring', resolve=False)
    uncounterable = cast(s, 'Last Word', [target.id], pid='p2', resolve=False)
    settle(s)
    assert s.state.rules.decision.resume['opt']['cost'] == '{4}'
    choose(s, ['decline'])
    assert s.state.cards[target.id].zone == 'p1:graveyard' and s.state.cards[uncounterable.id].zone == 'p2:graveyard'
    roundtrip(s)

def test_chaos_world_rule_replaces_old_world_and_noninstant_does_not_trigger_tax(cards):
    s = game(cards)
    old = cast(s, NAMES[5])
    creature = cast(s, 'Grizzly Bears')
    assert s.state.cards[creature.id].zone == 'p1:battlefield' and s.state.rules.decision is None
    world = cast(s, 'Concordant Crossroads')
    assert s.state.cards[old.id].zone == 'p1:graveyard' and s.state.cards[world.id].zone == 'p1:battlefield'
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.players['p1'].life == 37 and s.state.rules.decision is None
    roundtrip(s)


def test_canonical_chaos_requires_supported_world_and_tax_definition(cards):
    assert coverage.of_card_data(cards.resolve(NAMES[5])).level == 'FULL'


def test_chaos_original_tax_survives_actual_instant_destroying_source(cards):
    s = game(cards)
    source = cast(s, NAMES[5])
    for pid in ('p2', 'p3'):
        act(s, pid, type='set_prefs', hold_priority=True)
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    destroy = cast(s, 'Abrupt Decay', [source.id], pid='p3', resolve=False)
    settle(s)
    assert s.state.rules.decision.player == 'p3'
    assert s.state.rules.decision.resume['opt']['cost'] == '{2}'
    choose(s, ['pay'])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[destroy.id].zone == 'p3:graveyard'
    assert s.state.rules.decision.player == 'p2'
    choose(s, ['decline'])
    assert s.state.cards[bolt.id].zone == 'p2:graveyard'
    assert s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_true_fresh_process_chaos_pending_tax_preserves_original_payer(cards, tmp_path, pay):
    import os
    import subprocess
    import sys

    import app

    s = game(cards)
    source = cast(s, NAMES[5])
    target = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    settle(s)
    assert s.state.rules.decision.player == 'p2'
    saved = tmp_path / 'chaos.json'
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
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source,target,pay=sys.argv[3:]
d=s.state.rules.decision
assert d and d.player=='p2' and d.resume['opt']['cost']=='{1}'
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay' if pay=='yes' else 'decline'])
settle(s)
assert s.state.cards[source].zone=='p1:battlefield'
assert s.state.cards[target].zone=='p2:graveyard'
assert s.state.players['p1'].life==(37 if pay=='yes' else 40)
roundtrip(s)
repo.close()
'''
    backend = Path(app.__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, target.id, 'yes' if pay else 'no'],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)}, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


def test_old_save_without_original_cast_object_requires_manual_not_guessed_zero(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = game(cards)
    source = cast(s, NAMES[5])
    act(s, 'p2', type='set_prefs', hold_priority=True)
    target = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    entry = next(e for e in s.state.rules.stack.values() if e.source_card == source.id)
    assert entry.event and entry.event.objects
    entry.event.objects = []
    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    settle(s)
    decision = s.state.rules.decision
    assert decision and decision.kind == 'manual_resolution'
    assert decision.resume['step'] == 'tax_event_known79'
    choose(s, ['done'])
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    assert s.state.players['p1'].life == 37
    roundtrip(s)
