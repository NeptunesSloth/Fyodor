"""Canonical name/number guesses with native public choices and exact reveals."""
from __future__ import annotations

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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/resolved_library_guesses_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='rlg', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Tunnel Vision', 'Mindblaze', 'Scrying Glass'])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def cast(s, name):
    c = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5, 'U': 1, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=['p2'])
    settle(s)


def typed(s, value):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, name=value)
    settle(s)


@pytest.mark.parametrize('found', [True, False])
def test_tunnel_found_graveyard_or_failure_shuffle(cards, found):
    s = table(cards, ['Tunnel Vision'], ['Grizzly Bears', 'Sol Ring'])
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    ring = put(s, 'Sol Ring', 'library', 'p2')
    before = len(s.state.zones['p2:graveyard'])
    cast(s, 'Tunnel Vision')
    typed(s, 'Grizzly Bears' if found else 'Tunnel Vision')
    assert s.state.rules.decision is None
    assert len(s.state.zones['p2:graveyard']) == before + (1 if found else 0)
    if found:
        assert s.state.zones['p2:library'][0] == bear.id
        assert s.state.cards[ring.id].zone == 'p2:graveyard'
        assert not s.state.cards[bear.id].revealed_to
    roundtrip(s)


@pytest.mark.parametrize('guess', ['1', '2', '41'])
def test_mindblaze_exact_positive_count(cards, guess):
    s = table(cards, ['Mindblaze'], ['Grizzly Bears'])
    put(s, 'Grizzly Bears', 'library', 'p2')
    cast(s, 'Mindblaze')
    typed(s, 'Grizzly Bears')
    d = s.state.rules.decision
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, name='0')
    assert s.state.model_dump_json() == before
    typed(s, guess)
    assert s.state.players['p2'].life == (32 if guess == '1' else 40)
    assert all(not c.revealed_to for c in s.state.cards.values() if c.zone == 'p2:library')
    roundtrip(s)


@pytest.mark.parametrize('guess', ['1', '41'])
def test_glass_exact_color_and_cleanup(cards, guess):
    s = table(cards, ['Scrying Glass'], ['Grizzly Bears'])
    source = put(s, 'Scrying Glass', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'hand', 'p2')
    count = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=['p2'])
    settle(s)
    typed(s, guess)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['Green'])
    settle(s)
    assert len(s.state.zones['p1:hand']) == count + (guess == '1')
    assert not s.state.cards[bear.id].revealed_to
    roundtrip(s)


@pytest.mark.parametrize('name,answers', [('Tunnel Vision', ['Grizzly Bears']), ('Mindblaze', ['Grizzly Bears', '1']),
                                         ('Scrying Glass', ['1', 'Green'])])
def test_cold_public_guesses_resume_without_warm_registration(cards, tmp_path, name, answers):
    import subprocess
    import sys

    s = table(cards, [name], ['Grizzly Bears'])
    put(s, 'Grizzly Bears', 'hand' if name == 'Scrying Glass' else 'library', 'p2')
    if name == 'Scrying Glass':
        source = put(s, name, 'battlefield')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=['p2'])
        settle(s)
    else:
        cast(s, name)
    path = tmp_path / 'guess.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import json, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, name, answers = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
for answer in json.loads(answers):
    d = s.state.rules.decision
    assert d is not None
    data = {'type': 'choose', 'decision_id': d.id}
    if d.options[0].id in ('__number__', '__name__'):
        data['name'] = answer
    else:
        data['option_ids'] = [answer]
    s.perform(d.player, data)
for _ in range(30):
    assert s.state.rules.decision is None
    if not s.state.zones['stack']:
        break
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('resolution did not finish')
assert s.state.players['p2'].life == (32 if name == 'Mindblaze' else 40)
assert all(not c.revealed_to for c in s.state.cards.values() if c.zone.endswith((':hand', ':library')))
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), name, json.dumps(answers)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=90)
    assert result.returncode == 0, result.stderr


def test_mindblaze_rejects_land_name_atomically(cards):
    s = table(cards, ['Mindblaze'])
    cast(s, 'Mindblaze')
    d = s.state.rules.decision
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, name='Forest')
    assert s.state.model_dump_json() == before
    typed(s, 'Mindblaze')
    typed(s, '1')
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_tunnel_native_graveyard_replacement(cards):
    s = table(cards, ['Tunnel Vision', 'Rest in Peace'], ['Grizzly Bears', 'Sol Ring'])
    put(s, 'Rest in Peace', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    ring = put(s, 'Sol Ring', 'library', 'p2')
    cast(s, 'Tunnel Vision')
    typed(s, 'Grizzly Bears')
    assert s.state.zones['p2:library'][0] == bear.id
    assert s.state.cards[ring.id].zone == 'p2:exile'
    assert not s.state.cards[bear.id].revealed_to
    roundtrip(s)


def test_glass_replacement_draw_does_not_reveal_new_hand_card(cards):
    s = table(cards, ['Scrying Glass'], ['Grizzly Bears', 'Notion Thief'])
    put(s, 'Notion Thief', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'hand', 'p2')
    source = put(s, 'Scrying Glass', 'battlefield')
    original = len(s.state.zones['p1:hand'])
    theirs = len(s.state.zones['p2:hand'])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=['p2'])
    settle(s)
    typed(s, '1')
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['Green'])
    settle(s)
    assert len(s.state.zones['p1:hand']) == original
    assert len(s.state.zones['p2:hand']) == theirs + 1
    assert not s.state.cards[bear.id].revealed_to
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p2:hand'])
    roundtrip(s)
