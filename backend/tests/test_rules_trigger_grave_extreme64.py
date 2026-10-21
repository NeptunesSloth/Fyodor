"""The greatest graveyard creature is chosen without targets at resolution."""
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

NAME = 'Desecrator Hag'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_grave_extreme64_cards.json').read_text())


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


def setup(cards, graves=('Grizzly Bears', 'Hill Giant')):
    deck = [*[c['name'] for c in DATA], 'Grizzly Bears']
    s = table(cards, deck, deck, deck)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    dead = [put(s, name, 'graveyard') for name in graves]
    return s, dead


def cast(s, name=NAME, pool=None, targets=()):
    wait_priority(s, 'p1')
    c = put(s, name, 'hand')
    mana(s, **(pool or {'C': 2, 'B': 2}))
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=list(targets))
    return c


def choose(s, card_id):
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'choose_cards'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[card_id])
    settle(s)


def test_whole_actual_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'
    s, (bear, giant) = setup(cards)
    hag = cast(s)
    settle(s)
    assert hag.zone == 'p1:battlefield' and giant.zone == 'p1:hand' and bear.zone == 'p1:graveyard'
    roundtrip(s)


def test_tied_maximum_is_native_untargeted_owner_choice(cards):
    s, (bear,) = setup(cards, ('Grizzly Bears',))
    other = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p1' and c.id != bear.id)
    act(s, 'p1', type='move', card_ids=[other.id], to={'player': 'p1', 'zone': 'graveyard'})
    cast(s)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {bear.id, other.id}
    choose(s, other.id)
    assert other.zone == 'p1:hand' and bear.zone == 'p1:graveyard'


def test_stale_tied_choice_cannot_return_a_new_exile_incarnation(cards):
    s, (bear,) = setup(cards, ('Grizzly Bears',))
    other = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p1' and c.id != bear.id)
    act(s, 'p1', type='move', card_ids=[other.id], to={'player': 'p1', 'zone': 'graveyard'})
    cast(s)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {bear.id, other.id}
    act(s, 'p1', type='move', card_ids=[other.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[other.id])
    settle(s)
    assert other.zone == 'p1:exile' and bear.zone == 'p1:graveyard'


def test_opponent_graveyard_and_noncreature_cards_are_excluded(cards):
    s, (bear,) = setup(cards, ('Grizzly Bears',))
    giant = put(s, 'Hill Giant', 'graveyard', 'p2')
    land = put(s, 'Forest', 'graveyard')
    cast(s)
    settle(s)
    assert bear.zone == 'p1:hand' and giant.zone == 'p2:graveyard' and land.zone == 'p1:graveyard'


def test_negative_power_is_a_real_maximum_when_alone(cards):
    s, (rumbler,) = setup(cards, ('Char-Rumbler',))
    cast(s)
    settle(s)
    assert rumbler.zone == 'p1:hand'


def test_star_power_is_evaluated_in_graveyard(cards):
    s, (bear, giant, goyf) = setup(cards, ('Grizzly Bears', 'Hill Giant', 'Lhurgoyf'))
    foreign = put(s, 'Hill Giant', 'graveyard', 'p2')
    cast(s)
    settle(s)
    assert goyf.zone == 'p1:hand' and giant.zone == 'p1:graveyard' and foreign.zone == 'p2:graveyard'


def test_empty_graveyard_does_not_hold_a_target_or_choice(cards):
    s, _ = setup(cards, ())
    hag = cast(s)
    settle(s)
    assert hag.zone == 'p1:battlefield' and s.state.rules.decision is None


def test_native_response_changes_greatest_before_resolution(cards):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s, (bear, giant) = setup(cards)
    hag = cast(s)
    resolve_only(s, hag)
    assert s.state.zones['stack']
    cast(s, 'Reclaim', {'G': 1}, [giant.id])
    settle(s)
    assert giant.zone == 'p1:library' and bear.zone == 'p1:hand'


@pytest.mark.parametrize('change', ['bounce', 'control'])
def test_original_controller_graveyard_after_source_change(cards, change):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s, (bear, giant) = setup(cards)
    foreign = put(s, 'Lhurgoyf', 'graveyard', 'p2')
    hag = cast(s)
    resolve_only(s, hag)
    if change == 'bounce':
        cast(s, 'Boomerang', {'U': 2}, [hag.id])
    else:
        act(s, 'p1', type='set_controller', card_ids=[hag.id], player='p2')
    settle(s)
    assert giant.zone == 'p1:hand' and bear.zone == 'p1:graveyard' and foreign.zone == 'p2:graveyard'


@pytest.mark.parametrize('tie', [False, True])
def test_true_cold_pending_enter_trigger(cards, tmp_path, tie):
    import subprocess
    import sys

    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s, dead = setup(cards, ('Grizzly Bears',) if tie else ('Grizzly Bears', 'Hill Giant'))
    bear = dead[0]
    giant = dead[-1]
    if tie:
        giant = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p1' and c.id != bear.id)
        act(s, 'p1', type='move', card_ids=[giant.id], to={'player': 'p1', 'zone': 'graveyard'})
    hag = cast(s)
    resolve_only(s, hag)
    if tie:
        settle(s)
        assert s.state.rules.decision is not None and s.state.rules.decision.kind == 'choose_cards'
    saved = tmp_path / 'hag.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
assert s.state.zones['stack'] or s.state.rules.decision is not None
settle(s)
if s.state.rules.decision is not None:
    from tests.game_helpers import act
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[sys.argv[3]])
    settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:hand'
'''
    out = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), giant.id], capture_output=True, text=True, timeout=90)
    assert out.returncode == 0, out.stdout + out.stderr
