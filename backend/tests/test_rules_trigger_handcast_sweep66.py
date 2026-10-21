"""Native paid hand-cast sweeping preserves every exclusion and original receipt."""
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

NAME = 'Cyclone Summoner'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_handcast_sweep66_cards.json').read_text())


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
    deck = [c['name'] for c in DATA]
    s = table(cards, deck, deck, deck)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s


def cast(s, name=NAME, pool=None, targets=(), *, resolve=True):
    wait_priority(s, 'p1')
    c = put(s, name, 'hand')
    mana(s, **(pool or {'C': 5, 'U': 2}))
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=list(targets))
    if resolve:
        settle(s)
    return c


def test_whole_canonical_paid_cast_sweeps_all_players_and_permanent_types(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'
    s = setup(cards)
    targets = [put(s, n, 'battlefield', p) for n, p in [('Grizzly Bears', 'p2'), ('Icy Manipulator', 'p3'),
                                                       ('Howling Mine', 'p1'), ('Unnatural Selection', 'p2')]]
    source = cast(s)
    assert source.zone == 'p1:battlefield'
    for c in targets:
        assert c.zone == c.owner + ':hand'
    roundtrip(s)


def test_giants_wizards_changelings_noncreature_wizards_and_lands_are_excluded(cards):
    s = setup(cards)
    protected = [put(s, n, 'battlefield', p) for n, p in [('Hill Giant', 'p2'), ('Universal Automaton', 'p2'),
                                                         ("Diviner's Wand", 'p3'), ('Dryad Arbor', 'p1'),
                                                         ('Forest', 'p1')]]
    source = cast(s)
    assert source.zone == 'p1:battlefield'
    assert all(c.zone.endswith(':battlefield') for c in protected)


def test_stolen_unprotected_permanent_returns_to_actual_owner(cards):
    s = setup(cards)
    victim = put(s, 'Icy Manipulator', 'battlefield', 'p3')
    act(s, 'p3', type='set_controller', card_ids=[victim.id], player='p2')
    cast(s)
    assert victim.zone == 'p3:hand'


def test_real_zombify_does_not_trigger_handcast_sweep(cards):
    s = setup(cards)
    source = put(s, NAME, 'graveyard')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Zombify', {'C': 2, 'B': 2}, [source.id])
    assert source.zone == 'p1:battlefield' and bear.zone == 'p2:battlefield'


def test_real_blink_does_not_give_successor_a_handcast_receipt(cards):
    s = setup(cards)
    source = cast(s)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    old = s.state.rules.object_id(source.id)
    cast(s, 'Cloudshift', {'W': 1}, [source.id])
    assert source.zone == 'p1:battlefield' and s.state.rules.object_id(source.id) != old
    assert bear.zone == 'p2:battlefield'


def test_new_spell_controller_did_not_cast_the_source_from_their_hand(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    source = cast(s, resolve=False)
    assert source.zone == 'stack'
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert source.zone == 'p2:battlefield' and bear.zone == 'p3:battlefield'


@pytest.mark.parametrize('change', ['bounce', 'control', 'blink'])
def test_pending_original_handcast_receipt_survives_source_change(cards, change):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = cast(s, resolve=False)
    resolve_only(s, source)
    assert s.state.zones['stack']
    if change == 'control':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
        settle(s)
    else:
        cast(s, 'Boomerang' if change == 'bounce' else 'Cloudshift',
             {'U': 2} if change == 'bounce' else {'W': 1}, [source.id])
    assert bear.zone == 'p2:hand'


@pytest.mark.parametrize('change_source', [False, True])
def test_current_subtype_changes_before_resolution_determine_exclusion(cards, change_source):
    from tests.test_rules_counter_event_comparisons50 import resolve_only
    from tests.test_rules_wave6c_tokens_pumps import chars

    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    selector = put(s, 'Unnatural Selection', 'battlefield')
    source = cast(s, resolve=False)
    resolve_only(s, source)
    wait_priority(s, 'p1')
    mana(s, C=1)
    ability = next(a for a in chars(s, selector).abilities if a.kind == 'activated')
    changed = source if change_source else bear
    act(s, 'p1', type='activate_ability', card_id=selector.id, ability=ability.index, targets=[changed.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['Bear' if change_source else 'Wizard'])
    settle(s)
    if change_source:
        assert source.zone == 'p1:hand' and bear.zone == 'p2:hand'
    else:
        assert bear.zone == 'p2:battlefield' and 'Wizard' in chars(s, bear).subtypes
    assert selector.zone == 'p1:hand'


def test_true_cold_pending_sweep(cards, tmp_path):
    import subprocess
    import sys

    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    giant = put(s, 'Hill Giant', 'battlefield', 'p3')
    source = cast(s, resolve=False)
    resolve_only(s, source)
    saved = tmp_path / 'sweep66.json'
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
assert s.state.zones['stack']
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p2:hand'
assert s.state.cards[sys.argv[4]].zone=='p3:battlefield'
'''
    out = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), bear.id, giant.id], capture_output=True, text=True, timeout=90)
    assert out.returncode == 0, out.stdout + out.stderr
