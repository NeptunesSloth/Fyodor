"""Explicit 'in any order' is a private choice of the effect's controller (608.2d)."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/ordered_graveyard_library_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='ogl', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, ['Misinformation'], ['Perilous Myr', 'Lightning Bolt', 'Forest'], ['Perilous Myr'])
    source = put(s, 'Misinformation', 'hand')
    selected = [put(s, n, 'graveyard', 'p2') for n in ['Perilous Myr', 'Lightning Bolt', 'Forest']]
    mana(s, B=1)
    return s, source, selected


def cast(s, source, selected):
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[c.id for c in selected], target_counts=[len(selected)])


def test_misinformation_full(cards):
    assert coverage.of_card_data(cards.resolve('Misinformation')).level == 'FULL'


def test_caster_orders_opponents_cards_privately(cards):
    s, source, selected = setup(cards)
    cast(s, source, selected)
    d = until_asked(s)
    assert d is not None and d.kind == 'order' and d.player == 'p1'
    assert d.resume['owner'] == 'p2'
    assert {o.id for o in d.options} == {c.id for c in selected}
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    roundtrip(s)
    order = [c.id for c in reversed(selected)]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=order)
    settle(s)
    assert s.state.zones['p2:library'][:3] == order
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_targets_must_share_one_opponents_graveyard(cards):
    s, source, selected = setup(cards)
    other = put(s, 'Perilous Myr', 'graveyard', 'p3')
    with pytest.raises(ActionError):
        cast(s, source, [selected[0], other])
    assert s.state.cards[source.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('n', [0, 1])
def test_zero_or_one_target_needs_no_order_choice(cards, n):
    s, source, selected = setup(cards)
    cast(s, source, selected[:n])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    if n:
        assert s.state.zones['p2:library'][0] == selected[0].id
    roundtrip(s)


def test_illegal_target_is_excluded_from_order(cards):
    s, source, selected = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    cast(s, source, selected)
    act(s, 'p2', type='move', card_ids=[selected[0].id], to={'player': 'p2', 'zone': 'hand'})
    d = until_asked(s)
    assert d is not None and d.player == 'p1'
    order = [selected[2].id, selected[1].id]
    assert {o.id for o in d.options} == set(order)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=order)
    settle(s)
    assert s.state.zones['p2:library'][:2] == order
    assert s.state.cards[selected[0].id].zone == 'p2:hand'
    roundtrip(s)
