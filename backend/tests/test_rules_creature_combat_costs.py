"""Canonical self/Aura attack and block costs use real declaration payments."""
from __future__ import annotations

import json
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack, block

NAMES = ['Qal Sisma Behemoth', 'Oppressive Rays', 'Cowed by Wisdom', 'Myr Prototype', 'Whipgrass Entangler']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/creature_combat_cost_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ccc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [*NAMES, 'Grizzly Bears', 'Azure Mage', 'Llanowar Elves', 'Soul Warden', 'Phyrexian Altar', 'Memnite', 'Dress Down', 'Disenchant', 'Fumiko the Lowblood', 'Lure', 'High Ground', 'Lightning Bolt']
    s = table(cards, names, names, ['Soul Warden', 'Grizzly Bears'])
    hand = list(s.state.zones.get('p1:hand', []))
    if hand:
        act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'library'}, position='bottom')
    return s


def aura(s, name, target):
    spell = put(s, name, 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[spell.id].attached_to == target.id
    return spell


def current_cost(s, *creatures):
    from app.rules import creature_combat_costs

    return creature_combat_costs.total(Plan(s.state, 'p2', s.cards, None), [c.id for c in creatures]).generic


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('defender', ['p1', 'p3'])
def test_qal_sisma_attack_cost_applies_regardless_of_defender(cards, defender):
    s = setup(cards)
    qal = put(s, 'Qal Sisma Behemoth', 'battlefield', pid='p2')
    to_phase(s, 'declare_attackers', turn=2)
    with pytest.raises(ActionError):
        attack(s, (qal, defender), pid='p2')
    assert s.state.cards[qal.id].attacking is None
    mana(s, pid='p2', C=2)
    attack(s, (qal, defender), pid='p2')
    assert s.state.cards[qal.id].attacking is not None
    assert mana_pool(s, 'p2') == {}
    roundtrip(s)


def test_qal_sisma_block_cost_and_unpaid_declaration_rollback(cards):
    s = setup(cards)
    qal = put(s, 'Qal Sisma Behemoth', 'battlefield', pid='p2')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (bear, 'p2'))
    to_phase(s, 'declare_blockers', turn=4)
    with pytest.raises(ActionError):
        block(s, 'p2', (qal, bear))
    assert not s.state.cards[qal.id].blocking
    mana(s, pid='p2', C=2)
    block(s, 'p2', (qal, bear))
    assert s.state.cards[qal.id].blocking
    assert mana_pool(s, 'p2') == {}
    roundtrip(s)


@pytest.mark.parametrize(('name', 'cost'), [('Oppressive Rays', 3), ('Cowed by Wisdom', 2)])
def test_actual_aura_taxes_host_attack(cards, name, cost):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    aura(s, name, bear)
    if name == 'Cowed by Wisdom':
        act(s, 'p1', type='draw', count=2)
    assert current_cost(s, bear) == cost
    to_phase(s, 'declare_attackers', turn=2)
    with pytest.raises(ActionError):
        attack(s, (bear, 'p3'), pid='p2')
    mana(s, pid='p2', C=cost)
    attack(s, (bear, 'p3'), pid='p2')
    assert s.state.cards[bear.id].attacking is not None and mana_pool(s, 'p2') == {}
    roundtrip(s)


def test_cowed_counts_aura_controllers_hand_and_updates_when_control_changes(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    enchantment = aura(s, 'Cowed by Wisdom', bear)
    assert current_cost(s, bear) == 0
    act(s, 'p1', type='draw', count=2)
    assert current_cost(s, bear) == 2
    act(s, 'p3', type='draw', count=3)
    act(s, 'p3', type='set_controller', card_ids=[enchantment.id], player='p3')
    assert current_cost(s, bear) == 3
    to_phase(s, 'declare_attackers', turn=2)
    mana(s, pid='p2', C=2)
    with pytest.raises(ActionError):
        attack(s, (bear, 'p1'), pid='p2')
    mana(s, pid='p2', C=1)
    attack(s, (bear, 'p1'), pid='p2')
    assert mana_pool(s, 'p2') == {}
    roundtrip(s)


@pytest.mark.parametrize('count', [0, 3])
def test_myr_upkeep_counter_and_dynamic_per_counter_attack_cost(cards, count):
    s = setup(cards)
    myr = put(s, 'Myr Prototype', 'battlefield', pid='p2')
    to_phase(s, 'main1', turn=2)
    settle(s)
    assert s.state.cards[myr.id].counters.get('+1/+1') == 1
    act(s, 'p2', type='set_counter', card_id=myr.id, kind='+1/+1', value=count)
    assert current_cost(s, myr) == count
    to_phase(s, 'declare_attackers', turn=2)
    if count:
        with pytest.raises(ActionError):
            attack(s, (myr, 'p1'), pid='p2')
        mana(s, pid='p2', C=count)
    attack(s, (myr, 'p1'), pid='p2')
    assert s.state.cards[myr.id].attacking is not None
    roundtrip(s)


@pytest.mark.parametrize('copies', [1, 2])
def test_whipgrass_real_granted_static_counts_all_clerics_and_stacks_distinct_instances(cards, copies):
    s = setup(cards)
    entangler = put(s, 'Whipgrass Entangler', 'battlefield')
    put(s, 'Soul Warden', 'battlefield', pid='p3')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    to_phase(s, 'begin_combat', turn=2)
    for _ in range(copies):
        wait_priority(s, 'p1')
        mana(s, W=1, C=1)
        act(s, 'p1', type='activate_ability', card_id=entangler.id, ability=0, targets=[bear.id])
        settle(s)
    assert current_cost(s, bear) == 2 * copies
    to_phase(s, 'declare_attackers', turn=2)
    with pytest.raises(ActionError):
        attack(s, (bear, 'p1'), pid='p2')
    mana(s, pid='p2', C=2 * copies)
    attack(s, (bear, 'p1'), pid='p2')
    assert mana_pool(s, 'p2') == {}
    roundtrip(s)


def test_oppressive_rays_taxes_actual_nonmana_activation_of_host_only(cards):
    s = setup(cards)
    mage = put(s, 'Azure Mage', 'battlefield', pid='p2')
    aura(s, 'Oppressive Rays', mage)
    wait_priority(s, 'p2')
    mana(s, pid='p2', U=1, C=3)
    with pytest.raises(ActionError):
        act(s, 'p2', type='activate_ability', card_id=mage.id, ability=0)
    assert mana_pool(s, 'p2') == {'U': 1, 'C': 3}
    mana(s, pid='p2', C=3)
    before = len(s.state.zones.get('p2:hand', []))
    act(s, 'p2', type='activate_ability', card_id=mage.id, ability=0)
    settle(s)
    assert len(s.state.zones.get('p2:hand', [])) == before + 1
    assert mana_pool(s, 'p2') == {}
    roundtrip(s)


def test_oppressive_rays_taxes_actual_mana_activation(cards):
    s = setup(cards)
    elf = put(s, 'Llanowar Elves', 'battlefield', pid='p2')
    aura(s, 'Oppressive Rays', elf)
    to_phase(s, 'main1', turn=2)
    with pytest.raises(ActionError):
        act(s, 'p2', type='activate_ability', card_id=elf.id, ability=0)
    assert not s.state.cards[elf.id].tapped and mana_pool(s, 'p2') == {}
    mana(s, pid='p2', C=3)
    act(s, 'p2', type='activate_ability', card_id=elf.id, ability=0)
    assert s.state.cards[elf.id].tapped
    assert mana_pool(s, 'p2') == {'G': 1}
    roundtrip(s)


def test_losing_creature_abilities_removes_self_cost_but_keeps_auras_cost(cards):
    s = setup(cards)
    qal = put(s, 'Qal Sisma Behemoth', 'battlefield', pid='p2')
    aura(s, 'Oppressive Rays', qal)
    assert current_cost(s, qal) == 5
    to_phase(s, 'begin_combat', turn=2)
    wait_priority(s, 'p1')
    dress = put(s, 'Dress Down', 'hand')
    mana(s, U=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=dress.id, targets=[])
    settle(s)
    assert current_cost(s, qal) == 3
    to_phase(s, 'declare_attackers', turn=2)
    mana(s, pid='p2', C=3)
    attack(s, (qal, 'p1'), pid='p2')
    assert mana_pool(s, 'p2') == {}
    roundtrip(s)


def test_actual_disenchant_removes_aura_cost(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    enchantment = aura(s, 'Oppressive Rays', bear)
    to_phase(s, 'begin_combat', turn=2)
    wait_priority(s, 'p1')
    removal = put(s, 'Disenchant', 'hand')
    mana(s, W=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[enchantment.id])
    settle(s)
    assert current_cost(s, bear) == 0
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (bear, 'p1'), pid='p2')
    assert s.state.cards[bear.id].attacking is not None
    roundtrip(s)


def test_attack_requirement_never_forces_payment_even_with_mana_available(cards):
    s = setup(cards)
    put(s, 'Fumiko the Lowblood', 'battlefield')
    qal = put(s, 'Qal Sisma Behemoth', 'battlefield', pid='p2')
    to_phase(s, 'declare_attackers', turn=2)
    mana(s, pid='p2', C=2)
    act(s, 'p2', type='declare_attackers', attackers=[])
    assert s.state.cards[qal.id].attacking is None
    assert mana_pool(s, 'p2') == {'C': 2}
    roundtrip(s)


def test_lure_requirement_never_forces_block_cost_payment(cards):
    s = setup(cards)
    qal = put(s, 'Qal Sisma Behemoth', 'battlefield', pid='p2')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    lure = put(s, 'Lure', 'hand')
    mana(s, G=2, C=1)
    act(s, 'p1', type='cast_spell', card_id=lure.id, targets=[bear.id])
    settle(s)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (bear, 'p2'))
    to_phase(s, 'declare_blockers', turn=4)
    mana(s, pid='p2', C=2)
    block(s, 'p2')
    assert not s.state.cards[qal.id].blocking
    assert mana_pool(s, 'p2') == {'C': 2}
    roundtrip(s)


def test_creature_blocking_multiple_attackers_pays_self_cost_only_once(cards):
    s = setup(cards)
    qal = put(s, 'Qal Sisma Behemoth', 'battlefield', pid='p2')
    put(s, 'High Ground', 'battlefield', pid='p2')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    memnite = put(s, 'Memnite', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (bear, 'p2'), (memnite, 'p2'))
    to_phase(s, 'declare_blockers', turn=4)
    mana(s, pid='p2', C=2)
    block(s, 'p2', (qal, bear), (qal, memnite))
    assert s.state.cards[qal.id].blocks(bear.id) and s.state.cards[qal.id].blocks(memnite.id)
    assert mana_pool(s, 'p2') == {}
    roundtrip(s)


def test_whipgrass_source_leaves_granted_cost_persists_with_live_count_then_expires(cards):
    s = setup(cards)
    entangler = put(s, 'Whipgrass Entangler', 'battlefield')
    put(s, 'Soul Warden', 'battlefield', pid='p3')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    to_phase(s, 'begin_combat', turn=2)
    wait_priority(s, 'p1')
    mana(s, W=1, C=1)
    act(s, 'p1', type='activate_ability', card_id=entangler.id, ability=0, targets=[bear.id])
    settle(s)
    assert current_cost(s, bear) == 2
    wait_priority(s, 'p1')
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[entangler.id])
    settle(s)
    assert s.state.cards[entangler.id].zone == 'p1:graveyard'
    assert current_cost(s, bear) == 1
    to_phase(s, 'declare_attackers', turn=2)
    mana(s, pid='p2', C=1)
    attack(s, (bear, 'p1'), pid='p2')
    to_phase(s, 'main1', turn=3)
    assert current_cost(s, bear) == 0
    roundtrip(s)


def test_locked_attack_cost_is_still_paid_after_last_cleric_is_sacrificed_for_mana(cards):
    s = setup(cards)
    entangler = put(s, 'Whipgrass Entangler', 'battlefield', pid='p2')
    altar = put(s, 'Phyrexian Altar', 'battlefield', pid='p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    to_phase(s, 'begin_combat', turn=2)
    mana(s, pid='p2', W=1, C=1)
    act(s, 'p2', type='activate_ability', card_id=entangler.id, ability=0, targets=[bear.id])
    settle(s)
    assert current_cost(s, bear) == 1
    island = put(s, 'Island', 'battlefield', pid='p2')
    act(s, 'p2', type='set_prefs', payment='self')
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (bear, 'p1'), pid='p2')
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'pay_mana' and d.resume['cost'] == '{1}'
    act(s, 'p2', type='activate_ability', card_id=altar.id, ability=0, mana_choice='G')
    d = s.state.rules.decision
    if d and entangler.id in {o.id for o in d.options}:
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[entangler.id])
    d = s.state.rules.decision
    assert s.state.cards[entangler.id].zone == 'p2:graveyard'
    assert current_cost(s, bear) == 0
    roundtrip(s)
    if d:
        assert d.resume['step'] == 'pay_mana'
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
    assert s.state.cards[bear.id].attacking is not None
    assert mana_pool(s, 'p2') == {} and not s.state.cards[island.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('phase', ['attack', 'block'])
def test_saved_actual_combat_mana_payment_resumes_cold(cards, tmp_path, phase):
    import subprocess
    import sys

    s = setup(cards)
    qal = put(s, 'Qal Sisma Behemoth', 'battlefield', pid='p2')
    act(s, 'p2', type='set_prefs', payment='self')
    lands = [c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Island' and c.zone == 'p2:library'][:2]
    act(s, 'p2', type='move', card_ids=[c.id for c in lands], to={'player': 'p2', 'zone': 'battlefield'})
    if phase == 'attack':
        to_phase(s, 'declare_attackers', turn=2)
        attack(s, (qal, 'p1'), pid='p2')
    else:
        bear = put(s, 'Grizzly Bears', 'battlefield')
        to_phase(s, 'declare_attackers', turn=4)
        attack(s, (bear, 'p2'))
        to_phase(s, 'declare_blockers', turn=4)
        block(s, 'p2', (qal, bear))
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'pay_mana' and d.resume['cost'] == '{2}'
    act(s, 'p2', type='activate_ability', card_id=lands[0].id, ability=0)
    assert s.state.rules.decision and mana_pool(s, 'p2') == {'U': 1}
    roundtrip(s)
    saved = tmp_path / 'combat-payment.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act, mana_pool
repo = CardRepository(Path(sys.argv[2]), ImageStore(Path(sys.argv[2]).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()), cards=repo)
act(s, 'p2', type='activate_ability', card_id=sys.argv[3], ability=0)
d = s.state.rules.decision
if d:
    assert d.resume['step'] == 'pay_mana'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
assert mana_pool(s, 'p2') == {}
c = s.state.cards[sys.argv[4]]
assert c.attacking is not None if sys.argv[5] == 'attack' else bool(c.blocking)
assert s.history.state_at(s.history.cursor).model_dump() == s.state.model_dump()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), lands[1].id, qal.id, phase],
                            cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr


def test_oppressive_host_filter_and_actual_aura_removal_restore_mana_activation(cards):
    s = setup(cards)
    elf = put(s, 'Llanowar Elves', 'battlefield', pid='p2')
    other = put(s, 'Llanowar Elves', 'battlefield')
    act(s, 'p2', type='set_controller', card_ids=[other.id], player='p2')
    enchantment = aura(s, 'Oppressive Rays', elf)
    to_phase(s, 'main1', turn=2)
    act(s, 'p2', type='activate_ability', card_id=other.id, ability=0)
    assert mana_pool(s, 'p2') == {'G': 1}
    wait_priority(s, 'p1')
    removal = put(s, 'Disenchant', 'hand')
    mana(s, W=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[enchantment.id])
    settle(s)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=elf.id, ability=0)
    assert mana_pool(s, 'p2') == {'G': 2}
    roundtrip(s)


@pytest.mark.parametrize('grant_after_loss', [False, True])
def test_quoted_cost_respects_real_layer6_grant_and_ability_loss_order(cards, grant_after_loss):
    s = setup(cards)
    entangler = put(s, 'Whipgrass Entangler', 'battlefield')
    put(s, 'Soul Warden', 'battlefield', pid='p3')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    to_phase(s, 'begin_combat', turn=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, W=1, C=1)
    act(s, 'p1', type='activate_ability', card_id=entangler.id, ability=0, targets=[bear.id])
    if not grant_after_loss:
        settle(s)
        assert current_cost(s, bear) == 2
        wait_priority(s, 'p1')
    dress = put(s, 'Dress Down', 'hand')
    mana(s, U=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=dress.id, targets=[])
    settle(s)
    assert current_cost(s, bear) == (2 if grant_after_loss else 0)
    to_phase(s, 'declare_attackers', turn=2)
    if grant_after_loss:
        mana(s, pid='p2', C=2)
    attack(s, (bear, 'p1'), pid='p2')
    assert s.state.cards[bear.id].attacking is not None
    roundtrip(s)
