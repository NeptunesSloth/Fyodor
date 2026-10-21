"""Isolated exact split-card continuations, with real paid casting and decisions."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
from tests.test_rules_ordered_tutor_continuations import cast


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for filename in ('exile_outcomes42_cards.json','exile_cast_outcomes45_cards.json','research_development50_cards.json'):
        for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures'/filename).read_text())):
            base[c['name']]=card(c['name'],set_code='rd50',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()




@pytest.mark.parametrize('draws',[0,1,2,3])
def test_development_three_real_iterations_each_opponent_decides_then_exact_draw_or_token(cards,draws):
    s=gameplay.setup(cards,'Research // Development')
    before=len(s.state.zones['p1:hand'])
    cast(s,'Research // Development',face=1)
    for i in range(3):
        d=s.state.rules.decision
        assert d.resume['step']=='development50' and d.player=='p2'
        answer(s,['no'])
        assert s.state.rules.decision.player=='p3'
        answer(s,['yes' if i<draws else 'no'])
    assert s.state.rules.decision is None
    tokens=[c for c in s.state.cards.values() if c.token and c.zone=='p1:battlefield' and c.name=='Elemental']
    assert len(tokens)==3-draws
    assert len(s.state.zones['p1:hand'])==before+draws
    from app.rules.plan import Plan

    for token in tokens:
        ch=Plan(s.state,'p1',cards,None).ch(token)
        assert token.controller=='p1' and ch.pt==(3,1)
        assert ch.colors==frozenset({'R'})
    roundtrip(s)


def test_development_first_opponent_acceptance_skips_second_and_resets_each_iteration(cards):
    s=gameplay.setup(cards,'Research // Development')
    before=len(s.state.zones['p1:hand'])
    cast(s,'Research // Development',face=1)
    for _ in range(3):
        assert s.state.rules.decision.player=='p2'
        answer(s,['yes'])
    assert s.state.rules.decision is None
    assert len(s.state.zones['p1:hand'])==before+3
    roundtrip(s)


def test_research_actual_commander_empty_import_still_shuffles(cards):
    s=gameplay.setup(cards,'Research // Development')
    before=set(s.state.zones['p1:library'])
    names=sorted(s.state.cards[cid].name for cid in before)
    names.remove('Research // Development')
    cast(s,'Research // Development',face=0)
    assert sorted(s.state.cards[cid].name for cid in s.state.zones['p1:library'])==names
    assert s.state.rules.decision is None
    assert before.isdisjoint(s.state.zones['p1:library'])
    roundtrip(s)


def test_development_genuine_cold_between_opponents_then_next_iteration(cards,tmp_path):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    s=gameplay.setup(cards,'Research // Development')
    cast(s,'Research // Development',face=1)
    answer(s,['no'])
    d=s.state.rules.decision
    assert d.player=='p3'
    path=tmp_path/'development.json'
    path.write_text(s.state.model_dump_json())
    code="""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
p=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['yes']})
p.write_text(s.state.model_dump_json())
repo.close()
"""
    result=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path)],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    s=GameSession(GameState.model_validate_json(path.read_text()),cards=cards)
    assert s.state.rules.decision.player=='p2'
    answer(s,['yes'])
    answer(s,['yes'])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_research_development_whole_canonical_coverage(cards):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve('Research // Development'))
    assert result.level=='FULL',result


def test_development_opponents_follow_actual_active_player_order(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s=gameplay.setup(cards,'Research // Development')
    to_phase(s,'main1',turn=3)
    from tests.game_helpers import act

    while s.state.rules.priority!='p1':
        act(s,s.state.rules.priority,type='pass_priority')
    cast(s,'Research // Development',face=1)
    for _ in range(3):
        assert s.state.rules.decision.player=='p3'
        answer(s,['no'])
        assert s.state.rules.decision.player=='p2'
        answer(s,['yes'])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_development_current_opponent_concedes_remaining_opponent_still_gets_same_round(cards):
    from tests.game_helpers import act

    s=gameplay.setup(cards,'Research // Development')
    before=len(s.state.zones['p1:hand'])
    cast(s,'Research // Development',face=1)
    assert s.state.rules.decision.player=='p2'
    act(s,'p2',type='concede')
    d=s.state.rules.decision
    assert d.player=='p3' and d.resume['e']['round']==0
    for i in range(3):
        assert s.state.rules.decision.resume['e']['round']==i
        answer(s,['yes'])
    assert len(s.state.zones['p1:hand'])==before+3
    assert not [c for c in s.state.cards.values() if c.token and c.zone=='p1:battlefield']
    roundtrip(s)


def test_development_future_opponent_concedes_current_choice_retained_no_round_omitted(cards):
    from tests.game_helpers import act

    s=gameplay.setup(cards,'Research // Development')
    cast(s,'Research // Development',face=1)
    decision=s.state.rules.decision.id
    act(s,'p3',type='concede')
    assert s.state.rules.decision.id==decision
    for i in range(3):
        assert s.state.rules.decision.player=='p2' and s.state.rules.decision.resume['e']['round']==i
        answer(s,['no'])
    tokens=[c for c in s.state.cards.values() if c.token and c.zone=='p1:battlefield' and c.name=='Elemental']
    assert len(tokens)==3
    roundtrip(s)


def _fresh_development(s,cards,path,actor,payload):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code="""
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
p=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
s.perform(sys.argv[3],json.loads(sys.argv[4]))
p.write_text(s.state.model_dump_json())
repo.close()
"""
    result=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),actor,json.dumps(payload)],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()),cards=cards)


def test_development_cold_last_opponent_departure_keeps_token_and_resumes_next_two_rounds(cards,tmp_path):
    s=gameplay.setup(cards,'Research // Development')
    before=len(s.state.zones['p1:hand'])
    cast(s,'Research // Development',face=1)
    answer(s,['no'])
    assert s.state.rules.decision.player=='p3'
    s=_fresh_development(s,cards,tmp_path/'departure.json','p3',{'type':'concede'})
    d=s.state.rules.decision
    assert d.player=='p2' and d.resume['e']['round']==1
    assert len([c for c in s.state.cards.values() if c.token and c.zone=='p1:battlefield' and c.name=='Elemental'])==1
    s=_fresh_development(s,cards,tmp_path/'next-round.json','p2',{'type':'choose','decision_id':d.id,'option_ids':['yes']})
    assert len(s.state.zones['p1:hand'])==before+1
    assert s.state.rules.decision.player=='p2' and s.state.rules.decision.resume['e']['round']==2
    answer(s,['no'])
    assert s.state.rules.decision is None
    assert len([c for c in s.state.cards.values() if c.token and c.zone=='p1:battlefield' and c.name=='Elemental'])==2
    roundtrip(s)


def test_development_original_caster_departure_stops_owned_resolving_spell(cards):
    from tests.game_helpers import act

    s=gameplay.setup(cards,'Research // Development')
    cast(s,'Research // Development',face=1)
    act(s,'p1',type='concede')
    assert s.state.rules.decision is None
    assert not [c for c in s.state.cards.values() if c.token and c.name=='Elemental']
    assert not s.state.zones['stack']
    roundtrip(s)
