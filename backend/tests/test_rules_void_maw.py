"""Canonical Void Maw links death replacements to an exact reusable exile cost."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold


@pytest.fixture()
def cards(settings):
    data = json.loads((Path(__file__).parent / 'fixtures/void_maw_cards.json').read_text())
    extra = [card(c['name'], set_code='vma', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')}) for i, c in enumerate(data)]
    settings.ensure_dirs()
    build_database([*fixture_cards(), *extra], settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = ['Void Maw', 'Grizzly Bears', 'Lightning Bolt', 'Forest']
    s = three(cards, names, names, names)
    hold(s)
    source = put(s, 'Void Maw', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    spell(s, 'Lightning Bolt', {'R': 1}, [bear.id])
    assert s.state.cards[bear.id].zone == 'p2:exile'
    return s, source, bear


def pay(s, source, selected):
    from tests.test_rules_wave7b_activation import ability_index
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Put a card'),
        cost_choices=[{'component': 0, 'cards': [selected.id]}])
    settle(s)


def test_void_maw_canonical_linked_cost_pumps_and_uses_owner_graveyard(cards):
    assert coverage.of_card_data(cards.resolve('Void Maw')).level == 'FULL'
    s, source, bear = setup(cards)
    assert Plan(s.state, 'p1', cards, None).ch(source).pt == (4, 5)
    pay(s, source, bear)
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    assert Plan(s.state, 'p1', cards, None).ch(source).pt == (6, 7)
    roundtrip(s)
    from tests.test_rules_wave30m_durations import stops, to_phase
    stops(s, 'main1')
    to_phase(s, 'main1', turn=2)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).pt == (4, 5)
    roundtrip(s)


def test_void_maw_rejects_unlinked_exile_and_returned_incarnation(cards):
    s, source, bear = setup(cards)
    other = put(s, 'Forest', 'exile', 'p2')
    with pytest.raises(ActionError):
        pay(s, source, other)
    act(s, 'p2', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'graveyard'})
    act(s, 'p2', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'exile'})
    with pytest.raises(ActionError):
        pay(s, source, bear)
    assert Plan(s.state, 'p1', cards, None).ch(source).pt == (4, 5)
    roundtrip(s)


def test_void_maw_new_source_incarnation_cannot_spend_old_link(cards):
    s, source, bear = setup(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    with pytest.raises(ActionError):
        pay(s, source, bear)
    assert s.state.cards[bear.id].zone == 'p2:exile'
    roundtrip(s)


def test_void_maw_linked_exile_cost_survives_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s, source, bear = setup(cards)
    priority(s, 'p1')
    path = tmp_path / 'maw.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
path, database, source, selected = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
ab = next(a for a in Plan(s.state, 'p1', repo, None).ch(s.state.cards[source]).abilities if a.kind == 'activated')
s.perform('p1', {'type': 'activate_ability', 'card_id': source, 'ability': ab.index,
                 'cost_choices': [{'component': 0, 'cards': [selected]}]})
for _ in range(20):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert s.state.cards[selected].zone == 'p2:graveyard'
assert Plan(s.state, 'p1', repo, None).ch(s.state.cards[source]).pt == (6, 7)
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), source.id, bear.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
