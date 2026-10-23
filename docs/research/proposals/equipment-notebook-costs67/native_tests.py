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
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Glamdring, Foe-hammer // Gleam of Death','Tamiyo, Compleated Sage']


@pytest.fixture
def cards(settings):
    base = {c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/equipment_notebook_costs67_cards.json').read_text())):
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


def test_glamdring_actual_equip_uses_current_power_and_never_colored_mana(cards):
    s = table(cards,['Glamdring, Foe-hammer // Gleam of Death','Grizzly Bears','Giant Growth','Choking Tethers'])
    equipment = put(s,NAMES[0],'battlefield')
    bearer = put(s,'Grizzly Bears','battlefield')
    spell = put(s,'Choking Tethers','hand')
    growth = put(s,'Giant Growth','hand')
    ready(s)
    index = next(a.index for a in Plan(s.state,'p1',cards,None).ch(equipment).abilities if 'equip' in a.keywords)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'G':1,'U':1})
    act(s,'p1',type='activate_ability',card_id=equipment.id,ability=index,targets=[bearer.id],sources=[])
    answer(s)
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bearer.id],sources=[])
    answer(s)
    assert Plan(s.state,'p1',cards,None).ch(bearer).pt[0] == 5
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[bearer.id],target_counts=[1],sources=[])
    answer(s)
    assert bearer.tapped
    assert not s.state.players['p1'].mana_units
    roundtrip(s)


@pytest.mark.parametrize('pay_life',[True,False])
def test_tamiyo_actual_compleated_cast_preserves_native_loyalty(cards,pay_life):
    s = table(cards,['Tamiyo, Compleated Sage'])
    source = put(s,'Tamiyo, Compleated Sage','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'G':1 if pay_life else 2,'U':1})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    answer(s)
    assert source.zone == 'p1:battlefield'
    assert source.counters['loyalty'] == (3 if pay_life else 5)
    assert s.state.players['p1'].life == (38 if pay_life else 40)
    roundtrip(s)


def test_tamiyo_plus_one_native_tap_and_skip_next_untap(cards):
    s = table(cards,['Tamiyo, Compleated Sage'],['Grizzly Bears'])
    source = put(s,'Tamiyo, Compleated Sage','hand')
    target = put(s,'Grizzly Bears','battlefield',pid='p2')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'G':2,'U':1})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    answer(s)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,targets=[target.id],target_counts=[1],sources=[])
    answer(s)
    assert target.tapped and source.counters['loyalty'] == 6
    to_phase(s,'main1',5)
    assert target.tapped
    to_phase(s,'main1',8)
    assert not target.tapped
    roundtrip(s)


def test_tamiyo_minus_x_exiles_actual_matching_grave_card_and_copies(cards):
    s = table(cards,['Tamiyo, Compleated Sage','Grizzly Bears'])
    source = put(s,'Tamiyo, Compleated Sage','hand')
    target = put(s,'Grizzly Bears','graveyard')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'G':2,'U':1})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    answer(s)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=2,x_value=1,targets=[target.id],sources=[])
    assert s.state.model_dump_json() == before
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2,x_value=2,targets=[target.id],sources=[])
    answer(s)
    assert target.zone == 'p1:exile' and source.counters['loyalty'] == 3
    made = [c for c in s.state.cards.values() if c.token and c.name == 'Grizzly Bears' and c.zone == 'p1:battlefield']
    assert len(made) == 1 and Plan(s.state,'p1',cards,None).ch(made[0]).pt == (2,2)
    roundtrip(s)


def test_tamiyo_minus_seven_produces_correct_named_native_token_with_both_abilities(cards):
    s = table(cards,['Tamiyo, Compleated Sage','Divination'],['Divination'])
    source = put(s,'Tamiyo, Compleated Sage','hand')
    spell = put(s,'Divination','hand')
    opposing_spell = put(s,'Divination','hand',pid='p2')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'G':2,'U':1})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    answer(s)
    act(s,'p1',type='counter',card_ids=[source.id],kind='loyalty',delta=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=3,sources=[])
    answer(s)
    assert source.zone == 'p1:graveyard'
    made = [c for c in s.state.cards.values() if c.token and c.zone == 'p1:battlefield']
    assert len(made) == 1 and made[0].name == "Tamiyo's Notebook"
    token = made[0]
    ch = Plan(s.state,'p1',cards,None).ch(token)
    assert 'Legendary' in ch.supertypes and 'Book' in ch.subtypes and not ch.colors
    act(s,'p1',type='add_mana',player='p1',mana={'U':1})
    hand_before = len(s.state.zones['p1:hand'])
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert len(s.state.zones['p1:hand']) == hand_before + 1 and not s.state.players['p1'].mana_units
    act(s,'p1',type='activate_ability',card_id=token.id,ability=1,sources=[])
    answer(s)
    assert token.tapped and len(s.state.zones['p1:hand']) == hand_before + 2
    to_phase(s,'main1',5)
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=opposing_spell.id,sources=[])
    assert s.state.model_dump_json() == before
    act(s,'p2',type='add_mana',player='p2',mana={'C':2})
    act(s,'p2',type='cast_spell',card_id=opposing_spell.id,sources=[])
    answer(s)
    assert opposing_spell.zone == 'p2:graveyard' and not s.state.players['p2'].mana_units
    roundtrip(s)


def test_glamdring_adventure_native_mills_filters_and_casts_artifact_from_exile(cards):
    s = table(cards,[NAMES[0],'Giant Growth','Lightning Bolt','Divination','Grizzly Bears'])
    source = put(s,NAMES[0],'hand')
    ready(s)
    picked = [next(c for c in s.state.cards.values() if c.name == n and c.owner == 'p1') for n in ['Giant Growth','Lightning Bolt','Divination','Grizzly Bears']]
    lands = [c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1'][:2]
    for c in reversed(picked+lands):
        act(s,'p1',type='move',card_ids=[c.id],to={'zone':'library','player':'p1'},position='top')
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'U':1})
    act(s,'p1',type='cast_spell',card_id=source.id,face=1,sources=[])
    answer(s)
    assert source.zone == 'p1:exile'
    assert all(c.zone == 'p1:hand' for c in picked[:3])
    assert all(c.zone == 'p1:graveyard' for c in [picked[3],*lands])
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='cast_spell',card_id=source.id,face=0,sources=[])
    answer(s)
    assert source.zone == 'p1:battlefield' and source.face == 0
    roundtrip(s)


def test_glamdring_discount_vanishes_after_actual_bearer_blink(cards):
    s = table(cards,[NAMES[0],'Grizzly Bears','Cloudshift','Divination'])
    equipment = put(s,NAMES[0],'battlefield')
    bearer = put(s,'Grizzly Bears','battlefield')
    blink = put(s,'Cloudshift','hand')
    spell = put(s,'Divination','hand')
    ready(s)
    index = next(a.index for a in Plan(s.state,'p1',cards,None).ch(equipment).abilities if 'equip' in a.keywords)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'W':1,'U':1})
    act(s,'p1',type='activate_ability',card_id=equipment.id,ability=index,targets=[bearer.id],sources=[])
    answer(s)
    act(s,'p1',type='cast_spell',card_id=blink.id,targets=[bearer.id],sources=[])
    answer(s)
    assert equipment.attached_to is None
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    assert s.state.model_dump_json() == before
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert spell.zone == 'p1:graveyard' and not s.state.players['p1'].mana_units
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_genuine_cold_native_attached_value_and_named_token(cards,tmp_path,name):
    import subprocess
    import sys

    from app.rules import equipment_notebook_costs67
    if name == NAMES[0]:
        s = table(cards,[name,'Grizzly Bears','Giant Growth','Choking Tethers'])
        source = put(s,name,'battlefield')
        bearer = put(s,'Grizzly Bears','battlefield')
        spell = put(s,'Choking Tethers','hand')
        growth = put(s,'Giant Growth','hand')
        ready(s)
        index = next(a.index for a in Plan(s.state,'p1',cards,None).ch(source).abilities if 'equip' in a.keywords)
        act(s,'p1',type='add_mana',player='p1',mana={'C':2,'G':1,'U':1})
        act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=[bearer.id],sources=[])
        answer(s)
        act(s,'p1',type='cast_spell',card_id=growth.id,targets=[bearer.id],sources=[])
        answer(s)
        action = dict(type='cast_spell',card_id=spell.id,targets=[bearer.id],target_counts=[1],sources=[])
        target = bearer.id
    else:
        s = table(cards,[name,'Divination'])
        source = put(s,name,'hand')
        spell = put(s,'Divination','hand')
        ready(s)
        act(s,'p1',type='add_mana',player='p1',mana={'C':2,'G':2,'U':1})
        act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
        answer(s)
        act(s,'p1',type='counter',card_ids=[source.id],kind='loyalty',delta=2)
        action = dict(type='activate_ability',card_id=source.id,ability=3,sources=[])
        target = None
    saved = tmp_path/'saved.json'
    saved.write_text(s.state.model_dump_json())
    spec = tmp_path/'spec.json'
    spec.write_text(json.dumps(dict(name=name,target=target,action=action,spell=spell.id)))
    code = '''
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spec=json.loads(Path(sys.argv[3]).read_text())
act(s,'p1',**spec['action'])
answer(s)
if spec['target']:
 assert s.state.cards[spec['target']].tapped
else:
 token=next(c for c in s.state.cards.values() if c.token and c.zone=='p1:battlefield')
 assert token.name=="Tamiyo's Notebook"
 act(s,'p1',type='add_mana',player='p1',mana={'U':1})
 act(s,'p1',type='cast_spell',card_id=spec['spell'],sources=[])
 answer(s)
 act(s,'p1',type='activate_ability',card_id=token.id,ability=1,sources=[])
 answer(s)
 assert token.tapped
assert not s.state.players['p1'].mana_units
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),str(spec)],cwd=Path(equipment_notebook_costs67.__file__).resolve().parents[2],capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr
