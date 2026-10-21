"""CR 113.10, 611.3a: abilities borrowed from a qualifying public library top."""
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
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/top_borrowed_abilities_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='tba', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Conspicuous Snoop', 'Skill Borrower'])
def test_library_top_lenders_are_supported(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', ['Conspicuous Snoop', 'Skill Borrower'])
def test_top_card_ability_is_borrowed_and_replaced_when_the_top_changes(cards, name):
    from app.rules import abilities_of
    from app.rules.plan import Plan
    from tests.test_rules_permissions import put as place
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, [name, 'Goblin Fireslinger', 'Sol Ring'])
    source = put(s, name, 'battlefield')
    next_turn(s)
    lender = place(s, 'Goblin Fireslinger', 'library', position='top')
    assert s.view('p2')['zones']['p1:library']['known'] == [[0, lender.id]]
    borrowed = [a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.index >= abilities_of.BORROWED]
    assert len(borrowed) == 1
    old = borrowed[0].index
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=old, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 39
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    ring = place(s, 'Sol Ring', 'library', position='top')
    assert s.view('p2')['zones']['p1:library']['known'] == [[0, ring.id]]
    new = [a for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).abilities if a.index >= abilities_of.BORROWED]
    assert old not in [a.index for a in new]
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=old, targets=['p2'])
    assert before == s.state.model_dump(mode='json')
    if name == 'Skill Borrower':
        assert len(new) == 1 and new[0].kind == 'mana'
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=new[0].index)
        assert mana_pool(s, 'p1').get('C', 0) == 2
    else:
        assert not new
    roundtrip(s)


@pytest.mark.parametrize('name', ['Conspicuous Snoop', 'Skill Borrower'])
def test_wrong_top_type_or_empty_library_grants_no_abilities(cards, name):
    from app.rules import abilities_of
    from app.rules.plan import Plan
    from tests.test_rules_permissions import put as place

    s = build(cards, [name, 'Goblin Fireslinger'])
    source = put(s, name, 'battlefield')
    place(s, 'Goblin Fireslinger', 'library', position='top')
    assert any(a.index >= abilities_of.BORROWED for a in Plan(s.state, 'p1', cards, None).ch(source).abilities)
    place(s, 'Forest', 'library', position='top')
    assert not any(a.index >= abilities_of.BORROWED for a in Plan(s.state, 'p1', cards, None).ch(source).abilities)
    library = list(s.state.zones['p1:library'])
    act(s, 'p1', type='move', card_ids=library, to={'player': 'p1', 'zone': 'graveyard'})
    assert not any(a.index >= abilities_of.BORROWED for a in Plan(s.state, 'p1', cards, None).ch(source).abilities)
    assert not s.view('p2')['zones']['p1:library'].get('known')
    roundtrip(s)


@pytest.mark.parametrize('name', ['Conspicuous Snoop', 'Skill Borrower'])
def test_borrowed_tap_ability_obeys_borrowers_summoning_sickness(cards, name):
    from app.rules import abilities_of
    from app.rules.plan import Plan
    from tests.test_rules_permissions import put as place

    s = build(cards, [name, 'Goblin Fireslinger'])
    source = put(s, name, 'battlefield')
    place(s, 'Goblin Fireslinger', 'library', position='top')
    ab = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.index >= abilities_of.BORROWED)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='summoning sickness'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ab.index, targets=['p2'])
    assert before == s.state.model_dump(mode='json')
    roundtrip(s)


def test_snoop_can_cast_the_goblin_and_then_loses_its_borrowed_ability(cards):
    from app.rules import abilities_of
    from app.rules.plan import Plan
    from tests.test_rules_permissions import put as place

    s = build(cards, ['Conspicuous Snoop', 'Goblin Fireslinger'])
    source = put(s, 'Conspicuous Snoop', 'battlefield')
    lender = place(s, 'Goblin Fireslinger', 'library', position='top')
    assert any(a.index >= abilities_of.BORROWED for a in Plan(s.state, 'p1', cards, None).ch(source).abilities)
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=lender.id)
    settle(s)
    assert s.state.cards[lender.id].zone == 'p1:battlefield'
    assert not any(a.index >= abilities_of.BORROWED for a in Plan(s.state, 'p1', cards, None).ch(source).abilities)
    top = s.state.zones['p1:library'][0]
    assert s.view('p2')['zones']['p1:library']['known'] == [[0, top]]
    roundtrip(s)


def test_borrowed_counter_defined_cost_reads_the_borrower(cards):
    from app.rules import abilities_of
    from app.rules.plan import Plan
    from tests.test_rules_permissions import put as place
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ['Skill Borrower', 'Voodoo Doll'])
    source = put(s, 'Skill Borrower', 'battlefield')
    next_turn(s)
    lender = place(s, 'Voodoo Doll', 'library', position='top')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='pin', value=2)
    ab = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.index >= abilities_of.BORROWED)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ab.index, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 38 and mana_pool(s, 'p1').get('C', 0) == 0
    assert s.state.cards[source.id].tapped and not s.state.cards[lender.id].tapped
    roundtrip(s)


def test_borrowed_linked_ability_has_a_new_empty_link_and_zero_defined_cost(cards):
    from app.rules import abilities_of, defined_activation_x, scripts
    from app.rules.plan import Plan
    from tests.test_rules_permissions import put as place

    s = build(cards, ['Skill Borrower', 'Prototype Portal'])
    source = put(s, 'Skill Borrower', 'battlefield')
    place(s, 'Prototype Portal', 'library', position='top')
    ch = Plan(s.state, 'p1', cards, None).ch(source)
    ab = next(a for a in ch.abilities if a.index >= abilities_of.BORROWED)
    assert not abilities_of.manual(ab) and scripts.define(ab, ch) is not None
    value = defined_activation_x.spec(ab, ch.name)
    assert value and value['borrowed_link_scope']
    assert defined_activation_x.evaluate(Plan(s.state, 'p1', cards, None), source, value) == 0
    roundtrip(s)


@pytest.mark.parametrize('name', ['Conspicuous Snoop', 'Skill Borrower'])
def test_library_top_follows_the_borrowers_current_controller(cards, name):
    from app.rules import abilities_of
    from app.rules.plan import Plan
    from tests.test_rules_permissions import put as place
    from tests.test_rules_wave34b_activated import stops, to_phase

    s = build(cards, [name], bob=((1, 'Goblin Fireslinger'), (10, 'Island')))
    source = put(s, name, 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    stops(s)
    to_phase(s, 'main1', turn=2)
    lender = place(s, 'Goblin Fireslinger', 'library', pid='p2', position='top')
    ab = next(a for a in Plan(s.state, 'p2', cards, None).ch(s.state.cards[source.id]).abilities if a.index >= abilities_of.BORROWED)
    assert s.view('p1')['zones']['p2:library']['known'] == [[0, lender.id]]
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=ab.index, targets=['p1'])
    settle(s)
    assert s.state.players['p1'].life == 39
    roundtrip(s)


@pytest.mark.parametrize('name', ['Conspicuous Snoop', 'Skill Borrower'])
def test_a_top_card_that_changes_zones_has_new_borrowed_ability_indices(cards, name):
    from app.rules import abilities_of
    from app.rules.plan import Plan
    from tests.test_rules_permissions import put as place

    s = build(cards, [name, 'Goblin Fireslinger'])
    source = put(s, name, 'battlefield')
    lender = place(s, 'Goblin Fireslinger', 'library', position='top')
    old = next(a.index for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.index >= abilities_of.BORROWED)
    act(s, 'p1', type='move', card_ids=[lender.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[lender.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    new = next(a.index for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.index >= abilities_of.BORROWED)
    assert new != old
    roundtrip(s)
