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
    record=s.state.rules.payments[s.state.rules.object_id(skydiver.id)]
    assert record.kicked==additional and (record.x or 0)==additional
    roundtrip(s)


@pytest.mark.parametrize('name', ['Thieving Skydiver', 'Agonizing Demise'])
def test_true_cold_original_payment_and_object_resolution(cards, tmp_path, name):
    import subprocess
    import sys

    from app.rules import kicked_x_lki_outcomes61
    opponent = 'Silver-Inlaid Dagger' if name == 'Thieving Skydiver' else 'Hill Giant'
    s = game(cards, [name], opponents=[opponent])
    target = put(s, opponent, 'battlefield', pid='p2')
    spell = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':4, 'U':1, 'B':1, 'R':1})
    action = dict(type='cast_spell', card_id=spell.id, kicker=1, sources=[])
    if name == 'Thieving Skydiver':
        action['x_value'] = 1
    else:
        action['targets'] = [target.id]
    act(s, 'p1', **action)
    saved = tmp_path/'saved.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
name,target,spell=sys.argv[3:]
answer(s)
if name=='Thieving Skydiver':
 assert s.state.cards[target].controller=='p1'
 assert s.state.cards[target].attached_to==spell
else:
 assert s.state.cards[target].zone=='p2:graveyard'
 assert s.state.players['p2'].life==37
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, target.id, spell.id],
                            cwd=Path(kicked_x_lki_outcomes61.__file__).resolve().parents[2], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_demise_rejects_noncreature_artifact_target_atomically(cards):
    s = game(cards, ['Agonizing Demise'], opponents=['Silver-Inlaid Dagger'])
    artifact = put(s, 'Silver-Inlaid Dagger', 'battlefield', pid='p2')
    spell = put(s, 'Agonizing Demise', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':4, 'B':1, 'R':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=1, targets=[artifact.id], sources=[])
    assert s.state.model_dump_json() == before


def test_demise_cannot_target_black_creature(cards):
    s = game(cards, ['Agonizing Demise'], opponents=['Thorn of the Black Rose'])
    target = put(s, 'Thorn of the Black Rose', 'battlefield', pid='p2')
    spell = put(s, 'Agonizing Demise', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':4, 'B':1, 'R':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=1, targets=[target.id], sources=[])
    assert s.state.model_dump_json() == before


def test_demise_ignores_existing_regeneration_shield(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = game(cards, ['Agonizing Demise'], opponents=['River Boa'])
    target = put(s, 'River Boa', 'battlefield', pid='p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'G':1})
    act(s, 'p2', type='activate_ability', card_id=target.id, ability=1, sources=[])
    answer(s)
    wait_priority(s, 'p1')
    spell = put(s, 'Agonizing Demise', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':4, 'B':1, 'R':1})
    before = s.state.players['p2'].life
    act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=1, targets=[target.id], sources=[])
    answer(s)
    assert target.zone == 'p2:graveyard' and s.state.players['p2'].life == before-2
    roundtrip(s)


def test_demise_reads_resolution_controller_after_actual_dominate_response(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards, ['Agonizing Demise'], ['Hill Giant'], ['Dominate'])
    for pid in ('p1', 'p2', 'p3'):
        act(s, pid, type='set_prefs', hold_priority=True)
    to_phase(s, 'main1', 4)
    target = put(s, 'Hill Giant', 'battlefield', pid='p2')
    spell = put(s, 'Agonizing Demise', 'hand')
    response = put(s, 'Dominate', 'hand', pid='p3')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':4, 'B':1, 'R':1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=1, targets=[target.id], sources=[])
    wait_priority(s, 'p3')
    act(s, 'p3', type='add_mana', player='p3', mana={'C':5, 'U':2})
    act(s, 'p3', type='cast_spell', card_id=response.id, x_value=4, targets=[target.id], sources=[])
    answer(s)
    assert target.zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 40 and s.state.players['p3'].life == 37
    roundtrip(s)


def test_skydiver_blinked_before_entry_trigger_cannot_attach_to_new_incarnation(cards):
    s = game(cards, ['Thieving Skydiver', 'Cloudshift'], opponents=['Silver-Inlaid Dagger'])
    equipment = put(s, 'Silver-Inlaid Dagger', 'battlefield', pid='p2')
    spell = put(s, 'Thieving Skydiver', 'hand')
    blink = put(s, 'Cloudshift', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':2, 'U':1, 'W':1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=1, x_value=1, sources=[])
    for _ in range(30):
        if spell.zone == 'p1:battlefield' and s.state.rules.stack and s.state.rules.decision is None:
            break
        d = s.state.rules.decision
        if d is not None:
            assert equipment.id in {o.id for o in d.options}
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[equipment.id])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert spell.zone == 'p1:battlefield' and s.state.rules.stack
    old = s.state.rules.object_id(spell.id)
    from tests.test_rules_bandmate_references import wait_priority
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[spell.id], sources=[])
    answer(s)
    assert s.state.rules.object_id(spell.id) != old
    assert equipment.controller == 'p1' and equipment.attached_to is None
    roundtrip(s)
