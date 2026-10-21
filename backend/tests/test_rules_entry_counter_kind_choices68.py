"""Whole Bribe Taker freezes resolution-time kinds and uses native optional choices."""
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
from tests.test_rules_counter_event_comparisons50 import resolve_only
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

SOURCE = 'Bribe Taker'
DATA = json.loads((Path(__file__).parent / 'fixtures/entry_counter_kind_choices68_cards.json').read_text())
NAMES = [c['name'] for c in DATA] + ['Grizzly Bears', 'Sol Ring']


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
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s


def cast(s, pending=False):
    c = put(s, SOURCE, 'hand')
    mana(s, C=5, G=1)
    act(s, 'p1', type='cast_spell', card_id=c.id, sources=[])
    if pending:
        resolve_only(s, c)
    else:
        settle(s)
    assert c.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    return c


def choose(s, option):
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'pick_one'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[str(option)])
    settle(s)


def test_whole_canonical(cards):
    assert coverage.of_card_data(cards.resolve(SOURCE)).level == 'FULL'


def test_no_kinds_means_no_choices(cards):
    s = setup(cards)
    c = cast(s)
    assert not c.counters and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('choice,expected', [(0, {'+1/+1': 1}), (1, {'shield': 1}), (2, {})])
def test_one_kind_ignores_quantity_and_repeated_permanents(cards, choice, expected):
    s = setup(cards)
    a = put(s, 'Sol Ring', 'battlefield')
    b = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[a.id], kind='shield', delta=9)
    act(s, 'p1', type='counter', card_ids=[b.id], kind='shield', delta=3)
    c = cast(s)
    choose(s, choice)
    assert c.counters == expected and s.state.rules.decision is None
    roundtrip(s)


def test_kinds_frozen_before_new_counters_and_independent_may(cards):
    s = setup(cards)
    a = put(s, 'Sol Ring', 'battlefield')
    for kind, n in [('charge', 4), ('shield', 2), ('stun', 1)]:
        act(s, 'p1', type='counter', card_ids=[a.id], kind=kind, delta=n)
    c = cast(s)
    choose(s, 0)
    choose(s, 1)
    choose(s, 2)
    assert c.counters == {'+1/+1': 1, 'shield': 1}
    assert s.state.rules.decision is None
    roundtrip(s)


def test_opponent_and_nonbattlefield_counters_do_not_count(cards):
    s = setup(cards)
    for zone, pid in [('battlefield', 'p2'), ('hand', 'p1'), ('graveyard', 'p1')]:
        a = put(s, 'Sol Ring', zone, pid)
        act(s, pid, type='counter', card_ids=[a.id], kind='charge', delta=1)
    c = cast(s)
    assert not c.counters and s.state.rules.decision is None
    roundtrip(s)


def test_resolution_time_kinds(cards):
    s = setup(cards)
    a = put(s, 'Sol Ring', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[a.id], kind='charge', delta=1)
    c = cast(s, pending=True)
    act(s, 'p1', type='counter', card_ids=[a.id], kind='charge', delta=-1)
    act(s, 'p1', type='counter', card_ids=[a.id], kind='shield', delta=7)
    settle(s)
    choose(s, 1)
    assert c.counters == {'shield': 1}
    roundtrip(s)


def test_doubling_season_applies_to_each_chosen_counter(cards):
    s = setup(cards)
    a = put(s, 'Sol Ring', 'battlefield')
    for kind, n in [('charge', 3), ('shield', 4)]:
        act(s, 'p1', type='counter', card_ids=[a.id], kind=kind, delta=n)
    put(s, 'Doubling Season', 'battlefield')
    c = cast(s)
    choose(s, 0)
    choose(s, 1)
    assert c.counters == {'+1/+1': 2, 'shield': 2}
    roundtrip(s)


def test_counter_prohibition_makes_put_choices_unavailable(cards):
    s = setup(cards)
    a = put(s, 'Sol Ring', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[a.id], kind='charge', delta=2)
    put(s, 'Solemnity', 'battlefield')
    c = cast(s)
    assert not c.counters and s.state.rules.decision is None
    roundtrip(s)


def test_original_ability_controller_owns_the_count_and_choices(cards):
    s = setup(cards)
    a = put(s, 'Sol Ring', 'battlefield')
    b = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[a.id], kind='charge', delta=3)
    act(s, 'p2', type='counter', card_ids=[b.id], kind='shield', delta=4)
    c = cast(s, pending=True)
    act(s, 'p1', type='set_controller', card_ids=[c.id], player='p2')
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, 1)
    assert c.counters == {'charge': 1}
    roundtrip(s)


def test_departed_source_is_not_a_new_incarnation(cards):
    s = setup(cards)
    a = put(s, 'Sol Ring', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[a.id], kind='charge', delta=3)
    c = cast(s, pending=True)
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert c.counters == {} and s.state.rules.decision is None
    roundtrip(s)


def test_printed_trample_uses_augmented_power(cards):
    from tests.test_rules_conditional_prevention import damage
    from tests.test_rules_counter_alternatives50 import attack, to_phase

    s = setup(cards)
    a = put(s, 'Sol Ring', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[a.id], kind='charge', delta=1)
    c = cast(s)
    choose(s, 0)
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack(s, [c], turn=7)
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': c.id}])
    damage(s)
    d = s.state.rules.decision
    assert d
    act(s, 'p1', type='choose', decision_id=d.id, amounts=[2, 5])
    settle(s)
    assert blocker.zone == 'p2:graveyard' and s.state.players['p2'].life == 35
    assert c.zone == 'p1:battlefield'
    roundtrip(s)


def test_true_cold_mid_choice_retains_original_kinds(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    a = put(s, 'Sol Ring', 'battlefield')
    for kind in ('charge', 'shield'):
        act(s, 'p1', type='counter', card_ids=[a.id], kind=kind, delta=4)
    c = cast(s)
    choose(s, 0)
    saved = tmp_path / 'bribe68.json'
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
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d and d.resume['step']=='pick_one'
act(s,d.player,type='choose',decision_id=d.id,option_ids=['1'])
settle(s)
assert s.state.cards[sys.argv[3]].counters=={'+1/+1':1,'shield':1}
assert s.state.rules.decision is None
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), c.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_source_counters_count_and_plus_one_kind_has_one_put_option(cards):
    s = setup(cards)
    c = cast(s, pending=True)
    act(s, 'p1', type='counter', card_ids=[c.id], kind='+1/+1', delta=3)
    settle(s)
    d = s.state.rules.decision
    assert d and len(d.options) == 2
    choose(s, 0)
    assert c.counters == {'+1/+1': 4} and s.state.rules.decision is None
    roundtrip(s)
