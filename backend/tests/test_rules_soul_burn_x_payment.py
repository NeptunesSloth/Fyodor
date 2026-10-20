"""Soul Burn records actual black mana assigned to X through saved native payments."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for file in ('x_mana_restriction_cards.json','drain_life_soul_burn_cards.json'):
        for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures'/file).read_text())):
            base[c['name']]=card(c['name'],set_code='sbx',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=['Soul Burn','Drain Life','Jet Medallion','Trinisphere',"K'rrik, Son of Yawgmoth",'Mycosynth Lattice','Wand of the Worldsoul','Grizzly Bears','Omniscience','Crypt Rats']
    s=table(cards,names,names,names)
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True)
    return s


def cast(s,*,x=2,pool=None):
    act(s,'p1',type='add_mana',player='p1',mana=pool or {'B':3,'R':2})
    spell=put(s,'Soul Burn','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,x_value=x,targets=['p3'],sources=[])
    return spell


def choose_black(s,k):
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='x_allocation'
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[str(k)])


def record(s,spell):
    return s.state.rules.payments[s.state.rules.object_id(spell.id)]


@pytest.mark.parametrize('black',[0,1,2])
def test_same_aggregate_mana_different_x_assignment_survives_save_replay(cards,black):
    s=game(cards)
    spell=cast(s)
    assert mana_pool(s,'p1')=={'B':3,'R':2}  # The mandatory choice precedes mana commitment.
    choose_black(s,black)
    paid=record(s,spell)
    assert paid.x==2 and paid.x_black_spent==black
    assert paid.mana_spent=={'B':3,'R':2}
    assert not mana_pool(s,'p1')
    roundtrip(s)
    settle(s)
    assert s.state.players['p3'].life==38
    assert s.state.players['p1'].life==40+black
    roundtrip(s)


def test_fixed_black_cost_is_not_included_in_x_gain(cards):
    s=game(cards)
    spell=cast(s,pool={'B':1,'R':4})
    assert s.state.rules.decision is None
    assert record(s,spell).x_black_spent==0
    settle(s)
    assert s.state.players['p1'].life==40
    roundtrip(s)


def test_reducer_allocation_preserves_choice_to_pay_more_x_with_black(cards):
    s=game(cards)
    put(s,'Jet Medallion','battlefield')
    spell=cast(s,pool={'B':3,'R':1})
    choose_black(s,2)
    assert record(s,spell).x_black_spent==2
    assert sum(record(s,spell).mana_spent.values())==4
    settle(s)
    assert s.state.players['p1'].life==42
    roundtrip(s)


def test_floor_generic_is_not_x_after_all_original_generic_was_reduced(cards):
    s=game(cards)
    for pid in ('p1','p2','p3'):
        jet=put(s,'Jet Medallion','battlefield',pid=pid)
        if pid!='p1':
            act(s,'p1',type='set_controller',card_ids=[jet.id],player='p1')
    put(s,'Trinisphere','battlefield')
    spell=cast(s,x=1,pool={'B':3})
    assert s.state.rules.decision is None
    assert record(s,spell).x_black_spent==0
    assert record(s,spell).mana_spent=={'B':3}
    settle(s)
    assert s.state.players['p1'].life==40
    roundtrip(s)


def test_krrik_life_for_fixed_black_does_not_count_as_black_x_mana(cards):
    s=game(cards)
    put(s,"K'rrik, Son of Yawgmoth",'battlefield')
    spell=cast(s,pool={'B':1,'R':1,'C':2})
    assert s.state.rules.decision is None
    paid=record(s,spell)
    assert paid.x_black_spent==1 and paid.life==2
    settle(s)
    assert s.state.players['p1'].life==39
    roundtrip(s)


def test_as_though_blue_mana_stays_nonblack_in_x_record(cards):
    s=game(cards)
    put(s,'Mycosynth Lattice','battlefield')
    spell=cast(s,pool={'U':5})
    assert s.state.rules.decision is None
    assert record(s,spell).x_black_spent==0
    settle(s)
    assert s.state.players['p1'].life==40
    roundtrip(s)


def test_convoke_pays_x_without_spending_black_and_does_not_repeat_tapping(cards):
    s=game(cards)
    wand=put(s,'Wand of the Worldsoul','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='activate_ability',card_id=wand.id,ability=2)
    settle(s)
    act(s,'p1',type='add_mana',player='p1',mana={'B':2,'R':1})
    spell=put(s,'Soul Burn','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,x_value=1,targets=['p3'],sources=[],
        contributions=[{'kind':'convoke','card':bear.id}])
    choose_black(s,1)
    paid=record(s,spell)
    assert paid.x_black_spent==1 and len(paid.contributions)==1
    assert paid.contributions[0].pays=='1' and s.state.cards[bear.id].tapped
    assert paid.mana_spent=={'B':2,'R':1}
    settle(s)
    assert s.state.players['p1'].life==41
    roundtrip(s)


def test_free_cast_uses_x_zero_and_records_zero_black(cards):
    s=game(cards)
    put(s,'Omniscience','battlefield')
    spell=put(s,'Soul Burn','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,x_value=0,targets=['p3'],sources=[],free=True)
    assert s.state.rules.decision is None
    assert record(s,spell).x_black_spent==0
    settle(s)
    assert s.state.players['p1'].life==40 and s.state.players['p3'].life==40
    roundtrip(s)


@pytest.mark.parametrize('black',[0,1])
@pytest.mark.parametrize('automatic',[False,True])
def test_black_convoke_assignment_and_x_mana_allocation_are_chosen_jointly(cards,black,automatic):
    s=game(cards)
    wand=put(s,'Wand of the Worldsoul','battlefield')
    rat=put(s,'Crypt Rats','battlefield')
    act(s,'p1',type='activate_ability',card_id=wand.id,ability=2)
    settle(s)
    act(s,'p1',type='add_mana',player='p1',mana={'B':1,'R':1,'C':2})
    spell=put(s,'Soul Burn','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,x_value=2,targets=['p3'],
        **({} if automatic else {'sources':[], 'contributions':[{'kind':'convoke','card':rat.id}]}))
    assert not s.state.cards[rat.id].tapped  # Selection precedes helper commitment too.
    choose_black(s,black)
    paid=record(s,spell)
    assert paid.x_black_spent==black
    assert paid.contributions[0].pays==('1' if black==0 else 'B')
    assert s.state.cards[rat.id].tapped
    settle(s)
    assert s.state.players['p1'].life==40+black
    roundtrip(s)


def test_soul_quantity_choice_resumes_in_genuinely_cold_process(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    spell=cast(s)
    saved=tmp_path/'soul-x-allocation.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
save,db,spell=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
assert d.resume['step']=='x_allocation'
s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['1']})
assert s.state.rules.decision is None
record=s.state.rules.payments[s.state.rules.object_id(spell)]
assert record.x==2 and record.x_black_spent==1 and record.mana_spent=={'B':3,'R':2}
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    out=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),spell.id],
                       cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert out.returncode==0,out.stderr


def test_payment_cancellation_precedes_costs_and_quantity_choice(cards):
    s=game(cards)
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='add_mana',player='p1',mana={'B':1,'C':4})
    spell=put(s,'Soul Burn','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,x_value=2,targets=['p3'])
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='pay_mana'
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['cancel'])
    assert s.state.cards[spell.id].zone=='p1:hand'
    assert mana_pool(s,'p1')=={'B':1,'C':4}
    assert not s.state.rules.stack
    roundtrip(s)
