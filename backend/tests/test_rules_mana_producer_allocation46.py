import pytest
from app.rules import mana as M
from app.rules.mana_allocation_masks import MaskedSource, Slot, settle, solve
from app.rules.mana_requirement_rows import ProducerFact, ProducerRequirement as P, Requirement, RequirementPlan

CREATURE=ProducerFact(('Creature',),'p1:battlefield')
BASIC=ProducerFact(('Basic','Land'),'p1:battlefield')

def source(cid,fact,sym='G',mask=True):
    return MaskedSource(M.Source(cid,((sym,),),generic_allowed=(mask,),producer_facts=((fact,),)))

@pytest.mark.parametrize('iterative',[False,True])
def test_same_color_class_settlement(iterative):
    result=solve(M.ManaCost(1),{},[source('land',BASIC),source('elf',CREATURE)],iterative=iterative,
        plan=RequirementPlan(0,(Requirement(M.ALL_MANA,generic=True,producer=P.CREATURE_PERMANENT),)))
    assert result.payment.tapped==['elf']
    result_slots=[Slot(row.unit,'elf') for row in result.allocation]
    assert len(settle(result.allocation,result_slots).spent)==1

@pytest.mark.parametrize('iterative',[False,True])
def test_unknown_plain_pool_cannot_pay_producer_rows(iterative):
    with pytest.raises(M.ManaError):
        solve(M.ManaCost(1),{'G':5},[],iterative=iterative,
            plan=RequirementPlan(0,(Requirement(M.ALL_MANA,generic=True,producer=P.CREATURE_PERMANENT),)))

@pytest.mark.parametrize('iterative',[False,True])
def test_numeric_hybrid_retains_producer_on_generic_branch(iterative):
    rows=RequirementPlan(0,(Requirement(('2','G'),producer=P.CREATURE_PERMANENT),))
    with pytest.raises(M.ManaError):
        solve(M.ManaCost(hybrid=(('2','G'),)),{},[source('land1',BASIC,'C'),source('land2',BASIC,'C')],plan=rows,iterative=iterative)
    result=solve(M.ManaCost(hybrid=(('2','G'),)),{},[source('elf1',CREATURE,'C'),source('elf2',CREATURE,'C')],plan=rows,iterative=iterative)
    assert result.payment.spent=={'C':2}

@pytest.mark.parametrize('iterative',[False,True])
def test_unrestricted_input_and_constrained_spell_rows_survive_merge(iterative):
    rows=RequirementPlan(1,(Requirement(M.ALL_MANA,generic=True,producer=P.CREATURE_PERMANENT),))
    result=solve(M.ManaCost(2),{},[source('land',BASIC),source('elf',CREATURE)],plan=rows,iterative=iterative)
    assert set(result.payment.tapped)=={'land','elf'}


def test_nonmana_generic_helpers_are_not_mana_with_an_ineligible_producer():
    from app.rules.mana_allocation_masks import constrain_producer
    helpers=[MaskedSource(M.Source(cid,(('1',),),abilities=(-2,))) for cid in ('helper1','helper2')]
    cost=constrain_producer(M.ManaCost(2),P.CREATURE_PERMANENT)
    result=solve(cost,{},helpers)
    assert set(result.payment.tapped)=={'helper1','helper2'}
    assert result.payment.spent=={'1':2}


def test_same_color_output_positions_can_have_different_producers():
    src = MaskedSource(M.Source('forest-plus-keeper', (('G','G'),), producer_facts=((BASIC, CREATURE),)))
    result = solve(M.ManaCost(1), {}, [src], plan=RequirementPlan(0,(Requirement(M.ALL_MANA,generic=True,producer=P.CREATURE_PERMANENT),)))
    assert len(result.allocation)==1
    assert result.allocation[0].unit.producer==CREATURE
    assert sum(result.remaining.values())==1
    assert next(iter(result.remaining)).producer==BASIC


def test_duplicate_nominal_options_preserve_source_and_original_ability_indices():
    snow=ProducerFact(('Creature','Snow'),'p1:battlefield')
    src=MaskedSource(M.Source('same',(('G','G'),('G','G')),abilities=(5,5),ability_options=(3,7),
        producer_facts=((BASIC,CREATURE),(BASIC,snow))))
    paid=solve(M.ManaCost(colored=('S',)),{},[src],
        plan=RequirementPlan(0,(Requirement(('S',),producer=P.CREATURE_PERMANENT),)))
    assert paid.payment.selected_options==[('same',1)]
    assert paid.payment.ability_options==[('same',7)]
    assert paid.allocation[0].unit.producer==snow


def test_ordinary_snow_requirement_uses_each_output_actual_producer():
    snow_basic=ProducerFact(('Snow','Basic','Land'),'p1:battlefield')
    src=M.Source('snow-land-plus-bonus',(('G','G'),),snow=True,producer_facts=((snow_basic,CREATURE),))
    with pytest.raises(M.ManaError):
        M.solve(M.ManaCost(colored=('S','S')),{},[src])
    snow_bonus=ProducerFact(('Snow','Enchantment'),'p1:battlefield')
    src=M.Source('ordinary-land-plus-snow-bonus',(('G','G'),),producer_facts=((BASIC,snow_bonus),))
    paid=M.solve(M.ManaCost(colored=('S',)),{},[src])
    assert len(paid.allocation)==1 and paid.allocation[0].unit.producer==snow_bonus
