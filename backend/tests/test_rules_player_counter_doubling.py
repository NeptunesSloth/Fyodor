"""Aetheric Amplifier doubles player counters, not other player resources."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Aetheric Amplifier'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/player_counter_doubling_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='pcd', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, resources=None, permanent=None, opponent=False, second=None):
    s = table(cards, [NAME, 'Doubling Season', 'Vorinclex, Monstrous Raider', 'Solemnity',
                      'Melira, Sylvok Outcast', "Lae'zel, Vlaakith's Champion"], ['Vorinclex, Monstrous Raider'])
    source = put(s, NAME, 'battlefield')
    if permanent:
        put(s, permanent, 'battlefield', pid='p2' if opponent else 'p1')
    if second:
        put(s, second, 'battlefield')
    for kind, n in (resources or {}).items():
        act(s, 'p1', type='set_resource', player='p1', key=kind, value=n)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    return s, source


def activate(s, source, mode=1, targets=None):
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, modes=[mode], targets=targets or [], sources=[])


def test_canonical_all_modes_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_all_existing_counter_kinds_double_but_speed_and_others_do_not(cards):
    s, source = setup(cards, {'energy': 3, 'experience': 2, 'poison': 3, 'rad': 1, 'speed': 2})
    act(s, 'p2', type='set_resource', player='p2', key='energy', value=7)
    activate(s, source)
    assert s.state.cards[source.id].tapped and mana_pool(s, 'p1') == {}
    roundtrip(s)
    settle(s)
    assert s.state.players['p1'].resources == {'energy': 6, 'experience': 4, 'poison': 6, 'rad': 2, 'speed': 2}
    assert s.state.players['p2'].resources['energy'] == 7
    roundtrip(s)


def test_no_counters_is_still_a_legal_paid_activation(cards):
    s, source = setup(cards, {'speed': 3})
    activate(s, source)
    settle(s)
    assert s.state.players['p1'].resources == {'energy': 0, 'experience': 0, 'poison': 0, 'speed': 3}
    assert s.state.cards[source.id].tapped and mana_pool(s, 'p1') == {}
    roundtrip(s)


@pytest.mark.parametrize('permanent,opponent,expected', [('Vorinclex, Monstrous Raider', False, 9),
                                                       ('Vorinclex, Monstrous Raider', True, 4),
                                                       ('Doubling Season', False, 6), ('Solemnity', False, 3)])
def test_native_player_counter_replacements_and_prohibitions(cards, permanent, opponent, expected):
    s, source = setup(cards, {'energy': 3}, permanent, opponent)
    activate(s, source)
    settle(s)
    assert s.state.players['p1'].resources['energy'] == expected
    roundtrip(s)


def test_melira_prevents_only_poison_addition(cards):
    s, source = setup(cards, {'energy': 3, 'poison': 3}, 'Melira, Sylvok Outcast')
    activate(s, source)
    settle(s)
    assert s.state.players['p1'].resources['energy'] == 6 and s.state.players['p1'].resources['poison'] == 3
    roundtrip(s)


def test_doubling_poison_can_cause_normal_state_based_loss(cards):
    s, source = setup(cards, {'poison': 6})
    activate(s, source)
    settle(s)
    assert 'p1' in s.state.rules.lost
    roundtrip(s)


def test_original_ability_controller_gets_counters_after_source_changes_controller(cards):
    s, source = setup(cards, {'energy': 3})
    activate(s, source)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert s.state.players['p1'].resources['energy'] == 6 and s.state.players['p2'].resources['energy'] == 0
    roundtrip(s)


def test_first_mode_still_doubles_every_kind_on_a_permanent(cards):
    s, source = setup(cards, {'energy': 3})
    act(s, 'p1', type='set_counter', card_id=source.id, kind='charge', value=3)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='shield', value=1)
    activate(s, source, 0, [source.id])
    settle(s)
    assert s.state.cards[source.id].counters == {'charge': 6, 'shield': 2}
    assert s.state.players['p1'].resources['energy'] == 3
    roundtrip(s)


def test_sorcery_only_restriction_rejects_without_paying_or_tapping(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s, source = setup(cards, {'energy': 3})
    to_phase(s, 'begin_combat')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        activate(s, source)
    assert s.state.model_dump(mode='json') == before and not s.state.cards[source.id].tapped
    roundtrip(s)


def test_native_replacement_order_can_pause_for_each_counter_kind(cards):
    s, source = setup(cards, {'energy': 3, 'experience': 2}, 'Vorinclex, Monstrous Raider', second="Lae'zel, Vlaakith's Champion")
    activate(s, source)
    settle(s)
    choices = 0
    while (d := s.state.rules.decision) is not None:
        choices += 1
        roundtrip(s)
        option = next(o for o in d.options if 'Vorinclex' in o.label)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
        settle(s)
    assert choices == 2
    assert s.state.players['p1'].resources['energy'] == 10 and s.state.players['p1'].resources['experience'] == 7
    roundtrip(s)


@pytest.mark.parametrize('color', ['W', 'U', 'B', 'R', 'G'])
def test_original_any_color_mana_ability_is_unchanged(cards, color):
    s, source = setup(cards)
    act(s, 'p1', type='clear_mana', player='p1')
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    index = next(a.index for a in ch.abilities if a.kind == 'mana')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, mana_choice=color)
    assert mana_pool(s, 'p1') == {color: 1}
    roundtrip(s)


def test_cold_process_resolves_saved_modal_ability_with_counter_order_choices(cards, tmp_path):
    s, source = setup(cards, {'energy': 3, 'experience': 2}, 'Vorinclex, Monstrous Raider', second="Lae'zel, Vlaakith's Champion")
    activate(s, source)
    saved = tmp_path / 'pending-amplifier.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state_path, database = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state_path).read_text()), cards=repo)
choices = 0
for _ in range(50):
    d = s.state.rules.decision
    if d is not None:
        choice = next(o for o in d.options if 'Vorinclex' in o.label)
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [choice.id]})
        choices += 1
    elif s.state.rules.stack:
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
assert choices == 2
assert s.state.players['p1'].resources['energy'] == 10
assert s.state.players['p1'].resources['experience'] == 7
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
