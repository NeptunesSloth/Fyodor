"""Conditional attachment and Army animation use native continuous effects."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Blades of Velis Vel', 'Shields of Velis Vel', 'Volatile Claws', 'Ego Erasure', 'Nameless Inversion', 'Amoeboid Changeling']
DATA = json.loads((Path(__file__).parent/'fixtures/temporary_creature_types93_cards.json').read_text())
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
    mana(s,pid,C=20,W=10,U=10,B=10,R=10,G=10)
    wait_priority(s,pid)
    if name=='Blades of Velis Vel':
        kwargs.setdefault('target_counts',[len(targets)])
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),sources=[],**kwargs)
    settle(s)
    return source


def ch(s,source):
    return Plan.view(s.state,'p1',s.cards).ch(s.state.cards[source.id])


@pytest.mark.parametrize('name',NAMES)
def test_native_whole_card_cast_and_changeling(cards,name):
    from app.rules.creature_types import CREATURE_TYPES

    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'
    s=game(cards)
    source=put(s,name,'hand')
    if name!='Volatile Claws':
        assert ch(s,source).subtypes >= CREATURE_TYPES
    spider=put(s,'Giant Spider','battlefield','p2')
    targets=[spider.id] if name in ('Blades of Velis Vel','Nameless Inversion') else ['p2'] if name in ('Shields of Velis Vel','Ego Erasure') else []
    cast(s,name,targets=targets)
    assert s.state.cards[source.id].zone==('p1:battlefield' if name=='Amoeboid Changeling' else 'p1:graveyard')
    if name!='Volatile Claws':
        assert ch(s,source).subtypes >= CREATURE_TYPES
    roundtrip(s)


@pytest.mark.parametrize('name',['Blades of Velis Vel','Shields of Velis Vel','Volatile Claws'])
def test_native_gain_types_actual_lord_and_expiry(cards,name):
    from app.rules.creature_types import CREATURE_TYPES

    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    lord=cast(s,'Lord of Atlantis')
    targets=[bear.id] if name=='Blades of Velis Vel' else ['p1'] if name=='Shields of Velis Vel' else []
    cast(s,name,targets=targets)
    assert ch(s,bear).subtypes >= CREATURE_TYPES and 'islandwalk' in ch(s,bear).keywords
    assert ch(s,bear).pt==((3,4) if name=='Shields of Velis Vel' else (5,3))
    late=put(s,'Giant Spider','battlefield')
    assert 'Merfolk' not in ch(s,late).subtypes and ch(s,late).pt==(2,4)
    act(s,'p1',type='set_controller',card_ids=[bear.id],player='p2')
    assert ch(s,bear).subtypes >= CREATURE_TYPES
    to_phase(s,'main1',2)
    assert ch(s,bear).subtypes==frozenset({'Bear'}) and ch(s,bear).pt==(2,2)
    assert s.state.cards[lord.id].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name',['Ego Erasure','Nameless Inversion'])
def test_native_remove_creature_subtypes_preserves_equipment_and_forest(cards,name):
    s=game(cards)
    host=put(s,'Rabbit Battery','battlefield')
    forest=put(s,'Dryad Arbor','battlefield')
    for obj in [host,forest]:
        act(s,'p1',type='counter',card_ids=[obj.id],kind='+1/+1',delta=3)
    targets=['p1'] if name=='Ego Erasure' else [host.id]
    cast(s,name,targets=targets)
    assert ch(s,host).subtypes==frozenset({'Equipment'}) and 'Artifact' in ch(s,host).types and 'haste' in ch(s,host).keywords
    if name=='Ego Erasure':
        assert ch(s,forest).subtypes==frozenset({'Forest'}) and 'Land' in ch(s,forest).types
    to_phase(s,'main1',2)
    assert 'Rabbit' in ch(s,host).subtypes and 'Dryad' in ch(s,forest).subtypes
    roundtrip(s)


def test_native_two_targets_zero_targets_and_illegal_target_atomic(cards):
    from app.game.errors import ActionError
    from app.rules.creature_types import CREATURE_TYPES

    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    spider=put(s,'Giant Spider','battlefield','p2')
    cast(s,'Blades of Velis Vel',targets=[bear.id,spider.id])
    assert ch(s,bear).subtypes >= CREATURE_TYPES and ch(s,spider).subtypes >= CREATURE_TYPES
    roundtrip(s)
    s=game(cards)
    cast(s,'Blades of Velis Vel',targets=[])
    source=put(s,'Nameless Inversion','hand')
    mana(s,'p1',B=2,C=3)
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'],sources=[])
    assert s.state.model_dump_json()==before


def test_native_removal_overrides_changeling_then_later_grant_restores(cards):
    from app.rules.creature_types import CREATURE_TYPES

    s=game(cards)
    source=put(s,'Universal Automaton','battlefield')
    helper=put(s,'Amoeboid Changeling','battlefield')
    assert ch(s,source).subtypes>=CREATURE_TYPES
    cast(s,'Ego Erasure',targets=['p1'])
    assert not ch(s,source).subtypes and 'changeling' in ch(s,source).keywords
    # A second physical Ego copy belongs to p2: cast it on its own turn below.
    to_phase(s,'main1',5)
    cast(s,'Ego Erasure','p2',targets=['p1'])
    assert not ch(s,source).subtypes
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=helper.id,ability=1,targets=[source.id],sources=[])
    settle(s)
    assert ch(s,source).subtypes>=CREATURE_TYPES
    roundtrip(s)


def test_native_loss_removes_lord_bonus_and_keeps_other_abilities(cards):
    s=game(cards)
    subject=put(s,'Universal Automaton','battlefield')
    cast(s,'Lord of Atlantis')
    assert ch(s,subject).pt==(2,2) and 'islandwalk' in ch(s,subject).keywords
    cast(s,'Ego Erasure',targets=['p1'])
    assert ch(s,subject).pt==(-1,1) and 'islandwalk' not in ch(s,subject).keywords
    assert 'changeling' in ch(s,subject).keywords and s.state.cards[subject.id].zone=='p1:battlefield'
    to_phase(s,'main1',2)
    assert ch(s,subject).pt==(2,2) and 'islandwalk' in ch(s,subject).keywords
    roundtrip(s)


def test_native_blink_same_physical_card_does_not_retain_types_or_pump(cards):
    s=game(cards)
    subject=put(s,'Grizzly Bears','battlefield')
    cast(s,'Blades of Velis Vel',targets=[subject.id])
    assert 'Merfolk' in ch(s,subject).subtypes and ch(s,subject).pt==(4,2)
    cast(s,'Ephemerate',targets=[subject.id])
    assert s.state.cards[subject.id].zone=='p1:battlefield'
    assert ch(s,subject).subtypes==frozenset({'Bear'}) and ch(s,subject).pt==(2,2)
    roundtrip(s)


def test_native_partial_illegal_targets_only_affect_remaining_target(cards):
    from app.rules.creature_types import CREATURE_TYPES

    s=game(cards)
    first=put(s,'Grizzly Bears','battlefield')
    second=put(s,'Giant Spider','battlefield')
    spell=put(s,'Blades of Velis Vel','hand')
    mana(s,'p1',C=4,R=2,U=2)
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[first.id,second.id],target_counts=[2],sources=[])
    cast(s,'Unsummon',targets=[first.id])
    assert s.state.cards[first.id].zone=='p1:hand' and ch(s,first).subtypes==frozenset({'Bear'})
    assert ch(s,second).subtypes>=CREATURE_TYPES and ch(s,second).pt==(4,4)
    roundtrip(s)


@pytest.mark.parametrize('mode',['gain','loss','stack'])
def test_true_cold_temporary_type_layers_and_stack(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app

    s=game(cards)
    subject=put(s,'Rabbit Battery','battlefield')
    act(s,'p1',type='counter',card_ids=[subject.id],kind='+1/+1',delta=3)
    meta={'mode':mode,'subject':subject.id}
    if mode=='loss':
        cast(s,'Ego Erasure',targets=['p1'])
    elif mode=='gain':
        cast(s,'Blades of Velis Vel',targets=[subject.id])
    else:
        spell=put(s,'Nameless Inversion','hand')
        mana(s,'p1',B=3,C=4)
        wait_priority(s,'p1')
        act(s,'p1',type='cast_spell',card_id=spell.id,targets=[subject.id],sources=[])
    saved=tmp_path/'types93.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from app.rules.creature_types import CREATURE_TYPES
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
m=json.loads(sys.argv[3])
def ch():return Plan.view(s.state,'p1',repo).ch(s.state.cards[m['subject']])
if m['mode']=='stack':
 assert s.state.zones['stack'] and ch().subtypes==frozenset({'Rabbit','Equipment'})
 settle(s)
if m['mode']=='gain':
 assert ch().subtypes>=CREATURE_TYPES and 'Equipment' in ch().subtypes and ch().pt==(6,4)
elif m['mode']=='loss':
 assert ch().subtypes==frozenset({'Equipment'}) and ch().pt==(2,4)
else:
 assert ch().subtypes==frozenset({'Equipment'}) and ch().pt==(7,1)
assert 'haste' in ch().keywords and 'Artifact' in ch().types
to_phase(s,'main1',2)
assert ch().subtypes==frozenset({'Rabbit','Equipment'}) and ch().pt==(4,4)
roundtrip(s);repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),json.dumps(meta)],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr


def test_native_amoeboid_both_tap_abilities_and_actual_untap_between(cards):
    from app.rules.creature_types import CREATURE_TYPES

    s=game(cards)
    helper=cast(s,'Amoeboid Changeling')
    subject=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'main1',4)
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=helper.id,ability=1,targets=[subject.id],sources=[])
    settle(s)
    assert s.state.cards[helper.id].tapped and ch(s,subject).subtypes>=CREATURE_TYPES
    cast(s,'Cerulean Wisps',targets=[helper.id])
    assert not s.state.cards[helper.id].tapped
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=helper.id,ability=2,targets=[subject.id],sources=[])
    settle(s)
    assert s.state.cards[helper.id].tapped and not ch(s,subject).subtypes
    assert ch(s,helper).subtypes>=CREATURE_TYPES
    to_phase(s,'main1',5)
    assert ch(s,subject).subtypes==frozenset({'Bear'})
    roundtrip(s)
