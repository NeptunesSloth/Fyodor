"""Isolated one-line native outside-permission whitespace repair; real loyalty actions."""
import inspect
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import outside_game, scripts
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for name in ('exile_outcomes42_cards.json','exile_cast_outcomes45_cards.json','outside_game50_cards.json'):
        for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures'/name).read_text())):
            base[c['name']]=card(c['name'],set_code='og50',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_vivien_minus_five_real_loyalty_paid_no_impossible_commander_import_or_choice(cards):
    s=gameplay.setup(cards,'Vivien, Arkbow Ranger')
    cast(s,'Vivien, Arkbow Ranger')
    source=next(c for c in s.state.cards.values() if c.name=='Vivien, Arkbow Ranger' and c.zone=='p1:battlefield')
    act(s,'p1',type='counter',card_ids=[source.id],kind='loyalty',delta=1)
    hand=list(s.state.zones['p1:hand'])
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.zones['p1:hand']==hand
    assert s.state.rules.decision is None
    roundtrip(s)


def test_vivien_plus_one_native_division_trample_combat(cards):
    s=gameplay.setup(cards,'Vivien, Arkbow Ranger')
    cast(s,'Vivien, Arkbow Ranger')
    source=next(c for c in s.state.cards.values() if c.name=='Vivien, Arkbow Ranger' and c.zone=='p1:battlefield')
    own=put(s,'Grizzly Bears','battlefield')
    other=put(s,'Grizzly Bears','battlefield',pid='p3')
    blocker=put(s,'Grizzly Bears','battlefield',pid='p2')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[own.id,other.id],target_counts=[2],division=[1,1])
    settle(s)
    assert s.state.cards[own.id].counters.get('+1/+1')==1
    assert s.state.cards[other.id].counters.get('+1/+1')==1
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':own.id,'target':'p2'}])
    to_phase(s,'declare_blockers',turn=4)
    act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':blocker.id,'attacker_id':own.id}])
    for _ in range(40):
        if s.state.turn.phase=='main2':
            break
        d=s.state.rules.decision
        if d is not None:
            assert d.kind=='divide'
            act(s,d.player,type='choose',decision_id=d.id,amounts=[1 if o.id=='p2' else 2 for o in d.options])
        else:
            act(s,s.state.rules.priority,type='pass_priority')
    assert s.state.players['p2'].life==39
    assert s.state.cards[blocker.id].zone=='p2:graveyard'
    roundtrip(s)


def test_vivien_minus_three_actual_own_creature_power_damage(cards):
    s=gameplay.setup(cards,'Vivien, Arkbow Ranger')
    cast(s,'Vivien, Arkbow Ranger')
    source=next(c for c in s.state.cards.values() if c.name=='Vivien, Arkbow Ranger' and c.zone=='p1:battlefield')
    own=put(s,'Grizzly Bears','battlefield')
    foreign=put(s,'Grizzly Bears','battlefield',pid='p2')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,targets=[own.id,foreign.id],target_counts=[1,1])
    settle(s)
    assert s.state.cards[foreign.id].zone=='p2:graveyard'
    assert s.state.cards[own.id].zone=='p1:battlefield'
    assert s.state.cards[source.id].counters['loyalty']==1
    roundtrip(s)


def test_vivien_insufficient_loyalty_and_once_per_turn_rejected_atomically(cards):
    from app.game.errors import ActionError

    s=gameplay.setup(cards,'Vivien, Arkbow Ranger')
    cast(s,'Vivien, Arkbow Ranger')
    source=next(c for c in s.state.cards.values() if c.name=='Vivien, Arkbow Ranger' and c.zone=='p1:battlefield')
    own=put(s,'Grizzly Bears','battlefield')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError,match='loyalty'):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    assert s.state.model_dump_json()==before
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[own.id],target_counts=[1])
    settle(s)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError,match='already used'):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    assert s.state.model_dump_json()==before
    roundtrip(s)


def test_vivien_minus_three_cannot_use_foreign_creature_as_source_and_illegal_own_target_deals_no_damage(cards):
    from app.game.errors import ActionError

    s=gameplay.setup(cards,'Vivien, Arkbow Ranger','Murder')
    cast(s,'Vivien, Arkbow Ranger')
    source=next(c for c in s.state.cards.values() if c.name=='Vivien, Arkbow Ranger' and c.zone=='p1:battlefield')
    own=put(s,'Grizzly Bears','battlefield')
    foreign=put(s,'Grizzly Bears','battlefield',pid='p2')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1,targets=[foreign.id,own.id],target_counts=[1,1])
    assert s.state.model_dump_json()==before
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,targets=[own.id,foreign.id],target_counts=[1,1])
    cast(s,'Murder',targets=[own.id])
    settle(s)
    assert s.state.cards[foreign.id].zone=='p2:battlefield'
    assert s.state.cards[foreign.id].damage==0
    roundtrip(s)


def test_vivien_cold_pending_minus_five_native_cost_and_impossible_import(cards,tmp_path):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    s=gameplay.setup(cards,'Vivien, Arkbow Ranger')
    cast(s,'Vivien, Arkbow Ranger')
    source=next(c for c in s.state.cards.values() if c.name=='Vivien, Arkbow Ranger' and c.zone=='p1:battlefield')
    act(s,'p1',type='counter',card_ids=[source.id],kind='loyalty',delta=1)
    hand=list(s.state.zones['p1:hand'])
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    path=tmp_path/'cold.json'
    path.write_text(s.state.model_dump_json())
    code='''
import inspect,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import outside_game
path=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(path.parent/'images'))
s=GameSession(GameState.model_validate_json(path.read_text()),cards=repo)
while s.state.rules.decision is None and s.state.zones.get('stack'):
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
path.write_text(s.state.model_dump_json())
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    s=GameSession(GameState.model_validate_json(path.read_text()),cards=cards)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.zones['p1:hand']==hand
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.fixture()
def coax_stage(monkeypatch):
    import re

    from app.rules import effects

    pattern=re.compile(outside_game._EXILE_OR_OUTSIDE.pattern.replace('(?P<what>artifact)','(?P<what>artifact|Eldrazi)'))
    monkeypatch.setattr(outside_game,'_EXILE_OR_OUTSIDE',pattern)
    source=inspect.getsource(outside_game.combined).replace("return ([{'do': 'outside_permission', 'exile_choice': sel.key()}], None, False)","return ([{'do': 'outside_permission', 'exile_choice': sel.key(), 'label': f\"a face-up {m['what']} card you own in exile\"}], None, False)")
    namespace=dict(outside_game.__dict__)
    exec(source,namespace)
    monkeypatch.setattr(outside_game,'combined',namespace['combined'])
    source=inspect.getsource(outside_game.permission).replace("'label': 'a face-up artifact card you own in exile'","'label': e.get('label', 'a face-up artifact card you own in exile')")
    exec(source,namespace)
    monkeypatch.setattr(outside_game,'permission',namespace['permission'])
    monkeypatch.setitem(effects.PRIMITIVES,'outside_permission',namespace['permission'])
    scripts._cached.cache_clear()
    yield
    scripts._cached.cache_clear()


def test_coax_native_owned_faceup_eldrazi_only_to_hand_and_colored_mana_paid(cards,coax_stage):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_controller_tutors import answer

    s=gameplay.setup(cards,'Coax from the Blind Eternities','Eldrazi Mimic')
    own=put(s,'Eldrazi Mimic','exile')
    foreign=put(s,'Eldrazi Mimic','exile',pid='p2')
    bear=put(s,'Grizzly Bears','exile')
    spell=put(s,'Coax from the Blind Eternities','hand')
    act(s,'p1',type='clear_mana',player='p1')
    mana(s,U=1,C=2)
    act(s,'p1',type='cast_spell',card_id=spell.id)
    settle(s)
    d=s.state.rules.decision
    assert d.resume['step']=='return_choice'
    ids=[o.id for o in d.options]
    assert own.id in ids and foreign.id not in ids and bear.id not in ids
    assert not s.state.players['p1'].mana
    assert 'Eldrazi' in d.prompt
    answer(s,[own.id])
    assert s.state.cards[own.id].zone=='p1:hand'
    assert s.state.cards[foreign.id].zone=='p2:exile'
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    roundtrip(s)


def test_coax_no_owned_eldrazi_does_not_offer_outside_import(cards,coax_stage):
    s=gameplay.setup(cards,'Coax from the Blind Eternities')
    cast(s,'Coax from the Blind Eternities')
    assert s.state.rules.decision is None
    roundtrip(s)


def test_vivien_production_whole_canonical_coverage(cards):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve('Vivien, Arkbow Ranger'))
    assert result.level=='FULL',result


def test_coax_native_owned_facedown_eldrazi_is_not_eligible(cards,coax_stage):
    s=gameplay.setup(cards,'Coax from the Blind Eternities','Eldrazi Mimic')
    own=put(s,'Eldrazi Mimic','hand')
    act(s,'p1',type='move',card_ids=[own.id],to={'zone':'exile','player':'p1'},face_down=True)
    cast(s,'Coax from the Blind Eternities')
    assert s.state.rules.decision is None
    assert s.state.cards[own.id].zone=='p1:exile'
    roundtrip(s)


def test_coax_native_optional_decline_preserves_exact_exiled_card(cards,coax_stage):
    from tests.test_rules_controller_tutors import answer

    s=gameplay.setup(cards,'Coax from the Blind Eternities','Eldrazi Mimic')
    own=put(s,'Eldrazi Mimic','exile')
    old=s.state.rules.object_id(own.id)
    cast(s,'Coax from the Blind Eternities')
    answer(s,[])
    assert s.state.cards[own.id].zone=='p1:exile'
    assert s.state.rules.object_id(own.id)==old
    roundtrip(s)


def test_coax_genuine_cold_native_choice_returns_exact_eldrazi_without_bootstrap(cards,coax_stage,tmp_path):
    from tests.test_rules_exile_outcomes42_cold import fresh

    s=gameplay.setup(cards,'Coax from the Blind Eternities','Eldrazi Mimic')
    own=put(s,'Eldrazi Mimic','exile')
    cast(s,'Coax from the Blind Eternities')
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'coax.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[own.id]})
    assert s.state.cards[own.id].zone=='p1:hand'
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.fixture()
def raven_stage(monkeypatch):
    import re

    top=re.compile(r'^(?:you may )?put a card you own from outside the game on top of your library$')
    monkeypatch.setitem(outside_game.__dict__,'_TOP',top)
    monkeypatch.setattr(scripts,'EFFECTS',[(top,outside_game._permission),*scripts.EFFECTS])
    source=inspect.getsource(outside_game.plain).replace('(_HAND, _NAMED, _PLAY, _PUT)','(_HAND, _NAMED, _PLAY, _PUT, _TOP)')
    namespace=dict(outside_game.__dict__)
    exec(source,namespace)
    monkeypatch.setattr(outside_game,'plain',namespace['plain'])
    scripts._cached.cache_clear()
    yield
    scripts._cached.cache_clear()


def test_raven_whole_three_native_chapters_token_life_damage_handlook_draw_no_impossible_top_import(cards,raven_stage):
    from tests.test_rules_controller_tutors import answer

    s=gameplay.setup(cards,"The Raven's Warning")
    cast(s,"The Raven's Warning")
    source=next(c for c in s.state.cards.values() if c.name=="The Raven's Warning" and c.zone=='p1:battlefield')
    assert s.state.players['p1'].life==42
    bird=next(c for c in s.state.cards.values() if c.token and 'Bird' in c.token.type_line)
    assert bird.token.colors==['U']
    to_phase(s,'main1',turn=4)
    settle(s)
    before=len(s.state.zones['p1:hand'])
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bird.id,'target':'p2'}])
    to_phase(s,'combat_damage',turn=4)
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    assert d.resume['step']=='look_hand'
    assert d.player=='p1'
    answer(s,[d.options[0].id])
    assert len(s.state.zones['p1:hand'])==before+1
    assert s.state.players['p2'].life==39
    to_phase(s,'main1',turn=7)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_raven_nonflying_combat_does_not_trigger_handlook_or_draw(cards,raven_stage):
    s=gameplay.setup(cards,"The Raven's Warning")
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,"The Raven's Warning")
    to_phase(s,'main1',turn=4)
    settle(s)
    before=len(s.state.zones['p1:hand'])
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p2'}])
    to_phase(s,'main2',turn=4)
    settle(s)
    assert s.state.rules.decision is None
    assert len(s.state.zones['p1:hand'])==before
    assert s.state.players['p2'].life==38
    roundtrip(s)


def test_raven_genuine_cold_handlook_private_rights_then_third_chapter_native_no_import(cards,raven_stage,tmp_path):
    from tests.test_rules_exile_outcomes42_cold import fresh

    s=gameplay.setup(cards,"The Raven's Warning")
    cast(s,"The Raven's Warning")
    source=next(c for c in s.state.cards.values() if c.name=="The Raven's Warning" and c.zone=='p1:battlefield')
    bird=next(c for c in s.state.cards.values() if c.token and 'Bird' in c.token.type_line)
    to_phase(s,'main1',turn=4)
    settle(s)
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bird.id,'target':'p2'}])
    to_phase(s,'combat_damage',turn=4)
    settle(s)
    d=s.state.rules.decision
    assert d.resume['step']=='look_hand'
    from app.game.visibility import can_see
    assert all(can_see(s.state,s.state.cards[cid],'p1') for cid in s.state.zones['p2:hand'])
    assert not any(can_see(s.state,s.state.cards[cid],'p3') for cid in s.state.zones['p2:hand'])
    s=fresh(s,cards,tmp_path/'look.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[d.options[0].id]})
    assert not any(can_see(s.state,s.state.cards[cid],'p1') for cid in s.state.zones['p2:hand'])
    to_phase(s,'main1',turn=7)
    before=len(s.state.zones['p1:hand'])
    top=s.state.zones['p1:library'][0]
    s=raven_fresh(s,cards,tmp_path/'third.json',s.state.rules.priority,{'type':'pass_priority'})
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert len(s.state.zones['p1:hand'])==before
    assert s.state.zones['p1:library'][0]==top
    assert s.state.rules.decision is None
    roundtrip(s)


def test_coax_whole_canonical_coverage(cards,coax_stage):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve('Coax from the Blind Eternities'))
    assert result.level=='FULL',result


def test_raven_whole_canonical_coverage(cards,raven_stage):
    from app.rules import coverage

    result=coverage.of_card_data(cards.resolve("The Raven's Warning"))
    assert result.level=='FULL',result


def raven_fresh(s,cards,path,actor,payload):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code='''
import inspect,json,re,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import outside_game,scripts
top=re.compile(r'^(?:you may )?put a card you own from outside the game on top of your library$')
outside_game._TOP=top
scripts.EFFECTS=[(top,outside_game._permission),*scripts.EFFECTS]
source=inspect.getsource(outside_game.plain).replace('(_HAND, _NAMED, _PLAY, _PUT)','(_HAND, _NAMED, _PLAY, _PUT, _TOP)')
namespace=dict(outside_game.__dict__)
exec(source,namespace)
outside_game.plain=namespace['plain']
scripts._cached.cache_clear()
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
