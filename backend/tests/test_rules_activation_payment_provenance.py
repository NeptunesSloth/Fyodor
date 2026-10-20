"""Mana spent to activate belongs to each ability object, including copied abilities."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave18b_mana import treasure
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Forsworn Paladin',"Jetmir's Fixer",'Paragon of Modernity']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/activation_payment_provenance_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='apv',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/activation_payment_provenance_cards.json').read_text())]
    s=table(cards,names,names,names)
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True)
    return s


def mana(s,**pool):
    act(s,'p1',type='add_mana',player='p1',mana=pool)


def activate(s,source,ability=0,targets=()):
    before=set(s.state.zones.get('stack',[]))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability,targets=list(targets),sources=[])
    aid=next(cid for cid in s.state.zones['stack'] if cid not in before)
    roundtrip(s)
    return aid


def ch(s,c):
    from app.rules.plan import Plan
    return Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c.id])


def use_treasure(s,color):
    token=treasure(s)
    act(s,'p1',type='activate_ability',card_id=token.id,ability=0,mana_choice=color)
    return token


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('tagged',[False,True])
def test_forsworn_paladin_treasure_mana_adds_deathtouch(cards,tagged):
    s=game(cards)
    source=put(s,'Forsworn Paladin','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    if tagged:
        use_treasure(s,'B')
        mana(s,C=2)
    else:
        mana(s,C=2,B=1)
    aid=activate(s,source,2,[bear.id])
    paid=s.state.rules.payments[s.state.rules.object_id(aid)]
    assert bool(paid.mana_tags)==tagged
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    settle(s)
    assert ch(s,bear).pt==(4,2)
    assert ('deathtouch' in ch(s,bear).keywords)==tagged
    roundtrip(s)


@pytest.mark.parametrize('tagged',[False,True])
def test_fixer_counter_replaces_temporary_buff_only_for_treasure_spent(cards,tagged):
    s=game(cards)
    source=put(s,"Jetmir's Fixer",'battlefield')
    if tagged:
        use_treasure(s,'R')
        mana(s,G=1)
    else:
        mana(s,R=1,G=1)
    activate(s,source)
    settle(s)
    assert ch(s,source).pt==(3,3)
    assert s.state.cards[source.id].counters.get('+1/+1',0)==int(tagged)
    to_phase(s,'main2',2)
    assert ch(s,source).pt==((3,3) if tagged else (2,2))
    roundtrip(s)


@pytest.mark.parametrize(('pool','counter'),[({'W':1,'U':1,'B':1},True),({'W':1,'U':1,'C':1},False),({'B':3},False)])
def test_paragon_counts_distinct_colors_not_colorless_or_quantity(cards,pool,counter):
    s=game(cards)
    source=put(s,'Paragon of Modernity','battlefield')
    mana(s,**pool)
    aid=activate(s,source,1)
    assert s.state.rules.payments[s.state.rules.object_id(aid)].mana_spent==pool
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1',0)==int(counter)
    assert ch(s,source).pt==(3,3)
    roundtrip(s)


def test_four_distinct_colors_under_ability_tax_fail_exactly_three(cards):
    s=game(cards)
    source=put(s,'Paragon of Modernity','battlefield')
    put(s,'Suppression Field','battlefield')
    mana(s,W=1,U=1,B=1,R=1,C=1)
    activate(s,source,1)
    settle(s)
    assert not s.state.cards[source.id].counters.get('+1/+1')
    assert ch(s,source).pt==(3,3)
    roundtrip(s)


def test_real_paladin_treasure_mana_is_attributed_to_later_targeted_activation(cards):
    s=game(cards)
    source=put(s,'Forsworn Paladin','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'main1',4)
    mana(s,C=1,B=1)
    activate(s,source,1)
    settle(s)
    token=next(c for c in s.state.cards.values() if c.name=='Treasure' and c.zone=='p1:battlefield')
    assert s.state.players['p1'].life==39 and s.state.cards[source.id].tapped
    act(s,'p1',type='activate_ability',card_id=token.id,ability=0,mana_choice='B')
    mana(s,C=2)
    activate(s,source,2,[bear.id])
    settle(s)
    assert 'deathtouch' in ch(s,bear).keywords
    roundtrip(s)


def test_ability_payment_does_not_read_permanents_treasure_paid_cast_record(cards):
    s=game(cards)
    source=put(s,"Jetmir's Fixer",'hand')
    use_treasure(s,'R')
    mana(s,G=1)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    assert any('Treasure' in t for t in s.state.rules.payments[s.state.rules.object_id(source.id)].mana_tags)
    mana(s,R=1,G=1)
    activate(s,source)
    settle(s)
    assert not s.state.cards[source.id].counters.get('+1/+1')
    assert ch(s,source).pt==(3,3)
    roundtrip(s)


def test_two_activations_of_same_source_have_independent_payment_records(cards):
    s=game(cards)
    source=put(s,"Jetmir's Fixer",'battlefield')
    use_treasure(s,'R')
    mana(s,G=1)
    tagged=activate(s,source)
    mana(s,R=1,G=1)
    plain=activate(s,source)
    records=s.state.rules.payments
    assert records[s.state.rules.object_id(tagged)].mana_tags
    assert not records[s.state.rules.object_id(plain)].mana_tags
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1')==1
    assert ch(s,source).pt==(4,4)
    to_phase(s,'main2',2)
    assert ch(s,source).pt==(3,3)
    roundtrip(s)


def test_actual_lithoform_copy_spends_no_mana_and_keeps_source_identity(cards):
    s=game(cards)
    source=put(s,"Jetmir's Fixer",'battlefield')
    copier=put(s,'Lithoform Engine','battlefield')
    use_treasure(s,'R')
    mana(s,G=1)
    original=activate(s,source)
    mana(s,C=2)
    engine_ability=activate(s,copier,0,[original])
    while engine_ability in s.state.zones.get('stack',[]):
        assert s.state.rules.decision is None
        act(s,s.state.rules.priority,type='pass_priority')
    copied=next(cid for cid in s.state.zones['stack'] if cid!=original)
    entry=s.state.rules.stack[copied]
    assert entry.source_card==source.id
    payment=s.state.rules.payments[s.state.rules.object_id(copied)]
    assert payment.mana_spent=={} and payment.mana_tags==[] and payment.mana_sources==[]
    roundtrip(s)
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1')==1
    assert ch(s,source).pt==(4,4)
    to_phase(s,'main2',2)
    assert ch(s,source).pt==(3,3)
    roundtrip(s)


def test_only_modeled_activation_payment_wording_bypasses_coverage_refusal():
    assert coverage.refusal('If mana from a Treasure was spent to activate this ability, draw a card.') is None
    assert coverage.refusal('If exactly three colors of mana were spent to activate this ability, draw a card.') is None
    assert coverage.refusal('Roll a die for each mana from Treasures spent to activate this ability.') is not None
    assert coverage.refusal('If mana from a creature was spent to activate this ability, draw a card.') is not None
    assert coverage.refusal('If {S} of its colors was spent to cast it, draw a card.') is not None


def test_native_self_payment_keeps_treasure_provenance_in_cold_resume(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    source=put(s,'Forsworn Paladin','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    token=treasure(s)
    act(s,'p1',type='set_prefs',payment='self')
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2,targets=[bear.id])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    saved=tmp_path/'ability-mana-provenance.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.rules.plan import Plan
save,db,token,bear=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
s.perform('p1',{'type':'activate_ability','card_id':token,'ability':0,'mana_choice':'B'})
assert s.state.rules.decision is None
ability=s.state.zones['stack'][-1]
record=s.state.rules.payments[s.state.rules.object_id(ability)]
assert record.mana_spent=={'C':2,'B':1} and any('Treasure' in tags for tags in record.mana_tags)
while s.state.zones.get('stack'):
    s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert 'deathtouch' in Plan(s.state,'p1',repo,None).ch(s.state.cards[bear]).keywords
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    out=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),token.id,bear.id],
                       cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert out.returncode==0,out.stderr
