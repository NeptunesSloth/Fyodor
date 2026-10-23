"""Native Cyber-Controller public-mill, face-down return, and hidden visibility proofs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

CACHE, MIDNIGHT, DUMMY = 'Cache Grab', 'Midnight Tilling', 'Sparring Dummy'

@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/cyber_controller63_cards.json').read_text())):
        extra = {k:v for k,v in c.items() if k not in ('name','set_code','number')}
        if c.get('faces'):
            extra['card_faces'] = c['faces']
        base[c['name']] = card(c['name'], set_code='oc59', number=str(i), **extra)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def setup(cards):
    names = ['Cybership', 'Ingenious Artillerist', 'Grumgully, the Generous', 'Hardened Scales', 'Doubling Season', 'Aphetto Alchemist', 'Delver of Secrets // Insectile Aberration', "Grafdigger's Cage", 'Authority of the Consuls', 'The Cyber-Controller', CACHE, MIDNIGHT, DUMMY, 'Bruvac the Grandiloquent', 'Squirrel Sovereign', 'Chatterfang, Squirrel General', 'Environmental Sciences', 'Ashes of the Fallen', 'Wheel of Sun and Moon', 'Grizzly Bears', 'Hill Giant', 'Plains', 'Forest', 'Bonesplitter', 'Sol Ring', 'Rest in Peace', 'Lightning Bolt', 'Disperse', 'Darksteel Colossus']
    s = table(cards, names, names, names)
    to_phase(s, 'main1', 1)
    act(s, 'p1', type='add_mana', player='p1', mana={c:30 for c in ['C','W','U','B','R','G']})
    return s

def answer(s, ids):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)

def cast(s, name, **kwargs):
    source = put(s, name, 'hand')
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[], **kwargs)
    settle(s)
    return source

def top(s, names):
    cards = [put(s, name, 'hand') for name in names]
    for c in reversed(cards):
        act(s, 'p1', type='move', card_ids=[c.id], to={'player':'p1','zone':'library'}, position='top')
    return cards


def top_for(s,names,owner):
    cards=[put(s,name,'hand',owner) for name in names]
    for c in reversed(cards):
        act(s,owner,type='move',card_ids=[c.id],to={'player':owner,'zone':'library'},position='top')
    return cards


@pytest.mark.parametrize('rip',[False,True])
@pytest.mark.parametrize('x',[0,1,2])
def test_native_opponents_x_public_creature_returns(cards,rip,x):
    from app.rules.plan import Plan
    s=setup(cards)
    if rip:
        cast(s,'Rest in Peace')
    one=top_for(s,['Grizzly Bears','Forest'],'p2')
    two=top_for(s,['Hill Giant','Lightning Bolt'],'p3')
    source=cast(s,'The Cyber-Controller',x_value=x)
    assert source.zone=='p1:battlefield'
    for c in [one[0],two[0]]:
        if x:
            assert c.zone=='p1:battlefield' and c.controller=='p1' and c.face_down
            ch=Plan(s.state,"p1",cards,None).ch(s.state.cards[c.id])
            assert ch.types==frozenset({'Artifact','Creature'})
            assert ch.subtypes==frozenset({'Cyberman'})
            assert ch.power=='2' and ch.toughness=='2' and ch.pt==(3,3)
        else:
            assert c.zone in ['p2:library','p3:library']
    if x==2:
        assert one[1].zone==('p2:exile' if rip else 'p2:graveyard')
        assert two[1].zone==('p3:exile' if rip else 'p3:graveyard')
    roundtrip(s)

@pytest.mark.parametrize('rip',[False,True])
def test_native_cage_checks_actual_origin(cards,rip):
    s=setup(cards)
    if rip:
        cast(s,'Rest in Peace')
    cast(s,"Grafdigger's Cage")
    one=top_for(s,['Grizzly Bears'],'p2')[0]
    two=top_for(s,['Hill Giant'],'p3')[0]
    cast(s,'The Cyber-Controller',x_value=1)
    assert all(c.zone==('p1:battlefield' if rip else c.owner+':graveyard') for c in [one,two])
    roundtrip(s)


def test_native_opponent_authority_taps_face_down_entries(cards):
    s=setup(cards)
    put(s,'Authority of the Consuls','battlefield','p2')
    one=top_for(s,['Grizzly Bears'],'p2')[0]
    two=top_for(s,['Hill Giant'],'p3')[0]
    before=s.state.players['p2'].life
    cast(s,'The Cyber-Controller',x_value=1)
    assert one.face_down and two.face_down and one.tapped and two.tapped
    assert s.state.players['p2'].life==before+3
    roundtrip(s)

@pytest.mark.parametrize('outcome',['exile','library:shuffle'])
@pytest.mark.parametrize('cold',[False,True])
def test_native_pending_616_before_any_cyber_return(cards,tmp_path,outcome,cold):
    s=setup(cards)
    cast(s,'Rest in Peace')
    one=top_for(s,['Darksteel Colossus'],'p2')[0]
    two=top_for(s,['Hill Giant'],'p3')[0]
    source=cast(s,'The Cyber-Controller',x_value=1)
    d=s.state.rules.decision
    assert d and d.resume['step']=='prepared_mill61'
    assert one.zone=='p2:library' and two.zone=='p3:library'
    if cold:
        import os
        import subprocess
        import sys
        saved=tmp_path/'cyber63.json'
        saved.write_text(s.state.model_dump_json())
        code=r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision;assert d and d.resume['step']=='prepared_mill61'
assert s.state.cards[sys.argv[3]].zone=='p2:library' and s.state.cards[sys.argv[4]].zone=='p3:library'
chosen=next(o.id for o in d.options if o.label.endswith(': '+sys.argv[5]))
act(s,d.player,type='choose',decision_id=d.id,option_ids=[chosen]);settle(s)
one=next(c for c in s.state.cards.values() if c.owner=='p2' and c.name=='Darksteel Colossus')
two=next(c for c in s.state.cards.values() if c.owner=='p3' and c.name=='Hill Giant')
assert sys.argv[4] not in s.state.cards
if sys.argv[5]=='exile': assert sys.argv[3] not in s.state.cards
assert two.zone=='p1:battlefield' and two.face_down
assert one.zone==('p1:battlefield' if sys.argv[5]=='exile' else 'p2:library')
assert one.face_down==(sys.argv[5]=='exile')
assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.face_down])==(2 if sys.argv[5]=='exile' else 1)
ch=Plan(s.state,'p1',repo,None).ch(two);assert ch.power=='2' and ch.toughness=='2' and ch.pt==(3,3)
roundtrip(s)
"""
        result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),one.id,two.id,outcome],capture_output=True,text=True,timeout=60,env=os.environ.copy())
        assert result.returncode==0,result.stdout+result.stderr
        return
    answer(s,[next(o.id for o in d.options if o.label.endswith(': '+outcome))])
    assert source.zone=='p1:battlefield'
    assert two.zone=='p1:battlefield' and two.face_down
    assert one.zone==('p1:battlefield' if outcome=='exile' else 'p2:library')
    assert one.face_down==(outcome=='exile')
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.face_down])==(2 if outcome=='exile' else 1)
    roundtrip(s)


def test_whole_definition_and_exact_negative(cards):
    from app.rules import coverage, cyber_controller63
    assert coverage.of_card_data(cards.resolve('The Cyber-Controller')).level=='FULL'
    assert cyber_controller63.parse("Each opponent mills X cards. Put a creature card milled this way onto the battlefield face down under your control.") is None


def test_native_cyber_characteristics_visibility_and_no_manifest_turnup(cards):
    from app.game.errors import ActionError
    from app.game.visibility import SPECTATOR
    from tests.test_rules_wave18a_down import unseen_by
    s=setup(cards)
    body=top_for(s,['Grizzly Bears'],'p2')[0]
    top_for(s,['Forest'],'p3')
    cast(s,'The Cyber-Controller',x_value=1)
    assert body.face_down and body.face_down_kind=='generic'
    assert not unseen_by(s,body,'p1')
    assert unseen_by(s,body,'p2') and unseen_by(s,body,'p3') and unseen_by(s,body,SPECTATOR)
    with pytest.raises(ActionError):
        act(s,'p1',type='turn_face_up',card_id=body.id,sources=[])
    assert body.face_down
    roundtrip(s)


def test_native_morph_card_can_turn_up_and_ceases_to_be_cyberman(cards):
    from app.rules.plan import Plan
    s=setup(cards)
    body=top_for(s,['Aphetto Alchemist'],'p2')[0]
    top_for(s,['Forest'],'p3')
    cast(s,'The Cyber-Controller',x_value=1)
    act(s,'p1',type='turn_face_up',card_id=body.id,sources=[])
    settle(s)
    current=next(c for c in s.state.cards.values() if c.owner=='p2' and c.name=='Aphetto Alchemist')
    assert not current.face_down
    ch=Plan(s.state,'p1',cards,None).ch(current)
    assert 'Artifact' not in ch.types and 'Cyberman' not in ch.subtypes and ch.pt==(1,2)
    roundtrip(s)


def test_native_double_faced_creature_card_can_enter_face_down(cards):
    from app.rules.plan import Plan
    s=setup(cards)
    body=top_for(s,['Delver of Secrets // Insectile Aberration'],'p2')[0]
    top_for(s,['Forest'],'p3')
    cast(s,'The Cyber-Controller',x_value=1)
    assert body.face_down and body.zone=='p1:battlefield'
    ch=Plan(s.state,'p1',cards,None).ch(s.state.cards[body.id])
    assert ch.name=='' and not ch.colors and ch.pt==(3,3) and ch.subtypes==frozenset({'Cyberman'})
    roundtrip(s)


def test_native_two_cybermen_are_one_artifact_entry_event(cards):
    from app.rules import coverage
    s=setup(cards)
    assert coverage.of_card_data(cards.resolve('Ingenious Artillerist')).level=='FULL'
    art=put(s,'Ingenious Artillerist','battlefield')
    top_for(s,['Grizzly Bears'],'p2')
    top_for(s,['Hill Giant'],'p3')
    source=put(s,'The Cyber-Controller','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],x_value=1)
    seen={}
    for _ in range(100):
        for key,e in s.state.rules.stack.items():
            if e.source_card==art.id and e.event is not None:
                seen[key]=e.event.count
        d=s.state.rules.decision
        if d is not None:
            assert d.kind=='order',(d.kind,d.prompt)
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
        elif s.state.zones.get('stack'):
            act(s,s.state.rules.priority,type='pass_priority')
        else:
            break
    assert sorted(seen.values())==[1,2],seen
    assert s.state.players['p2'].life==37 and s.state.players['p3'].life==37
    roundtrip(s)


def test_native_cyber_counter_entry_choices_finish_before_returns(cards):
    s=setup(cards)
    put(s,'Grumgully, the Generous','battlefield')
    put(s,'Hardened Scales','battlefield')
    put(s,'Doubling Season','battlefield')
    top_for(s,['Grizzly Bears'],'p2')
    top_for(s,['Hill Giant'],'p3')
    source=put(s,'The Cyber-Controller','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],x_value=1)
    entry_choices=0
    for _ in range(120):
        d=s.state.rules.decision
        if d is not None:
            if d.kind=='order':
                ids=[o.id for o in d.options]
            else:
                labels=[o.label for o in d.options]
                assert any('Hardened Scales' in label for label in labels),(d.kind,d.prompt,labels)
                entry_choices+=1
                if source.zone=='p1:battlefield':
                    assert not any(c.face_down and c.zone=='p1:battlefield' for c in s.state.cards.values())
                    assert sum(c.name in ('Grizzly Bears','Hill Giant') and c.zone.endswith(':graveyard') for c in s.state.cards.values())==2
                ids=[next(o.id for o in d.options if 'Hardened Scales' in o.label)]
            act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
        elif s.state.zones.get('stack'):
            act(s,s.state.rules.priority,type='pass_priority')
        else:
            break
    assert entry_choices==3,entry_choices
    bodies=[c for c in s.state.cards.values() if c.face_down and c.zone=='p1:battlefield']
    assert len(bodies)==2 and all(c.counters.get('+1/+1')==4 for c in bodies)
    roundtrip(s)


@pytest.mark.parametrize('mode',['valid','reincarnated','missing'])
def test_true_cold_pending_face_down_entry_orders_are_atomic_and_original(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app
    s=setup(cards)
    put(s,'Grumgully, the Generous','battlefield')
    put(s,'Hardened Scales','battlefield')
    put(s,'Doubling Season','battlefield')
    original=top_for(s,['Grizzly Bears'],'p2')[0]
    top_for(s,['Hill Giant'],'p3')
    source=put(s,'The Cyber-Controller','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],x_value=1)
    for _ in range(80):
        d=s.state.rules.decision
        if d is not None:
            if source.zone=='p1:battlefield' and d.resume.get('step')=='enter_choice':
                break
            assert d.kind=='choose_one'
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if 'Hardened Scales' in o.label)])
        else:
            act(s,s.state.rules.priority,type='pass_priority')
    else:
        raise AssertionError('No pending Cyberman entry choice')
    assert original.zone=='p2:graveyard'
    assert not any(c.face_down and c.zone=='p1:battlefield' for c in s.state.cards.values())
    saved=tmp_path/'cyber-entry.json'
    saved.write_text(s.state.model_dump_json())
    code=r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
mode,original=sys.argv[3:]
d=s.state.rules.decision
assert d and d.resume['step']=='enter_choice'
entries=d.resume['entries']
assert len(entries)==2 and all('face_down_entry64' in e for e in entries)
if mode=='reincarnated':
 act(s,'p2',type='move',card_ids=[original],to={'player':'p2','zone':'hand'})
 act(s,'p2',type='move',card_ids=[original],to={'player':'p2','zone':'graveyard'})
elif mode=='missing':
 entries[0]['face_down_entry64'].pop('object')
if mode!='valid':
 before=s.state.model_dump_json()
 try:
  act(s,d.player,type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if 'Hardened Scales' in o.label)])
 except ActionError:
  pass
 else:
  raise AssertionError('A stale original face-down entry was accepted')
 assert s.state.model_dump_json()==before
 assert not any(c.face_down and c.zone=='p1:battlefield' for c in s.state.cards.values())
else:
 decisions=0
 while s.state.rules.decision:
  d=s.state.rules.decision
  assert d.resume['step']=='enter_choice'
  assert not any(c.face_down and c.zone=='p1:battlefield' for c in s.state.cards.values())
  act(s,d.player,type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if 'Hardened Scales' in o.label)])
  decisions+=1
 assert decisions==2
 settle(s)
 bodies=[c for c in s.state.cards.values() if c.face_down and c.zone=='p1:battlefield']
 assert len(bodies)==2 and all(c.counters.get('+1/+1')==4 for c in bodies)
 assert sum(len(s.state.zones.get(p+':graveyard',[])) for p in ['p2','p3'])==0
 roundtrip(s)
repo.close()
"""
    backend=Path(app.__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),mode,original.id],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr


def test_native_owner_conceding_during_entry_choice_skips_only_their_card(cards):
    s=setup(cards)
    put(s,'Grumgully, the Generous','battlefield')
    put(s,'Hardened Scales','battlefield')
    put(s,'Doubling Season','battlefield')
    original=top_for(s,['Grizzly Bears'],'p2')[0]
    top_for(s,['Hill Giant'],'p3')
    source=put(s,'The Cyber-Controller','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],x_value=1)
    for _ in range(80):
        d=s.state.rules.decision
        if d is not None:
            if source.zone=='p1:battlefield' and d.resume.get('step')=='enter_choice':
                break
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if 'Hardened Scales' in o.label)])
        else:
            act(s,s.state.rules.priority,type='pass_priority')
    act(s,'p2',type='concede')
    for _ in range(60):
        d=s.state.rules.decision
        if d is not None:
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if 'Hardened Scales' in o.label)])
        elif s.state.zones.get('stack'):
            act(s,s.state.rules.priority,type='pass_priority')
        else:
            break
    bodies=[c for c in s.state.cards.values() if c.face_down and c.zone=='p1:battlefield']
    assert original.zone=='p2:graveyard'
    assert len(bodies)==1 and bodies[0].owner=='p3'
    roundtrip(s)


def test_native_cybership_prepares_both_face_down_entry_counter_choices(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    grum=put(s,'Grumgully, the Generous','battlefield')
    put(s,'Hardened Scales','battlefield')
    put(s,'Doubling Season','battlefield')
    pilot=put(s,'Hill Giant','battlefield')
    ship=put(s,'Cybership','battlefield')
    to_phase(s,'main1',7)
    from app.rules.casting import activatable
    ability=next(a for a in activatable(s.state,'p1',cards) if a['card_id']==ship.id)
    act(s,'p1',type='activate_ability',card_id=ship.id,ability=ability['ability'],crew=[grum.id,pilot.id])
    settle(s)
    selected=top_for(s,['Grizzly Bears','Hill Giant'],'p2')
    to_phase(s,'declare_attackers',turn=7)
    attack(s,(ship,'p2'))
    count=0
    for _ in range(60):
        d=s.state.rules.decision
        if d is not None:
            assert d.resume.get('step')=='enter_choice'
            assert not any(c.face_down and c.zone=='p1:battlefield' for c in selected)
            count+=1
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if 'Hardened Scales' in o.label)])
        elif all(c.zone=='p1:battlefield' for c in selected):
            break
        else:
            act(s,s.state.rules.priority,type='pass_priority')
    assert count==2, (s.state.turn, s.state.rules.decision, [(c.zone,c.face_down) for c in selected], s.state.players['p2'].life, ship.zone)
    assert all(c.face_down and c.zone=='p1:battlefield' and c.counters.get('+1/+1')==4 for c in selected)
    roundtrip(s)
