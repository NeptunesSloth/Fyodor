"""Native permanent offers defer every outcome until all APNAP choices finish."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/martyrs87_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest', 'Island']


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


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)



NAMES = ['Martyr of Frost', 'Martyr of Sands', 'Martyr of Ashes', 'Martyr of Bones', 'Martyr of Spores']


@pytest.mark.parametrize('name', NAMES)
def test_canonical_whole_martyr(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def hold(s):
    for pid in ['p1', 'p2', 'p3']:
        act(s, pid, type='set_prefs', hold_priority=True)


def activate(s, source, shown, targets=(), x=None, mana=2):
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': mana})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=list(targets),
        x_value=len(shown) if x is None else x, target_counts=[len(targets)] if source.name == 'Martyr of Bones' else [], sources=[], cost_choices=[{'component': 1, 'cards': [c.id for c in shown]}])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    return next(c for c in s.state.cards.values() if c.zone == 'stack' and c.ability is not None)


def test_sands_native_chosen_x_reveal_lifetime_and_three_times_x_gain(cards):
    from app.game.visibility import ALL
    from app.rules.plan import Plan

    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Sands', 'battlefield')
    a = put(s, 'Swords to Plowshares', 'hand')
    b = put(s, 'Disenchant', 'hand')
    ability = activate(s, source, [a, b], mana=1)
    p = Plan(s.state, 'p1', s.cards, None)
    record = s.state.rules.payments[p.oid(ability)]
    assert record.x == 2 and set(record.revealed) == {a.id, b.id}
    assert all(ALL in s.state.cards[c.id].revealed_to for c in [a, b])
    assert s.state.players['p1'].life == 40
    settle(s)
    assert s.state.players['p1'].life == 46
    assert all(ALL not in s.state.cards[c.id].revealed_to for c in [a, b])
    assert not s.state.rules.revealed_activation_costs
    roundtrip(s)


def test_spores_native_x_buff_uses_two_original_green_cards(cards):
    from app.rules.plan import Plan

    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Spores', 'battlefield')
    a = put(s, 'Giant Growth', 'hand')
    b = put(s, 'Growth Spiral', 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    activate(s, source, [a, b], [bear.id], mana=1)
    settle(s)
    assert Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[bear.id]).pt == (4, 4)
    assert s.state.cards[a.id].zone == s.state.cards[b.id].zone == 'p1:hand'
    roundtrip(s)


def test_ashes_native_x_damage_hits_ground_creatures_and_excludes_flying(cards):
    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Ashes', 'battlefield')
    a = put(s, 'Lightning Bolt', 'hand')
    b = put(s, 'Pyroclasm', 'hand')
    ground = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    flyer = put(s, 'Serra Angel', 'battlefield', 'p3')
    activate(s, source, [a, b], mana=2)
    settle(s)
    assert s.state.cards[ground.id].zone == 'p2:graveyard'
    assert s.state.cards[flyer.id].zone == 'p3:battlefield' and s.state.cards[flyer.id].damage == 0
    assert all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)


def test_bones_native_up_to_x_original_targets_in_one_graveyard(cards):
    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Bones', 'battlefield')
    a = put(s, 'Dark Ritual', 'hand')
    b = put(s, 'Go for the Throat', 'hand')
    left = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    right = put(s, 'Lightning Bolt', 'graveyard', 'p2')
    activate(s, source, [a, b], [left.id, right.id], mana=1)
    settle(s)
    assert s.state.cards[left.id].zone == s.state.cards[right.id].zone == 'p2:exile'
    roundtrip(s)


def test_frost_native_counter_tax_uses_revealed_x_after_source_sacrifice(cards):
    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Frost', 'battlefield')
    a = put(s, 'Opt', 'hand')
    b = put(s, 'Counterspell', 'hand')
    spell = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=['p3'], sources=[])
    activate(s, source, [a, b], [spell.id], mana=2)
    settle(s)
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    assert s.state.players['p3'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_zero_x_still_pays_mana_and_sacrifices_source_without_revealing_any_card(cards, name):
    from app.rules.plan import Plan

    s = game(cards)
    hold(s)
    source = put(s, name, 'battlefield')
    targets = []
    if name == 'Martyr of Frost':
        spell = put(s, 'Lightning Bolt', 'hand', 'p2')
        wait_priority(s, 'p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
        act(s, 'p2', type='cast_spell', card_id=spell.id, targets=['p3'], sources=[])
        targets = [spell.id]
    elif name == 'Martyr of Spores':
        targets = [put(s, 'Grizzly Bears', 'battlefield', 'p2').id]
    ability = activate(s, source, [], targets, x=0, mana=2 if name in ['Martyr of Frost', 'Martyr of Ashes'] else 1)
    record = s.state.rules.payments[Plan(s.state, 'p1', s.cards, None).oid(ability)]
    assert record.x == 0 and record.revealed == []
    settle(s)
    if name == 'Martyr of Frost':
        assert s.state.rules.decision and s.state.rules.decision.player == 'p2'
        choose(s, ['pay'])
        assert s.state.players['p3'].life == 37
    assert s.state.players['p1'].life == 40
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_devoid_blue_mana_cost_card_is_not_blue_for_reveal_cost_and_rejection_is_atomic(cards):
    from app.game.errors import ActionError

    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Frost', 'battlefield')
    colorless = put(s, 'Spell Shrivel', 'hand')
    spell = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=['p3'], sources=[])
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=1, targets=[spell.id], sources=[],
            cost_choices=[{'component': 1, 'cards': [colorless.id]}])
    assert s.state.model_dump(mode='json') == before


def test_duplicate_reveal_choices_cannot_fake_two_distinct_white_cards(cards):
    from app.game.errors import ActionError

    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Sands', 'battlefield')
    a = put(s, 'Disenchant', 'hand')
    put(s, 'Swords to Plowshares', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=2, targets=[], sources=[],
            cost_choices=[{'component': 1, 'cards': [a.id, a.id]}])
    assert s.state.model_dump(mode='json') == before


def test_bones_cannot_split_up_to_x_targets_between_two_graveyards(cards):
    from app.game.errors import ActionError

    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Bones', 'battlefield')
    a = put(s, 'Dark Ritual', 'hand')
    b = put(s, 'Go for the Throat', 'hand')
    left = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    right = put(s, 'Lightning Bolt', 'graveyard', 'p3')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=2, targets=[left.id, right.id],
            target_counts=[2], sources=[], cost_choices=[{'component': 1, 'cards': [a.id, b.id]}])
    assert s.state.model_dump(mode='json') == before


def cast_pending(s, pid, name, targets, mana):
    spell = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana=mana)
    act(s, pid, type='cast_spell', card_id=spell.id, targets=list(targets), sources=[])
    return spell


def resolve_one(s, cid):
    for _ in range(30):
        card = s.state.cards.get(cid)
        if card is None or card.zone != 'stack':
            return
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('The selected stack object never resolved')


def test_actual_stifle_counters_activation_and_cleans_reveal_lifetime_without_refunding_cost(cards):
    from app.game.visibility import ALL

    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Sands', 'battlefield')
    a = put(s, 'Swords to Plowshares', 'hand')
    b = put(s, 'Disenchant', 'hand')
    ability = activate(s, source, [a, b], mana=1)
    cast_pending(s, 'p2', 'Stifle', [ability.id], {'U': 1})
    settle(s)
    assert s.state.players['p1'].life == 40
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert not s.state.players['p1'].mana and not s.state.rules.revealed_activation_costs
    assert all(ALL not in s.state.cards[c.id].revealed_to for c in [a, b])
    roundtrip(s)


def test_actual_revealed_flash_card_returns_as_new_incarnation_without_changing_x_or_inheriting_reveal(cards):
    from app.game.visibility import ALL
    from app.rules.plan import Plan

    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Sands', 'battlefield')
    a = put(s, 'Whitemane Lion', 'hand')
    b = put(s, 'Disenchant', 'hand')
    original = s.state.rules.object_id(a.id)
    ability = activate(s, source, [a, b], mana=1)
    ability_oid = s.state.rules.object_id(ability.id)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=a.id, targets=[], sources=[])
    resolve_one(s, a.id)
    for _ in range(30):
        if s.state.cards[a.id].zone == 'p1:hand':
            break
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[a.id])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[a.id].zone == 'p1:hand' and s.state.rules.object_id(a.id) != original
    assert ALL not in s.state.cards[a.id].revealed_to and ALL in s.state.cards[b.id].revealed_to
    assert s.state.rules.payments[ability_oid].x == 2
    assert Plan(s.state, 'p1', s.cards, None).rules.stack[ability.id].x == 2
    settle(s)
    assert s.state.players['p1'].life == 46
    assert not s.state.rules.revealed_activation_costs and ALL not in s.state.cards[a.id].revealed_to
    roundtrip(s)


def test_already_revealed_multicolor_card_can_pay_two_distinct_activations_and_remains_revealed_until_both_originals_leave(cards):
    from app.game.visibility import ALL
    from app.rules.plan import Plan

    s = game(cards)
    hold(s)
    frost = put(s, 'Martyr of Frost', 'battlefield')
    spores = put(s, 'Martyr of Spores', 'battlefield')
    shared = put(s, 'Growth Spiral', 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    spell = cast_pending(s, 'p2', 'Lightning Bolt', ['p3'], {'R': 1})
    first = activate(s, frost, [shared], [spell.id], mana=2)
    activate(s, spores, [shared], [bear.id], mana=1)
    second = next(c for c in s.state.cards.values() if c.zone == 'stack' and c.ability is not None and c.id != first.id)
    assert len(s.state.rules.revealed_activation_costs) == 2 and ALL in s.state.cards[shared.id].revealed_to
    resolve_one(s, second.id)
    assert Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[bear.id]).pt == (3, 3)
    assert len(s.state.rules.revealed_activation_costs) == 1 and ALL in s.state.cards[shared.id].revealed_to
    settle(s)
    assert s.state.players['p3'].life == 40 and s.state.cards[spell.id].zone == 'p2:graveyard'
    assert not s.state.rules.revealed_activation_costs and ALL not in s.state.cards[shared.id].revealed_to
    roundtrip(s)


@pytest.mark.parametrize('stage', ['private_choice', 'stack'])
def test_true_cold_native_x_reveal_cost_and_original_activation_visibility_lifetime(cards, tmp_path, stage):
    import os
    import subprocess
    import sys

    import app
    from app.game.visibility import ALL

    s = game(cards)
    hold(s)
    source = put(s, 'Martyr of Sands', 'battlefield')
    a = put(s, 'Swords to Plowshares', 'hand')
    b = put(s, 'Disenchant', 'hand')
    if stage == 'private_choice':
        third = put(s, 'Serra Angel', 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=2, targets=[], sources=[])
        assert s.state.rules.decision.resume['step'] == 'ability_cost'
        assert s.state.cards[source.id].zone == 'p1:battlefield'
        assert all(ALL not in s.state.cards[c.id].revealed_to for c in [a, b, third])
        for pid in ['p2', 'p3']:
            assert not any(c.id in json.dumps(s.view(pid)['rules']['decision']) for c in [a, b, third])
        ability_id = ''
        counter_id = ''
    else:
        ability_id = activate(s, source, [a, b], mana=1).id
        counter_id = put(s, 'Stifle', 'hand', 'p2').id
        act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
        assert s.state.rules.revealed_activation_costs
        assert ALL in s.state.cards[a.id].revealed_to and ALL in s.state.cards[b.id].revealed_to
    saved = tmp_path / 'martyrs87.json'
    saved.write_text(s.state.model_dump_json())
    backend = Path(app.__file__).resolve().parents[1]
    code = r'''
import sys,json
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.game.visibility import ALL
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.test_rules_bandmate_references import wait_priority
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
stage,source,first,second,ability,counter=sys.argv[3:]
if stage=='private_choice':
 d=s.state.rules.decision
 assert d and d.resume['step']=='ability_cost'
 assert s.state.cards[source].zone=='p1:battlefield'
 assert ALL not in s.state.cards[first].revealed_to and ALL not in s.state.cards[second].revealed_to
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[first,second])
 created=next(c for c in s.state.cards.values() if c.zone=='stack' and c.ability is not None)
 payment=s.state.rules.payments[s.state.rules.object_id(created.id)]
 assert payment.x==2 and set(payment.revealed)=={first,second}
 assert ALL in s.state.cards[first].revealed_to and ALL in s.state.cards[second].revealed_to
 assert s.state.cards[source].zone=='p1:graveyard'
 settle(s)
 assert s.state.players['p1'].life==46
else:
 assert s.state.rules.revealed_activation_costs
 assert s.state.cards[ability].zone=='stack'
 wait_priority(s,'p2')
 act(s,'p2',type='cast_spell',card_id=counter,targets=[ability],sources=[])
 settle(s)
 assert s.state.players['p1'].life==40
assert s.state.cards[source].zone=='p1:graveyard'
assert not s.state.rules.revealed_activation_costs
assert ALL not in s.state.cards[first].revealed_to and ALL not in s.state.cards[second].revealed_to
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), stage, source.id, a.id, b.id, ability_id, counter_id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
