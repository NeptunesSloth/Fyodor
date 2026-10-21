"""Unimported Morningtide's Light through native targets, return and next-turn shield."""

from tests import test_rules_delayed_blinks50 as gameplay
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards




def test_morningtide_actual_foreign_target_returns_tapped_self_exiles_and_shield_until_next_turn(cards):
    s=gameplay.gameplay.setup(cards,"Morningtide's Light",'Lightning Bolt')
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,"Morningtide's Light",targets=[target.id],target_counts=[1])
    assert s.state.cards[target.id].zone=='p2:exile'
    spell=next(c for c in s.state.cards.values() if c.name=="Morningtide's Light" and c.zone=='p1:exile')
    cast(s,'Lightning Bolt',targets=['p1'])
    assert s.state.players['p1'].life==40
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[target.id].zone=='p2:battlefield'
    assert s.state.cards[target.id].tapped
    to_phase(s,'main1',turn=4)
    cast(s,'Lightning Bolt',targets=['p1'])
    assert s.state.players['p1'].life==37
    assert s.state.cards[spell.id].zone=='p1:exile'
    roundtrip(s)


def test_morningtide_zero_targets_still_exiles_and_prevents_opponents_combat_until_next_turn(cards):
    s=gameplay.gameplay.setup(cards,"Morningtide's Light")
    attacker=put(s,'Grizzly Bears','battlefield',pid='p2')
    spell=cast(s,"Morningtide's Light",targets=[],target_counts=[0])
    assert s.state.cards[spell.id].zone=='p1:exile'
    to_phase(s,'declare_attackers',turn=2)
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p1'}])
    to_phase(s,'main2',turn=2)
    assert s.state.players['p1'].life==40
    to_phase(s,'declare_attackers',turn=5)
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p1'}])
    to_phase(s,'main2',turn=5)
    assert s.state.players['p1'].life==38
    roundtrip(s)


def test_morningtide_all_targets_illegal_means_no_shield_or_self_exile(cards):
    from tests.test_rules_bandmate_references import mana

    s=gameplay.gameplay.setup(cards,"Morningtide's Light",'Murder','Lightning Bolt')
    target=put(s,'Grizzly Bears','battlefield')
    spell=put(s,"Morningtide's Light",'hand')
    mana(s,W=2,C=5)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[target.id],target_counts=[1])
    cast(s,'Murder',targets=[target.id])
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert not s.state.rules.delayed
    cast(s,'Lightning Bolt',targets=['p1'])
    assert s.state.players['p1'].life==37
    roundtrip(s)


def test_morningtide_partial_illegal_targets_exiles_actual_legal_subset_and_shields(cards):
    from tests.test_rules_bandmate_references import mana

    s=gameplay.gameplay.setup(cards,"Morningtide's Light",'Murder','Lightning Bolt')
    first=put(s,'Grizzly Bears','battlefield')
    second=put(s,'Grizzly Bears','battlefield',pid='p2')
    spell=put(s,"Morningtide's Light",'hand')
    mana(s,W=2,C=5)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[first.id,second.id],target_counts=[2])
    cast(s,'Murder',targets=[first.id])
    settle(s)
    assert s.state.cards[first.id].zone=='p1:graveyard'
    assert s.state.cards[second.id].zone=='p2:exile'
    assert s.state.cards[spell.id].zone=='p1:exile'
    cast(s,'Lightning Bolt',targets=['p1'])
    assert s.state.players['p1'].life==40
    roundtrip(s)


def test_morningtide_genuine_cold_delayed_tapped_return_and_persisted_shield(cards,tmp_path):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_exile_outcomes42_cold import fresh

    s=gameplay.gameplay.setup(cards,"Morningtide's Light",'Lightning Bolt')
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,"Morningtide's Light",targets=[target.id],target_counts=[1])
    to_phase(s,'end',turn=1)
    s=fresh(s,cards,tmp_path/'return.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[target.id].zone=='p2:battlefield'
    assert s.state.cards[target.id].tapped
    bolt=put(s,'Lightning Bolt','hand')
    mana(s,R=1)
    s=fresh(s,cards,tmp_path/'shield.json','p1',{'type':'cast_spell','card_id':bolt.id,'targets':['p1']})
    assert s.state.players['p1'].life==40
    roundtrip(s)


def test_morningtide_whole_canonical_coverage(cards):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve("Morningtide's Light"))
    assert result.level=='FULL',result
