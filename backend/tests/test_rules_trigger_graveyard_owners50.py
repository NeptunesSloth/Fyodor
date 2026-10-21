"""Graveyard destination owners remain separate from former controllers."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_graveyard_owners50_cards.json').read_text())


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


def test_liability_charges_owner_of_stolen_permanent(cards):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Murder']
    s = table(cards, names, names, names)
    start(s)
    source = put(s, 'Liability', 'hand')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    creature = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[creature.id], player='p3')
    spell = put(s, 'Murder', 'hand')
    mana(s, C=1, B=2)
    before = {p: s.state.players[p].life for p in ('p1', 'p2', 'p3')}
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[], targets=[creature.id])
    settle(s)
    assert creature.zone == 'p2:graveyard'
    assert s.state.players['p2'].life == before['p2'] - 1
    assert s.state.players['p3'].life == before['p3']
    roundtrip(s)


NAMES = ['Mortuary', 'Patron of the Nezumi', 'Liability', 'Planar Void', 'Measure of Wickedness']


@pytest.mark.parametrize('name', NAMES)
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, name):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Murder', 'Wrath of God', 'Sol Ring']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, name, 'hand')
    mana(s, C=7, B=7)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    return s, source


def cast(s, name, targets=()):
    spell = put(s, name, 'hand')
    mana(s, C=7, B=3, U=1, W=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[], targets=list(targets))
    return spell


@pytest.mark.parametrize('owner,controller,returns', [('p1', 'p2', True), ('p2', 'p1', False)])
def test_mortuary_uses_destination_owner_not_former_controller(cards, owner, controller, returns):
    s, _ = setup(cards, 'Mortuary')
    creature = put(s, 'Grizzly Bears', 'battlefield', owner)
    act(s, 'p1', type='set_controller', card_ids=[creature.id], player=controller)
    cast(s, 'Murder', [creature.id])
    settle(s)
    assert creature.zone == owner + (':library' if returns else ':graveyard')
    if returns:
        assert s.state.zones[owner + ':library'][0] == creature.id
    roundtrip(s)


@pytest.mark.parametrize('owner,controller,loss', [('p2', 'p1', 1), ('p1', 'p2', 0)])
def test_patron_uses_opponent_graveyard_owner(cards, owner, controller, loss):
    s, _ = setup(cards, 'Patron of the Nezumi')
    creature = put(s, 'Grizzly Bears', 'battlefield', owner)
    act(s, 'p1', type='set_controller', card_ids=[creature.id], player=controller)
    before = {p: s.state.players[p].life for p in ('p1', 'p2', 'p3')}
    cast(s, 'Murder', [creature.id])
    settle(s)
    assert s.state.players[owner].life == before[owner] - loss
    assert all(s.state.players[p].life == before[p] for p in before if p != owner)
    roundtrip(s)


def test_patron_dying_with_opponents_creatures_still_triggers(cards):
    s, source = setup(cards, 'Patron of the Nezumi')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Typhoid Rats', 'battlefield', 'p2')
    life = s.state.players['p2'].life
    cast(s, 'Wrath of God')
    settle(s)
    assert source.zone == 'p1:graveyard' and s.state.players['p2'].life == life - 2


def test_patron_native_rat_offering_casts_over_a_pending_spell(cards):
    names = [c['name'] for c in DATA] + ['Murder']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    rat = put(s, 'Typhoid Rats', 'battlefield')
    spell = put(s, 'Murder', 'hand')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[], targets=[rat.id])
    patron = put(s, 'Patron of the Nezumi', 'hand')
    mana(s, C=5, B=1)
    act(s, 'p1', type='cast_spell', card_id=patron.id, sources=[], optional_costs=[patron.id + ':offering'])
    settle(s)
    assert patron.zone == 'p1:battlefield' and rat.zone == 'p1:graveyard' and spell.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name,loss', [('Liability', 0), ('Patron of the Nezumi', 1)])
def test_tokens_are_excluded_only_when_the_text_says_nontoken(cards, name, loss):
    s, _ = setup(cards, name)
    act(s, 'p1', type='create_token', player='p2',
        token={'name': 'Soldier', 'type_line': 'Token Creature — Soldier', 'power': '1', 'toughness': '1'})
    life = s.state.players['p2'].life
    cast(s, 'Wrath of God')
    settle(s)
    assert s.state.players['p2'].life == life - loss
    roundtrip(s)


def test_void_mill_and_spell_graveyard_entry_are_independent_triggers(cards):
    s, _ = setup(cards, 'Planar Void')
    top = list(s.state.zones['p2:library'])[:5]
    spell = cast(s, 'Tome Scour', ['p2'])
    settle(s)
    assert all(s.state.cards[c].zone == 'p2:exile' for c in top)
    assert spell.zone == 'p1:exile'
    roundtrip(s)


def test_void_does_not_look_back_when_it_dies_simultaneously(cards):
    s, source = setup(cards, 'Planar Void')
    creature = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    spell = cast(s, 'Planar Cleansing')
    settle(s)
    assert source.zone == 'p1:graveyard' and creature.zone == 'p2:graveyard' and spell.zone == 'p1:graveyard'
    roundtrip(s)


def test_measure_destination_graveyard_selects_opponent_at_trigger_time(cards):
    s, source = setup(cards, 'Measure of Wickedness')
    creature = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, 'Murder', [creature.id])
    settle(s)
    # The creature and then the resolving Murder each entered our graveyard while we controlled Measure.
    seen = 0
    while (d := s.state.rules.decision) is not None:
        assert d.player == 'p1' and d.resume['step'] == 'trigger_target'
        assert 'p1' not in {o.id for o in d.options}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
        seen += 1
        settle(s)
    assert seen == 2 and source.controller == 'p2'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Mortuary', 'Planar Void'])
def test_pending_graveyard_object_is_not_a_new_incarnation(cards, name):
    s, _ = setup(cards, name)
    creature = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, 'Murder', [creature.id])
    for _ in range(30):
        if creature.zone == 'p1:graveyard':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert creature.zone == 'p1:graveyard'
    act(s, 'p1', type='move', card_ids=[creature.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[creature.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert creature.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_native_pending_zone_trigger_survives_cold_source_change(cards, tmp_path, name):
    import os
    import subprocess
    import sys

    import app

    s, source = setup(cards, name)
    if name == 'Measure of Wickedness':
        from tests.test_rules_wave30m_durations import stops, to_phase

        stops(s, 'end')
        to_phase(s, 'end', turn=s.state.turn.number)
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
        selected, expected, pid = source.id, 'p2:battlefield', 'p1'
        # Sacrifice requires control as the already-triggered ability resolves.
        delta = 8
    else:
        owner = 'p1' if name == 'Mortuary' else 'p2'
        creature = put(s, 'Grizzly Bears', 'battlefield', owner)
        act(s, 'p1', type='set_controller', card_ids=[creature.id], player='p3')
        cast(s, 'Murder', [creature.id])
        for _ in range(30):
            if creature.zone == owner + ':graveyard':
                break
            assert s.state.rules.decision is None
            act(s, s.state.rules.priority, type='pass_priority')
        assert creature.zone == owner + ':graveyard'
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
        selected = creature.id
        expected = owner + (':library' if name == 'Mortuary' else ':exile' if name == 'Planar Void' else ':graveyard')
        pid, delta = owner, 1 if name in ('Liability', 'Patron of the Nezumi') else 0
    before = s.state.players[pid].life
    saved = tmp_path / 'graveyard-owner.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
assert s.state.cards[sys.argv[3]].zone==sys.argv[4]
assert s.state.players[sys.argv[5]].life==int(sys.argv[6])-int(sys.argv[7])
if sys.argv[4].endswith(':library'):assert s.state.zones[sys.argv[4]][0]==sys.argv[3]
if sys.argv[8]=='Measure of Wickedness':assert s.state.cards[sys.argv[3]].controller=='p2'
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), selected, expected, pid,
         str(before), str(delta), name],
        cwd=Path(app.__file__).resolve().parents[1],
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
