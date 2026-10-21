"""Announced owner groups and actual exile packets compose native copied-card casts."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library

NAMES = ['Chandra, Pyromaster', 'Mysterious Stranger', 'Doubling Season', 'Shock', 'Blaze', 'Fling',
         'Ground Seal', 'Into the Roil', 'Centaur Courser', 'Jace Beleren', 'Forest', 'Sol Ring',
         'Llanowar Elves', 'Lightning Bolt', 'Healing Salve', 'Hermetic Study', 'Murder', 'Noxious Revival', 'Reclaim', 'Opt', 'Disperse', 'Darksteel Myr']
TOP_TEN = ['Lightning Bolt', 'Divination', 'Giant Growth', 'Forest', 'Sol Ring', 'Llanowar Elves',
           'Grizzly Bears', 'Centaur Courser', 'Jace Beleren', 'Hermetic Study']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json',
                     'fight_exile_receipts65_cards.json', 'copied_exile_packets66_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='ce66', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *NAMES)


@pytest.mark.parametrize('name', NAMES[:2])
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_chandra_plus_player_binds_optional_creature_and_native_loyalty(cards):
    s = setup(cards)
    source = cast(s, NAMES[0])
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
        targets=['p2', target.id], target_counts=[1, 1])
    settle(s)
    assert s.state.players['p2'].life == 39
    assert s.state.cards[target.id].damage == 1
    assert s.state.cards[source.id].counters['loyalty'] == 5
    roundtrip(s)


def test_chandra_plus_own_planeswalker_uses_its_controller_for_creature_group(cards):
    s = setup(cards)
    walker = cast(s, 'Jace Beleren')
    source = cast(s, NAMES[0])
    creature = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
        targets=[walker.id, creature.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 2
    assert s.state.cards[creature.id].damage == 1
    roundtrip(s)


def test_chandra_plus_can_omit_optional_creature(cards):
    s = setup(cards)
    source = cast(s, NAMES[0])
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
        targets=['p2'], target_counts=[1, 0])
    settle(s)
    assert s.state.players['p2'].life == 39
    roundtrip(s)


def ultimate(s, top=TOP_TEN):
    cast(s, 'Doubling Season')
    source = cast(s, NAMES[0])
    assert s.state.cards[source.id].counters['loyalty'] == 8
    originals = stack_library(s, top)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    settle(s)
    assert s.state.cards[source.id].counters['loyalty'] == 1
    return source, originals


def test_chandra_actual_ten_exile_original_selection_then_three_individual_copies(cards):
    s = setup(cards)
    source, originals = ultimate(s)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'select_copy_originals'
    assert {s.state.cards[o.id].name for o in d.options} == {'Lightning Bolt', 'Divination', 'Giant Growth'}
    chosen = next(o.id for o in d.options if s.state.cards[o.id].name == 'Lightning Bolt')
    answer(s, [chosen])
    for _ in range(3):
        d = s.state.rules.decision
        assert d and d.resume['step'] == 'free_cast_pick'
        option = next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == 'Lightning Bolt')
        answer(s, [option])
        d = s.state.rules.decision
        assert d and 'p2' in [o.id for o in d.options]
        answer(s, ['p2'])
    settle(s)
    assert s.state.players['p2'].life == 31
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in originals)
    assert s.state.cards[chosen].zone == 'p1:exile' and not s.state.cards[chosen].is_token
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_stranger_empty_graveyards_needs_no_targets_and_creates_no_copy(cards):
    s = setup(cards)
    source = cast(s, NAMES[1])
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert not any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


def test_stranger_one_actual_exile_creates_no_copy(cards):
    s = setup(cards)
    original = put(s, 'Lightning Bolt', 'graveyard')
    cast(s, NAMES[1])
    d = s.state.rules.decision
    assert d and [o.id for o in d.options] == [original.id]
    answer(s, [original.id])
    assert s.state.cards[original.id].zone == 'p1:exile'
    assert s.state.rules.decision is None
    assert not any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


def test_stranger_one_required_target_per_matching_graveyard_then_one_random_copy(cards):
    s = setup(cards)
    own = put(s, 'Lightning Bolt', 'graveyard')
    foreign = put(s, 'Divination', 'graveyard', 'p2')
    ineligible = put(s, 'Grizzly Bears', 'graveyard', 'p3')
    cast(s, NAMES[1])
    d = s.state.rules.decision
    assert d and d.min_choices == d.max_choices == 1 and [o.id for o in d.options] == [own.id]
    answer(s, [own.id])
    d = s.state.rules.decision
    assert d and [o.id for o in d.options] == [foreign.id]
    answer(s, [foreign.id])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'free_cast_pick'
    copies = [c for c in s.state.cards.values() if c.is_token]
    assert len(copies) == 1 and copies[0].name in ('Lightning Bolt', 'Divination')
    assert copies[0].controller == 'p1' and copies[0].owner == 'p1'
    assert s.state.cards[own.id].zone == 'p1:exile'
    assert s.state.cards[foreign.id].zone == 'p2:exile'
    assert s.state.cards[ineligible.id].zone == 'p3:graveyard'
    answer(s, [])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_stranger_protected_matching_graveyards_do_not_silently_lose_required_targets(cards):
    s = setup(cards)
    cast(s, 'Ground Seal')
    original = put(s, 'Lightning Bolt', 'graveyard')
    foreign = put(s, 'Divination', 'graveyard', 'p2')
    cast(s, NAMES[1])
    assert s.state.rules.decision is None
    assert s.state.cards[original.id].zone == 'p1:graveyard'
    assert s.state.cards[foreign.id].zone == 'p2:graveyard'
    assert not any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize('cast_count', [0, 1, 2])
def test_chandra_copies_can_individually_be_cast_or_declined(cards, cast_count):
    s = setup(cards)
    _, originals = ultimate(s)
    d = s.state.rules.decision
    original = next(o.id for o in d.options if s.state.cards[o.id].name == 'Lightning Bolt')
    answer(s, [original])
    for _ in range(cast_count):
        d = s.state.rules.decision
        option = next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == 'Lightning Bolt')
        answer(s, [option])
        answer(s, ['p2'])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'free_cast_pick'
    answer(s, [])
    settle(s)
    assert s.state.players['p2'].life == 40 - 3 * cast_count
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in originals)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_chandra_zero_plays_actual_exiled_land_with_normal_land_limit(cards):
    s = setup(cards)
    source = cast(s, NAMES[0])
    land = stack_library(s, ['Forest'])[0]
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    assert s.state.cards[land].zone == 'p1:exile'
    act(s, 'p1', type='play_land', card_id=land)
    assert s.state.cards[land].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters['loyalty'] == 4
    roundtrip(s)


def test_chandra_zero_requires_normal_spell_mana_payment(cards):
    from tests.test_rules_bandmate_references import mana

    s = setup(cards)
    source = cast(s, NAMES[0])
    original = stack_library(s, ['Shock'])[0]
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    s.state.players['p1'].mana.clear()
    from app.game.errors import ActionError

    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=original, targets=['p2'], sources=[])
    assert s.state.model_dump_json() == before
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=original, targets=['p2'], sources=[])
    settle(s)
    assert s.state.players['p2'].life == 38
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_chandra_plus_retains_legal_creature_when_planeswalker_target_leaves(cards):
    from tests.test_rules_conditional_prevention import cast as response_cast

    s = setup(cards)
    walker = cast(s, 'Jace Beleren')
    source = cast(s, NAMES[0])
    creature = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
        targets=[walker.id, creature.id], target_counts=[1, 1])
    response_cast(s, 'Disperse', targets=[walker.id])
    assert s.state.cards[walker.id].zone == 'p1:hand'
    assert s.state.cards[creature.id].zone == 'p1:battlefield'
    assert s.state.cards[creature.id].damage == 1
    roundtrip(s)


def test_chandra_creature_cannot_block_even_when_actual_damage_is_prevented(cards):
    from app.game.errors import ActionError
    from tests.test_rules_conditional_prevention import attack
    from tests.test_rules_conditional_prevention import cast as response_cast
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    attacker = put(s, 'Llanowar Elves', 'battlefield')
    creature = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = cast(s, NAMES[0])
    to_phase(s, 'main1', turn=4)
    response_cast(s, 'Healing Salve', targets=[creature.id], modes=[1], pid='p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
        targets=['p2', creature.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[creature.id].damage == 0
    attack(s, [attacker], target='p2', turn=4)
    to_phase(s, 'declare_blockers')
    with pytest.raises(ActionError, match="can't block"):
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': creature.id, 'attacker_id': attacker.id}])
    roundtrip(s)


def test_chandra_rejects_creature_controlled_by_a_different_player_atomically(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    source = cast(s, NAMES[0])
    other = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
            targets=['p2', other.id], target_counts=[1, 1])
    assert s.state.model_dump_json() == before
    assert s.state.cards[source.id].counters['loyalty'] == 4


def test_stranger_cannot_choose_two_cards_from_one_graveyard_or_wrong_owner(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    first = put(s, 'Lightning Bolt', 'graveyard')
    second = put(s, 'Shock', 'graveyard')
    foreign = put(s, 'Divination', 'graveyard', 'p2')
    cast(s, NAMES[1])
    d = s.state.rules.decision
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[first.id, second.id])
    assert s.state.model_dump_json() == before
    answer(s, [first.id])
    d = s.state.rules.decision
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[second.id])
    assert s.state.model_dump_json() == before
    answer(s, [foreign.id])
    assert s.state.cards[second.id].zone == 'p1:graveyard'
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    answer(s, [])
    roundtrip(s)


def test_stranger_actual_flash_cast_on_opponents_turn(cards):
    from tests.test_rules_conditional_prevention import cast as response_cast
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    to_phase(s, 'main1', turn=2)
    source = response_cast(s, NAMES[1])
    assert s.state.turn.active_player == 'p2'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_stranger_one_target_removed_before_resolution_counts_only_actual_exile(cards):
    from tests.test_rules_conditional_prevention import cast as response_cast

    s = setup(cards)
    own = put(s, 'Lightning Bolt', 'graveyard')
    foreign = put(s, 'Divination', 'graveyard', 'p2')
    cast(s, NAMES[1])
    answer(s, [own.id])
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[foreign.id])
    response_cast(s, 'Noxious Revival', targets=[foreign.id], life_symbols=[])
    assert s.state.cards[own.id].zone == 'p1:exile'
    assert s.state.cards[foreign.id].zone == 'p2:library'
    assert s.state.rules.decision is None
    assert not any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


def test_stranger_copied_x_spell_has_x_zero(cards):
    s = setup(cards)
    own = put(s, 'Blaze', 'graveyard')
    foreign = put(s, 'Blaze', 'graveyard', 'p2')
    cast(s, NAMES[1])
    answer(s, [own.id])
    answer(s, [foreign.id])
    d = s.state.rules.decision
    option = next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == 'Blaze')
    answer(s, [option])
    answer(s, ['p2'])
    settle(s)
    assert s.state.players['p2'].life == 40
    assert s.state.cards[own.id].zone == 'p1:exile' and s.state.cards[foreign.id].zone == 'p2:exile'
    roundtrip(s)


def test_stranger_copied_fling_pays_mandatory_sacrifice_even_of_stranger_itself(cards):
    s = setup(cards)
    own = put(s, 'Fling', 'graveyard')
    foreign = put(s, 'Fling', 'graveyard', 'p2')
    source = cast(s, NAMES[1])
    answer(s, [own.id])
    answer(s, [foreign.id])
    d = s.state.rules.decision
    option = next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == 'Fling')
    answer(s, [option])
    answer(s, ['p2'])
    if s.state.rules.decision is not None:
        assert source.id in [o.id for o in s.state.rules.decision.options]
        answer(s, [source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == 37
    assert s.state.rules.decision is None
    roundtrip(s)


def test_native_seeded_resolver_reaches_each_actual_exiled_original_and_replays(cards):
    import random

    from app.game import engine
    from app.game.actions import parse_action
    from app.game.resolve import resolve
    from app.game.session import GameSession
    from app.game.state import GameState

    s = setup(cards)
    own = put(s, 'Lightning Bolt', 'graveyard')
    foreign = put(s, 'Divination', 'graveyard', 'p2')
    cast(s, NAMES[1])
    answer(s, [own.id])
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[foreign.id])
    saved = s.state.model_dump_json()
    outcomes = set()
    for seed in [0, 1]:
        clone = GameSession(GameState.model_validate_json(saved), cards=cards)
        for _ in range(8):
            if clone.state.rules.decision is not None:
                break
            actor = clone.state.rules.priority
            resolved = resolve(clone.state, parse_action({'type': 'pass_priority'}),
                               actor=actor, cards=cards, rng=random.Random(seed))
            engine.apply(clone.state, resolved)
            clone.history.record(resolved, clone.state)
        d = clone.state.rules.decision
        assert d and d.resume['step'] == 'free_cast_pick'
        copies = [c for c in clone.state.cards.values() if c.is_token]
        assert len(copies) == 1
        expected = random.Random(seed).sample(sorted([own.id, foreign.id]), 1)[0]
        assert copies[0].name == clone.state.cards[expected].name
        outcomes.add(copies[0].name)
        assert clone.history.rebuild().model_dump_json() == clone.state.model_dump_json()
    assert outcomes == {'Lightning Bolt', 'Divination'}


@pytest.mark.parametrize('resume_after', [0, 1, 2])
def test_genuine_cold_chandra_original_choice_and_each_copy_cast_continuation(cards, tmp_path, resume_after):
    import subprocess
    import sys

    s = setup(cards)
    _, originals = ultimate(s)
    d = s.state.rules.decision
    chosen = next(o.id for o in d.options if s.state.cards[o.id].name == 'Lightning Bolt')
    if resume_after:
        answer(s, [chosen])
        for _ in range(resume_after):
            d = s.state.rules.decision
            option = next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == 'Lightning Bolt')
            answer(s, [option])
            answer(s, ['p2'])
    saved = tmp_path / 'chandra66.json'
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
left=3-int(sys.argv[4])
d=s.state.rules.decision
if d.resume['step']=='select_copy_originals':
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[sys.argv[3]])
 settle(s)
for _ in range(left):
 d=s.state.rules.decision
 assert d and d.resume['step']=='free_cast_pick'
 option=next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name=='Lightning Bolt')
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[option])
 settle(s)
 d=s.state.rules.decision
 assert d and 'p2' in [o.id for o in d.options]
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['p2'])
 settle(s)
assert s.state.players['p2'].life==31
assert s.state.cards[sys.argv[3]].zone=='p1:exile'
assert not s.state.cards[sys.argv[3]].is_token
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), chosen, str(resume_after)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in originals)


@pytest.mark.parametrize('pending_targets', [False, True])
def test_genuine_cold_stranger_target_groups_or_frozen_random_copy(cards, tmp_path, pending_targets):
    import subprocess
    import sys

    s = setup(cards)
    own = put(s, 'Lightning Bolt', 'graveyard')
    foreign = put(s, 'Divination', 'graveyard', 'p2')
    cast(s, NAMES[1])
    frozen_copy = ''
    if not pending_targets:
        answer(s, [own.id])
        answer(s, [foreign.id])
        frozen_copy = next(c.id for c in s.state.cards.values() if c.is_token)
    saved = tmp_path / 'stranger66.json'
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
if not sys.argv[5]:
 for target in sys.argv[3:5]:
  d=s.state.rules.decision
  assert d and target in [o.id for o in d.options]
  act(s,d.player,type='choose',decision_id=d.id,option_ids=[target])
  settle(s)
copies=[c for c in s.state.cards.values() if c.is_token]
assert len(copies)==1
if sys.argv[5]:assert copies[0].id==sys.argv[5]
d=s.state.rules.decision
assert d and d.resume['step']=='free_cast_pick'
option=next(o.id for o in d.options if o.card_id==copies[0].id)
act(s,d.player,type='choose',decision_id=d.id,option_ids=[option])
settle(s)
if copies[0].name=='Lightning Bolt':
 d=s.state.rules.decision
 assert d and 'p2' in [o.id for o in d.options]
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['p2'])
 settle(s)
assert s.state.players['p2'].life==(37 if copies[0].name=='Lightning Bolt' else 40)
assert s.state.cards[sys.argv[3]].zone=='p1:exile'
assert s.state.cards[sys.argv[4]].zone=='p2:exile'
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), own.id, foreign.id, frozen_copy],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


NON_INSTANTS = ['Forest', 'Sol Ring', 'Llanowar Elves', 'Grizzly Bears', 'Centaur Courser',
                'Jace Beleren', 'Hermetic Study', 'Ground Seal', 'Mysterious Stranger', 'Darksteel Myr']


def test_chandra_ultimate_no_eligible_card_creates_no_copy(cards):
    s = setup(cards)
    _, originals = ultimate(s, NON_INSTANTS)
    assert s.state.rules.decision is None
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in originals)
    assert not any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


def test_chandra_three_copied_x_spells_all_have_x_zero(cards):
    s = setup(cards)
    _, originals = ultimate(s, ['Blaze', *NON_INSTANTS[:9]])
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    for _ in range(3):
        d = s.state.rules.decision
        option = next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == 'Blaze')
        answer(s, [option])
        answer(s, ['p2'])
    settle(s)
    assert s.state.players['p2'].life == 40
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in originals)
    roundtrip(s)


def test_chandra_ultimate_does_not_select_card_from_prior_zero_activation(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    cast(s, 'Doubling Season')
    source = cast(s, NAMES[0])
    old = stack_library(s, ['Shock'])[0]
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    assert s.state.cards[old].zone == 'p1:exile'
    to_phase(s, 'main1', turn=4)
    stack_library(s, TOP_TEN)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'select_copy_originals'
    assert old not in [o.id for o in d.options]
    chosen = next(o.id for o in d.options if s.state.cards[o.id].name == 'Lightning Bolt')
    answer(s, [chosen])
    answer(s, [])
    assert s.state.cards[old].zone == 'p1:exile'
    roundtrip(s)


def test_chandra_ultimate_source_departure_preserves_exile_and_copy_permissions(cards):
    from tests.test_rules_conditional_prevention import cast as response_cast

    s = setup(cards)
    cast(s, 'Doubling Season')
    source = cast(s, NAMES[0])
    stack_library(s, TOP_TEN)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    response_cast(s, 'Lightning Bolt', targets=[source.id], pid='p2')
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    d = s.state.rules.decision
    assert d and d.player == 'p1' and d.resume['step'] == 'select_copy_originals'
    original = next(o.id for o in d.options if s.state.cards[o.id].name == 'Lightning Bolt')
    answer(s, [original])
    d = s.state.rules.decision
    assert d and d.player == 'p1' and d.resume['step'] == 'free_cast_pick'
    answer(s, [])
    assert s.state.cards[original].zone == 'p1:exile'
    roundtrip(s)


def test_stranger_all_three_graveyards_contribute_one_original(cards):
    s = setup(cards)
    originals = [put(s, name, 'graveyard', pid).id for name, pid in
                 [('Lightning Bolt', 'p1'), ('Divination', 'p2'), ('Giant Growth', 'p3')]]
    cast(s, NAMES[1])
    for cid in originals:
        d = s.state.rules.decision
        assert d and d.min_choices == d.max_choices == 1 and [o.id for o in d.options] == [cid]
        answer(s, [cid])
    assert all(s.state.cards[cid].zone == f'p{i}:exile' for i, cid in enumerate(originals, 1))
    copies = [c for c in s.state.cards.values() if c.is_token]
    assert len(copies) == 1 and copies[0].name in ('Lightning Bolt', 'Divination', 'Giant Growth')
    answer(s, [])
    roundtrip(s)


def test_stranger_all_announced_targets_illegal_exiles_nothing_and_copies_nothing(cards):
    from tests.test_rules_conditional_prevention import cast as response_cast

    s = setup(cards)
    own = put(s, 'Lightning Bolt', 'graveyard')
    foreign = put(s, 'Divination', 'graveyard', 'p2')
    cast(s, NAMES[1])
    answer(s, [own.id])
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[foreign.id])
    response_cast(s, 'Noxious Revival', targets=[foreign.id], life_symbols=[], resolve=False)
    response_cast(s, 'Reclaim', targets=[own.id])
    assert s.state.cards[own.id].zone == 'p1:library'
    assert s.state.cards[foreign.id].zone == 'p2:library'
    assert s.state.rules.decision is None
    assert not any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


def test_stranger_newly_populated_graveyard_after_announcement_is_not_added(cards):
    from tests.test_rules_conditional_prevention import cast as response_cast

    s = setup(cards)
    own = put(s, 'Lightning Bolt', 'graveyard')
    foreign = put(s, 'Divination', 'graveyard', 'p2')
    cast(s, NAMES[1])
    answer(s, [own.id])
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[foreign.id])
    added = response_cast(s, 'Opt', pid='p3')
    assert s.state.rules.decision is not None
    answer(s, [])
    assert s.state.cards[added.id].zone == 'p3:graveyard'
    assert s.state.cards[own.id].zone == 'p1:exile'
    assert s.state.cards[foreign.id].zone == 'p2:exile'
    assert s.state.rules.decision.resume['step'] == 'free_cast_pick'
    answer(s, [])
    roundtrip(s)
