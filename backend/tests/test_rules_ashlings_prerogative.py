"""Chosen parity is evaluated for the prospective permanent, before entry."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars

NAME="Ashling's Prerogative"

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/ashlings_prerogative_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='ash',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=[NAME,'Grizzly Bears','Llanowar Elves','Walking Ballista','Sol Ring','Living Lands']
    return table(cards,ns,ns,ns)


def cast_choice(s,quality):
    source=put(s,NAME,'hand')
    mana(s,C=1,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d
    roundtrip(s)
    option=next(o.id for o in d.options if o.label.lower()==quality.lower())
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[option])
    settle(s)
    return source


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'

@pytest.mark.parametrize('quality',['Odd','Even'])
@pytest.mark.parametrize('name,odd',[('Grizzly Bears',False),('Llanowar Elves',True)])
def test_actual_choice_creature_enters_tapped_exact_inverse_and_gets_haste(cards,quality,name,odd):
    s=game(cards)
    cast_choice(s,quality)
    source=put(s,name,'hand')
    mana(s,C=1 if not odd else 0,G=1)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    matches=(quality=='Odd')==odd
    assert s.state.cards[source.id].tapped is not matches
    assert ('haste' in chars(s,s.state.cards[source.id]).keywords)==matches
    roundtrip(s)

@pytest.mark.parametrize('quality',['Odd','Even'])
def test_permanent_x_is_zero_even_when_announced_x_was_odd(cards,quality):
    s=game(cards)
    cast_choice(s,quality)
    source=put(s,'Walking Ballista','hand')
    mana(s,C=2)
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=1,sources=[])
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1')==1
    assert s.state.cards[source.id].tapped==(quality=='Odd')
    assert ('haste' in chars(s,s.state.cards[source.id]).keywords)==(quality=='Even')
    roundtrip(s)


def test_missing_chosen_quality_is_fail_closed_and_noncreature_is_not_tapped(cards):
    s=game(cards)
    put(s,NAME,'battlefield')
    bear=put(s,'Grizzly Bears','hand')
    mana(s,C=1,G=1)
    act(s,'p1',type='cast_spell',card_id=bear.id,sources=[])
    settle(s)
    assert not s.state.cards[bear.id].tapped
    assert 'haste' not in chars(s,s.state.cards[bear.id]).keywords
    roundtrip(s)

@pytest.mark.parametrize('animated',[False,True])
def test_prospective_land_creature_type_and_zero_mana_value(cards,animated):
    s=game(cards)
    cast_choice(s,'Odd')
    if animated:
        put(s,'Living Lands','battlefield')
    land=put(s,'Forest','hand')
    act(s,'p1',type='play_land',card_id=land.id)
    settle(s)
    assert s.state.cards[land.id].tapped==animated
    assert ('Creature' in chars(s,s.state.cards[land.id]).types)==animated
    roundtrip(s)


def test_actual_choice_survives_cold_load_and_applies_to_opponents(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    source=put(s,NAME,'hand')
    mana(s,C=1,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    bear=put(s,'Grizzly Bears','hand','p2')
    saved=tmp_path/'ashling.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_bandmate_references import mana
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import settle
save,db,bear=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[next(o.id for o in d.options if o.label=='Odd')]})
settle(s)
to_phase(s,'main1',turn=2)
mana(s,pid='p2',C=1,G=1)
s.perform('p2',{'type':'cast_spell','card_id':bear,'sources':[]})
settle(s)
assert s.state.cards[bear].zone=='p2:battlefield' and s.state.cards[bear].tapped
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),bear.id],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
