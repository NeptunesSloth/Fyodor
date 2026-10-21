"""Native destination-independent attack costs and requirement solvers."""
from pathlib import Path

import pytest

from tests.test_rules_random_previous_combat44 import (
    test_global_attack_cost_allows_declining_attack_but_cannot_pay_for_wrong_destination,  # noqa: F401,E501
)


@pytest.fixture()
def cards(settings):
    import json

    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import card, fixture_cards
    from tests.test_rules_random_previous_combat44 import DATA, ROWS
    from tests.test_rules_wave5c_combat import EXTRA

    base = {c['name']: c for c in [*fixture_cards(), *EXTRA]}
    rows = [*DATA, *ROWS]
    for file in ['creature_combat_cost_cards.json', 'nonmana_declaration_costs_cards.json']:
        rows += json.loads((Path(__file__).parent / 'fixtures' / file).read_text())
    for i, row in enumerate(rows):
        base[row['name']] = card(row['name'], set_code='gc44', number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def table(cards):
    from tests.test_rules_random_previous_combat44 import DATA, ROWS
    from tests.test_rules_wave30m_durations import stops, three
    from tests.test_rules_wave31d_spell_copies import hold
    names = [r['name'] for r in [*DATA, *ROWS]] + ['Crawlspace', 'Kardur, Doomscourge', 'Qal Sisma Behemoth', 'Exalted Dragon', 'Hollow Warrior', 'Forest', 'Grizzly Bears']
    s = three(cards, names, names, names)
    hold(s)
    stops(s, 'begin_combat', 'declare_attackers', 'declare_blockers')
    return s


@pytest.mark.parametrize('cap', [False, True])
def test_global_plus_destination_cost_still_allows_free_destination_requirement_exception(cards, monkeypatch, cap):
    from app.rules.mana_units import visible_pool
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_player_protection import priority
    from tests.test_rules_random_previous_combat44 import NAME, begin_combat
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards)
    source = put(s, NAME, 'battlefield')
    tax = put(s, 'War Tax', 'battlefield', 'p2')
    put(s, 'Ghostly Prison', 'battlefield', 'p2')
    if cap:
        put(s, 'Crawlspace', 'battlefield', 'p2')
    monkeypatch.setattr('secrets.SystemRandom.choice', lambda rng, pool: 'p2')
    begin_combat(s, 1)
    priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2, 'U': 1})
    act(s, 'p2', type='activate_ability', card_id=tax.id, ability=0, x_value=2, sources=[])
    settle(s)
    priority(s, 'p1')
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p3'}], sources=[])
    assert visible_pool(s.state, 'p1') == {}
    assert s.state.cards[source.id].attacking.id == 'p3'
    roundtrip(s)


@pytest.mark.parametrize('kind', ['mana', 'nonmana'])
@pytest.mark.parametrize('declared', [False, True])
def test_goad_global_fee_is_accepted_per_creature_only_with_native_payment_atomicity(cards, kind, declared):
    from app.game.errors import ActionError
    from app.rules.mana_units import visible_pool
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_source_quality_protection import spell
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards)
    source = put(s, 'Qal Sisma Behemoth' if kind == 'mana' else 'Exalted Dragon', 'battlefield', 'p2')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    land = put(s, 'Forest', 'battlefield', 'p2')
    spell(s, 'Kardur, Doomscourge', {'C': 2, 'B': 1, 'R': 1})
    settle(s)
    to_phase(s, 'declare_attackers', turn=2)
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2})
    if declared:
        with pytest.raises(ActionError):
            act(s, 'p2', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p1'}, {'card_id': other.id, 'target': 'p3'}])
        assert visible_pool(s.state, 'p2') == {'C': 2}
        assert s.state.cards[land.id].zone == 'p2:battlefield'
        kwargs = {'sources': []} if kind == 'mana' else {'cost_choices': [{'component': 0, 'cards': [land.id]}]}
        act(s, 'p2', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p3'}, {'card_id': other.id, 'target': 'p3'}], **kwargs)
        assert s.state.cards[source.id].attacking.id == 'p3'
        if kind == 'mana':
            assert visible_pool(s.state, 'p2') == {}
        else:
            assert s.state.cards[land.id].zone == 'p2:graveyard'
    else:
        act(s, 'p2', type='declare_attackers', attackers=[{'card_id': other.id, 'target': 'p3'}])
        assert s.state.cards[source.id].attacking is None
        assert visible_pool(s.state, 'p2') == {'C': 2}
        assert s.state.cards[land.id].zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('solver', ['cap', 'companion'])
def test_global_fee_chosen_destination_enforced_by_other_native_requirement_solvers(cards, monkeypatch, solver):
    from app.game.errors import ActionError
    from app.rules.mana_units import visible_pool
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_effects import token
    from tests.test_rules_player_protection import priority
    from tests.test_rules_random_previous_combat44 import NAME, begin_combat
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards)
    source = put(s, NAME, 'battlefield')
    tax = put(s, 'War Tax', 'battlefield', 'p2')
    companion = None
    if solver == 'cap':
        put(s, 'Crawlspace', 'battlefield', 'p2')
    else:
        companion = token(s, 'p1', 'Companion', text="Haste\nThis creature can't attack alone.")
    monkeypatch.setattr('secrets.SystemRandom.choice', lambda rng, pool: 'p2')
    begin_combat(s, 1)
    priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2, 'U': 1})
    act(s, 'p2', type='activate_ability', card_id=tax.id, ability=0, x_value=2, sources=[])
    settle(s)
    priority(s, 'p1')
    to_phase(s, 'declare_attackers', turn=1)
    extra = [{'card_id': companion.id, 'target': 'p3'}] if companion is not None else []
    amount = 4 if companion is not None else 2
    act(s, 'p1', type='add_mana', player='p1', mana={'C': amount})
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p3'}, *extra])
    assert visible_pool(s.state, 'p1') == {'C': amount}
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}, *extra], sources=[])
    assert visible_pool(s.state, 'p1') == {}
    roundtrip(s)
