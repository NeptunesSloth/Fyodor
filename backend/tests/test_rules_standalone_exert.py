"""CR701.43: standalone attack exert and action-based exert observers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave5c_combat import declare, to_attack
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Rohirrim Chargers', 'Battlefield Scavenger', 'Trueheart Twins', 'Resolute Survivors', 'Vizier of the True']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/standalone_exert_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ext', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name='Resolute Survivors', extra=(), enemy=()):
    s = table(cards, [name, 'Hooded Brawler', 'Oasis Ritualist', 'Aggravated Assault', 'Twiddle', *extra], ['Grizzly Bears', *enemy], [])
    source = put(s, name, 'battlefield')
    brawler = put(s, 'Hooded Brawler', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    return s, source, brawler, enemy


def attack(s, attackers, selected):
    to_attack(s, 4)
    declare(s, *[(c, 'p2') for c in attackers])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'exert_attackers'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[c.id for c in selected])


@pytest.mark.parametrize('name', NAMES)
def test_standalone_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('exert', [False, True])
def test_standalone_exert_is_optional_and_triggers_once(cards, exert):
    s, source, _, _ = setup(cards)
    attack(s, [source], [source] if exert else [])
    settle(s)
    assert [s.state.players[p].life for p in ['p1', 'p2', 'p3']] == ([41, 39, 39] if exert else [40, 40, 40])
    assert bool(s.state.rules.exerted) == exert
    roundtrip(s)


def test_two_creatures_exert_individually_and_linked_trigger_is_not_duplicated(cards):
    s, source, brawler, _ = setup(cards)
    attack(s, [source, brawler], [source, brawler])
    settle(s)
    assert [s.state.players[p].life for p in ['p1', 'p2', 'p3']] == [42, 38, 38]
    assert Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[brawler.id]).pt == (5, 4)
    assert len(s.state.rules.exerted) == 2
    roundtrip(s)


def test_generic_observer_sees_another_creatures_existing_linked_exert(cards):
    s, source, brawler, _ = setup(cards, name='Trueheart Twins')
    attack(s, [brawler], [brawler])
    settle(s)
    plan = Plan(s.state, 'p1', s.cards, None)
    assert plan.ch(s.state.cards[source.id]).pt == (5, 4)
    assert plan.ch(s.state.cards[brawler.id]).pt == (6, 4)
    roundtrip(s)


def test_mana_ability_exert_cost_fires_observer_without_attack(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index

    s, _, _, _ = setup(cards)
    ritualist = put(s, 'Oasis Ritualist', 'battlefield')
    to_phase(s, 'main1', turn=7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=ritualist.id, ability=ability_index(s, ritualist, 'two mana'))
    settle(s)
    assert [s.state.players[p].life for p in ['p1', 'p2', 'p3']] == [41, 39, 39]
    assert s.state.cards[ritualist.id].tapped
    assert s.state.rules.exerted
    roundtrip(s)


def test_vizier_targets_opponents_creature_for_each_exert(cards):
    s, source, _, enemy = setup(cards, name='Vizier of the True')
    attack(s, [source], [source])
    settle(s)
    assert s.state.cards[enemy.id].tapped
    roundtrip(s)


def test_rohirrim_equipment_attaches_to_exact_other_exerted_creature(cards):
    s, _, brawler, _ = setup(cards, name='Rohirrim Chargers', extra=['Bonesplitter', 'Sol Ring'])
    equipment = put(s, 'Bonesplitter', 'hand')
    non = put(s, 'Sol Ring', 'hand')
    for cid in [equipment.id, non.id]:
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'library'}, position='top')
    attack(s, [brawler], [brawler])
    settle(s)
    assert s.state.cards[equipment.id].zone == 'p1:battlefield'
    assert s.state.cards[equipment.id].attached_to == brawler.id
    assert s.state.zones['p1:library'][-1] == non.id
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_scavenger_optional_discard_is_private_and_draw_requires_payment(cards, pay):
    from tests.test_rules_conditionals import until

    s, source, _, _ = setup(cards, name='Battlefield Scavenger')
    before = len(s.state.zones['p1:hand'])
    old_gy = set(s.state.zones.get('p1:graveyard', []))
    attack(s, [source], [source])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'pay_or_sacrifice')
    d = s.state.rules.decision
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if pay else 'decline'])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before
    assert len(set(s.state.zones.get('p1:graveyard', [])) - old_gy) == (1 if pay else 0)
    roundtrip(s)


def test_opponents_exert_does_not_fire_your_observer(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Resolute Survivors'], ['Oasis Ritualist'], [])
    put(s, 'Resolute Survivors', 'battlefield')
    ritualist = put(s, 'Oasis Ritualist', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=5)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=ritualist.id, ability=ability_index(s, ritualist, 'two mana'))
    settle(s)
    assert [s.state.players[p].life for p in ['p1', 'p2', 'p3']] == [40, 40, 40]
    roundtrip(s)


def test_repeated_cost_exert_fires_twice_but_skips_one_actual_untap(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index

    s, _, _, _ = setup(cards)
    ritualist = put(s, 'Oasis Ritualist', 'battlefield')
    to_phase(s, 'main1', turn=7)
    for i in range(2):
        if i:
            act(s, 'p1', type='tap', card_ids=[ritualist.id], tapped=False)
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=ritualist.id, ability=ability_index(s, ritualist, 'two mana'))
        settle(s)
    assert [s.state.players[p].life for p in ['p1', 'p2', 'p3']] == [42, 38, 38]
    assert len(s.state.rules.exerted) == 1
    to_phase(s, 'main1', turn=10)
    assert s.state.cards[ritualist.id].tapped
    to_phase(s, 'main1', turn=13)
    assert not s.state.cards[ritualist.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('reenter', [False, True])
def test_rohirrim_creature_gone_or_new_object_does_not_receive_equipment(cards, reenter):
    s, _, brawler, _ = setup(cards, name='Rohirrim Chargers', extra=['Bonesplitter'])
    equipment = put(s, 'Bonesplitter', 'hand')
    act(s, 'p1', type='move', card_ids=[equipment.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    attack(s, [brawler], [brawler])
    act(s, 'p1', type='move', card_ids=[brawler.id], to={'player': 'p1', 'zone': 'graveyard'})
    if reenter:
        act(s, 'p1', type='move', card_ids=[brawler.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert s.state.cards[equipment.id].zone == 'p1:battlefield'
    assert s.state.cards[equipment.id].attached_to is None
    roundtrip(s)


def test_rohirrim_without_equipment_randomizes_revealed_library_without_draw(cards):
    s, source, _, _ = setup(cards, name='Rohirrim Chargers')
    before = set(s.state.zones['p1:library'])
    hand = len(s.state.zones['p1:hand'])
    attack(s, [source], [source])
    settle(s)
    assert set(s.state.zones['p1:library']) == before
    assert len(s.state.zones['p1:hand']) == hand
    assert 'p1' not in s.state.rules.lost
    roundtrip(s)


def test_rohirrim_source_leaves_but_trigger_still_equips_exerted_creature(cards):
    s, source, brawler, _ = setup(cards, name='Rohirrim Chargers', extra=['Bonesplitter'])
    equipment = put(s, 'Bonesplitter', 'hand')
    act(s, 'p1', type='move', card_ids=[equipment.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    attack(s, [brawler], [brawler])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[equipment.id].attached_to == brawler.id
    roundtrip(s)


def test_exert_does_not_tap_a_vigilant_attacker(cards):
    s, source, _, _ = setup(cards, extra=['Always Watching'])
    put(s, 'Always Watching', 'battlefield')
    attack(s, [source], [source])
    settle(s)
    assert not s.state.cards[source.id].tapped
    assert s.state.players['p1'].life == 41
    assert s.state.rules.exerted
    roundtrip(s)


def test_standalone_exert_can_be_paid_again_in_an_additional_combat(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave7b_activation import ability_index

    s, source, _, _ = setup(cards)
    assault = put(s, 'Aggravated Assault', 'battlefield')
    attack(s, [source], [source])
    settle(s)
    to_phase(s, 'main2', turn=4)
    wait_priority(s, 'p1')
    mana(s, C=3, R=2)
    act(s, 'p1', type='activate_ability', card_id=assault.id, ability=ability_index(s, assault, 'Untap'))
    settle(s)
    attack(s, [source], [source])
    settle(s)
    assert s.state.players['p1'].life == 42
    assert s.state.players['p3'].life == 38
    roundtrip(s)


def test_rohirrim_no_hit_in_library_over_reveal_top_action_limit(cards):
    s = table(cards, ['Rohirrim Chargers', *(['Forest'] * 110)], [], [])
    source = put(s, 'Rohirrim Chargers', 'battlefield')
    to_phase(s, 'main1', turn=4)
    before = set(s.state.zones['p1:library'])
    assert len(before) > 100
    attack(s, [source], [source])
    settle(s)
    assert set(s.state.zones['p1:library']) == before
    assert 'p1' not in s.state.rules.lost
    roundtrip(s)


@pytest.mark.parametrize('name', ['Resolute Survivors', 'Rohirrim Chargers'])
def test_saved_exert_choice_and_generic_observer_resume_in_fresh_process(cards, tmp_path, name):
    import subprocess
    import sys

    s, source, brawler, _ = setup(cards, name=name, extra=['Bonesplitter'])
    equipment = put(s, 'Bonesplitter', 'hand')
    act(s, 'p1', type='move', card_ids=[equipment.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    attacker = brawler if name == 'Rohirrim Chargers' else source
    to_attack(s, 4)
    declare(s, (attacker, 'p2'))
    assert s.state.rules.decision.resume['step'] == 'exert_attackers'
    saved = tmp_path / 'exert-choice.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, database, attacker, equipment, kind = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
d = s.state.rules.decision
s.perform('p1', {'type':'choose','decision_id':d.id,'option_ids':[attacker]})
for _ in range(80):
    d = s.state.rules.decision
    if d is not None:
        s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[o.id for o in d.options][:max(1,d.min_choices)]})
    elif s.state.zones.get('stack'):
        s.perform(s.state.rules.priority, {'type':'pass_priority'})
    else:
        break
else:
    raise AssertionError('did not settle')
assert s.state.rules.exerted
if kind == 'Rohirrim Chargers':
    assert s.state.cards[equipment].attached_to == attacker
else:
    assert [s.state.players[p].life for p in ['p1','p2','p3']] == [41,39,39]
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), attacker.id, equipment.id, name],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_cancelled_activated_exert_proposal_does_not_pay_or_trigger(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index

    s, _, _, _ = setup(cards, extra=['Fervent Paincaster'])
    paincaster = put(s, 'Fervent Paincaster', 'battlefield')
    to_phase(s, 'main1', turn=7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=paincaster.id, ability=ability_index(s, paincaster, 'target creature'))
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'cast_target'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
    settle(s)
    assert not s.state.cards[paincaster.id].tapped
    assert not s.state.rules.exerted
    assert [s.state.players[p].life for p in ['p1', 'p2', 'p3']] == [40, 40, 40]
    roundtrip(s)


def test_countering_activated_ability_does_not_undo_paid_exert_event(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave7b_activation import ability_index

    s, _, _, enemy = setup(cards, extra=['Fervent Paincaster'], enemy=['Stifle'])
    paincaster = put(s, 'Fervent Paincaster', 'battlefield')
    stifle = put(s, 'Stifle', 'hand', 'p2')
    to_phase(s, 'main1', turn=7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=paincaster.id,
        ability=ability_index(s, paincaster, 'target creature'), targets=[enemy.id])
    ability = next(cid for cid in s.state.zones['stack'] if s.state.cards[cid].ability is not None
                   and s.state.cards[cid].name == paincaster.name)
    wait_priority(s, 'p2')
    mana(s, pid='p2', U=1)
    act(s, 'p2', type='cast_spell', card_id=stifle.id, targets=[ability])
    settle(s)
    assert s.state.cards[enemy.id].damage == 0
    assert s.state.cards[paincaster.id].tapped and s.state.rules.exerted
    assert [s.state.players[p].life for p in ['p1', 'p2', 'p3']] == [41, 39, 39]
    roundtrip(s)
