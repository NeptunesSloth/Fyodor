"""Native actual-object graveyard keyword-cost grants."""
import pytest

from app.rules import coverage, mana_units
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_table_activation_modifiers52 import game


@pytest.fixture
def cards(settings):
    import json
    from pathlib import Path

    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import card, fixture_cards
    base = {c["name"]: c for c in fixture_cards()}
    for filename in ["dynamic_keyword_costs55_cards.json", "granted_foretell56_cards.json", "graveyard_cost_grants57_supports.json"]:
        for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / filename).read_text())):
            base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Araumi of the Dead Tide', 'Cursecloth Wrappings'])
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'

@pytest.mark.parametrize('source_name,keyword', [('Araumi of the Dead Tide', 'encore'), ('Cursecloth Wrappings', 'embalm')])
def test_native_granted_graveyard_ability(cards, source_name, keyword):
    s = game(cards, [source_name, 'Shivan Dragon', 'Ponder', 'Lightning Bolt'])
    source = put(s, source_name, 'battlefield')
    target = put(s, 'Shivan Dragon', 'graveyard')
    fodder = put(s, 'Ponder', 'graveyard')
    fodder2 = put(s, 'Lightning Bolt', 'graveyard')
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


def test_araumi_can_exile_its_target_as_cost_then_fizzles(cards):
    s = game(cards, ['Araumi of the Dead Tide', 'Shivan Dragon', 'Ponder'])
    source = put(s, 'Araumi of the Dead Tide', 'battlefield')
    target = put(s, 'Shivan Dragon', 'graveyard')
    fodder = put(s, 'Ponder', 'graveyard')
    s.state.rules.controlled_since[source.id].turn = 0
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index,
        targets=[target.id], cost_choices=[{'component': 1, 'cards': [target.id, fodder.id]}], sources=[])
    answer(s)
    assert target.zone == 'p1:exile' and fodder.zone == 'p1:exile'
    assert not any('encore' in a.keywords for a in Plan(s.state, 'p1', cards, None).ch(target).abilities)
    roundtrip(s)


def test_araumi_insufficient_payment_is_atomic(cards):
    from app.game.errors import ActionError
    s = game(cards, ['Araumi of the Dead Tide', 'Shivan Dragon', 'Ponder'])
    source = put(s, 'Araumi of the Dead Tide', 'battlefield')
    target = put(s, 'Shivan Dragon', 'graveyard')
    fodder = put(s, 'Ponder', 'graveyard')
    s.state.rules.controlled_since[source.id].turn = 0
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index,
            targets=[target.id], cost_choices=[{'component': 1, 'cards': [fodder.id]}], sources=[])
    assert not source.tapped and target.zone == 'p1:graveyard' and fodder.zone == 'p1:graveyard'
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize('source_name,keyword', [('Araumi of the Dead Tide', 'encore'), ('Cursecloth Wrappings', 'embalm')])
def test_true_cold_graveyard_grant(cards, tmp_path, source_name, keyword):
    import subprocess
    import sys
    from pathlib import Path

    from app.rules import graveyard_cost_grants57
    s = game(cards, [source_name, 'Shivan Dragon', 'Ponder', 'Lightning Bolt'])
    source = put(s, source_name, 'battlefield')
    target = put(s, 'Shivan Dragon', 'graveyard')
    fodder = put(s, 'Ponder', 'graveyard')
    other = put(s, 'Lightning Bolt', 'graveyard')
    s.state.rules.controlled_since[source.id].turn = 0
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[target.id],
        cost_choices=[{'component': 1, 'cards': [fodder.id, other.id]}] if keyword == 'encore' else [], sources=[])
    answer(s)
    granted = next(a for a in Plan(s.state, 'p1', cards, None).ch(target).abilities if keyword in a.keywords)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4, 'R': 2})
    saved = tmp_path/'game.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]), ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
act(s,'p1',type='activate_ability',card_id=sys.argv[3],ability=int(sys.argv[4]),sources=[])
answer(s)
assert s.state.cards[sys.argv[3]].zone=='p1:exile'
assert len([c for c in s.state.cards.values() if c.token and c.name=='Shivan Dragon'])==int(sys.argv[5])
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id, str(granted.index),
                             '2' if keyword == 'encore' else '1'],
                            cwd=Path(graveyard_cost_grants57.__file__).resolve().parents[2], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_granted_embalm_x_is_paid_but_not_copied_to_token(cards):
    s = game(cards, ['Cursecloth Wrappings', 'Stonecoil Serpent'])
    source = put(s, 'Cursecloth Wrappings', 'battlefield')
    target = put(s, 'Stonecoil Serpent', 'graveyard')
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[target.id], sources=[])
    answer(s)
    granted = next(a for a in Plan(s.state, 'p1', cards, None).ch(target).abilities if 'embalm' in a.keywords)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    act(s, 'p1', type='activate_ability', card_id=target.id, ability=granted.index, x_value=4, sources=[])
    answer(s)
    token = next(c for c in s.state.cards.values() if c.token and c.name == 'Stonecoil Serpent')
    assert token.counters.get('+1/+1', 0) == 0
    ch = Plan(s.state, 'p1', cards, None).ch(token)
    assert ch.pt == (1, 1) and not ch.mana_cost and 'Zombie' in ch.subtypes
    roundtrip(s)


def test_graveyard_grant_cannot_follow_a_new_object(cards):
    s = game(cards, ['Cursecloth Wrappings', 'Shivan Dragon'])
    source = put(s, 'Cursecloth Wrappings', 'battlefield')
    target = put(s, 'Shivan Dragon', 'graveyard')
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[target.id], sources=[])
    answer(s)
    assert any('embalm' in a.keywords for a in Plan(s.state, 'p1', cards, None).ch(target).abilities)
    for zone in ['hand', 'graveyard']:
        act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': zone})
    assert not any('embalm' in a.keywords for a in Plan(s.state, 'p1', cards, None).ch(target).abilities)
    roundtrip(s)


def test_graveyard_grant_expires_at_end_of_turn(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards, ['Cursecloth Wrappings', 'Shivan Dragon'])
    source = put(s, 'Cursecloth Wrappings', 'battlefield')
    target = put(s, 'Shivan Dragon', 'graveyard')
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[target.id], sources=[])
    answer(s)
    assert any('embalm' in a.keywords for a in Plan(s.state, 'p1', cards, None).ch(target).abilities)
    to_phase(s, 'main1', 5)
    assert not any('embalm' in a.keywords for a in Plan(s.state, 'p1', cards, None).ch(target).abilities)
    roundtrip(s)


def test_encore_x_payment_does_not_change_token_x(cards):
    s = game(cards, ['Araumi of the Dead Tide', 'Stonecoil Serpent', 'Ponder', 'Lightning Bolt', 'Glorious Anthem'])
    source = put(s, 'Araumi of the Dead Tide', 'battlefield')
    put(s, 'Glorious Anthem', 'battlefield')
    target = put(s, 'Stonecoil Serpent', 'graveyard')
    fodder = put(s, 'Ponder', 'graveyard')
    other = put(s, 'Lightning Bolt', 'graveyard')
    s.state.rules.controlled_since[source.id].turn = 0
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[target.id],
        cost_choices=[{'component': 1, 'cards': [fodder.id, other.id]}], sources=[])
    answer(s)
    granted = next(a for a in Plan(s.state, 'p1', cards, None).ch(target).abilities if 'encore' in a.keywords)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    act(s, 'p1', type='activate_ability', card_id=target.id, ability=granted.index, x_value=4, sources=[])
    answer(s)
    tokens = [c for c in s.state.cards.values() if c.token and c.name == 'Stonecoil Serpent']
    assert len(tokens) == 2
    for token in tokens:
        assert token.counters.get('+1/+1', 0) == 0
        assert Plan(s.state, 'p1', cards, None).ch(token).pt == (1, 1)
    assert not mana_units.visible_pool(s.state, 'p1')
    roundtrip(s)


def test_no_mana_cost_card_has_no_payable_granted_keyword(cards):
    s = game(cards, ['Cursecloth Wrappings', 'Dryad Arbor'])
    source = put(s, 'Cursecloth Wrappings', 'battlefield')
    target = put(s, 'Dryad Arbor', 'graveyard')
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[target.id], sources=[])
    answer(s)
    assert not any('embalm' in a.keywords for a in Plan(s.state, 'p1', cards, None).ch(target).abilities)
    assert target.zone == 'p1:graveyard'
    roundtrip(s)
