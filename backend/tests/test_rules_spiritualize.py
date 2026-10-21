"""Spiritualize draws immediately and watches exact actual damage through this turn."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_reveal_consequences import cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA=json.loads((Path(__file__).parent/'fixtures/spiritualize_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(DATA):
        base[c['name']]=card(c['name'],set_code='spr',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in DATA]
    return table(cards,names,names,names)


def activate(s,source,pid='p1',inspect=False):
    mana(s,pid=pid,B=1)
    wait_priority(s,pid)
    act(s,pid,type='activate_ability',card_id=source.id,ability=0,sources=[])
    if inspect:
        for _ in range(16):
            found=[e for e in s.state.rules.stack.values() if e.event is not None and e.event.kind=='deal_damage']
            if found:
                return found
            act(s,s.state.rules.priority,type='pass_priority')
        raise AssertionError('damage did not create its watch trigger')
    settle(s)
    return []


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve('Spiritualize')).level=='FULL'


def test_immediate_genuine_draw_happens_before_any_damage(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    shown=put(s,'Sol Ring','library')
    drawn=s.state.rules.turn_log.drew.get('p1',0)
    source=cast(s,'Spiritualize',[bear.id])
    assert s.state.rules.turn_log.drew.get('p1',0)==drawn+1
    assert s.state.cards[shown.id].zone=='p1:hand'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.players['p1'].life==40
    roundtrip(s)


def test_noncombat_simultaneous_damage_aggregates_once_and_repeated_damage_survives_source_death(cards):
    s=game(cards)
    source=put(s,'Thrashing Wumpus','battlefield')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Spiritualize',[source.id])
    found=activate(s,source,inspect=True)
    assert len(found)==1
    assert found[0].event.amount==5 and found[0].event.count==5
    settle(s)
    assert s.state.players['p1'].life==44
    activate(s,source)
    assert s.state.players['p1'].life==48
    assert s.state.cards[bear.id].zone=='p2:graveyard'
    activate(s,source)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.players['p1'].life==51
    assert s.state.rules.turn_log.gained.get('p1',0)==14
    roundtrip(s)


def test_prevented_damage_does_not_count_toward_life_gain(cards):
    s=game(cards)
    source=put(s,'Thrashing Wumpus','battlefield')
    cast(s,'Spiritualize',[source.id])
    cast(s,'Safe Passage')
    found=activate(s,source,inspect=True)
    assert len(found)==1 and found[0].event.amount==2 and found[0].event.count==2
    settle(s)
    assert s.state.players['p1'].life==42
    assert s.state.players['p2'].life==39 and s.state.players['p3'].life==39
    assert s.state.cards[source.id].damage==0
    roundtrip(s)


def test_actual_combat_damage_gains_life_to_original_spell_controller(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'main1',turn=4)
    cast(s,'Spiritualize',[bear.id])
    to_phase(s,'declare_attackers')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p2'}])
    to_phase(s,'combat_damage')
    settle(s)
    assert s.state.players['p1'].life==42
    assert s.state.players['p2'].life==38
    roundtrip(s)


def test_watched_source_control_change_keeps_original_spell_controller_life_gain(cards):
    s=game(cards)
    source=put(s,'Thrashing Wumpus','battlefield')
    cast(s,'Spiritualize',[source.id])
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    activate(s,source,'p2')
    assert s.state.players['p1'].life==43
    assert s.state.players['p2'].life==39
    assert s.state.rules.turn_log.gained.get('p2',0)==0
    roundtrip(s)


@pytest.mark.parametrize('change',['blink','next_turn'])
def test_new_incarnation_and_after_end_of_turn_are_not_watched(cards,change):
    s=game(cards)
    source=put(s,'Thrashing Wumpus','battlefield')
    cast(s,'Spiritualize',[source.id])
    if change=='blink':
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'battlefield'})
    else:
        to_phase(s,'upkeep',turn=2)
        settle(s)
    activate(s,source)
    assert s.state.players['p1'].life==39
    assert s.state.rules.turn_log.gained.get('p1',0)==0
    roundtrip(s)


def test_saved_watch_resumes_in_fresh_process_with_one_immediate_draw(cards,tmp_path):
    import subprocess
    import sys
    s=game(cards)
    source=put(s,'Thrashing Wumpus','battlefield')
    before=s.state.rules.turn_log.drew.get('p1',0)
    cast(s,'Spiritualize',[source.id])
    assert s.state.rules.turn_log.drew.get('p1',0)==before+1
    saved=tmp_path/'spiritualize.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db,source,drawn=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
s.perform('p1',{'type':'activate_ability','card_id':source,'ability':0,'sources':[]})
for _ in range(24):
 if not s.state.zones['stack']:break
 assert not s.state.rules.decision
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
else:raise AssertionError('did not finish')
assert s.state.players['p1'].life==43
assert s.state.rules.turn_log.gained.get('p1',0)==4
assert s.state.rules.turn_log.drew.get('p1',0)==int(drawn)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,str(before+1)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
