"""Exact exile-batch permissions and delayed remaining-card damage."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/nimbus_troll_activation_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()







def setup(cards, name):
    s = table(cards, [name, 'Gigantosaurus', 'Colossal Dreadmaw', 'Char-Rumbler', "Faith's Fetters", 'Murder'],
              ['Gigantosaurus'])
    source = put(s, name, 'battlefield')
    ab = next(a for a in Plan(s.state, 'p1', s.cards, None).ch(source).abilities if a.kind == 'activated')
    return s, source, ab.index


@pytest.mark.parametrize('name,cost', [('Knight of the Holy Nimbus', 2), ('Clergy of the Holy Nimbus', 1)])
def test_opponents_only_actor_and_hints_follow_current_controller(cards, name, cost):
    s, source, index = setup(cards, name)
    mana(s, C=cost)
    assert not any(a['card_id'] == source.id for a in casting.activatable(s.state, 'p1', s.cards, check_priority=False))
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    assert s.state.model_dump(mode='json') == before
    mana(s, C=cost, pid='p2')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    assert any(a['card_id'] == source.id for a in casting.activatable(s.state, 'p2', s.cards, check_priority=False))
    act(s, 'p1', type='pass_priority')
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=index)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].tapped
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    mana(s, C=cost, pid='p2')
    assert not any(a['card_id'] == source.id for a in casting.activatable(s.state, 'p2', s.cards, check_priority=False))
    assert any(a['card_id'] == source.id for a in casting.activatable(s.state, 'p1', s.cards, check_priority=False))
    for _ in range(3):
        if s.state.rules.priority in (None, 'p1'):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    settle(s)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Knight of the Holy Nimbus', 'Clergy of the Holy Nimbus'])
def test_opponents_permission_does_not_bypass_nonmana_activation_prohibition(cards, name):
    s, source, index = setup(cards, name)
    aura = put(s, "Faith's Fetters", 'hand')
    mana(s, C=3, W=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[source.id])
    settle(s)
    mana(s, C=2, pid='p2')
    act(s, 'p1', type='pass_priority')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p2', type='activate_ability', card_id=source.id, ability=index)
    assert s.state.model_dump(mode='json') == before
    assert not any(a['card_id'] == source.id for a in casting.activatable(s.state, 'p2', s.cards, check_priority=False))
    roundtrip(s)


@pytest.mark.parametrize('source_tapped', [False, True])
def test_troll_taps_other_summoning_sick_creatures_without_tapping_itself(cards, source_tapped):
    s, source, index = setup(cards, 'Mossbridge Troll')
    if source_tapped:
        act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    giant = put(s, 'Gigantosaurus', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index,
        cost_choices=[{'component': 0, 'cards': [giant.id]}])
    settle(s)
    assert s.state.cards[giant.id].tapped and s.state.cards[source.id].tapped == source_tapped
    assert Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[source.id]).pt == (25, 25)
    roundtrip(s)


def test_negative_power_is_included_in_selected_sum_but_not_forced_for_availability(cards):
    s, source, index = setup(cards, 'Mossbridge Troll')
    giant = put(s, 'Gigantosaurus', 'battlefield')
    negative = put(s, 'Char-Rumbler', 'battlefield')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index,
            cost_choices=[{'component': 0, 'cards': [giant.id, negative.id]}])
    assert s.state.model_dump(mode='json') == before
    assert any(a['card_id'] == source.id for a in casting.activatable(s.state, 'p1', s.cards, check_priority=False))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    d = s.state.rules.decision
    assert d is not None and negative.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[giant.id])
    settle(s)
    assert s.state.cards[giant.id].tapped and not s.state.cards[negative.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('wrong', ['source', 'opponent', 'tapped', 'below'])
def test_troll_rejects_ineligible_or_insufficient_payment_atomically(cards, wrong):
    s, source, index = setup(cards, 'Mossbridge Troll')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2' if wrong == 'opponent' else 'p1')
    small = put(s, 'Colossal Dreadmaw', 'battlefield')
    if wrong == 'tapped':
        act(s, 'p1', type='tap', card_ids=[giant.id], tapped=True)
    selected = [source.id, small.id] if wrong == 'source' else [small.id] if wrong == 'below' else [giant.id]
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index,
            cost_choices=[{'component': 0, 'cards': selected}])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


@pytest.mark.parametrize('name', ['Knight of the Holy Nimbus', 'Clergy of the Holy Nimbus', 'Mossbridge Troll'])
def test_canonical_family_fully_supported_after_shared_regeneration_core(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
