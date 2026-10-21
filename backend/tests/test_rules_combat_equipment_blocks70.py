"""Conditional declaration requirements preserve origin, legality and native optimization."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/combat_equipment_blocks70_cards.json').read_text())
NAMES = ["Kemba's Legion", "Bonesplitter", "Vulshok Morningstar"]


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
    s = table(cards, [c['name'] for c in DATA] + ['Grizzly Bears', 'Sol Ring'], ['Grizzly Bears'] * 5, ['Grizzly Bears'])
    army = [c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p2']
    assert len(army) == 5
    for c in army:
        act(s, 'p2', type='move', card_ids=[c.id], to={'player': 'p2', 'zone': 'battlefield'})
    other = put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    return s, army, other


def choose(s, value):
    d = s.state.rules.decision
    assert d is not None and value in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[value])
    settle(s)


def cast(s, name, targets=(), *, pid='p1', direction=None):
    source = put(s, name, 'hand', pid)
    mana(s, pid=pid, C=8, W=4, U=4, R=4, G=4, B=4)
    wait_priority(s, pid)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[])
    settle(s)
    if direction is not None:
        choose(s, direction)
        assert source.choices.get('Chosen direction') == direction
    return source


def equip(s, gear, host):
    mana(s, C=8)
    wait_priority(s, 'p1')
    ability = next(a.index for a in Plan(s.state, 'p1', s.cards, None).ch(gear).abilities if 'equip' in a.keywords)
    act(s, 'p1', type='activate_ability', card_id=gear.id, ability=ability, targets=[host.id], sources=[])
    settle(s)
    assert gear.attached_to == host.id


def prepared(cards, equipment=0):
    s, army, other = setup(cards)
    host = cast(s, NAMES[0])
    gears = []
    for name in NAMES[1:equipment + 1]:
        gear = cast(s, name)
        equip(s, gear, host)
        gears.append(gear)
    return s, host, gears, army, other


def attackers(s, army, *, turn=5, count=5):
    to_phase(s, 'declare_attackers', turn=turn)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p1'} for c in army[:count]])
    to_phase(s, 'declare_blockers', turn=turn)


def block(s, host, army):
    act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': host.id, 'attacker_id': c.id} for c in army])


def blocked_ids(s, host):
    from app.rules import combat

    return {c.id for c in combat.blocked_by(s.state, host)}


def refuse_blocks(s, host, army):
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        block(s, host, army)
    assert s.state.model_dump_json() == before


def copy_as(s, target):
    copied = cast(s, 'Phyrexian Metamorph')
    choose(s, target.id)
    return copied


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAMES[0])).level == 'FULL'


@pytest.mark.parametrize('equipment', [0, 1, 2])
def test_actual_equipment_count_controls_native_multiple_blocks(cards, equipment):
    s, host, _, army, _ = prepared(cards, equipment)
    attackers(s, army)
    refuse_blocks(s, host, army[:equipment + 2])
    block(s, host, army[:equipment + 1])
    assert len(blocked_ids(s, host)) == equipment + 1
    roundtrip(s)


def test_paid_vigilance_attack_leaves_host_untapped_for_equipped_blocks(cards):
    s, host, _, army, _ = prepared(cards, 2)
    to_phase(s, 'declare_attackers', turn=7)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': host.id, 'target': 'p2'}])
    assert not host.tapped
    attackers(s, army, turn=8, count=3)
    block(s, host, army[:3])
    assert len(blocked_ids(s, host)) == 3
    roundtrip(s)


def test_equipment_adds_to_independent_fixed_block_permission(cards):
    s, host, _, army, _ = prepared(cards, 2)
    cast(s, 'Brave the Sands')
    attackers(s, army)
    refuse_blocks(s, host, army[:5])
    block(s, host, army[:4])
    assert len(blocked_ids(s, host)) == 4
    roundtrip(s)


def test_equipment_attached_to_other_creature_does_not_count(cards):
    s, host, gears, army, other = prepared(cards, 1)
    equip(s, gears[0], other)
    attackers(s, army)
    refuse_blocks(s, host, army[:2])
    block(s, host, army[:1])
    roundtrip(s)


def test_other_controller_equipment_stays_attached_and_counts(cards):
    s, host, gears, army, _ = prepared(cards, 1)
    act(s, 'p1', type='set_controller', card_ids=[gears[0].id], player='p3')
    assert gears[0].attached_to == host.id
    attackers(s, army)
    block(s, host, army[:2])
    roundtrip(s)


@pytest.mark.parametrize('blink', [False, True])
def test_native_copy_current_equipment_type_and_changed_object_identity(cards, blink):
    s, host, gears, army, _ = prepared(cards, 1)
    copied = copy_as(s, gears[0])
    equip(s, copied, host)
    assert 'Equipment' in Plan(s.state, 'p1', s.cards, None).ch(copied).subtypes
    oid = s.state.rules.object_id(copied.id)
    if blink:
        cast(s, 'Flicker', targets=[copied.id])
        choose(s, gears[0].id)
        assert s.state.rules.object_id(copied.id) != oid and copied.attached_to is None
    attackers(s, army)
    count = 2 if blink else 3
    refuse_blocks(s, host, army[:count + 1])
    block(s, host, army[:count])
    roundtrip(s)


def test_copied_kemba_counts_its_own_attachments_not_originals(cards):
    s, host, gears, army, _ = prepared(cards, 1)
    copied = copy_as(s, host)
    equip(s, gears[0], copied)
    attackers(s, army)
    refuse_blocks(s, host, army[:2])
    block(s, copied, army[:2])
    assert len(blocked_ids(s, copied)) == 2 and not blocked_ids(s, host)
    roundtrip(s)


def test_equipment_removed_after_legal_declaration_does_not_undo_blocks(cards):
    s, host, gears, army, _ = prepared(cards, 2)
    attackers(s, army, count=3)
    block(s, host, army[:3])
    cast(s, 'Disenchant', targets=[gears[0].id])
    assert gears[0].zone == 'p1:graveyard'
    assert blocked_ids(s, host) == {c.id for c in army[:3]}
    roundtrip(s)


def test_copied_host_pending_blocks_genuine_cold_reload(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, host, gears, army, _ = prepared(cards, 2)
    copied = copy_as(s, host)
    for gear in gears:
        equip(s, gear, copied)
    attackers(s, army, count=3)
    saved = tmp_path / 'equipment70.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_combat_equipment_blocks70 import block, blocked_ids
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
host=s.state.cards[sys.argv[3]]
army=[s.state.cards[x] for x in sys.argv[4:]]
block(s,host,army)
assert blocked_ids(s, host)=={c.id for c in army}
roundtrip(s)
"""
    backend = Path(app.__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), copied.id, *[c.id for c in army[:3]]],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=180, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
