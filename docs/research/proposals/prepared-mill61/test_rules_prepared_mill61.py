"""Native public milling and delayed optional Equipment continuations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

AIR, REQUEST = 'Airlift Chaplain', 'Unexpected Request'

@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/prepared_mill61_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='oc59', number=str(i), **{k:v for k,v in c.items() if k not in ('name','set_code','number')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def setup(cards):
    names = [AIR, REQUEST, 'Eden, Seat of the Sanctum', 'Blood Spatter Analysis', 'Dauthi Voidwalker', 'Crawling Sensation', 'Grizzly Bears', 'Hill Giant', 'Plains', 'Forest', 'Bonesplitter', 'Sol Ring', 'Rest in Peace', 'Lightning Bolt', 'Disperse', 'Darksteel Colossus', 'Progenitus']
    s = table(cards, names, names, names)
    to_phase(s, 'main1', 1)
    act(s, 'p1', type='add_mana', player='p1', mana={c:30 for c in ['C','W','U','B','R','G']})
    return s

def answer(s, ids):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)

def cast(s, name, **kwargs):
    source = put(s, name, 'hand')
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[], **kwargs)
    settle(s)
    return source

def top(s, names):
    cards = [put(s, name, 'hand') for name in names]
    for c in reversed(cards):
        act(s, 'p1', type='move', card_ids=[c.id], to={'player':'p1','zone':'library'}, position='top')
    return cards



@pytest.mark.parametrize('name',['Eden, Seat of the Sanctum','Blood Spatter Analysis'])
@pytest.mark.parametrize('outcome',['exile','library:shuffle'])
def test_native_existing_mill_continuation_waits_for_all_replacements(cards,name,outcome):
    s,source,target=prepare_existing_boundary(cards,name)
    d=s.state.rules.decision
    assert d and d.resume['step']=='prepared_mill61'
    assert source.zone=='p1:battlefield'
    if name=='Blood Spatter Analysis':
        assert source.counters=={'bloodstain':4}
    answer(s,[next(o.id for o in d.options if o.label.endswith(': '+outcome))])
    if name=='Eden, Seat of the Sanctum':
        d=s.state.rules.decision
        assert d and 'pay' in [o.id for o in d.options]
        answer(s,['pay'])
    d=s.state.rules.decision
    assert d and d.resume['step']=='trigger_target' and target.id in [o.id for o in d.options]
    answer(s,[target.id])
    assert source.zone=='p1:exile' and target.zone=='p1:hand'
    roundtrip(s)


def prepare_existing_boundary(cards,name):
    s=setup(cards)
    source=put(s,name,'hand')
    if name=='Eden, Seat of the Sanctum':
        act(s,'p1',type='play_land',card_id=source.id)
    else:
        act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
        settle(s)
        act(s,'p1',type='counter',card_ids=[source.id],kind='bloodstain',delta=4)
    target=put(s,'Grizzly Bears','graveyard')
    put(s,'Dauthi Voidwalker','battlefield','p2')
    if name=='Eden, Seat of the Sanctum':
        top(s,['Darksteel Colossus','Forest'])
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    else:
        victim=put(s,'Grizzly Bears','battlefield','p2')
        bolt=put(s,'Lightning Bolt','hand')
        top(s,['Darksteel Colossus'])
        act(s,'p1',type='cast_spell',card_id=bolt.id,targets=[victim.id],sources=[])
    settle(s)
    return s,source,target


@pytest.mark.parametrize('name',['Eden, Seat of the Sanctum','Blood Spatter Analysis'])
def test_genuine_cold_pending_replacement_then_existing_continuation(cards,tmp_path,name):
    import os
    import subprocess
    import sys
    s,source,target=prepare_existing_boundary(cards,name)
    d=s.state.rules.decision
    assert d and d.resume['step']=='prepared_mill61'
    saved=tmp_path/'quality61.json'
    saved.write_text(s.state.model_dump_json())
    code=r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
def choose(ids):
 d=s.state.rules.decision;assert d
 act(s,d.player,type='choose',decision_id=d.id,option_ids=ids);settle(s)
d=s.state.rules.decision;assert d and d.resume['step']=='prepared_mill61'
choose([next(o.id for o in d.options if o.label.endswith(': exile'))])
if sys.argv[3]=='Eden, Seat of the Sanctum':choose(['pay'])
d=s.state.rules.decision;assert d and d.resume['step']=='trigger_target'
choose([sys.argv[5]])
assert s.state.cards[sys.argv[4]].zone=='p1:exile' and s.state.cards[sys.argv[5]].zone=='p1:hand'
roundtrip(s)
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name,source.id,target.id],capture_output=True,text=True,timeout=60,env=os.environ.copy())
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('rip',[True,False])
def test_public_replacement_refs_do_not_invent_mill_facts_or_first_graveyard_trigger(cards,rip):
    from app.rules import history
    from app.rules.plan import Plan
    s=setup(cards)
    put(s,'Crawling Sensation','battlefield')
    source=put(s,'Eden, Seat of the Sanctum','hand')
    act(s,'p1',type='play_land',card_id=source.id)
    if rip:
        cast(s,'Rest in Peace')
        milled=top(s,['Darksteel Colossus','Forest'])
    else:
        milled=top(s,['Plains','Forest'])
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    settle(s)
    if rip:
        d=s.state.rules.decision
        assert d and d.resume['step']=='prepared_mill61'
        answer(s,[next(o.id for o in d.options if o.label.endswith(': exile'))])
    d=s.state.rules.decision
    assert d and 'decline' in [o.id for o in d.options]
    assert not [c for c in s.state.cards.values() if c.is_token and c.name=='Insect']
    answer(s,['decline'])
    insects=[c for c in s.state.cards.values() if c.is_token and c.name=='Insect' and c.zone=='p1:battlefield']
    assert len(insects)==(0 if rip else 1)
    facts=[f for f in history.log_for(Plan(s.state,'p1',cards,None)).facts if f.kind=='mill']
    assert len(facts)==(0 if rip else 2)
    assert all(c.zone==('p1:exile' if rip else 'p1:graveyard') for c in milled)
    roundtrip(s)


def test_prepared_mill_rejects_a_new_incarnation_in_an_imported_pending_frame(cards):
    from app.game.errors import ActionError
    from app.game.session import GameSession
    from app.game.state import GameState
    s,source,target=prepare_existing_boundary(cards,'Eden, Seat of the Sanctum')
    raw=s.state.model_dump(mode='json')
    selected=raw['rules']['decision']['resume']['request']['before61'][0]
    # Corrupt only the frozen selection's OID; the native state still contains
    # the current card. The saved continuation must not silently adopt it.
    selected['object_id'] += '.unrelated'
    other=GameSession(GameState.model_validate(raw),cards=cards)
    d=other.state.rules.decision
    with pytest.raises(ActionError,match='selected library object changed'):
        act(other,d.player,type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.label.endswith(': exile'))])
