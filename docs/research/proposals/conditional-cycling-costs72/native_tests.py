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

NAMES = ["New Perspectives"]
DATA = json.loads((Path(__file__).parent / "fixtures/conditional_cycling_costs72_cards.json").read_text())


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


def setup(cards, name="Renewed Faith", count=7):
    ns = [c["name"] for c in DATA]
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    source = put(s, "New Perspectives", "battlefield")
    act(s, "p1", type="move", card_ids=list(s.state.zones.get("p1:hand",[])), to={"zone":"library", "player":"p1"})
    cycled = put(s, name, "hand")
    for n in ["Forest","Plains","Island","Mountain","Swamp","Lightning Bolt"][:count-1]:
        put(s,n,"hand")
    return s,source,cycled


def cycle(s, card, side=None, mana_window=False):
    from app.rules.plan import Plan
    ability = next(a.index for a in Plan(s.state,"p1",s.cards,None).ch(card).abilities if any("cycling" in k for k in a.keywords))
    wait_priority(s,"p1")
    kwargs = {} if side is None else {"cost_choices":[{"component":20,"cards":[f"either:{side}"]}]}
    return act(s,"p1",type="activate_ability",card_id=card.id,ability=ability,sources=None if mana_window else [],**kwargs)


def test_canonical(cards):
    assert coverage.of_card_data(cards.resolve("New Perspectives")).level == "FULL"


def test_seven_hand_free_cost_discard_and_native_trigger_then_draw(cards):
    s,_,c = setup(cards)
    cycle(s,c)
    assert c.zone == "p1:graveyard"
    assert len(s.state.zones['p1:hand']) == 6
    assert s.state.zones.get('stack')
    answer(s)
    assert len(s.state.zones['p1:hand']) == 7
    assert s.state.players['p1'].life == 42
    roundtrip(s)


def test_six_hand_no_alternative_atomic(cards):
    s,_,c = setup(cards,count=6)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        cycle(s,c)
    assert s.state.model_dump_json()==before


def test_current_hand_rechecked_when_first_cycle_has_not_drawn(cards):
    s,_,c=setup(cards)
    second=put(s,'Krosan Tusker','hand')
    # Eight cards: cycling once leaves seven, twice leaves six before either draw.
    cycle(s,c)
    cycle(s,second)
    assert second.zone=='p1:graveyard'
    assert len(s.state.zones['p1:hand'])==6
    answer(s)
    assert len(s.state.zones['p1:hand'])>=8


def test_repeat_cycle_after_each_draw_remains_free(cards):
    s,_,c=setup(cards)
    cycle(s,c)
    answer(s)
    # Swap a filler for another canonical cycler while retaining exactly seven cards.
    filler=next(cid for cid in s.state.zones['p1:hand'] if s.state.cards[cid].name=='Forest')
    act(s,'p1',type='move',card_ids=[filler],to={'zone':'library','player':'p1'})
    second=put(s,'Krosan Tusker','hand')
    while len(s.state.zones['p1:hand']) < 7:
        cid=next(cid for cid in s.state.zones['p1:library'] if cid != second.id)
        act(s,'p1',type='move',card_ids=[cid],to={'zone':'hand','player':'p1'})
    assert len(s.state.zones['p1:hand']) == 7
    cycle(s,second)
    assert second.zone=='p1:graveyard'
    answer(s)
    roundtrip(s)


def test_multi_typecycling_chooses_forest_zero_cost(cards):
    s,_,c=setup(cards,'Valley Rannet')
    cycle(s,c)
    d=s.state.rules.decision
    assert d and len(d.options)==2
    forest=next(o.id for o in d.options if 'Forestcycling' in o.label)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[forest])
    assert c.zone=='p1:graveyard'
    answer(s)
    roundtrip(s)


def test_actual_cast_draws_three_on_native_entry(cards):
    s,source,_=setup(cards,count=6)
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'hand','player':'p1'})
    before=len(s.state.zones['p1:hand'])
    act(s,'p1',type='add_mana',player='p1',mana={'C':5,'U':1})
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    answer(s)
    assert source.zone=='p1:battlefield'
    assert len(s.state.zones['p1:hand'])==before+2


def test_may_pay_printed_cycling_cost_despite_alternative(cards):
    s,_,c=setup(cards)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    cycle(s,c,side=0)
    assert c.zone=='p1:graveyard'
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)


def test_actual_activation_tax_applies_to_free_alternative(cards):
    s,_,c=setup(cards)
    put(s,'Suppression Field','battlefield',pid='p2')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        cycle(s,c)
    assert s.state.model_dump_json()==before
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    cycle(s,c)
    assert c.zone=='p1:graveyard'
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)


def test_opponents_do_not_receive_alternative(cards):
    s,source,c=setup(cards)
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        cycle(s,c)
    assert s.state.model_dump_json()==before


def test_basic_landcycling_native_tutor_does_not_draw(cards):
    s,_,c=setup(cards,'Sylvan Reclamation')
    cycle(s,c)
    assert c.zone=='p1:graveyard'
    answer(s)
    assert len(s.state.zones['p1:hand'])==7
    assert sum(s.state.cards[cid].name in ['Forest','Plains','Island','Mountain','Swamp'] for cid in s.state.zones['p1:hand'])==6
    roundtrip(s)


def test_multi_typecycling_real_cold_choice(cards,tmp_path):
    import os
    import subprocess
    import sys
    s,_,c=setup(cards,'Valley Rannet')
    cycle(s,c)
    d=s.state.rules.decision
    assert d and d.resume['step']=='ability_cost'
    saved=tmp_path/'save.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
saved,database,cid=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p3')
d=s.state.rules.decision
assert d and d.resume['step']=='ability_cost'
option=next(o.id for o in d.options if 'Forestcycling' in o.label)
act(s,d.player,type='choose',decision_id=d.id,option_ids=[option])
assert s.state.cards[cid].zone=='p1:graveyard'
# The actual selected ability searches Forest, rather than Mountain or drawing.
for _ in range(20):
 d=s.state.rules.decision
 if d and d.resume.get('step')=='search':
  assert d.options
  assert all('Forest' in repo.resolve(s.state.cards[o.id].name)['type_line'] for o in d.options)
  break
 if d:
  act(s,d.player,type='choose',decision_id=d.id,option_ids=[d.options[0].id])
 elif s.state.zones.get('stack'):
  act(s,s.state.rules.priority,type='pass_priority')
 else:
  raise AssertionError('Expected actual Forest search')
else: raise AssertionError('Missing search')
answer(s)
assert len(s.state.zones['p1:hand'])==7
GameState.model_validate_json(s.state.model_dump_json())
'''
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),c.id],capture_output=True,text=True,env=os.environ.copy())
    assert run.returncode==0,run.stdout+run.stderr


def test_seven_to_six_before_draw_removes_next_free_alternative(cards):
    s,_,c=setup(cards,count=6)
    second=put(s,'Krosan Tusker','hand')
    assert len(s.state.zones['p1:hand'])==7
    cycle(s,c)
    assert len(s.state.zones['p1:hand'])==6
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        cycle(s,second)
    assert s.state.model_dump_json()==before
    assert second.zone=='p1:hand'
    answer(s)


@pytest.mark.parametrize("cold", [False, True])
def test_multi_alternative_stays_announced_when_mana_ability_discards_below_seven(cards, tmp_path, cold):
    s,_,c=setup(cards,'Valley Rannet')
    put(s,'Suppression Field','battlefield',pid='p2')
    familiar=put(s,'Skirge Familiar','battlefield')
    put(s,'Forest','battlefield')
    put(s,'Plains','battlefield')
    # Restore hand to seven after moving two fillers to battlefield.
    for cid in list(s.state.zones['p1:library'])[:2]:
        act(s,'p1',type='move',card_ids=[cid],to={'zone':'hand','player':'p1'})
    assert len(s.state.zones['p1:hand'])==7
    act(s,'p1',type='set_prefs',payment='self')
    cycle(s,c,mana_window=True)
    d=s.state.rules.decision
    assert d and d.resume['step']=='ability_cost'
    pick=next(o.id for o in d.options if o.label == 'Forestcycling {0}')
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[pick])
    d=s.state.rules.decision
    assert d and d.resume['step']=='pay_mana'
    discard=next(cid for cid in s.state.zones['p1:hand'] if cid!=c.id)
    act(s,'p1',type='activate_ability',card_id=familiar.id,ability=1,
        cost_choices=[{'component':0,'cards':[discard]}],sources=[])
    assert len(s.state.zones['p1:hand'])==6
    roundtrip(s)
    if cold:
        import os
        import subprocess
        import sys
        saved=tmp_path/'window.json'
        saved.write_text(s.state.model_dump_json())
        code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
saved,database,cid=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p3')
d=s.state.rules.decision
assert d and d.resume['step']=='pay_mana'
assert d.resume['payment_context']['cycling_menu72']
assert len(s.state.zones['p1:hand'])==6
act(s,'p1',type='add_mana',player='p1',mana={'C':1})
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
assert s.state.cards[cid].zone=='p1:graveyard'
answer(s)
GameState.model_validate_json(s.state.model_dump_json())
"""
        run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),c.id],capture_output=True,text=True,env=os.environ.copy())
        assert run.returncode==0,run.stdout+run.stderr
        return
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    d=s.state.rules.decision
    assert d and d.resume['step']=='pay_mana'
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
    assert c.zone=='p1:graveyard'
    answer(s)
    roundtrip(s)
