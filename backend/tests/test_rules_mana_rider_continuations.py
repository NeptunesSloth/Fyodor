"""Persistent mana rider stages. Synthetic sources deliberately isolate CPS plumbing.

CR 605.1a makes Chromatic Sphere/Eggs ordinary stack abilities. Their genuine
respondable activations are separate from low-level injected mana-rider tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_abundance import set_library
from tests.test_rules_conditionals import pick
from tests.test_rules_costs_components import artifact
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.wave9c_kit import reloaded


@pytest.fixture()
def cards(settings, monkeypatch):
    from tests.mana_rider_kit import inject_draw_riders
    inject_draw_riders(monkeypatch)
    base = {c['name']: c for c in fixture_cards()}
    for filename in ('abundance_cards.json', 'mana_rider_continuation_cards.json'):
        raw = json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())
        for i, c in enumerate(raw):
            base[c['name']] = card(c['name'], set_code='cps', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, ['Abundance', 'Chromatic Sphere', 'Revitalize', 'Grizzly Bears', 'Lightning Bolt', 'Forest', 'Island', 'Bloodbraid Elf', 'Gnarlid Pack', 'Rod of Ruin', 'Shadowblood Egg', 'Mossfire Egg', 'Sungrass Egg', 'Skycloud Egg', 'Darkwater Egg', 'Toxic Deluge'], ['Stifle'])
    put(s, 'Abundance', 'battlefield')
    top = set_library(s, ['Forest', 'Lightning Bolt', 'Grizzly Bears', 'Island'])
    return s, top


def replacement(s, *, decline=False):
    d = s.state.rules.decision
    assert d and 'decline' in {o.id for o in d.options}
    roundtrip(s)
    pick(s, 'decline' if decline else next(o.id for o in d.options if o.id != 'decline'))
    if not decline:
        d = s.state.rules.decision
        assert {o.id for o in d.options} == {'land', 'nonland'}
        roundtrip(s)
        pick(s, 'land')
        d = s.state.rules.decision
        if d is not None and d.kind == 'order':
            roundtrip(s)
            pick(s, *(o.id for o in d.options))


@pytest.mark.parametrize('decline', [False, True])
def test_automatic_cast_stops_before_cast_event_and_later_rider(cards, decline):
    s, top = setup(cards)
    source = artifact(s, 'CPS Test Spring', '{T}: Add {W}{W}. You gain 2 life.')
    spell = put(s, 'Revitalize', 'hand')
    before = s.state.players['p1'].life
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[source.id])
    assert source.id in s.state.cards and s.state.cards[source.id].tapped
    assert s.state.players['p1'].life == before
    assert spell.id not in s.state.rules.stack
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 0
    replacement(s, decline=decline)
    assert s.state.cards[top[0]].zone == 'p1:hand'
    assert s.state.players['p1'].life == before + 2
    assert spell.id in s.state.rules.stack
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 1
    roundtrip(s)


def test_nested_manual_source_restores_outer_cast_only_after_body(cards):
    s, _ = setup(cards)
    source = artifact(s, 'CPS Test Spring', '{T}: Add {W}{W}. You gain 2 life.')
    spell = put(s, 'Revitalize', 'hand')
    # Record the preference as an intent so replay uses the same payer.
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    before = s.state.players['p1'].life
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert s.state.rules.payment_outer is not None
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert s.state.players['p1'].life == before
    restored = reloaded(s)
    for game in (s, restored):
        replacement(game)
        assert game.state.rules.payment_outer is None
        assert game.state.cards[spell.id].zone == 'stack'
        assert game.state.players['p1'].life == before + 2
        roundtrip(game)


def test_actual_chromatic_sphere_manual_activation_at_priority(cards):
    s, top = setup(cards)
    sphere = put(s, 'Chromatic Sphere', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=sphere.id, ability=0)
    assert s.state.cards[sphere.id].zone == 'p1:graveyard'
    assert len(s.state.rules.stack) == 1
    from tests.test_rules_conditionals import until_asked
    d = until_asked(s)
    if 'decline' not in {o.id for o in d.options}:
        pick(s, next(o.id for o in d.options if o.label == '{G}'))
    restored = reloaded(s)
    for game in (s, restored):
        replacement(game)
        assert game.state.cards[top[0]].zone == 'p1:hand'
        assert game.state.players['p1'].mana_units[0].sym == 'G'
        roundtrip(game)


def test_two_draw_riders_preserve_sequence_and_gain_happens_last(cards):
    s, _ = setup(cards)
    source = artifact(s, 'CPS Test Two Draws', '{T}: Add {G}. You gain 2 life.')
    before = s.state.players['p1'].life
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    replacement(s)
    assert s.state.rules.decision is not None
    assert s.state.players['p1'].life == before
    roundtrip(s)
    replacement(s)
    assert s.state.players['p1'].life == before + 2
    assert s.state.rules.decision is None
    roundtrip(s)


def test_multiple_sources_activate_in_order_before_outer_mana_is_spent(cards):
    s, _ = setup(cards)
    first = artifact(s, 'CPS Test First', '{T}: Add {W}.')
    second = artifact(s, 'CPS Test Second', '{T}: Add {W}.')
    spell = put(s, 'Revitalize', 'hand')
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[first.id, second.id])
    tapped = [c for c in (first, second) if s.state.cards[c.id].tapped]
    assert len(tapped) == 1
    assert len(s.state.players['p1'].mana_units) == 1
    assert spell.id not in s.state.rules.stack
    replacement(s)
    assert all(s.state.cards[c.id].tapped for c in (first, second))
    assert len(s.state.players['p1'].mana_units) == 2
    assert spell.id not in s.state.rules.stack
    roundtrip(s)
    replacement(s)
    assert not s.state.players['p1'].mana_units
    assert spell.id in s.state.rules.stack
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 1
    roundtrip(s)


def test_filter_draw_completes_before_outer_pool_payment_and_keeps_provenance(cards):
    from app.rules.plan import Plan
    s, _ = setup(cards)
    source = artifact(s, 'CPS Test Filter', '{1}, {T}: Add {W}{W}.')
    forest = put(s, 'Forest', 'battlefield')
    spell = put(s, 'Revitalize', 'hand')
    old = Plan(s.state, 'p1', cards, None).oid(source)
    forest_oid = Plan(s.state, 'p1', cards, None).oid(forest)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[source.id, forest.id])
    assert s.state.cards[forest.id].tapped and s.state.cards[source.id].tapped
    assert len(s.state.players['p1'].mana_units) == 2
    assert {u.src for u in s.state.players['p1'].mana_units} == {old}
    assert spell.id not in s.state.rules.stack
    restored = reloaded(s)
    for game in (s, restored):
        replacement(game)
        record = game.state.rules.payments[Plan(game.state, 'p1', cards, None).oid(game.state.cards[spell.id])]
        assert record.mana_sources == [old, old]
        assert forest_oid not in record.mana_sources
        assert record.mana_spent == {'W': 2}
        assert not game.state.players['p1'].mana_units
        roundtrip(game)


def test_actual_sphere_still_cannot_activate_inside_payment(cards):
    from app.game.errors import ActionError
    s, _ = setup(cards)
    sphere = put(s, 'Chromatic Sphere', 'battlefield')
    spell = put(s, 'Revitalize', 'hand')
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    before = s.state.rules.decision.id
    with pytest.raises(ActionError, match='only tap for mana'):
        act(s, 'p1', type='activate_ability', card_id=sphere.id, ability=0, mana_choice='W')
    assert s.state.rules.decision.id == before
    assert s.state.cards[sphere.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_free_cascade_cast_with_multikicker_waits_for_replacement(cards):
    from tests.test_rules_conditionals import until_asked
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, _ = setup(cards)
    set_library(s, ['Gnarlid Pack', 'Forest', 'Island', 'Lightning Bolt'])
    source = artifact(s, 'CPS Test Spring', '{T}: Add {G}{G}{G}{G}.')
    elf = put(s, 'Bloodbraid Elf', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'R': 1, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=elf.id, sources=[])
    d = until_asked(s)
    assert d.resume['step'] == 'suspend_cast'
    pick(s, 'yes')
    d = s.state.rules.decision
    assert 'kicker:2' in {o.id for o in d.options}
    pick(s, 'kicker:2')
    pack = next(c for c in s.state.cards.values() if c.name == 'Gnarlid Pack')
    assert pack.id not in s.state.rules.stack
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 1
    restored = reloaded(s)
    for game in (s, restored):
        replacement(game)
        settle(game)
        assert game.state.cards[pack.id].zone == 'p1:battlefield'
        assert chars(game, game.state.cards[pack.id]).pt == (4, 4)
        assert game.state.rules.spells_this_turn('p1', game.state.turn.number) == 2
        assert game.state.cards[source.id].tapped
        roundtrip(game)


def test_activated_ability_finishes_payment_and_stack_entry_once(cards):
    s, _ = setup(cards)
    source = artifact(s, 'CPS Test Spring', '{T}: Add {C}{C}{C}.')
    rod = put(s, 'Rod of Ruin', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=rod.id, ability=0, targets=['p2'], sources=[source.id])
    # 602.2b follows 601.2g before 601.2h: finish mana abilities before paying the tap cost.
    assert not s.state.cards[rod.id].tapped
    assert not s.state.rules.stack
    assert s.state.players['p2'].life == 40
    restored = reloaded(s)
    for game in (s, restored):
        replacement(game)
        assert game.state.cards[rod.id].tapped
        assert len(game.state.rules.stack) == 1
        settle(game)
        assert game.state.players['p2'].life == 39
        assert not game.state.players['p1'].mana_units
        roundtrip(game)


@pytest.mark.parametrize('text,kind', [
    ('{T}: Add {G}. Draw a card.', 'activated'),
    ('{T}: Add {G}. Each player draws a card.', 'activated'),
    ('{T}: Add {G}. Mill two cards.', 'activated'),
    ('{T}, Mill any number of cards: Add {G}.', 'activated'),
    ('{T}: Add {G}. Exile the top two cards of your library.', 'activated'),
    ('{T}: Add {G}. Put the top card of your library into your hand.', 'activated'),
    ('{T}: Add {G}. Return a card from your graveyard to the top of your library.', 'activated'),
    ('{T}: Add {G}. When you spend this mana, draw a card.', 'mana'),
    ('{T}: Add {G}. When you do, mill two cards.', 'mana'),
    ("{T}: Add {G}. Draw a card at the beginning of the next turn's upkeep.", 'mana'),
    ("{T}: Add {G} for each card you've drawn this turn.", 'mana'),
    ('{T}: Add {G}. Reveal the top card of your library.', 'mana'),
    ('Reveal the top card of your library: Add {G}.', 'mana'),
    ('{T}: Add {G}. Look at the top card of your library. You may put it on the bottom.', 'mana'),
    ('{T}: Add {G}. Search your library for a card, reveal it, then shuffle.', 'mana'),
    ('{T}: Add {G}. Look at the top two cards of your library. Put them back on top in any order. Return a card from your graveyard to the top of your library.', 'activated'),
    ('{T}: Add {G}. Look at the top two cards of your library. Put them onto the top of your library in any order.', 'mana'),
])
def test_library_movement_classification_ignores_other_abilities_and_same_zone_reordering(text, kind):
    from app.rules.oracle import classify
    assert classify(text, spell=False)[0] == kind


@pytest.mark.parametrize('name', ['Shadowblood Egg', 'Mossfire Egg', 'Sungrass Egg', 'Skycloud Egg', 'Darkwater Egg'])
def test_canonical_eggs_are_ordinary_stack_abilities_and_keep_source_after_sacrifice(cards, name):
    from app.rules import coverage
    from app.rules.oracle import parse_abilities
    from app.rules.plan import Plan
    from tests.test_rules_conditionals import until_asked
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
    assert parse_abilities(cards.resolve(name)['oracle_text'])[0].kind == 'activated'
    s, top = setup(cards)
    source = put(s, name, 'battlefield')
    old = Plan(s.state, 'p1', cards, None).oid(source)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert len(s.state.rules.stack) == 1
    assert not s.state.players['p1'].mana_units
    roundtrip(s)
    until_asked(s)
    assert len(s.state.players['p1'].mana_units) == 2
    assert {u.src for u in s.state.players['p1'].mana_units} == {old}
    restored = reloaded(s)
    for game in (s, restored):
        replacement(game)
        assert game.state.cards[top[0]].zone == 'p1:hand'
        assert not game.state.rules.stack
        roundtrip(game)


def test_actual_sphere_ability_can_be_responded_to_and_countered(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s, _ = setup(cards)
    sphere = put(s, 'Chromatic Sphere', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=sphere.id, ability=0, sources=[])
    ability = next(iter(s.state.rules.stack))
    stifle = put(s, 'Stifle', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=stifle.id, targets=[ability], sources=[])
    settle(s)
    assert not s.state.rules.stack
    assert s.state.cards[sphere.id].zone == 'p1:graveyard'
    assert not s.state.players['p1'].mana_units
    assert s.state.rules.decision is None
    roundtrip(s)


def test_chosen_cost_source_token_departure_keeps_frozen_riders_after_saved_color_choice(cards):
    s, top = setup(cards)
    act(s, 'p1', type='create_token', player='p1', token={
        'name': 'CPS Test Self Sacrifice', 'type_line': 'Token Artifact Creature — Test', 'power': '2', 'toughness': '2',
        'text': 'Sacrifice a creature: Add one mana of any color.'})
    source = next(c for c in s.state.cards.values() if c.name == 'CPS Test Self Sacrifice')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
        cost_choices=[{'component': 0, 'cards': [source.id]}])
    assert source.id not in s.state.cards
    d = s.state.rules.decision
    assert d and d.resume.get('paid') is True
    roundtrip(s)
    restored = reloaded(s)
    for game in (s, restored):
        d = game.state.rules.decision
        pick(game, next(o.id for o in d.options if o.label == '{G}'))
        replacement(game)
        assert game.state.cards[top[0]].zone == 'p1:hand'
        assert len(game.state.players['p1'].mana_units) == 1
        assert game.state.players['p1'].mana_units[0].sym == 'G'
        roundtrip(game)


def test_cancelling_outer_spell_after_completed_nested_mana_keeps_paid_source_and_found_card(cards):
    s, top = setup(cards)
    source = artifact(s, 'CPS Test Spring', '{T}: Add {W}.')
    spell = put(s, 'Revitalize', 'hand')
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    replacement(s)
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    assert s.state.cards[spell.id].zone == 'p1:hand'
    roundtrip(s)
    pick(s, 'cancel')
    assert s.state.cards[source.id].tapped
    assert s.state.cards[top[0]].zone == 'p1:hand'
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert len(s.state.players['p1'].mana_units) == 1
    assert s.state.rules.decision is None
    roundtrip(s)


def test_declining_replacement_on_empty_library_finishes_cast_before_state_based_loss(cards):
    s, _ = setup(cards)
    set_library(s, [])
    source = artifact(s, 'CPS Test Spring', '{T}: Add {W}{W}.')
    spell = put(s, 'Revitalize', 'hand')
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[source.id])
    assert 'p1' not in s.state.rules.lost
    replacement(s, decline=True)
    assert 'p1' in s.state.rules.lost
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 1
    assert s.state.rules.decision is None
    roundtrip(s)


def test_real_life_additional_cost_clears_reservation_before_next_same_plan_payment(cards):
    from app.game.actions import CastSpell
    from app.rules import casting, mana
    from app.rules import payment_continuations as pc
    from app.rules.plan import Plan
    s, _ = setup(cards)
    spell = put(s, 'Toxic Deluge', 'hand')
    act(s, 'p1', type='set_life', player='p1', value=6)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'B': 1})
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    casting.cast_spell(plan, CastSpell(card_id=spell.id, x_value=2, sources=[]))
    assert plan.state.players['p1'].life == 4
    paid = []

    def done(p, data, payment):
        paid.append(payment.life)

    pc.register('test_reservation_payment', dict, done)
    after = pc.continuation(plan, 'test_reservation_payment', {})
    casting.pay_then(plan, 'p1', mana.parse_cost('{B/P}{B/P}'), 'later same-plan payment', sources=[], then=after)
    assert paid == [4]
    assert plan.state.players['p1'].life == 0
    assert plan.reserved_life == 0


@pytest.mark.parametrize('same_context', [False, True])
def test_saved_stage_restores_different_caller_context_but_keeps_same_context_cleanup(cards, same_context):
    from app.rules import payment_continuations as pc
    from app.rules.plan import Plan
    s, _ = setup(cards)
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    plan.reserved_life = 3
    seen = []

    def clear(p, data, payment):
        seen.append((p.actor, p.reserved_life))
        p.reserved_life = 0

    pc.register('test_reservation_cleanup', dict, clear)
    after = pc.continuation(plan, 'test_reservation_cleanup', {})
    if not same_context:
        plan.actor, plan.reserved_life = 'p2', 5
    pc.finish(plan, after, None)
    assert seen == [('p1', 3)]
    assert (plan.actor, plan.reserved_life) == (('p1', 0) if same_context else ('p2', 5))


@pytest.mark.parametrize('same_context', [False, True])
def test_resumed_rider_queue_keeps_terminal_cleanup_and_restores_other_caller(cards, same_context):
    from pydantic import TypeAdapter

    from app.rules import payment_continuations as pc
    from app.rules import replace
    from app.rules.plan import Plan
    s, _ = setup(cards)
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    plan.reserved_life = 3

    def clear(p, data, payment):
        p.reserved_life = 0

    pc.register('test_rider_reservation_cleanup', dict, clear)
    after = pc.continuation(plan, 'test_rider_reservation_cleanup', {})
    source = next(c for c in plan.state.cards.values() if c.name == 'Abundance')
    frame = pc.ManaRiderFrame(source.model_dump(mode='json'), plan.oid(source), 'p1', [], after, 'p1', 3)
    saved = TypeAdapter(pc.ManaRiderFrame).dump_python(frame, mode='json')
    if not same_context:
        plan.actor, plan.reserved_life = 'p2', 5
    replace.run_then(plan, {'do': 'mana_riders', 'frame': saved})
    assert (plan.actor, plan.reserved_life) == (('p1', 0) if same_context else ('p2', 5))
