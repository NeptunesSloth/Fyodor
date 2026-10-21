"""Native first qualifying activation cost history and actual selected targets."""
import pytest

from app.game.errors import ActionError
from app.rules import mana_units
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_targeting_sources77 import setup


@pytest.fixture
def cards(settings):
    import json
    from pathlib import Path
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import card, fixture_cards
    base = {c["name"]: c for c in fixture_cards()}
    for filename in ["targeting_sources77_cards.json", "first_target_activation_cost58_supports.json"]:
        for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / filename).read_text())):
            base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def equip(s, gear, target):
    act(s, 'p1', type='activate_ability', card_id=gear.id, ability=2, targets=[target.id], sources=[])
    settle(s)


def test_first_qualifying_equip_reduced_second_not(cards):
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    equip(s, gear, bear)
    assert gear.attached_to == bear.id and not mana_units.visible_pool(s.state, 'p1')
    with pytest.raises(ActionError):
        equip(s, gear, elf)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    equip(s, gear, elf)
    assert gear.attached_to == elf.id and not mana_units.visible_pool(s.state, 'p1')
    roundtrip(s)


def test_prior_qualifying_activation_before_hojo_enters_counts(cards):
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    equip(s, gear, bear)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    with pytest.raises(ActionError):
        equip(s, gear, elf)
    assert gear.attached_to == bear.id
    roundtrip(s)


def test_legacy_unknown_current_turn_history_cannot_guess_first(cards):
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    s.state.rules.target_activation_history_turn = None
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        equip(s, gear, bear)
    assert s.state.model_dump_json() == before


def test_own_creature_is_second_of_actual_x_multiple_targets(cards):
    from app.rules.plan import Plan
    from tests.test_rules_table_activation_modifiers52 import game
    s = game(cards, ['Professor Hojo', 'Magus of the Candelabra', 'Treetop Village', 'Forest'])
    put(s, 'Professor Hojo', 'battlefield')
    magus = put(s, 'Magus of the Candelabra', 'battlefield')
    tree = put(s, 'Treetop Village', 'battlefield')
    forest = put(s, 'Forest', 'battlefield')
    s.state.rules.controlled_since[magus.id].turn = 0
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(tree).abilities if a.kind == 'activated')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    act(s, 'p1', type='activate_ability', card_id=tree.id, ability=ability.index, sources=[])
    settle(s)
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(magus).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=magus.id, ability=ability.index, x_value=2,
        targets=[forest.id, tree.id], sources=[])
    settle(s)
    assert not tree.tapped and not mana_units.visible_pool(s.state, 'p1')
    assert s.state.rules.once_per_turn['activated:p1:controlled_creature_target'] == s.state.turn.number
    roundtrip(s)


def test_target_sacrificed_as_payment_still_consumes_first_qualification(cards):
    from app.rules.plan import Plan
    from tests.test_rules_table_activation_modifiers52 import game
    s = game(cards, ['Professor Hojo', 'Attrition', 'Grizzly Bears', 'Silver-Inlaid Dagger'])
    put(s, 'Professor Hojo', 'battlefield')
    source = put(s, 'Attrition', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[bear.id],
        cost_choices=[{'component': 1, 'cards': [bear.id]}], sources=[])
    settle(s)
    assert bear.zone == 'p1:graveyard'
    assert s.state.rules.once_per_turn['activated:p1:controlled_creature_target'] == s.state.turn.number
    roundtrip(s)
