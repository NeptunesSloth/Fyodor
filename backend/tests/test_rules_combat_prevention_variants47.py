"""Opt-in exact prevention sentences through otherwise native modal/combat consumers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_damage_redirection import attack, cast, damage
from tests.test_rules_designations import put, settle
from tests.test_rules_ordered_zone_costs46 import DATA as BASE_DATA
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = [*BASE_DATA, *json.loads((Path(__file__).parent / 'fixtures/combat_prevention_variants47_cards.json').read_text()),
        *json.loads((Path(__file__).parent / 'fixtures/prevention47_copy_support.json').read_text())]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(DATA):
        base[row['name']] = card(row['name'], set_code='f47', number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def game(cards):
    names = ["Dromoka's Command", 'Winds of Qal Sisma', 'Woolly Razorback', 'Grizzly Bears',
             'Black Knight', 'Leashling', 'Lightning Bolt', 'Alms', "Nature's Kiss", 'Counterspell', 'Turn to Frog', 'Prey Upon', 'Twincast']
    return table(cards, names, names, names)


@pytest.mark.parametrize('name', ["Dromoka's Command", 'Winds of Qal Sisma'])
def test_staged_full_original_definition_coverage(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('ferocious', [False, True])
def test_winds_normal_or_ferocious_branch_applies_once_in_native_combat(cards, ferocious):
    s = game(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if ferocious:
        put(s, 'Woolly Razorback', 'battlefield')
    attack(s, [attacker])
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    settle(s)
    cast(s, 'Winds of Qal Sisma')
    damage(s)
    assert s.state.cards[attacker.id].zone == 'p1:battlefield' and s.state.cards[attacker.id].damage == 0
    assert s.state.cards[blocker.id].zone == ('p2:graveyard' if ferocious else 'p2:battlefield')


def test_command_native_spell_source_prevention_and_counter_modes(cards):
    s = game(cards)
    creature = put(s, 'Grizzly Bears', 'battlefield')
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    before = s.state.players['p1'].life
    cast(s, "Dromoka's Command", [creature.id, bolt.id], modes=[2, 0])
    assert s.state.players['p1'].life == before
    assert s.state.cards[creature.id].counters.get('+1/+1') == 1


def test_command_counter_precedes_native_fight_and_same_creature_can_be_in_two_modes(cards):
    s = game(cards)
    creature = put(s, 'Grizzly Bears', 'battlefield')
    opponent = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, "Dromoka's Command", [creature.id, creature.id, opponent.id], modes=[2, 3], target_counts=[1, 1, 1])
    assert s.state.cards[creature.id].zone == 'p1:battlefield'
    assert s.state.cards[creature.id].counters.get('+1/+1') == 1
    assert s.state.cards[creature.id].damage == 2
    assert s.state.cards[opponent.id].zone == 'p2:graveyard'


@pytest.mark.parametrize('enchantments', [False, True])
def test_command_native_targeted_player_sacrifice_and_empty_player_legal(cards, enchantments):
    s = game(cards)
    creature = put(s, 'Grizzly Bears', 'battlefield')
    if enchantments:
        first = put(s, 'Alms', 'battlefield', 'p2')
        target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
        to_phase(s, 'main1', turn=2)
        second = cast(s, "Nature's Kiss", [target.id], pid='p2')
    cast(s, "Dromoka's Command", ['p2', creature.id], modes=[1, 2])
    if enchantments:
        d = s.state.rules.decision
        assert d is not None and d.player == 'p2'
        assert {o.id for o in d.options} == {first.id, second.id}
        assert not s.state.cards[creature.id].counters.get('+1/+1')
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[second.id])
        settle(s)
        assert s.state.cards[second.id].zone == 'p2:graveyard' and s.state.cards[first.id].zone == 'p2:battlefield'
    assert s.state.cards[creature.id].counters.get('+1/+1') == 1


def test_command_spell_source_mode_does_not_prevent_creature_fight_caused_by_spell(cards):
    s = game(cards)
    mine = put(s, 'Grizzly Bears', 'battlefield')
    theirs = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    prey = cast(s, 'Prey Upon', [theirs.id, mine.id], pid='p2', target_counts=[1, 1], resolve=False)
    cast(s, "Dromoka's Command", [prey.id, mine.id], modes=[0, 2])
    assert s.state.cards[mine.id].zone == 'p1:battlefield' and s.state.cards[mine.id].damage == 2
    assert s.state.cards[theirs.id].zone == 'p2:graveyard'


@pytest.mark.parametrize('all_illegal', [False, True])
def test_command_mode_target_legality_filters_partial_and_all_targets_native(cards, all_illegal):
    s = game(cards)
    mine = put(s, 'Grizzly Bears', 'battlefield')
    theirs = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, "Dromoka's Command", [mine.id, mine.id, theirs.id], modes=[2, 3], target_counts=[1, 1, 1], resolve=False)
    if all_illegal:
        act(s, 'p1', type='move', card_ids=[mine.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p2', type='set_controller', card_ids=[theirs.id], player='p1')
    settle(s)
    assert s.state.cards[theirs.id].zone.endswith(':battlefield') and s.state.cards[theirs.id].damage == 0
    assert s.state.cards[mine.id].counters.get('+1/+1', 0) == (0 if all_illegal else 1)


@pytest.mark.parametrize('remove_when', ['before_resolve', 'after_resolve'])
def test_winds_freezes_ferocious_at_actual_resolution_not_later_damage(cards, remove_when):
    s = game(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    qualifier = put(s, 'Woolly Razorback', 'battlefield')
    attack(s, [attacker])
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    settle(s)
    cast(s, 'Winds of Qal Sisma', resolve=remove_when == 'after_resolve')
    act(s, 'p1', type='move', card_ids=[qualifier.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    damage(s)
    assert s.state.cards[attacker.id].zone == 'p1:battlefield' and s.state.cards[attacker.id].damage == 0
    assert s.state.cards[blocker.id].zone == ('p2:battlefield' if remove_when == 'before_resolve' else 'p2:graveyard')


def test_winds_ferocious_uses_actual_spell_controller_as_you(cards):
    s = game(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Woolly Razorback', 'battlefield', 'p2')
    attack(s, [attacker])
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    settle(s)
    cast(s, 'Winds of Qal Sisma', pid='p2')
    damage(s)
    assert s.state.cards[attacker.id].zone == 'p1:graveyard'
    assert s.state.cards[blocker.id].zone == 'p2:battlefield' and s.state.cards[blocker.id].damage == 0


@pytest.mark.parametrize('power', [3, 4])
def test_winds_ferocious_exact_current_power_threshold(cards, power):
    s = game(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    qualifier = put(s, 'Leashling', 'battlefield')
    if power == 4:
        act(s, 'p1', type='counter', card_ids=[qualifier.id], kind='+1/+1', delta=1)
    attack(s, [attacker])
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    settle(s)
    cast(s, 'Winds of Qal Sisma')
    damage(s)
    assert s.state.cards[blocker.id].zone == ('p2:graveyard' if power == 4 else 'p2:battlefield')


@pytest.mark.parametrize('ferocious', [False, True])
def test_real_fresh_load_before_winds_cast_rediscovers_full_pair_and_freezes_ferocious(cards, tmp_path, ferocious):
    import subprocess
    import sys

    s = game(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    qualifier = put(s, 'Woolly Razorback', 'battlefield') if ferocious else None
    attack(s, [attacker])
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    settle(s)
    save = tmp_path / 'winds-before-cast.json'
    save.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_damage_redirection import cast,damage
save,db,attacker,blocker,qualifier=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
cast(s,'Winds of Qal Sisma')
if qualifier:
 act(s,'p1',type='move',card_ids=[qualifier],to={'player':'p1','zone':'graveyard'})
damage(s)
assert s.state.cards[attacker].zone=='p1:battlefield' and s.state.cards[attacker].damage==0
assert s.state.cards[blocker].zone==('p2:graveyard' if qualifier else 'p2:battlefield')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), attacker.id, blocker.id, qualifier.id if qualifier else ''],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_fresh_process_command_saved_targeted_player_choice_continues_next_mode_once(cards, tmp_path):
    import subprocess
    import sys

    s = game(cards)
    creature = put(s, 'Grizzly Bears', 'battlefield')
    first = put(s, 'Alms', 'battlefield', 'p2')
    other_creature = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    second = cast(s, "Nature's Kiss", [other_creature.id], pid='p2')
    cast(s, "Dromoka's Command", ['p2', creature.id], modes=[1, 2])
    assert s.state.rules.decision is not None and s.state.rules.decision.player == 'p2'
    save = tmp_path / 'command-edict-choice.json'
    save.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
save,db,first,second,creature=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
assert d is not None and d.player=='p2'
act(s,'p2',type='choose',decision_id=d.id,option_ids=[second])
settle(s)
assert s.state.cards[second].zone=='p2:graveyard' and s.state.cards[first].zone=='p2:battlefield'
assert s.state.cards[creature].counters.get('+1/+1')==1
roundtrip(s)
assert s.state.cards[creature].counters.get('+1/+1')==1
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), first.id, second.id, creature.id],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_twincast_copy_preserves_command_modes_and_independent_counter_resolution(cards):
    from tests.test_rules_wave31d_spell_copies import settle as settle_copies

    s = game(cards)
    creature = put(s, 'Grizzly Bears', 'battlefield')
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    before = s.state.players['p1'].life
    act(s, 'p1', type='set_prefs', hold_priority=True)
    command = cast(s, "Dromoka's Command", [bolt.id, creature.id], modes=[0, 2], resolve=False)
    cast(s, 'Twincast', [command.id], resolve=False)
    settle_copies(s)
    assert s.state.players['p1'].life == before
    assert s.state.cards[creature.id].counters.get('+1/+1') == 2


def test_winds_only_prevents_combat_damage_and_current_turn(cards):
    s = game(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Winds of Qal Sisma')
    before = s.state.players['p1'].life
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.players['p1'].life == before - 3
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    to_phase(s, 'declare_blockers')
    if (d := s.state.rules.decision) is not None and d.kind == 'declare_blockers':
        act(s, 'p1', type='declare_blockers', blocks=[])
    settle(s)
    before = s.state.players['p1'].life
    damage(s)
    assert s.state.players['p1'].life == before - 2
    assert not any(r.get('kind') == 'prevent' and r.get('source_card')
                   and s.state.cards[r['source_card']].name == 'Winds of Qal Sisma' for r in s.state.rules.replacements)
