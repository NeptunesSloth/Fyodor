"""A discarded source is found by exact cost identity, with an unconditional shuffle."""
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
from tests.game_helpers import act, mana_pool
from tests.test_rules_abundance import set_library
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Kogla and Yidaro'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/discarded_self_shuffle_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='dss', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, target=None, permanent=None):
    s = table(cards, [NAME, 'Forest', 'Island', 'Rest in Peace', 'Rings of Brighthearth'], ['Sol Ring', 'Rhystic Study', 'Scavenging Ooze', 'Stifle'])
    if permanent:
        put(s, permanent, 'battlefield')
    source = put(s, NAME, 'hand')
    picked = put(s, target, 'battlefield', pid='p2') if target else None
    set_library(s, ['Forest', 'Island'])
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'R': 1, 'G': 1})
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    index = next(a.index for a in ch.abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[picked.id] if picked else [],
        target_counts=[1] if picked else [0], sources=[])
    d = s.state.rules.decision
    if d is not None:
        assert picked is None
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
    assert s.state.cards[source.id].zone == ('p1:exile' if permanent == 'Rest in Peace' else 'p1:graveyard')
    assert mana_pool(s, 'p1') == {} and len(s.state.rules.stack) == (2 if permanent == 'Rings of Brighthearth' else 1)
    roundtrip(s)
    return s, source, picked, before


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('target', [None, 'Sol Ring', 'Rhystic Study'])
def test_actual_activation_pays_discards_destroys_then_shuffles_and_draws(cards, target):
    s, source, picked, before = setup(cards, target)
    settle(s)
    assert s.state.cards[source.id].zone in ('p1:library', 'p1:hand')
    assert len(s.state.zones['p1:hand']) == before
    assert len(s.state.zones['p1:library']) == 2
    if picked:
        assert s.state.cards[picked.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('change', ['exile', 'leave_return', 'rest_in_peace'])
def test_source_no_longer_same_graveyard_object_still_shuffles_and_draws(cards, change):
    s, source, _, before = setup(cards, permanent='Rest in Peace' if change == 'rest_in_peace' else None)
    if change != 'rest_in_peace':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
        if change == 'leave_return':
            act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    old_oids = {s.state.rules.object_id(cid) for cid in s.state.zones['p1:library']}
    settle(s)
    assert len(s.state.zones['p1:hand']) == before
    assert s.state.cards[source.id].zone == ('p1:graveyard' if change == 'leave_return' else 'p1:exile')
    assert len(s.state.zones['p1:library']) == 1
    assert all(s.state.rules.object_id(cid) not in old_oids for cid in s.state.zones['p1:library'])
    roundtrip(s)


def test_all_chosen_targets_illegal_counter_ability_before_shuffle_or_draw(cards):
    s, source, picked, before = setup(cards, 'Sol Ring')
    act(s, 'p2', type='move', card_ids=[picked.id], to={'player': 'p2', 'zone': 'exile'})
    old_oids = {s.state.rules.object_id(cid) for cid in s.state.zones['p1:library']}
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert len(s.state.zones['p1:hand']) == before - 1
    assert {s.state.rules.object_id(cid) for cid in s.state.zones['p1:library']} == old_oids
    roundtrip(s)


def test_actual_ooze_response_exiles_cost_source_but_does_not_stop_draw(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s, source, _, before = setup(cards)
    ooze = put(s, 'Scavenging Ooze', 'battlefield', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'G': 1})
    wait_priority(s, 'p2')
    ch = Plan(s.state, 'p2', cards, None).ch(s.state.cards[ooze.id])
    index = next(a.index for a in ch.abilities if a.kind == 'activated')
    act(s, 'p2', type='activate_ability', card_id=ooze.id, ability=index, targets=[source.id], sources=[])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert len(s.state.zones['p1:hand']) == before and len(s.state.zones['p1:library']) == 1
    assert s.state.cards[ooze.id].counters['+1/+1'] == 1
    roundtrip(s)


def test_real_stifle_counters_activated_ability_without_refunding_discard_or_mana(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s, source, _, before = setup(cards)
    ability = next(iter(s.state.rules.stack))
    stifle = put(s, 'Stifle', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=stifle.id, targets=[ability], sources=[])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert len(s.state.zones['p1:hand']) == before - 1 and len(s.state.zones['p1:library']) == 2
    assert mana_pool(s, 'p1') == {}
    roundtrip(s)


def test_real_rings_copy_uses_original_discard_identity_and_both_abilities_draw(cards):
    s, source, _, before = setup(cards, permanent='Rings of Brighthearth')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    settle(s)
    d = s.state.rules.decision
    assert d is not None and 'pay' in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert d.min_choices == 0
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    assert len(s.state.zones['p1:library']) == 1
    assert s.state.cards[source.id].zone in ('p1:hand', 'p1:library')
    roundtrip(s)
