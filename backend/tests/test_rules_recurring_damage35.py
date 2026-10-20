"""Canonical collateral: paid graveyard return respects upkeep and raid."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_discard_outcomes import cold_run
from tests.test_rules_mana_delayed_effects import answer, cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA=Path(__file__).parent/'fixtures/recurring_damage35_cards.json'
NAMES=['Hammer of Bogardan','Repeating Barrage']

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads(DATA.read_text())):
        fields={k:v for k,v in c.items() if k not in ['name','id','oracle_id','set_code','collector_number']}
        base[c['name']]=card(c['name'],set_code='rd35',number=str(i),**fields)
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    r=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield r
    r.close()

def game(cards):
    names=NAMES+['Trained Armodon']
    s=table(cards,names,names,names)
    for p in ['p1','p2','p3']:
        act(s,p,type='set_prefs',hold_priority=True)
    to_phase(s,'main1',4)
    return s

def activate(s,c,pool=None):
    wait_priority(s,'p1')
    if pool:
        act(s,'p1',type='add_mana',player='p1',mana=pool)
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c.id])
    index=next(a.index for a in ch.abilities if a.kind=='activated')
    act(s,'p1',type='activate_ability',card_id=c.id,ability=index,sources=[])

@pytest.mark.parametrize('name',NAMES)
def test_actual_damage_and_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'
    s=game(cards)
    life=s.state.players['p2'].life
    c=cast(s,name,{'R':3,'C':1},['p2'])
    answer(s)
    roundtrip(s)
    assert s.state.players['p2'].life==life-3
    assert s.state.cards[c.id].zone=='p1:graveyard'

@pytest.mark.parametrize('name',NAMES)
def test_illegal_main_phase_without_raid_is_atomic(cards,name):
    s=game(cards)
    c=put(s,name,'graveyard')
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        activate(s,c)
    assert s.state.model_dump(mode='json')==before

@pytest.mark.parametrize('cold',[False,True])
def test_hammer_own_upkeep_paid_return(cards,tmp_path,cold):
    s=game(cards)
    c=put(s,'Hammer of Bogardan','graveyard')
    to_phase(s,'upkeep',7)
    activate(s,c,{'R':3,'C':2})
    assert s.state.cards[c.id].zone=='p1:graveyard'
    assert s.state.players['p1'].mana.get('R',0)==0
    if cold:
        cold_run(s,cards,tmp_path,"answer(s)\nassert s.state.cards[args[0]].zone=='p1:hand'\n",c.id)
    else:
        answer(s)
        roundtrip(s)
        assert s.state.cards[c.id].zone=='p1:hand'

def test_hammer_opponent_upkeep_rejected(cards):
    s=game(cards)
    c=put(s,'Hammer of Bogardan','graveyard')
    to_phase(s,'upkeep',5)
    with pytest.raises(ActionError):
        activate(s,c,{'R':3,'C':2})
    assert s.state.cards[c.id].zone=='p1:graveyard'

def test_barrage_actual_attack_paid_cold_return(cards,tmp_path):
    s=game(cards)
    c=put(s,'Repeating Barrage','graveyard')
    attacker=put(s,'Trained Armodon','battlefield')
    to_phase(s,'declare_attackers',7)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p2'}])
    to_phase(s,'main2',7)
    activate(s,c,{'R':2,'C':3})
    assert s.state.cards[c.id].zone=='p1:graveyard'
    cold_run(s,cards,tmp_path,"answer(s)\nassert s.state.cards[args[0]].zone=='p1:hand'\n",c.id)

def test_hammer_insufficient_cost_rejected(cards):
    s=game(cards)
    c=put(s,'Hammer of Bogardan','graveyard')
    to_phase(s,'upkeep',7)
    with pytest.raises(ActionError):
        activate(s,c,{'R':2,'C':2})
    assert s.state.cards[c.id].zone=='p1:graveyard'
    assert not s.state.rules.stack
