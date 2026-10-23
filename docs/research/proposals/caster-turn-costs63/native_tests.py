"""Native static spell/activation prices and counterability follow actual spell/caster/turn."""
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

NAMES = ['Cunning Nightbonder','Hum of the Radix','Tithe Taker']


@pytest.fixture
def cards(settings):
    base = {c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/caster_turn_costs63_cards.json').read_text())):
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
def test_whole_definitions(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('protected',[False,True])
def test_cunning_discount_and_actual_counterspell(cards,protected):
    s = table(cards,['Cunning Nightbonder','Ashcoat Bear'],['Counterspell'])
    if protected:
        put(s,'Cunning Nightbonder','battlefield')
    spell = put(s,'Ashcoat Bear','hand')
    counter = put(s,'Counterspell','hand',pid='p2')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'G':1,**({} if protected else {'C':1})})
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':2})
    act(s,'p2',type='cast_spell',card_id=counter.id,targets=[spell.id],sources=[])
    answer(s)
    assert spell.zone == ('p1:battlefield' if protected else 'p1:graveyard')
    assert not s.state.players['p1'].mana_units
    roundtrip(s)


@pytest.mark.parametrize('pid',['p1','p2'])
@pytest.mark.parametrize('count',[0,2])
def test_hum_counts_only_casters_actual_artifacts(cards,pid,count):
    deck = ['Hum of the Radix','Silver-Inlaid Dagger','Darksteel Myr','Sol Ring']
    s = table(cards,deck,deck)
    put(s,'Hum of the Radix','battlefield')
    other = 'p2' if pid == 'p1' else 'p1'
    for name in ('Darksteel Myr','Sol Ring'):
        put(s,name,'battlefield',pid=other)
        if count:
            put(s,name,'battlefield',pid=pid)
    spell = put(s,'Silver-Inlaid Dagger','hand',pid=pid)
    ready(s)
    if pid == 'p2':
        to_phase(s,'main1',5)
    wait_priority(s,pid)
    act(s,pid,type='add_mana',player=pid,mana={'C':1+count})
    act(s,pid,type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert spell.zone == pid+':battlefield' and not s.state.players[pid].mana_units
    roundtrip(s)


@pytest.mark.parametrize('own_turn',[False,True])
def test_tithe_opponent_spell_tax_only_during_sources_controller_turn(cards,own_turn):
    s = table(cards,['Tithe Taker'],['Lightning Bolt'])
    put(s,'Tithe Taker','battlefield')
    spell = put(s,'Lightning Bolt','hand',pid='p2')
    ready(s)
    if not own_turn:
        to_phase(s,'main1',5)
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'R':1,**({'C':1} if own_turn else {})})
    act(s,'p2',type='cast_spell',card_id=spell.id,targets=['p3'],sources=[])
    answer(s)
    assert s.state.players['p3'].life == 37 and not s.state.players['p2'].mana_units
    roundtrip(s)


@pytest.mark.parametrize('own_turn',[False,True])
def test_tithe_nonmana_activation_tax_uses_source_turn(cards,own_turn):
    s = table(cards,['Tithe Taker'],['Prodigal Pyromancer'])
    put(s,'Tithe Taker','battlefield')
    source = put(s,'Prodigal Pyromancer','battlefield',pid='p2')
    ready(s)
    if not own_turn:
        to_phase(s,'main1',5)
    wait_priority(s,'p2')
    if own_turn:
        act(s,'p2',type='add_mana',player='p2',mana={'C':1})
    act(s,'p2',type='activate_ability',card_id=source.id,ability=0,targets=['p3'],sources=[])
    answer(s)
    assert source.tapped and s.state.players['p3'].life == 39 and not s.state.players['p2'].mana_units
    roundtrip(s)


def test_tithe_does_not_tax_actual_opponent_mana_ability(cards):
    s = table(cards,['Tithe Taker'],['Llanowar Elves'])
    put(s,'Tithe Taker','battlefield')
    source = put(s,'Llanowar Elves','battlefield',pid='p2')
    ready(s)
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=source.id,ability=0,sources=[])
    assert source.tapped
    assert s.state.players['p2'].mana_units
    roundtrip(s)


def test_tithe_actual_death_creates_afterlife_spirit(cards):
    s = table(cards,['Tithe Taker'],['Lightning Bolt'])
    source = put(s,'Tithe Taker','battlefield')
    spell = put(s,'Lightning Bolt','hand',pid='p2')
    ready(s)
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'C':1,'R':1})
    act(s,'p2',type='cast_spell',card_id=spell.id,targets=[source.id],sources=[])
    answer(s)
    assert source.zone == 'p1:graveyard'
    view = Plan(s.state,'p1',cards,None)
    spirits = [c for c in s.state.cards.values() if c.controller == 'p1' and c.zone.endswith(':battlefield') and 'Spirit' in view.ch(c).subtypes]
    assert len(spirits) == 1 and view.ch(spirits[0]).pt == (1,1) and 'flying' in view.ch(spirits[0]).keywords
    roundtrip(s)


def test_hum_tax_applies_to_omnisicience_alternative_free_base(cards):
    s = table(cards,['Hum of the Radix','Omniscience','Darksteel Myr','Sol Ring','Silver-Inlaid Dagger'])
    for name in ['Hum of the Radix','Omniscience','Darksteel Myr','Sol Ring']:
        put(s,name,'battlefield')
    spell = put(s,'Silver-Inlaid Dagger','hand')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='cast_spell',card_id=spell.id,free=True,sources=[])
    answer(s)
    assert spell.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_tithe_nonmana_activation_cannot_avoid_required_mana(cards):
    s = table(cards,['Tithe Taker'],['Prodigal Pyromancer'])
    put(s,'Tithe Taker','battlefield')
    source = put(s,'Prodigal Pyromancer','battlefield',pid='p2')
    ready(s)
    wait_priority(s,'p2')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='activate_ability',card_id=source.id,ability=0,targets=['p3'],sources=[])
    assert s.state.model_dump_json() == before


def test_cunning_does_not_make_orrery_timing_into_keyword_flash(cards):
    s = table(cards,['Cunning Nightbonder','Vedalken Orrery','Silver-Inlaid Dagger'],['Counterspell'])
    put(s,'Cunning Nightbonder','battlefield')
    put(s,'Vedalken Orrery','battlefield')
    spell = put(s,'Silver-Inlaid Dagger','hand')
    counter = put(s,'Counterspell','hand',pid='p2')
    ready(s)
    to_phase(s,'main1',5)
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':2})
    act(s,'p2',type='cast_spell',card_id=counter.id,targets=[spell.id],sources=[])
    answer(s)
    assert spell.zone == 'p1:graveyard' and not s.state.players['p1'].mana_units
    roundtrip(s)


def test_cunning_source_removed_before_counter_resolution_loses_protection(cards):
    s = table(cards,['Cunning Nightbonder','Ashcoat Bear'],['Counterspell'],['Lightning Bolt'])
    source = put(s,'Cunning Nightbonder','battlefield')
    spell = put(s,'Ashcoat Bear','hand')
    counter = put(s,'Counterspell','hand',pid='p2')
    bolt = put(s,'Lightning Bolt','hand',pid='p3')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'G':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'U':2})
    act(s,'p2',type='cast_spell',card_id=counter.id,targets=[spell.id],sources=[])
    wait_priority(s,'p3')
    act(s,'p3',type='add_mana',player='p3',mana={'R':1})
    act(s,'p3',type='cast_spell',card_id=bolt.id,targets=[source.id],sources=[])
    answer(s)
    assert source.zone == 'p1:graveyard' and spell.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_genuine_new_process_static_cost_and_counterability(cards,tmp_path,name):
    import subprocess
    import sys

    from app.rules import caster_turn_costs63
    pid = 'p1'
    counter_id = None
    if name == 'Cunning Nightbonder':
        s = table(cards,[name,'Ashcoat Bear'],['Counterspell'])
        put(s,name,'battlefield')
        source = put(s,'Ashcoat Bear','hand')
        counter_id = put(s,'Counterspell','hand',pid='p2').id
        ready(s)
        act(s,'p1',type='add_mana',player='p1',mana={'G':1})
        action = dict(type='cast_spell',card_id=source.id,sources=[])
    elif name == 'Hum of the Radix':
        s = table(cards,[name,'Darksteel Myr','Silver-Inlaid Dagger'])
        put(s,name,'battlefield')
        put(s,'Darksteel Myr','battlefield')
        source = put(s,'Silver-Inlaid Dagger','hand')
        ready(s)
        act(s,'p1',type='add_mana',player='p1',mana={'C':2})
        action = dict(type='cast_spell',card_id=source.id,sources=[])
    else:
        s = table(cards,[name],['Prodigal Pyromancer'])
        put(s,name,'battlefield')
        source = put(s,'Prodigal Pyromancer','battlefield',pid='p2')
        ready(s)
        wait_priority(s,'p2')
        pid = 'p2'
        act(s,pid,type='add_mana',player=pid,mana={'C':1})
        action = dict(type='activate_ability',card_id=source.id,ability=0,targets=['p3'],sources=[])
    saved = tmp_path/'saved.json'
    saved.write_text(s.state.model_dump_json())
    spec = tmp_path/'spec.json'
    spec.write_text(json.dumps(dict(name=name,pid=pid,source=source.id,action=action,counter=counter_id)))
    code = '''
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spec=json.loads(Path(sys.argv[3]).read_text())
act(s,spec['pid'],**spec['action'])
if spec['name']=='Cunning Nightbonder':
 wait_priority(s,'p2')
 act(s,'p2',type='add_mana',player='p2',mana={'U':2})
 act(s,'p2',type='cast_spell',card_id=spec['counter'],targets=[spec['source']],sources=[])
answer(s)
assert not s.state.players[spec['pid']].mana_units
if spec['name']=='Tithe Taker':assert s.state.players['p3'].life==39 and s.state.cards[spec['source']].tapped
else:assert s.state.cards[spec['source']].zone=='p1:battlefield'
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),str(spec)],
                            cwd=Path(caster_turn_costs63.__file__).resolve().parents[2],capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr


def test_cunning_does_not_discount_or_protect_opponents_flash_spell(cards):
    s = table(cards,['Cunning Nightbonder'],['Ashcoat Bear'],['Counterspell'])
    put(s,'Cunning Nightbonder','battlefield')
    spell = put(s,'Ashcoat Bear','hand',pid='p2')
    counter = put(s,'Counterspell','hand',pid='p3')
    ready(s)
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'C':1,'G':1})
    act(s,'p2',type='cast_spell',card_id=spell.id,sources=[])
    wait_priority(s,'p3')
    act(s,'p3',type='add_mana',player='p3',mana={'U':2})
    act(s,'p3',type='cast_spell',card_id=counter.id,targets=[spell.id],sources=[])
    answer(s)
    assert spell.zone == 'p2:graveyard' and not s.state.players['p2'].mana_units
    roundtrip(s)


def test_tithe_does_not_tax_controllers_own_nonmana_activation(cards):
    s = table(cards,['Tithe Taker','Prodigal Pyromancer'])
    put(s,'Tithe Taker','battlefield')
    source = put(s,'Prodigal Pyromancer','battlefield')
    ready(s)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=['p3'],sources=[])
    answer(s)
    assert s.state.players['p3'].life == 39 and source.tapped
    roundtrip(s)
