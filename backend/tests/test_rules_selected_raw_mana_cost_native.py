"""Actual Rosheen spending exercises raw-cost provenance without a Nexos adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ('mana_followthrough_profiles_cards.json', 'selected_raw_mana_cost_cards.json'):
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='srcx', number=f'{filename[:4]}{i}',
                                  **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def activate_rosheen(s, cards, source, player='p1'):
    wait_priority(s, player)
    index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    act(s, player, type='activate_ability', card_id=source.id, ability=index)
    assert len(s.state.players[player].mana_units) == 4


def test_native_nexos_actual_granted_basic_land_cc_and_nonbasic_negative(cards):
    from app.rules.plan import Plan

    s = table(cards, ['Nexos', 'Forest', 'Walking Ballista', 'Sol Ring', 'Command Tower'], [], [])
    source = put(s, 'Nexos', 'battlefield')
    land = put(s, 'Forest', 'battlefield')
    nonbasic = put(s, 'Command Tower', 'battlefield')
    spell = put(s, 'Walking Ballista', 'hand')
    ring = put(s, 'Sol Ring', 'hand')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    abilities = list(casting.mana_abilities(s.state, land, cards))
    index = next(i for i, ab in abilities if ab.spend_only)
    assert not any(ab.spend_only for _, ab in casting.mana_abilities(s.state, nonbasic, cards))
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=index)
    units = s.state.players['p1'].mana_units
    assert len(units) == 2 and all(u.sym == 'C' and u.src == Plan(s.state, 'p1', cards, None).oid(land) for u in units)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert not any(ab.spend_only for _, ab in casting.mana_abilities(s.state, land, cards))
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ring.id, sources=[])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=1, sources=[])
    assert not s.state.players['p1'].mana_units
    roundtrip(s)


@pytest.mark.parametrize('x', [0, 1])
def test_native_nexos_x_zero_and_black_only_x_can_pay_original_generic_part(cards, x):
    s = table(cards, ['Nexos', 'Forest', 'Consume Spirit'], [], [])
    put(s, 'Nexos', 'battlefield')
    land = put(s, 'Forest', 'battlefield')
    spell = put(s, 'Consume Spirit', 'hand')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    index = next(i for i, ab in casting.mana_abilities(s.state, land, cards) if ab.spend_only)
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=index)
    act(s, 'p1', type='add_mana', player='p1', mana={'B': x + 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=x, targets=['p2'], sources=[])
    record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert record.mana_spent == {'C': 1, 'B': x + 1}
    assert len(s.state.players['p1'].mana_units) == 1
    roundtrip(s)


def test_native_nexos_two_units_can_pay_different_actual_costs(cards):
    s = table(cards, ['Nexos', 'Forest', 'Fireball', 'Fireball'], [], [])
    put(s, 'Nexos', 'battlefield')
    land = put(s, 'Forest', 'battlefield')
    spells = [c for c in s.state.cards.values() if c.name == 'Fireball' and c.owner == 'p1']
    assert len(spells) == 2
    for spell in spells:
        act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    index = next(i for i, ab in casting.mana_abilities(s.state, land, cards) if ab.spend_only)
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=index)
    for i, spell in enumerate(spells):
        act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
        act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=1, targets=['p2'], sources=[])
        assert len(s.state.players['p1'].mana_units) == 1 - i
        assert s.state.rules.payments[s.state.rules.object_id(spell.id)].mana_spent == {'C': 1, 'R': 1}
        answer(s)
        wait_priority(s, 'p1')
    roundtrip(s)


def test_native_nexos_controller_changes_refresh_grant_and_keep_old_units(cards):
    s = table(cards, ['Nexos', 'Forest'], ['Forest'], [])
    source = put(s, 'Nexos', 'battlefield')
    own = put(s, 'Forest', 'battlefield')
    other = put(s, 'Forest', 'battlefield', 'p2')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    index = next(i for i, ab in casting.mana_abilities(s.state, own, cards) if ab.spend_only)
    act(s, 'p1', type='activate_ability', card_id=own.id, ability=index)
    old = s.state.players['p1'].mana_units.copy()
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    assert not any(ab.spend_only for _, ab in casting.mana_abilities(s.state, own, cards))
    assert any(ab.spend_only for _, ab in casting.mana_abilities(s.state, other, cards))
    assert s.state.players['p1'].mana_units == old
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert not any(ab.spend_only for _, ab in casting.mana_abilities(s.state, other, cards))
    roundtrip(s)


def test_native_nexos_saved_spell_payment_true_cold_after_granter_departure(cards, tmp_path):
    import subprocess
    import sys

    s = table(cards, ['Nexos', 'Forest', 'Forest', 'Walking Ballista'], [], [])
    source = put(s, 'Nexos', 'battlefield')
    lands = [c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1'][:2]
    for land in lands:
        act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'battlefield'})
    spell = put(s, 'Walking Ballista', 'hand')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    index = next(i for i, ab in casting.mana_abilities(s.state, lands[0], cards) if ab.spend_only)
    act(s, 'p1', type='activate_ability', card_id=lands[0].id, ability=index)
    produced_by = s.state.rules.object_id(lands[0].id)
    act(s, 'p1', type='move', card_ids=[lands[0].id], to={'player': 'p1', 'zone': 'graveyard'})
    assert all(u.src == produced_by for u in s.state.players['p1'].mana_units)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=2)
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    assert s.state.rules.decision.resume['payment_context']['selected_cost_has_x'] is True
    path = tmp_path / 'nexos-selected-cost.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,database,land,spell=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
assert s.state.rules.decision.resume['payment_context']['selected_cost_has_x'] is True
s.perform('p1',{'type':'activate_ability','card_id':land,'ability':0})
if s.state.rules.decision is not None:
 d=s.state.rules.decision
 assert d.resume['step']=='pay_mana'
 s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
record=s.state.rules.payments[s.state.rules.object_id(spell)]
assert record.mana_spent=={'C':3,'G':1},record.mana_spent
assert not s.state.players['p1'].mana_units
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), lands[1].id, spell.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('kind', ['activated', 'cycling'])
def test_native_nexos_actual_activated_or_cycling_raw_x(cards, kind):
    from app.rules.plan import Plan

    name = 'Helix Pinnacle' if kind == 'activated' else 'Shark Typhoon'
    s = table(cards, ['Nexos', 'Forest', name], [], [])
    put(s, 'Nexos', 'battlefield')
    land = put(s, 'Forest', 'battlefield')
    source = put(s, name, 'battlefield' if kind == 'activated' else 'hand')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    index = next(i for i, ab in casting.mana_abilities(s.state, land, cards) if ab.spend_only)
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=index)
    ch = Plan(s.state, 'p1', cards, None).ch(source)
    if kind == 'cycling':
        act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
        index = next(ab.index for ab in ch.abilities if 'cycling' in ab.keywords)
    else:
        index = next(ab.index for ab in ch.abilities if ab.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, x_value=2 if kind == 'activated' else 1, sources=[])
    assert not s.state.players['p1'].mana_units
    if kind == 'cycling':
        assert s.state.cards[source.id].zone == 'p1:graveyard'
    answer(s)
    if kind == 'activated':
        assert s.state.cards[source.id].counters.get('tower') == 2
    roundtrip(s)


def test_native_nexos_selected_madness_mana_x_and_nonmana_x_are_distinct(cards):
    s = table(cards, ['Nexos', 'Forest', "Nahiri's Wrath", 'From Under the Floorboards'], [], [])
    put(s, 'Nexos', 'battlefield')
    land = put(s, 'Forest', 'battlefield')
    spell = put(s, 'From Under the Floorboards', 'hand')
    discard = put(s, "Nahiri's Wrath", 'hand')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    index = next(i for i, ab in casting.mana_abilities(s.state, land, cards) if ab.spend_only)
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=index)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'R': 1, 'B': 2})
    act(s, 'p1', type='cast_spell', card_id=discard.id, x_value=1, targets=[], target_counts=[0],
        cost_choices=[{'component': 0, 'cards': [spell.id]}], sources=[])
    assert len(s.state.players['p1'].mana_units) == 2
    assert s.state.rules.payments[s.state.rules.object_id(discard.id)].mana_spent == {'C': 2, 'R': 1}
    d = until_asked(s)
    assert 'Madness' in d.prompt
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
    d = s.state.rules.decision
    assert d is not None and any(o.id == 'x:2' for o in d.options)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['x:2'])
    assert not s.state.players['p1'].mana_units
    answer(s)
    assert len([c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.token]) == 2
    roundtrip(s)


def test_rosheen_actual_announced_x_spell_uses_frozen_selected_cost(cards):
    s = table(cards, ['Rosheen Meanderer', 'Walking Ballista', 'Sol Ring'], [], [])
    source = put(s, 'Rosheen Meanderer', 'battlefield')
    spell = put(s, 'Walking Ballista', 'hand')
    ring = put(s, 'Sol Ring', 'hand')
    to_phase(s, 'main1', 4)
    activate_rosheen(s, cards, source)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ring.id, sources=[])
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=2, sources=[])
    record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert record.mana_spent == {'C': 4}
    assert not s.state.players['p1'].mana_units
    roundtrip(s)


@pytest.mark.parametrize('kicked', [False, True])
def test_rosheen_actual_selected_kicker_x_qualifies_entire_cost(cards, kicked):
    s = table(cards, ['Rosheen Meanderer', 'Verdeloth the Ancient'], [], [])
    source = put(s, 'Rosheen Meanderer', 'battlefield')
    spell = put(s, 'Verdeloth the Ancient', 'hand')
    to_phase(s, 'main1', 4)
    activate_rosheen(s, cards, source)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 2, 'C': 2})
    payload = dict(type='cast_spell', card_id=spell.id, sources=[], kicker=1 if kicked else 0)
    if kicked:
        payload['x_value'] = 2
        act(s, 'p1', **payload)
        record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
        assert record.mana_spent == {'G': 2, 'C': 6}
    else:
        before = s.state.model_dump(mode='json')
        with pytest.raises(ActionError):
            act(s, 'p1', **payload)
        assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_free_printed_x_spell_with_real_tax_cannot_spend_rosheen(cards):
    s = table(cards, ['Rosheen Meanderer', 'Omniscience', 'Walking Ballista', 'Sphere of Resistance'], [], [])
    source = put(s, 'Rosheen Meanderer', 'battlefield')
    put(s, 'Omniscience', 'battlefield')
    put(s, 'Sphere of Resistance', 'battlefield')
    spell = put(s, 'Walking Ballista', 'hand')
    to_phase(s, 'main1', 4)
    activate_rosheen(s, cards, source)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=0, sources=[], free=True)
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=0, sources=[], free=True)
    assert len(s.state.players['p1'].mana_units) == 4
    record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert record.mana_spent == {'C': 1}
    roundtrip(s)


def test_actual_suspend_special_action_x_uses_rosheen_without_spell_or_ability_purpose(cards):
    s = table(cards, ['Rosheen Meanderer', 'Aeon Chronicler'], [], [])
    source = put(s, 'Rosheen Meanderer', 'battlefield')
    spell = put(s, 'Aeon Chronicler', 'hand')
    to_phase(s, 'main1', 4)
    activate_rosheen(s, cards, source)
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    from app.rules.plan import Plan

    ch = Plan(s.state, 'p1', cards, None).ch(spell)
    index = next(ab.index for ab in ch.abilities if 'suspend' in ab.keywords)
    act(s, 'p1', type='activate_ability', card_id=spell.id, ability=index, x_value=1, sources=[])
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert s.state.cards[spell.id].counters.get('time') == 1
    assert not s.state.zones.get('stack')
    assert not s.state.players['p1'].mana_units and not s.state.players['p1'].mana
    roundtrip(s)


@pytest.mark.parametrize('cold', [False, True])
def test_actual_condescend_resolution_x_uses_rosheen_without_casting_purpose(cards, tmp_path, cold):
    s = table(cards, ['Rosheen Meanderer', 'Opt', 'Condescend'], [], [])
    source = put(s, 'Rosheen Meanderer', 'battlefield')
    opt = put(s, 'Opt', 'hand')
    counter = put(s, 'Condescend', 'hand')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=opt.id, sources=[])
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=counter.id, x_value=3, targets=[opt.id], sources=[])
    d = until_asked(s)
    assert d.resume['opt']['cost_has_x'] is True
    assert d.resume['opt']['cost'] == '{3}'
    roundtrip(s)
    if cold:
        import subprocess
        import sys

        path = tmp_path / 'condescend-raw-cost.json'
        path.write_text(s.state.model_dump_json())
        code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,database,source,spell=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
d=s.state.rules.decision
assert d.resume['opt']['cost_has_x'] is True
assert d.resume['opt']['cost']=='{3}'
s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
assert s.state.cards[source].tapped
assert len(s.state.players['p1'].mana_units)==1
assert s.state.cards[spell].zone=='stack'
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
        result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), source.id, opt.id],
                                capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
        assert result.returncode == 0, result.stderr
        return
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    assert s.state.cards[source.id].tapped
    assert len(s.state.players['p1'].mana_units) == 1
    assert s.state.cards[opt.id].zone == 'stack'
    answer(s)
    roundtrip(s)
