"""Only a single simultaneous damage event meets Innocent Bystander's threshold."""
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
from tests.test_rules_conditional_prevention import activate, attack, damage
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Innocent Bystander'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_damage_threshold70_cards.json').read_text())


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


def cast(s, name, targets=(), resolve=True, modes=()):
    wait_priority(s, 'p1')
    source = put(s, name, 'hand')
    mana(s, C=2, R=1, G=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=list(targets), sources=[], modes=list(modes))
    if resolve:
        settle(s)
    return source


def setup(cards):
    names = [c['name'] for c in DATA] + ['Llanowar Elves']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s, cast(s, NAME)


def clues(s):
    return [c for c in s.state.cards.values() if c.name == 'Clue' and c.zone.endswith(':battlefield')]


def test_whole_actual_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_actual_bolt_kills_source_but_creates_one_clue_then_paid_draw(cards):
    s, source = setup(cards)
    cast(s, 'Lightning Bolt', [source.id])
    assert source.zone == 'p1:graveyard'
    clue, = clues(s)
    assert clue.controller == 'p1'
    hand = len(s.state.zones['p1:hand'])
    activate(s, clue, 'Draw a card')
    assert len(s.state.zones['p1:hand']) == hand + 1
    assert not clues(s)
    roundtrip(s)


def test_two_damage_is_insufficient_even_when_lethal(cards):
    s, source = setup(cards)
    cast(s, 'Shock', [source.id])
    assert source.zone == 'p1:graveyard' and not clues(s)
    roundtrip(s)


def test_separate_two_plus_two_damage_events_do_not_add_to_threshold(cards):
    s, source = setup(cards)
    cast(s, 'Giant Growth', [source.id])
    cast(s, 'Shock', [source.id])
    assert source.zone == 'p1:battlefield' and source.damage == 2 and not clues(s)
    other = put(s, 'Shock', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=other.id, targets=[source.id], sources=[])
    settle(s)
    assert source.zone == 'p1:graveyard' and not clues(s)
    roundtrip(s)


def test_replaced_six_damage_is_one_threshold_event(cards):
    s, source = setup(cards)
    put(s, 'Furnace of Rath', 'battlefield')
    cast(s, 'Lightning Bolt', [source.id])
    assert source.zone == 'p1:graveyard' and len(clues(s)) == 1
    roundtrip(s)


def test_prevented_damage_does_not_meet_threshold(cards):
    s, source = setup(cards)
    bolt = cast(s, 'Lightning Bolt', [source.id], resolve=False)
    salve = cast(s, 'Healing Salve', [source.id], resolve=False, modes=[1])
    # The selected mode prevents the next three damage to the creature.
    assert salve.zone == 'stack'
    settle(s)
    assert bolt.zone == 'p1:graveyard'
    assert source.zone == 'p1:battlefield' and source.damage == 0 and not clues(s)
    roundtrip(s)


def test_simultaneous_two_plus_one_combat_damage_triggers_once(cards):
    s, source = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    elf = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=7)
    cast(s, 'Giant Growth', [source.id])
    attack(s, [source], turn=7)
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id':bear.id,'attacker_id':source.id},
                                               {'blocker_id':elf.id,'attacker_id':source.id}])
    damage(s)
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type='choose', decision_id=d.id, amounts=[2, 3])
    settle(s)
    assert source.damage == 3 and len(clues(s)) == 1
    roundtrip(s)


def test_true_cold_pending_threshold_after_source_dies(cards, tmp_path):
    import app

    s, source = setup(cards)
    bolt = cast(s, 'Lightning Bolt', [source.id], resolve=False)
    for _ in range(12):
        if bolt.zone != 'stack':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert source.zone == 'p1:graveyard' and s.state.zones['stack']
    saved = tmp_path / 'threshold.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
settle(s)
assert sum(c.name=='Clue' and c.zone=='p1:battlefield' for c in s.state.cards.values())==1
roundtrip(s)
'''
    p = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)],capture_output=True,text=True,timeout=90,cwd=Path(app.__file__).resolve().parents[1])
    assert p.returncode == 0, p.stdout + p.stderr
