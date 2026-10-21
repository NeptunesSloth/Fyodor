"""CR 601.2c/f, 702.6: equip costs based on the chosen targets counters."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/target_counter_equip_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = "Warrior's Blades"


def test_blades_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_equip(cards, count=0, *, tax=False):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, [NAME, 'Grizzly Bears', 'Llanowar Elves', 'Suppression Field', 'Lightning Greaves'], [])
    source = put(s, NAME, 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Llanowar Elves', 'battlefield')
    if count:
        act(s, 'p1', type='set_counter', card_id=target.id, kind='+1/+1', value=count)
    if tax:
        put(s, 'Suppression Field', 'battlefield')
    return s, source, target, other, ability_index(s, source, 'Equip {3}')


@pytest.mark.parametrize('count', [0, 1, 3, 5])
@pytest.mark.parametrize('tax', [False, True])
def test_chosen_targets_counters_reduce_generic_equip_after_cost_increases(cards, count, tax):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, target, _, index = setup_equip(cards, count, tax=tax)
    cost = max(0, 3 + (2 if tax else 0) - count)
    if cost:
        mana(s, C=cost)
    roundtrip(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    assert not any(s.state.players['p1'].mana.values())
    settle(s)
    assert s.state.cards[source.id].attached_to == target.id
    assert chars(s, target).pt == (4 + count, 3 + count)
    roundtrip(s)


def test_discount_is_not_taken_from_an_unchosen_creature(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, source, _, other, index = setup_equip(cards, 5)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[other.id])
    assert s.state.cards[source.id].attached_to is None
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('count_after', [0, 5])
def test_equip_cost_is_locked_before_counters_change_during_resolution(cards, count_after):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    before = 5 if count_after == 0 else 0
    s, source, target, _, index = setup_equip(cards, before)
    if not before:
        mana(s, C=3)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    act(s, 'p1', type='set_counter', card_id=target.id, kind='+1/+1', value=count_after)
    roundtrip(s)
    settle(s)
    assert not any(s.state.players['p1'].mana.values())
    assert s.state.cards[source.id].attached_to == target.id
    roundtrip(s)


def test_other_counter_kinds_do_not_reduce_equip_cost(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle

    s, source, target, _, index = setup_equip(cards)
    act(s, 'p1', type='set_counter', card_id=target.id, kind='vow', value=5)
    mana(s, C=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    settle(s)
    assert s.state.cards[source.id].attached_to == target.id
    roundtrip(s)


def test_best_target_affordability_ignores_a_shrouded_high_counter_creature(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip

    s, source, target, _, index = setup_equip(cards, 5)
    greaves = put(s, 'Lightning Greaves', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[greaves.id], to=target.id)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    d = s.state.rules.decision
    assert d and target.id not in {o.id for o in d.options}
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.rules.decision.id == d.id and s.state.cards[source.id].attached_to is None
    roundtrip(s)


def test_real_cast_enter_trigger_then_free_equip_to_countered_creature(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, [NAME, 'Grizzly Bears'], [])
    source = put(s, NAME, 'hand')
    target = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=target.id, kind='+1/+1', value=3)
    mana(s, R=3, W=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d and 'p2' in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37 and s.state.players['p1'].life == 43
    index = ability_index(s, source, 'Equip {3}')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[target.id])
    settle(s)
    assert s.state.cards[source.id].attached_to == target.id
    roundtrip(s)
