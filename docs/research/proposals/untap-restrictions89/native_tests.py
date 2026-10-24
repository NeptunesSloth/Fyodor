"""The upkeep player chooses exact card categories; native phasing owns all returns."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

REALM = 'Storage Matrix'
DATA = json.loads((Path(__file__).parent/'fixtures/untap_restrictions89_cards.json').read_text())
ALL = [c['name'] for c in DATA]


@pytest.fixture()
def cards(settings):
    base = {c['name']:c for c in fixture_cards()}
    for i,c in enumerate(DATA):
        base[c['name']]=card(c['name'],number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s=table(cards,ALL,ALL,ALL)
    to_phase(s,'main1',1)
    return s


def cast(s,name,pid='p1',targets=(),**kwargs):
    source=put(s,name,'hand',pid)
    mana(s,pid,C=20,W=10,U=10,G=10)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),sources=[],**kwargs)
    settle(s)
    return source


def answer_type(s,chosen):
    d=s.state.rules.decision
    assert d and d.player=='p2' and d.resume['step']=='untap_category89'
    assert {o.id for o in d.options}=={'Artifact','Creature','Land'}
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[chosen])


@pytest.mark.parametrize('name',['Mungha Wurm','Storage Matrix'])
def test_canonical_full_and_actual_cast(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'
    s=game(cards)
    assert cast(s,name).zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('category',['Artifact','Creature','Land'])
def test_native_category_types_and_multitype_intersection(cards,category):
    s=game(cards)
    cast(s,REALM)
    names={'artifact':'Sol Ring','creature':'Grizzly Bears','land':'Forest','multi':'Memnite','other':'Glorious Anthem'}
    objects={k:put(s,n,'battlefield','p2') for k,n in names.items()}
    act(s,'p2',type='tap',card_ids=[o.id for o in objects.values()],tapped=True)
    to_phase(s,'untap',2)
    answer_type(s,category)
    to_phase(s,'main1',2)
    untapped={'Artifact':{'artifact','multi'},'Creature':{'creature','multi'},'Land':{'land'}}[category]
    for k,o in objects.items():
        assert s.state.cards[o.id].tapped==(k not in untapped)
    roundtrip(s)


def test_native_mungha_limit_follows_source_controller_only(cards):
    s=game(cards)
    cast(s,'Mungha Wurm')
    ours=[put(s,n,'battlefield') for n in ('Forest','Island')]
    theirs=[put(s,n,'battlefield','p2') for n in ('Forest','Island')]
    act(s,'p1',type='tap',card_ids=[o.id for o in ours],tapped=True)
    act(s,'p2',type='tap',card_ids=[o.id for o in theirs],tapped=True)
    to_phase(s,'main1',2)
    assert all(not s.state.cards[o.id].tapped for o in theirs)
    to_phase(s,'untap',4)
    d=s.state.rules.decision
    assert d and d.player=='p1' and d.resume['step']=='untap_limit'
    assert {o.id for o in d.options}=={o.id for o in ours}
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[ours[0].id])
    to_phase(s,'main1',4)
    assert not s.state.cards[ours[0].id].tapped and s.state.cards[ours[1].id].tapped
    roundtrip(s)


def test_native_two_matrices_intersect_types(cards):
    s=game(cards)
    cast(s,REALM)
    put(s,REALM,'battlefield','p2')
    objects=[put(s,n,'battlefield','p2') for n in ('Sol Ring','Grizzly Bears','Memnite')]
    act(s,'p2',type='tap',card_ids=[o.id for o in objects],tapped=True)
    to_phase(s,'untap',2)
    answer_type(s,'Artifact')
    answer_type(s,'Creature')
    to_phase(s,'main1',2)
    assert [s.state.cards[o.id].tapped for o in objects]==[True,True,False]
    roundtrip(s)


def test_native_matrix_stun_applies_only_to_permitted_objects_once(cards):
    s=game(cards)
    cast(s,REALM)
    objects=[put(s,n,'battlefield','p2') for n in ('Sol Ring','Grizzly Bears')]
    act(s,'p2',type='tap',card_ids=[o.id for o in objects],tapped=True)
    act(s,'p2',type='counter',card_ids=[o.id for o in objects],kind='stun',delta=2)
    to_phase(s,'untap',2)
    answer_type(s,'Artifact')
    to_phase(s,'main1',2)
    assert [s.state.cards[o.id].counters.get('stun',0) for o in objects]==[1,2]
    assert all(s.state.cards[o.id].tapped for o in objects)
    roundtrip(s)


@pytest.mark.parametrize('stay',[True,False])
@pytest.mark.parametrize('matrix',[True,False])
def test_native_optional_keep_combines_with_matrix_and_numeric_limit(cards,stay,matrix):
    s=game(cards)
    if matrix:
        cast(s,REALM)
    put(s,'Imi Statue','battlefield')
    prison=put(s,'Amber Prison','battlefield','p2')
    ring=put(s,'Sol Ring','battlefield','p2')
    act(s,'p2',type='tap',card_ids=[prison.id,ring.id],tapped=True)
    to_phase(s,'untap',2)
    if matrix:
        answer_type(s,'Artifact')
    d=s.state.rules.decision
    assert d and d.resume['step']=='untap_keep' and {o.id for o in d.options}=={prison.id}
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[prison.id] if stay else [])
    if not stay:
        d=s.state.rules.decision
        assert d and d.resume['step']=='untap_limit' and {o.id for o in d.options}=={prison.id,ring.id}
        act(s,'p2',type='choose',decision_id=d.id,option_ids=[ring.id])
    to_phase(s,'main1',2)
    assert s.state.cards[prison.id].tapped and not s.state.cards[ring.id].tapped
    roundtrip(s)


def test_native_intersecting_numeric_groups_remove_one_stun_counter(cards):
    s=game(cards)
    put(s,'Imi Statue','battlefield')
    put(s,'Smoke','battlefield')
    memnite=put(s,'Memnite','battlefield','p2')
    other=[put(s,n,'battlefield','p2') for n in ('Sol Ring','Grizzly Bears')]
    act(s,'p2',type='tap',card_ids=[memnite.id,*[o.id for o in other]],tapped=True)
    act(s,'p2',type='counter',card_ids=[memnite.id],kind='stun',delta=2)
    to_phase(s,'untap',2)
    for _ in range(2):
        d=s.state.rules.decision
        assert d and d.resume['step']=='untap_limit' and memnite.id in {o.id for o in d.options}
        act(s,'p2',type='choose',decision_id=d.id,option_ids=[memnite.id])
    to_phase(s,'main1',2)
    assert s.state.cards[memnite.id].tapped and s.state.cards[memnite.id].counters.get('stun',0)==1
    assert all(s.state.cards[o.id].tapped for o in other)
    roundtrip(s)


def test_native_tapped_matrix_is_inactive_and_skipped_untap_has_no_choice(cards):
    s=game(cards)
    source=cast(s,REALM)
    land=put(s,'Forest','battlefield','p2')
    act(s,'p1',type='tap',card_ids=[source.id],tapped=True)
    act(s,'p2',type='tap',card_ids=[land.id],tapped=True)
    to_phase(s,'main1',2)
    assert not s.state.cards[land.id].tapped
    act(s,'p1',type='tap',card_ids=[source.id],tapped=False)
    put(s,'Stasis','battlefield')
    act(s,'p2',type='tap',card_ids=[land.id],tapped=True)
    to_phase(s,'main1',3)
    assert s.state.cards[land.id].tapped
    roundtrip(s)


def test_native_category_cannot_override_other_untap_restriction(cards):
    s=game(cards)
    cast(s,REALM)
    monolith=put(s,'Basalt Monolith','battlefield','p2')
    act(s,'p2',type='tap',card_ids=[monolith.id],tapped=True)
    act(s,'p2',type='counter',card_ids=[monolith.id],kind='stun',delta=2)
    to_phase(s,'untap',2)
    answer_type(s,'Artifact')
    to_phase(s,'main1',2)
    assert s.state.cards[monolith.id].tapped and s.state.cards[monolith.id].counters.get('stun',0)==2
    roundtrip(s)


def test_native_only_active_player_chooses_a_public_allowed_type(cards):
    from app.game.errors import ActionError

    s=game(cards)
    cast(s,REALM)
    to_phase(s,'untap',2)
    d=s.state.rules.decision
    assert d and d.resume['step']=='untap_category89'
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='choose',decision_id=d.id,option_ids=['Artifact'])
    assert s.state.model_dump_json()==before
    with pytest.raises(ActionError):
        act(s,'p2',type='choose',decision_id=d.id,option_ids=['Enchantment'])
    assert s.state.model_dump_json()==before
    answer_type(s,'Land')
    to_phase(s,'main1',2)
    roundtrip(s)


@pytest.mark.parametrize('mode',['category','optional'])
def test_true_cold_category_and_optional_untap_continuations(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app

    s=game(cards)
    cast(s,REALM)
    put(s,'Imi Statue','battlefield')
    prison=put(s,'Amber Prison','battlefield','p2')
    ring=put(s,'Sol Ring','battlefield','p2')
    act(s,'p2',type='tap',card_ids=[prison.id,ring.id],tapped=True)
    to_phase(s,'untap',2)
    if mode=='optional':
        answer_type(s,'Artifact')
    saved=tmp_path/'untap89.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import roundtrip
from tests.test_rules_untap_restrictions89 import answer_type
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
prison,ring,mode=sys.argv[3:]
if mode=='category':answer_type(s,'Artifact')
d=s.state.rules.decision
assert d and d.resume['step']=='untap_keep'
act(s,'p2',type='choose',decision_id=d.id,option_ids=[])
d=s.state.rules.decision
assert d and d.resume['step']=='untap_limit' and {o.id for o in d.options}=={prison,ring}
act(s,'p2',type='choose',decision_id=d.id,option_ids=[ring])
to_phase(s,'main1',2)
assert s.state.cards[prison].tapped and not s.state.cards[ring].tapped
roundtrip(s);repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),prison.id,ring.id,mode],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
