"""CR 509.1c–g: blocking taxes lock and pay before a declaration commits."""
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
from tests.test_rules_designations import build, put, roundtrip
from tests.test_rules_wave34b_activated import attack, next_turn, stops, to_phase

DATA = Path(__file__).parent / 'fixtures/archangel_tithes_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='abt', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, extra=(), defenders=('Wall of Air',), with_source=True, at_blockers=True):
    s = build(cards, ['Archangel of Tithes', 'Grizzly Bears', *extra], bob=[*((1, n) for n in defenders), (10, 'Island')])
    source = put(s, 'Archangel of Tithes', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    blockers = [put(s, name, 'battlefield', 'p2') for name in defenders]
    stops(s)
    next_turn(s)
    attack(s, *([source, bear] if with_source else [bear]))
    if at_blockers:
        to_phase(s, 'declare_blockers')
        assert s.state.rules.decision.kind == 'declare_blockers'
    return s, source, bear, blockers


def declare(s, pairs=(), **kwargs):
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': b.id, 'attacker_id': a.id} for b, a in pairs], **kwargs)


def choose(s, ids):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    roundtrip(s)


def test_canonical_archangel_is_full(cards):
    c = coverage.of_card_data(cards.resolve('Archangel of Tithes'))
    assert c.level == 'FULL', c.manual_parts


def test_attacking_source_charges_once_for_each_unique_declared_blocker(cards):
    s, source, bear, blockers = setup(cards, defenders=('Wall of Air', 'Grizzly Bears'))
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2})
    declare(s, [(blockers[0], source), (blockers[1], bear)])
    assert mana_pool(s, 'p2') == {}
    assert s.state.cards[blockers[0].id].blocking == source.id
    assert s.state.cards[blockers[1].id].blocking == bear.id
    roundtrip(s)


def test_nonattacking_source_does_not_charge_for_blocking_other_attackers(cards):
    s, _, bear, blockers = setup(cards, with_source=False, defenders=('Grizzly Bears',))
    declare(s, [(blockers[0], bear)])
    assert s.state.cards[blockers[0].id].blocking == bear.id
    roundtrip(s)


def test_insufficient_mana_rejects_without_committing_blockers(cards):
    s, source, _, blockers = setup(cards)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='Blocking costs'):
        declare(s, [(blockers[0], source)])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_cancel_payment_returns_to_same_defenders_declaration(cards):
    s, source, _, blockers = setup(cards)
    land = put(s, 'Island', 'battlefield', 'p2')
    act(s, 'p2', type='set_prefs', payment='self')
    declare(s, [(blockers[0], source)])
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    assert s.state.cards[blockers[0].id].blocking is None
    choose(s, ['cancel'])
    assert s.state.rules.decision.kind == 'declare_blockers' and s.state.rules.decision.player == 'p2'
    assert mana_pool(s, 'p2') == {} and not s.state.cards[land.id].tapped
    declare(s)
    assert s.state.cards[blockers[0].id].blocking is None
    roundtrip(s)


def test_lure_does_not_force_paying_to_declare_a_blocker(cards):
    s, _, bear, blockers = setup(cards, extra=('Lure',), defenders=('Grizzly Bears',))
    lure = put(s, 'Lure', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[lure.id], to=bear.id)
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1})
    declare(s)
    assert s.state.cards[blockers[0].id].blocking is None and mana_pool(s, 'p2') == {'C': 1}
    roundtrip(s)


def test_already_paid_multi_blocker_must_obey_free_additional_lure_assignment(cards):
    s = build(cards, ['Archangel of Tithes', 'Grizzly Bears', 'Grizzly Bears', 'Lure'], bob=[(1, 'Palace Guard'), (10, 'Island')])
    source = put(s, 'Archangel of Tithes', 'battlefield')
    bears = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Grizzly Bears']
    for bear in bears:
        act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'battlefield'})
    guard = put(s, 'Palace Guard', 'battlefield', 'p2')
    lure = put(s, 'Lure', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[lure.id], to=bears[0].id)
    stops(s)
    next_turn(s)
    attack(s, source, *bears)
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1})
    with pytest.raises(ActionError, match='blocks .* if able'):
        declare(s, [(guard, bears[1])])
    declare(s, [(guard, bears[0]), (guard, bears[1])])
    assert {s.state.cards[guard.id].blocking, *s.state.cards[guard.id].blocking_more} == {b.id for b in bears}
    assert mana_pool(s, 'p2') == {}
    roundtrip(s)


def test_selected_blocker_can_tap_for_mana_and_still_become_a_blocker(cards):
    s, _, bear, blockers = setup(cards, defenders=('Elvish Mystic',))
    blocker = blockers[0]
    act(s, 'p2', type='set_prefs', payment='self')
    declare(s, [(blocker, bear)])
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    act(s, 'p2', type='activate_ability', card_id=blocker.id, ability=0)
    assert s.state.cards[blocker.id].tapped and s.state.cards[blocker.id].blocking == bear.id
    assert mana_pool(s, 'p2') == {}
    roundtrip(s)


def test_cost_and_original_objects_stay_locked_when_source_leaves_during_mana_window(cards):
    s, source, bear, blockers = setup(cards)
    put(s, 'Island', 'battlefield', 'p2')
    act(s, 'p2', type='set_prefs', payment='self')
    declare(s, [(blockers[0], bear)])
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1})
    choose(s, ['pay'])
    assert mana_pool(s, 'p2') == {} and s.state.cards[blockers[0].id].blocking == bear.id
    roundtrip(s)


@pytest.mark.parametrize('change', ['blink', 'control'])
def test_original_selected_blocker_identity_and_controller_are_checked_after_payment(cards, change):
    s, _, bear, blockers = setup(cards)
    blocker = blockers[0]
    put(s, 'Island', 'battlefield', 'p2')
    act(s, 'p2', type='set_prefs', payment='self')
    declare(s, [(blocker, bear)])
    if change == 'blink':
        act(s, 'p2', type='move', card_ids=[blocker.id], to={'player': 'p2', 'zone': 'exile'})
        act(s, 'p2', type='move', card_ids=[blocker.id], to={'player': 'p2', 'zone': 'battlefield'})
    else:
        act(s, 'p2', type='set_controller', card_ids=[blocker.id], player='p1')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1})
    choose(s, ['pay'])
    assert mana_pool(s, 'p2') == {} and s.state.cards[blocker.id].blocking is None
    roundtrip(s)


def test_two_attacking_sources_stack_even_when_blocking_only_one(cards):
    s = build(cards, ['Archangel of Tithes', 'Archangel of Tithes'], bob=[(1, 'Wall of Air'), (10, 'Island')])
    sources = [c for c in s.state.cards.values() if c.name == 'Archangel of Tithes']
    for source in sources:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    blocker = put(s, 'Wall of Air', 'battlefield', 'p2')
    stops(s)
    next_turn(s)
    attack(s, *sources)
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2})
    declare(s, [(blocker, sources[0])])
    assert mana_pool(s, 'p2') == {} and s.state.cards[blocker.id].blocking == sources[0].id
    roundtrip(s)


@pytest.mark.parametrize('source_leaves', [False, True])
def test_mana_ability_rider_pauses_before_spending_and_block_commit(cards, monkeypatch, source_leaves):
    from tests.payment_rider_injection import inject_mana_draw_rider

    inject_mana_draw_rider(monkeypatch, {'Island'})
    s, source, _, blockers = setup(cards, defenders=('Wall of Air', 'Abundance'))
    land = put(s, 'Island', 'battlefield', 'p2')
    declare(s, [(blockers[0], source)], sources=[land.id])
    d = s.state.rules.decision
    assert d and 'decline' in {o.id for o in d.options}
    assert s.state.cards[land.id].tapped and mana_pool(s, 'p2') == {'U': 1}
    assert s.state.cards[blockers[0].id].blocking is None and not s.state.rules.blocked
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    roundtrip(s)
    choose(s, ['decline'])
    assert s.state.cards[blockers[0].id].blocking == (None if source_leaves else source.id)
    assert mana_pool(s, 'p2') == {}
    roundtrip(s)


def test_multiplayer_defenders_pay_separately_and_second_defender_can_cancel(cards):
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Archangel of Tithes', 'Grizzly Bears'], ['Wall of Air'], ['Grizzly Bears', 'Island'])
    source = put(s, 'Archangel of Tithes', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    first = put(s, 'Wall of Air', 'battlefield', 'p2')
    second = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    land = put(s, 'Island', 'battlefield', 'p3')
    to_phase(s, 'main1', turn=s.state.turn.number + 3)
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}, {'card_id': bear.id, 'target': 'p3'}])
    to_phase(s, 'declare_blockers')
    assert s.state.rules.decision.player == 'p2'
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1})
    declare(s, [(first, source)])
    assert s.state.rules.decision.player == 'p3'
    act(s, 'p3', type='set_prefs', payment='self')
    act(s, 'p3', type='declare_blockers', blocks=[{'blocker_id': second.id, 'attacker_id': bear.id}])
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    choose(s, ['cancel'])
    assert s.state.rules.decision.kind == 'declare_blockers' and s.state.rules.decision.player == 'p3'
    assert s.state.cards[first.id].blocking == source.id and not s.state.cards[land.id].tapped
    act(s, 'p3', type='add_mana', player='p3', mana={'C': 1})
    act(s, 'p3', type='declare_blockers', blocks=[{'blocker_id': second.id, 'attacker_id': bear.id}])
    assert s.state.cards[second.id].blocking == bear.id and mana_pool(s, 'p3') == {}
    roundtrip(s)


def test_source_leaving_before_declaration_removes_the_tax(cards):
    s, source, bear, blockers = setup(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    declare(s, [(blockers[0], bear)])
    assert s.state.cards[blockers[0].id].blocking == bear.id
    roundtrip(s)


def test_real_reconnaissance_removes_source_from_combat_before_block_declaration(cards):
    from tests.test_rules_designations import settle

    s, source, bear, blockers = setup(cards, extra=('Reconnaissance',), at_blockers=False)
    enchantment = put(s, 'Reconnaissance', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=enchantment.id, ability=0, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].attacking is None
    to_phase(s, 'declare_blockers')
    declare(s, [(blockers[0], bear)])
    assert s.state.cards[blockers[0].id].blocking == bear.id
    roundtrip(s)


def test_real_sudden_spoiling_removes_source_tax_ability_before_declaration(cards):
    from tests.test_rules_designations import settle

    s, source, _, blockers = setup(cards, extra=('Sudden Spoiling',), at_blockers=False)
    spell = put(s, 'Sudden Spoiling', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p1'])
    settle(s)
    to_phase(s, 'declare_blockers')
    declare(s, [(blockers[0], source)])
    assert s.state.cards[blockers[0].id].blocking == source.id
    roundtrip(s)
