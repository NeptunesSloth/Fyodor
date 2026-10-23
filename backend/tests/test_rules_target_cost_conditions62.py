"""Target-dependent native ability and Aura costs are locked after announcing targets."""
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
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Ghostfire Blade', 'Raft Security Officer', 'Strong Back', 'Kopala, Warden of Waves']


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/target_cost_conditions62_cards.json').read_text())):
        base[c['name']] = card(c['name'], number=str(i), **{k:v for k,v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ready(s):
    for pid in ('p1', 'p2', 'p3'):
        act(s, pid, type='set_prefs', hold_priority=True)
    to_phase(s, 'main1', 4)


@pytest.mark.parametrize('name', NAMES)
def test_whole_definitions(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('creature,amount', [('Darksteel Myr',1), ('Llanowar Elves',3)])
def test_ghostfire_exact_announced_target_controls_price(cards, creature, amount):
    s = table(cards, ['Ghostfire Blade', creature])
    equipment = put(s, 'Ghostfire Blade', 'battlefield')
    target = put(s, creature, 'battlefield')
    ready(s)
    index = next(a.index for a in Plan(s.state,'p1',cards,None).ch(equipment).abilities if 'equip' in a.keywords)
    act(s,'p1',type='add_mana',player='p1',mana={'C':amount})
    act(s,'p1',type='activate_ability',card_id=equipment.id,ability=index,targets=[target.id],sources=[])
    answer(s)
    assert equipment.attached_to == target.id
    assert not s.state.players['p1'].mana_units
    assert Plan(s.state,'p1',cards,None).ch(target).pt == ((2,3) if creature == 'Darksteel Myr' else (3,3))
    roundtrip(s)


@pytest.mark.parametrize('target_name,amount', [('Grizzly Bears',1), ('Air Elemental',2)])
def test_raft_target_actual_power_controls_price(cards, target_name, amount):
    s = table(cards, ['Raft Security Officer'], [target_name])
    source = put(s,'Raft Security Officer','battlefield')
    target = put(s,target_name,'battlefield',pid='p2')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':amount})
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[target.id],sources=[])
    answer(s)
    assert source.tapped and target.tapped and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_raft_cannot_lock_preview_discount_for_large_actual_target(cards):
    s = table(cards,['Raft Security Officer'],['Grizzly Bears','Air Elemental'])
    source = put(s,'Raft Security Officer','battlefield')
    put(s,'Grizzly Bears','battlefield',pid='p2')
    large = put(s,'Air Elemental','battlefield',pid='p2')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[large.id],sources=[])
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize('target_name,amount',[('Merfolk of the Pearl Trident',2),('Grizzly Bears',0)])
def test_kopala_opponent_activated_target_tax(cards,target_name,amount):
    s = table(cards,['Kopala, Warden of Waves',target_name],['Prodigal Pyromancer'])
    put(s,'Kopala, Warden of Waves','battlefield')
    target = put(s,target_name,'battlefield')
    source = put(s,'Prodigal Pyromancer','battlefield',pid='p2')
    ready(s)
    wait_priority(s,'p2')
    if amount:
        act(s,'p2',type='add_mana',player='p2',mana={'C':amount})
    act(s,'p2',type='activate_ability',card_id=source.id,ability=0,targets=[target.id],sources=[])
    answer(s)
    assert target.damage == 1 if target_name == 'Grizzly Bears' else target.zone == 'p1:graveyard'
    assert not s.state.players['p2'].mana_units
    roundtrip(s)


def strong_back_setup(cards):
    s = table(cards,['Strong Back','Grizzly Bears','Llanowar Elves','Silver-Inlaid Dagger','Pacifism'])
    bear = put(s,'Grizzly Bears','battlefield')
    elf = put(s,'Llanowar Elves','battlefield')
    equipment = put(s,'Silver-Inlaid Dagger','battlefield')
    aura = put(s,'Strong Back','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'G':1})
    act(s,'p1',type='cast_spell',card_id=aura.id,targets=[bear.id],sources=[])
    answer(s)
    assert aura.attached_to == bear.id
    assert Plan(s.state,'p1',cards,None).ch(bear).pt == (4,4)
    return s,bear,elf,equipment


@pytest.mark.parametrize('enchanted,amount',[(True,0),(False,2)])
def test_strong_back_equipment_discount_only_actual_enchanted_creature(cards,enchanted,amount):
    s,bear,elf,equipment = strong_back_setup(cards)
    target = bear if enchanted else elf
    index = next(a.index for a in Plan(s.state,'p1',cards,None).ch(equipment).abilities if 'equip' in a.keywords)
    if amount:
        act(s,'p1',type='add_mana',player='p1',mana={'C':amount})
    act(s,'p1',type='activate_ability',card_id=equipment.id,ability=index,targets=[target.id],sources=[])
    answer(s)
    assert equipment.attached_to == target.id and not s.state.players['p1'].mana_units
    assert Plan(s.state,'p1',cards,None).ch(bear).pt == ((8,6) if enchanted else (4,4))
    roundtrip(s)


@pytest.mark.parametrize('enchanted,amount',[(True,0),(False,1)])
def test_strong_back_aura_reduction_preserves_colored_cost_and_actual_target(cards,enchanted,amount):
    s,bear,elf,_ = strong_back_setup(cards)
    target = bear if enchanted else elf
    spell = put(s,'Pacifism','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':amount,'W':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[target.id],sources=[])
    answer(s)
    assert spell.attached_to == target.id and not s.state.players['p1'].mana_units
    assert Plan(s.state,'p1',cards,None).ch(bear).pt == ((6,6) if enchanted else (4,4))
    roundtrip(s)


def test_kopala_does_not_tax_its_controllers_own_activation(cards):
    s = table(cards,['Kopala, Warden of Waves','Merfolk of the Pearl Trident','Prodigal Pyromancer'])
    put(s,'Kopala, Warden of Waves','battlefield')
    target = put(s,'Merfolk of the Pearl Trident','battlefield')
    source = put(s,'Prodigal Pyromancer','battlefield')
    ready(s)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[target.id],sources=[])
    answer(s)
    assert target.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_genuine_cold_target_pricing(cards,tmp_path,name):
    import subprocess
    import sys

    from app.rules import target_cost_conditions62
    pid = 'p1'
    if name == 'Strong Back':
        s,bear,_,_ = strong_back_setup(cards)
        target = bear
        source = put(s,'Pacifism','hand')
        act(s,'p1',type='add_mana',player='p1',mana={'W':1})
        action = dict(type='cast_spell',card_id=source.id,targets=[target.id],sources=[])
    elif name == 'Ghostfire Blade':
        s = table(cards,['Ghostfire Blade','Darksteel Myr'])
        source = put(s,'Ghostfire Blade','battlefield')
        target = put(s,'Darksteel Myr','battlefield')
        ready(s)
        index = next(a.index for a in Plan(s.state,'p1',cards,None).ch(source).abilities if 'equip' in a.keywords)
        act(s,'p1',type='add_mana',player='p1',mana={'C':1})
        action = dict(type='activate_ability',card_id=source.id,ability=index,targets=[target.id],sources=[])
    elif name == 'Raft Security Officer':
        s = table(cards,[name],['Grizzly Bears'])
        source = put(s,name,'battlefield')
        target = put(s,'Grizzly Bears','battlefield',pid='p2')
        ready(s)
        act(s,'p1',type='add_mana',player='p1',mana={'C':1})
        action = dict(type='activate_ability',card_id=source.id,ability=0,targets=[target.id],sources=[])
    else:
        s = table(cards,[name,'Merfolk of the Pearl Trident'],['Prodigal Pyromancer'])
        put(s,name,'battlefield')
        target = put(s,'Merfolk of the Pearl Trident','battlefield')
        source = put(s,'Prodigal Pyromancer','battlefield',pid='p2')
        ready(s)
        wait_priority(s,'p2')
        pid = 'p2'
        act(s,pid,type='add_mana',player=pid,mana={'C':2})
        action = dict(type='activate_ability',card_id=source.id,ability=0,targets=[target.id],sources=[])
    saved = tmp_path/'saved.json'
    saved.write_text(s.state.model_dump_json())
    spec = tmp_path/'spec.json'
    spec.write_text(json.dumps(dict(name=name,pid=pid,source=source.id,target=target.id,action=action)))
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
act(s,spec['pid'],**spec['action'])
answer(s)
source,target=s.state.cards[spec['source']],s.state.cards[spec['target']]
if spec['name'] in ['Strong Back','Ghostfire Blade']:assert source.attached_to==target.id
elif spec['name']=='Raft Security Officer':assert target.tapped and source.tapped
else:assert target.zone=='p1:graveyard'
assert not s.state.players[spec['pid']].mana_units
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),str(spec)],
                            cwd=Path(target_cost_conditions62.__file__).resolve().parents[2],capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr


def test_ghostfire_cannot_apply_colorless_preview_to_colored_target(cards):
    s = table(cards,['Ghostfire Blade','Llanowar Elves','Darksteel Myr'])
    source = put(s,'Ghostfire Blade','battlefield')
    target = put(s,'Llanowar Elves','battlefield')
    put(s,'Darksteel Myr','battlefield')
    ready(s)
    index = next(a.index for a in Plan(s.state,'p1',cards,None).ch(source).abilities if 'equip' in a.keywords)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=[target.id],sources=[])
    assert s.state.model_dump_json() == before


def test_kopala_actual_merfolk_target_tax_cannot_be_skipped(cards):
    s = table(cards,['Kopala, Warden of Waves','Merfolk of the Pearl Trident'],['Prodigal Pyromancer'])
    put(s,'Kopala, Warden of Waves','battlefield')
    source = put(s,'Prodigal Pyromancer','battlefield',pid='p2')
    target = put(s,'Merfolk of the Pearl Trident','battlefield')
    ready(s)
    wait_priority(s,'p2')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='activate_ability',card_id=source.id,ability=0,targets=[target.id],sources=[])
    assert s.state.model_dump_json() == before


def test_strong_back_generic_reduction_cannot_pay_colored_symbol(cards):
    s,bear,_,_ = strong_back_setup(cards)
    spell = put(s,'Pacifism','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,targets=[bear.id],sources=[])
    assert s.state.model_dump_json() == before
