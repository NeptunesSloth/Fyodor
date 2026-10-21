"""Clockwork combats and optional recharge counters respect exact combat and final ceilings."""
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
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/clockwork_counter_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()





NAMES = ['Clockwork Steed', 'Clockwork Beast', 'Clockwork Avian', 'Clockwork Swarm']


def setup(cards, name='Clockwork Steed'):
    s = table(cards, [name, 'Relentless Assault', 'Reconnaissance', 'Doubling Season', 'Vorinclex, Monstrous Raider', 'Daredevil Dragster', 'Grizzly Bears'],
              ['Grizzly Bears', 'Stifle', 'Vorinclex, Monstrous Raider'], ['Grizzly Bears'])
    source = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 10})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+0') == (7 if name == 'Clockwork Beast' else 4)
    act(s, 'p1', type='next_turn', player='p1', force=True)
    return s, source


def combat(s, source=None):
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}] if source else [])
    to_phase(s, 'end_combat')
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_full_and_declared_attack_loses_one_counter_at_end_combat(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
    s, source = setup(cards, name)
    before = s.state.cards[source.id].counters['+1/+0']
    combat(s, source)
    assert s.state.cards[source.id].counters['+1/+0'] == before - 1
    roundtrip(s)


def test_nonparticipating_creature_keeps_all_counters(cards):
    s, source = setup(cards)
    combat(s)
    assert s.state.cards[source.id].counters['+1/+0'] == 4
    roundtrip(s)


def recharge(s, source, x):
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'upkeep')
    if x:
        act(s, 'p1', type='add_mana', player='p1', mana={'C': x})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Put up to X'), x_value=x, sources=[])
    until_asked(s)


def number(s, n):
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'capped_counters'
    act(s, d.player, type='choose', decision_id=d.id, name=str(n))


@pytest.mark.parametrize('n', [0, 1, 2])
def test_upkeep_recharge_may_choose_less_than_x_and_cannot_exceed_ceiling(cards, n):
    s, source = setup(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+0', delta=-2)
    recharge(s, source, 3)
    roundtrip(s)
    number(s, n)
    settle(s)
    assert s.state.cards[source.id].counters['+1/+0'] == 2 + n
    assert s.state.cards[source.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('already', [4, 6])
def test_recharge_does_nothing_when_already_at_or_over_cap(cards, already):
    s, source = setup(cards)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='+1/+0', value=already)
    recharge(s, source, 3)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].counters['+1/+0'] == already
    assert s.state.cards[source.id].tapped
    roundtrip(s)


def test_replacement_doubling_cannot_push_total_above_ability_ceiling(cards):
    s, source = setup(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+0', delta=-1)
    put(s, 'Doubling Season', 'battlefield')
    recharge(s, source, 3)
    number(s, 1)
    settle(s)
    assert s.state.cards[source.id].counters['+1/+0'] == 4
    roundtrip(s)


def test_upkeep_restriction_is_enforced(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards)
    to_phase(s, 'main1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Put up to X'), x_value=0, sources=[])
    assert not s.state.cards[source.id].tapped


def test_actual_daredevil_dragster_attacks_twice_then_sacrifices_and_draws(cards):
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    s, clock = setup(cards)
    vehicle = put(s, 'Daredevil Dragster', 'battlefield')
    act(s, 'p1', type='next_turn', player='p1', force=True)
    for attack in (1, 2):
        to_phase(s, 'main1')
        act(s, 'p1', type='activate_ability', card_id=vehicle.id, ability=ability_index(s, vehicle, 'Crew'), crew=[clock.id])
        settle(s)
        before = len(s.state.zones['p1:hand'])
        combat(s, vehicle)
        assert s.state.cards[clock.id].counters['+1/+0'] == 4  # crewing did not attack or block
        if attack == 1:
            assert s.state.cards[vehicle.id].counters.get('velocity') == 1
            act(s, 'p1', type='next_turn', player='p1', force=True)
        else:
            assert s.state.cards[vehicle.id].zone == 'p1:graveyard'
            assert len(s.state.zones['p1:hand']) == before + 2
        roundtrip(s)


def test_declared_blocker_loses_counter_at_end_of_opponents_combat(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='next_turn', player='p2', force=True)
    act(s, 'p2', type='pass_priority')
    to_phase(s, 'declare_attackers')
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p1'}])
    to_phase(s, 'declare_blockers')
    act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': source.id, 'attacker_id': attacker.id}])
    roundtrip(s)
    to_phase(s, 'end_combat')
    settle(s)
    assert s.state.cards[source.id].counters['+1/+0'] == 3
    roundtrip(s)


def test_second_combat_does_not_reuse_first_combats_attack_history(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards)
    combat(s, source)
    assert s.state.cards[source.id].counters['+1/+0'] == 3
    to_phase(s, 'main2')
    spell = put(s, 'Relentless Assault', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 2, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    settle(s)
    combat(s)
    assert s.state.cards[source.id].counters['+1/+0'] == 3
    assert s.state.rules.combats >= 2
    roundtrip(s)


def test_removing_attacker_from_combat_does_not_erase_its_declaration(cards):
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards)
    enchantment = put(s, 'Reconnaissance', 'battlefield')
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    act(s, 'p1', type='activate_ability', card_id=enchantment.id, ability=ability_index(s, enchantment, 'Remove target'), targets=[source.id])
    settle(s)
    assert not s.state.cards[source.id].attacking
    to_phase(s, 'end_combat')
    settle(s)
    assert s.state.cards[source.id].counters['+1/+0'] == 3
    roundtrip(s)


def test_new_object_after_blink_did_not_attack_in_this_combat(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards)
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='set_counter', card_id=source.id, kind='+1/+0', value=4)
    to_phase(s, 'end_combat')
    settle(s)
    assert s.state.cards[source.id].counters['+1/+0'] == 4
    roundtrip(s)


def test_replacement_order_pause_preserves_chosen_amount_and_final_ceiling(cards):
    totals = set()
    for answer in ('yes', 'no'):
        s, source = setup(cards)
        act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+0', delta=-1)
        put(s, 'Doubling Season', 'battlefield')
        put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
        recharge(s, source, 3)
        number(s, 1)
        d = s.state.rules.decision
        assert d and {o.id for o in d.options} == {'yes', 'no'}
        assert s.state.cards[source.id].counters['+1/+0'] == 3
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[answer])
        settle(s)
        totals.add(s.state.cards[source.id].counters['+1/+0'])
        assert s.state.rules.decision is None
        roundtrip(s)
    assert totals == {3, 4}


def test_number_choice_resumes_in_fresh_python_process(cards, tmp_path):
    import subprocess
    import sys
    s, source = setup(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+0', delta=-2)
    recharge(s, source, 3)
    saved = tmp_path / 'clockwork.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.rules import coverage
from app.game.session import GameSession
from app.game.state import GameState
state_path, database, target = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state_path).read_text()), cards=repo)
d = s.state.rules.decision
assert d.resume['step'] == 'capped_counters'
s.perform(d.player, {'type':'choose', 'decision_id':d.id, 'name':'2'})
assert s.state.cards[target].counters['+1/+0'] == 4
assert s.state.rules.decision is None
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json()).model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_invalid_number_is_atomic_and_put_no_counters_is_available(cards):
    from app.game.errors import ActionError
    s, source = setup(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+0', delta=-2)
    recharge(s, source, 3)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        number(s, 999999999)
    assert s.state.model_dump(mode='json') == before
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, name='pass')
    assert s.state.cards[source.id].counters['+1/+0'] == 2
    roundtrip(s)


def test_zero_x_does_not_offer_counters(cards):
    s, source = setup(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+0', delta=-2)
    recharge(s, source, 0)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].counters['+1/+0'] == 2
    assert s.state.cards[source.id].tapped
    roundtrip(s)


def test_blinked_source_does_not_receive_old_recharge_counters(cards):
    s, source = setup(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+0', delta=-2)
    recharge(s, source, 3)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    number(s, 2)
    settle(s)
    assert not s.state.cards[source.id].counters.get('+1/+0')
    roundtrip(s)


def test_counter_reduction_can_make_a_choice_larger_than_remaining_room_legal(cards):
    s, source = setup(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+0', delta=-1)
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    recharge(s, source, 3)
    number(s, 3)  # one room remains, but three chosen becomes one after replacement
    settle(s)
    assert s.state.cards[source.id].counters['+1/+0'] == 4
    roundtrip(s)
