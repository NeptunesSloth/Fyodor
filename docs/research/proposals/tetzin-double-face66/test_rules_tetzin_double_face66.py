"""Native public-mill selections and exact hand outcomes."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/tetzin_double_face66_cards.json').read_text())):
        extra = {k:v for k,v in c.items() if k not in ('name','set_code','number')}
        if c.get('faces'):
            extra['card_faces'] = c['faces']
        if c.get('related_cards') or c.get('related_tokens'):
            extra['all_parts'] = [*c.get('related_cards', []), *[{**part, 'component': 'token'} for part in c.get('related_tokens', [])]]
        base[c['name']] = card(c['name'], set_code='oc59', number=str(i), **extra)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def setup(cards):
    names = list(dict.fromkeys([c['name'] for c in json.loads((Path(__file__).parent/'fixtures/tetzin_double_face66_cards.json').read_text()) if c['name'] != 'Urza, Planeswalker'] + ['Grizzly Bears','Hill Giant','Forest','Lightning Bolt']))
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


TETZIN='Tetzin, Gnome Champion // The Golden-Gear Colossus'
COMPASS='Thaumatic Compass // Spires of Orazca'
CAULDRON='Pestilent Cauldron // Restorative Burst'
MATERIALS=['Bonesplitter','Sol Ring','Sparring Dummy','Arcane Signet',"Wayfarer's Bauble",'Mind Stone']


def resolve66(s,target=None):
    for _ in range(100):
        d=s.state.rules.decision
        if d:
            assert d.resume.get('step') in ('public_pick65','trigger_target','trigger_group','trigger_modes','order_triggers')
            ids=[o.id for o in d.options] if d.resume.get('step')=='order_triggers' else [next(o.id for o in d.options if o.label.startswith('Draw two cards'))] if d.resume.get('step')=='trigger_modes' else [target.id] if d.resume.get('step') in ('trigger_target','trigger_group') and target else []
            act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
        elif s.state.zones.get('stack'):
            act(s,s.state.rules.priority,type='pass_priority')
        else:
            return
    raise AssertionError('Tetzin did not finish')


def front66(cards):
    s=setup(cards)
    top(s,['Forest','Grizzly Bears','Lightning Bolt'])
    source=put(s,TETZIN,'hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    resolve66(s)
    return s,source


def craft66(s,source,target=None):
    materials=[put(s,n,'battlefield' if i%2 else 'graveyard') for i,n in enumerate(MATERIALS)]
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,cost_choices=[{'component':2,'cards':[c.id for c in materials]}],sources=[])
    resolve66(s,target)
    assert all(c.zone=='p1:exile' for c in materials)
    assert source.zone=='p1:battlefield' and source.face==1
    return materials


def test_whole66(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve(TETZIN)).level=='FULL'


def test_native_front_self_mills_three_and_optionally_returns_only_artifact(cards):
    s=setup(cards)
    selected=top(s,['Bonesplitter','Forest','Lightning Bolt','Hill Giant'])
    source=put(s,TETZIN,'hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='public_pick65' and {o.id for o in d.options}=={selected[0].id} and d.max_choices==1
    answer(s,[selected[0].id])
    assert source.face==0 and selected[0].zone=='p1:hand' and selected[3].zone=='p1:library'
    roundtrip(s)


def test_native_incubate_creates_double_faced_artifact_and_triggers_front(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve('Converter Beast')).level=='FULL'
    s,source=front66(cards)
    selected=top(s,['Bonesplitter','Forest','Lightning Bolt','Hill Giant'])
    beast=put(s,'Converter Beast','hand')
    act(s,'p1',type='cast_spell',card_id=beast.id,sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='public_pick65' and {o.id for o in d.options}=={selected[0].id}
    answer(s,[])
    assert selected[3].zone=='p1:library' and all(c.zone=='p1:graveyard' for c in selected[:3])
    token=next(c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Incubator')
    assert token.token is not None and token.token.back is not None
    roundtrip(s)


def test_native_craft_six_actual_artifacts_returns_back_and_creates_two_gnomes(cards):
    s,source=front66(cards)
    craft66(s,source)
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Gnome'])==2
    roundtrip(s)


@pytest.mark.parametrize('owner',['p1','p2'])
def test_another_physical_double_faced_artifact_is_controller_qualified(cards,owner):
    s,source=front66(cards)
    if owner=='p2':
        to_phase(s,'main1',2)
        act(s,'p2',type='add_mana',player='p2',mana={'C':10})
    selected=top(s,['Bonesplitter','Forest','Lightning Bolt','Hill Giant'])
    compass=put(s,COMPASS,'hand',owner)
    act(s,owner,type='cast_spell',card_id=compass.id,sources=[])
    settle(s)
    if owner=='p1':
        d=s.state.rules.decision
        assert d and d.resume.get('step')=='public_pick65' and {o.id for o in d.options}=={selected[0].id}
        answer(s,[])
        assert all(c.zone=='p1:graveyard' for c in selected[:3])
    else:
        assert s.state.rules.decision is None and all(c.zone=='p1:library' for c in selected)
    roundtrip(s)


def test_native_single_faced_servo_tokens_do_not_trigger_front(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve('Servo Exhibition')).level=='FULL'
    s,source=front66(cards)
    selected=top(s,['Bonesplitter','Forest','Lightning Bolt'])
    spell=put(s,'Servo Exhibition','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    resolve66(s)
    assert all(c.zone=='p1:library' for c in selected)
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Servo'])==2
    roundtrip(s)


def test_native_single_faced_metamorph_copy_of_double_faced_artifact_does_not_trigger(cards):
    from app.rules import coverage
    from app.rules.plan import Plan
    assert coverage.of_card_data(cards.resolve('Phyrexian Metamorph')).level=='FULL'
    s,source=front66(cards)
    compass=put(s,COMPASS,'hand')
    act(s,'p1',type='cast_spell',card_id=compass.id,sources=[])
    resolve66(s)
    selected=top(s,['Bonesplitter','Forest','Lightning Bolt'])
    mimic=put(s,'Phyrexian Metamorph','hand')
    act(s,'p1',type='cast_spell',card_id=mimic.id,sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and compass.id in {o.id for o in d.options}
    answer(s,[compass.id])
    assert Plan(s.state,'p1',cards,None).ch(mimic).name=='Thaumatic Compass'
    assert all(c.zone=='p1:library' for c in selected)
    roundtrip(s)


def test_native_cyberman_face_down_double_faced_artifact_triggers_front(cards):
    s,source=front66(cards)
    selected=top(s,['Bonesplitter','Forest','Lightning Bolt','Hill Giant'])
    body=top_for(s,['Delver of Secrets // Insectile Aberration'],'p2')[0]
    top_for(s,['Forest'],'p3')
    cyber=put(s,'The Cyber-Controller','hand')
    act(s,'p1',type='cast_spell',card_id=cyber.id,sources=[],x_value=1)
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='public_pick65' and {o.id for o in d.options}=={selected[0].id}
    assert body.face_down and body.zone=='p1:battlefield'
    answer(s,[])
    assert all(c.zone=='p1:graveyard' for c in selected[:3]) and selected[3].zone=='p1:library'
    roundtrip(s)


@pytest.mark.parametrize('kind',['incubator','sorcery_back'])
def test_native_craft_back_target_transforms_incubator_and_handles_nonpermanent_other_face(cards,kind):
    from app.rules.plan import Plan
    s,source=front66(cards)
    if kind=='incubator':
        beast=put(s,'Converter Beast','hand')
        act(s,'p1',type='cast_spell',card_id=beast.id,sources=[])
        resolve66(s)
        target=next(c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Incubator')
    else:
        target=put(s,CAULDRON,'hand')
        act(s,'p1',type='cast_spell',card_id=target.id,sources=[])
        resolve66(s)
    craft66(s,source,target)
    assert target.face==(1 if kind=='incubator' else 0)
    if kind=='incubator':
        assert 'Creature' in Plan(s.state,'p1',cards,None).ch(target).types
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Gnome'])==2
    roundtrip(s)


def test_native_back_attack_creates_two_more_gnomes_and_has_vigilance(cards):
    from tests.test_rules_wave30p_combat import attack
    s,source=front66(cards)
    craft66(s,source)
    to_phase(s,'declare_attackers',turn=7)
    attack(s,(source,'p2'))
    resolve66(s)
    assert not source.tapped
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Gnome'])==4
    roundtrip(s)


def test_native_reversible_art_treatment_is_not_a_double_faced_permanent(cards):
    name='Reckoner Bankbuster // Reckoner Bankbuster'
    s,source=front66(cards)
    selected=top(s,['Bonesplitter','Forest','Lightning Bolt'])
    bank=put(s,name,'hand')
    act(s,'p1',type='cast_spell',card_id=bank.id,sources=[])
    resolve66(s)
    assert bank.zone=='p1:battlefield' and bank.counters.get('charge')==3
    assert all(c.zone=='p1:library' for c in selected)
    roundtrip(s)


def test_native_back_target_fizzling_skips_gnome_creation(cards):
    s,source=front66(cards)
    compass=put(s,COMPASS,'hand')
    act(s,'p1',type='cast_spell',card_id=compass.id,sources=[])
    resolve66(s)
    materials=[put(s,n,'battlefield' if i%2 else 'graveyard') for i,n in enumerate(MATERIALS)]
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,cost_choices=[{'component':2,'cards':[c.id for c in materials]}],sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='trigger_group' and compass.id in {o.id for o in d.options}
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[compass.id])
    spell=put(s,'Disperse','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[],targets=[compass.id])
    resolve66(s)
    assert compass.zone=='p1:hand' and source.face==1
    assert not [c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Gnome']
    roundtrip(s)


def test_native_back_face_down_double_faced_artifact_target_cannot_transform_but_creates_gnomes(cards):
    s,source=front66(cards)
    body=top_for(s,['Delver of Secrets // Insectile Aberration'],'p2')[0]
    top_for(s,['Forest'],'p3')
    cyber=put(s,'The Cyber-Controller','hand')
    act(s,'p1',type='cast_spell',card_id=cyber.id,sources=[],x_value=1)
    resolve66(s)
    assert body.face_down and body.zone=='p1:battlefield'
    craft66(s,source,body)
    assert body.face_down and body.face==0
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Gnome'])==2
    roundtrip(s)


@pytest.mark.parametrize('kind',['meld','modal_permanent'])
def test_native_back_target_meld_is_unchanged_but_modal_permanent_transforms_under_pinned_rules(cards,kind):
    from app.rules.plan import Plan
    s,source=front66(cards)
    name='The Mightstone and Weakstone' if kind=='meld' else 'Birgi, God of Storytelling // Harnfel, Horn of Bounty'
    target=put(s,name,'hand')
    act(s,'p1',type='cast_spell',card_id=target.id,sources=[],**({'face':1} if kind=='modal_permanent' else {}))
    resolve66(s)
    assert target.face==(0 if kind=='meld' else 1)
    craft66(s,source,target)
    assert target.face==0
    if kind=='modal_permanent':
        assert Plan(s.state,'p1',cards,None).ch(target).name=='Birgi, God of Storytelling'
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Gnome'])==2
    roundtrip(s)


@pytest.mark.parametrize('target_it',[False,True])
def test_true_cold_crafted_back_optional_target_double_faced_incubator(cards,tmp_path,target_it):
    import os
    import subprocess
    import sys

    import app
    s,source=front66(cards)
    beast=put(s,'Converter Beast','hand')
    act(s,'p1',type='cast_spell',card_id=beast.id,sources=[])
    resolve66(s)
    target=next(c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Incubator')
    materials=[put(s,n,'battlefield' if i%2 else 'graveyard') for i,n in enumerate(MATERIALS)]
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,cost_choices=[{'component':2,'cards':[c.id for c in materials]}],sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='trigger_group' and target.id in {o.id for o in d.options}
    assert source.id not in {o.id for o in d.options}
    assert source.face==1 and all(c.zone=='p1:exile' for c in materials)
    saved=tmp_path/'tetzinback66.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision;assert d and d.resume['step']=='trigger_group'
target=s.state.cards[sys.argv[3]]
assert target.token and target.token.back and not target.face
act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id] if sys.argv[4]=='yes' else []);settle(s)
assert target.face==(1 if sys.argv[4]=='yes' else 0)
assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Gnome'])==2
assert s.state.rules.decision is None
roundtrip(s)
'''
    backend=Path(app.__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),target.id,'yes' if target_it else 'no'],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr


@pytest.mark.parametrize('outcome',['exile','library:shuffle'])
def test_true_cold_front_mill_replacements_finish_before_public_artifact_selection(cards,tmp_path,outcome):
    import os
    import subprocess
    import sys

    import app
    s=setup(cards)
    cast(s,'Rest in Peace')
    selected=top(s,['Darksteel Colossus','Bonesplitter','Forest'])
    source=put(s,TETZIN,'hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='prepared_mill61'
    assert all(c.zone=='p1:library' for c in selected)
    saved=tmp_path/'tetzinfront66.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision;assert d and d.resume['step']=='prepared_mill61'
choice=next(o.id for o in d.options if o.label.endswith(': '+sys.argv[4]))
act(s,d.player,type='choose',decision_id=d.id,option_ids=[choice]);settle(s)
d=s.state.rules.decision;assert d and d.resume['step']=='public_pick65' and d.max_choices==1
assert {o.label for o in d.options}==({'Bonesplitter','Darksteel Colossus'} if sys.argv[4]=='exile' else {'Bonesplitter'})
act(s,d.player,type='choose',decision_id=d.id,option_ids=[sys.argv[3]]);settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:hand'
colossus=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Darksteel Colossus')
assert colossus.zone==('p1:exile' if sys.argv[4]=='exile' else 'p1:library')
assert s.state.rules.decision is None
roundtrip(s)
'''
    backend=Path(app.__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),selected[1].id,outcome],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr


def test_native_melded_artifact_is_distinct_from_mutated_merge_and_is_legal_target(cards):
    s,source=front66(cards)
    lattice=put(s,'Mycosynth Lattice','hand')
    act(s,'p1',type='cast_spell',card_id=lattice.id,sources=[])
    resolve66(s)
    urza=put(s,'Urza, Lord Protector','hand')
    act(s,'p1',type='cast_spell',card_id=urza.id,sources=[])
    resolve66(s)
    stone=put(s,'The Mightstone and Weakstone','hand')
    act(s,'p1',type='cast_spell',card_id=stone.id,sources=[])
    resolve66(s)
    selected=top(s,['Bonesplitter','Forest','Lightning Bolt'])
    library_before=len(s.state.zones['p1:library'])
    act(s,'p1',type='activate_ability',card_id=urza.id,ability=1,sources=[])
    resolve66(s)
    melded=next((c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.melded),None)
    assert melded, [(c.name,c.zone,c.face) for c in s.state.cards.values() if 'Urza' in (c.name or '') or 'Mightstone' in (c.name or '')]
    assert len(melded.merged)==2 and all(c.zone=='p1:graveyard' for c in selected)
    assert len(s.state.zones['p1:library'])==library_before-3
    craft66(s,source,melded)
    assert melded.melded and len(melded.merged)==2
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Gnome'])==2
    roundtrip(s)


@pytest.mark.parametrize('command',[False,True])
def test_native_front_artifact_pick_prepares_commander_hand_replacement(cards,command):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable
    names=[TETZIN,'Forest','Lightning Bolt']
    decks=[deck(cards,'Hope of Ghirapur',[(1,n) for n in names]+[(20,'Forest')]),
           deck(cards,'Krenko, Mob Boss',[(20,'Forest')]),deck(cards,'Krenko, Mob Boss',[(20,'Forest')])]
    s=GameSession(enable(new_game([PlayerSetup(str(i),cards=d) for i,d in enumerate(decks)],shuffle=False)),cards=cards)
    act(s,'p1',type='pass_priority')
    for pid in s.state.players:
        act(s,pid,type='set_prefs',response='on')
    to_phase(s,'main1',1)
    act(s,'p1',type='add_mana',player='p1',mana={c:30 for c in ['C','W','U','B','R','G']})
    original=next(c for c in s.state.cards.values() if c.owner=='p1' and c.commander_key)
    top(s,['Forest','Lightning Bolt'])
    act(s,'p1',type='move',card_ids=[original.id],to={'player':'p1','zone':'library'},position='top')
    source=put(s,TETZIN,'hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='public_pick65' and {o.id for o in d.options}=={original.id}
    answer(s,[original.id])
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='public_command65' and original.zone=='p1:graveyard'
    answer(s,['yes' if command else 'no'])
    assert original.zone==('p1:command' if command else 'p1:hand')
    roundtrip(s)


def test_native_craft_accepts_artifact_token_material_that_ceases_to_exist(cards):
    s,source=front66(cards)
    spell=put(s,'Servo Exhibition','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    resolve66(s)
    token=next(c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Servo')
    materials=[put(s,n,'battlefield' if i%2 else 'graveyard') for i,n in enumerate(MATERIALS[:5])]
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,cost_choices=[{'component':2,'cards':[token.id,*[c.id for c in materials]]}],sources=[])
    resolve66(s)
    assert token.id not in s.state.cards and all(c.zone=='p1:exile' for c in materials)
    assert source.face==1 and source.zone=='p1:battlefield'
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Gnome'])==2
    roundtrip(s)


def test_native_single_faced_copy_with_craft_stays_exiled_after_paying_cost(cards):
    s,source=front66(cards)
    selected=top(s,['Forest','Grizzly Bears','Lightning Bolt'])
    mimic=put(s,'Phyrexian Metamorph','hand')
    library_before=len(s.state.zones['p1:library'])
    act(s,'p1',type='cast_spell',card_id=mimic.id,sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and source.id in {o.id for o in d.options}
    answer(s,[source.id])
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='legend_rule'
    answer(s,[mimic.id])
    resolve66(s)
    assert source.zone=='p1:graveyard' and mimic.zone=='p1:battlefield'
    assert all(c.zone=='p1:graveyard' for c in selected) and len(s.state.zones['p1:library'])==library_before-3
    materials=[put(s,n,'battlefield' if i%2 else 'graveyard') for i,n in enumerate(MATERIALS)]
    act(s,'p1',type='activate_ability',card_id=mimic.id,ability=1,cost_choices=[{'component':2,'cards':[c.id for c in materials]}],sources=[])
    resolve66(s)
    assert mimic.zone=='p1:exile' and all(c.zone=='p1:exile' for c in materials)
    assert not [c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Gnome']
    roundtrip(s)
