"""Canonical optional revealed-card entry and exact hand fallback."""
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
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold


@pytest.fixture()
def cards(settings):
    data = json.loads((Path(__file__).parent / 'fixtures/look_optional_placement_cards.json').read_text())
    extra = [card(c['name'], set_code='vma', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')}) for i, c in enumerate(data)]
    settings.ensure_dirs()
    build_database([*fixture_cards(), *extra], settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def setup(cards):
    names = ['Whiskervale Forerunner', 'Break Out', 'Grizzly Bears', 'Giant Growth', 'Lightning Bolt', "Grafdigger's Cage", 'Twincast']
    s = three(cards, names, names, names)
    hold(s)
    return s


def top(s, name):
    c = put(s, name, 'library')
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    return c


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


@pytest.mark.parametrize('name', ['Break Out', 'Whiskervale Forerunner'])
def test_optional_placements_canonical_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


@pytest.mark.parametrize('edge', ['battlefield', 'hand', 'large', 'decline'])
def test_break_out_private_selection_then_actual_haste_or_hand(cards, edge):
    from app.rules.plan import Plan
    s = setup(cards)
    selected = top(s, 'Whiskervale Forerunner' if edge == 'large' else 'Grizzly Bears')
    spell(s, 'Break Out', {'R': 1, 'G': 1})
    d = s.state.rules.decision
    assert d is not None and any(o.id == selected.id for o in d.options)
    # The looked-at identities and options remain private until a card is selected.
    assert selected.id not in str(s.view('p2').get('rules', {}).get('decision', {}))
    choose(s, [] if edge == 'decline' else [selected.id])
    if edge in ('battlefield', 'hand'):
        choose(s, [selected.id] if edge == 'battlefield' else [])
    if edge == 'battlefield':
        assert s.state.cards[selected.id].zone == 'p1:battlefield'
        assert 'haste' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[selected.id]).keywords
    elif edge != 'decline':
        assert s.state.cards[selected.id].zone == 'p1:hand'
    else:
        assert s.state.cards[selected.id].zone == 'p1:library'
    roundtrip(s)


@pytest.mark.parametrize('own_turn', [True, False])
def test_whiskervale_first_own_targeting_only_and_own_turn_entry(cards, own_turn):
    from tests.test_rules_wave30m_durations import stops, to_phase
    s = setup(cards)
    source = put(s, 'Whiskervale Forerunner', 'battlefield')
    if not own_turn:
        stops(s, 'main1')
        to_phase(s, 'main1', turn=2)
    selected = top(s, 'Grizzly Bears')
    spell(s, 'Giant Growth', {'G': 1}, [source.id])
    choose(s, [selected.id])
    if own_turn:
        choose(s, [selected.id])
    assert s.state.cards[selected.id].zone == ('p1:battlefield' if own_turn else 'p1:hand')
    spell(s, 'Giant Growth', {'G': 1}, [source.id])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_break_out_failed_entry_stays_original_library_object_then_goes_to_hand(cards):
    s = setup(cards)
    put(s, "Grafdigger's Cage", 'battlefield', 'p2')
    selected = top(s, 'Grizzly Bears')
    spell(s, 'Break Out', {'R': 1, 'G': 1})
    choose(s, [selected.id])
    choose(s, [selected.id])
    assert s.state.cards[selected.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('edge', ['source_blinked', 'opponent_spell', 'copy'])
def test_whiskervale_pending_trigger_and_actual_controlled_target_provenance(cards, edge):
    s = setup(cards)
    source = put(s, 'Whiskervale Forerunner', 'battlefield')
    selected = top(s, 'Grizzly Bears')
    if edge == 'opponent_spell':
        spell(s, 'Lightning Bolt', {'R': 1}, [source.id], player='p2')
        assert s.state.rules.decision is None
    if edge == 'copy':
        other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
        growth = put(s, 'Giant Growth', 'hand', 'p2')
        priority(s, 'p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'G': 1})
        act(s, 'p2', type='cast_spell', card_id=growth.id, targets=[other.id])
        priority(s, 'p1')
        twin = put(s, 'Twincast', 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'U': 2})
        act(s, 'p1', type='cast_spell', card_id=twin.id, targets=[growth.id])
        for _ in range(12):
            if s.state.rules.decision is not None:
                break
            act(s, s.state.rules.priority, type='pass_priority')
        choose(s, [source.id])
    else:
        spell(s, 'Giant Growth', {'G': 1}, [source.id])
    assert s.state.rules.decision is not None
    if edge == 'source_blinked':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    choose(s, [selected.id])
    choose(s, [selected.id])
    assert s.state.cards[selected.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['breakout', 'valiant'])
def test_optional_placement_queued_native_entry_resumes_in_fresh_process(cards, tmp_path, mode):
    import subprocess
    import sys

    s = setup(cards)
    source = put(s, 'Whiskervale Forerunner', 'battlefield') if mode == 'valiant' else None
    selected = top(s, 'Grizzly Bears')
    if source is not None:
        spell(s, 'Giant Growth', {'G': 1}, [source.id])
    else:
        spell(s, 'Break Out', {'R': 1, 'G': 1})
    choose(s, [selected.id])
    assert s.state.rules.decision is not None
    path = tmp_path / (mode + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
path, database, selected, mode = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [selected]})
for _ in range(50):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert s.state.cards[selected].zone == 'p1:battlefield'
assert ('haste' in Plan(s.state, 'p1', repo, None).ch(s.state.cards[selected]).keywords) == (mode == 'breakout')
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), selected.id, mode],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
