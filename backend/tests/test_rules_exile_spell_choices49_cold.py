"""Fresh-process Spark through production registrations."""
from tests import test_rules_exile_spell_choices49 as gameplay
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_exile_outcomes42_cold import fresh
from tests.test_rules_ordered_tutor_continuations import cast

cards=gameplay.cards



def test_spark_cold_optional_choice_then_normal_exact_land_play(cards,tmp_path):
    s=gameplay.gameplay.setup(cards,'Spark of Creativity','Forest')
    target=put(s,'Grizzly Bears','battlefield')
    top=put(s,'Forest','library')
    cast(s,'Spark of Creativity',targets=[target.id])
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'choice.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['play']})
    s=fresh(s,cards,tmp_path/'land.json','p1',{'type':'play_land','card_id':top.id})
    assert s.state.cards[top.id].zone=='p1:battlefield'
    assert s.state.cards[target.id].damage==0
    assert s.state.rules.lands_this_turn('p1',s.state.turn.number)==1
    roundtrip(s)
