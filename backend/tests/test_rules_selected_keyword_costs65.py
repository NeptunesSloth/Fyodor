"""Selected dash and actual controller-turn equip costs retain native keyword rules."""
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
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_suspend import until
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Warbringer','Nahiri, Storm of Stone']


@pytest.fixture
def cards(settings):
    base = {c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/selected_keyword_costs65_cards.json').read_text())):
        base[c['name']] = card(c['name'],number=str(i),**{k:v for k,v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ready(s):
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True,response='on')
    to_phase(s,'main1',4)


@pytest.mark.parametrize('name',NAMES)
def test_whole_definitions(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('dash,amount',[(False,2),(True,1)])
def test_warbringer_applies_to_actual_selected_dash_not_regular_cast(cards,dash,amount):
    s = table(cards,['Warbringer','Mardu Strike Leader'])
    put(s,'Warbringer','battlefield')
    spell = put(s,'Mardu Strike Leader','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':amount,'B':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,dash=dash,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    assert ('haste' in Plan(s.state,'p1',cards,None).ch(spell).keywords) == dash
    if dash:
        until(s,lambda s:s.state.cards[spell.id].zone != 'p1:battlefield')
        assert spell.zone == 'p1:hand'
    roundtrip(s)


def test_warbringer_does_not_discount_itself_cast_from_hand(cards):
    s = table(cards,['Warbringer'])
    spell = put(s,'Warbringer','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'R':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and 'haste' in Plan(s.state,'p1',cards,None).ch(spell).keywords
    assert not s.state.players['p1'].mana_units
    until(s,lambda s:s.state.cards[spell.id].zone != 'p1:battlefield')
    assert spell.zone == 'p1:hand'
    roundtrip(s)


def test_warbringer_multiple_native_copy_sources_combine_generic_discount(cards):
    s = table(cards,['Warbringer','Cackling Counterpart','Mardu Strike Leader'])
    source = put(s,'Warbringer','battlefield')
    copy = put(s,'Cackling Counterpart','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'U':2})
    act(s,'p1',type='cast_spell',card_id=copy.id,targets=[source.id],sources=[])
    answer(s)
    warbringers = [c for c in s.state.cards.values() if c.zone.endswith(':battlefield') and Plan(s.state,'p1',cards,None).ch(c).name == 'Warbringer']
    assert len(warbringers) == 2
    spell = put(s,'Mardu Strike Leader','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'B':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_warbringer_generic_reduction_does_not_pay_dash_colored_symbol(cards):
    s = table(cards,['Warbringer','Mardu Strike Leader'])
    put(s,'Warbringer','battlefield')
    spell = put(s,'Mardu Strike Leader','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[])
    assert s.state.model_dump_json() == before


def nahiri_scene(cards):
    s = table(cards,['Nahiri, Storm of Stone','Silver-Inlaid Dagger','Merfolk of the Pearl Trident','Leonin Shikari'],['Merfolk of the Pearl Trident'])
    own = put(s,'Merfolk of the Pearl Trident','battlefield')
    enemy = put(s,'Merfolk of the Pearl Trident','battlefield',pid='p2')
    equipment = put(s,'Silver-Inlaid Dagger','battlefield')
    put(s,'Leonin Shikari','battlefield')
    source = put(s,'Nahiri, Storm of Stone','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'R':2})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    answer(s)
    assert source.counters.get('loyalty') == 6
    return s,source,own,enemy,equipment


@pytest.mark.parametrize('own_turn,amount',[(True,1),(False,2)])
def test_nahiri_first_strike_and_equip_price_follow_controller_turn(cards,own_turn,amount):
    s,_,own,enemy,equipment = nahiri_scene(cards)
    if not own_turn:
        to_phase(s,'main1',5)
        wait_priority(s,'p1')
    view = Plan(s.state,'p1',cards,None)
    assert ('first strike' in view.ch(own).keywords) == own_turn
    assert 'first strike' not in view.ch(enemy).keywords
    index = next(a.index for a in view.ch(equipment).abilities if 'equip' in a.keywords)
    act(s,'p1',type='add_mana',player='p1',mana={'C':amount})
    act(s,'p1',type='activate_ability',card_id=equipment.id,ability=index,targets=[own.id],sources=[])
    answer(s)
    assert equipment.attached_to == own.id and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_nahiri_actual_negative_x_loyalty_hits_only_tapped_target(cards):
    s = table(cards,['Nahiri, Storm of Stone'],['Llanowar Elves'])
    target = put(s,'Llanowar Elves','battlefield',pid='p2')
    source = put(s,'Nahiri, Storm of Stone','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'R':2})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    answer(s)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1,x_value=1,targets=[target.id],sources=[])
    assert s.state.model_dump_json() == before
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=target.id,ability=0,sources=[])
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,x_value=1,targets=[target.id],sources=[])
    answer(s)
    assert source.counters.get('loyalty') == 5 and target.zone == 'p2:graveyard'
    roundtrip(s)


def test_warbringer_dash_commander_cost_reduction_applies_after_commander_tax(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    decks = [deck(cards,'Zurgo Bellstriker',[(1,'Warbringer'),(20,'Mountain')]),
             deck(cards,"Atraxa, Praetors' Voice",[(1,'Lightning Bolt'),(20,'Island')]),
             deck(cards,"Atraxa, Praetors' Voice",[(20,'Island')])]
    s = GameSession(enable(new_game([PlayerSetup(n,cards=d) for n,d in zip(('A','B','C'),decks,strict=True)],shuffle=False)),cards=cards)
    act(s,'p1',type='pass_priority')
    put(s,'Warbringer','battlefield')
    spell = next(c for c in s.state.cards.values() if c.name == 'Zurgo Bellstriker')
    bolt = put(s,'Lightning Bolt','hand',pid='p2')
    ready(s)
    assert spell.zone == 'p1:command'
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'R':1})
    act(s,'p2',type='cast_spell',card_id=bolt.id,targets=[spell.id],sources=[])
    answer(s)
    assert spell.zone == 'p1:command'
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'R':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    assert s.state.players['p1'].commander_casts[spell.commander_key] == 2
    roundtrip(s)


def test_warbringer_dash_from_native_graveyard_permission(cards):
    s = table(cards,['Warbringer','Muldrotha, the Gravetide','Mardu Strike Leader'])
    put(s,'Warbringer','battlefield')
    put(s,'Muldrotha, the Gravetide','battlefield')
    spell = put(s,'Mardu Strike Leader','graveyard')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'B':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and 'haste' in Plan(s.state,'p1',cards,None).ch(spell).keywords
    assert not s.state.players['p1'].mana_units
    until(s,lambda s:s.state.cards[spell.id].zone != 'p1:battlefield')
    assert spell.zone == 'p1:hand'
    roundtrip(s)


def test_dash_does_not_itself_grant_permission_to_cast_from_graveyard(cards):
    s = table(cards,['Warbringer','Mardu Strike Leader'])
    put(s,'Warbringer','battlefield')
    spell = put(s,'Mardu Strike Leader','graveyard')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'B':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[])
    assert s.state.model_dump_json() == before


def test_dash_cannot_replace_escape_cost_required_by_selected_permission(cards):
    s = table(cards,['Warbringer','Underworld Breach','Mardu Strike Leader'])
    put(s,'Warbringer','battlefield')
    spell = put(s,'Mardu Strike Leader','graveyard')
    forest_ids = [c.id for c in s.state.cards.values() if c.name == 'Forest'][:3]
    act(s,'p1',type='move',card_ids=forest_ids,to={'zone':'graveyard','player':'p1'})
    ready(s)
    put(s,'Underworld Breach','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'B':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError,match='alternative'):
        act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[])
    assert s.state.model_dump_json() == before


def test_dash_reduction_follows_generic_sphere_increase(cards):
    s = table(cards,['Warbringer','Sphere of Resistance','Lightning Berserker'])
    put(s,'Warbringer','battlefield')
    put(s,'Sphere of Resistance','battlefield')
    spell = put(s,'Lightning Berserker','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units


def test_opponent_warbringer_does_not_reduce_your_dash(cards):
    s = table(cards,['Mardu Strike Leader'],['Warbringer'])
    put(s,'Warbringer','battlefield',pid='p2')
    spell = put(s,'Mardu Strike Leader','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'B':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[])
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize('name',NAMES)
def test_genuine_cold_selected_cost(cards,tmp_path,name):
    import subprocess
    import sys

    from app.rules import selected_keyword_costs65
    if name == 'Warbringer':
        s = table(cards,[name,'Mardu Strike Leader'])
        put(s,name,'battlefield')
        target = put(s,'Mardu Strike Leader','hand')
        ready(s)
        act(s,'p1',type='add_mana',player='p1',mana={'C':1,'B':1})
        action = dict(type='cast_spell',card_id=target.id,dash=True,sources=[])
        equipment_id = None
    else:
        s = table(cards,[name,'Silver-Inlaid Dagger','Merfolk of the Pearl Trident'])
        source = put(s,name,'hand')
        equipment = put(s,'Silver-Inlaid Dagger','battlefield')
        target = put(s,'Merfolk of the Pearl Trident','battlefield')
        ready(s)
        act(s,'p1',type='add_mana',player='p1',mana={'C':2,'R':2})
        act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
        answer(s)
        act(s,'p1',type='add_mana',player='p1',mana={'C':1})
        index = next(a.index for a in Plan(s.state,'p1',cards,None).ch(equipment).abilities if 'equip' in a.keywords)
        action = dict(type='activate_ability',card_id=equipment.id,ability=index,targets=[target.id],sources=[])
        equipment_id = equipment.id
    saved = tmp_path/'saved.json'
    saved.write_text(s.state.model_dump_json())
    spec = tmp_path/'spec.json'
    spec.write_text(json.dumps(dict(name=name,target=target.id,equipment=equipment_id,action=action)))
    code = '''
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_suspend import until
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spec=json.loads(Path(sys.argv[3]).read_text())
act(s,'p1',**spec['action'])
answer(s)
assert not s.state.players['p1'].mana_units
c=s.state.cards[spec['target']]
if spec['name']=='Warbringer':
 assert c.zone=='p1:battlefield' and 'haste' in Plan(s.state,'p1',repo,None).ch(c).keywords
 until(s,lambda s:s.state.cards[c.id].zone!='p1:battlefield')
 assert c.zone=='p1:hand'
else:
 assert s.state.cards[spec['equipment']].attached_to==c.id
 assert 'first strike' in Plan(s.state,'p1',repo,None).ch(c).keywords
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),str(spec)],cwd=Path(selected_keyword_costs65.__file__).resolve().parents[2],capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr


@pytest.mark.parametrize('flags',[{'evoke':True},{'face_down':True},{'awaken':True},{'alt_cost':'bogus'}])
def test_dash_rejects_other_selected_alternative_flags_atomically(cards,flags):
    s = table(cards,['Warbringer','Mardu Strike Leader'])
    put(s,'Warbringer','battlefield')
    spell = put(s,'Mardu Strike Leader','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':10,'B':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,dash=True,sources=[],**flags)
    assert s.state.model_dump_json() == before
