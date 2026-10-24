"""Vine Gecko uses actual first kicked-spell payments and preserves other cast costs."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Vine Gecko"]
DATA = json.loads((Path(__file__).parent / "fixtures/first_kicked_costs77_cards.json").read_text())


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,name='Burst Lightning',source=True):
    ns=[c['name'] for c in DATA]*2
    s=table(cards,ns,ns,ns)
    for pid in ['p1','p2','p3']:
        act(s,pid,type='set_prefs',hold_priority=True,response='on')
    to_phase(s,'main1',4)
    gecko=put(s,'Vine Gecko','battlefield') if source else None
    spell=put(s,name,'hand')
    return s,gecko,spell


def cast(s,c,mana,kicker=0,**kwargs):
    act(s,'p1',type='add_mana',player='p1',mana=mana)
    wait_priority(s,'p1')
    return act(s,'p1',type='cast_spell',card_id=c.id,sources=[],kicker=kicker,optional_asked=True,**kwargs)


def test_canonical(cards):
    assert coverage.of_card_data(cards.resolve('Vine Gecko')).level=='FULL'


def test_first_actual_kicked_spell_costs_one_less_and_native_trigger_grows_gecko(cards):
    s,source,c=setup(cards)
    cast(s,c,{'C':3,'R':1},kicker=1,targets=['p3'])
    assert sum(s.state.players['p1'].mana.values())==0
    note=s.state.rules.turn_log.casts[-1]
    assert note.kicked77 is True
    assert len(s.state.zones['stack'])==2
    answer(s)
    assert source.counters.get('+1/+1')==1
    assert s.state.players['p3'].life==36
    roundtrip(s)


def test_multikicker_two_is_one_spell_one_discount_one_gecko_trigger(cards):
    s,source,c=setup(cards,'Everflowing Chalice')
    cast(s,c,{'C':3},kicker=2)
    assert sum(s.state.players['p1'].mana.values())==0
    assert s.state.rules.turn_log.casts[-1].kicked77 is True
    answer(s)
    assert c.counters.get('charge')==2
    assert source.counters.get('+1/+1')==1


def test_no_actual_kicker_has_no_discount_or_gecko_trigger(cards):
    s,source,c=setup(cards,'Grizzly Bears')
    cast(s,c,{'C':1,'G':1})
    assert sum(s.state.players['p1'].mana.values())==0
    assert s.state.rules.turn_log.casts[-1].kicked77 is False
    assert len(s.state.zones['stack'])==1
    answer(s)
    assert not source.counters


def test_actual_bargain_is_not_a_kicked_spell_and_does_not_consume_first_kicker_discount(cards):
    s,source,c=setup(cards,'Candy Grapple')
    artifact=put(s,'Ornithopter','battlefield')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,c,{'C':1,'B':1},optional_costs=[c.id+':bargain'],targets=[victim.id])
    d=s.state.rules.decision
    if d is not None:
        assert artifact.id in [o.id for o in d.options]
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[artifact.id])
    assert artifact.zone=='p1:graveyard'
    record=s.state.rules.payments[s.state.rules.object_id(c.id)]
    assert record.kicked==1
    assert s.state.rules.turn_log.casts[-1].kicked77 is False
    assert sum(s.state.players['p1'].mana.values())==0
    assert len(s.state.zones['stack'])==1
    answer(s)
    assert not source.counters
    actual=put(s,'Burst Lightning','hand')
    cast(s,actual,{'C':3,'R':1},kicker=1,targets=['p3'])
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert source.counters.get('+1/+1')==1


def second(s,name,exclude):
    c=next(c for c in s.state.cards.values() if c.name==name and c.owner=='p1' and c.id!=exclude.id)
    act(s,'p1',type='move',card_ids=[c.id],to={'zone':'hand','player':'p1'})
    return c


def test_ordinary_first_spell_does_not_consume_first_kicked_price(cards):
    s,source,c=setup(cards)
    cast(s,c,{'R':1},targets=['p3'])
    answer(s)
    actual=second(s,'Burst Lightning',c)
    cast(s,actual,{'C':3,'R':1},kicker=1,targets=['p3'])
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert source.counters.get('+1/+1')==1


def test_second_kicked_spell_has_full_price_even_if_first_still_on_stack(cards):
    s,source,c=setup(cards)
    cast(s,c,{'C':3,'R':1},kicker=1,targets=['p3'])
    actual=second(s,'Burst Lightning',c)
    cast(s,actual,{'C':4,'R':1},kicker=1,targets=['p3'])
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert source.counters.get('+1/+1')==2
    assert s.state.players['p3'].life==32


def test_failed_first_kicked_cast_does_not_consume_price_or_create_counter(cards):
    s,source,c=setup(cards)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'R':1})
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=c.id,sources=[],kicker=1,targets=['p3'])
    assert s.state.model_dump_json()==before
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    act(s,'p1',type='cast_spell',card_id=c.id,sources=[],kicker=1,targets=['p3'])
    answer(s)
    assert source.counters.get('+1/+1')==1


def test_real_tax_is_added_before_first_kicked_generic_reduction(cards):
    s,_,c=setup(cards)
    put(s,'Sphere of Resistance','battlefield',pid='p2')
    cast(s,c,{'C':4,'R':1},kicker=1,targets=['p3'])
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)


def test_late_entering_gecko_does_not_forget_an_earlier_kicked_spell(cards):
    s,_,c=setup(cards,source=False)
    cast(s,c,{'C':4,'R':1},kicker=1,targets=['p3'])
    answer(s)
    source=put(s,'Vine Gecko','battlefield')
    actual=second(s,'Burst Lightning',c)
    cast(s,actual,{'C':4,'R':1},kicker=1,targets=['p3'])
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert source.counters.get('+1/+1')==1


def test_awakens_synthetic_kicked_receipt_does_not_consume_true_first_kicker(cards):
    s,source,c=setup(cards,'Clutch of Currents')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    land=put(s,'Forest','battlefield')
    cast(s,c,{'C':4,'U':1},awaken=True,targets=[victim.id,land.id],target_counts=[1,1])
    assert s.state.rules.payments[s.state.rules.object_id(c.id)].kicked==1
    assert s.state.rules.turn_log.casts[-1].kicked77 is False
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert not source.counters
    actual=put(s,'Burst Lightning','hand')
    cast(s,actual,{'C':3,'R':1},kicker=1,targets=['p3'])
    answer(s)
    assert source.counters.get('+1/+1')==1


def test_entwine_does_not_consume_true_first_kicker(cards):
    s,source,c=setup(cards,'Tooth and Nail')
    cast(s,c,{'C':7,'G':2},kicker=1)
    assert s.state.rules.turn_log.casts[-1].kicked77 is False
    assert sum(s.state.players['p1'].mana.values())==0
    assert len(s.state.zones['stack'])==1
    counter=put(s,'Counterspell','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':2})
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=counter.id,targets=[c.id],sources=[])
    answer(s)
    assert not source.counters
    actual=put(s,'Burst Lightning','hand')
    cast(s,actual,{'C':3,'R':1},kicker=1,targets=['p3'])
    answer(s)
    assert source.counters.get('+1/+1')==1


def test_first_kicked_zero_generic_requirement_stays_colored_and_still_consumes_first_spell(cards):
    s,source,c=setup(cards,'Vines of Vastwood')
    cast(s,c,{'G':2},kicker=1,targets=[source.id])
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    actual=put(s,'Burst Lightning','hand')
    cast(s,actual,{'C':4,'R':1},kicker=1,targets=['p3'])
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert source.counters.get('+1/+1')==2


def test_native_minimum_mana_floor_applies_after_first_kicker_reduction(cards):
    s,source,c=setup(cards,'Everflowing Chalice')
    put(s,'Trinisphere','battlefield',pid='p2')
    cast(s,c,{'C':3},kicker=1)
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert c.counters.get('charge')==1
    assert source.counters.get('+1/+1')==1


def test_other_players_first_kicked_spell_is_not_discounted_and_does_not_consume_yours(cards):
    s,source,_=setup(cards)
    c=put(s,'Burst Lightning','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'C':4,'R':1})
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=c.id,sources=[],kicker=1,targets=['p3'])
    assert sum(s.state.players['p2'].mana.values())==0
    answer(s)
    assert not source.counters
    own=put(s,'Burst Lightning','hand')
    cast(s,own,{'C':3,'R':1},kicker=1,targets=['p3'])
    answer(s)
    assert source.counters.get('+1/+1')==1


def test_legacy_missing_paid_kicker_receipt_guards_only_actual_kicked_cost_and_keeps_views_safe(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    s,source,c=setup(cards,'Grizzly Bears')
    cast(s,c,{'C':1,'G':1})
    answer(s)
    actual=put(s,'Burst Lightning','hand')
    old=s.state.model_dump(mode='json')
    for note in old['rules']['turn_log']['casts']:
        note.pop('kicked77',None)
    s=GameSession(GameState.model_validate(old),cards=cards)
    s.view('p1')
    s.view('p3')
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'R':1})
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError,match='unknown.*manually'):
        act(s,'p1',type='cast_spell',card_id=actual.id,sources=[],kicker=1,targets=['p3'])
    assert s.state.model_dump_json()==before
    act(s,'p1',type='cast_spell',card_id=actual.id,sources=[],targets=['p3'],optional_asked=True)
    answer(s)
    assert not s.state.cards[source.id].counters


def test_true_cold_countered_first_kicked_receipt_still_consumes_current_turn_discount(cards,tmp_path):
    import os
    import subprocess
    import sys
    s,source,c=setup(cards)
    cast(s,c,{'C':3,'R':1},kicker=1,targets=['p3'])
    counter=put(s,'Counterspell','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':2})
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=counter.id,sources=[],targets=[c.id])
    answer(s)
    assert c.zone=='p1:graveyard'
    assert source.counters.get('+1/+1')==1
    actual=second(s,'Burst Lightning',c)
    saved=tmp_path/'save.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.game_helpers import act
saved,database,cid,source=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p1')
assert any(n.player=='p1' and n.kicked77 is True for n in s.state.rules.turn_log.casts)
act(s,'p1',type='add_mana',player='p1',mana={'C':4,'R':1})
wait_priority(s,'p1')
act(s,'p1',type='cast_spell',card_id=cid,sources=[],kicker=1,targets=['p3'])
assert sum(s.state.players['p1'].mana.values())==0
answer(s)
assert s.state.cards[source].counters.get('+1/+1')==2
assert s.state.players['p3'].life==36
GameState.model_validate_json(s.state.model_dump_json())
'''
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),actual.id,source.id],capture_output=True,text=True,env=os.environ.copy())
    assert run.returncode==0,run.stdout+run.stderr


def test_promised_gift_is_not_actual_kicker_or_first_kicked_price_consumption(cards):
    s,source,c=setup(cards,"Long River's Pull")
    original=put(s,'Opt','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=original.id,sources=[])
    cast(s,c,{'U':2},optional_costs=[c.id+':gift'],gift_to='p2',targets=[original.id],target_counts=[0,1])
    assert s.state.rules.payments[s.state.rules.object_id(c.id)].kicked==1
    assert s.state.rules.turn_log.casts[-1].kicked77 is False
    answer(s)
    assert not source.counters
    actual=put(s,'Burst Lightning','hand')
    cast(s,actual,{'C':3,'R':1},kicker=1,targets=['p3'])
    answer(s)
    assert source.counters.get('+1/+1')==1


def test_actual_nonmana_kicker_is_still_kicked_and_discount_applies_to_total_mana(cards):
    s,source,c=setup(cards,'Rushing River')
    land=put(s,'Forest','battlefield')
    first=put(s,'Grizzly Bears','battlefield',pid='p2')
    other=put(s,'Ornithopter','battlefield',pid='p2')
    cast(s,c,{'C':1,'U':1},kicker=1,targets=[first.id,other.id],target_counts=[1,1])
    d=s.state.rules.decision
    if d:
        assert land.id in [o.id for o in d.options]
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[land.id])
    assert land.zone=='p1:graveyard'
    assert s.state.rules.turn_log.casts[-1].kicked77 is True
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert first.zone=='p2:hand' and other.zone=='p2:hand'
    assert source.counters.get('+1/+1')==1


def test_true_cold_legacy_unknown_kicker_guards_explicit_payment_then_next_turn_recovers(cards,tmp_path):
    import os
    import subprocess
    import sys
    s,source,c=setup(cards,'Grizzly Bears')
    cast(s,c,{'C':1,'G':1})
    answer(s)
    actual=put(s,'Burst Lightning','hand')
    old=s.state.model_dump(mode='json')
    for note in old['rules']['turn_log']['casts']:
        note.pop('kicked77',None)
    saved=tmp_path/'legacy.json'
    saved.write_text(json.dumps(old))
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_wave30m_durations import to_phase
from tests.game_helpers import act
saved,database,cid,source=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p1');s.view('p3')
assert any(n.player=='p1' and n.kicked77 is None for n in s.state.rules.turn_log.casts)
act(s,'p1',type='add_mana',player='p1',mana={'C':3,'R':1})
wait_priority(s,'p1')
before=s.state.model_dump_json()
try:
 act(s,'p1',type='cast_spell',card_id=cid,sources=[],kicker=1,targets=['p3'])
except ActionError as e:
 assert 'unknown' in str(e) and 'manually' in str(e)
else: raise AssertionError('Unknown earlier kicker cannot be silently treated as false')
assert s.state.model_dump_json()==before
act(s,'p1',type='clear_mana',player='p1')
to_phase(s,'main1',7)
assert not any(n.kicked77 is None for n in s.state.rules.turn_log.casts)
act(s,'p1',type='add_mana',player='p1',mana={'C':3,'R':1})
wait_priority(s,'p1')
act(s,'p1',type='cast_spell',card_id=cid,sources=[],kicker=1,targets=['p3'])
assert sum(s.state.players['p1'].mana.values())==0
answer(s)
assert s.state.cards[source].counters.get('+1/+1')==1
GameState.model_validate_json(s.state.model_dump_json())
'''
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),actual.id,source.id],capture_output=True,text=True,env=os.environ.copy())
    assert run.returncode==0,run.stdout+run.stderr


def test_actual_omnisicience_free_base_still_pays_kicker_and_records_real_first_payment(cards):
    s,source,c=setup(cards)
    put(s,'Omniscience','battlefield')
    cast(s,c,{'C':3},kicker=1,free=True,targets=['p3'])
    record=s.state.rules.payments[s.state.rules.object_id(c.id)]
    assert record.alternative=='free' and record.total_cost=='{3}'
    assert s.state.rules.turn_log.casts[-1].kicked77 is True
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    actual=second(s,'Burst Lightning',c)
    cast(s,actual,{'C':4},kicker=1,free=True,targets=['p3'])
    assert s.state.rules.payments[s.state.rules.object_id(actual.id)].total_cost=='{4}'
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert source.counters.get('+1/+1')==2
    roundtrip(s)
