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

NAMES = ["Belt of Giant Strength"]
DATA = json.loads((Path(__file__).parent / "fixtures/target_power_costs74_cards.json").read_text())


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


def setup(cards, name="Grizzly Bears"):
    ns = [c["name"] for c in DATA]
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    source = put(s, "Belt of Giant Strength", "battlefield")
    host = put(s, name, "battlefield")
    return s,source,host


def equip(s,source,host,n):
    from app.rules.plan import Plan
    if n:
        act(s,'p1',type='add_mana',player='p1',mana={'C':n})
    wait_priority(s,'p1')
    index=next(a.index for a in Plan(s.state,'p1',s.cards,None).ch(source).abilities if 'equip' in a.keywords)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=[host.id],sources=[])


def test_canonical(cards):
    assert coverage.of_card_data(cards.resolve("Belt of Giant Strength")).level == "FULL"


def test_native_current_target_power_reduces_actual_equip_then_base_ten_applies(cards):
    from app.rules.plan import Plan
    s,source,host=setup(cards)
    equip(s,source,host,8)
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert source.attached_to==host.id
    assert Plan(s.state,'p1',cards,None).ch(host).pt==(10,10)
    equip(s,source,host,0)
    answer(s)
    assert source.attached_to==host.id
    roundtrip(s)


def test_zero_power_target_still_requires_all_ten_generic(cards):
    s,source,host=setup(cards,'Ornithopter')
    equip(s,source,host,10)
    answer(s)
    assert source.attached_to==host.id


def test_current_power_above_ten_floors_cost_at_zero(cards):
    s,source,host=setup(cards,'Phyrexian Dreadnought')
    # Fixture move avoids its unrelated ETB; the real native 12-power characteristic sets the equip price.
    equip(s,source,host,0)
    answer(s)
    assert source.attached_to==host.id


def test_unaffordable_selected_low_power_target_cannot_use_another_high_power_target(cards):
    s,source,host=setup(cards,'Ornithopter')
    put(s,'Phyrexian Dreadnought','battlefield')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        equip(s,source,host,0)
    assert s.state.model_dump_json()==before


def test_current_layered_power_sets_price_and_belt_preserves_growth_modifier(cards):
    from app.rules.plan import Plan
    s,source,host=setup(cards)
    growth=put(s,'Giant Growth','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'G':1})
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[host.id],sources=[])
    answer(s)
    assert Plan(s.state,'p1',cards,None).ch(host).pt==(5,5)
    equip(s,source,host,5)
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert Plan(s.state,'p1',cards,None).ch(host).pt==(13,13)
    roundtrip(s)


def test_actual_activation_tax_is_added_before_target_power_reduction(cards):
    s,source,host=setup(cards)
    put(s,'Suppression Field','battlefield',pid='p2')
    equip(s,source,host,10)
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert source.attached_to==host.id


def test_equipping_new_small_target_does_not_use_current_equipped_host_power(cards):
    s,source,host=setup(cards,'Phyrexian Dreadnought')
    equip(s,source,host,0)
    answer(s)
    small=put(s,'Ornithopter','battlefield')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        equip(s,source,small,0)
    assert s.state.model_dump_json()==before
    equip(s,source,small,10)
    answer(s)
    assert source.attached_to==small.id


def test_real_cold_actual_equip_stack_restores_attachment_and_base_power(cards,tmp_path):
    import os
    import subprocess
    import sys
    s,source,host=setup(cards)
    equip(s,source,host,8)
    assert source.attached_to is None
    saved=tmp_path/'save.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_activated_copy_family import answer
saved,database,source,host=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p3')
assert s.state.cards[source].attached_to is None
assert s.state.zones.get('stack')
answer(s)
assert s.state.cards[source].attached_to==host
assert Plan(s.state,'p1',repo,None).ch(s.state.cards[host]).pt==(10,10)
GameState.model_validate_json(s.state.model_dump_json())
'''
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,host.id],capture_output=True,text=True,env=os.environ.copy())
    assert run.returncode==0,run.stdout+run.stderr


def test_negative_target_power_is_zero_reduction_not_extra_cost(cards):
    from app.rules.plan import Plan
    s,source,host=setup(cards)
    shrink=put(s,'Downsize','hand',pid='p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=shrink.id,targets=[host.id],sources=[])
    answer(s)
    assert Plan(s.state,'p1',cards,None).ch(host).pt==(-2,2)
    equip(s,source,host,10)
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert source.attached_to==host.id


def test_actual_mana_life_payment_changes_target_power_but_total_cost_stays_locked(cards):
    from app.rules.plan import Plan
    s,source,_=setup(cards)
    act(s,'p1',type='set_life',player='p1',value=6)
    host=put(s,"Death's Shadow",'battlefield')
    assert Plan(s.state,'p1',cards,None).ch(host).pt==(7,7)
    familiar=put(s,'Blood Celebrant','battlefield')
    put(s,'Swamp','battlefield')
    put(s,'Forest','battlefield')
    put(s,'Island','battlefield')
    act(s,'p1',type='set_prefs',payment='self')
    wait_priority(s,'p1')
    index=next(a.index for a in Plan(s.state,'p1',cards,None).ch(source).abilities if 'equip' in a.keywords)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=[host.id])
    d=s.state.rules.decision
    assert d and d.resume['step']=='pay_mana' and d.resume['cost']=='{3}'
    act(s,'p1',type='add_mana',player='p1',mana={'B':1})
    act(s,'p1',type='activate_ability',card_id=familiar.id,ability=0,sources=[])
    d=s.state.rules.decision
    if d and d.resume['step']!='pay_mana':
        act(s,d.player,type='choose',decision_id=d.id,option_ids=['B'])
    assert s.state.players['p1'].life==5
    assert Plan(s.state,'p1',cards,None).ch(host).pt==(8,8)
    roundtrip(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    d=s.state.rules.decision
    assert d and d.resume['step']=='pay_mana' and d.resume['cost']=='{3}'
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert source.attached_to==host.id
    roundtrip(s)
