"""Every other player pays one shared nominal life-gain event as a real alternative cost."""

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

NAMES = ["Pollywog Symbiote"]
DATA = json.loads((Path(__file__).parent / "fixtures/mutate_keyword_costs73_cards.json").read_text())


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


def setup(cards, name="Gemrazer"):
    ns = [c["name"] for c in DATA]
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    source = put(s, "Pollywog Symbiote", "battlefield")
    spell = put(s, name, "hand")
    return s,source,spell


def cast(s,c,mana,**kwargs):
    act(s,'p1',type='add_mana',player='p1',mana=mana)
    wait_priority(s,'p1')
    return act(s,'p1',type='cast_spell',card_id=c.id,sources=[],**kwargs)


def test_canonical(cards):
    assert coverage.of_card_data(cards.resolve("Pollywog Symbiote")).level == "FULL"


def test_normal_cast_of_mutate_keyword_spell_is_reduced_and_loots_before_it_resolves(cards):
    s,_,c=setup(cards)
    before=len(s.state.zones['p1:hand'])
    drew=s.state.rules.turn_log.drew.get('p1',0)
    cast(s,c,{'C':2,'G':1})
    assert c.zone=='stack'
    assert len(s.state.zones['stack'])==2
    assert sum(s.state.players['p1'].mana.values())==0
    assert len(s.state.zones['p1:hand'])==before-1
    answer(s)
    assert c.zone=='p1:battlefield'
    assert len(s.state.zones['p1:hand'])==before-1
    assert s.state.rules.turn_log.drew.get('p1',0)==drew+1
    roundtrip(s)


def test_actual_mutate_alternative_is_reduced_too(cards):
    from app.rules import alt_costs
    from app.rules.plan import Plan
    s,_,c=setup(cards)
    host=put(s,'Grizzly Bears','battlefield')
    plan=Plan(s.state,'p1',s.cards,None)
    key=next(o.key for o in alt_costs.offers(s.state,'p1',c,plan.ch(c),s.cards) if o.tag=='mutate')
    cast(s,c,{'G':2},alt_cost=key,targets=[host.id])
    assert len(s.state.zones['stack'])==2
    answer(s)
    assert any(x.merged for x in s.state.cards.values() if x.zone=='p1:battlefield')
    roundtrip(s)


def test_without_mutate_creature_spell_neither_reduces_nor_triggers(cards):
    s,_,c=setup(cards,'Grizzly Bears')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=c.id,sources=[])
    assert s.state.model_dump_json()==before
    cast(s,c,{'C':1,'G':1})
    assert len(s.state.zones['stack'])==1
    answer(s)


def test_opponents_mutate_keyword_spell_neither_reduced_nor_triggers(cards):
    s,source,c=setup(cards)
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    cast(s,c,{'C':3,'G':1})
    assert len(s.state.zones['stack'])==1
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)


def test_real_tax_is_applied_before_keyword_reduction(cards):
    s,_,c=setup(cards)
    put(s,'Sphere of Resistance','battlefield',pid='p2')
    cast(s,c,{'C':3,'G':1})
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)


def test_countered_original_spell_still_loots_via_native_event_lki(cards):
    s,_,c=setup(cards)
    before=len(s.state.zones['p1:hand'])
    drew=s.state.rules.turn_log.drew.get('p1',0)
    cast(s,c,{'C':2,'G':1})
    counter=put(s,'Counterspell','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':2})
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=counter.id,targets=[c.id],sources=[])
    answer(s)
    assert c.zone=='p1:graveyard'
    assert len(s.state.zones['p1:hand'])==before-1
    assert s.state.rules.turn_log.drew.get('p1',0)==drew+1
    roundtrip(s)


def test_reduction_never_pays_colored_symbols_and_failing_cast_is_atomic(cards):
    s,_,c=setup(cards)
    act(s,'p1',type='add_mana',player='p1',mana={'C':4})
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=c.id,sources=[])
    assert s.state.model_dump_json()==before


def test_source_departure_does_not_remove_already_triggered_native_loot(cards):
    s,source,c=setup(cards)
    before=len(s.state.zones['p1:hand'])
    drew=s.state.rules.turn_log.drew.get('p1',0)
    cast(s,c,{'C':2,'G':1})
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'graveyard','player':'p1'})
    answer(s)
    assert len(s.state.zones['p1:hand'])==before-1
    assert s.state.rules.turn_log.drew.get('p1',0)==drew+1
    assert c.zone=='p1:battlefield'


def test_true_cold_countered_spell_event_retains_mutate_lki_for_loot(cards,tmp_path):
    import os
    import subprocess
    import sys
    s,_,c=setup(cards)
    before=len(s.state.zones['p1:hand'])
    drew=s.state.rules.turn_log.drew.get('p1',0)
    cast(s,c,{'C':2,'G':1})
    counter=put(s,'Counterspell','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':2})
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=counter.id,targets=[c.id],sources=[])
    # Resolve Counterspell alone; leave Pollywog's original cast trigger on stack.
    for _ in range(10):
        if c.zone=='p1:graveyard':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert c.zone=='p1:graveyard'
    assert len(s.state.zones['stack'])==1
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
saved,database,cid,before,drew=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p3')
assert s.state.cards[cid].zone=='p1:graveyard'
assert len(s.state.zones['stack'])==1
answer(s)
assert len(s.state.zones['p1:hand'])==int(before)-1
assert s.state.rules.turn_log.drew.get('p1',0)==int(drew)+1
assert not s.state.zones.get('stack')
GameState.model_validate_json(s.state.model_dump_json())
'''
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),c.id,str(before),str(drew)],capture_output=True,text=True,env=os.environ.copy())
    assert run.returncode==0,run.stdout+run.stderr
