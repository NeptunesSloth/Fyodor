"""Copy-entry conditions distinguish copied abilities from additional entry counters."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/conditional_copy_entry_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='cce', number=str(i), **{k:v for k,v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=['Flesh Duplicate','Undercover Operative','Grizzly Bears','Chronozoa','Soultether Golem','Clone','Adaptive Automaton','Doubling Season','Shock','Turn to Frog','Maelstrom Djinn','Solemnity']
    return table(cards,names,[*names,'Vorinclex, Monstrous Raider'],['Grizzly Bears'])


def cast(s,name):
    c=put(s,name,'hand')
    pay(s,'p1',name)
    act(s,'p1',type='cast_spell',card_id=c.id,sources=[])
    settle(s)
    return c


def choose(s, cid):
    d=s.state.rules.decision
    assert d and cid in {o.id for o in d.options}, (d.kind if d else None,d.prompt if d else None)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[cid])
    settle(s)


def ch(s,c):
    return Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c.id])


@pytest.mark.parametrize('name',['Flesh Duplicate','Undercover Operative'])
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_flesh_copy_of_nonvanishing_creature_gains_copiable_vanishing_three(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    duplicate=cast(s,'Flesh Duplicate')
    roundtrip(s)
    choose(s,bear.id)
    assert ch(s,duplicate).name=='Grizzly Bears'
    assert 'vanishing' in ch(s,duplicate).keywords
    assert s.state.cards[duplicate.id].counters=={'time':3}
    clone=cast(s,'Clone')
    choose(s,duplicate.id)
    assert 'vanishing' in ch(s,clone).keywords
    assert s.state.cards[clone.id].counters=={'time':3}
    roundtrip(s)


@pytest.mark.parametrize('source_name,number',[('Chronozoa',3),('Soultether Golem',1)])
def test_existing_vanishing_is_not_added_again_and_counter_status_is_not_copied(cards,source_name,number):
    s=game(cards)
    source=put(s,source_name,'battlefield')
    act(s,'p1',type='set_counter',card_id=source.id,kind='time',value=8)
    duplicate=cast(s,'Flesh Duplicate')
    choose(s,source.id)
    assert s.state.cards[duplicate.id].counters=={'time':number}
    assert len([a for a in ch(s,duplicate).abilities if 'vanishing' in a.keywords])==1
    roundtrip(s)


@pytest.mark.parametrize('owner,controller',[('p1','p1'),('p1','p2'),('p2','p1'),('p2','p2')])
def test_undercover_control_condition_is_not_ownership(cards,owner,controller):
    s=game(cards)
    source=put(s,'Grizzly Bears','battlefield',pid=owner)
    if controller != owner:
        act(s,'p1',type='set_controller',card_ids=[source.id],player=controller)
    operative=cast(s,'Undercover Operative')
    choose(s,source.id)
    assert s.state.cards[operative.id].counters==({'shield':1} if controller=='p1' else {})
    assert ch(s,operative).pt==(2,2)
    roundtrip(s)


def test_shield_counter_is_not_copied_by_later_clone(cards):
    s=game(cards)
    source=put(s,'Grizzly Bears','battlefield')
    operative=cast(s,'Undercover Operative')
    choose(s,source.id)
    clone=cast(s,'Clone')
    choose(s,operative.id)
    assert not s.state.cards[clone.id].counters
    assert 'shield' not in ch(s,clone).keywords
    roundtrip(s)


@pytest.mark.parametrize('name',['Flesh Duplicate','Undercover Operative'])
def test_declining_copy_does_not_apply_exception(cards,name):
    s=game(cards)
    put(s,'Grizzly Bears','battlefield')
    source=cast(s,name)
    choose(s,'none')
    assert s.state.cards[source.id].zone=='p1:graveyard'  # It remains its printed0/0.
    roundtrip(s)


@pytest.mark.parametrize('name,kind,amount',[('Flesh Duplicate','time',6),('Undercover Operative','shield',2)])
def test_entry_counters_use_native_doubling_before_entry(cards,name,kind,amount):
    s=game(cards)
    put(s,'Doubling Season','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    source=cast(s,name)
    choose(s,bear.id)
    assert s.state.cards[source.id].counters=={kind:amount}
    events=[e for e in s.state.rules.events if e.kind=='counters' and e.card==source.id and e.counter==kind and not e.manual]
    assert len(events)==1 and events[0].amount==amount
    roundtrip(s)


def answer_entry_orders(s):
    for _ in range(20):
        d=s.state.rules.decision
        if d is None:
            return
        assert 'modify' in d.prompt or 'replacement' in d.prompt or 'applies first' in d.prompt, (d.kind,d.prompt)
        roundtrip(s)
        option=next((o for o in d.options if 'Doubling Season' in o.label),d.options[0])
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[option.id])
        settle(s)
    raise AssertionError('entry replacement order did not finish')


@pytest.mark.parametrize('initial_controller',['p1','p2'])
def test_source_control_condition_is_frozen_before_counter_entry_order(cards,initial_controller):
    s=game(cards)
    put(s,'Doubling Season','battlefield')
    put(s,'Vorinclex, Monstrous Raider','battlefield',pid='p2')
    source=put(s,'Chronozoa','battlefield',pid=initial_controller)
    operative=cast(s,'Undercover Operative')
    choose(s,source.id)
    assert s.state.rules.decision is not None
    roundtrip(s)
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2' if initial_controller=='p1' else 'p1')
    answer_entry_orders(s)
    assert s.state.cards[operative.id].zone=='p1:battlefield'
    assert s.state.cards[operative.id].counters.get('shield',0)==(1 if initial_controller=='p1' else 0)
    roundtrip(s)


def test_flesh_vanishing_upkeep_and_last_counter_sacrifice_are_real_triggers(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    source=cast(s,'Flesh Duplicate')
    choose(s,bear.id)
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[source.id].counters=={'time':2}
    act(s,'p1',type='set_counter',card_id=source.id,kind='time',value=1)
    to_phase(s,'upkeep',turn=7)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_undercover_snapshot_and_copy_recipe_survive_fresh_process_entry_order(cards,tmp_path):
    import subprocess
    import sys
    s=game(cards)
    put(s,'Doubling Season','battlefield')
    put(s,'Vorinclex, Monstrous Raider','battlefield',pid='p2')
    bear=put(s,'Grizzly Bears','battlefield')
    source=cast(s,'Undercover Operative')
    choose(s,bear.id)
    assert s.state.rules.decision is not None
    saved=tmp_path/'operative.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state_path,database,source,bear=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(state_path).read_text()),cards=repo)
s.perform('p1',{'type':'set_controller','card_ids':[bear],'player':'p2'})
for _ in range(20):
    d=s.state.rules.decision
    if d is not None:
        option=next((o for o in d.options if 'Doubling Season' in o.label),d.options[0])
        s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[option.id]})
    elif s.state.rules.stack:
        s.perform(s.state.rules.priority,{'type':'pass_priority'})
    else: break
assert s.state.cards[source].counters=={'shield':1}
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json()).model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,bear.id],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr



def test_source_ability_loss_is_distinct_from_copiable_vanishing(cards):
    s=game(cards)
    golem=put(s,'Soultether Golem','battlefield')
    frog=put(s,'Turn to Frog','hand')
    pay(s,'p1','Turn to Frog')
    act(s,'p1',type='cast_spell',card_id=frog.id,targets=[golem.id],sources=[])
    settle(s)
    assert 'vanishing' not in ch(s,golem).keywords
    duplicate=cast(s,'Flesh Duplicate')
    choose(s,golem.id)
    assert ch(s,duplicate).name=='Soultether Golem' and ch(s,duplicate).pt==(3,3)
    assert len([a for a in ch(s,duplicate).abilities if 'vanishing' in a.keywords])==2
    assert s.state.cards[duplicate.id].counters=={'time':4}  # PrintedVanishing1 plus the exception's Vanishing3.
    roundtrip(s)


def face_up_djinn(s):
    source=put(s,'Maelstrom Djinn','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':3})
    act(s,'p1',type='cast_spell',card_id=source.id,face_down=True,sources=[])
    settle(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'U':1})
    act(s,'p1',type='turn_face_up',card_id=source.id,sources=[])
    settle(s)
    return source


def test_non_copiable_granted_vanishing_suppresses_extra_vanishing(cards):
    from tests.test_rules_wave30m_durations import to_phase
    assert coverage.of_card_data(cards.resolve('Maelstrom Djinn')).level=='FULL'
    s=game(cards)
    source=face_up_djinn(s)
    assert s.state.cards[source.id].counters=={'time':2}
    assert any('vanishing' in a.keywords for a in ch(s,source).abilities)
    duplicate=cast(s,'Flesh Duplicate')
    choose(s,source.id)
    assert ch(s,duplicate).pt==(5,6) and 'flying' in ch(s,duplicate).keywords
    assert not any('vanishing' in a.keywords for a in ch(s,duplicate).abilities)
    assert not s.state.cards[duplicate.id].counters
    act(s,'p1',type='set_counter',card_id=source.id,kind='time',value=1)
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[duplicate.id].zone=='p1:battlefield'
    roundtrip(s)


def test_bare_vanishing_without_time_counters_does_not_sacrifice_at_upkeep(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s=game(cards)
    put(s,'Solemnity','battlefield')
    source=face_up_djinn(s)
    assert any('vanishing' in a.keywords for a in ch(s,source).abilities) and not s.state.cards[source.id].counters
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)
