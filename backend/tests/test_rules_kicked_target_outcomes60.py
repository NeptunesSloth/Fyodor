"""Native announced kicker groups, modal target slots and actual returned-object counts."""
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
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Inscription of Insight', 'Waste Management', 'The Eagles Are Coming!']


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['kicked_spell_outcomes59_cards.json','kicked_spell_outcomes59_supports.json','kicked_target_outcomes60_supports.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures'/filename).read_text())):
            base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', NAMES)
def test_canonical_complete(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_insight_all_modes_use_actual_later_player_slot_hand(cards):
    s = game(cards, ['Inscription of Insight'], opponents=['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    spell = put(s, 'Inscription of Insight', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5, 'U': 3})
    act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=1, modes=[0,1,2],
        targets=[bear.id,'p2'], target_counts=[1,1], sources=[])
    answer(s)
    token = next(c for c in s.state.cards.values() if c.token and c.name == 'Illusion')
    expected = len(s.state.zones['p2:hand'])
    assert bear.zone == 'p2:hand' and token.controller == 'p2'
    assert Plan(s.state, 'p1', cards, None).ch(token).pt == (expected, expected)
    roundtrip(s)


@pytest.mark.parametrize('name,mana', [('Inscription of Insight',{'C':5,'U':3}),('Inscription of Abundance',{'C':3,'G':2}),('Inscription of Ruin',{'C':4,'B':3})])
def test_any_number_kicked_modes_includes_actual_zero_choice(cards, name, mana):
    s = game(cards, [name])
    spell = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=1, sources=[])
    decision = s.state.rules.decision
    assert decision is not None and decision.min_choices == 0
    act(s, 'p1', type='choose', decision_id=decision.id, option_ids=[])
    answer(s)
    assert spell.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('kicked', [0,1])
def test_waste_management_conditional_native_target_groups_and_creature_count(cards, kicked):
    s = game(cards, ['Waste Management'], opponents=['Grizzly Bears','Hill Giant','Lightning Bolt'])
    bear = put(s, 'Grizzly Bears', 'graveyard', pid='p2')
    giant = put(s, 'Hill Giant', 'graveyard', pid='p2')
    other = put(s, 'Lightning Bolt', 'graveyard', pid='p2')
    spell = put(s, 'Waste Management', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':2+3*kicked,'B':1+kicked})
    act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=kicked, sources=[],
        targets=['p2'] if kicked else [bear.id,other.id], target_counts=[0,1] if kicked else [2,0])
    answer(s)
    assert bear.zone == other.zone == 'p2:exile'
    assert giant.zone == ('p2:exile' if kicked else 'p2:graveyard')
    tokens = [c for c in s.state.cards.values() if c.token and c.name == 'Rogue']
    assert len(tokens) == 1+kicked
    roundtrip(s)


@pytest.mark.parametrize('kicked', [0,1])
def test_eagles_returns_announced_targets_then_delayed_actual_count(cards, kicked):
    s = game(cards, ['The Eagles Are Coming!', 'Grizzly Bears','Llanowar Elves'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    spell = put(s, 'The Eagles Are Coming!', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':1+2*kicked,'W':1+2*kicked})
    act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=kicked, sources=[],
        targets=[bear.id,elf.id] if kicked else [bear.id], target_counts=[0,2] if kicked else [1,0])
    answer(s)
    assert bear.zone == 'p1:hand' and elf.zone == ('p1:hand' if kicked else 'p1:battlefield')
    to_phase(s, 'upkeep', 5)
    answer(s)
    tokens = [c for c in s.state.cards.values() if c.token and c.name == 'Bird Soldier']
    assert len(tokens) == 1+kicked
    roundtrip(s)


def test_waste_management_rejects_unkicked_cards_from_different_graveyards(cards):
    s = game(cards, ['Waste Management','Grizzly Bears'], opponents=['Hill Giant'])
    first = put(s, 'Grizzly Bears', 'graveyard')
    second = put(s, 'Hill Giant', 'graveyard', pid='p2')
    spell = put(s, 'Waste Management', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':2,'B':1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match='single graveyard'):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[first.id,second.id], target_counts=[2,0], sources=[])
    assert s.state.model_dump_json() == before


def test_eagles_returned_creature_tokens_count_after_they_cease(cards):
    s = game(cards, ['The Eagles Are Coming!','Raise the Alarm'])
    spell = put(s, 'Raise the Alarm', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':1,'W':1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    answer(s)
    soldiers = [c.id for c in s.state.cards.values() if c.token and c.name == 'Soldier']
    assert len(soldiers) == 2
    eagles = put(s, 'The Eagles Are Coming!', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':3,'W':3})
    act(s, 'p1', type='cast_spell', card_id=eagles.id, kicker=1, targets=soldiers, target_counts=[0,2], sources=[])
    answer(s)
    assert all(cid not in s.state.cards for cid in soldiers)
    to_phase(s, 'upkeep', 5)
    answer(s)
    assert len([c for c in s.state.cards.values() if c.token and c.name == 'Bird Soldier']) == 2
    roundtrip(s)


def test_eagles_commander_replaced_into_command_does_not_count_as_returned(cards):
    s = game(cards, ['The Eagles Are Coming!'])
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    spell = put(s, 'The Eagles Are Coming!', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':1,'W':1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[commander.id], target_counts=[1,0], sources=[])
    for _ in range(30):
        decision = s.state.rules.decision
        if decision is not None:
            assert decision.kind == 'confirm'
            act(s, decision.player, type='choose', decision_id=decision.id, option_ids=['yes'])
        elif s.state.zones['stack']:
            act(s, s.state.rules.priority, type='pass_priority')
        else:
            break
    assert commander.zone == 'p1:command'
    to_phase(s, 'upkeep', 5)
    answer(s)
    assert not any(c.token and c.name == 'Bird Soldier' for c in s.state.cards.values())
    roundtrip(s)


def test_true_cold_explicit_zero_modes_locked_before_mana_payment(cards, tmp_path):
    import subprocess
    import sys

    from app.rules import kicked_target_outcomes60
    s = game(cards, ['Inscription of Insight','Island'])
    island = put(s, 'Island', 'battlefield')
    spell = put(s, 'Inscription of Insight', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C':5,'U':2})
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=1)
    decision = s.state.rules.decision
    assert decision.min_choices == 0
    act(s, 'p1', type='choose', decision_id=decision.id, option_ids=[])
    decision = s.state.rules.decision
    assert decision.resume['step'] == 'pay_mana'
    assert decision.resume['zero_modes_object'] == s.state.rules.object_id(spell.id)
    assert decision.resume['intent']['modes'] == []
    saved = tmp_path/'payment.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
act(s,'p1',type='activate_ability',card_id=sys.argv[3],ability=0)
assert s.state.rules.decision is None
entry=s.state.rules.stack[sys.argv[4]]
assert entry.modes==[] and entry.effects==[]
answer(s)
assert s.state.cards[sys.argv[4]].zone=='p1:graveyard'
roundtrip(s)
'''
    result = subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),island.id,spell.id],
                            cwd=Path(kicked_target_outcomes60.__file__).resolve().parents[2],capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_true_cold_eagles_delayed_count_survives_returned_tokens_ceasing(cards, tmp_path):
    import subprocess
    import sys

    from app.rules import kicked_target_outcomes60
    s = game(cards, ['The Eagles Are Coming!','Raise the Alarm'])
    first = put(s,'Raise the Alarm','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    act(s,'p1',type='cast_spell',card_id=first.id,sources=[])
    answer(s)
    soldiers=[c.id for c in s.state.cards.values() if c.token and c.name=='Soldier']
    spell=put(s,'The Eagles Are Coming!','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'W':3})
    act(s,'p1',type='cast_spell',card_id=spell.id,kicker=1,targets=soldiers,target_counts=[0,2],sources=[])
    answer(s)
    assert all(cid not in s.state.cards for cid in soldiers)
    saved=tmp_path/'eagles.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
to_phase(s,'upkeep',5);answer(s)
assert len([c for c in s.state.cards.values() if c.token and c.name=='Bird Soldier'])==2
roundtrip(s)
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path)],
                          cwd=Path(kicked_target_outcomes60.__file__).resolve().parents[2],capture_output=True,text=True,timeout=90)
    assert result.returncode == 0,result.stdout+result.stderr


def test_true_cold_waste_management_kicked_player_group_and_original_card_count(cards, tmp_path):
    import subprocess
    import sys

    from app.rules import kicked_target_outcomes60
    s=game(cards,['Waste Management'],opponents=['Grizzly Bears','Hill Giant','Lightning Bolt'])
    for name in ['Grizzly Bears','Hill Giant','Lightning Bolt']:
        put(s,name,'graveyard',pid='p2')
    spell=put(s,'Waste Management','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':5,'B':2})
    saved=tmp_path/'waste.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
act(s,'p1',type='cast_spell',card_id=sys.argv[3],kicker=1,targets=['p2'],target_counts=[0,1],sources=[])
answer(s)
assert not s.state.zones['p2:graveyard']
assert len([c for c in s.state.cards.values() if c.token and c.name=='Rogue'])==2
roundtrip(s)
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),spell.id],
                          cwd=Path(kicked_target_outcomes60.__file__).resolve().parents[2],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('name,kicker,mana', [('The Eagles Are Coming!',1,{'C':3,'W':3}),('Waste Management',0,{'C':2,'B':1})])
def test_zero_native_targets_are_legal_for_kicked_eagles_or_unkicked_waste(cards, name, kicker, mana):
    s=game(cards,[name])
    spell=put(s,name,'hand')
    act(s,'p1',type='add_mana',player='p1',mana=mana)
    act(s,'p1',type='cast_spell',card_id=spell.id,kicker=kicker,targets=[],target_counts=[0,0],sources=[])
    answer(s)
    assert spell.zone=='p1:graveyard'
    if name=='The Eagles Are Coming!':
        to_phase(s,'upkeep',5)
        answer(s)
    assert not any(c.token and c.name in ('Bird Soldier','Rogue') for c in s.state.cards.values())
    roundtrip(s)


def test_eagles_ownership_not_controller_authorizes_the_target(cards):
    s=game(cards,['The Eagles Are Coming!','Grizzly Bears'],opponents=['Hill Giant'])
    own=put(s,'Grizzly Bears','battlefield')
    other=put(s,'Hill Giant','battlefield',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[own.id],player='p2')
    act(s,'p1',type='set_controller',card_ids=[other.id],player='p1')
    spell=put(s,'The Eagles Are Coming!','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,targets=[other.id],target_counts=[1,0],sources=[])
    assert s.state.model_dump_json()==before
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[own.id],target_counts=[1,0],sources=[])
    answer(s)
    assert own.zone=='p1:hand' and other.zone=='p1:battlefield'
    to_phase(s,'upkeep',5)
    answer(s)
    assert len([c for c in s.state.cards.values() if c.token and c.name=='Bird Soldier'])==1
    roundtrip(s)
