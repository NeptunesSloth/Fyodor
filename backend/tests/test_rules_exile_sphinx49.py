"""Ur-Sphinx through production eminence, attacks, mill and casting."""
import pytest

from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards


@pytest.mark.parametrize('zone',['command','battlefield'])
def test_ur_sphinx_actual_eminence_reduces_other_sphinx_generic_cost_in_named_zones(cards,zone):
    s=gameplay.setup(cards,'The Ur-Sphinx','Serra Sphinx')
    put(s,'The Ur-Sphinx',zone)
    spell=put(s,'Serra Sphinx','hand')
    mana(s,U=2,C=2)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_ur_sphinx_actual_nonattacking_source_counts_declared_sphinx_and_mills_all_before_each_quota(cards):
    s=gameplay.setup(cards,'The Ur-Sphinx','Serra Sphinx')
    source=put(s,'The Ur-Sphinx','battlefield')
    attacker=put(s,'Serra Sphinx','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    milled={p:put(s,'Divination','library',pid=p) for p in ('p1','p2','p3')}
    prior=put(s,'Giant Growth','graveyard',pid='p2')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p2'}])
    settle(s)
    assert all(s.state.cards[c.id].zone==p+':graveyard' for p,c in milled.items())
    assert s.state.cards[source.id].attacking is None
    for player in ('p1','p2','p3'):
        d=s.state.rules.decision
        assert d.resume['step']=='free_cast_pick'
        assert milled[player].id in [o.card_id for o in d.options]
        assert prior.id not in [o.card_id for o in d.options]
        answer(s,[milled[player].id])
    assert all(s.state.cards[c.id].zone==p+':graveyard' for p,c in milled.items())
    assert s.state.cards[prior.id].zone=='p2:graveyard'
    roundtrip(s)


def test_ur_sphinx_eminence_does_not_apply_from_graveyard_or_reduce_its_own_spell(cards):
    from app.game.errors import ActionError

    s=gameplay.setup(cards,'The Ur-Sphinx','Serra Sphinx')
    source=put(s,'The Ur-Sphinx','graveyard')
    spell=put(s,'Serra Sphinx','hand')
    mana(s,U=2,C=2)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id)
    assert s.state.model_dump_json()==before
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='set_commander',card_id=source.id)
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'command','player':'p1'})
    mana(s,U=1,W=1,B=1,C=5)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id)
    assert s.state.model_dump_json()==before
    mana(s,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_ur_sphinx_two_actual_declared_attackers_remain_counted_after_source_dies(cards):
    from tests.test_rules_ordered_tutor_continuations import cast

    s=gameplay.setup(cards,'The Ur-Sphinx','Serra Sphinx','Serra Sphinx','Murder')
    source=put(s,'The Ur-Sphinx','battlefield')
    first=put(s,'Serra Sphinx','battlefield')
    second=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Serra Sphinx' and c.id!=first.id)
    act(s,'p1',type='move',card_ids=[second.id],to={'zone':'battlefield','player':'p1'})
    put(s,'Grizzly Bears','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    first_cards={p:put(s,'Divination','library',pid=p) for p in ('p1','p2','p3')}
    second_cards={p:put(s,'Giant Growth','library',pid=p) for p in ('p1','p2','p3')}
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':c.id,'target':'p2'} for c in (first,second)])
    cast(s,'Murder',targets=[source.id])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert all(s.state.cards[c.id].zone==p+':graveyard' for p,c in [*first_cards.items(),*second_cards.items()])
    for player in ('p1','p2','p3'):
        d=s.state.rules.decision
        assert {first_cards[player].id,second_cards[player].id} <= {o.card_id for o in d.options}
        answer(s,[first_cards[player].id])
    assert all(s.state.cards[c.id].zone==p+':graveyard' for p,c in second_cards.items())
    roundtrip(s)


def test_ur_sphinx_actual_mill_replacement_expands_exact_opponent_packets_and_preserves_own_count(cards):
    s=gameplay.setup(cards,'The Ur-Sphinx','Serra Sphinx','Bruvac the Grandiloquent')
    put(s,'The Ur-Sphinx','battlefield')
    attacker=put(s,'Serra Sphinx','battlefield')
    put(s,'Bruvac the Grandiloquent','battlefield')
    put(s,'Grizzly Bears','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    second={p:put(s,'Giant Growth','library',pid=p) for p in ('p1','p2','p3')}
    first={p:put(s,'Divination','library',pid=p) for p in ('p1','p2','p3')}
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p2'}])
    settle(s)
    assert s.state.cards[second['p1'].id].zone=='p1:library'
    assert all(s.state.cards[second[p].id].zone==p+':graveyard' for p in ('p2','p3'))
    for p in ('p1','p2','p3'):
        ids={o.card_id for o in s.state.rules.decision.options}
        assert first[p].id in ids
        assert (second[p].id in ids)==(p!='p1')
        answer(s,[])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_ur_sphinx_exile_replacement_produces_no_milled_card_cast_permissions(cards):
    s=gameplay.setup(cards,'The Ur-Sphinx','Serra Sphinx','Rest in Peace')
    put(s,'The Ur-Sphinx','battlefield')
    attacker=put(s,'Serra Sphinx','battlefield')
    put(s,'Rest in Peace','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    first={p:put(s,'Divination','library',pid=p) for p in ('p1','p2','p3')}
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p2'}])
    settle(s)
    assert all(s.state.cards[c.id].zone==p+':exile' for p,c in first.items())
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    assert not s.state.rules.permissions
    roundtrip(s)


def test_ur_sphinx_entering_attacking_sphinx_is_not_a_declared_attack_trigger(cards):
    s=gameplay.setup(cards,'The Ur-Sphinx','Serra Sphinx','Yore-Tiller Nephilim')
    put(s,'The Ur-Sphinx','battlefield')
    attacker=put(s,'Yore-Tiller Nephilim','battlefield')
    sphinx=put(s,'Serra Sphinx','graveyard')
    to_phase(s,'declare_attackers',turn=4)
    top=put(s,'Divination','library')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p2'}])
    settle(s)
    answer(s,[sphinx.id])
    if s.state.rules.decision is not None:
        answer(s,['p2'])
    assert s.state.cards[sphinx.id].zone=='p1:battlefield'
    assert s.state.cards[sphinx.id].attacking is not None
    assert s.state.cards[top.id].zone=='p1:library'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_ur_sphinx_exact_milled_creature_and_adventure_spell_are_cast_but_land_is_not_played(cards):
    s=gameplay.setup(cards,'The Ur-Sphinx','Serra Sphinx','Two-Handed Axe // Sweeping Cleave','Forest')
    put(s,'The Ur-Sphinx','battlefield')
    attacker=put(s,'Serra Sphinx','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    creature=put(s,'Grizzly Bears','library')
    adventure=put(s,'Two-Handed Axe // Sweeping Cleave','library',pid='p2')
    land=put(s,'Forest','library',pid='p3')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p2'}])
    settle(s)
    answer(s,[creature.id])
    assert s.state.cards[creature.id].zone=='stack'
    ids={o.id for o in s.state.rules.decision.options}
    assert {adventure.id+'@0',adventure.id+'@1'} <= ids
    answer(s,[adventure.id+'@1'])
    if s.state.rules.decision is not None:
        answer(s,[attacker.id])
    assert s.state.cards[creature.id].zone=='p1:battlefield'
    assert s.state.cards[adventure.id].zone=='p2:exile'
    assert s.state.cards[land.id].zone=='p3:graveyard'
    assert s.state.rules.lands_this_turn('p1',s.state.turn.number)==0
    assert s.state.rules.decision is None
    roundtrip(s)


def test_ur_sphinx_free_x_is_zero_and_mandatory_additional_discard_is_paid(cards):
    s=gameplay.setup(cards,'The Ur-Sphinx','Serra Sphinx','Earthquake','Cathartic Reunion','Forest')
    put(s,'The Ur-Sphinx','battlefield')
    attacker=put(s,'Serra Sphinx','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    first=put(s,'Earthquake','library')
    second=put(s,'Cathartic Reunion','library',pid='p2')
    put(s,'Forest','library',pid='p3')
    discards=[put(s,name,'hand').id for name in ('Giant Growth','Divination')]
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p2'}])
    settle(s)
    answer(s,[first.id])
    answer(s,[second.id])
    if s.state.rules.decision is not None:
        assert s.state.rules.decision.resume['step']=='ability_cost'
        answer(s,discards)
    assert all(s.state.players[p].life==40 for p in ('p1','p2','p3'))
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in discards)
    assert s.state.cards[first.id].zone=='p1:graveyard'
    assert s.state.cards[second.id].zone=='p2:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)
