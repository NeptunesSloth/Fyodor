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

NAMES = ["Archive Trap"]
DATA = json.loads((Path(__file__).parent / "fixtures/own_library_search_costs75_cards.json").read_text())


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


def setup(cards, own=False):
    ns = [c["name"] for c in DATA]*3
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4 if own else 5)
    source = put(s, "Archive Trap", "hand")
    return s,source


def search(s, pid='p2', name='Rampant Growth', none=False):
    spell=put(s,name,'hand',pid=pid)
    mana={'C':1,'G':1} if name=='Rampant Growth' else {'C':1,'B':2}
    act(s,pid,type='add_mana',player=pid,mana=mana)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=spell.id,sources=[],**({'targets':['p3']} if name=="Praetor's Grasp" else {}))
    for _ in range(30):
        d=s.state.rules.decision
        if d:
            pick=[] if none and d.min_choices==0 else [d.options[0].id]
            act(s,d.player,type='choose',decision_id=d.id,option_ids=pick)
        elif s.state.zones.get('stack'):
            act(s,s.state.rules.priority,type='pass_priority')
        else:
            break
    assert spell.zone==f'{pid}:graveyard'


def alt(s,source,**kwargs):
    wait_priority(s,'p1')
    return act(s,'p1',type='cast_spell',card_id=source.id,alt_cost=f'{source.id}:0',targets=['p3'],sources=[],**kwargs)


def test_canonical(cards):
    assert coverage.of_card_data(cards.resolve("Archive Trap")).level == "FULL"


@pytest.mark.parametrize('none',[False,True])
def test_actual_opponent_own_library_search_even_failfind_allows_zero_cost_trap(cards,none):
    s,source=setup(cards)
    search(s,none=none)
    assert s.state.rules.turn_log.searched_own_library75==['p2']
    before=len(s.state.zones['p3:library'])
    alt(s,source)
    assert source.zone=='stack'
    answer(s)
    assert before-len(s.state.zones['p3:library'])==13
    assert source.zone=='p1:graveyard'
    roundtrip(s)


def test_no_search_cannot_announce_zero_alternative_atomically(cards):
    s,source=setup(cards)
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s,source)
    assert s.state.model_dump_json()==before


def test_casters_own_search_does_not_satisfy_opponent_condition(cards):
    s,source=setup(cards,own=True)
    search(s,pid='p1')
    assert s.state.rules.turn_log.searched_own_library75==['p1']
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s,source)
    assert s.state.model_dump_json()==before


def test_opponent_searching_another_players_library_does_not_satisfy_own_library_condition(cards):
    s,source=setup(cards)
    search(s,name="Praetor's Grasp")
    assert not s.state.rules.turn_log.searched_own_library75
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s,source)
    assert s.state.model_dump_json()==before


def test_forbidden_search_does_not_record_search_receipt(cards):
    s,source=setup(cards)
    put(s,'Mindlock Orb','battlefield')
    search(s)
    assert not s.state.rules.turn_log.searched_own_library75
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s,source)
    assert s.state.model_dump_json()==before


def test_restricted_top_four_still_is_actual_opponent_search(cards):
    s,source=setup(cards)
    put(s,'Aven Mindcensor','battlefield')
    search(s,none=True)
    assert s.state.rules.turn_log.searched_own_library75==['p2']
    alt(s,source)
    answer(s)


def test_previous_turn_search_does_not_qualify_this_turn(cards):
    s,source=setup(cards)
    search(s)
    to_phase(s,'main1',6)
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s,source)
    assert s.state.model_dump_json()==before


def test_actual_look_scry_draw_is_not_a_search(cards):
    s,source=setup(cards)
    opt=put(s,'Opt','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=opt.id,sources=[])
    answer(s)
    assert not s.state.rules.turn_log.searched_own_library75
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s,source)
    assert s.state.model_dump_json()==before


@pytest.mark.parametrize('searched',[False,True])
def test_actual_normal_mana_is_always_optional_and_preserves_mana_value(cards,searched):
    from app.rules.plan import Plan
    s,source=setup(cards)
    if searched:
        search(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'U':2})
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p3'],sources=[])
    assert Plan(s.state,'p1',cards,None).ch(source).mana_value==5
    assert sum(s.state.players['p1'].mana.values())==0
    assert s.state.rules.payments[s.state.rules.object_id(source.id)].alternative is None
    answer(s)


def test_real_alternative_tax_is_paid_once_without_mana_value_change(cards):
    from app.rules.plan import Plan
    s,source=setup(cards)
    search(s)
    put(s,'Sphere of Resistance','battlefield',pid='p2')
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        alt(s,source)
    assert s.state.model_dump_json()==before
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    alt(s,source)
    assert sum(s.state.players['p1'].mana.values())==0
    assert Plan(s.state,'p1',cards,None).ch(source).mana_value==5
    answer(s)


def test_real_short_library_mills_all_remaining_cards(cards):
    s,source=setup(cards)
    search(s)
    remove=list(s.state.zones['p3:library'])[5:]
    act(s,'p3',type='move',card_ids=remove,to={'zone':'graveyard','player':'p3'})
    assert len(s.state.zones['p3:library'])==5
    alt(s,source)
    answer(s)
    assert not s.state.zones['p3:library']


def test_true_cold_actual_search_receipt_enables_later_zero_alternative(cards,tmp_path):
    import os
    import subprocess
    import sys
    s,source=setup(cards)
    search(s,none=True)
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
saved,database,cid=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p3')
assert s.state.rules.turn_log.searched_own_library75==['p2']
wait_priority(s,'p1')
before=len(s.state.zones['p3:library'])
act(s,'p1',type='cast_spell',card_id=cid,alt_cost=f'{cid}:0',targets=['p3'],sources=[])
answer(s)
assert before-len(s.state.zones['p3:library'])==13
assert s.state.cards[cid].zone=='p1:graveyard'
GameState.model_validate_json(s.state.model_dump_json())
'''
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id],capture_output=True,text=True,env=os.environ.copy())
    assert run.returncode==0,run.stdout+run.stderr


def legacy(s,cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    old=s.state.model_dump(mode='json')
    old['rules']['turn_log'].pop('searched_own_library75',None)
    old['rules']['turn_log'].pop('search_history75_known',None)
    s=GameSession(GameState.model_validate(old),cards=cards)
    s.view('p3')
    s.view('p1')
    assert s.state.rules.turn_log.search_history75_known is None
    return s


def test_legacy_unknown_selected_alternative_has_explicit_atomic_manual_guard_but_normal_paid_cast_works(cards):
    s,source=setup(cards)
    search(s)
    s=legacy(s,cards)
    wait_priority(s,'p1')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError,match='unknown.*manually'):
        alt(s,source)
    assert s.state.model_dump_json()==before
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'U':2})
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p3'],sources=[])
    answer(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_legacy_unknown_positive_actual_opponent_search_is_sufficient_without_faking_known_history(cards):
    s,source=setup(cards)
    s=legacy(s,cards)
    search(s,none=True)
    assert s.state.rules.turn_log.search_history75_known is None
    assert s.state.rules.turn_log.searched_own_library75==['p2']
    alt(s,source)
    answer(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_legacy_unknown_own_search_does_not_erase_missing_opponent_history(cards):
    s,source=setup(cards,own=True)
    s=legacy(s,cards)
    search(s,pid='p1')
    assert s.state.rules.turn_log.search_history75_known is None
    assert s.state.rules.turn_log.searched_own_library75==['p1']
    wait_priority(s,'p1')
    with pytest.raises(ActionError,match='unknown.*manually'):
        alt(s,source)


def test_native_next_turn_establishes_known_empty_after_legacy_unknown(cards):
    s,source=setup(cards)
    s=legacy(s,cards)
    to_phase(s,'main1',6)
    assert s.state.rules.turn_log.search_history75_known is True
    assert not s.state.rules.turn_log.searched_own_library75
    wait_priority(s,'p1')
    with pytest.raises(ActionError) as got:
        alt(s,source)
    assert 'unknown' not in str(got.value)


def test_true_cold_old_save_manual_guard_and_normal_paid_cast(cards,tmp_path):
    import os
    import subprocess
    import sys
    s,source=setup(cards)
    search(s)
    old=s.state.model_dump(mode='json')
    old['rules']['turn_log'].pop('searched_own_library75',None)
    old['rules']['turn_log'].pop('search_history75_known',None)
    saved=tmp_path/'old.json'
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
from tests.game_helpers import act
saved,database,cid=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p3')
s.view('p1')
assert s.state.rules.turn_log.search_history75_known is None
wait_priority(s,'p1')
before=s.state.model_dump_json()
try:
 act(s,'p1',type='cast_spell',card_id=cid,alt_cost=f'{cid}:0',targets=['p3'],sources=[])
except ActionError as e:
 assert 'unknown' in str(e) and 'manually' in str(e)
else: raise AssertionError('Legacy history must not silently become known none')
assert s.state.model_dump_json()==before
act(s,'p1',type='add_mana',player='p1',mana={'C':3,'U':2})
act(s,'p1',type='cast_spell',card_id=cid,targets=['p3'],sources=[])
answer(s)
assert s.state.cards[cid].zone=='p1:graveyard'
GameState.model_validate_json(s.state.model_dump_json())
'''
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id],capture_output=True,text=True,env=os.environ.copy())
    assert run.returncode==0,run.stdout+run.stderr
