"""Production native gameplay gates for exact mana allocation restrictions."""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import casting
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_mana_followthrough_profiles import cards  # noqa: F401
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Jegantha, the Wellspring'


def setup(cards):  # noqa: F811
    s = table(cards, [NAME, 'Grizzly Bears', 'Sol Ring', 'Opt'], [], [])
    source = put(s, NAME, 'battlefield')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    return s, source


@pytest.mark.parametrize('manual', [False, True])
def test_native_jegantha_keeps_restricted_leftover_and_spends_old_plain_generic(cards, manual):  # noqa: F811
    s, source = setup(cards)
    if manual:
        index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
        units = s.state.players['p1'].mana_units
        assert len(units) == 5 and all(not u.generic_allowed and u.src == Plan(s.state, 'p1', cards, None).oid(source) for u in units)
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    spell = put(s, 'Grizzly Bears', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[] if manual else [source.id])
    assert s.state.players['p1'].mana.get('W', 0) == 0
    assert {u.sym for u in s.state.players['p1'].mana_units} == set('WUBR')
    assert all(not u.generic_allowed for u in s.state.players['p1'].mana_units)
    answer(s)
    ring = put(s, 'Sol Ring', 'hand')
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ring.id, sources=[])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


@pytest.mark.parametrize('name,x,allowed', [('Sliver Hivelord', None, True), ('Wild Cantor', None, True),
    ('Gut Shot', None, True), ('Matter Reshaper', None, False), ('Walking Ballista', 1, False)])
def test_jegantha_actual_colored_hybrid_phyrexian_colorless_and_x_costs(cards, name, x, allowed):  # noqa: F811
    names = [NAME, name]
    s = table(cards, names, [], [])
    source = put(s, NAME, 'battlefield')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    spell = put(s, name, 'hand')
    wait_priority(s, 'p1')
    payload = {'type': 'cast_spell', 'card_id': spell.id, 'sources': []}
    if x is not None:
        payload['x_value'] = x
    if name == 'Gut Shot':
        payload.update(targets=['p2'], life_symbols=[])
    old_life = s.state.players['p1'].life
    if allowed:
        act(s, 'p1', **payload)
        assert s.state.cards[spell.id].zone == 'stack'
        assert s.state.players['p1'].life == old_life
        record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
        assert all(c in 'WUBRG' for c in record.mana_spent)
        assert sum(record.mana_spent.values()) == (5 if name == 'Sliver Hivelord' else 1)
    else:
        before = s.state.model_dump(mode='json')
        with pytest.raises(ActionError):
            act(s, 'p1', **payload)
        assert s.state.model_dump(mode='json') == before
    roundtrip(s)


@pytest.mark.parametrize('family', ['as_though', 'chosen', 'chosen_krrik', 'restricted_x', 'filter'])
def test_actual_four_cost_encodings_keep_genuine_generic_origin(cards, family):  # noqa: F811
    extra = {'as_though': ['Mycosynth Lattice', 'Grizzly Bears'], 'chosen': ['Throne of Eldraine'], 'chosen_krrik': ['Throne of Eldraine', "K'rrik, Son of Yawgmoth"],
             'restricted_x': ["K'rrik, Son of Yawgmoth", 'Consume Spirit'], 'filter': ['Sungrass Prairie', 'Centaur Courser']}[family]
    s = table(cards, [NAME, *extra], [], [])
    source = put(s, NAME, 'battlefield')
    permanent = None
    if family in ('as_though', 'chosen', 'chosen_krrik', 'filter'):
        permanent = put(s, extra[0], 'battlefield')
    elif family == 'restricted_x':
        put(s, extra[0], 'battlefield')
    if family.startswith('chosen'):
        act(s, 'p1', type='set_choice', card_id=permanent.id, key='Chosen color', value='Black' if family == 'chosen_krrik' else 'Red')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    if family.startswith('chosen'):
        if family == 'chosen_krrik':
            put(s, extra[1], 'battlefield')
        act(s, 'p1', type='add_mana', player='p1', mana={'B' if family == 'chosen_krrik' else 'R': 2})
        ab = next(ab for ab in Plan(s.state, 'p1', cards, None).ch(permanent).abilities if 'Draw two cards' in ab.text)
        payload = {'type': 'activate_ability', 'card_id': permanent.id, 'ability': ab.index, 'sources': []}
    else:
        spell = put(s, extra[-1], 'hand')
        payload = {'type': 'cast_spell', 'card_id': spell.id, 'sources': []}
        if family == 'restricted_x':
            act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
            payload.update(x_value=1, targets=['p2'])
        if family == 'filter':
            payload.pop('sources')
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', **payload)
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1} if family == 'restricted_x' else {'B' if family == 'chosen_krrik' else 'R': 1} if family.startswith('chosen') else {'C': 1})
    act(s, 'p1', **payload)
    if family.startswith('chosen'):
        assert len(s.state.players['p1'].mana_units) == 5
    elif family == 'as_though':
        record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
        assert record.mana_spent == {'W': 1, 'C': 1}
    elif family == 'restricted_x':
        record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
        assert record.mana_spent == {'B': 2, 'C': 1}
    else:
        assert s.state.cards[permanent.id].tapped
        assert {u.sym for u in s.state.players['p1'].mana_units} == set('WUBR')
        assert all(not u.generic_allowed for u in s.state.players['p1'].mana_units)
    roundtrip(s)


@pytest.mark.parametrize('change', ['none', 'base_departure', 'bonus_departure', 'bonus_control'])
def test_native_kinnan_bonus_has_independent_provenance_and_pays_generic(cards, change):  # noqa: F811
    s = table(cards, [NAME, 'Kinnan, Bonder Prodigy', 'Sol Ring'], [], [])
    source = put(s, NAME, 'battlefield')
    bonus = put(s, 'Kinnan, Bonder Prodigy', 'battlefield')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    plan = Plan(s.state, 'p1', cards, None)
    source_oid, bonus_oid = plan.oid(source), plan.oid(bonus)
    index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'staged_mana_option'
    assert len(s.state.players['p1'].mana_units) == 5
    if change.endswith('departure'):
        card = source if change == 'base_departure' else bonus
        act(s, 'p1', type='move', card_ids=[card.id], to={'player': 'p1', 'zone': 'graveyard'})
    elif change == 'bonus_control':
        act(s, 'p1', type='set_controller', card_ids=[bonus.id], player='p2')
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['0'])
    units = s.state.players['p1'].mana_units
    assert len(units) == 6
    assert len([u for u in units if u.src == source_oid and not u.generic_allowed]) == 5
    assert [(u.sym, u.generic_allowed) for u in units if u.src == bonus_oid] == [('W', True)]
    ring = put(s, 'Sol Ring', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=ring.id, sources=[])
    assert len(s.state.players['p1'].mana_units) == 5
    assert all(u.src == source_oid and not u.generic_allowed for u in s.state.players['p1'].mana_units)
    answer(s)
    roundtrip(s)


def test_jegantha_kinnan_pending_bonus_true_cold_retains_both_producers(cards, tmp_path):  # noqa: F811
    import subprocess
    import sys
    from pathlib import Path

    s = table(cards, [NAME, 'Kinnan, Bonder Prodigy', 'Sol Ring'], [], [])
    source = put(s, NAME, 'battlefield')
    bonus = put(s, 'Kinnan, Bonder Prodigy', 'battlefield')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    source_oid, bonus_oid = (Plan(s.state, 'p1', cards, None).oid(c) for c in (source, bonus))
    index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    assert s.state.rules.decision.resume['step'] == 'staged_mana_option'
    act(s, 'p1', type='move', card_ids=[source.id, bonus.id], to={'player': 'p1', 'zone': 'graveyard'})
    path = tmp_path / 'masked-bonus.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
path,database,base,bonus=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
d=s.state.rules.decision
assert d.resume['step']=='staged_mana_option'
s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['0']})
units=s.state.players['p1'].mana_units
assert len([u for u in units if u.src==base and not u.generic_allowed])==5
assert [(u.sym,u.generic_allowed) for u in units if u.src==bonus]==[('W',True)]
ring=put(s,'Sol Ring','hand')
wait_priority(s,'p1')
s.perform('p1',{'type':'cast_spell','card_id':ring.id,'sources':[]})
assert len(s.state.players['p1'].mana_units)==5
assert all(u.src==base and not u.generic_allowed for u in s.state.players['p1'].mana_units)
answer(s)
assert s.state.cards[ring.id].zone=='p1:battlefield'
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), source_oid, bonus_oid],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_as_though_locked_origin_survives_true_cold_nested_mana_payment(cards, tmp_path):  # noqa: F811
    import subprocess
    import sys
    from pathlib import Path

    s = table(cards, [NAME, 'Mycosynth Lattice', 'Grizzly Bears', 'Forest'], [], [])
    source = put(s, NAME, 'battlefield')
    put(s, 'Mycosynth Lattice', 'battlefield')
    forest = put(s, 'Forest', 'battlefield')
    to_phase(s, 'main1', 4)
    wait_priority(s, 'p1')
    index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    spell = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='set_prefs', payment='self')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    path = tmp_path / 'as-though-origin.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,database,forest,spell=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
assert s.state.rules.decision.resume['step']=='pay_mana'
s.perform('p1',{'type':'activate_ability','card_id':forest,'ability':0})
if s.state.rules.decision is not None:
 d=s.state.rules.decision
 assert d.resume['step']=='pay_mana'
 s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
assert s.state.cards[spell].zone=='stack'
p=s.state.rules.payments[s.state.rules.object_id(spell)]
assert p.mana_spent=={'W':1,'G':1},p.mana_spent
assert {u.sym for u in s.state.players['p1'].mana_units}==set('UBRG')
assert all(not u.generic_allowed for u in s.state.players['p1'].mana_units)
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), forest.id, spell.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_actual_jegantha_activation_inside_payment_in_true_cold_process(cards, tmp_path):  # noqa: F811
    import subprocess
    import sys
    from pathlib import Path

    s, source = setup(cards)
    forest = put(s, 'Forest', 'battlefield')
    spell = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='set_prefs', payment='self')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    source_oid = Plan(s.state, 'p1', cards, None).oid(source)
    path = tmp_path / 'jegantha-activate-cold.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
path,database,source,oid,forest,spell=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p3')
assert s.state.rules.decision.resume['step']=='pay_mana'
index=next(a.index for a in Plan(s.state,'p1',repo,None).ch(s.state.cards[source]).abilities if 'Add ' in a.text)
s.perform('p1',{'type':'activate_ability','card_id':source,'ability':index})
assert s.state.rules.decision.resume['step']=='pay_mana'
units=s.state.players['p1'].mana_units
assert len(units)==5 and all(u.src==oid and not u.generic_allowed for u in units)
s.perform('p1',{'type':'activate_ability','card_id':forest,'ability':0})
if s.state.rules.decision is not None:
 d=s.state.rules.decision
 assert d.resume['step']=='pay_mana'
 s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
assert s.state.cards[spell].zone=='stack'
p=s.state.rules.payments[s.state.rules.object_id(spell)]
assert p.mana_spent=={'G':2}
units=s.state.players['p1'].mana_units
assert {u.sym for u in units}==set('WUBR')
assert all(u.src==oid and not u.generic_allowed for u in units)
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path),
                             source.id, source_oid, forest.id, spell.id], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr
