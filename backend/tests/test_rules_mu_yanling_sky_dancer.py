"""Liliana's nested-quotation emblem grants an additional mana ability to Swamps."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import characteristics, coverage
from app.rules.layers import derive
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave31d_spell_copies import hold

NAME = 'Mu Yanling, Sky Dancer'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/mu_yanling_sky_dancer_cards.json').read_text())
    for i, c in enumerate(rows):
        base[c['name']] = card(c['name'], set_code='mys', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = build(cards, [NAME, 'Island', 'Forest', 'Dryad of the Ilysian Grove', 'Living Lands', 'Tropical Island', 'Blood Moon'], bob=[(1, 'Island'), (10, 'Forest')])
    hold(s)
    source = put(s, NAME, 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=8)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'You get an emblem'))
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    settle(s)
    assert any(c.zone == 'p1:command' and c.token and c.token.type_line == 'Emblem' for c in s.state.cards.values())
    roundtrip(s)
    return s


def draw_ability(s, cards, land):
    ch = derive(s.state, s.state.cards[land.id], characteristics.of(s.state.cards[land.id], cards), cards)
    return next(a for a in ch.abilities if 'Draw a card' in a.text)


def test_canonical_mu_yanling_is_full(cards):
    c = coverage.of_card_data(cards.resolve(NAME))
    assert c.level == 'FULL', c.manual_parts


def test_actual_ultimate_grants_islands_a_stack_using_draw_ability(cards):
    s = setup(cards)
    island = put(s, 'Island', 'battlefield')
    ability = draw_ability(s, cards, island)
    assert ability.kind == 'activated'
    ch = derive(s.state, s.state.cards[island.id], characteristics.of(s.state.cards[island.id], cards), cards)
    assert any(a.kind == 'mana' for a in ch.abilities)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='activate_ability', card_id=island.id, ability=ability.index)
    assert s.state.cards[island.id].tapped
    assert len(s.state.zones['p1:hand']) == before and len(s.state.rules.stack) == 1
    roundtrip(s)
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=island.id, ability=ability.index)
    roundtrip(s)


def test_emblem_uses_current_island_type_and_current_controller(cards):
    s = setup(cards)
    forest = put(s, 'Forest', 'battlefield')
    enemy = put(s, 'Island', 'battlefield', 'p2')
    def has(land):
        ch = derive(s.state, s.state.cards[land.id], characteristics.of(s.state.cards[land.id], cards), cards)
        return any('Draw a card' in a.text for a in ch.abilities)
    assert not has(forest) and not has(enemy)
    put(s, 'Dryad of the Ilysian Grove', 'battlefield')
    assert has(forest) and not has(enemy)
    act(s, 'p2', type='set_controller', card_ids=[enemy.id], player='p1')
    assert has(enemy) and s.state.cards[enemy.id].owner == 'p2'
    act(s, 'p1', type='set_controller', card_ids=[enemy.id], player='p2')
    assert not has(enemy)
    roundtrip(s)


def test_nonbasic_island_loses_draw_ability_when_blood_moon_removes_island_type(cards):
    s = setup(cards)
    dual = put(s, 'Tropical Island', 'battlefield')
    assert draw_ability(s, cards, dual)
    put(s, 'Blood Moon', 'battlefield')
    ch = derive(s.state, s.state.cards[dual.id], characteristics.of(s.state.cards[dual.id], cards), cards)
    assert 'Island' not in ch.subtypes and not any('Draw a card' in a.text for a in ch.abilities)
    roundtrip(s)


def test_creature_islands_must_obey_summoning_sickness_for_the_granted_tap_cost(cards):
    s = setup(cards)
    put(s, 'Dryad of the Ilysian Grove', 'battlefield')
    put(s, 'Living Lands', 'battlefield')
    island = put(s, 'Island', 'battlefield')
    ability = draw_ability(s, cards, island)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='summoning sickness'):
        act(s, 'p1', type='activate_ability', card_id=island.id, ability=ability.index)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_granted_draw_ability_can_be_used_on_an_opponents_turn(cards):
    from tests.test_rules_wave34b_activated import priority_to, to_phase

    s = setup(cards)
    island = put(s, 'Island', 'battlefield')
    to_phase(s, 'main1', turn=s.state.turn.number + 1)
    priority_to(s, 'p1')
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='activate_ability', card_id=island.id, ability=draw_ability(s, cards, island).index)
    assert s.state.players[s.state.turn.active_player].id == 'p2'
    assert len(s.state.zones['p1:hand']) == before
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)
