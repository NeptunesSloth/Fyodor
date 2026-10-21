"""Ordered graveyard guards read the current source incarnation at both checks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Nether Shadow', 'Death Spark', 'Ashen Ghoul', 'Krovikan Horror']


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/ordered_graveyard53_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ogy', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    names = [*NAMES, 'Grizzly Bears', 'Llanowar Elves', 'Goblin Piker', 'Sol Ring', 'Forest', 'Lightning Bolt', 'Wrath of God']
    s = table(cards, names, names, names)
    to_phase(s, 'main1', 4)
    source = put(s, name, 'graveyard')
    return s, source


def three_above(s):
    return [put(s, name, 'graveyard') for name in ['Grizzly Bears', 'Llanowar Elves', 'Goblin Piker']]


def answer(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def begin(s, name):
    to_phase(s, 'end', 4) if name == 'Krovikan Horror' else to_phase(s, 'upkeep', 7)
    if name == 'Death Spark':
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    settle(s)


def activate_ghoul(s, source):
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', ['Nether Shadow', 'Ashen Ghoul'])
def test_exact_three_creatures_above_restore_and_have_haste(cards, name):
    from tests.test_rules_conditional_prevention import attack, damage

    s, source = setup(cards, name)
    three_above(s)
    put(s, 'Sol Ring', 'graveyard')
    begin(s, name)
    if name == 'Ashen Ghoul':
        activate_ghoul(s, source)
    else:
        answer(s, ['yes'])
    assert source.zone == 'p1:battlefield'
    before = s.state.players['p2'].life
    attack(s, [source], target='p2', turn=7)
    damage(s)
    assert s.state.players['p2'].life == before - (1 if name == 'Nether Shadow' else 3)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Nether Shadow', 'Ashen Ghoul'])
def test_creatures_below_source_and_opponents_do_not_count(cards, name):
    s, source = setup(cards, name)
    three_above(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    put(s, 'Grizzly Bears', 'graveyard', 'p2')
    put(s, 'Sol Ring', 'graveyard')
    begin(s, name)
    assert s.state.rules.decision is None
    if name == 'Ashen Ghoul':
        act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
        assert s.state.model_dump_json() == before
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Death Spark', 'Krovikan Horror'])
@pytest.mark.parametrize('direct', [True, False])
def test_directly_above_requires_adjacent_creature(cards, name, direct):
    s, source = setup(cards, name)
    put(s, 'Grizzly Bears', 'graveyard')
    if not direct:
        put(s, 'Sol Ring', 'graveyard')
    begin(s, name)
    if direct:
        answer(s, ['yes'])
        assert source.zone == 'p1:hand'
    else:
        assert s.state.rules.decision is None and source.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Nether Shadow', 'Death Spark', 'Krovikan Horror'])
def test_intervening_if_rechecks_removed_creature_before_resolution(cards, name):
    s, source = setup(cards, name)
    above = three_above(s) if name == 'Nether Shadow' else [put(s, 'Grizzly Bears', 'graveyard')]
    act(s, 'p1', type='set_prefs', hold_priority=True)
    to_phase(s, 'end', 4) if name == 'Krovikan Horror' else to_phase(s, 'upkeep', 7)
    assert s.state.zones.get('stack')
    for obj in above:
        act(s, 'p1', type='move', card_ids=[obj.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert source.zone == 'p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name', ['Nether Shadow', 'Death Spark', 'Krovikan Horror'])
def test_new_graveyard_incarnation_does_not_satisfy_original_trigger(cards, name):
    s, source = setup(cards, name)
    three_above(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    to_phase(s, 'end', 4) if name == 'Krovikan Horror' else to_phase(s, 'upkeep', 7)
    assert s.state.zones.get('stack')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    for obj in ['Grizzly Bears', 'Llanowar Elves', 'Goblin Piker']:
        c = next(c for c in s.state.cards.values() if c.name == obj and c.zone == 'p1:graveyard')
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'hand'})
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert source.zone == 'p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name', ['Nether Shadow', 'Ashen Ghoul'])
def test_two_creatures_above_are_insufficient(cards, name):
    s, source = setup(cards, name)
    put(s, 'Grizzly Bears', 'graveyard')
    put(s, 'Llanowar Elves', 'graveyard')
    put(s, 'Sol Ring', 'graveyard')
    begin(s, name)
    assert s.state.rules.decision is None
    if name == 'Ashen Ghoul':
        act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
        assert s.state.model_dump_json() == before
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Nether Shadow', 'Death Spark', 'Krovikan Horror'])
def test_optional_return_or_payment_can_be_declined(cards, name):
    s, source = setup(cards, name)
    three_above(s)
    begin(s, name)
    answer(s, ['no'])
    assert source.zone == 'p1:graveyard'
    assert s.state.players['p1'].mana == ({'C': 1} if name == 'Death Spark' else {})
    roundtrip(s)


def test_ghoul_activation_condition_is_not_rechecked_on_resolution(cards):
    s, source = setup(cards, 'Ashen Ghoul')
    above = three_above(s)
    begin(s, 'Ashen Ghoul')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    assert s.state.zones.get('stack')
    for obj in above:
        act(s, 'p1', type='move', card_ids=[obj.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


def test_death_spark_spell_and_horror_sacrifice_establish_actual_adjacent_card(cards):
    from app.rules import costs, scripts
    from app.rules.plan import Plan

    s, source = setup(cards, 'Death Spark')
    source = put(s, 'Death Spark', 'hand')
    before = s.state.players['p2'].life
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'], sources=[])
    settle(s)
    assert source.zone == 'p1:graveyard' and s.state.players['p2'].life == before - 1
    horror = put(s, 'Krovikan Horror', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    ch = Plan(s.state, 'p1', cards, None).ch(horror)
    ab = next(a for a in ch.abilities if a.kind == 'activated')
    cost = scripts.parse_ability_cost(ab.cost, card_name=ch.name)
    component = next(i for i, c in enumerate(cost.components) if c.kind == costs.SACRIFICE and c.selector)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=horror.id, ability=ab.index,
        targets=['p2'], sources=[], cost_choices=[{'component': component, 'cards': [bear.id]}])
    settle(s)
    assert s.state.zones['p1:graveyard'][-2:] == [source.id, bear.id]
    assert s.state.players['p2'].life == before - 2
    begin(s, 'Death Spark')
    answer(s, ['yes'])
    assert source.zone == 'p1:hand' and not s.state.players['p1'].mana
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_original_graveyard_guard_and_return(cards, tmp_path, name):
    import subprocess
    import sys

    s, source = setup(cards, name)
    above = three_above(s)
    begin(s, name)
    if name == 'Ashen Ghoul':
        act(s, 'p1', type='set_prefs', hold_priority=True)
        act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
        for obj in above:
            act(s, 'p1', type='move', card_ids=[obj.id], to={'player': 'p1', 'zone': 'exile'})
    saved = tmp_path / 'ordered-graveyard.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_placements import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
name,source=sys.argv[3:5]
if name=='Ashen Ghoul':
 settle(s)
else:
 d=s.state.rules.decision
 assert d is not None
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes'])
 settle(s)
assert s.state.cards[source].zone==('p1:battlefield' if name in ['Nether Shadow','Ashen Ghoul'] else 'p1:hand')
roundtrip(s)
repo.close()
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, source.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('phase,turn,battlefield', [('main1', 4, False), ('upkeep', 5, False), ('upkeep', 7, True)])
def test_ghoul_restriction_requires_own_upkeep_and_actual_graveyard(cards, phase, turn, battlefield):
    from tests.test_rules_bandmate_references import wait_priority

    s, source = setup(cards, 'Ashen Ghoul')
    three_above(s)
    if battlefield:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    to_phase(s, phase, turn)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_horror_opponents_end_step_returns_to_its_owners_hand(cards):
    s, source = setup(cards, 'Krovikan Horror')
    put(s, 'Grizzly Bears', 'graveyard')
    to_phase(s, 'end', 4)
    settle(s)
    answer(s, ['no'])
    assert source.zone == 'p1:graveyard'
    to_phase(s, 'end', 5)
    settle(s)
    answer(s, ['yes'])
    assert source.zone == 'p1:hand' and source.id not in s.state.zones['p2:hand']
    roundtrip(s)
