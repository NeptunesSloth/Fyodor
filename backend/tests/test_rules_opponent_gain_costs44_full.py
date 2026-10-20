"""Canonical Invigorate native casting, opponent cost and saved payment proofs."""
import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests import test_rules_opponent_gain_costs44 as fixtures
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Invigorate'


@pytest.fixture()
def cards(settings):
    yield from fixtures.cards.__wrapped__(settings)


def scene(cards, forest='Forest'):
    names = [c['name'] for c in fixtures.DATA]
    s = table(cards, names, names, names)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    land = put(s, forest, 'battlefield') if forest else None
    target = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, NAME, 'hand')
    return s, spell, target, land


def cast_alt(s, spell, target, recipient='p2'):
    wait_priority(s, 'p1')
    kw = {'cost_choices': [{'component': 0, 'cards': [recipient]}]} if recipient else {}
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id], alt_cost=f'{spell.id}:0', **kw)


def payment(s, spell):
    return s.state.rules.payments[s.state.rules.object_id(spell.id)]


def test_full_canonical_production(cards):
    q = coverage.of_card_data(cards.resolve(NAME))
    assert q.level == 'FULL', [(f.label, f.supported) for f in q.features]


def test_actual_normal_mana_cast_unchanged_and_four_four_expires(cards):
    s, spell, target, _ = scene(cards, forest=None)
    mana(s, C=2, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    record = payment(s, spell)
    assert record.mana_spent == {'C': 2, 'G': 1} and record.alternative is None
    assert not record.opponent_gain_costs
    assert all(p.life == 40 for p in s.state.players.values())
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).pt == (6, 6)
    to_phase(s, 'main1', turn=2)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).pt == (2, 2)
    roundtrip(s)


@pytest.mark.parametrize('forest,recipient', [('Forest', 'p2'), ('Breeding Pool', 'p3')])
def test_actual_forest_alternative_records_chosen_opponent_payment(cards, forest, recipient):
    s, spell, target, land = scene(cards, forest=forest)
    act(s, 'p1', type='tap', card_ids=[land.id], tapped=True)
    cast_alt(s, spell, target, recipient)
    assert s.state.players[recipient].life == 43
    assert all(p.life == 40 for pid, p in s.state.players.items() if pid != recipient)
    record = payment(s, spell)
    assert record.alternative == 'alternative' and not record.mana_spent and record.life == 0
    assert [r.model_dump() for r in record.opponent_gain_costs] == [{'recipient': recipient, 'nominal_amount': 3}]
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[spell.id]).mana_value == 3
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).pt == (6, 6)
    roundtrip(s)


@pytest.mark.parametrize('modifier,amount', [('Thalia, Guardian of Thraben', 1), ('Lodestone Golem', 1), ('Trinisphere', 3)])
def test_actual_alternative_still_pays_native_mana_tax(cards, modifier, amount):
    s, spell, target, land = scene(cards)
    put(s, modifier, 'battlefield', pid='p2')
    act(s, 'p1', type='tap', card_ids=[land.id], tapped=True)
    mana(s, C=amount)
    cast_alt(s, spell, target)
    record = payment(s, spell)
    assert record.mana_spent == {'C': amount} and len(record.opponent_gain_costs) == 1
    assert s.state.players['p2'].life == 43
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).pt == (6, 6)
    roundtrip(s)


@pytest.mark.parametrize('failure', ['no_forest', 'opponent_forest', 'self', 'blocked', 'all_blocked', 'free', 'tax'])
def test_actual_alternative_preflight_refusal_is_atomic(cards, failure):
    from app.game.errors import ActionError

    s, spell, target, land = scene(cards, forest=None if failure in ('no_forest', 'opponent_forest') else 'Forest')
    recipient = 'p1' if failure == 'self' else 'p2'
    if failure == 'opponent_forest':
        put(s, 'Forest', 'battlefield', pid='p2')
    if failure in ('blocked', 'all_blocked'):
        put(s, 'Platinum Emperion', 'battlefield', pid='p2')
    if failure == 'all_blocked':
        put(s, 'Platinum Emperion', 'battlefield', pid='p3')
    if failure == 'free':
        put(s, 'Omniscience', 'battlefield')
    if failure == 'tax':
        put(s, 'Thalia, Guardian of Thraben', 'battlefield', pid='p2')
        act(s, 'p1', type='tap', card_ids=[land.id], tapped=True)
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id],
            alt_cost=f'{spell.id}:0', free=failure == 'free', cost_choices=[{'component': 0, 'cards': [recipient]}])
    assert s.state.model_dump(mode='json') == before
    assert s.state.cards[spell.id].zone == 'p1:hand'


def test_actual_opponent_choice_cancel_does_not_consume_tax_or_move_spell(cards):
    from app.rules import mana_units

    s, spell, target, land = scene(cards)
    put(s, 'Thalia, Guardian of Thraben', 'battlefield', pid='p2')
    act(s, 'p1', type='tap', card_ids=[land.id], tapped=True)
    mana(s, C=1)
    before = mana_units.visible_pool(s.state, 'p1')
    cast_alt(s, spell, target, recipient=None)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'p2', 'p3'}
    assert s.state.cards[spell.id].zone == 'p1:hand'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
    assert s.state.rules.decision is None and s.state.cards[spell.id].zone == 'p1:hand'
    assert not s.state.zones.get('stack') and mana_units.visible_pool(s.state, 'p1') == before
    assert all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)


def test_actual_current_control_of_opponent_owned_forest_qualifies(cards):
    s, spell, target, _ = scene(cards, forest=None)
    forest = put(s, 'Forest', 'battlefield', pid='p2')
    original = s.state.rules.object_id(forest.id)
    act(s, 'p1', type='move', card_ids=[forest.id], to={'zone': 'battlefield', 'player': 'p1'})
    assert s.state.rules.object_id(forest.id) == original
    assert s.state.cards[forest.id].owner == 'p2'
    cast_alt(s, spell, target)
    assert s.state.players['p2'].life == 43
    settle(s)
    roundtrip(s)


@pytest.mark.parametrize('modifier,life', [('Sulfuric Vortex', 40), ('Tainted Remedy', 37), ("Alhammarret's Archive", 46)])
def test_actual_modified_opponent_gain_still_pays_nominal_alternative(cards, modifier, life):
    s, spell, target, _ = scene(cards)
    put(s, modifier, 'battlefield', pid='p1' if modifier == 'Tainted Remedy' else 'p2')
    cast_alt(s, spell, target)
    assert s.state.players['p2'].life == life
    assert [r.model_dump() for r in payment(s, spell).opponent_gain_costs] == [{'recipient': 'p2', 'nominal_amount': 3}]
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).pt == (6, 6)
    roundtrip(s)


def test_actual_late_invalid_opponent_choice_rejects_without_consuming_tax_or_stack_ghost(cards):
    from app.game.errors import ActionError
    from app.rules import mana_units

    s, spell, target, land = scene(cards)
    put(s, 'Thalia, Guardian of Thraben', 'battlefield', pid='p2')
    act(s, 'p1', type='tap', card_ids=[land.id], tapped=True)
    mana(s, C=1)
    cast_alt(s, spell, target, recipient=None)
    d = s.state.rules.decision
    assert d is not None and s.state.cards[spell.id].zone == 'p1:hand'
    put(s, 'Platinum Emperion', 'battlefield', pid='p2')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    assert s.state.model_dump(mode='json') == before
    assert s.state.cards[spell.id].zone == 'p1:hand' and not s.state.zones.get('stack')
    assert mana_units.visible_pool(s.state, 'p1') == {'C': 1}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p3'])
    assert s.state.players['p3'].life == 43
    assert payment(s, spell).mana_spent == {'C': 1}
    settle(s)
    roundtrip(s)


def test_actual_illegal_target_fizzles_without_refunding_opponent_gain(cards):
    from tests.test_rules_linked_aggregates import cast

    s, spell, target, _ = scene(cards)
    cast_alt(s, spell, target)
    assert s.state.players['p2'].life == 43
    removal = put(s, 'Swords to Plowshares', 'hand')
    cast(s, removal, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:exile'
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == 43
    roundtrip(s)


@pytest.mark.parametrize('unpayable', [False, True])
def test_actual_terror_additional_life_cost_is_paid_or_rejected_before_alternative(cards, unpayable):
    from app.game.errors import ActionError

    s, spell, _, _ = scene(cards)
    target = put(s, 'Terror of the Peaks', 'battlefield', pid='p2')
    if unpayable:
        act(s, 'p1', type='set_life', player='p1', value=2)
        before = s.state.model_dump(mode='json')
        with pytest.raises(ActionError):
            cast_alt(s, spell, target, recipient='p3')
        assert s.state.model_dump(mode='json') == before
        return
    cast_alt(s, spell, target, recipient='p3')
    record = payment(s, spell)
    assert record.life == 3 and record.opponent_gain_costs[0].recipient == 'p3'
    assert s.state.players['p1'].life == 37 and s.state.players['p3'].life == 43
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).pt == (9, 8)
    roundtrip(s)


def test_actual_cold_opponent_choice_preserves_unspent_tax_and_casts_once(cards, tmp_path):
    from app.rules import mana_units
    from tests.test_rules_linked_return_family import cold_choose

    s, spell, target, land = scene(cards)
    put(s, 'Thalia, Guardian of Thraben', 'battlefield', pid='p2')
    act(s, 'p1', type='tap', card_ids=[land.id], tapped=True)
    mana(s, C=1)
    cast_alt(s, spell, target, recipient=None)
    assert s.state.cards[spell.id].zone == 'p1:hand'
    assert mana_units.visible_pool(s.state, 'p1') == {'C': 1}
    s = cold_choose(s, cards, tmp_path, ['p3'])
    assert s.state.rules.decision is None
    record = payment(s, spell)
    assert record.mana_spent == {'C': 1}
    assert [r.model_dump() for r in record.opponent_gain_costs] == [{'recipient': 'p3', 'nominal_amount': 3}]
    assert s.state.players['p3'].life == 43 and s.state.players['p2'].life == 40
    assert mana_units.visible_pool(s.state, 'p1') == {}
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).pt == (6, 6)
    roundtrip(s)


@pytest.mark.parametrize('first,life', [('Archive', 47), ('Angel', 48)])
def test_actual_cold_replacement_payment_retains_original_native_tax_allocation(cards, tmp_path, first, life):
    from app.rules import mana_units
    from tests.test_rules_linked_return_family import cold_choose

    s, spell, target, land = scene(cards)
    put(s, 'Thalia, Guardian of Thraben', 'battlefield', pid='p2')
    put(s, "Alhammarret's Archive", 'battlefield', pid='p2')
    put(s, 'Angel of Vitality', 'battlefield', pid='p2')
    act(s, 'p1', type='tap', card_ids=[land.id], tapped=True)
    mana(s, C=1)
    cast_alt(s, spell, target)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2'
    assert s.state.players['p2'].life == 40 and mana_units.visible_pool(s.state, 'p1') == {}
    # The native allocation is serialized inside the actual paid-stage frame,
    # alongside the pending nominal gain; no replacement-generated payment.
    stage = d.resume['then']
    assert stage['stage'] == 'opponent_gain_costs44'
    allocation = stage['payload']['payment']
    assert allocation['spent'] == {'C': 1}
    assert {'allocation', 'slots', 'selected_options', 'sources'} <= allocation.keys()
    option = next(o.id for o in d.options if first in o.label)
    s = cold_choose(s, cards, tmp_path, [option])
    assert s.state.rules.decision is None and s.state.players['p2'].life == life
    record = payment(s, spell)
    assert record.mana_spent == {'C': 1}
    assert [r.model_dump() for r in record.opponent_gain_costs] == [{'recipient': 'p2', 'nominal_amount': 3}]
    assert mana_units.visible_pool(s.state, 'p1') == {}
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).pt == (6, 6)
    roundtrip(s)


def test_actual_cold_tax_allocation_keeps_real_mana_source_identity(cards, tmp_path):
    from app.rules import mana_units
    from tests.test_rules_linked_return_family import cold_choose

    s, spell, target, land = scene(cards)
    put(s, 'Thalia, Guardian of Thraben', 'battlefield', pid='p2')
    put(s, 'Lodestone Golem', 'battlefield', pid='p2')
    put(s, "Alhammarret's Archive", 'battlefield', pid='p2')
    put(s, 'Angel of Vitality', 'battlefield', pid='p2')
    ring = put(s, 'Sol Ring', 'battlefield')
    ring_oid = s.state.rules.object_id(ring.id)
    act(s, 'p1', type='tap', card_ids=[land.id], tapped=True)
    act(s, 'p1', type='activate_ability', card_id=ring.id, ability=0)
    cast_alt(s, spell, target)
    d = s.state.rules.decision
    assert d is not None
    allocation = d.resume['then']['payload']['payment']
    assert allocation['spent'] == {'C': 2} and allocation['sources'] == [ring_oid, ring_oid]
    from app.rules import payment_continuations as pc

    assert pc.payment_data(pc.payment_of(allocation)) == allocation
    assert s.state.cards[ring.id].tapped
    option = next(o.id for o in d.options if 'Archive' in o.label)
    s = cold_choose(s, cards, tmp_path, [option])
    record = payment(s, spell)
    assert record.mana_spent == {'C': 2} and record.mana_sources == allocation['sources']
    assert s.state.cards[ring.id].tapped and mana_units.visible_pool(s.state, 'p1') == {}
    assert s.state.players['p2'].life == 47 and len(record.opponent_gain_costs) == 1
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).pt == (6, 6)
    roundtrip(s)
