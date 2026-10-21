"""Native targeting source kinds, aggregate watches and copied backup provenance."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

NAMES = ['Erdwal Illuminator', 'Valiant Rescuer', 'Crawling Sensation']
DATA = json.loads((Path(__file__).parent / 'fixtures/first_event_receipts78_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, source=None, turn=4):
    names = [c['name'] for c in DATA] + ['Grizzly Bears','Llanowar Elves','Island']
    s = table(cards,names,names,names)
    start(s,turn=turn)
    act(s,'p1',type='set_prefs',hold_priority=True)
    if source:
        put(s,source,'battlefield')
    return s


def tokens(s,name):
    return [c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield' and c.name==name]


def investigations(s):
    return [e for e in s.state.rules.turn_log.facts if e.kind=='investigate']


def test_investigate_twice_first_only_extra_once(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards,'Erdwal Illuminator')
    cast(s,'Wavesifter',{'C':3,'G':1,'U':1})
    assert len(tokens(s,'Clue'))==3
    assert len(investigations(s))==3


def test_direct_clue_creation_is_not_investigation(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards,'Erdwal Illuminator')
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Cunning Maneuver',{'C':1,'R':1},[bear.id])
    assert len(tokens(s,'Clue'))==1 and not investigations(s)
    cast(s,'Secrets of the Key',{'U':1})
    assert len(tokens(s,'Clue'))==3 and len(investigations(s))==2


@pytest.mark.parametrize('replacement', ['Parallel Lives','Academy Manufactor'])
def test_investigation_counts_actions_not_replaced_token_quantity(cards,replacement):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards,'Erdwal Illuminator')
    put(s,replacement,'battlefield')
    cast(s,'Secrets of the Key',{'U':1})
    assert len(investigations(s))==2
    assert len(tokens(s,'Clue'))==(4 if replacement=='Parallel Lives' else 2)
    if replacement=='Academy Manufactor':
        assert len(tokens(s,'Food'))==2 and len(tokens(s,'Treasure'))==2


def test_first_investigation_before_source_entry_stays_first(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards)
    cast(s,'Secrets of the Key',{'U':1})
    cast(s,'Erdwal Illuminator',{'C':1,'U':1})
    cast(s,'Wavesifter',{'C':3,'G':1,'U':1})
    assert len(tokens(s,'Clue'))==3 and len(investigations(s))==3


def cycle(s,name,pool):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave7b_activation import ability_index
    wait_priority(s,'p1')
    source=put(s,name,'hand')
    mana(s,**pool)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'Cycling'),sources=[])
    settle(s)
    return source


def test_two_native_cycles_trigger_one_soldier_and_printed_self_cycle_draws(cards):
    s=setup(cards,'Valiant Rescuer')
    cycle(s,'Remote Isle',{'C':2})
    cycle(s,'Barren Moor',{'B':1})
    assert len(tokens(s,'Human Soldier'))==1
    before=len(s.state.zones['p1:hand'])
    source=cycle(s,'Valiant Rescuer',{'C':2})
    assert source.zone=='p1:graveyard'
    assert len(s.state.zones['p1:hand'])==before+1
    assert len(tokens(s,'Human Soldier'))==1


def test_cycle_before_source_entry_stays_first(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards)
    cycle(s,'Remote Isle',{'C':2})
    cast(s,'Valiant Rescuer',{'C':1,'W':1})
    cycle(s,'Barren Moor',{'B':1})
    assert not tokens(s,'Human Soldier')


def top(s,name):
    c=put(s,name,'hand')
    act(s,'p1',type='move',card_ids=[c.id],to={'player':'p1','zone':'library'},index=0)
    return c


def mill_two(s):
    source=put(s,'Millstone','battlefield')
    top(s,'Forest')
    top(s,'Island')
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=['p1'],sources=[])
    settle(s)


def test_native_two_land_mill_simultaneous_triggers_once(cards):
    s=setup(cards,'Crawling Sensation')
    mill_two(s)
    assert len(tokens(s,'Insect'))==1


def test_prior_native_land_arrivals_before_source_entry_suppress_later_batch(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards)
    mill_two(s)
    cast(s,'Crawling Sensation',{'C':2,'G':1})
    put(s,'Forest','battlefield')
    put(s,'Island','battlefield')
    cast(s,'Armageddon',{'C':3,'W':1})
    assert not tokens(s,'Insect')


def test_two_native_land_deaths_same_batch_trigger_once(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards,'Crawling Sensation')
    put(s,'Forest','battlefield')
    put(s,'Island','battlefield')
    cast(s,'Armageddon',{'C':3,'W':1})
    assert len(tokens(s,'Insect'))==1


@pytest.mark.parametrize('name',NAMES)
def test_legacy_unknown_first_event_requires_manual_notice_without_fabricated_trigger(cards,name):
    from app.game.session import GameSession
    from app.game.state import GameState
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards,name)
    raw=s.state.model_dump()
    raw['rules'].pop('first_event_history_turn78',None)
    raw['rules'].pop('first_event_notices78',None)
    s=GameSession(GameState.model_validate(raw),cards=cards)
    if name=='Erdwal Illuminator':
        cast(s,'Secrets of the Key',{'U':1})
        assert len(tokens(s,'Clue'))==1
    elif name=='Valiant Rescuer':
        cycle(s,'Remote Isle',{'C':2})
        assert not tokens(s,'Human Soldier')
    else:
        mill_two(s)
        assert not tokens(s,'Insect')
    d=s.state.rules.decision
    assert d is not None and d.kind=='manual_resolution'
    assert 'earlier actions this turn are unknown' in d.prompt
    assert not any(e.name==name for e in s.state.rules.stack.values())
    cold_legacy_notice(s,cards,name)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['done'])
    settle(s)
    if name=='Erdwal Illuminator':
        cast(s,'Wavesifter',{'C':3,'G':1,'U':1})
        assert len(tokens(s,'Clue'))==3
    elif name=='Valiant Rescuer':
        cycle(s,'Barren Moor',{'B':1})
        assert not tokens(s,'Human Soldier')
    else:
        put(s,'Forest','battlefield')
        put(s,'Island','battlefield')
        cast(s,'Armageddon',{'C':3,'W':1})
        assert not tokens(s,'Insect')
    assert s.state.rules.decision is None
    from tests.test_rules_wave30m_durations import to_phase
    if name=='Crawling Sensation':
        put(s,'Forest','battlefield')
        put(s,'Island','battlefield')
    to_phase(s,'main1',turn=5)
    assert s.state.rules.first_event_history_turn78==5
    if name=='Erdwal Illuminator':
        cast(s,'Deduce',{'C':1,'U':1})
        assert len(tokens(s,'Clue'))==5
    elif name=='Valiant Rescuer':
        cycle(s,'Remote Isle',{'C':2})
        assert len(tokens(s,'Human Soldier'))==1
    else:
        cast(s,'Armageddon',{'C':3,'W':1},pid='p2')
        assert len(tokens(s,'Insect'))==1


@pytest.mark.parametrize('name,pool',[('Erdwal Illuminator',{'C':1,'U':1}),('Valiant Rescuer',{'C':1,'W':1}),('Crawling Sensation',{'C':2,'G':1})])
def test_paid_whole_source_entry(cards,name,pool):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards)
    source=cast(s,name,pool)
    assert source.zone=='p1:battlefield'


@pytest.mark.parametrize('accept',[True,False])
def test_sensation_printed_upkeep_optional_mill(cards,accept):
    from tests.test_rules_wave30m_durations import to_phase
    s=setup(cards,'Crawling Sensation')
    top(s,'Forest')
    top(s,'Island')
    to_phase(s,'upkeep',turn=7)
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes' if accept else 'no'])
    settle(s)
    assert len(tokens(s,'Insect'))==(1 if accept else 0)


def test_illuminator_printed_flying_blocks_ground_creature(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import to_phase
    from tests.test_rules_wave30p_combat import attack, block
    s=setup(cards,'Erdwal Illuminator')
    source=next(c for c in s.state.cards.values() if c.name=='Erdwal Illuminator' and c.owner=='p1')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    to_phase(s,'declare_attackers',turn=7)
    attack(s,(source,'p2'))
    to_phase(s,'declare_blockers',turn=7)
    with pytest.raises(ActionError):
        block(s,'p2',(bear,source))


def test_native_declaration_controller_count_investigates_separately(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards)
    put(s,'Erdwal Illuminator','battlefield','p2')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    foreign=put(s,'Grizzly Bears','battlefield','p3')
    act(s,'p3',type='set_controller',card_ids=[foreign.id],player='p2')
    cast(s,'Declaration in Stone',{'C':1,'W':1},[bear.id])
    assert bear.zone=='p2:exile' and foreign.zone=='p3:exile'
    clues=[c for c in s.state.cards.values() if c.is_token and c.zone=='p2:battlefield' and c.name=='Clue']
    assert len(clues)==3
    assert len(investigations(s))==3 and all(f.player=='p2' for f in investigations(s))


@pytest.mark.parametrize('name',NAMES)
def test_genuine_cold_investigation_replacement_or_pending_first_trigger(cards,tmp_path,name):
    import subprocess
    import sys

    import app
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    from tests.test_rules_wave7b_activation import ability_index
    s=setup(cards,name)
    if name=='Erdwal Illuminator':
        put(s,'Chatterfang, Squirrel General','battlefield')
        put(s,'Academy Manufactor','battlefield')
        cast(s,'Secrets of the Key',{'U':1})
        assert s.state.rules.decision is not None
    elif name=='Valiant Rescuer':
        c=put(s,'Remote Isle','hand')
        mana(s,C=2)
        act(s,'p1',type='activate_ability',card_id=c.id,ability=ability_index(s,c,'Cycling'),sources=[])
        assert s.state.rules.stack
    else:
        source=put(s,'Millstone','battlefield')
        top(s,'Forest')
        top(s,'Island')
        mana(s,C=2)
        act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=['p1'],sources=[])
        for _ in range(12):
            if not any(e.source_card==source.id for e in s.state.rules.stack.values()):
                break
            act(s,s.state.rules.priority,type='pass_priority')
        assert any(e.name==name for e in s.state.rules.stack.values())
    saved=tmp_path/'first-event.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
name=sys.argv[3]
for _ in range(40):
 settle(s)
 d=s.state.rules.decision
 if d is None:break
 assert d.kind!='manual_resolution',d.prompt
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options][:max(1,d.min_choices)])
def count(n):return sum(c.is_token and c.zone=='p1:battlefield' and c.name==n for c in s.state.cards.values())
if name=='Erdwal Illuminator':
 assert count('Clue')==2 and count('Food')==2 and count('Treasure')==2
 assert count('Squirrel') in (2,4,6)
 assert sum(f.kind=='investigate' for f in s.state.rules.turn_log.facts)==2
elif name=='Valiant Rescuer':assert count('Human Soldier')==1
else:assert count('Insect')==1
assert s.state.rules.decision is None
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name],capture_output=True,text=True,
                          timeout=90,cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode==0,result.stdout+result.stderr



def cold_legacy_notice(s,cards,name):
    import subprocess
    import sys
    import tempfile

    import app

    with tempfile.TemporaryDirectory() as directory:
        saved=Path(directory)/'notice.json'
        saved.write_text(s.state.model_dump_json())
        code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
d=s.state.rules.decision
assert d is not None and d.kind=='manual_resolution'
assert s.state.rules.first_event_history_turn78 is None
assert len(s.state.rules.first_event_notices78)==1
act(s,d.player,type='choose',decision_id=d.id,option_ids=['done'])
settle(s)
assert s.state.rules.decision is None
name=sys.argv[3]
expected='Clue' if name=='Erdwal Illuminator' else 'Human Soldier' if name=='Valiant Rescuer' else 'Insect'
n=sum(c.is_token and c.zone=='p1:battlefield' and c.name==expected for c in s.state.cards.values())
assert n==(1 if name=='Erdwal Illuminator' else 0)
'''
        result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name],capture_output=True,text=True,
                              timeout=90,cwd=Path(app.__file__).resolve().parents[1])
        assert result.returncode==0,result.stdout+result.stderr



@pytest.mark.parametrize('name',NAMES)
def test_trustworthy_fresh_first_turn_native_first_action(cards,name):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards,name,turn=1)
    assert s.state.turn.number==1 and s.state.rules.first_event_history_turn78==1
    if name=='Erdwal Illuminator':
        cast(s,'Secrets of the Key',{'U':1})
        assert len(tokens(s,'Clue'))==2
    elif name=='Valiant Rescuer':
        cycle(s,'Remote Isle',{'C':2})
        assert len(tokens(s,'Human Soldier'))==1
    else:
        mill_two(s)
        assert len(tokens(s,'Insect'))==1
    assert s.state.rules.decision is None


def test_loading_first_turn_without_marker_preserves_unknown_history(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s=setup(cards,'Erdwal Illuminator',turn=1)
    raw=s.state.model_dump()
    raw['rules'].pop('first_event_history_turn78',None)
    s=GameSession(GameState.model_validate(raw),cards=cards)
    assert s.state.rules.first_event_history_turn78 is None
    cast(s,'Secrets of the Key',{'U':1})
    assert s.state.rules.decision is not None and s.state.rules.decision.kind=='manual_resolution'
    assert len(tokens(s,'Clue'))==1
