"""Constable's targets are counted from actual combat damage, not current power."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import attack, damage
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_ordered_tutor_continuations import cast


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json', 'damage_target_counts65_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='dc65', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards):
    s = gameplay.setup(cards, 'Cephalid Constable', 'Fog', 'Hermetic Study', 'Forest', 'Sol Ring', 'Llanowar Elves')
    source = cast(s, 'Cephalid Constable')
    return s, source


def test_constable_whole_canonical(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve('Cephalid Constable')).level == 'FULL'


def test_actual_one_combat_damage_bounds_choice_and_bounces_noncreature(cards):
    s, source = setup(cards)
    land = put(s, 'Forest', 'battlefield', 'p2')
    ring = put(s, 'Sol Ring', 'battlefield', 'p3')
    before = s.state.players['p2'].life
    attack(s, [source], target='p2', turn=4)
    damage(s)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'trigger_group' and d.min_choices == 0 and d.max_choices == 1
    assert land.id in [o.id for o in d.options] and ring.id not in [o.id for o in d.options]
    assert s.state.players['p2'].life == before - 1
    answer(s, [land.id])
    assert s.state.cards[land.id].zone == 'p2:hand'
    assert s.state.cards[ring.id].zone == 'p3:battlefield'
    roundtrip(s)


def test_actual_combat_trigger_allows_choosing_zero(cards):
    s, source = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack(s, [source], target='p2', turn=4)
    damage(s)
    answer(s, [])
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_real_growth_four_damage_allows_many_and_foreign_owned_returns_to_owner(cards):
    s, source = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    land = put(s, 'Forest', 'battlefield', 'p2')
    ring = put(s, 'Sol Ring', 'battlefield', 'p2')
    elf = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    foreign = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[foreign.id], player='p2')
    # Cast in the attacking turn so the temporary boost remains during damage.
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', turn=4)
    cast(s, 'Giant Growth', targets=[source.id])
    attack(s, [source], target='p2', turn=4)
    damage(s)
    d = s.state.rules.decision
    assert d and d.max_choices == 4
    assert {target.id, land.id, ring.id, elf.id, foreign.id} <= {o.id for o in d.options}
    answer(s, [target.id, ring.id, foreign.id])
    assert s.state.cards[target.id].zone == 'p2:hand'
    assert s.state.cards[ring.id].zone == 'p2:hand'
    assert s.state.cards[foreign.id].zone == 'p1:hand'
    assert s.state.cards[land.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_actual_noncombat_damage_from_granted_ability_does_not_trigger_bounce(cards):
    from tests.test_rules_conditional_prevention import activate
    from tests.test_rules_wave30m_durations import to_phase

    s, source = setup(cards)
    target = put(s, 'Sol Ring', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    cast(s, 'Hermetic Study', targets=[source.id])
    before = s.state.players['p2'].life
    activate(s, source, 'deals 1 damage', targets=['p2'])
    assert s.state.players['p2'].life == before - 1
    assert s.state.rules.decision is None
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_actual_prevented_combat_damage_does_not_trigger_bounce(cards):
    from tests.test_rules_conditional_prevention import cast as cast_for_player

    s, source = setup(cards)
    target = put(s, 'Sol Ring', 'battlefield', 'p2')
    attack(s, [source], target='p2', turn=4)
    cast_for_player(s, 'Fog', pid='p2')
    before = s.state.players['p2'].life
    damage(s)
    assert s.state.players['p2'].life == before
    assert s.state.rules.decision is None
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('response', ['leave_and_return', 'change_controller'])
def test_only_current_legal_incarnations_are_returned_after_response(cards, response):
    from tests.test_rules_library_look import settle
    from tests.test_rules_wave30m_durations import to_phase

    s, source = setup(cards)
    first = put(s, 'Sol Ring', 'battlefield', 'p2')
    second = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    cast(s, 'Giant Growth', targets=[source.id])
    attack(s, [source], target='p2', turn=4)
    damage(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[first.id, second.id])
    if response == 'leave_and_return':
        act(s, 'p2', type='move', card_ids=[first.id], to={'player': 'p2', 'zone': 'exile'})
        act(s, 'p2', type='move', card_ids=[first.id], to={'player': 'p2', 'zone': 'battlefield'})
    else:
        act(s, 'p1', type='set_controller', card_ids=[first.id], player='p3')
    settle(s)
    assert s.state.cards[first.id].zone.endswith(':battlefield')
    assert s.state.cards[second.id].zone == 'p2:hand'
    roundtrip(s)


def test_source_departure_keeps_damage_count_and_pending_native_targets(cards):
    from tests.test_rules_library_look import settle
    from tests.test_rules_wave30m_durations import to_phase

    s, source = setup(cards)
    first = put(s, 'Sol Ring', 'battlefield', 'p2')
    second = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    third = put(s, 'Forest', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    cast(s, 'Giant Growth', targets=[source.id])
    attack(s, [source], target='p2', turn=4)
    damage(s)
    d = s.state.rules.decision
    assert d.max_choices == 3  # Four damage, but only three legal permanents.
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[first.id, second.id, third.id])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p2:hand' for c in [first, second, third])
    roundtrip(s)


def test_genuine_cold_pending_damage_sized_target_group_uses_retained_event(cards, tmp_path):
    import subprocess
    import sys

    s, source = setup(cards)
    target = put(s, 'Sol Ring', 'battlefield', 'p2')
    attack(s, [source], target='p2', turn=4)
    damage(s)
    saved = tmp_path / 'constable65.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
p=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision
assert d and d.player=='p1' and d.max_choices==1
act(s,'p1',type='choose',decision_id=d.id,option_ids=[sys.argv[3]])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p2:hand'
assert s.state.rules.decision is None
roundtrip(s)
'''
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), target.id],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
