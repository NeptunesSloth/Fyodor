"""A tutor reads current legendary creature colors after the Ring tempts its controller."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_abundance import set_library
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Ringsight'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/ringsight_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='rst', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, creature='Grizzly Bears', extra=None, enemy=None, defer=False, top_names=None):
    s = table(cards, [NAME, 'Grizzly Bears', 'Cultivate', 'Lightning Bolt', 'Counterspell', 'Forest',
                      'Baral, Chief of Compliance', 'Myr Retriever', 'The Great Henge', 'Kozilek, the Great Distortion',
                      'Balmor, Battlemage Captain', "Kozilek's Return"],
              ['Baral, Chief of Compliance', 'Krenko, Mob Boss', 'Lightning Bolt'])
    bearer = put(s, creature, 'battlefield') if creature else None
    if extra:
        put(s, extra, 'battlefield')
    if enemy:
        put(s, enemy, 'battlefield', pid='p2')
    source = put(s, NAME, 'hand')
    top = set_library(s, top_names or ['Cultivate', 'Lightning Bolt', 'Counterspell', 'Forest'])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 1, 'B': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    if not defer:
        reach_search(s, bearer)
    return s, source, bearer, top


def reach_search(s, bearer):
    settle(s)
    d = s.state.rules.decision
    if d is not None and (d.resume or {}).get('step') == 'ring_tempts':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[bearer.id])
        settle(s)
    d = s.state.rules.decision
    assert d is not None and (d.resume or {}).get('step') == 'search'
    roundtrip(s)
    return d


def names(s):
    return {s.state.cards[o.card_id].name for o in s.state.rules.decision.options if o.card_id}


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_new_ring_bearer_opens_green_search_and_actual_find_reveals_then_shuffles(cards):
    s, source, bearer, top = setup(cards)
    assert 'Legendary' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bearer.id]).supertypes
    assert s.state.rules.ring_tempted['p1'] == 1
    assert names(s) == {'Cultivate'}
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    assert all(cid not in s.view('p2')['cards'] for cid in top)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[0]])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:hand' and s.state.cards[source.id].zone == 'p1:graveyard'
    assert len(s.state.zones['p1:library']) == 3
    roundtrip(s)


@pytest.mark.parametrize('extra,expected', [('Baral, Chief of Compliance', {'Cultivate', 'Counterspell'}),
                                          ('The Great Henge', {'Cultivate'})])
def test_union_of_controlled_legendary_creature_colors_excludes_noncreature_legends(cards, extra, expected):
    s, _, _, _ = setup(cards, extra=extra)
    assert names(s) == expected


@pytest.mark.parametrize('creature', ['Myr Retriever', 'Kozilek, the Great Distortion', None])
def test_colorless_or_no_bearer_does_not_share_a_color_even_with_colorless_cards(cards, creature):
    s, _, _, _ = setup(cards, creature, extra='The Great Henge', enemy='Baral, Chief of Compliance')
    assert names(s) == set()
    assert s.state.rules.ring_tempted['p1'] == 1
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    roundtrip(s)


def test_opponents_colored_legendary_creature_does_not_qualify_a_card(cards):
    s, _, _, _ = setup(cards, enemy='Baral, Chief of Compliance')
    assert names(s) == {'Cultivate'}


def test_legend_that_leaves_before_resolution_is_not_used_by_tutor(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s, _, bearer, _ = setup(cards, extra='Baral, Chief of Compliance', defer=True)
    legend = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Baral, Chief of Compliance' and c.zone.endswith(':battlefield'))
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[legend.id], sources=[])
    reach_search(s, bearer)
    assert names(s) == {'Cultivate'}


def test_multicolored_legend_uses_either_color_and_devoid_does_not_match_mana_cost(cards):
    s, _, _, _ = setup(cards, extra='Balmor, Battlemage Captain',
                       top_names=['Cultivate', 'Lightning Bolt', 'Counterspell', 'Forest', "Kozilek's Return"])
    assert names(s) == {'Cultivate', 'Lightning Bolt', 'Counterspell'}


def test_may_fail_to_find_even_with_an_eligible_hidden_card(cards):
    s, _, _, top = setup(cards)
    old_oids = {s.state.rules.object_id(cid) for cid in top}
    d = s.state.rules.decision
    assert d.min_choices == 0
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert len(s.state.zones['p1:library']) == 4
    assert all(s.state.rules.object_id(cid) not in old_oids for cid in top)
    roundtrip(s)
