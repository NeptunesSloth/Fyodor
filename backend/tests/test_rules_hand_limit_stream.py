"""Native dynamic/timed hand limits and simultaneous hidden-zone exchange."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_keyed_player_bindings import maximum
from tests.test_rules_player_protection import answer
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import stops, three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/hand_limit_stream_cards.json'
NAMES = ['Midnight Oil', 'Winter, Misanthropic Guide', 'Inspired Idea', 'Enter the Infinite', 'Mordenkainen']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='hls', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())] + ['Inspired Idea']
    s = three(cards, names, names, names)
    hold(s)
    return s


def activate(s, c, needle):
    act(s, 'p1', type='activate_ability', card_id=c.id, ability=ability_index(s, c, needle))
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_midnight_oil_native_entry_and_counter_changes_set_current_maximum(cards):
    s = setup(cards)
    oil = spell(s, 'Midnight Oil', {'B': 2, 'C': 2})
    assert s.state.cards[oil.id].counters['hour'] == 7 and maximum(s) == 7
    for n in (1, 0, 5):
        act(s, 'p1', type='set_counter', card_id=oil.id, kind='hour', value=n)
        assert maximum(s) == n
    put(s, 'Reliquary Tower', 'battlefield')
    assert maximum(s) is None
    act(s, 'p1', type='set_counter', card_id=oil.id, kind='hour', value=2)
    assert maximum(s) is None  # Changing the value does not refresh the source timestamp.
    roundtrip(s)


@pytest.mark.parametrize('winter_last', [True, False])
def test_winter_new_delirium_keeps_original_source_timestamp(cards, winter_last):
    s = setup(cards)
    if winter_last:
        put(s, 'Reliquary Tower', 'battlefield', 'p2')
        source = put(s, 'Winter, Misanthropic Guide', 'battlefield')
    else:
        source = put(s, 'Winter, Misanthropic Guide', 'battlefield')
        put(s, 'Reliquary Tower', 'battlefield', 'p2')
    assert maximum(s, 'p2') is None
    for name in ['Lightning Bolt', 'Grizzly Bears', 'Cursed Rack', "Praetor's Counsel"]:
        put(s, name, 'graveyard')
    assert maximum(s, 'p2') == (3 if winter_last else None)
    put(s, 'Fervor', 'graveyard')
    assert maximum(s, 'p3') == 2
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    assert maximum(s, 'p3') == 7 and maximum(s, 'p2') is None
    roundtrip(s)


@pytest.mark.parametrize('cleave', [False, True])
def test_inspired_idea_real_normal_and_cleave_cast(cards, cleave):
    s = setup(cards)
    source = put(s, 'Inspired Idea', 'hand')
    before = len(s.state.zones['p1:hand']) - 1
    spell(s, 'Inspired Idea', {'U': 2, 'C': 3} if cleave else {'U': 1, 'C': 2}, **({'alt_cost': f'{source.id}:0'} if cleave else {}))
    assert len(s.state.zones['p1:hand']) == before + 3
    assert maximum(s) == (7 if cleave else 4)
    roundtrip(s)


def test_permanent_hand_delta_accumulates_and_later_setting_overwrites(cards):
    s = setup(cards)
    spell(s, 'Inspired Idea', {'U': 1, 'C': 2})
    spell(s, 'Inspired Idea', {'U': 1, 'C': 2})
    assert maximum(s) == 1
    put(s, 'Null Profusion', 'battlefield')
    assert maximum(s) == 2
    roundtrip(s)


def test_enter_infinite_draws_whole_library_then_private_putback_and_timed_limit(cards):
    s = setup(cards)
    source = spell(s, 'Enter the Infinite', {'U': 4, 'C': 8})
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.min_choices == 1
    assert not s.state.zones['p1:library']
    chosen = d.options[0].id
    answer(s, [chosen])
    assert s.state.zones['p1:library'] == [chosen]
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert maximum(s) is None
    to_phase(s, 'main1', turn=4)
    assert maximum(s) == 7
    roundtrip(s)


def test_mordenkainen_plus_draws_then_puts_chosen_card_on_bottom(cards):
    s = setup(cards)
    pw = spell(s, 'Mordenkainen', {'U': 2, 'C': 4})
    original_library = list(s.state.zones['p1:library'])
    before_hand = len(s.state.zones['p1:hand'])
    activate(s, pw, 'Draw two cards')
    d = s.state.rules.decision
    assert d is not None and len(s.state.zones['p1:hand']) == before_hand + 2
    selected = d.options[0].id
    answer(s, [selected])
    assert s.state.zones['p1:library'][-1] == selected
    assert s.state.zones['p1:library'][:-1] == original_library[2:]
    assert s.state.cards[pw.id].counters['loyalty'] == 7
    roundtrip(s)


def test_mordenkainen_ultimate_exchanges_whole_sets_without_draws_and_creates_emblem(cards):
    s = setup(cards)
    pw = spell(s, 'Mordenkainen', {'U': 2, 'C': 4})
    put(s, 'Grizzly Bears', 'hand')
    put(s, 'Lightning Bolt', 'hand')
    hand = Counter(s.state.cards[cid].card_id for cid in s.state.zones['p1:hand'])
    library = Counter(s.state.cards[cid].card_id for cid in s.state.zones['p1:library'])
    drawn = len(s.state.rules.turn_log.drawn.get('p1', []))
    act(s, 'p1', type='set_counter', card_id=pw.id, kind='loyalty', value=10)
    activate(s, pw, 'Exchange your hand')
    assert Counter(s.state.cards[cid].card_id for cid in s.state.zones['p1:hand']) == library
    assert Counter(s.state.cards[cid].card_id for cid in s.state.zones['p1:library']) == hand
    assert len(s.state.rules.turn_log.drawn.get('p1', [])) == drawn
    assert s.state.cards[pw.id].zone == 'p1:graveyard'
    assert maximum(s) is None
    assert any(c.token and c.token.type_line == 'Emblem' for c in s.state.cards.values())
    roundtrip(s)


def test_midnight_oil_cleanup_discards_trigger_life_loss_and_repeat_cleanup(cards):
    from tests.test_rules_wave10b_static_forms import hand_after_cleanup

    s = setup(cards)
    oil = spell(s, 'Midnight Oil', {'B': 2, 'C': 2})
    act(s, 'p1', type='set_counter', card_id=oil.id, kind='hour', value=1)
    assert hand_after_cleanup(s) == 1
    assert s.state.players['p1'].life == 32 and s.state.turn.number == 2
    roundtrip(s)


def test_midnight_oil_draw_step_keeps_drawing_after_hour_counters_run_out(cards):
    s = setup(cards)
    oil = spell(s, 'Midnight Oil', {'B': 2, 'C': 2})
    act(s, 'p1', type='set_counter', card_id=oil.id, kind='hour', value=1)
    stops(s, 'draw', 'main1')
    to_phase(s, 'draw', turn=4)
    settle(s)
    assert s.state.cards[oil.id].counters.get('hour', 0) == 0 and maximum(s) == 0
    assert len(s.state.rules.turn_log.drawn.get('p1', [])) == 2
    to_phase(s, 'draw', turn=7)
    settle(s)
    assert len(s.state.rules.turn_log.drawn.get('p1', [])) == 2
    roundtrip(s)


def test_temporary_no_maximum_expiry_restores_older_permanent_delta(cards):
    s = setup(cards)
    spell(s, 'Inspired Idea', {'U': 1, 'C': 2})
    spell(s, 'Enter the Infinite', {'U': 4, 'C': 8})
    d = s.state.rules.decision
    answer(s, [d.options[0].id])
    assert maximum(s) is None
    to_phase(s, 'main1', turn=4)
    assert maximum(s) == 4
    roundtrip(s)


def test_enter_infinite_library_above_table_draw_action_limit(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())]
    s = three(cards, names * 4, names, names)
    hold(s)
    spell(s, 'Enter the Infinite', {'U': 4, 'C': 8})
    assert len(s.state.zones['p1:hand']) > 100 and not s.state.zones['p1:library']
    d = s.state.rules.decision
    answer(s, [d.options[0].id])
    assert maximum(s) is None and 'p1' not in s.state.rules.lost
    roundtrip(s)


def test_enter_infinite_draw_prevention_does_not_skip_putback_or_hand_limit(cards):
    s = setup(cards)
    narset = put(s, 'Narset, Parter of Veils', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=narset.id, kind='loyalty', value=5)
    before = len(s.state.zones['p1:library'])
    spell(s, 'Enter the Infinite', {'U': 4, 'C': 8})
    # The first-turn draw was already made; Narset forbids all further draws.
    assert len(s.state.zones['p1:library']) == before  # Casting removed one card; putting the existing hand card back adds one.
    assert not s.state.zones['p1:hand'] and maximum(s) is None
    roundtrip(s)


@pytest.mark.parametrize('empty', ['hand', 'library'])
def test_mordenkainen_exchange_works_with_one_empty_zone(cards, empty):
    s = setup(cards)
    pw = spell(s, 'Mordenkainen', {'U': 2, 'C': 4})
    ids = list(s.state.zones[f'p1:{empty}'])
    if ids:
        act(s, 'p1', type='move', card_ids=ids, to={'zone': 'exile'})
    hand = Counter(s.state.cards[cid].card_id for cid in s.state.zones['p1:hand'])
    library = Counter(s.state.cards[cid].card_id for cid in s.state.zones['p1:library'])
    act(s, 'p1', type='set_counter', card_id=pw.id, kind='loyalty', value=10)
    activate(s, pw, 'Exchange your hand')
    assert Counter(s.state.cards[cid].card_id for cid in s.state.zones['p1:hand']) == library
    assert Counter(s.state.cards[cid].card_id for cid in s.state.zones['p1:library']) == hand
    assert maximum(s) is None
    roundtrip(s)


def exchange_with_commander(s, zone):
    pw = spell(s, 'Mordenkainen', {'U': 2, 'C': 4})
    commander = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.commander_key)
    act(s, 'p1', type='move', card_ids=[commander.id], to={'zone': zone})
    before = {z: Counter(s.state.cards[cid].card_id for cid in s.state.zones[f'p1:{z}']) for z in ('hand', 'library')}
    act(s, 'p1', type='set_counter', card_id=pw.id, kind='loyalty', value=10)
    activate(s, pw, 'Exchange your hand')
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'exchange_hand_library'
    assert s.state.cards[pw.id].zone == 'p1:graveyard'
    assert s.state.cards[commander.id].zone == f'p1:{zone}'
    assert {z: Counter(s.state.cards[cid].card_id for cid in s.state.zones[f'p1:{z}']) for z in before} == before
    assert not s.view('p2')['rules']['decision'].get('options')
    assert 'resume' not in s.view('p2')['rules']['decision']
    return commander, before


@pytest.mark.parametrize('zone', ['hand', 'library'])
@pytest.mark.parametrize('choice', ['yes', 'no'])
def test_exchange_prepares_commander_replacement_before_any_zone_changes(cards, zone, choice):
    s = setup(cards)
    commander, before = exchange_with_commander(s, zone)
    answer(s, [choice])
    target = 'library' if zone == 'hand' else 'hand'
    current = next(c for c in s.state.cards.values() if c.commander_key == commander.commander_key)
    assert current.zone == f'p1:{"command" if choice == "yes" else target}'
    for old, new in [('hand', 'library'), ('library', 'hand')]:
        expected = before[old].copy()
        if choice == 'yes' and zone == old:
            expected.subtract({commander.card_id: 1})
            expected = +expected
        assert Counter(s.state.cards[cid].card_id for cid in s.state.zones[f'p1:{new}']) == expected
    assert maximum(s) is None
    roundtrip(s)


def test_exchange_commander_replacement_resumes_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    commander, _ = exchange_with_commander(s, 'hand')
    path = tmp_path / 'exchange-commander.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import hand_size
from app.rules.plan import Plan
path, database, commander_key = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
d = s.state.rules.decision
assert d.resume['step'] == 'exchange_hand_library'
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['yes']})
for _ in range(20):
    if not s.state.zones['stack']:
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('ultimate failed to complete')
assert next(c for c in s.state.cards.values() if c.commander_key == commander_key).zone == 'p1:command'
assert hand_size.maximum(Plan(s.state, 'p1', repo, None), 'p1') is None
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), commander.commander_key],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('mode', ['infinite', 'bottom'])
def test_private_putback_cold_resume_preserves_placement_and_timed_hand_limit(cards, tmp_path, mode):
    import subprocess
    import sys

    s = setup(cards)
    if mode == 'infinite':
        spell(s, 'Enter the Infinite', {'U': 4, 'C': 8})
    else:
        pw = spell(s, 'Mordenkainen', {'U': 2, 'C': 4})
        activate(s, pw, 'Draw two cards')
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'put_back'
    assert not s.view('p2')['rules']['decision'].get('options')
    selected = d.options[0].id
    printing = s.state.cards[selected].card_id
    path = tmp_path / f'putback-{mode}.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import hand_size
from app.rules.plan import Plan
path, database, selected, printing, mode = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [selected]})
for _ in range(12):
    if not s.state.zones['stack']:
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('putback did not finish')
assert s.state.cards[s.state.zones['p1:library'][-1 if mode == 'bottom' else 0]].card_id == printing
assert hand_size.maximum(Plan(s.state, 'p1', repo, None), 'p1') == (7 if mode == 'bottom' else None)
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), selected, printing, mode],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_winter_multitype_graveyard_and_losing_delirium_restores_underlying_limit(cards):
    s = setup(cards)
    put(s, 'Reliquary Tower', 'battlefield', 'p2')
    put(s, 'Winter, Misanthropic Guide', 'battlefield')
    multi = put(s, 'Triarch Stalker', 'graveyard')  # Artifact + creature count as two distinct types.
    put(s, 'Lightning Bolt', 'graveyard')
    put(s, "Praetor's Counsel", 'graveyard')
    assert maximum(s, 'p2') == 3
    act(s, 'p1', type='move', card_ids=[multi.id], to={'zone': 'exile'})
    assert maximum(s, 'p2') is None
    roundtrip(s)


def test_winter_eight_distinct_types_clamps_derived_maximum_at_zero(cards):
    s = setup(cards)
    put(s, 'Winter, Misanthropic Guide', 'battlefield')
    for name in ['Triarch Stalker', 'Lightning Bolt', "Praetor's Counsel", 'Fervor', 'Karn Liberated', 'Invasion of Zendikar // Awakened Skyclave']:
        put(s, name, 'graveyard')
    # The six cards supply seven types; adding a land supplies the eighth.
    put(s, 'Forest', 'graveyard')
    assert maximum(s, 'p2') == maximum(s, 'p3') == 0
    roundtrip(s)


def test_mordenkainen_dog_cda_remains_native_after_hand_limit_extension(cards):
    from tests.test_rules_source_quality_protection import ch

    s = setup(cards)
    pw = spell(s, 'Mordenkainen', {'U': 2, 'C': 4})
    activate(s, pw, 'Dog Illusion')
    dog = next(c for c in s.state.cards.values() if c.token and 'Dog' in c.token.type_line)
    n = len(s.state.zones['p1:hand'])
    assert ch(s, dog).pt == (2 * n, 2 * n)
    put(s, 'Grizzly Bears', 'hand')
    assert ch(s, dog).pt == (2 * (n + 1), 2 * (n + 1))
    roundtrip(s)
