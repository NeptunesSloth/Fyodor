"""Actual nonzero kicker X, entry target limits and original-object damage values."""
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
from tests.test_rules_table_activation_modifiers52 import game


@pytest.fixture
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for filename in ['kicked_spell_outcomes59_cards.json','kicked_spell_outcomes59_supports.json','kicked_x_lki61_supports.json']:
        for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures'/filename).read_text())):
            base[c['name']]=card(c['name'],number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name',['Thieving Skydiver','Agonizing Demise'])
def test_canonical_complete(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('kicked',[0,1])
def test_skydiver_actual_selected_kicker_x_steals_and_attaches_equipment(cards,kicked):
    s=game(cards,['Thieving Skydiver'],opponents=['Silver-Inlaid Dagger'])
    equipment=put(s,'Silver-Inlaid Dagger','battlefield',pid='p2')
    spell=put(s,'Thieving Skydiver','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1+kicked,'U':1})
    a=dict(type='cast_spell',card_id=spell.id,kicker=kicked,sources=[])
    if kicked:
        a['x_value']=1
    act(s,'p1',**a)
    answer(s)
    assert spell.zone=='p1:battlefield'
    assert equipment.controller==('p1' if kicked else 'p2')
    assert equipment.attached_to==(spell.id if kicked else None)
    assert Plan(s.state,'p1',cards,None).ch(spell).pt==((4,1) if kicked else (2,1))
    roundtrip(s)


def test_skydiver_zero_kicker_x_is_refused_atomically(cards):
    s=game(cards,['Thieving Skydiver'])
    spell=put(s,'Thieving Skydiver','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'U':1})
    before=s.state.model_dump_json()
    with pytest.raises(ActionError,match='at least 1'):
        act(s,'p1',type='cast_spell',card_id=spell.id,kicker=1,x_value=0,sources=[])
    assert s.state.model_dump_json()==before


@pytest.mark.parametrize('x',[2,3])
def test_skydiver_artifact_mana_value_limit_and_nonequipment_branch(cards,x):
    s=game(cards,['Thieving Skydiver'],opponents=['Staff of Domination'])
    artifact=put(s,'Staff of Domination','battlefield',pid='p2')
    spell=put(s,'Thieving Skydiver','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1+x,'U':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,kicker=1,x_value=x,sources=[])
    answer(s)
    assert artifact.controller==('p1' if x==3 else 'p2') and artifact.attached_to is None
    roundtrip(s)


@pytest.mark.parametrize('kicked',[0,1])
def test_demise_uses_destroyed_original_power_and_controller(cards,kicked):
    s=game(cards,['Agonizing Demise','Giant Growth'],opponents=['Hill Giant'])
    target=put(s,'Hill Giant','battlefield',pid='p2')
    growth=put(s,'Giant Growth','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'G':1})
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[target.id],sources=[])
    answer(s)
    assert Plan(s.state,'p1',cards,None).ch(target).pt==(6,6)
    spell=put(s,'Agonizing Demise','hand')
    before=s.state.players['p2'].life
    act(s,'p1',type='add_mana',player='p1',mana={'C':3+kicked,'B':1,**({'R':1} if kicked else {})})
    act(s,'p1',type='cast_spell',card_id=spell.id,kicker=kicked,targets=[target.id],sources=[])
    answer(s)
    assert target.zone=='p2:graveyard' and s.state.players['p2'].life==before-6*kicked
    roundtrip(s)


def test_demise_still_deals_damage_when_indestructible_target_survives(cards):
    s=game(cards,['Agonizing Demise','Giant Growth'],opponents=['Darksteel Myr'])
    target=put(s,'Darksteel Myr','battlefield',pid='p2')
    growth=put(s,'Giant Growth','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'G':1})
    act(s,'p1',type='cast_spell',card_id=growth.id,targets=[target.id],sources=[])
    answer(s)
    spell=put(s,'Agonizing Demise','hand')
    before=s.state.players['p2'].life
    act(s,'p1',type='add_mana',player='p1',mana={'C':4,'B':1,'R':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,kicker=1,targets=[target.id],sources=[])
    answer(s)
    assert target.zone=='p2:battlefield' and s.state.players['p2'].life==before-3
    roundtrip(s)


def test_free_skydiver_still_announces_and_pays_positive_kicker_x(cards):
    s=game(cards,['Thieving Skydiver','Omniscience'],opponents=['Silver-Inlaid Dagger'])
    put(s,'Omniscience','battlefield')
    equipment=put(s,'Silver-Inlaid Dagger','battlefield',pid='p2')
    spell=put(s,'Thieving Skydiver','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,free=True,kicker=1,x_value=1,sources=[])
    answer(s)
    assert equipment.controller=='p1' and equipment.attached_to==spell.id
    roundtrip(s)


@pytest.mark.parametrize('additional',[0,1])
def test_actual_effect_free_cast_offers_only_payable_positive_kicker_x(cards,additional):
    s=game(cards,['Thieving Skydiver','Electrodominance'],opponents=['Silver-Inlaid Dagger'])
    equipment=put(s,'Silver-Inlaid Dagger','battlefield',pid='p2')
    skydiver=put(s,'Thieving Skydiver','hand')
    spell=put(s,'Electrodominance','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2+additional,'R':2})
    act(s,'p1',type='cast_spell',card_id=spell.id,x_value=2,targets=['p2'],sources=[])
    answer(s)
    assert skydiver.zone=='p1:battlefield'
    assert equipment.controller==('p1' if additional else 'p2')
    record=s.state.rules.payments[s.state.rules.object_id(skydiver)]
    assert record.kicked==additional and (record.x or 0)==additional
    roundtrip(s)
