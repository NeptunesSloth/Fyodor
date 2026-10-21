"""Unimported exact Legion's Initiative using native costs and next-combat scheduler."""
import pytest

from tests import test_rules_delayed_blinks50 as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards




def test_legion_actual_exile_source_cost_returns_at_next_combat_with_real_haste(cards):
    s=gameplay.gameplay.setup(cards,"Legion's Initiative")
    source=put(s,"Legion's Initiative",'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    mana(s,R=1,W=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    assert s.state.cards[source.id].zone=='p1:exile'
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:exile'
    to_phase(s,'begin_combat',turn=1)
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    to_phase(s,'declare_attackers',turn=1)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p2'}])
    to_phase(s,'main2',turn=1)
    assert s.state.players['p2'].life==38
    roundtrip(s)


def test_legion_red_white_static_bonuses_only_controlled_creatures_real_damage(cards):
    s=gameplay.gameplay.setup(cards,"Legion's Initiative")
    put(s,"Legion's Initiative",'battlefield')
    attackers=[]
    for name,colors in [('Both',['R','W']),('Red',['R']),('White',['W'])]:
        act(s,'p1',type='create_token',player='p1',token={'name':name,'type_line':'Token Creature — Soldier','power':'1','toughness':'1','text':'','colors':colors})
        attackers.append(next(c.id for c in s.state.cards.values() if c.name==name))
    attackers.append(put(s,'Grizzly Bears','battlefield').id)
    act(s,'p1',type='create_token',player='p2',token={'name':'Foreign Both','type_line':'Token Creature — Soldier','power':'1','toughness':'1','text':'','colors':['R','W']})
    foreign=next(c for c in s.state.cards.values() if c.name=='Foreign Both')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':cid,'target':'p2'} for cid in attackers])
    to_phase(s,'main2',turn=4)
    assert s.state.players['p2'].life==33
    to_phase(s,'declare_attackers',turn=5)
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':foreign.id,'target':'p1'}])
    to_phase(s,'main2',turn=5)
    assert s.state.players['p1'].life==39
    roundtrip(s)


def test_legion_next_combat_opponents_turn_no_attack_intended_haste_expires_at_end_of_that_turn(cards):
    from app.game.errors import ActionError

    s=gameplay.gameplay.setup(cards,"Legion's Initiative")
    source=put(s,"Legion's Initiative",'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'end',turn=1)
    mana(s,R=1,W=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:exile'
    to_phase(s,'begin_combat',turn=2)
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    act(s,'p2',type='set_controller',card_ids=[bear.id],player='p2')
    to_phase(s,'declare_attackers',turn=2)
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p1'}])
    to_phase(s,'main1',turn=3)
    act(s,'p3',type='set_controller',card_ids=[bear.id],player='p3')
    to_phase(s,'declare_attackers',turn=3)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p3',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p1'}])
    assert s.state.model_dump_json()==before
    roundtrip(s)


def test_legion_stifled_activated_ability_leaves_source_exiled_without_exiling_creatures(cards):
    from tests.test_rules_ordered_tutor_continuations import cast

    s=gameplay.gameplay.setup(cards,"Legion's Initiative",'Stifle')
    source=put(s,"Legion's Initiative",'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    mana(s,R=1,W=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    ability=next(k for k,e in s.state.rules.stack.items() if e.kind=='activated' and e.source_card==source.id)
    cast(s,'Stifle',targets=[ability])
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert not s.state.rules.delayed
    roundtrip(s)


def test_legion_genuine_cold_next_combat_return_then_actual_haste_attack(cards,tmp_path):
    s=gameplay.gameplay.setup(cards,"Legion's Initiative")
    source=put(s,"Legion's Initiative",'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    mana(s,R=1,W=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    settle(s)
    to_phase(s,'begin_combat',turn=1)
    s=stage_fresh(s,cards,tmp_path/'combat.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    to_phase(s,'declare_attackers',turn=1)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p2'}])
    to_phase(s,'main2',turn=1)
    assert s.state.players['p2'].life==38
    roundtrip(s)


def test_legion_whole_canonical_coverage(cards):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve("Legion's Initiative"))
    assert result.level=='FULL',result


def stage_fresh(s,cards,path,actor,payload):
    import json
    import subprocess
    import sys
    from pathlib import Path

    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code='''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(path.parent/'cold-images'))
s=GameSession(GameState.model_validate_json(path.read_text()),cards=repo)
s.perform(sys.argv[3],json.loads(sys.argv[4]))
while s.state.rules.decision is None and s.state.zones.get('stack'):
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
path.write_text(s.state.model_dump_json())
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),actor,json.dumps(payload)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()),cards=cards)
