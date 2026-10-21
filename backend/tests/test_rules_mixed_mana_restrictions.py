"""Actual mixed-purpose restricted mana remains restricted through native payments."""
from __future__ import annotations

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
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import settle as answer
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Discreet Retreat','Creeping Peeper','Unblinking Observer','Cultivator Drone','Tin Street Gossip','Qarsi Deceiver']
ROOM='Grand Entryway // Elegant Rotunda'


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/mixed_mana_restrictions_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='mmr',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def mana(s,**pool):
    act(s,'p1',type='add_mana',player='p1',mana=pool)


def index(s,source,substring):
    return next(a.index for a in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).abilities if substring in a.text)


def game(cards,name):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/mixed_mana_restrictions_cards.json').read_text())]
    s=table(cards,names,names,names)
    if name=='Discreet Retreat':
        source=put(s,'Forest','battlefield')
        aura=put(s,name,'hand')
        mana(s,C=3,B=1)
        act(s,'p1',type='cast_spell',card_id=aura.id,targets=[source.id],sources=[])
        settle(s)
    else:
        source=put(s,name,'battlefield')
    to_phase(s,'main1',4)
    act(s,'p1',type='set_prefs',hold_priority=True)
    return s,source


def produce(s,source,color=None):
    a=index(s,source,'Add two mana') if source.name=='Forest' else index(s,source,'Add ')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=a,**({'mana_choice':color} if color else {}))
    roundtrip(s)


def cast(s,name,pool=None,**extra):
    source=put(s,name,'hand')
    if pool:
        mana(s,**pool)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],**extra)
    return source


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('name',NAMES)
def test_restricted_mana_cannot_pay_for_ordinary_creature_spell(cards,name):
    s,source=game(cards,name)
    produce(s,source,'G' if name=='Discreet Retreat' else None)
    if name not in ('Discreet Retreat','Tin Street Gossip'):
        mana(s,G=1)
    before=mana_pool(s,'p1')
    victim=put(s,'Grizzly Bears','hand')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=victim.id,sources=[])
    assert mana_pool(s,'p1')==before and s.state.cards[victim.id].zone=='p1:hand'
    roundtrip(s)


def test_discreet_retreat_pays_outlaw_spell_and_outlaw_source_ability(cards):
    s,land=game(cards,'Discreet Retreat')
    produce(s,land,'B')
    assassin=cast(s,'Guul Draz Assassin')
    settle(s)
    mana(s,C=1)
    act(s,'p1',type='activate_ability',card_id=assassin.id,ability=index(s,assassin,'Put a level counter'),sources=[])
    settle(s)
    assert s.state.cards[assassin.id].counters.get('level')==1
    assert not mana_pool(s,'p1')
    roundtrip(s)


def test_creeping_peeper_pays_enchantment_spell(cards):
    s,source=game(cards,'Creeping Peeper')
    produce(s,source)
    spell=cast(s,'Secret Plans',{'G':1})
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    roundtrip(s)


def test_creeping_peeper_pays_room_unlock_special_action(cards):
    s,source=game(cards,'Creeping Peeper')
    room=put(s,ROOM,'battlefield')
    produce(s,source)
    mana(s,W=1,C=1)
    act(s,'p1',type='unlock_door',card_id=room.id,door=2)
    assert 2 in s.state.rules.unlocked[s.state.rules.object_id(room.id)]
    answer(s)
    roundtrip(s)


def test_ability_only_mana_does_not_pay_room_unlock_special_action(cards):
    s,source=game(cards,'The Enigma Jewel // Locus of Enlightenment')
    room=put(s,ROOM,'battlefield')
    produce(s,source)
    mana(s,W=1)
    before=mana_pool(s,'p1')
    with pytest.raises(ActionError):
        act(s,'p1',type='unlock_door',card_id=room.id,door=2)
    assert mana_pool(s,'p1')==before
    roundtrip(s)


def test_observer_pays_actual_disturb_creature_spell(cards):
    s,source=game(cards,'Unblinking Observer')
    produce(s,source)
    angler=put(s,'Baithook Angler // Hook-Haunt Drifter','graveyard')
    mana(s,C=1)
    act(s,'p1',type='cast_spell',card_id=angler.id,sources=[])
    paid=s.state.rules.payments[s.state.rules.object_id(angler.id)]
    assert paid.alternative=='disturb' and paid.mana_spent=={'C':1,'U':1}
    settle(s)
    assert s.state.cards[angler.id].face==1 and s.state.cards[angler.id].zone=='p1:battlefield'
    roundtrip(s)


def test_observer_pays_instant_spell(cards):
    s,source=game(cards,'Unblinking Observer')
    produce(s,source)
    spell=cast(s,'Opt')
    assert s.state.rules.payments[s.state.rules.object_id(spell.id)].mana_spent=={'U':1}
    answer(s)
    roundtrip(s)


@pytest.mark.parametrize('name',['Tin Street Gossip','Qarsi Deceiver'])
def test_face_down_spell_cast_uses_restricted_mana(cards,name):
    s,source=game(cards,name)
    produce(s,source)
    spell=cast(s,'Willbender',{'C':1 if name=='Tin Street Gossip' else 2},face_down=True)
    assert s.state.cards[spell.id].face_down
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:battlefield' and s.state.cards[spell.id].face_down
    roundtrip(s)


@pytest.mark.parametrize('name',['Creeping Peeper','Tin Street Gossip','Qarsi Deceiver'])
def test_native_morph_payment_accepts_each_appropriate_restriction(cards,name):
    s,source=game(cards,name)
    victim=put(s,'Willbender','battlefield')
    act(s,'p1',type='face_down',card_ids=[victim.id],face_down=True,kind='morph')
    produce(s,source)
    mana(s,**({'C':1} if name=='Creeping Peeper' else {'U':1}))
    act(s,'p1',type='turn_face_up',card_id=victim.id,method='morph',sources=[])
    assert not s.state.cards[victim.id].face_down
    answer(s)
    roundtrip(s)


@pytest.mark.parametrize(('kind','allowed'),[('manifest',True),('cloak',False)])
def test_qarsi_distinguishes_manifest_mana_from_cloak_mana(cards,kind,allowed):
    s,source=game(cards,'Qarsi Deceiver')
    victim=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='face_down',card_ids=[victim.id],face_down=True,kind=kind)
    produce(s,source)
    mana(s,G=1)
    if allowed:
        act(s,'p1',type='turn_face_up',card_id=victim.id,method='mana_cost',sources=[])
        assert not s.state.cards[victim.id].face_down
    else:
        before=mana_pool(s,'p1')
        with pytest.raises(ActionError):
            act(s,'p1',type='turn_face_up',card_id=victim.id,method='mana_cost',sources=[])
        assert s.state.cards[victim.id].face_down and mana_pool(s,'p1')==before
    roundtrip(s)


def test_cultivator_pays_colorless_spell_and_colorless_source_ability(cards):
    s,source=game(cards,'Cultivator Drone')
    produce(s,source)
    spell=cast(s,'Sol Ring')
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    roundtrip(s)


def test_cultivator_pays_colored_source_ability_with_actual_colorless_symbol(cards):
    s,source=game(cards,'Cultivator Drone')
    victim=put(s,'Grizzly Bears','battlefield')
    aura=cast(s,'Utter Insignificance',{'C':2,'U':1},targets=[victim.id])
    settle(s)
    produce(s,source)
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=aura.id,ability=index(s,aura,'Exile enchanted creature'),sources=[])
    settle(s)
    assert s.state.cards[victim.id].zone=='p1:exile' and not mana_pool(s,'p1')
    roundtrip(s)


@pytest.mark.parametrize('name',['Unblinking Observer','Qarsi Deceiver'])
def test_restricted_native_self_payment_context_survives_cold_load(cards,tmp_path,name):
    import subprocess
    import sys

    s,source=game(cards,name)
    act(s,'p1',type='set_prefs',payment='self')
    if name=='Unblinking Observer':
        spell=put(s,'Baithook Angler // Hook-Haunt Drifter','graveyard')
        mana(s,C=1)
        act(s,'p1',type='cast_spell',card_id=spell.id)
        assert s.state.rules.decision.resume['payment_context']['alternative']=='disturb'
    else:
        spell=put(s,'Willbender','hand')
        mana(s,C=2)
        act(s,'p1',type='cast_spell',card_id=spell.id,face_down=True)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    roundtrip(s)
    saved=tmp_path/'restricted.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
saved,database,source,spell,name=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
a=next(a.index for a in Plan(s.state,'p1',repo,None).ch(s.state.cards[source]).abilities if 'Add ' in a.text)
s.perform('p1',{'type':'activate_ability','card_id':source,'ability':a})
assert s.state.rules.decision is None
if name=='Qarsi Deceiver':
    spell=next(c.id for c in s.state.cards.values() if c.zone=='stack' and c.face_down)
assert s.state.cards[spell].zone=='stack'
p=s.state.rules.payments[s.state.rules.object_id(spell)]
assert p.mana_spent==({'C':1,'U':1} if name=='Unblinking Observer' else {'C':3})
assert p.alternative==('disturb' if name=='Unblinking Observer' else 'face_down')
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,spell.id,name],
                          capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_qarsi_pays_megamorph_and_its_extra_counter(cards):
    s,source=game(cards,'Qarsi Deceiver')
    victim=put(s,'Ainok Survivalist','battlefield')
    act(s,'p1',type='face_down',card_ids=[victim.id],face_down=True,kind='morph')
    produce(s,source)
    mana(s,G=1)
    act(s,'p1',type='turn_face_up',card_id=victim.id,method='morph',sources=[])
    assert not s.state.cards[victim.id].face_down
    assert s.state.cards[victim.id].counters.get('+1/+1')==1
    answer(s)
    roundtrip(s)


@pytest.mark.parametrize('kind',['manifest','cloak'])
def test_qarsi_can_pay_morph_even_when_card_was_hidden_by_another_method(cards,kind):
    s,source=game(cards,'Qarsi Deceiver')
    victim=put(s,'Willbender','battlefield')
    act(s,'p1',type='face_down',card_ids=[victim.id],face_down=True,kind=kind)
    produce(s,source)
    mana(s,U=1)
    act(s,'p1',type='turn_face_up',card_id=victim.id,method='morph',sources=[])
    assert not s.state.cards[victim.id].face_down
    answer(s)
    roundtrip(s)


def test_cultivator_pays_colorless_source_mana_ability(cards):
    s,source=game(cards,'Cultivator Drone')
    prism=put(s,'Prismite','battlefield')
    produce(s,source)
    mana(s,C=1)
    act(s,'p1',type='activate_ability',card_id=prism.id,ability=index(s,prism,'Add one mana'),mana_choice='U',sources=[])
    assert mana_pool(s,'p1')=={'U':1}
    roundtrip(s)


def test_cultivator_rejects_colored_source_cost_without_colorless_symbol(cards):
    s,source=game(cards,'Cultivator Drone')
    mage=put(s,'Azure Mage','battlefield')
    produce(s,source)
    mana(s,C=2,U=1)
    before=mana_pool(s,'p1')
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=mage.id,ability=index(s,mage,'Draw a card'),sources=[])
    assert mana_pool(s,'p1')==before
    roundtrip(s)


def test_spend_as_any_type_does_not_erase_observer_spell_restriction(cards):
    s,source=game(cards,'Unblinking Observer')
    put(s,'Mycosynth Lattice','battlefield')
    produce(s,source)
    mana(s,C=1)
    victim=put(s,'Grizzly Bears','hand')
    before=mana_pool(s,'p1')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=victim.id,sources=[])
    assert mana_pool(s,'p1')==before and s.state.cards[victim.id].zone=='p1:hand'
    roundtrip(s)


def test_qarsi_rejects_disguise_even_when_its_mana_could_pay_generic_portion(cards):
    s,source=game(cards,'Qarsi Deceiver')
    victim=put(s,'Museum Nightwatch','battlefield')
    act(s,'p1',type='face_down',card_ids=[victim.id],face_down=True,kind='disguise')
    produce(s,source)
    mana(s,W=1)
    before=mana_pool(s,'p1')
    with pytest.raises(ActionError):
        act(s,'p1',type='turn_face_up',card_id=victim.id,method='disguise',sources=[])
    assert s.state.cards[victim.id].face_down and mana_pool(s,'p1')==before
    roundtrip(s)


def test_cultivator_does_not_treat_colorless_card_in_hand_as_permanent(cards):
    s,source=game(cards,'Cultivator Drone')
    victim=put(s,'Hollow One','hand')
    produce(s,source)
    mana(s,C=1)
    before=mana_pool(s,'p1')
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=victim.id,ability=index(s,victim,'Cycling'),sources=[])
    assert mana_pool(s,'p1')==before and s.state.cards[victim.id].zone=='p1:hand'
    roundtrip(s)
