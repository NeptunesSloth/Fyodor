"""Anrakyr native production proofs after the numeric multikicker repair."""
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_exile_outcomes42_cold import fresh
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards


test_anrakyr_actual_attack_cast_artifact_pays_life_not_mana=gameplay.test_anrakyr_actual_attack_cast_artifact_pays_life_not_mana
test_anrakyr_actual_life_alternative_can_decline_and_cannot_afford_three_at_two_life=gameplay.test_anrakyr_actual_life_alternative_can_decline_and_cannot_afford_three_at_two_life
test_anrakyr_actual_trigger_counter_source_departure_or_optional_decline=gameplay.test_anrakyr_actual_trigger_counter_source_departure_or_optional_decline
test_anrakyr_actual_hand_artifact_x_forced_zero_and_artifact_land_is_not_a_spell=gameplay.test_anrakyr_actual_hand_artifact_x_forced_zero_and_artifact_land_is_not_a_spell
test_anrakyr_actual_artifact_spell_face_not_physical_card_front_controls_eligibility_and_life=gameplay.test_anrakyr_actual_artifact_spell_face_not_physical_card_front_controls_eligibility_and_life
test_anrakyr_actual_prohibition_on_paying_or_changing_life_does_not_offer_artifact=gameplay.test_anrakyr_actual_prohibition_on_paying_or_changing_life_does_not_offer_artifact
test_anrakyr_actual_life_alternative_preserves_optional_additional_mana_kicker=gameplay.test_anrakyr_actual_life_alternative_preserves_optional_additional_mana_kicker


def test_anrakyr_whole_canonical_production(cards):
    gameplay.test_staged_all_printed_lines_compile_without_fallback(cards,'Anrakyr the Traveller')


def test_anrakyr_cold_attack_to_artifact_life_alternative_payment(cards,tmp_path):
    s=gameplay.setup(cards,'Anrakyr the Traveller')
    source=put(s,'Anrakyr the Traveller','battlefield')
    altar=put(s,"Ashnod's Altar",'graveyard')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    d=s.state.rules.decision
    life=s.state.players['p1'].life
    s=fresh(s,cards,tmp_path/'life.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[altar.id]})
    assert s.state.players['p1'].life==life-3
    assert s.state.cards[altar.id].zone=='p1:battlefield'
