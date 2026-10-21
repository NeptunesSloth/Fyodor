"""Attached-artifact controller damage uses current information or exact LKI."""
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

NAME = 'Gremlin Infestation'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_attached_artifact67_cards.json').read_text())


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


def setup(cards, owner='p2'):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    artifact = put(s, 'Sol Ring', 'battlefield', owner)
    aura = put(s, NAME, 'hand')
    mana(s, C=3, R=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[artifact.id], sources=[])
    settle(s)
    assert aura.zone == 'p1:battlefield' and aura.attached_to == artifact.id
    return s, aura, artifact


def test_complete_actual_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('owner', ['p1', 'p2', 'p3'])
def test_native_paid_aura_damages_artifact_controller_on_auras_end_step(cards, owner):
    s, aura, artifact = setup(cards, owner)
    before = s.state.players[owner].life
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.players[owner].life == before - 2
    assert aura.attached_to == artifact.id
    roundtrip(s)


def test_opponents_end_step_does_not_trigger(cards):
    s, _, _ = setup(cards)
    to_phase(s, 'end', turn=4)
    settle(s)
    before = {p: s.state.players[p].life for p in s.state.players}
    to_phase(s, 'end', turn=5)
    settle(s)
    assert {p: s.state.players[p].life for p in s.state.players} == before
    roundtrip(s)


def test_control_change_before_resolution_uses_current_artifact_controller(cards):
    s, _, artifact = setup(cards)
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='set_controller', card_ids=[artifact.id], player='p3')
    before = {p: s.state.players[p].life for p in s.state.players}
    settle(s)
    assert s.state.players['p3'].life == before['p3'] - 2
    assert s.state.players['p2'].life == before['p2']
    roundtrip(s)


def test_departed_aura_still_uses_original_host_current_controller(cards):
    s, aura, artifact = setup(cards)
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='move', card_ids=[aura.id], to={'player':'p1','zone':'graveyard'})
    act(s, 'p1', type='set_controller', card_ids=[artifact.id], player='p3')
    before = s.state.players['p3'].life
    settle(s)
    assert s.state.players['p3'].life == before - 2
    roundtrip(s)


def test_host_departure_uses_last_controller_and_creates_token_for_aura_controller(cards):
    s, aura, artifact = setup(cards)
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='set_controller', card_ids=[artifact.id], player='p3')
    before = s.state.players['p3'].life
    spell = put(s, 'Disenchant', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[artifact.id], sources=[])
    settle(s)
    assert s.state.players['p3'].life == before - 2
    assert aura.zone == 'p1:graveyard'
    tokens = [c for c in s.state.cards.values() if c.name == 'Gremlin' and c.zone.endswith(':battlefield')]
    assert len(tokens) == 1 and tokens[0].controller == 'p1', [(x.name,x.object_id,x.attached_to,x.attached) for x in s.state.rules.lki.values() if x.card in (artifact.id,aura.id)]
    roundtrip(s)


def test_blinked_host_successor_does_not_replace_original_controller(cards):
    s, _, artifact = setup(cards)
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='move', card_ids=[artifact.id], to={'player':'p2','zone':'exile'})
    act(s, 'p1', type='move', card_ids=[artifact.id], to={'player':'p2','zone':'battlefield'})
    act(s, 'p1', type='set_controller', card_ids=[artifact.id], player='p3')
    before = {p:s.state.players[p].life for p in s.state.players}
    settle(s)
    assert s.state.players['p2'].life == before['p2'] - 2
    assert s.state.players['p3'].life == before['p3']
    assert not any(c.name == 'Gremlin' for c in s.state.cards.values())
    roundtrip(s)


def test_true_cold_pending_trigger_retains_departed_host_lki(cards, tmp_path):
    s, _, artifact = setup(cards)
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='set_controller', card_ids=[artifact.id], player='p3')
    spell = put(s, 'Disenchant', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[artifact.id], sources=[])
    for _ in range(12):
        if spell.zone != 'stack':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert spell.zone == 'p1:graveyard' and s.state.zones['stack']
    saved = tmp_path / 'gremlin.json'
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
before=s.state.players['p3'].life
settle(s)
assert s.state.players['p3'].life==before-2
assert sum(c.name=='Gremlin' and c.zone=='p1:battlefield' for c in s.state.cards.values())==1
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def hex_setup(cards, attached=True):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    equipment = put(s, 'Bonesplitter', 'battlefield', 'p2')
    creature = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if attached:
        act(s, 'p2', type='attach', card_ids=[equipment.id], to=creature.id)
    aura = put(s, "Artificer's Hex", 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[equipment.id], sources=[])
    settle(s)
    return s, aura, equipment, creature


def test_complete_actual_canonical_hex(cards):
    assert coverage.of_card_data(cards.resolve("Artificer's Hex")).level == 'FULL'


def test_hex_uses_auras_upkeep_and_destroys_equipped_creature(cards):
    s, _, _, creature = hex_setup(cards)
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert creature.zone == 'p2:battlefield'
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    assert creature.zone == 'p2:graveyard'
    roundtrip(s)


def test_hex_no_retroactive_trigger_when_unattached_at_upkeep(cards):
    s, _, equipment, creature = hex_setup(cards, False)
    to_phase(s, 'upkeep', turn=7)
    assert not s.state.zones.get('stack')
    act(s, 'p2', type='attach', card_ids=[equipment.id], to=creature.id)
    settle(s)
    assert creature.zone == 'p2:battlefield'
    roundtrip(s)


def test_hex_rechecks_attachment_at_resolution(cards):
    s, _, equipment, creature = hex_setup(cards)
    to_phase(s, 'upkeep', turn=7)
    assert s.state.zones['stack']
    act(s, 'p2', type='detach', card_ids=[equipment.id])
    settle(s)
    assert creature.zone == 'p2:battlefield'
    roundtrip(s)


def test_hex_actual_instant_equip_changes_which_creature_dies(cards):
    from tests.test_rules_conditional_prevention import activate

    s, _, equipment, original = hex_setup(cards)
    put(s, 'Leonin Shikari', 'battlefield', 'p2')
    new = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    to_phase(s, 'upkeep', turn=7)
    activate(s, equipment, 'Equip {', targets=[new.id], pid='p2', resolve=False)
    settle(s)
    assert original.zone == 'p2:battlefield'
    assert new.zone == 'p2:graveyard'
    roundtrip(s)


def test_hex_departed_aura_keeps_original_equipment_host(cards):
    s, aura, _, creature = hex_setup(cards)
    to_phase(s, 'upkeep', turn=7)
    act(s, 'p1', type='move', card_ids=[aura.id], to={'player':'p1','zone':'graveyard'})
    settle(s)
    assert creature.zone == 'p2:graveyard'
    roundtrip(s)


def test_hex_blinked_equipment_successor_is_not_original_host(cards):
    s, _, equipment, creature = hex_setup(cards)
    to_phase(s, 'upkeep', turn=7)
    act(s, 'p2', type='move', card_ids=[equipment.id], to={'player':'p2','zone':'exile'})
    act(s, 'p2', type='move', card_ids=[equipment.id], to={'player':'p2','zone':'battlefield'})
    act(s, 'p2', type='attach', card_ids=[equipment.id], to=creature.id)
    settle(s)
    assert creature.zone == 'p2:battlefield'
    roundtrip(s)


def test_true_cold_hex_pending_trigger_tracks_original_equipment(cards, tmp_path):
    s, aura, _, creature = hex_setup(cards)
    to_phase(s, 'upkeep', turn=7)
    act(s, 'p1', type='move', card_ids=[aura.id], to={'player':'p1','zone':'graveyard'})
    saved = tmp_path / 'hex.json'
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
assert s.state.cards[sys.argv[3]].zone=='p2:graveyard'
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), creature.id], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
