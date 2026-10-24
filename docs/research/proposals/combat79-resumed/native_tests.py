"""Native unblocked life, resolution payments, and original-source reveal durations."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

NAMES = ['Master of Cruelties', 'Bone Dancer', 'Stromgald Spy']
DATA = json.loads((Path(__file__).parent / 'fixtures/unblocked_choices79_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




@pytest.mark.parametrize('name', NAMES)
def test_whole_card_full(cards, name):
    report = coverage.of_card_data(cards.resolve(name))
    assert report.level == 'FULL', report


def test_master_alone_group(cards):
    from app.game.errors import ActionError
    s = table(cards, NAMES + ['Grizzly Bears'], [], [])
    master = put(s, 'Master of Cruelties', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    to_phase(s, 'declare_attackers', turn=7)
    with pytest.raises(ActionError):
        attack(s, (master, 'p2'), (bear, 'p2'))
    attack(s, (master, 'p2'))


def setup79(cards, name):
    s = table(cards, [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves'], ['Grizzly Bears', 'Llanowar Elves', 'Forest', 'Island'], [])
    source = put(s, name, 'battlefield')
    start(s)
    return s, source


def unblocked79(s, source):
    from tests.test_rules_unblocked_riders32 import unblocked
    unblocked(s, source)


def answer79(s, yes):
    from tests.test_rules_designations import pick
    assert s.state.rules.decision is not None
    pick(s, ['yes' if yes else 'no'])
    settle(s)


def test_master_actual_unblocked_life_assignment(cards):
    s, source = setup79(cards, 'Master of Cruelties')
    unblocked79(s, source)
    assert s.state.players['p2'].life == 1
    assert 'assign_none' in chars(s, source).imposed
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == 1
    to_phase(s, 'main2', turn=4)
    assert 'assign_none' not in chars(s, source).imposed


@pytest.mark.parametrize('yes', [True, False])
def test_bone_current_top_creature_ignores_noncreature(cards, yes):
    s, source = setup79(cards, 'Bone Dancer')
    bear = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    put(s, 'Forest', 'graveyard', 'p2')
    unblocked79(s, source)
    answer79(s, yes)
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    assert s.state.cards[elf.id].zone == ('p1:battlefield' if yes else 'p2:graveyard')
    assert ('assign_none' in chars(s, source).imposed) is yes
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == (40 if yes else 38)


@pytest.mark.parametrize('yes', [True, False])
def test_spy_live_visibility_and_damage(cards, yes):
    from app.game.visibility import SPECTATOR, can_see
    s, source = setup79(cards, 'Stromgald Spy')
    hidden = put(s, 'Forest', 'hand', 'p2')
    unblocked79(s, source)
    answer79(s, yes)
    assert can_see(s.state, hidden, 'p1') is yes
    assert can_see(s.state, hidden, SPECTATOR) is yes
    assert ('assign_none' in chars(s, source).imposed) is yes
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == (40 if yes else 38)


def test_bone_prevented_entry_does_not_pay_no_damage(cards):
    s, source = setup79(cards, 'Bone Dancer')
    put(s, "Grafdigger's Cage", 'battlefield')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    unblocked79(s, source)
    assert s.state.rules.decision is None
    assert s.state.cards[elf.id].zone == 'p2:graveyard'
    assert 'assign_none' not in chars(s, source).imposed
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == 38


def test_bone_empty_graveyard_does_not_pay(cards):
    s, source = setup79(cards, 'Bone Dancer')
    put(s, 'Forest', 'graveyard', 'p2')
    unblocked79(s, source)
    assert s.state.rules.decision is None
    assert 'assign_none' not in chars(s, source).imposed
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == 38


@pytest.mark.parametrize('change', ['control', 'leave', 'blink'])
def test_spy_reveal_fixed_player_and_source_duration(cards, change):
    from app.game.visibility import can_see
    s, source = setup79(cards, 'Stromgald Spy')
    hidden = put(s, 'Forest', 'hand', 'p2')
    unblocked79(s, source)
    answer79(s, True)
    assert can_see(s.state, hidden, 'p1')
    later = put(s, 'Island', 'hand', 'p2')
    assert can_see(s.state, later, 'p1')
    if change == 'control':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    else:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player':'p1','zone':'hand'})
        if change == 'blink':
            act(s, 'p1', type='move', card_ids=[source.id], to={'player':'p1','zone':'battlefield'})
    assert can_see(s.state, hidden, 'p1') is (change == 'control')
    assert can_see(s.state, later, 'p1') is (change == 'control')


@pytest.mark.parametrize('name', NAMES)
def test_genuine_cold_native_unblocked_resolution(cards, tmp_path, name):
    import subprocess
    import sys

    import app
    s, source = setup79(cards, name)
    hidden = put(s, 'Forest', 'hand', 'p2')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    from tests.test_rules_wave30m_durations import stops
    stops(s, 'main1', 'declare_attackers', 'declare_blockers', 'combat_damage', 'end_combat')
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    to_phase(s, 'declare_blockers', turn=4)
    # Native blockers submission commits the unblocked event and leaves actual trigger pending.
    if s.state.rules.decision is not None:
        act(s, 'p2', type='declare_blockers', blocks=[])
    assert s.state.zones.get('stack')
    saved = tmp_path / 'unblocked.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.visibility import can_see,SPECTATOR
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_wave6c_tokens_pumps import chars
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
name,source,hidden,elf=sys.argv[3:]
settle(s)
if name!='Master of Cruelties':
 d=s.state.rules.decision
 assert d and d.kind=='confirm'
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes'])
 settle(s)
assert 'assign_none' in chars(s,s.state.cards[source]).imposed
if name=='Master of Cruelties':assert s.state.players['p2'].life==1
elif name=='Bone Dancer':assert s.state.cards[elf].zone=='p1:battlefield'
else:assert can_see(s.state,s.state.cards[hidden],SPECTATOR)
assert s.state.rules.decision is None
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, source.id, hidden.id, elf.id],
        capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr


def test_bone_replaced_return_is_paid_no_combat_damage(cards):
    s, source = setup79(cards, 'Bone Dancer')
    put(s, 'Containment Priest', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    unblocked79(s, source)
    answer79(s, True)
    assert s.state.cards[elf.id].zone == 'p2:exile'
    assert 'assign_none' in chars(s, source).imposed
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == 40


@pytest.mark.parametrize('name', NAMES)
def test_blocked_attacker_does_not_trigger(cards, name):
    from tests.test_rules_wave30p_combat import block
    s, source = setup79(cards, name)
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    to_phase(s, 'declare_blockers', turn=4)
    block(s, 'p2', (blocker, source))
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.zones.get('stack')
    assert s.state.players['p2'].life == 40
    assert 'assign_none' not in chars(s, source).imposed


@pytest.mark.parametrize('name', NAMES)
def test_attacking_planeswalker_uses_actual_defending_player(cards, name):
    from tests.test_rules_unblocked_riders32 import unblocked
    s = table(cards, [c['name'] for c in DATA], [c['name'] for c in DATA] + ['Forest', 'Llanowar Elves'], [])
    source = put(s, name, 'battlefield')
    walker = put(s, 'Gideon Jura', 'battlefield', 'p2')
    act(s, 'p2', type='counter', card_ids=[walker.id], kind='loyalty', delta=6)
    hidden = put(s, 'Forest', 'hand', 'p2')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    start(s)
    unblocked(s, source, defender=walker.id)
    assert s.state.players['p2'].life == 40
    if name == 'Master of Cruelties':
        assert s.state.rules.decision is None
        assert 'assign_none' not in chars(s, source).imposed
    else:
        answer79(s, True)
        assert 'assign_none' in chars(s, source).imposed
        if name == 'Bone Dancer':
            assert s.state.cards[elf.id].zone == 'p1:battlefield'
        else:
            from app.game.visibility import can_see
            assert can_see(s.state, hidden, 'p1')


def test_master_attack_requirement_optimizer_prefers_required_other(cards):
    from app.game.errors import ActionError
    from tests.test_rules_declaration_requirements33 import cast
    s, source = setup79(cards, 'Master of Cruelties')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=7)
    cast(s, 'Incite', [bear.id])
    to_phase(s, 'declare_attackers', turn=7)
    with pytest.raises(ActionError):
        attack(s, (source, 'p2'))
    attack(s, (bear, 'p2'))
    assert s.state.cards[bear.id].attacking is not None
    assert s.state.cards[source.id].attacking is None


def test_master_life_cannot_change_still_assigns_none(cards):
    s = table(cards, [c['name'] for c in DATA], ['Platinum Emperion'], [])
    source = put(s, 'Master of Cruelties', 'battlefield')
    put(s, 'Platinum Emperion', 'battlefield', 'p2')
    start(s)
    unblocked79(s, source)
    assert s.state.players['p2'].life == 40
    assert 'assign_none' in chars(s, source).imposed
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == 40


def test_spy_resolved_duration_survives_ability_loss(cards):
    from app.game.visibility import can_see
    from tests.test_rules_declaration_requirements33 import cast
    s, source = setup79(cards, 'Stromgald Spy')
    hidden = put(s, 'Forest', 'hand', 'p2')
    unblocked79(s, source)
    answer79(s, True)
    to_phase(s, 'main2', turn=4)
    cast(s, 'Humility')
    assert not chars(s, source).abilities
    assert can_see(s.state, hidden, 'p1')


@pytest.mark.parametrize('top_name', ['Grizzly Bears', 'Llanowar Elves'])
def test_bone_simultaneous_graveyard_order_is_chosen_by_owner(cards, top_name):
    from tests.test_rules_designations import pick
    s, source = setup79(cards, 'Bone Dancer')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    elf = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=1)
    pyro = put(s, 'Pyroclasm', 'hand')
    mana(s, R=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=pyro.id)
    for _ in range(8):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2' and d.resume['step'] == 'graveyard_order'
    first, second = (bear, elf) if top_name == 'Grizzly Bears' else (elf, bear)
    pick(s, [first.id, second.id])
    settle(s)
    unblocked79(s, source)
    answer79(s, True)
    assert s.state.cards[first.id].zone == 'p1:battlefield'
    assert s.state.cards[second.id].zone == 'p2:graveyard'


def pending79(s, source):
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    to_phase(s, 'declare_blockers', turn=4)
    d = s.state.rules.decision
    if d is not None and d.kind == 'declare_blockers':
        act(s, 'p2', type='declare_blockers', blocks=[])
    assert s.state.zones.get('stack')


@pytest.mark.parametrize('name', NAMES)
def test_original_source_blinked_before_resolution_is_not_new_source(cards, name):
    from app.game.visibility import can_see
    s, source = setup79(cards, name)
    hidden = put(s, 'Forest', 'hand', 'p2')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    cloud = put(s, 'Cloudshift', 'hand')
    pending79(s, source)
    old_oid = s.state.rules.object_id(source.id)
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=cloud.id, targets=[source.id])
    settle(s)
    assert s.state.rules.object_id(source.id) != old_oid
    if name != 'Master of Cruelties':
        answer79(s, True)
    assert 'assign_none' not in chars(s, source).imposed
    if name == 'Master of Cruelties':
        assert s.state.players['p2'].life == 1
    elif name == 'Bone Dancer':
        assert s.state.cards[elf.id].zone == 'p1:battlefield'
    else:
        assert not can_see(s.state, hidden, 'p1')


@pytest.mark.parametrize('name', ['Bone Dancer', 'Stromgald Spy'])
def test_turn_duration_keeps_no_damage_in_actual_additional_combat(cards, name):
    s, source = setup79(cards, name)
    assault = put(s, 'Aggravated Assault', 'battlefield')
    put(s, 'Llanowar Elves', 'graveyard', 'p2')
    unblocked79(s, source)
    answer79(s, True)
    to_phase(s, 'main2', turn=4)
    assert 'assign_none' in chars(s, source).imposed
    mana(s, R=2, C=3)
    act(s, 'p1', type='activate_ability', card_id=assault.id, ability=0)
    settle(s)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    to_phase(s, 'declare_blockers', turn=4)
    d = s.state.rules.decision
    if d and d.kind == 'declare_blockers':
        act(s, 'p2', type='declare_blockers', blocks=[])
    settle(s)
    if name == 'Stromgald Spy':
        answer79(s, False)
    assert 'assign_none' in chars(s, source).imposed
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == 40


def test_master_put_onto_battlefield_attacking_with_another_triggers(cards):
    from tests.test_rules_wave30p_combat import drive
    s = table(cards, [c['name'] for c in DATA], [], [])
    kaalia = put(s, 'Kaalia of the Vast', 'battlefield')
    source = put(s, 'Master of Cruelties', 'hand')
    start(s)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (kaalia, 'p2'))
    drive(s, pick=['yes', source.id], stop_at=('declare_blockers',))
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].attacking is not None
    to_phase(s, 'declare_blockers', turn=4)
    d = s.state.rules.decision
    if d and d.kind == 'declare_blockers':
        act(s, 'p2', type='declare_blockers', blocks=[])
    settle(s)
    assert s.state.players['p2'].life == 1
    assert 'assign_none' in chars(s, source).imposed
    assert 'assign_none' not in chars(s, kaalia).imposed
    to_phase(s, 'end_combat', turn=4)
    assert s.state.players['p2'].life == -1


@pytest.mark.parametrize('name', NAMES)
def test_actual_cast_and_later_native_unblocked_action(cards, name):
    from tests.test_rules_unblocked_riders32 import unblocked
    s = table(cards, [c['name'] for c in DATA], ['Forest', 'Llanowar Elves'], [])
    source = put(s, name, 'hand')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    hidden = put(s, 'Forest', 'hand', 'p2')
    start(s)
    mana(s, C=8, B=3, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    unblocked(s, source, turn=7)
    if name != 'Master of Cruelties':
        answer79(s, True)
    assert 'assign_none' in chars(s, source).imposed
    if name == 'Master of Cruelties':
        assert s.state.players['p2'].life == 1
    elif name == 'Bone Dancer':
        assert s.state.cards[elf.id].zone == 'p1:battlefield'
    else:
        from app.game.visibility import can_see
        assert can_see(s.state, hidden, 'p1')


@pytest.mark.parametrize('name', NAMES)
def test_battle_defending_player_is_protector_not_controller(cards, name):
    from tests.test_rules_unblocked_riders32 import unblocked
    s = table(cards, [c['name'] for c in DATA], ['Forest', 'Llanowar Elves'], [])
    source = put(s, name, 'battlefield')
    siege = put(s, 'Invasion of Zendikar // Awakened Skyclave', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[siege.id], kind='defense', delta=4)
    hidden = put(s, 'Forest', 'hand', 'p2')
    elf = put(s, 'Llanowar Elves', 'graveyard', 'p2')
    start(s)
    assert s.state.rules.protectors[s.state.rules.object_id(siege.id)] == 'p2'
    unblocked(s, source, defender=siege.id)
    assert s.state.players['p2'].life == 40
    if name == 'Master of Cruelties':
        assert s.state.rules.decision is None
        assert 'assign_none' not in chars(s, source).imposed
    else:
        answer79(s, True)
        assert 'assign_none' in chars(s, source).imposed
        if name == 'Bone Dancer':
            assert s.state.cards[elf.id].zone == 'p1:battlefield'
        else:
            from app.game.visibility import can_see
            assert can_see(s.state, hidden, 'p1')
