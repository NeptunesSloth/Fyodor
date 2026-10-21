"""Canonical conditional counters retain stack facts and native choices."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_mana_delayed_effects import answer, cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/conditional_counter_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='nac',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/conditional_counter_cards.json').read_text())]
    s=table(cards,names,names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    to_phase(s,'main1',5)
    return s


NAMES=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/conditional_counter_cards.json').read_text())][:12]


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('name,extra',[
    ('Corrupted Resolve',{}),('Unified Will',{}),('Second Guess',{}),
    ("Ertai's Trickery",{}),('Glorious Gale',{}),("Jace's Defeat",{}),
    ('Vex',{}),('Frightful Delusion',{}),('Icy Reception',{'modes':[0]}),
    ('Anticognition',{}),("Bane's Contingency",{}),
])
def test_actual_counter_resolution(cards,name,extra):
    s=game(cards)
    if name=='Corrupted Resolve':
        act(s,'p1',type='resource',player='p2',key='poison',delta=1)
    if name=='Unified Will':
        put(s,'Scryb Sprites','battlefield')
    if name=='Second Guess':
        cast(s,'Lightning Bolt',{'R':1},['p3'],pid='p3')
        answer(s)
    target_name='Jace Beleren' if name=="Jace's Defeat" else 'Storm Crow'
    target=cast(s,target_name,{'U':2 if target_name=='Jace Beleren' else 1,'C':1},pid='p2')
    if name=="Ertai's Trickery":
        # Negative condition: any spell remains a legal target, but an unkicked spell survives.
        pass
    spell=cast(s,name,{'U':4,'G':1,'C':5},[target.id],**extra)
    roundtrip(s)
    answer(s)
    if name=="Ertai's Trickery":
        assert s.state.cards[target.id].zone=='p2:battlefield'
    else:
        assert s.state.cards[target.id].zone=='p2:graveyard'
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    roundtrip(s)


def test_actual_graveyard_cast_selector_and_draw(cards):
    s=game(cards)
    target=put(s,'Think Twice','graveyard',pid='p2')
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':1,'C':2})
    act(s,'p2',type='cast_spell',card_id=target.id,sources=[],targets=[],flashback_choice=0)
    cast(s,"Laquatus's Disdain",{'U':1,'C':1},[target.id])
    answer(s)
    assert s.state.cards[target.id].zone=='p2:exile'
    roundtrip(s)


@pytest.mark.parametrize('name',['Corrupted Resolve','Unified Will'])
def test_resolution_condition_false_keeps_legal_target(cards,name):
    s=game(cards)
    target=cast(s,'Storm Crow',{'U':1,'C':1},pid='p2')
    cast(s,name,{'U':2,'G':1},[target.id])
    answer(s)
    assert s.state.cards[target.id].zone=='p2:battlefield'
    roundtrip(s)


def test_actual_kicked_spell_countered(cards):
    s=game(cards)
    bear=put(s,'Scryb Sprites','battlefield',pid='p2')
    target=cast(s,'Rite of Replication',{'U':2,'C':7},[bear.id],pid='p2',kicker=True)
    cast(s,"Ertai's Trickery",{'U':1},[target.id])
    answer(s)
    assert s.state.cards[target.id].zone=='p2:graveyard'
    roundtrip(s)


def test_legendary_creature_ring_rider(cards):
    s=game(cards)
    target=cast(s,'Isamaru, Hound of Konda',{'W':1},pid='p2')
    cast(s,'Glorious Gale',{'U':1,'C':1},[target.id])
    answer(s)
    assert s.state.cards[target.id].zone=='p2:graveyard'
    assert s.state.rules.ring_tempted.get('p1')==1
    roundtrip(s)


def test_bane_commander_target_rider(cards):
    from tests.test_rules_mana_delayed_effects import drawn
    s=game(cards)
    commander=next(c for c in s.state.cards.values() if c.owner=='p1' and c.commander_key)
    act(s,'p1',type='move',card_ids=[commander.id],to={'player':'p1','zone':'battlefield'})
    target=cast(s,'Lightning Bolt',{'R':1},[commander.id],pid='p2')
    before=drawn(s)
    cast(s,"Bane's Contingency",{'U':2,'C':1},[target.id])
    answer(s)
    assert drawn(s)==before+1
    assert s.state.cards[target.id].zone=='p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name',["Laquatus's Disdain",'Second Guess'])
def test_origin_and_ordinal_are_real_target_restrictions(cards,name):
    from app.game.errors import ActionError
    s=game(cards)
    target=cast(s,'Storm Crow',{'U':1,'C':1},pid='p2')
    with pytest.raises(ActionError):
        cast(s,name,{'U':2,'C':2},[target.id])
    assert s.state.cards[target.id].zone=='stack'
    roundtrip(s)


@pytest.mark.parametrize('qualifies',[True,False])
def test_poison_is_checked_at_resolution(cards,qualifies):
    s=game(cards)
    act(s,'p1',type='resource',player='p2',key='poison',delta=0 if qualifies else 1)
    target=cast(s,'Storm Crow',{'U':1,'C':1},pid='p2')
    cast(s,'Corrupted Resolve',{'U':1,'C':1},[target.id])
    act(s,'p1',type='resource',player='p2',key='poison',delta=1 if qualifies else -1)
    answer(s)
    assert s.state.cards[target.id].zone==('p2:graveyard' if qualifies else 'p2:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('pay',[True,False])
def test_frightful_discard_happens_after_either_payment_outcome(cards,pay):
    s=game(cards)
    target=cast(s,'Storm Crow',{'U':1,'C':2 if pay else 1},pid='p2')
    put(s,'Forest','hand',pid='p2')
    before=len(s.state.zones['p2:hand'])
    cast(s,'Frightful Delusion',{'U':1,'C':2},[target.id])
    answer(s)
    assert len(s.state.zones['p2:hand'])==before-1
    assert s.state.cards[target.id].zone==('p2:battlefield' if pay else 'p2:graveyard')
    roundtrip(s)


def test_uncounterable_target_still_gives_vex_controller_choice(cards,tmp_path):
    import subprocess
    import sys
    s=game(cards)
    target=cast(s,'Loxodon Smiter',{'G':1,'W':1,'C':1},pid='p2')
    cast(s,'Vex',{'U':1,'C':2},[target.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player=='p2' and {'yes','no'}<={o.id for o in d.options}
    assert s.state.cards[target.id].zone=='stack'
    roundtrip(s)
    saved=tmp_path/'vex-controller-choice.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_mana_delayed_effects import answer,drawn
save,db,target=sys.argv[1:]
r=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=r)
d=s.state.rules.decision
before=drawn(s,'p2')
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['yes']})
answer(s)
assert drawn(s,'p2')==before+1
assert s.state.cards[target].zone=='p2:battlefield'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),target.id],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['no'])
    answer(s)
    assert s.state.cards[target.id].zone=='p2:battlefield'
    roundtrip(s)


def copy_spell(s,original):
    copy_source=cast(s,'Reverberate',{'R':2},[original.id],pid='p3')
    for _ in range(30):
        copies=[s.state.cards[c] for c,e in s.state.rules.stack.items() if e.copy_of and c!=copy_source.id]
        if copies:
            d=s.state.rules.decision
            if d is not None:
                ids={o.id for o in d.options}
                assert 'keep' in ids
                act(s,d.player,type='choose',decision_id=d.id,option_ids=['keep'])
            return copies[-1]
        d=s.state.rules.decision
        if d is not None:
            assert 'keep' in {o.id for o in d.options}
            act(s,d.player,type='choose',decision_id=d.id,option_ids=['keep'])
        else:
            act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('No copied spell')


def test_kicked_copy_keeps_cost_decision_without_being_cast(cards):
    s=game(cards)
    bear=put(s,'Scryb Sprites','battlefield',pid='p2')
    original=cast(s,'Rite of Replication',{'U':2,'C':7},[bear.id],pid='p2',kicker=1)
    copied=copy_spell(s,original)
    counter=cast(s,"Ertai's Trickery",{'U':1},[copied.id])
    for _ in range(30):
        if s.state.cards[counter.id].zone!='stack':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert copied.id not in s.state.zones.get('stack',[])
    assert s.state.cards[original.id].zone=='stack'
    roundtrip(s)


@pytest.mark.parametrize('name',["Laquatus's Disdain",'Second Guess'])
def test_cast_origin_and_ordinal_do_not_transfer_to_spell_copy(cards,name):
    from app.game.errors import ActionError
    s=game(cards)
    if name=='Second Guess':
        cast(s,'Lightning Bolt',{'R':1},['p3'],pid='p3')
        answer(s)
        original=cast(s,'Lightning Bolt',{'R':1},['p1'],pid='p2')
    else:
        original=put(s,'Think Twice','graveyard',pid='p2')
        wait_priority(s,'p2')
        act(s,'p2',type='add_mana',player='p2',mana={'U':1,'C':2})
        act(s,'p2',type='cast_spell',card_id=original.id,sources=[],targets=[],flashback_choice=0)
    copied=copy_spell(s,original)
    with pytest.raises(ActionError):
        cast(s,name,{'U':2,'C':2},[copied.id])
    assert copied.id in s.state.zones.get('stack',[])
    roundtrip(s)


@pytest.mark.parametrize('graveyard_player',['p1','p3'])
def test_anticognition_any_opponent_threshold_excludes_own_graveyard(cards,graveyard_player):
    s=game(cards)
    for name in NAMES[:8]:
        put(s,name,'graveyard',pid=graveyard_player)
    target=cast(s,'Storm Crow',{'U':1,'C':3},pid='p2')
    cast(s,'Anticognition',{'U':1,'C':1},[target.id])
    answer(s)
    assert s.state.cards[target.id].zone==('p2:graveyard' if graveyard_player=='p3' else 'p2:battlefield')
    roundtrip(s)


def test_icy_reception_other_mode_uses_native_creature_target(cards):
    from app.rules.plan import Plan
    s=game(cards)
    creature=put(s,'Scryb Sprites','battlefield',pid='p2')
    cast(s,'Icy Reception',{'U':1,'C':1},[creature.id],modes=[1])
    answer(s)
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[creature.id]).pt[0]==-4
    roundtrip(s)
