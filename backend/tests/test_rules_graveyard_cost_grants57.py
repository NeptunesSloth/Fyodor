"""Native actual-object graveyard keyword-cost grants."""
import pytest
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_granted_foretell56 import cards  # noqa: F401
from tests.test_rules_table_activation_modifiers52 import game

@pytest.mark.parametrize('name', ['Araumi of the Dead Tide', 'Cursecloth Wrappings'])
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'

@pytest.mark.parametrize('source_name,keyword', [('Araumi of the Dead Tide', 'encore'), ('Cursecloth Wrappings', 'embalm')])
def test_native_granted_graveyard_ability(cards, source_name, keyword):
    s = game(cards, [source_name, 'Shivan Dragon', 'Ponder'])
    source = put(s, source_name, 'battlefield')
    target = put(s, 'Shivan Dragon', 'graveyard')
    fodder = put(s, 'Ponder', 'graveyard')
    fodder2 = put(s, 'Ponder', 'graveyard')
    s.state.rules.controlled_since[source.id].turn = 0
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    choices = [{'component': 1, 'cards': [fodder.id, fodder2.id]}] if keyword == 'encore' else []
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index,
        targets=[target.id], cost_choices=choices, sources=[])
    answer(s)
    granted = next(a for a in Plan(s.state, 'p1', cards, None).ch(target).abilities if keyword in a.keywords)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4, 'R': 2})
    act(s, 'p1', type='activate_ability', card_id=target.id, ability=granted.index, sources=[])
    answer(s)
    assert target.zone == 'p1:exile'
    tokens = [c for c in s.state.cards.values() if c.token and c.name == 'Shivan Dragon']
    assert len(tokens) == (2 if keyword == 'encore' else 1)
    ch = Plan(s.state, 'p1', cards, None).ch(tokens[0])
    if keyword == 'embalm':
        assert ch.colors == frozenset({'W'}) and 'Zombie' in ch.subtypes and not ch.mana_cost
    else:
        assert 'haste' in ch.keywords
    roundtrip(s)
