"""Static exile replacements read actual damage to original objects this turn."""
import pytest

from app.rules import coverage
from tests import test_rules_fight_exile_receipts65 as support
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Kumano's Blessing", 'Kumano Faces Kakkazan // Etching of Kumano']


@pytest.fixture()
def cards(settings):
    yield from support.cards.__wrapped__(settings)


setup = support.setup


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def etching(s):
    source = cast(s, NAMES[1])
    to_phase(s, 'main1', turn=4)
    settle(s)
    to_phase(s, 'main1', turn=7)
    settle(s)
    assert s.state.cards[source.id].face == 1
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    return s.state.cards[source.id]


def test_all_three_chapters_extra_counter_transform_and_actual_haste_combat(cards):
    from tests.test_rules_conditional_prevention import attack, damage
    from tests.test_rules_conditional_prevention import cast as cast_for_player

    s = setup(cards)
    own_walker = cast(s, 'Jace Beleren')
    to_phase(s, 'main1', turn=2)
    opponent_walker = cast_for_player(s, 'Jace Beleren', pid='p2')
    to_phase(s, 'main1', turn=4)
    source = cast(s, NAMES[1])
    assert s.state.players['p2'].life == s.state.players['p3'].life == 39
    assert s.state.cards[own_walker.id].counters['loyalty'] == 3
    assert s.state.cards[opponent_walker.id].counters['loyalty'] == 2
    to_phase(s, 'main1', turn=7)
    settle(s)
    first = cast(s, 'Llanowar Elves')
    second = cast(s, 'Grizzly Bears')
    assert s.state.cards[first.id].counters.get('+1/+1') == 1
    assert not s.state.cards[second.id].counters.get('+1/+1')
    to_phase(s, 'main1', turn=10)
    settle(s)
    assert s.state.cards[source.id].face == 1
    attack(s, [s.state.cards[source.id]], target='p2', turn=10)
    damage(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('aura_after_damage', [False, True])
def test_blessing_uses_actual_enchanted_creature_damage_including_before_aura_enters(cards, aura_after_damage):
    from tests.test_rules_conditional_prevention import activate

    s = setup(cards)
    source = put(s, 'Grizzly Bears', 'battlefield')
    target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    cast(s, 'Hermetic Study', targets=[source.id])
    if not aura_after_damage:
        cast(s, NAMES[0], targets=[source.id])
    activate(s, source, 'deals 1 damage', targets=[target.id])
    if aura_after_damage:
        cast(s, NAMES[0], targets=[source.id])
    cast(s, 'Murder', targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:exile'
    roundtrip(s)


def test_destroyed_blessing_no_longer_replaces_later_death(cards):
    from tests.test_rules_conditional_prevention import activate

    s = setup(cards)
    source = put(s, 'Grizzly Bears', 'battlefield')
    target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    cast(s, 'Hermetic Study', targets=[source.id])
    aura = cast(s, NAMES[0], targets=[source.id])
    activate(s, source, 'deals 1 damage', targets=[target.id])
    cast(s, 'Naturalize', targets=[aura.id])
    cast(s, 'Murder', targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('source_player,target_player,expected', [('p1', 'p1', 'exile'), ('p1', 'p2', 'exile'), ('p2', 'p3', 'graveyard')])
def test_etching_filters_damage_source_controller_not_victim_controller(cards, source_player, target_player, expected):
    from tests.test_rules_conditional_prevention import cast as cast_for_player

    s = setup(cards)
    etching(s)
    target = put(s, 'Centaur Courser', 'battlefield', target_player)
    cast_for_player(s, 'Lightning Bolt', targets=[target.id], pid=source_player)
    assert s.state.cards[target.id].zone == target_player + ':' + expected
    roundtrip(s)


def test_native_damage_actor_freezes_source_controller_for_deferred_history_collection(cards):
    from app.rules import effects, history, targets
    from app.rules.plan import Plan

    s = setup(cards)
    source = put(s, 'Grizzly Bears', 'battlefield')
    target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    plan = Plan(s.state, 'p1', cards, None)
    context = {'controller': 'p1', 'source_card': source.id, 'source_object': plan.oid(source),
               'targets': [targets.ref(plan, target.id).model_dump()]}
    assert effects.damage(plan, context, {'do': 'damage', 'who': 'target', 'n': 1})
    # Model a later instruction of the same resolving ability changing control
    # before the damage event collector reads it; the event's actor stays p1.
    source.controller = 'p2'
    facts = [f for f in history.log_for(plan).facts if f.kind == 'damaged' and f.object_id == plan.oid(target)]
    assert len(facts) == 1 and facts[0].source_controller == 'p1'


def test_etching_simultaneous_lethal_damage_includes_itself_and_other_creature(cards):
    s = setup(cards)
    source = etching(s)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Pyroclasm')
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert s.state.cards[target.id].zone == 'p2:exile'
    roundtrip(s)


def test_fully_prevented_damage_does_not_qualify_for_etching(cards):
    from tests.test_rules_conditional_prevention import cast as cast_for_player

    s = setup(cards)
    etching(s)
    target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    cast_for_player(s, 'Healing Salve', targets=[target.id], modes=[1], pid='p2')
    cast(s, 'Lightning Bolt', targets=[target.id])
    cast(s, 'Murder', targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_genuine_cold_blessing_reads_prior_damage_to_original_object(cards, tmp_path):
    import subprocess
    import sys

    from tests.test_rules_conditional_prevention import activate

    s = setup(cards)
    source = put(s, 'Grizzly Bears', 'battlefield')
    target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    cast(s, 'Hermetic Study', targets=[source.id])
    activate(s, source, 'deals 1 damage', targets=[target.id])
    cast(s, NAMES[0], targets=[source.id])
    saved = tmp_path / 'blessing65.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import roundtrip
from tests.test_rules_ordered_tutor_continuations import cast
p=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
cast(s,'Murder',targets=[sys.argv[3]])
assert s.state.cards[sys.argv[3]].zone=='p2:exile'
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_blessing_actual_flash_cast_on_opponents_turn(cards):
    from tests.test_rules_conditional_prevention import cast as cast_for_player

    s = setup(cards)
    source = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=2)
    aura = cast_for_player(s, NAMES[0], targets=[source.id], pid='p1')
    assert s.state.turn.active_player == 'p2'
    assert s.state.cards[aura.id].zone == 'p1:battlefield'
    assert s.state.cards[aura.id].attached_to == source.id
    roundtrip(s)


@pytest.mark.parametrize('blink_host', [False, True])
def test_blessing_damage_does_not_follow_source_or_recipient_successor(cards, blink_host):
    from tests.game_helpers import act
    from tests.test_rules_conditional_prevention import activate
    from tests.test_rules_conditional_prevention import cast as response_cast

    s = setup(cards)
    source = put(s, 'Grizzly Bears', 'battlefield')
    target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    cast(s, 'Hermetic Study', targets=[source.id])
    aura = cast(s, NAMES[0], targets=[source.id])
    activate(s, source, 'deals 1 damage', targets=[target.id])
    if blink_host:
        response_cast(s, 'Cloudshift', targets=[source.id])
        assert s.state.cards[aura.id].zone == 'p1:graveyard'
        cast(s, 'Regrowth', targets=[aura.id])
        act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[source.id], sources=[])
        settle(s)
    else:
        response_cast(s, 'Cloudshift', targets=[target.id], pid='p2')
    cast(s, 'Murder', targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)
