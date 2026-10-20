"""CR 107.3c / 607.3: text-defined activation X is determined rather than chosen."""
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
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/defined_activation_x_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='dax', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Prototype Portal', 'Soul Foundry', 'Elite Arcanist', 'Voodoo Doll'])
def test_text_defined_activation_x_is_supported(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def imprinted(cards, source_name, names, doubled=False, extra=()):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, [source_name, *names, *extra, *(['Panharmonicon'] if doubled else [])])
    if doubled:
        put(s, 'Panharmonicon', 'battlefield')
    chosen = [put(s, n, 'hand').id for n in names]
    source = put(s, source_name, 'hand')
    hold(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 10, 'U': 10})
    act(s, 'p1', type='cast_spell', card_id=source.id)
    for _ in range(12):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        ids = [o.id for o in d.options]
        if d.kind == 'order':
            pick(s, ids)
        elif 'pay' in ids:
            pick(s, ['pay'])
        elif 'yes' in ids:
            pick(s, ['yes'])
        else:
            pick(s, [next(c for c in chosen if c in ids)])
    assert all(s.state.cards[c].zone == 'p1:exile' for c in chosen)
    act(s, 'p1', type='clear_mana', player='p1')
    roundtrip(s)
    return s, s.state.cards[source.id], chosen


@pytest.mark.parametrize('name,payment,x', [('Prototype Portal', 'Sol Ring', 1), ('Prototype Portal', 'Ornithopter', 0), ('Soul Foundry', 'Grizzly Bears', 2)])
def test_fixed_linked_mana_value_pays_without_an_x_choice(cards, name, payment, x):
    from app.rules import casting

    s, source, chosen = imprinted(cards, name, [payment])
    if x:
        assert not any(h['card_id'] == source.id and h['ability'] == 1 for h in casting.activatable(s.state, 'p1', cards))
        act(s, 'p1', type='add_mana', player='p1', mana={'C': x})
    hint = next(h for h in casting.activatable(s.state, 'p1', cards) if h['card_id'] == source.id and h['ability'] == 1)
    assert not hint.get('x')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    roundtrip(s)
    settle(s)
    made = [c for c in s.state.cards.values() if c.is_token and c.name == payment]
    assert len(made) == 1 and s.state.cards[chosen[0]].zone == 'p1:exile'
    assert s.state.players['p1'].mana.get('C', 0) == 0
    roundtrip(s)


@pytest.mark.parametrize('wrong', [0, 2])
def test_defined_x_cannot_be_overridden_by_the_client(cards, wrong):
    s, source, _ = imprinted(cards, 'Prototype Portal', ['Sol Ring'])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match="isn't chosen"):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, x_value=wrong)
    assert before == s.state.model_dump(mode='json')
    roundtrip(s)


@pytest.mark.parametrize('name,names', [('Prototype Portal', ['Sol Ring', 'Arcane Signet']), ('Soul Foundry', ['Grizzly Bears', 'Llanowar Elves'])])
def test_multiple_imprinted_cards_sum_the_cost_and_each_get_a_copy(cards, name, names):
    from app.rules import casting

    s, source, _ = imprinted(cards, name, names, doubled=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    assert not any(h['card_id'] == source.id and h['ability'] == 1 for h in casting.activatable(s.state, 'p1', cards))
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    assert sorted(c.name for c in s.state.cards.values() if c.is_token) == sorted(names)
    assert s.state.players['p1'].mana.get('C', 0) == 0
    roundtrip(s)


@pytest.mark.parametrize('after', [False, True])
def test_only_cards_still_linked_in_exile_are_copied(cards, after):
    s, source, chosen = imprinted(cards, 'Prototype Portal', ['Sol Ring'])
    if after:
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    act(s, 'p1', type='move', card_ids=chosen, to={'player': 'p1', 'zone': 'graveyard'})
    if not after:
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    assert not any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


def test_linked_copy_can_resolve_after_the_source_leaves(cards):
    s, source, _ = imprinted(cards, 'Prototype Portal', ['Sol Ring'])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert sum(c.is_token and c.name == 'Sol Ring' for c in s.state.cards.values()) == 1
    roundtrip(s)


def test_elite_arcanist_pays_the_instant_mana_value_and_casts_a_copy(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave34b_activated import next_turn

    s, source, chosen = imprinted(cards, 'Elite Arcanist', ['Lightning Bolt'])
    next_turn(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 1 and d.options[0].label == 'Lightning Bolt'
    pick(s, [d.options[0].id])
    pick(s, ['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    assert s.state.cards[chosen[0]].zone == 'p1:exile'
    roundtrip(s)


def test_counter_defined_x_is_paid_twice_but_damage_reads_current_counters(cards):
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, ['Voodoo Doll'])
    source = put(s, 'Voodoo Doll', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='pin', value=2)
    hold(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, targets=['p2'])
    assert s.state.players['p1'].mana.get('C', 0) == 0
    act(s, 'p1', type='set_counter', card_id=source.id, kind='pin', value=3)
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_defined_x_is_set_before_cost_reductions_and_affordability_hints(cards):
    from app.rules import casting

    s, source, _ = imprinted(cards, 'Soul Foundry', ['Rumbling Baloth'], extra=['Zirda, the Dawnwaker'])
    put(s, 'Zirda, the Dawnwaker', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    assert any(h['card_id'] == source.id and h['ability'] == 1 and not h.get('x') for h in casting.activatable(s.state, 'p1', cards))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    assert s.state.players['p1'].mana.get('C', 0) == 0
    assert sum(c.is_token and c.name == 'Rumbling Baloth' for c in s.state.cards.values()) == 1
    roundtrip(s)


def test_fixed_x_cost_retains_x_for_restricted_mana(cards):
    from tests.test_rules_wave34b_activated import next_turn

    s, source, _ = imprinted(cards, 'Soul Foundry', ['Rumbling Baloth'], extra=['Rosheen Meanderer'])
    rosheen = put(s, 'Rosheen Meanderer', 'battlefield')
    next_turn(s)
    act(s, 'p1', type='activate_ability', card_id=rosheen.id, ability=0)
    assert s.state.players['p1'].mana_units
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    assert s.state.players['p1'].mana.get('C', 0) == 0
    assert sum(c.is_token and c.name == 'Rumbling Baloth' for c in s.state.cards.values()) == 1
    roundtrip(s)


def test_voodoo_doll_upkeep_and_untapped_end_step_still_resolve(cards):
    from tests.test_rules_wave34b_activated import next_turn, stops, to_phase

    s = build(cards, ['Voodoo Doll'])
    source = put(s, 'Voodoo Doll', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    next_turn(s)
    settle(s)
    assert s.state.cards[source.id].counters.get('pin') == 1
    stops(s)
    to_phase(s, 'end')
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].life == 39
    roundtrip(s)
