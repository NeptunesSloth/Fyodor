"""Canonical validation of collateral promotions from private one-card bottom placement."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_player_protection import answer
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/bottom_putback_collateral_cards.json'
NAMES = ['Amass the Components', 'Errand-Rider of Gondor']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='bpc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = three(cards, [*NAMES, 'Grizzly Bears'], [*NAMES, 'Grizzly Bears'], ['Grizzly Bears'])
    hold(s)
    return s


@pytest.mark.parametrize('name', NAMES)
def test_actual_canonical_collateral_is_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def cast_until_bottom(s, name):
    card = put(s, name, 'hand')
    hand_before = len(s.state.zones['p1:hand'])
    library_before = list(s.state.zones['p1:library'])
    mana, n = ({'U': 1, 'C': 3}, 3) if name == 'Amass the Components' else ({'W': 1, 'C': 2}, 1)
    source = spell(s, name, mana)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'put_back' and d.resume['place'] == 'bottom'
    assert d.player == 'p1' and d.min_choices == d.max_choices == 1
    assert len(s.state.zones['p1:hand']) == hand_before - 1 + n
    assert s.state.zones['p1:library'] == library_before[n:]
    assert not s.view('p2')['rules']['decision'].get('options')
    assert 'resume' not in s.view('p2')['rules']['decision']
    assert card.id == source.id
    return source, hand_before, library_before, n


@pytest.mark.parametrize('name', NAMES)
def test_real_spell_and_etb_draw_then_private_bottom_putback(cards, name):
    s = setup(cards)
    source, hand_before, library_before, n = cast_until_bottom(s, name)
    d = s.state.rules.decision
    chosen = d.options[-1].id
    answer(s, [chosen])
    assert s.state.zones['p1:library'] == [*library_before[n:], chosen]
    assert len(s.state.zones['p1:hand']) == hand_before - 2 + n
    assert s.state.cards[source.id].zone == ('p1:graveyard' if name == NAMES[0] else 'p1:battlefield')
    roundtrip(s)


def test_errand_rider_legendary_creature_skips_only_putback(cards):
    s = setup(cards)
    put(s, 'Krenko, Mob Boss', 'battlefield')
    source = put(s, 'Errand-Rider of Gondor', 'hand')
    before = len(s.state.zones['p1:hand'])
    library = len(s.state.zones['p1:library'])
    spell(s, 'Errand-Rider of Gondor', {'W': 1, 'C': 2})
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert len(s.state.zones['p1:hand']) == before
    assert len(s.state.zones['p1:library']) == library - 1
    roundtrip(s)


def test_opponents_legendary_creature_does_not_skip_errand_rider_putback(cards):
    s = setup(cards)
    put(s, "Atraxa, Praetors' Voice", 'battlefield', 'p2')
    cast_until_bottom(s, 'Errand-Rider of Gondor')
    answer(s, [s.state.rules.decision.options[0].id])
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_each_collateral_private_choice_resumes_in_fresh_process(cards, tmp_path, name):
    import subprocess
    import sys

    s = setup(cards)
    _, hand_before, _, n = cast_until_bottom(s, name)
    d = s.state.rules.decision
    selected = d.options[0].id
    path = tmp_path / 'bottom-collateral.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, selected, expected_hand = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
d = s.state.rules.decision
assert d.resume['place'] == 'bottom'
assert not s.view('p2')['rules']['decision'].get('options')
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [selected]})
for _ in range(12):
    if not s.state.zones['stack']:
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('draw and bottom placement did not finish')
assert s.state.zones['p1:library'][-1] == selected
assert len(s.state.zones['p1:hand']) == int(expected_hand)
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), selected, str(hand_before - 2 + n)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_plain_saved_game_can_project_private_views_before_first_fresh_process_action(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    path = tmp_path / 'plain-saved-game.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
before = s.state.model_dump_json()
first, other = s.view('p1'), s.view('p2')
assert first['rules'] is not None and other['rules'] is not None
for cid in s.state.zones['p1:hand']:
    assert first['cards'][cid].get('name') == s.state.cards[cid].name
    assert not other['cards'].get(cid, {}).get('name')
assert s.state.model_dump_json() == before
assert s.history.rebuild() == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
