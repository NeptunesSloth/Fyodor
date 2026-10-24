"""Native saddle payment, designation, contributors and frozen counter cohorts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, sba
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

NAMES = ['Master of Cruelties', 'Bone Dancer', 'Stromgald Spy']
DATA = json.loads((Path(__file__).parent / 'fixtures/unblocked_choices79_cards.json').read_text())


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




@pytest.mark.parametrize('name', NAMES)
def test_whole_card_full(cards, name):
    report = coverage.of_card_data(cards.resolve(name))
    assert report.level == 'FULL', report


def test_master_alone_group(cards):
    from app.game.errors import ActionError
    s = table(cards, NAMES + ['Grizzly Bears'], [], [])
    master = put(s, 'Master of Cruelties', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    to_phase(s, 'declare_attackers', turn=7)
    with pytest.raises(ActionError):
        attack(s, (master, 'p2'), (bear, 'p2'))
    attack(s, (master, 'p2'))


def setup79(cards, name):
    s = table(cards, [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves'], ['Grizzly Bears', 'Llanowar Elves', 'Forest', 'Island'], [])
    source = put(s, name, 'battlefield')
    start(s)
    return s, source


def unblocked79(s, source):
    from tests.test_rules_unblocked_riders32 import unblocked
    unblocked(s, source)


def answer79(s, yes):
    from tests.test_rules_designations import pick
    assert s.state.rules.decision is not None
    pick(s, ['yes' if yes else 'no'])
    settle(s)


def test_master_actual_unblocked_life_assignment(cards):
    s, source = setup79(cards, 'Master of Cruelties')
    unblocked79(s, source)
    assert s.state.players['p2'].life == 1
    assert 'assign_none' in chars(s, source).imposed
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == 1
    to_phase(s, 'main2', turn=4)
    assert 'assign_none' not in chars(s, source).imposed


@pytest.mark.parametrize('yes', [True, False])
def test_bone_current_top_creature_ignores_noncreature(cards, yes):
    s, source = setup79(cards, 'Bone Dancer')
    bear = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    put(s, 'Forest', 'graveyard', 'p2')
    unblocked79(s, source)
    answer79(s, yes)
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    assert s.state.cards[elf.id].zone == ('p1:battlefield' if yes else 'p2:graveyard')
    assert ('assign_none' in chars(s, source).imposed) is yes
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == (40 if yes else 38)


@pytest.mark.parametrize('yes', [True, False])
def test_spy_live_visibility_and_damage(cards, yes):
    from app.game.visibility import can_see, SPECTATOR
    s, source = setup79(cards, 'Stromgald Spy')
    hidden = put(s, 'Forest', 'hand', 'p2')
    unblocked79(s, source)
    answer79(s, yes)
    assert can_see(s.state, hidden, 'p1') is yes
    assert can_see(s.state, hidden, SPECTATOR) is yes
    assert ('assign_none' in chars(s, source).imposed) is yes
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == (40 if yes else 38)


def test_bone_prevented_entry_does_not_pay_no_damage(cards):
    s, source = setup79(cards, 'Bone Dancer')
    cage = put(s, "Grafdigger's Cage", 'battlefield')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    unblocked79(s, source)
    answer79(s, True)
    assert s.state.cards[elf.id].zone == 'p2:graveyard'
    assert 'assign_none' not in chars(s, source).imposed
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == 38


def test_bone_empty_graveyard_does_not_pay(cards):
    s, source = setup79(cards, 'Bone Dancer')
    put(s, 'Forest', 'graveyard', 'p2')
    unblocked79(s, source)
    answer79(s, True)
    assert 'assign_none' not in chars(s, source).imposed
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == 38


@pytest.mark.parametrize('change', ['control', 'leave', 'blink'])
def test_spy_reveal_fixed_player_and_source_duration(cards, change):
    from app.game.visibility import can_see
    s, source = setup79(cards, 'Stromgald Spy')
    hidden = put(s, 'Forest', 'hand', 'p2')
    unblocked79(s, source)
    answer79(s, True)
    assert can_see(s.state, hidden, 'p1')
    later = put(s, 'Island', 'hand', 'p2')
    assert can_see(s.state, later, 'p1')
    if change == 'control':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    else:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player':'p1','zone':'hand'})
        if change == 'blink':
            act(s, 'p1', type='move', card_ids=[source.id], to={'player':'p1','zone':'battlefield'})
    assert can_see(s.state, hidden, 'p1') is (change == 'control')
    assert can_see(s.state, later, 'p1') is (change == 'control')


@pytest.mark.parametrize('name', NAMES)
def test_genuine_cold_native_unblocked_resolution(cards, tmp_path, name):
    import subprocess
    import sys
    import app
    s, source = setup79(cards, name)
    hidden = put(s, 'Forest', 'hand', 'p2')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    from tests.test_rules_wave30m_durations import stops
    stops(s, 'main1', 'declare_attackers', 'declare_blockers', 'combat_damage', 'end_combat')
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    to_phase(s, 'declare_blockers', turn=4)
    # Native blockers submission commits the unblocked event and leaves actual trigger pending.
    if s.state.rules.decision is not None:
        act(s, 'p2', type='declare_blockers', blocks=[])
    assert s.state.zones.get('stack')
    saved = tmp_path / 'unblocked.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.visibility import can_see,SPECTATOR
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_wave6c_tokens_pumps import chars
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
name,source,hidden,elf=sys.argv[3:]
settle(s)
if name!='Master of Cruelties':
 d=s.state.rules.decision
 assert d and d.kind=='confirm'
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes'])
 settle(s)
assert 'assign_none' in chars(s,s.state.cards[source]).imposed
if name=='Master of Cruelties':assert s.state.players['p2'].life==1
elif name=='Bone Dancer':assert s.state.cards[elf].zone=='p1:battlefield'
else:assert can_see(s.state,s.state.cards[hidden],SPECTATOR)
assert s.state.rules.decision is None
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, source.id, hidden.id, elf.id],
        capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr
