"""Selected dash and actual controller-turn equip costs retain native keyword rules."""
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
from tests.test_rules_suspend import until
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Tax Collector','Academy Loremaster']


@pytest.fixture
def cards(settings):
    base = {c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/stored_player_costs66_cards.json').read_text())):
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


def pick(s,label):
    until(s,lambda s:s.state.rules.decision is not None)
    d = s.state.rules.decision
    options = [o for o in d.options if label.casefold() in o.label.casefold() or label == o.id]
    assert len(options) == 1, [(o.id,o.label) for o in d.options]
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[options[0].id])


def test_tax_collector_actual_cast_tax_mode_expires_on_your_next_turn(cards):
    s = table(cards,['Tax Collector'],['Merfolk of the Pearl Trident'])
    source = put(s,'Tax Collector','hand')
    spell = put(s,'Merfolk of the Pearl Trident','hand',pid='p2')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    pick(s,'Tax —')
    answer(s)
    to_phase(s,'main1',5)
    assert s.state.turn.active_player == 'p2'
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=spell.id,sources=[])
    assert s.state.model_dump_json() == before
    act(s,'p2',type='add_mana',player='p2',mana={'C':1})
    act(s,'p2',type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert spell.zone == 'p2:battlefield' and not s.state.players['p2'].mana_units
    assert s.state.rules.cost_modifiers
    to_phase(s,'main1',7)
    assert not s.state.rules.cost_modifiers
    roundtrip(s)


@pytest.mark.parametrize('take',[True,False])
def test_loremaster_actual_opponent_draw_choice_binds_only_that_caster(cards,take):
    s = table(cards,['Academy Loremaster','Merfolk of the Pearl Trident','Lightning Bolt'],['Merfolk of the Pearl Trident'])
    own = put(s,'Merfolk of the Pearl Trident','hand')
    bolt = put(s,'Lightning Bolt','hand')
    spell = put(s,'Merfolk of the Pearl Trident','hand',pid='p2')
    ready(s)
    source = put(s,'Academy Loremaster','battlefield')
    until(s,lambda s:s.state.rules.decision is not None and 'draw a card?' in s.state.rules.decision.prompt)
    d = s.state.rules.decision
    assert d.player == 'p2' and s.state.turn.number == 5
    hand_before = len(s.state.zones['p2:hand'])
    pick(s,'Yes' if take else 'No')
    answer(s)
    assert len(s.state.zones['p2:hand']) == hand_before + int(take)
    assert len(s.state.rules.cost_modifiers) == int(take)
    if take:
        assert s.state.rules.cost_modifiers[0].controller == 'p2'
    # Stored effect survives the source leaving; no other player's spells are taxed.
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'graveyard','player':'p1'})
    to_phase(s,'main1',5)
    act(s,'p2',type='add_mana',player='p2',mana={'U':1})
    if take:
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s,'p2',type='cast_spell',card_id=spell.id,sources=[])
        assert s.state.model_dump_json() == before
        act(s,'p2',type='add_mana',player='p2',mana={'C':2})
    act(s,'p2',type='cast_spell',card_id=spell.id,sources=[])
    answer(s)
    assert spell.zone == 'p2:battlefield' and not s.state.players['p2'].mana_units
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    life_before = s.state.players['p3'].life
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=['p3'],sources=[])
    answer(s)
    assert s.state.players['p3'].life == life_before - 3
    assert not s.state.players['p1'].mana_units
    to_phase(s,'main1',7)
    assert not s.state.rules.cost_modifiers
    act(s,'p1',type='add_mana',player='p1',mana={'U':1})
    act(s,'p1',type='cast_spell',card_id=own.id,sources=[])
    answer(s)
    assert own.zone == 'p1:battlefield'
    roundtrip(s)


def test_tax_collector_arrest_native_target_blocks_mana_activation_until_next_turn(cards):
    s = table(cards,['Tax Collector'],['Llanowar Elves'])
    source = put(s,'Tax Collector','hand')
    target = put(s,'Llanowar Elves','battlefield',pid='p2')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    pick(s,'Arrest —')
    pick(s,'Llanowar Elves')
    answer(s)
    assert not s.state.rules.cost_modifiers
    to_phase(s,'main1',5)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='activate_ability',card_id=target.id,ability=0,sources=[])
    assert s.state.model_dump_json() == before
    to_phase(s,'main1',7)
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=target.id,ability=0,sources=[])
    assert target.tapped and s.state.players['p2'].mana_units
    roundtrip(s)


def test_tax_mode_survives_actual_source_removal_response_and_taxes_only_opponents(cards):
    s = table(cards,['Tax Collector','Merfolk of the Pearl Trident'],['Lightning Bolt','Merfolk of the Pearl Trident'])
    source = put(s,'Tax Collector','hand')
    own = put(s,'Merfolk of the Pearl Trident','hand')
    bolt = put(s,'Lightning Bolt','hand',pid='p2')
    ready(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    pick(s,'Tax —')
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'R':1})
    act(s,'p2',type='cast_spell',card_id=bolt.id,targets=[source.id],sources=[])
    answer(s)
    assert source.zone == 'p1:graveyard' and len(s.state.rules.cost_modifiers) == 1
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'U':1})
    act(s,'p1',type='cast_spell',card_id=own.id,sources=[])
    answer(s)
    assert own.zone == 'p1:battlefield' and not s.state.players['p1'].mana_units
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_genuine_cold_native_stored_choice(cards,tmp_path,name):
    import subprocess
    import sys

    from app.rules import stored_player_costs66
    s = table(cards,[name],['Merfolk of the Pearl Trident'])
    spell = put(s,'Merfolk of the Pearl Trident','hand',pid='p2')
    ready(s)
    if name == 'Tax Collector':
        source = put(s,name,'hand')
        act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
        act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
        until(s,lambda s:s.state.rules.decision is not None)
        chosen = next(o.id for o in s.state.rules.decision.options if 'Tax —' in o.label)
        amount = 1
    else:
        put(s,name,'battlefield')
        until(s,lambda s:s.state.rules.decision is not None and 'draw a card?' in s.state.rules.decision.prompt)
        chosen = next(o.id for o in s.state.rules.decision.options if o.label == 'Yes')
        amount = 2
    saved = tmp_path/'saved.json'
    saved.write_text(s.state.model_dump_json())
    spec = tmp_path/'spec.json'
    spec.write_text(json.dumps(dict(chosen=chosen,amount=amount,spell=spell.id)))
    code = '''
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spec=json.loads(Path(sys.argv[3]).read_text())
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=[spec['chosen']])
answer(s)
assert len(s.state.rules.cost_modifiers)==1
to_phase(s,'main1',5)
act(s,'p2',type='add_mana',player='p2',mana={'C':spec['amount'],'U':1})
act(s,'p2',type='cast_spell',card_id=spec['spell'],sources=[])
answer(s)
assert s.state.cards[spec['spell']].zone=='p2:battlefield'
assert not s.state.players['p2'].mana_units
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),str(spec)],cwd=Path(stored_player_costs66.__file__).resolve().parents[2],capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr
