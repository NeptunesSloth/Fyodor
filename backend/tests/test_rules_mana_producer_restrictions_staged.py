"""Pure, unimported allocation witnesses; not whole-card engine coverage."""
from itertools import permutations

import pytest

from app.rules.mana_producer_restrictions_staged import (
    ProducerFact,
    Row,
    Unit,
    allocations,
    eligible,
    filtered_allocations,
)
from app.rules.mana_producer_restrictions_staged import (
    ProducerRequirement as P,
)
from app.rules.mana_requirement_rows import Requirement
from tests.test_rules_mana_followthrough_profiles import cards  # noqa: F401

CREATURE = ProducerFact(('Creature', 'Elf'), 'a:battlefield')
BASIC = ProducerFact(('Basic', 'Land', 'Forest'), 'a:battlefield')
NONBASIC = ProducerFact(('Land', 'Forest'), 'a:battlefield')
ANIMATED = ProducerFact(('Basic', 'Land', 'Creature'), 'a:battlefield')
GENERIC = ('W', 'U', 'B', 'R', 'G', 'C')


def row(predicate=None, colors=GENERIC, generic=True):
    return Row(Requirement(colors, generic=generic), predicate)


@pytest.mark.parametrize(('fact', 'predicate', 'expected'), [
    (CREATURE, P.CREATURE_PERMANENT, True),
    (ProducerFact(('Creature', 'Elf'), 'a:hand'), P.CREATURE_PERMANENT, False),
    (ProducerFact(('Creature', 'Elf'), 'a:exile'), P.CREATURE_PERMANENT, False),
    (ProducerFact(('Creature',), 'stack'), P.CREATURE_PERMANENT, False),
    (ProducerFact(('Creature',), None), P.CREATURE_PERMANENT, False),
    (None, P.CREATURE_PERMANENT, False),
    (BASIC, P.BASIC_LAND, True),
    (NONBASIC, P.BASIC_LAND, False),
    (ProducerFact(('Basic',), 'a:battlefield'), P.BASIC_LAND, False),
    (ANIMATED, P.BASIC_LAND, True),
    (ANIMATED, P.CREATURE_PERMANENT, True),
    (ProducerFact(('Treasure', 'Artifact'), 'a:battlefield'), P.TREASURE, True),
    (ProducerFact(('Treasure', 'Artifact'), 'a:graveyard'), P.TREASURE, False),
    (None, None, True),
])
def test_actual_producer_eligibility_requires_known_battlefield(fact, predicate, expected):
    assert eligible(fact, predicate) is expected


def test_same_color_exact_settlement_preserves_ineligible_and_unknown_units():
    units = (Unit('land', 'G', BASIC), Unit('elf', 'G', CREATURE), Unit('old', 'G'))
    assert allocations(units, (row(P.CREATURE_PERMANENT),)) == (('elf',),)
    assert allocations(units, (row(P.BASIC_LAND),)) == (('land',),)


def test_filter_can_consume_ineligible_mana_to_produce_eligible_output():
    paid = filtered_allocations((Unit('forest', 'G', BASIC),), (row(),),
                                (Unit('creature-output', 'G', CREATURE),),
                                (row(P.CREATURE_PERMANENT),))
    assert [(r.inputs, r.final) for r in paid] == [(('forest',), ('creature-output',))]


def test_filter_output_cannot_inherit_its_inputs_creature_producer():
    assert not filtered_allocations((Unit('elf', 'G', CREATURE),), (row(),),
                                   (Unit('land-output', 'G', NONBASIC),),
                                   (row(P.CREATURE_PERMANENT),))


def test_filter_output_cannot_fund_own_activation():
    assert not filtered_allocations((), (row(),), (Unit('out', 'G', CREATURE),),
                                   (row(P.CREATURE_PERMANENT),))


def test_merged_cost_rows_keep_activation_and_spell_producer_scopes_separate():
    units = (Unit('forest', 'G', BASIC), Unit('elf', 'G', CREATURE))
    assert allocations(units, (row(), row(P.CREATURE_PERMANENT))) == (('forest', 'elf'),)
    assert allocations(units, (row(P.CREATURE_PERMANENT), row())) == (('elf', 'forest'),)


def test_generic_mask_and_producer_predicate_are_independent():
    jag = Unit('jegantha', 'G', CREATURE, generic_allowed=False)
    assert not allocations((jag,), (row(P.CREATURE_PERMANENT),))
    assert allocations((jag,), (row(P.CREATURE_PERMANENT, ('G',), False),)) == (('jegantha',),)
    assert not allocations((jag,), (row(P.BASIC_LAND, ('G',), False),))


def test_as_though_alternatives_do_not_erase_producer_predicate():
    units = (Unit('land', 'C', BASIC), Unit('creature', 'C', CREATURE))
    assert allocations(units, (row(P.CREATURE_PERMANENT, ('R', 'C'), False),)) == (('creature',),)


def test_snow_requires_actual_mana_but_nonmana_helpers_bypass_producer_check():
    helper = Unit('convoke', 'G', helper=True)
    assert allocations((helper,), (row(P.BASIC_LAND, ('G',), False),)) == (('convoke',),)
    assert not allocations((helper,), (row(P.BASIC_LAND, ('S',), False),))
    assert allocations((Unit('snow-basic', 'G', BASIC, snow=True),),
                       (row(P.BASIC_LAND, ('S',), False),)) == (('snow-basic',),)


def test_zero_mana_cost_requires_no_known_producer_fact():
    assert allocations((Unit('unknown', 'G'),), ()) == ((),)


def test_allocator_matches_exhaustive_distinct_unit_oracle_under_order_changes():
    units = (Unit('land', 'G', BASIC), Unit('elf', 'G', CREATURE), Unit('old', 'G'),
             Unit('animated', 'G', ANIMATED))
    rows = (row(P.CREATURE_PERMANENT), row(P.BASIC_LAND), row())
    expected = {tuple(u.id for u in receipt) for receipt in permutations(units, 3)
                if receipt[0].id in {'elf', 'animated'} and receipt[1].id in {'land', 'animated'}}
    for ordered in permutations(units):
        assert set(allocations(ordered, rows)) == expected


def test_no_exact_unit_identity_can_be_spent_twice():
    with pytest.raises(ValueError, match='Duplicate'):
        allocations((Unit('same', 'G', BASIC), Unit('same', 'G', CREATURE)), (row(),))


def test_independent_bonus_keeps_own_producer_while_replacement_output_keeps_land():
    # One basic-land event doubled to GG; an independent Kinnan event adds G.
    units = (Unit('basic-original', 'G', BASIC), Unit('basic-replacement', 'G', BASIC),
             Unit('kinnan-bonus', 'G', CREATURE))
    assert set(allocations(units, (row(P.BASIC_LAND), row(P.BASIC_LAND)))) == {
        ('basic-original', 'basic-replacement'), ('basic-replacement', 'basic-original')}
    assert allocations(units, (row(P.CREATURE_PERMANENT),)) == (('kinnan-bonus',),)
    assert not allocations(units, (row(P.BASIC_LAND),) * 3)


def test_two_filter_inputs_cannot_spend_the_same_known_unit():
    output = (Unit('out1', 'G', CREATURE), Unit('out2', 'G', CREATURE))
    assert not filtered_allocations((Unit('land', 'G', BASIC),), (row(), row()), output,
                                   (row(P.CREATURE_PERMANENT),) * 2)


def test_actual_colored_requirement_origin_survives_helper_alternative_encoding():
    requirement = Row(Requirement(('R', 'C'), generic=False, helpers=('R',)), P.CREATURE_PERMANENT)
    assert allocations((Unit('actual-C', 'C', CREATURE),), (requirement,))
    assert not allocations((Unit('green-helper', 'G', helper=True),), (requirement,))
    assert allocations((Unit('red-helper', 'R', helper=True),), (requirement,))


def test_numeric_hybrid_generic_branch_preserves_producer_and_generic_origins():
    hybrid = Row(Requirement(('2', 'G'), helpers=('2', 'G')), P.CREATURE_PERMANENT)
    units = (Unit('land1', 'C', BASIC), Unit('land2', 'C', BASIC))
    assert not allocations(units, (hybrid,))
    assert allocations((Unit('elf1', 'C', CREATURE), Unit('elf2', 'C', CREATURE)),
                       (hybrid,)) == (('elf1', 'elf2'), ('elf2', 'elf1'))
    assert allocations((Unit('jegantha-green', 'G', CREATURE, generic_allowed=False),),
                       (hybrid,)) == (('jegantha-green',),)
    assert not allocations((Unit('jegantha-C1', 'C', CREATURE, generic_allowed=False),
                            Unit('jegantha-C2', 'C', CREATURE, generic_allowed=False)), (hybrid,))


def test_native_exact_source_capture_preserves_departure_lki_and_rejects_new_incarnation(cards):  # noqa: F811
    from app.game.rules_state import ObjectRef
    from app.rules.mana_producer_restrictions_staged import capture
    from app.rules.plan import Plan
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Grizzly Bears'], [], [])
    source = put(s, 'Grizzly Bears', 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    original = ObjectRef(card=source.id, object_id=plan.oid(source), zone=source.zone)
    fact = capture(plan, original)
    assert eligible(fact, P.CREATURE_PERMANENT)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    assert capture(Plan(s.state, 'p1', cards, None), original) == fact
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert Plan(s.state, 'p1', cards, None).oid(s.state.cards[source.id]) != original.object_id
    assert capture(Plan(s.state, 'p1', cards, None), original) == fact
    roundtrip(s)
    assert capture(Plan(s.state, 'p1', cards, None), original) == fact
    del s.state.rules.lki[original.object_id]
    assert capture(Plan(s.state, 'p1', cards, None), original) is None
