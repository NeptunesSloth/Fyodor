"""Current source characteristics/typed choices and actual distinct creature targets determine price."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Mistform Warchief','Seal of the Guildpact','Battlefield Thaumaturge']


@pytest.fixture
def cards(settings):
    base = {c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/source_spell_discounts64_cards.json').read_text())):
        base[c['name']] = card(c['name'],number=str(i),**{k:v for k,v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ready(s):
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True)
    to_phase(s,'main1',4)


@pytest.mark.parametrize('name',NAMES)
def test_complete_definitions(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_mistform_original_current_shared_type_discount(cards):
    s = table(cards,['Mistform Warchief','Phantom Warrior'])
    put(s,'Mistform Warchief','battlefield')
    spell = put(s,'Phantom Warrior','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'U':2})
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_mistform_native_choice_changes_shared_type_discount(cards):
    s = table(cards,['Mistform Warchief','Elvish Visionary'])
    source = put(s,'Mistform Warchief','battlefield')
    spell = put(s,'Elvish Visionary','hand')
    ready(s)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            assert 'Elf' in {o.id for o in d.options}
            act(s,d.player,type='choose',decision_id=d.id,option_ids=['Elf'])
            break
        act(s,s.state.rules.priority,type='pass_priority')
    answer(s)
    assert Plan(s.state,'p1',cards,None).ch(source).subtypes == {'Elf'}
    act(s,'p1',type='add_mana',player='p1',mana={'G':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    roundtrip(s)


def seal_scene(cards, names=()):
    s = table(cards,['Seal of the Guildpact',*names])
    source = put(s,'Seal of the Guildpact','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':5})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    for color in ('Blue','Green'):
        for _ in range(30):
            d = s.state.rules.decision
            if d is not None:
                assert color in {o.id for o in d.options}
                act(s,d.player,type='choose',decision_id=d.id,option_ids=[color])
                break
            act(s,s.state.rules.priority,type='pass_priority')
    answer(s)
    assert source.choices == {'Chosen color':'Blue','Chosen second color':'Green'}
    return s,source


@pytest.mark.parametrize('name,mana',[('Assault Zeppelid',{'G':1,'U':1}),('Air Elemental',{'C':2,'U':2}),('Hill Giant',{'C':3,'R':1})])
def test_seal_actual_two_entry_choices_intersect_only_current_spell_colors(cards,name,mana):
    s,_ = seal_scene(cards,[name])
    spell = put(s,name,'hand')
    act(s,'p1',type='add_mana',player='p1',mana=mana)
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_thaumaturge_four_creature_native_targets_and_hint(cards):
    s = table(cards,['Battlefield Thaumaturge','Choking Tethers','Grizzly Bears','Llanowar Elves'],['Hill Giant'])
    source = put(s,'Battlefield Thaumaturge','battlefield')
    targets = [source,put(s,'Grizzly Bears','battlefield'),put(s,'Llanowar Elves','battlefield'),put(s,'Hill Giant','battlefield',pid='p2')]
    spell = put(s,'Choking Tethers','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'U':1})
    assert casting.castable(s.state,'p1',spell,cards)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[c.id for c in targets],target_counts=[4],sources=[])
    answer(s)
    assert all(c.tapped for c in targets)
    assert 'hexproof' in Plan(s.state,'p1',cards,None).ch(source).keywords
    assert not s.state.players['p1'].mana_units
    roundtrip(s)


@pytest.mark.parametrize('distinct',[False,True])
def test_thaumaturge_counts_distinct_creatures_not_target_slot_mentions(cards,distinct):
    s = table(cards,['Battlefield Thaumaturge','Common Bond','Sphere of Resistance','Grizzly Bears','Llanowar Elves'])
    put(s,'Battlefield Thaumaturge','battlefield')
    put(s,'Sphere of Resistance','battlefield')
    bear = put(s,'Grizzly Bears','battlefield')
    elf = put(s,'Llanowar Elves','battlefield')
    spell = put(s,'Common Bond','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'G':1,'W':1,**({} if distinct else {'C':1})})
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[bear.id,elf.id if distinct else bear.id],target_counts=[1,1],sources=[])
    answer(s)
    assert bear.counters.get('+1/+1') == (1 if distinct else 2)
    assert elf.counters.get('+1/+1',0) == (1 if distinct else 0)
    assert not s.state.players['p1'].mana_units
    roundtrip(s)


def pick(s,wanted):
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            assert wanted in {o.id for o in d.options}, d
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[wanted])
            return
        act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('No expected decision')


@pytest.mark.parametrize('name,mana',[('Air Elemental',{'C':2,'U':2}),('Hill Giant',{'C':2,'R':1})])
def test_seal_actual_copy_has_own_entry_choices_not_originals(cards,name,mana):
    s,original = seal_scene(cards,['Sculpting Steel',name])
    copied = put(s,'Sculpting Steel','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':3})
    act(s,'p1',type='cast_spell',card_id=copied.id,sources=[])
    pick(s,original.id)
    pick(s,'Red')
    pick(s,'White')
    answer(s)
    assert copied.choices == {'Chosen color':'Red','Chosen second color':'White'}
    spell = put(s,name,'hand')
    act(s,'p1',type='add_mana',player='p1',mana=mana)
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_seal_later_native_copy_does_not_borrow_entry_colors(cards):
    s,source = seal_scene(cards,['Mirage Mirror','Air Elemental'])
    mirror = put(s,'Mirage Mirror','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='activate_ability',card_id=mirror.id,ability=0,targets=[source.id],sources=[])
    answer(s)
    assert Plan(s.state,'p1',cards,None).ch(mirror).name == 'Seal of the Guildpact'
    assert not mirror.choices
    spell = put(s,'Air Elemental','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'U':2})
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_seal_unknown_legacy_blocks_only_automatic_colored_cast_until_source_manual(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s,source = seal_scene(cards,['Hill Giant','Sol Ring'])
    spell = put(s,'Hill Giant','hand')
    colorless = put(s,'Sol Ring','hand')
    raw = s.state.model_dump(mode='json')
    raw['rules'].pop('chosen_color_pairs')
    s = GameSession(GameState.model_validate(raw),cards=cards)
    spell = s.state.cards[spell.id]
    colorless = s.state.cards[colorless.id]
    act(s,'p1',type='add_mana',player='p1',mana={'C':4,'R':1})
    assert not casting.castable(s.state,'p1',spell,cards)
    s.view('p1')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError,match='manual'):
        act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    assert s.state.model_dump_json() == before
    # A colorless spell has known zero overlap regardless of the missing pair.
    act(s,'p1',type='cast_spell',card_id=colorless.id,sources=[])
    answer(s)
    assert colorless.zone == 'p1:battlefield'
    act(s,'p1',type='set_card_automation',card_id=source.id,mode='manual')
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_thaumaturge_does_not_discount_player_target_or_graveyard_creature_cards(cards):
    s = table(cards,['Battlefield Thaumaturge','Blaze','Soul Salvage','Grizzly Bears'])
    put(s,'Battlefield Thaumaturge','battlefield')
    dead = put(s,'Grizzly Bears','graveyard')
    fire = put(s,'Blaze','hand')
    salvage = put(s,'Soul Salvage','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'R':1})
    act(s,'p1',type='cast_spell',card_id=fire.id,x_value=3,targets=['p2'],sources=[])
    answer(s)
    assert s.state.players['p2'].life == 37 and not s.state.players['p1'].mana_units
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'B':1})
    act(s,'p1',type='cast_spell',card_id=salvage.id,targets=[dead.id],target_counts=[1],sources=[])
    answer(s)
    assert dead.zone == 'p1:hand' and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_thaumaturge_does_not_discount_creature_targeting_aura(cards):
    s = table(cards,['Battlefield Thaumaturge','Pacifism','Grizzly Bears'])
    put(s,'Battlefield Thaumaturge','battlefield')
    target = put(s,'Grizzly Bears','battlefield')
    aura = put(s,'Pacifism','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    act(s,'p1',type='cast_spell',card_id=aura.id,targets=[target.id],sources=[])
    answer(s)
    assert aura.attached_to == target.id and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_mistform_type_choice_expires_and_opponents_do_not_share_discount(cards):
    s = table(cards,['Mistform Warchief','Elvish Visionary'],['Phantom Warrior'])
    source = put(s,'Mistform Warchief','battlefield')
    own_spell = put(s,'Elvish Visionary','hand')
    enemy_spell = put(s,'Phantom Warrior','hand',pid='p2')
    ready(s)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[])
    pick(s,'Elf')
    answer(s)
    assert Plan(s.state,'p1',cards,None).ch(source).subtypes == {'Elf'}
    to_phase(s,'main1',5)
    assert Plan(s.state,'p1',cards,None).ch(source).subtypes == {'Illusion'}
    act(s,'p2',type='add_mana',player='p2',mana={'C':1,'U':2})
    act(s,'p2',type='cast_spell',card_id=enemy_spell.id,sources=[])
    answer(s)
    assert enemy_spell.zone == 'p2:battlefield' and not s.state.players['p2'].mana_units
    to_phase(s,'main1',7)
    act(s,'p1',type='add_mana',player='p1',mana={'G':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=own_spell.id,sources=[])
    assert s.state.model_dump_json() == before
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_genuine_cold_native_choice_and_target_price(cards,tmp_path,name):
    import subprocess
    import sys

    from app.rules import source_spell_discounts64
    source_id = None
    target_ids = []
    if name == 'Seal of the Guildpact':
        s = table(cards,[name,'Assault Zeppelid'])
        source = put(s,name,'hand')
        spell = put(s,'Assault Zeppelid','hand')
        ready(s)
        act(s,'p1',type='add_mana',player='p1',mana={'C':5,'G':1,'U':1})
        act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
        pick(s,'Blue')
        assert s.state.rules.decision is not None and 'Green' in {o.id for o in s.state.rules.decision.options}
        chosen = 'Green'
        action = dict(type='cast_spell',card_id=spell.id,sources=[])
    elif name == 'Mistform Warchief':
        s = table(cards,[name,'Elvish Visionary'])
        source = put(s,name,'battlefield')
        spell = put(s,'Elvish Visionary','hand')
        ready(s)
        act(s,'p1',type='add_mana',player='p1',mana={'G':1})
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[])
        for _ in range(30):
            if s.state.rules.decision is not None:
                break
            act(s,s.state.rules.priority,type='pass_priority')
        assert 'Elf' in {o.id for o in s.state.rules.decision.options}
        chosen = 'Elf'
        action = dict(type='cast_spell',card_id=spell.id,sources=[])
    else:
        s = table(cards,[name,'Choking Tethers','Grizzly Bears','Llanowar Elves'],['Hill Giant'])
        source = put(s,name,'battlefield')
        targets = [source,put(s,'Grizzly Bears','battlefield'),put(s,'Llanowar Elves','battlefield'),put(s,'Hill Giant','battlefield',pid='p2')]
        spell = put(s,'Choking Tethers','hand')
        ready(s)
        act(s,'p1',type='add_mana',player='p1',mana={'U':1})
        chosen = None
        target_ids = [c.id for c in targets]
        action = dict(type='cast_spell',card_id=spell.id,targets=target_ids,target_counts=[4],sources=[])
    source_id = source.id
    saved = tmp_path/'saved.json'
    saved.write_text(s.state.model_dump_json())
    spec = tmp_path/'spec.json'
    spec.write_text(json.dumps(dict(name=name,source=source_id,spell=spell.id,chosen=chosen,action=action,targets=target_ids)))
    code = '''
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import casting
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spec=json.loads(Path(sys.argv[3]).read_text())
if spec['chosen'] is not None:
 d=s.state.rules.decision
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[spec['chosen']])
 answer(s)
spell=s.state.cards[spec['spell']]
assert casting.castable(s.state,'p1',spell,repo)
act(s,'p1',**spec['action'])
answer(s)
assert not s.state.players['p1'].mana_units
if spec['name']=='Battlefield Thaumaturge':assert all(s.state.cards[c].tapped for c in spec['targets'])
else:assert spell.zone=='p1:battlefield'
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),str(spec)],
                            cwd=Path(source_spell_discounts64.__file__).resolve().parents[2],capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr
