"""Opponent graveyard cards return to the bottom of their owners libraries."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

NAMES = ['Landscaper Colos']
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_grave_bottom51_cards.json').read_text())


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


def cast(s, name, pool, targets=(), pid='p1', resolve=True):
    wait_priority(s, pid)
    spell = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=spell.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return spell



def setup(cards):
    names = NAMES + ['Grizzly Bears', 'Forest', 'Island', 'Sol Ring']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s


def test_full_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAMES[0])).level == 'FULL'


@pytest.mark.parametrize('pid', ['p2','p3'])
def test_native_paid_entry_targets_opponent_graveyard_and_bottoms_in_owner_library(cards, pid):
    s = setup(cards)
    corpse = put(s, 'Grizzly Bears', 'graveyard', pid)
    own = put(s, 'Sol Ring', 'graveyard')
    source = cast(s, NAMES[0], {'C': 5, 'W': 1})
    d = s.state.rules.decision
    assert d is not None and corpse.id in {o.id for o in d.options} and own.id not in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[corpse.id])
    settle(s)
    assert source.zone == 'p1:battlefield' and corpse.zone == f'{pid}:library'
    assert s.state.zones[f'{pid}:library'][-1] == corpse.id
    assert own.zone == 'p1:graveyard'
    roundtrip(s)


def test_no_legal_opponent_graveyard_does_not_target_own_graveyard(cards):
    s = setup(cards)
    own = put(s, 'Sol Ring', 'graveyard')
    source = cast(s, NAMES[0], {'C': 5, 'W': 1})
    assert s.state.rules.decision is None and own.zone == 'p1:graveyard' and source.zone == 'p1:battlefield'
    roundtrip(s)


def test_paid_native_basic_landcycling_discards_searches_no_draw_and_no_entry(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s = setup(cards)
    source = put(s, NAMES[0], 'hand')
    corpse = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    before = len(s.state.zones['p1:hand'])
    mana(s, C=1, W=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Basic landcycling'), sources=[])
    assert source.zone == 'p1:graveyard' and not s.state.players['p1'].mana
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    forest = next(c for c in s.state.cards.values() if c.name == 'Forest' and c.zone == 'p1:library')
    assert forest.id in {o.id for o in d.options}
    assert not any(c.name == 'Sol Ring' for c in s.state.cards.values() if c.id in {o.id for o in d.options})
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[forest.id])
    settle(s)
    assert forest.zone == 'p1:hand' and corpse.zone == 'p2:graveyard'
    assert len(s.state.zones['p1:hand']) == before and s.state.rules.decision is None
    roundtrip(s)


def test_target_that_left_graveyard_and_returned_is_new_object(cards):
    s = setup(cards)
    corpse = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    cast(s, NAMES[0], {'C': 5, 'W': 1})
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[corpse.id])
    old = s.state.rules.object_id(corpse.id)
    act(s, 'p2', type='move', card_ids=[corpse.id], to={'player': 'p2', 'zone': 'hand'})
    act(s, 'p2', type='move', card_ids=[corpse.id], to={'player': 'p2', 'zone': 'graveyard'})
    assert old != s.state.rules.object_id(corpse.id)
    settle(s)
    assert corpse.zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['entry', 'cycling'])
def test_true_cold_target_owner_bottom_or_basic_land_search(cards, tmp_path, mode):
    from tests.test_rules_wave7b_activation import ability_index

    s = setup(cards)
    corpse = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    if mode == 'entry':
        source = cast(s, NAMES[0], {'C': 5, 'W': 1})
    else:
        source = put(s, NAMES[0], 'hand')
        mana(s, C=1, W=1)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Basic landcycling'), sources=[])
        settle(s)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'colos.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=s.state.cards[sys.argv[3]]
corpse=s.state.cards[sys.argv[4]]
d=s.state.rules.decision
assert d is not None
if sys.argv[5]=='entry':
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[corpse.id])
 settle(s)
 assert corpse.zone=='p2:library' and s.state.zones['p2:library'][-1]==corpse.id
 assert source.zone=='p1:battlefield'
else:
 forest=next(c for c in s.state.cards.values() if c.name=='Forest' and c.zone=='p1:library')
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[forest.id])
 settle(s)
 assert forest.zone=='p1:hand' and source.zone=='p1:graveyard' and corpse.zone=='p2:graveyard'
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, corpse.id, mode],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
