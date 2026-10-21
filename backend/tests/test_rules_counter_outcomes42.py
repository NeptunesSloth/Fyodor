"""Canonical counter outcomes, exact recipient receipts and saved native continuations."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_linked_aggregates import activate, cast
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/counter_outcomes42_cards.json').read_text())
NAMES = [c['name'] for c in DATA]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='cmv', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, names=NAMES):
    return table(cards, names, names, names)


def counters(s, c, kind='+1/+1'):
    return s.state.cards[c.id].counters.get(kind, 0)


@pytest.mark.parametrize('overload', [False, True])
@pytest.mark.parametrize('barrier,expected', [(None, 1), ('Solemnity', 0), ('Vorinclex, Monstrous Raider', 0), ('Doubling Season', 2)])
def test_actual_showdown_receipt_goads_only_actual_recipients(cards, overload, barrier, expected):
    from app.rules import keyword_actions

    s = setup(cards, ['Spectacular Showdown', 'Grizzly Bears', 'Solemnity', 'Vorinclex, Monstrous Raider', 'Doubling Season'])
    source = put(s, 'Spectacular Showdown', 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    if barrier:
        put(s, barrier, 'battlefield', pid='p2' if barrier == 'Vorinclex, Monstrous Raider' else 'p1')
    cast(s, source, targets=[] if overload else [bear.id], alt_cost=f'{source.id}:1' if overload else None)
    settle(s)
    roundtrip(s)
    for obj, n in [(bear, expected), (other, (1 if barrier == 'Doubling Season' else expected) if overload else 0)]:
        assert counters(s, obj, 'double strike') == n
        assert ('p1' in keyword_actions.goaded_by(Plan(s.state, 'p1', cards, None).ch(s.state.cards[obj.id]))) == bool(n)


def test_showdown_full(cards):
    assert coverage.of_card_data(cards.resolve('Spectacular Showdown')).level == 'FULL'


def test_gatewatch_full(cards):
    result = coverage.of_card_data(cards.resolve('Gatewatch Beacon'))
    assert result.level == 'FULL', [(f.label, f.supported) for f in result.features]


@pytest.mark.parametrize('first,expected', [('Doubling Season', 1), ('Vorinclex', 0)])
def test_showdown_cold_616_receipt(first, expected, cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards, ['Spectacular Showdown', 'Grizzly Bears', 'Doubling Season', 'Vorinclex, Monstrous Raider'])
    source = put(s, 'Spectacular Showdown', 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    cast(s, source, targets=[bear.id])
    settle(s)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'showdown.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from app.rules import effects, keyword_actions
state, db, target, first, expected = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state).read_text()), cards=repo)
d = s.state.rules.decision
option = next(o for o in d.options if first in o.label)
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [option.id]})
for _ in range(30):
    assert s.state.rules.decision is None
    if not s.state.rules.stack: break
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert s.state.cards[target].counters.get('double strike', 0) == int(expected)
assert ('p1' in keyword_actions.goaded_by(Plan(s.state, 'p1', repo, None).ch(s.state.cards[target]))) == bool(int(expected))
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), bear.id, first, str(expected)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('accept', [False, True])
def test_actual_gatewatch_enters_mana_and_optional_loyalty_transfer(cards, accept):
    s = setup(cards, ['Gatewatch Beacon', 'Test Walker Card'])
    beacon = put(s, 'Gatewatch Beacon', 'hand')
    cast(s, beacon)
    settle(s)
    assert counters(s, beacon, 'loyalty') == 3
    before = s.state.players['p1'].mana.get('W', 0)
    activate(s, beacon, ability=1)
    settle(s)
    assert s.state.players['p1'].mana.get('W', 0) > before
    walker = put(s, 'Test Walker Card', 'hand')
    cast(s, walker)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    option = next(o for o in d.options if o.id == ('yes' if accept else 'no'))
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    settle(s)
    assert counters(s, beacon, 'loyalty') == 3 - int(accept)
    assert counters(s, walker, 'loyalty') == 3 + int(accept)
    roundtrip(s)


def test_maze_full(cards):
    result = coverage.of_card_data(cards.resolve('Lost in the Maze'))
    assert result.level == 'FULL', [(f.label, f.supported) for f in result.features]


@pytest.mark.parametrize('already_tapped', [False, True])
def test_actual_maze_cast_x_taps_all_but_stuns_only_opponents(cards, already_tapped):
    s = setup(cards, ['Lost in the Maze', 'Grizzly Bears'])
    own = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    if already_tapped:
        act(s, 'p1', type='tap', card_ids=[other.id], tapped=True)
    maze = put(s, 'Lost in the Maze', 'hand')
    cast(s, maze, x_value=2)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[own.id, other.id])
    settle(s)
    assert s.state.cards[own.id].tapped and s.state.cards[other.id].tapped
    assert counters(s, own, 'stun') == 0 and counters(s, other, 'stun') == 1
    assert 'hexproof' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[own.id]).keywords
    roundtrip(s)


def test_conformer_full(cards):
    result = coverage.of_card_data(cards.resolve('Conformer Shuriken'))
    assert result.level == 'FULL', [(f.label, f.supported) for f in result.features]


@pytest.mark.parametrize('opponent_bonus,expected', [(0, 0), (3, 3)])
def test_actual_conformer_equips_attacks_and_uses_current_power(cards, opponent_bonus, expected):
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['Conformer Shuriken', 'Grizzly Bears'])
    bearer = put(s, 'Grizzly Bears', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    equipment = put(s, 'Conformer Shuriken', 'hand')
    cast(s, equipment)
    settle(s)
    activate(s, equipment, ability=1, targets=[bearer.id])
    settle(s)
    assert s.state.cards[equipment.id].attached_to == bearer.id
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (bearer, 'p2'))
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[victim.id])
    if opponent_bonus:
        act(s, 'p1', type='counter', card_ids=[victim.id], kind='+1/+1', delta=opponent_bonus)
    settle(s)
    assert s.state.cards[victim.id].tapped
    assert counters(s, bearer) == expected
    roundtrip(s)


@pytest.mark.parametrize('name', ['Sanctuary Warden', 'Dyadrine, Synthesis Amalgam'])
def test_counter_payment_cards_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', [(f.label, f.supported) for f in result.features]


def test_actual_warden_optional_any_kind_cost_draw_and_citizen(cards):
    s = setup(cards, ['Sanctuary Warden', 'Test Walker Card'])
    walker = put(s, 'Test Walker Card', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=3)
    warden = put(s, 'Sanctuary Warden', 'hand')
    cast(s, warden)
    settle(s)
    assert counters(s, warden, 'shield') == 2
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'counter_payment42'
    hand = len(s.state.zones['p1:hand'])
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    assert d is not None
    choice = next(o for o in d.options if o.card_id == walker.id and 'loyalty' in o.label)
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[choice.id])
    settle(s)
    assert counters(s, walker, 'loyalty') == 2
    assert counters(s, warden, 'shield') == 2
    assert len(s.state.zones['p1:hand']) == hand + 1
    citizens = [c for c in s.state.cards.values() if c.token and c.name == 'Citizen' and c.zone.endswith(':battlefield')]
    assert len(citizens) == 1
    ch = Plan(s.state, 'p1', cards, None).ch(citizens[0])
    assert ch.pt == (1, 1) and set(ch.colors) == {'G', 'W'}
    roundtrip(s)


def test_actual_dyadrine_cast_mana_and_atomic_two_distinct_creature_payment(cards, tmp_path):
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['Dyadrine, Synthesis Amalgam', 'Grizzly Bears'])
    source = put(s, 'Dyadrine, Synthesis Amalgam', 'hand')
    cast(s, source, x_value=3)
    settle(s)
    assert counters(s, source) == 5
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=1)
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (bear, 'p2'))
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'counter_payment42'
    hand = len(s.state.zones['p1:hand'])
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    assert d is not None and d.min_choices == d.max_choices == 2
    selected = [o.id for o in d.options if o.card_id in [source.id, bear.id]]
    assert len(selected) == 2
    cold_finish(s, cards, tmp_path, [selected],
                f"assert s.state.cards[{source.id!r}].counters['+1/+1'] == 4\n"
                f"assert s.state.cards[{bear.id!r}].counters.get('+1/+1', 0) == 0\n"
                "assert len([c for c in s.state.cards.values() if c.token and c.name == 'Robot']) == 1")
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=selected)
    settle(s)
    assert counters(s, source) == 4 and counters(s, bear) == 0
    assert len(s.state.zones['p1:hand']) == hand + 1
    robots = [c for c in s.state.cards.values() if c.token and c.name == 'Robot' and c.zone.endswith(':battlefield')]
    assert len(robots) == 1 and Plan(s.state, 'p1', cards, None).ch(robots[0]).pt == (2, 2)
    roundtrip(s)


def test_froghemoth_full(cards):
    result = coverage.of_card_data(cards.resolve('Froghemoth'))
    assert result.level == 'FULL', [(f.label, f.supported) for f in result.features]


@pytest.mark.parametrize('depart', [False, True])
@pytest.mark.parametrize('modifier', [None, 'Solemnity', 'Doubling Season'])
def test_actual_froghemoth_haste_damage_gy_cap_and_independent_outcomes(cards, modifier, depart):
    from tests.test_rules_wave5c_combat import declare, to_attack

    s = setup(cards, ['Froghemoth', 'Grizzly Bears', 'Forest', 'Naturalize', 'Nesting Grounds', 'Resourceful Defense', 'Solemnity', 'Doubling Season'])
    source = put(s, 'Froghemoth', 'hand')
    creature = put(s, 'Grizzly Bears', 'graveyard', pid='p2')
    land = put(s, 'Forest', 'graveyard', pid='p2')
    spare = put(s, 'Naturalize', 'graveyard', pid='p2')
    extra = [put(s, name, 'graveyard', pid='p2') for name in ['Nesting Grounds', 'Resourceful Defense']]
    wrong = put(s, 'Forest', 'graveyard', pid='p3')
    if modifier:
        put(s, modifier, 'battlefield')
    cast(s, source)
    settle(s)
    to_attack(s)
    declare(s, (source, 'p2'))
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
        elif d is not None and d.kind == 'order':
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
        elif d is not None:
            break
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0 and d.max_choices == 4
    assert {o.id for o in d.options} == {creature.id, land.id, spare.id, *(c.id for c in extra)}
    assert wrong.id not in {o.id for o in d.options}
    before = s.state.players['p1'].life
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[creature.id, land.id])
    if depart:
        act(s, 'p2', type='move', card_ids=[creature.id], to={'zone': 'hand'})
    settle(s)
    assert s.state.cards[creature.id].zone.endswith(':hand' if depart else ':exile') and s.state.cards[land.id].zone.endswith(':exile')
    assert s.state.cards[spare.id].zone.endswith(':graveyard')
    assert counters(s, source) == (0 if depart or modifier == 'Solemnity' else 2 if modifier == 'Doubling Season' else 1)
    assert s.state.players['p1'].life == before + 1
    roundtrip(s)


@pytest.mark.parametrize('name', ['Elspeth Conquers Death', 'Call of the Death-Dweller'])
def test_returned_counter_cards_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', [(f.label, f.supported) for f in result.features]


def test_chandra_full(cards):
    result = coverage.of_card_data(cards.resolve('Chandra, Legacy of Fire'))
    assert result.level == 'FULL', [(f.label, f.supported) for f in result.features]


@pytest.mark.parametrize('split', [False, True])
def test_actual_call_returns_total_mv_three_then_independent_counter_recipients(cards, split, tmp_path):
    s = setup(cards, ['Call of the Death-Dweller', 'Grizzly Bears', 'Llanowar Elves'])
    bear = put(s, 'Grizzly Bears', 'graveyard')
    elf = put(s, 'Llanowar Elves', 'graveyard')
    source = put(s, 'Call of the Death-Dweller', 'hand')
    cast(s, source, targets=[bear.id, elf.id], target_counts=[2])
    settle(s)
    assert s.state.cards[bear.id].zone.endswith(':battlefield') and s.state.cards[elf.id].zone.endswith(':battlefield')
    if not split:
        cold_finish(s, cards, tmp_path, [[bear.id], [bear.id]],
                    f"assert s.state.cards[{bear.id!r}].counters['deathtouch'] == 1\n"
                    f"assert s.state.cards[{bear.id!r}].counters['menace'] == 1")
    for kind, target in [('deathtouch', bear), ('menace', elf if split else bear)]:
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'returned_counter_choice42'
        assert {o.id for o in d.options} == {bear.id, elf.id}
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
        settle(s)
        assert counters(s, target, kind) == 1
    assert s.state.rules.decision is None
    roundtrip(s)


def test_actual_call_rejects_excess_total_mv_and_zero_targets_has_no_counter_choices(cards):
    from app.game.errors import ActionError

    s = setup(cards, ['Call of the Death-Dweller', 'Grizzly Bears', 'Tatterkite'])
    bear = put(s, 'Grizzly Bears', 'graveyard')
    kite = put(s, 'Tatterkite', 'graveyard')
    source = put(s, 'Call of the Death-Dweller', 'hand')
    with pytest.raises(ActionError):
        cast(s, source, targets=[bear.id, kite.id], target_counts=[2])
    cast(s, source, targets=[], target_counts=[0])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].zone.endswith(':graveyard') and s.state.cards[kite.id].zone.endswith(':graveyard')
    roundtrip(s)


def test_rise_full(cards):
    result = coverage.of_card_data(cards.resolve('Rise and Shine'))
    assert result.level == 'FULL', [(f.label, f.supported) for f in result.features]


@pytest.mark.parametrize('kind', ['+1/+1', 'loyalty'])
def test_actual_ecd_three_natural_chapters_tax_and_post_return_kind(cards, kind, tmp_path):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['Elspeth Conquers Death', 'Tatterkite', 'Grizzly Bears', 'The Ozolith', 'Naturalize'])
    victim = put(s, 'Tatterkite', 'battlefield', pid='p2')
    dead = put(s, 'Grizzly Bears', 'graveyard')
    saga = put(s, 'Elspeth Conquers Death', 'hand')
    cast(s, saga)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and victim.id in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone.endswith(':exile')
    to_phase(s, 'main1', turn=4)
    settle(s)
    assert counters(s, saga, 'lore') == 2
    modifiers = s.state.rules.cost_modifiers
    assert len(modifiers) == 1 and modifiers[0].caster == 'opponent' and modifiers[0].delta == 2
    artifact = put(s, 'The Ozolith', 'battlefield')
    removal = put(s, 'Naturalize', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 3, 'G': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=removal.id, targets=[artifact.id], sources=[])
    receipt = next(p for p in s.state.rules.payments.values() if p.card == removal.id)
    assert sum(receipt.mana_spent.values()) == 4
    settle(s)
    to_phase(s, 'main1', turn=7)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[dead.id])
    settle(s)
    assert s.state.cards[dead.id].zone.endswith(':battlefield')
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'+1/+1', 'loyalty'}
    cold_finish(s, cards, tmp_path, [[kind]], f"assert s.state.cards[{dead.id!r}].counters[{kind!r}] == 1")
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[kind])
    settle(s)
    assert counters(s, dead, kind) == 1 and s.state.cards[saga.id].zone.endswith(':graveyard')
    assert not s.state.rules.cost_modifiers
    roundtrip(s)


def test_actual_chandra_all_lines_removed_loyalty_packet_and_paid_play(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['Chandra, Legacy of Fire', 'Test Walker Card', 'The Ozolith', 'Grizzly Bears', 'Forest'])
    source = put(s, 'Chandra, Legacy of Fire', 'hand')
    cast(s, source)
    settle(s)
    walker = put(s, 'Test Walker Card', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=3)
    artifact = put(s, 'The Ozolith', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=artifact.id, kind='loyalty', value=1)
    creature = put(s, 'Grizzly Bears', 'hand')
    land = put(s, 'Forest', 'hand')
    for obj in [creature, land]:
        act(s, 'p1', type='move', card_ids=[obj.id], to={'zone': 'library'}, position='top')
    activate(s, source, ability=2)
    settle(s)
    while (d := s.state.rules.decision) is not None:
        assert d.resume['step'] == 'choose_group_counters'
        row = d.resume['ctx']['_group_counter_choices'][str(d.resume['ctx']['next'] - 1)]['rows'][
            len(d.resume['ctx']['_group_counter_choices'][str(d.resume['ctx']['next'] - 1)]['choices'])]
        number = '0' if row['card'] == walker.id else '1'
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, name=number)
        settle(s)
    assert counters(s, walker, 'loyalty') == 3 and counters(s, artifact, 'loyalty') == 0
    assert s.state.cards[creature.id].zone.endswith(':exile') and s.state.cards[land.id].zone.endswith(':exile')
    act(s, 'p1', type='play_land', card_id=land.id)
    cast(s, creature)
    settle(s)
    assert s.state.cards[creature.id].zone.endswith(':battlefield')
    payment = next(p for p in s.state.rules.payments.values() if p.card == creature.id)
    assert sum(payment.mana_spent.values()) == 2
    before = s.state.players['p2'].life
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.players['p2'].life == before - 2
    to_phase(s, 'main1', turn=4)
    wait_priority(s, 'p1')
    from app.rules import mana_units

    before = mana_units.visible_pool(s.state, 'p1').get('R', 0)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    assert mana_units.visible_pool(s.state, 'p1').get('R', 0) == before + 2
    roundtrip(s)


@pytest.mark.parametrize('overload', [False, True])
def test_actual_rise_animates_only_eligible_own_artifacts_then_counters_exact_packet(cards, overload):
    s = setup(cards, ['Rise and Shine', 'The Ozolith', 'Gatewatch Beacon', 'Tatterkite'])
    first = put(s, 'The Ozolith', 'battlefield')
    second = put(s, 'Gatewatch Beacon', 'battlefield')
    existing = put(s, 'Tatterkite', 'battlefield')
    theirs = put(s, 'The Ozolith', 'battlefield', pid='p2')
    source = put(s, 'Rise and Shine', 'hand')
    cast(s, source, targets=[] if overload else [first.id], alt_cost=f'{source.id}:1' if overload else None)
    settle(s)
    plan = Plan(s.state, 'p1', cards, None)
    assert plan.ch(s.state.cards[first.id]).is_creature and plan.ch(s.state.cards[first.id]).pt == (4, 4)
    assert counters(s, first) == 4
    assert plan.ch(s.state.cards[second.id]).is_creature == overload
    assert counters(s, second) == (4 if overload else 0)
    assert counters(s, existing) == 0 and not plan.ch(s.state.cards[theirs.id]).is_creature
    roundtrip(s)


def test_aesir_full(cards):
    result = coverage.of_card_data(cards.resolve('The Aesir Escape Valhalla'))
    assert result.level == 'FULL', [(f.label, f.supported) for f in result.features]


def test_zack_full(cards):
    result = coverage.of_card_data(cards.resolve('Zack Fair'))
    assert result.level == 'FULL', [(f.label, f.supported) for f in result.features]


@pytest.mark.parametrize('exile_name,mv', [('The Ozolith', 1), ('Dyadrine, Synthesis Amalgam', 2)])
def test_actual_aesir_three_chapters_linked_exile_mana_and_owner_hand(cards, exile_name, mv, tmp_path):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['The Aesir Escape Valhalla', 'The Ozolith', 'Dyadrine, Synthesis Amalgam', 'Naturalize', 'Tatterkite', 'Grizzly Bears'])
    card = put(s, exile_name, 'graveyard')
    invalid = put(s, 'Naturalize', 'graveyard')
    put(s, 'Tatterkite', 'graveyard')
    bearer = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'The Aesir Escape Valhalla', 'hand')
    before = s.state.players['p1'].life
    cast(s, source)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and card.id in {o.id for o in d.options} and invalid.id not in {o.id for o in d.options}
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[card.id])
    settle(s)
    assert s.state.cards[card.id].zone.endswith(':exile') and s.state.players['p1'].life == before + mv
    original = s.state.rules.object_id(source.id)
    assert s.state.rules.exiled_with[original] == [s.state.rules.object_id(card.id)]
    to_phase(s, 'main1', turn=4)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bearer.id])
    settle(s)
    assert counters(s, bearer) == mv
    to_phase(s, 'main1', turn=7)
    cold_finish(s, cards, tmp_path, [],
                "for _ in range(30):\n    if not s.state.rules.stack: break\n    s.perform(s.state.rules.priority, {'type': 'pass_priority'})\n"
                f"assert s.state.cards[{source.id!r}].zone == s.state.cards[{card.id!r}].zone == 'p1:hand'")
    settle(s)
    assert s.state.cards[source.id].zone == s.state.cards[card.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('blink', [False, True])
def test_actual_zack_copies_all_sacrificed_counters_and_chooses_one_original_equipment(cards, blink, tmp_path):
    s = setup(cards, ['Zack Fair', 'Bonesplitter', 'Behemoth Sledge', 'Grizzly Bears', 'Conformer Shuriken'])
    source = put(s, 'Zack Fair', 'hand')
    cast(s, source)
    settle(s)
    assert counters(s, source) == 1
    bearer = put(s, 'Grizzly Bears', 'battlefield')
    items = []
    for name in ['Conformer Shuriken', 'Bonesplitter']:
        item = put(s, name, 'hand')
        cast(s, item)
        settle(s)
        activate(s, item, ability=1, targets=[source.id])
        settle(s)
        assert s.state.cards[item.id].attached_to == source.id
        items.append(item)
    unrelated = put(s, 'Behemoth Sledge', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=2)
    oid = s.state.rules.object_id(source.id)
    old_equipment = {item.id: s.state.rules.object_id(item.id) for item in items}
    activate(s, source, ability=1, targets=[bearer.id])
    assert s.state.cards[source.id].zone.endswith(':graveyard')
    snap = s.state.rules.lki[oid]
    assert snap.attached_objects_known and snap.attached_objects == old_equipment
    if blink:
        act(s, 'p1', type='move', card_ids=[items[1].id], to={'zone': 'hand'})
        act(s, 'p1', type='move', card_ids=[items[1].id], to={'zone': 'battlefield'})
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'sacrificed_equipment42'
    assert {o.id for o in d.options} == {items[0].id, *([] if blink else [items[1].id])}
    assert unrelated.id not in {o.id for o in d.options}
    assert counters(s, bearer) == 1 and counters(s, bearer, 'charge') == 2
    assert 'indestructible' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bearer.id]).keywords
    roundtrip(s)
    if not blink:
        cold_finish(s, cards, tmp_path, [[items[0].id]],
                    f"assert s.state.cards[{items[0].id!r}].attached_to == {bearer.id!r}\n"
                    f"assert s.state.cards[{items[1].id!r}].attached_to is None")
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[items[0].id])
    settle(s)
    assert s.state.cards[items[0].id].attached_to == bearer.id
    assert s.state.cards[items[1].id].attached_to is None
    roundtrip(s)


def cold_finish(s, cards, tmp_path, choices, assertion):
    import subprocess
    import sys

    saved = tmp_path / 'counter42-pending.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import json, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import effects
state, db, choices, assertion = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state).read_text()), cards=repo)
for answer in json.loads(choices):
    d = s.state.rules.decision
    assert d is not None
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': answer})
    for _ in range(30):
        if s.state.rules.decision is not None or not s.state.rules.stack: break
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
exec(assertion)
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), json.dumps(choices), assertion],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_warden_cold_actual_optional_cost_choice(cards, tmp_path):
    s = setup(cards, ['Sanctuary Warden'])
    source = put(s, 'Sanctuary Warden', 'hand')
    cast(s, source)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    assert d is not None
    option = next(o.id for o in d.options if o.card_id == source.id)
    cold_finish(s, cards, tmp_path, [[option]],
                f"assert s.state.cards[{source.id!r}].counters['shield'] == 1\n"
                "assert len([c for c in s.state.cards.values() if c.token and c.name == 'Citizen']) == 1")


def test_gatewatch_depleted_source_or_opponent_walker_does_not_offer_move(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['Gatewatch Beacon', 'Test Walker Card'])
    source = put(s, 'Gatewatch Beacon', 'hand')
    cast(s, source)
    settle(s)
    opponent = put(s, 'Test Walker Card', 'hand', pid='p2')
    to_phase(s, 'main1', turn=2)
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2, 'U': 2})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=opponent.id, sources=[])
    settle(s)
    assert s.state.rules.decision is None and counters(s, source, 'loyalty') == 3
    assert counters(s, opponent, 'loyalty') == 3
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=0)
    to_phase(s, 'main1', turn=4)
    own = put(s, 'Test Walker Card', 'hand')
    cast(s, own)
    settle(s)
    assert s.state.rules.decision is None and counters(s, own, 'loyalty') == 3
    roundtrip(s)


def test_warden_declines_entry_then_can_pay_attack_trigger(cards):
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['Sanctuary Warden'])
    source = put(s, 'Sanctuary Warden', 'hand')
    cast(s, source)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert counters(s, source, 'shield') == 2
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (source, 'p2'))
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'counter_payment42'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert counters(s, source, 'shield') == 1
    assert len([c for c in s.state.cards.values() if c.token and c.name == 'Citizen']) == 1
    roundtrip(s)


@pytest.mark.parametrize('second_counter', [False, True])
def test_dyadrine_requires_two_distinct_current_successful_removals(cards, second_counter):
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['Dyadrine, Synthesis Amalgam', 'Grizzly Bears'])
    source = put(s, 'Dyadrine, Synthesis Amalgam', 'hand')
    cast(s, source, x_value=0)
    settle(s)
    assert counters(s, source) == 2
    bear = put(s, 'Grizzly Bears', 'battlefield')
    if second_counter:
        act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=1)
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (bear, 'p2'))
    settle(s)
    hand = len(s.state.zones['p1:hand'])
    if second_counter:
        d = s.state.rules.decision
        assert d is not None
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
        d = s.state.rules.decision
        assert d is not None
        selected = [o.id for o in d.options]
        act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=-1)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=selected)
        settle(s)
    assert s.state.rules.decision is None
    assert counters(s, source) == 2 and counters(s, bear) == 0
    assert len(s.state.zones['p1:hand']) == hand
    assert not [c for c in s.state.cards.values() if c.token and c.name == 'Robot']
    roundtrip(s)


@pytest.mark.parametrize('depart', [False, True])
def test_ecd_tax_survives_source_and_expires_on_actual_or_departed_next_turn(cards, depart):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['Elspeth Conquers Death', 'Tatterkite', 'Naturalize', 'Lightning Bolt'])
    victim = put(s, 'Tatterkite', 'battlefield', pid='p2')
    source = put(s, 'Elspeth Conquers Death', 'hand')
    cast(s, source)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[victim.id])
    settle(s)
    to_phase(s, 'main1', turn=4)
    settle(s)
    assert s.state.rules.cost_modifiers
    if depart:
        act(s, 'p1', type='concede')
        to_phase(s, 'main1', turn=5)
    else:
        removal = put(s, 'Naturalize', 'hand', pid='p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'C': 3, 'G': 1})
        wait_priority(s, 'p2')
        act(s, 'p2', type='cast_spell', card_id=removal.id, targets=[source.id], sources=[])
        settle(s)
        assert s.state.cards[source.id].zone.endswith(':graveyard')
    assert s.state.rules.cost_modifiers
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2, 'R': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'], sources=[])
    receipt = next(p for p in s.state.rules.payments.values() if p.card == bolt.id)
    assert sum(receipt.mana_spent.values()) == 3
    settle(s)
    to_phase(s, 'main1', turn=8 if depart else 7)
    assert not s.state.rules.cost_modifiers
    roundtrip(s)


@pytest.mark.parametrize('first,expected', [('Doubling Season', 3), ('Hardened Scales', 4)])
def test_froghemoth_cold_counter_order_keeps_exiled_partition_and_life(cards, tmp_path, first, expected):
    from tests.test_rules_wave5c_combat import declare, to_attack

    s = setup(cards, ['Froghemoth', 'Grizzly Bears', 'Forest', 'Doubling Season', 'Hardened Scales'])
    source = put(s, 'Froghemoth', 'hand')
    creature = put(s, 'Grizzly Bears', 'graveyard', pid='p2')
    land = put(s, 'Forest', 'graveyard', pid='p2')
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Hardened Scales', 'battlefield')
    cast(s, source)
    settle(s)
    to_attack(s)
    declare(s, (source, 'p2'))
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
        elif d is not None:
            break
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[creature.id, land.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'replace_order'
    option = next(o.id for o in d.options if first in o.label)
    before = s.state.players['p1'].life
    cold_finish(s, cards, tmp_path, [[option]],
                f"assert s.state.cards[{source.id!r}].counters['+1/+1'] == {expected}\n"
                f"assert s.state.players['p1'].life == {before + 1}\n"
                f"assert s.state.cards[{creature.id!r}].zone.endswith(':exile')")


@pytest.mark.parametrize('stops_all', [False, True])
def test_froghemoth_trample_cap_is_actual_damage_and_zero_does_not_trigger(cards, stops_all):
    from tests.test_rules_wave5c_combat import declare, to_attack

    s = setup(cards, ['Froghemoth', 'Llanowar Elves', 'Forest', 'Nesting Grounds', 'Resourceful Defense', 'Naturalize'])
    source = put(s, 'Froghemoth', 'hand')
    blocker = put(s, 'Llanowar Elves', 'battlefield', pid='p2')
    if stops_all:
        act(s, 'p2', type='counter', card_ids=[blocker.id], kind='+1/+1', delta=3)
    targets = [put(s, name, 'graveyard', pid='p2') for name in ['Forest', 'Nesting Grounds', 'Resourceful Defense', 'Naturalize']]
    cast(s, source)
    settle(s)
    to_attack(s)
    declare(s, (source, 'p2'))
    blocked = False
    for _ in range(50):
        d = s.state.rules.decision
        if d is not None and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': source.id}])
            blocked = True
        elif d is not None and d.kind == 'divide':
            act(s, d.player, type='choose', decision_id=d.id, amounts=[4, 0] if stops_all else [1, 3])
        elif d is not None or s.state.turn.phase == 'main2':
            break
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert blocked
    if stops_all:
        assert s.state.rules.decision is None and s.state.players['p2'].life == 40
    else:
        d = s.state.rules.decision
        assert d is not None and d.min_choices == 0 and d.max_choices == 3
        assert {c.id for c in targets}.issubset({o.id for o in d.options})
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        settle(s)
        assert counters(s, source) == 0
    roundtrip(s)


def test_zack_legacy_missing_attachment_receipt_stays_manual(cards, tmp_path):
    s = setup(cards, ['Zack Fair', 'Bonesplitter', 'Grizzly Bears'])
    source = put(s, 'Zack Fair', 'hand')
    cast(s, source)
    settle(s)
    target = put(s, 'Grizzly Bears', 'battlefield')
    item = put(s, 'Bonesplitter', 'hand')
    cast(s, item)
    settle(s)
    activate(s, item, ability=1, targets=[source.id])
    settle(s)
    oid = s.state.rules.object_id(source.id)
    activate(s, source, ability=1, targets=[target.id])
    assert s.state.cards[source.id].zone.endswith(':graveyard')
    cold_finish(s, cards, tmp_path, [],
                f"old = json.loads(s.state.model_dump_json())\n"
                f"old['rules']['lki'][{oid!r}].pop('attached_objects', None)\n"
                f"old['rules']['lki'][{oid!r}].pop('attached_objects_known', None)\n"
                "s = GameSession(GameState.model_validate(old), cards=repo)\n"
                "for _ in range(30):\n    if s.state.rules.decision is not None: break\n    s.perform(s.state.rules.priority, {'type': 'pass_priority'})\n"
                "d = s.state.rules.decision\nassert d is not None and d.kind == 'manual_resolution' and d.resume.get('legacy')\n"
                f"assert s.state.cards[{item.id!r}].attached_to is None\n"
                "s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['done']})\n"
                f"assert s.state.cards[{item.id!r}].attached_to is None\n"
                f"assert s.state.cards[{target.id!r}].counters['+1/+1'] == 1")


def test_zack_cold_counter_replacement_keeps_source_lki_then_equipment_choice(cards, tmp_path):
    s = setup(cards, ['Zack Fair', 'Bonesplitter', 'Grizzly Bears', 'Doubling Season', 'Hardened Scales'])
    source = put(s, 'Zack Fair', 'hand')
    cast(s, source)
    settle(s)
    target = put(s, 'Grizzly Bears', 'battlefield')
    item = put(s, 'Bonesplitter', 'hand')
    cast(s, item)
    settle(s)
    activate(s, item, ability=1, targets=[source.id])
    settle(s)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=2)
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Hardened Scales', 'battlefield')
    oid = s.state.rules.object_id(source.id)
    activate(s, source, ability=1, targets=[target.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'replace_order'
    option = next(o.id for o in d.options if 'Doubling Season' in o.label)
    cold_finish(s, cards, tmp_path, [[option], [item.id]],
                f"assert s.state.cards[{target.id!r}].counters == {{'+1/+1': 3, 'charge': 4}}\n"
                f"assert s.state.rules.lki[{oid!r}].counters == {{'+1/+1': 1, 'charge': 2}}\n"
                f"assert s.state.cards[{item.id!r}].attached_to == {target.id!r}")


def test_aesir_cold_original_source_trigger_returns_only_original_link(cards, tmp_path):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['The Aesir Escape Valhalla', 'The Ozolith', 'Grizzly Bears'])
    linked = put(s, 'The Ozolith', 'graveyard')
    target = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'The Aesir Escape Valhalla', 'hand')
    cast(s, source)
    settle(s)
    assert s.state.cards[linked.id].zone.endswith(':exile')
    old = s.state.rules.object_id(source.id)
    to_phase(s, 'main1', turn=4)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    settle(s)
    to_phase(s, 'main1', turn=7)
    assert s.state.rules.stack
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'battlefield'})
    new = s.state.rules.object_id(source.id)
    assert new != old
    cold_finish(s, cards, tmp_path, [],
                "for _ in range(30):\n    if not s.state.rules.stack: break\n    s.perform(s.state.rules.priority, {'type': 'pass_priority'})\n"
                f"assert s.state.cards[{linked.id!r}].zone == 'p1:hand'\n"
                f"assert s.state.cards[{source.id!r}].zone == 'p1:battlefield'\n"
                f"assert s.state.rules.object_id({source.id!r}) == {new!r}\n"
                f"assert {new!r} not in s.state.rules.exiled_with")


def test_maze_flash_x_zero_and_live_tapped_hexproof(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['Lost in the Maze', 'Grizzly Bears'])
    own = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    source = put(s, 'Lost in the Maze', 'hand')
    to_phase(s, 'main1', turn=2)
    cast(s, source, x_value=0)
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[own.id].tapped and not s.state.cards[other.id].tapped
    assert counters(s, own, 'stun') == counters(s, other, 'stun') == 0
    act(s, 'p1', type='tap', card_ids=[own.id, other.id], tapped=True)
    plan = Plan(s.state, 'p1', cards, None)
    assert 'hexproof' in plan.ch(s.state.cards[own.id]).keywords
    assert 'hexproof' not in plan.ch(s.state.cards[other.id]).keywords
    roundtrip(s)


def test_maze_stun_uses_control_at_resolution(cards):
    s = setup(cards, ['Lost in the Maze', 'Grizzly Bears'])
    creature = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    source = put(s, 'Lost in the Maze', 'hand')
    cast(s, source, x_value=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[creature.id])
    act(s, 'p1', type='set_controller', card_ids=[creature.id], player='p1')
    settle(s)
    assert s.state.cards[creature.id].tapped and counters(s, creature, 'stun') == 0
    roundtrip(s)


def test_conformer_cold_original_attacker_and_fixed_difference_after_equipment_moves(cards, tmp_path):
    from tests.test_rules_wave5c_combat import declare, to_attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards, ['Conformer Shuriken', 'Grizzly Bears', 'Llanowar Elves', 'Doubling Season', 'Hardened Scales'])
    bearer = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Llanowar Elves', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p2', type='counter', card_ids=[victim.id], kind='+1/+1', delta=3)
    source = put(s, 'Conformer Shuriken', 'hand')
    cast(s, source)
    settle(s)
    activate(s, source, ability=1, targets=[bearer.id])
    settle(s)
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Hardened Scales', 'battlefield')
    to_phase(s, 'main1', turn=4)
    to_attack(s, 4)
    declare(s, (bearer, 'p2'))
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[victim.id])
    act(s, 'p1', type='attach', card_ids=[source.id], to=other.id)
    settle(s)
    assert s.state.cards[victim.id].tapped
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'replace_order'
    option = next(o.id for o in d.options if 'Doubling Season' in o.label)
    cold_finish(s, cards, tmp_path, [[option]],
                f"assert s.state.cards[{bearer.id!r}].counters['+1/+1'] == 7\n"
                f"assert not s.state.cards[{other.id!r}].counters\n"
                f"assert s.state.cards[{source.id!r}].attached_to == {other.id!r}")


def test_rise_cold_counter_replacement_keeps_zero_zero_animation_alive_until_resolution(cards, tmp_path):
    s = setup(cards, ['Rise and Shine', 'The Ozolith', 'Doubling Season', 'Hardened Scales'])
    target = put(s, 'The Ozolith', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Hardened Scales', 'battlefield')
    source = put(s, 'Rise and Shine', 'hand')
    cast(s, source, targets=[target.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'replace_order'
    assert s.state.cards[target.id].zone.endswith(':battlefield')
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).pt == (0, 0)
    option = next(o.id for o in d.options if 'Doubling Season' in o.label)
    cold_finish(s, cards, tmp_path, [[option]],
                f"assert s.state.cards[{target.id!r}].zone == 'p1:battlefield'\n"
                f"assert s.state.cards[{target.id!r}].counters['+1/+1'] == 9")
