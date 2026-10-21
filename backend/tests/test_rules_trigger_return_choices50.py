"""Non-target choices use current controlled permanents and their real owners."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_return_choices50_cards.json').read_text())


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
    names = [c['name'] for c in DATA] + ['Forest', 'Island', 'Swamp', 'Grizzly Bears', 'Sol Ring']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s


def cast(s, name):
    source = put(s, name, 'hand')
    mana(s, C=5, G=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    return source


@pytest.mark.parametrize('name', ['Kazandu Stomper', 'Nulltread Gargantuan'])
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('count', [0, 1, 2])
def test_stomper_choice_is_up_to_two_owned_lands(cards, count):
    s = setup(cards)
    lands = [put(s, n, 'battlefield') for n in ('Forest', 'Island', 'Swamp')]
    foreign = put(s, 'Forest', 'battlefield', 'p2')
    creature = put(s, 'Grizzly Bears', 'battlefield')
    source = cast(s, 'Kazandu Stomper')
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.min_choices == 0 and d.max_choices == 2
    assert {o.id for o in d.options} == {c.id for c in lands}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[c.id for c in lands[:count]])
    settle(s)
    assert all(c.zone == ('p1:hand' if i < count else 'p1:battlefield') for i, c in enumerate(lands))
    assert foreign.zone == 'p2:battlefield' and creature.zone == 'p1:battlefield' and source.zone == 'p1:battlefield'
    roundtrip(s)


def test_stomper_foreign_owned_land_returns_to_owner(cards):
    s = setup(cards)
    land = put(s, 'Forest', 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[land.id], player='p1')
    cast(s, 'Kazandu Stomper')
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[land.id])
    settle(s)
    assert land.zone == 'p2:hand'


def test_stomper_no_lands_does_not_strand_prompt(cards):
    s = setup(cards)
    source = cast(s, 'Kazandu Stomper')
    assert s.state.rules.decision is None and source.zone == 'p1:battlefield'


@pytest.mark.parametrize('invalid', ['foreign', 'three'])
def test_stomper_illegal_choice_rejected_atomically(cards, invalid):
    s = setup(cards)
    lands = [put(s, n, 'battlefield') for n in ('Forest', 'Island', 'Swamp')]
    foreign = put(s, 'Forest', 'battlefield', 'p2')
    cast(s, 'Kazandu Stomper')
    d = s.state.rules.decision
    assert d is not None
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id,
            option_ids=[foreign.id] if invalid == 'foreign' else [c.id for c in lands])
    assert s.state.model_dump_json() == before


def test_gargantuan_only_itself_is_mandatory(cards):
    s = setup(cards)
    source = cast(s, 'Nulltread Gargantuan')
    assert source.zone == 'p1:library' and s.state.zones['p1:library'][0] == source.id
    assert s.state.rules.decision is None
    roundtrip(s)


def test_gargantuan_chooses_controlled_not_targeted_creature(cards):
    s = setup(cards)
    creature = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    foreign = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    act(s, 'p1', type='set_controller', card_ids=[creature.id], player='p1')
    source = cast(s, 'Nulltread Gargantuan')
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {creature.id, source.id}
    assert foreign.id not in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[creature.id])
    settle(s)
    assert creature.zone == 'p2:library' and s.state.zones['p2:library'][0] == creature.id
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name,chosen,destination', [
    ('Kazandu Stomper', 'Forest', 'p2:hand'),
    ('Nulltread Gargantuan', 'Grizzly Bears', 'p2:library'),
])
def test_resolution_choice_survives_cold_departed_source(cards, tmp_path, name, chosen, destination):
    import os
    import subprocess
    import sys

    import app

    s = setup(cards)
    permanent = put(s, chosen, 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[permanent.id], player='p1')
    source = cast(s, name)
    assert s.state.rules.decision is not None
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    saved = tmp_path / 'return-choice.json'
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
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d is not None and d.player=='p1'
act(s,'p1',type='choose',decision_id=d.id,option_ids=[sys.argv[3]])
settle(s)
assert s.state.cards[sys.argv[3]].zone==sys.argv[4]
if sys.argv[4].endswith(':library'):assert s.state.zones[sys.argv[4]][0]==sys.argv[3]
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), permanent.id, destination],
        cwd=Path(app.__file__).resolve().parents[1],
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
