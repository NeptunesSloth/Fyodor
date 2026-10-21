"""Actual named Equipment grants and named-land scaling from batch31 collateral."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_source_quality_protection import ch, spell
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/kaldra_wastes_collateral_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='kwc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())] + ['Forest']
    s = three(cards, names, names, names)
    hold(s)
    return s


@pytest.mark.parametrize('name', ['Shield of Kaldra', 'Walker of the Wastes'])
def test_actual_canonical_collateral_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_shield_actual_cast_grants_exact_three_names_globally_and_source_leaves(cards):
    s = setup(cards)
    sword = put(s, 'Sword of Kaldra', 'battlefield', 'p2')
    helm = put(s, 'Helm of Kaldra', 'battlefield', 'p3')
    other = put(s, 'Shadowspear', 'battlefield')
    shield = spell(s, 'Shield of Kaldra', {'C': 4})
    assert all('indestructible' in ch(s, c).keywords for c in (shield, sword, helm))
    assert 'indestructible' not in ch(s, other).keywords
    act(s, 'p1', type='set_controller', card_ids=[shield.id], player='p2')
    assert all('indestructible' in ch(s, c).keywords for c in (shield, sword, helm))
    act(s, 'p1', type='move', card_ids=[shield.id], to={'player': 'p1', 'zone': 'exile'})
    assert all('indestructible' not in ch(s, c).keywords for c in (sword, helm, other))
    roundtrip(s)


def test_shield_native_equip_protects_only_host_from_lethal_damage(cards):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    shield = spell(s, 'Shield of Kaldra', {'C': 4})
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    act(s, 'p1', type='activate_ability', card_id=shield.id, ability=ability_index(s, shield, 'Equip {4}'), targets=[host.id])
    settle(s)
    assert 'indestructible' in ch(s, host).keywords
    assert 'indestructible' not in ch(s, enemy).keywords
    spell(s, 'Lightning Bolt', {'R': 1}, [host.id], player='p2')
    assert s.state.cards[host.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_shield_ability_loss_removes_named_equipment_grant_in_layers(cards):
    s = setup(cards)
    shield = put(s, 'Shield of Kaldra', 'battlefield')
    sword = put(s, 'Sword of Kaldra', 'battlefield', 'p2')
    put(s, 'March of the Machines', 'battlefield')
    assert 'Creature' in ch(s, shield).types
    assert 'indestructible' in ch(s, sword).keywords
    spell(s, 'Turn to Frog', {'U': 1, 'C': 1}, [shield.id])
    assert 'indestructible' not in ch(s, sword).keywords
    roundtrip(s)


def test_walker_native_cast_counts_only_own_lands_named_wastes(cards):
    s = setup(cards)
    own = put(s, 'Wastes', 'battlefield')
    other = put(s, 'Wastes', 'battlefield', 'p2')
    put(s, 'Forest', 'battlefield')
    put(s, 'Darksteel Citadel', 'battlefield')
    walker = spell(s, 'Walker of the Wastes', {'C': 5})
    assert ch(s, walker).pt == (5, 5)
    assert 'Wastes' not in ch(s, own).subtypes
    act(s, 'p1', type='set_controller', card_ids=[other.id], player='p1')
    assert ch(s, walker).pt == (6, 6)
    act(s, 'p1', type='set_controller', card_ids=[own.id], player='p2')
    assert ch(s, walker).pt == (5, 5)
    act(s, 'p1', type='move', card_ids=[other.id], to={'player': 'p2', 'zone': 'graveyard'})
    assert ch(s, walker).pt == (4, 4)
    roundtrip(s)


def test_walker_uses_name_not_basic_land_type_and_loses_boost_with_ability(cards):
    s = setup(cards)
    waste = put(s, 'Wastes', 'battlefield')
    forest = put(s, 'Forest', 'battlefield')
    walker = put(s, 'Walker of the Wastes', 'battlefield')
    put(s, 'Urborg, Tomb of Yawgmoth', 'battlefield')
    assert 'Swamp' in ch(s, waste).subtypes and 'Swamp' in ch(s, forest).subtypes
    assert ch(s, walker).pt == (5, 5)
    spell(s, 'Turn to Frog', {'U': 1, 'C': 1}, [walker.id])
    assert ch(s, walker).pt == (1, 1)
    roundtrip(s)


def test_walker_counts_actual_vesuva_copy_name_not_original_printing(cards):
    from tests.test_rules_player_protection import answer

    s = setup(cards)
    waste = put(s, 'Wastes', 'battlefield')
    walker = put(s, 'Walker of the Wastes', 'battlefield')
    copy = put(s, 'Vesuva', 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='play_land', card_id=copy.id)
    assert s.state.rules.decision is not None
    answer(s, [waste.id])
    assert ch(s, copy).name == 'Wastes'
    assert ch(s, walker).pt == (6, 6)
    roundtrip(s)


def test_shield_actual_cast_resolves_and_derives_global_names_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    sword = put(s, 'Sword of Kaldra', 'battlefield', 'p2')
    shield = spell(s, 'Shield of Kaldra', {'C': 4}, finish=False)
    path = tmp_path / 'shield.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
path, database, shield, sword = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p2')
for _ in range(12):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('Shield did not resolve')
p = Plan(s.state, 'p1', repo, None)
assert all('indestructible' in p.ch(s.state.cards[c]).keywords for c in (shield, sword))
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), shield.id, sword.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_shield_does_not_grant_a_matching_named_card_without_equipment_type(cards):
    s = setup(cards)
    sword = put(s, 'Sword of Kaldra', 'battlefield', 'p2')
    spell(s, 'Song of the Dryads', {'G': 1, 'C': 2}, [sword.id])
    assert ch(s, sword).name == 'Sword of Kaldra' and 'Equipment' not in ch(s, sword).subtypes
    shield = spell(s, 'Shield of Kaldra', {'C': 4})
    assert 'indestructible' in ch(s, shield).keywords
    assert 'indestructible' not in ch(s, sword).keywords
    roundtrip(s)
