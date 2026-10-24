"""Native alternative and upkeep taxes retain actual payers and affected objects."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Cosmic Horror','Demonic Hordes']
DATA = json.loads((Path(__file__).parent / 'fixtures/upkeep_consequences81_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Lightning Bolt', 'Counterspell', 'Forest', 'Island', 'Mountain']


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


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids, resolve=True):
    d = s.state.rules.decision
    assert d
    result = act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    if resolve:
        settle(s)
    return result


def cast(s, name, targets=(), pid='p1', resolve=True, **extra):
    c = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana={'C': 30, 'W': 4, 'U': 5, 'R': 2, 'B': 3, 'G': 3})
    act(s, pid, type='cast_spell', card_id=c.id, targets=list(targets), sources=[], **extra)
    if resolve:
        settle(s)
    return c


@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def upkeep_game(cards,name):
    s=game(cards)
    source=cast(s,name)
    to_phase(s,'upkeep',4)
    return s,source


@pytest.mark.parametrize('protection,expected_zone,life',[(None,'graveyard',33),('Heroic Intervention','battlefield',40),('Regenerate','battlefield',40),('Rest in Peace','exile',33)])
def test_horror_actual_destroyed_receipt_and_native_damage(cards,protection,expected_zone,life):
    s=game(cards)
    source=cast(s,NAMES[0])
    if protection=='Rest in Peace':
        cast(s,protection)
    to_phase(s,'upkeep',4)
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'B':3})
    if protection in ('Heroic Intervention','Regenerate'):
        cast(s,protection,[source.id] if protection=='Regenerate' else [])
    else:
        settle(s)
    assert s.state.rules.decision and s.state.rules.decision.player=='p1'
    choose(s,['decline'])
    assert s.state.cards[source.id].zone=='p1:'+expected_zone
    assert s.state.players['p1'].life==life
    roundtrip(s)


def test_horror_paying_upkeep_has_no_destruction_or_damage(cards):
    s,source=upkeep_game(cards,NAMES[0])
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'B':3})
    settle(s)
    choose(s,['pay'])
    assert s.state.cards[source.id].zone=='p1:battlefield' and s.state.players['p1'].life==40
    roundtrip(s)


def test_hordes_controller_chooses_opponent_then_opponent_chooses_own_land(cards):
    s=game(cards)
    lands=[put(s,n,'battlefield') for n in ['Forest','Island']]
    foreign=put(s,'Island','battlefield','p3')
    source=cast(s,NAMES[1])
    to_phase(s,'upkeep',4)
    act(s,'p1',type='add_mana',player='p1',mana={'B':3})
    settle(s)
    choose(s,['decline'])
    d=s.state.rules.decision
    assert d and d.player=='p1' and {o.id for o in d.options}=={'p2','p3'}
    assert s.state.cards[source.id].tapped
    choose(s,['p3'])
    d=s.state.rules.decision
    assert d and d.player=='p3' and {o.id for o in d.options}=={c.id for c in lands}
    choose(s,[lands[1].id])
    assert s.state.cards[lands[1].id].zone=='p1:graveyard'
    assert s.state.cards[lands[0].id].zone=='p1:battlefield' and s.state.cards[foreign.id].zone=='p3:battlefield'
    roundtrip(s)

@pytest.mark.parametrize('leave', [False,True])
def test_hordes_paying_or_losing_original_source_preserves_native_choice_rules(cards,leave):
    s=game(cards)
    lands=[put(s,n,'battlefield') for n in ['Forest','Island']]
    source=cast(s,NAMES[1])
    to_phase(s,'upkeep',4)
    act(s,'p1',type='add_mana',player='p1',mana={'B':3})
    settle(s)
    if leave:
        act(s,'p1',type='move',card_ids=[source.id],to={'zone':'exile'})
        choose(s,['decline'])
        choose(s,['p2'])
        assert s.state.rules.decision.player=='p2'
        choose(s,[lands[0].id])
        assert s.state.cards[lands[0].id].zone=='p1:graveyard'
    else:
        choose(s,['pay'])
        assert not s.state.cards[source.id].tapped
        assert all(s.state.cards[c.id].zone=='p1:battlefield' for c in lands)
    roundtrip(s)


def test_horror_departed_original_is_not_destroyed_and_deals_no_damage(cards):
    s,source=upkeep_game(cards,NAMES[0])
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'B':3})
    settle(s)
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'exile'})
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'battlefield'})
    choose(s,['decline'])
    assert s.state.cards[source.id].zone=='p1:battlefield' and s.state.players['p1'].life==40
    roundtrip(s)

@pytest.mark.parametrize('name',NAMES)
def test_fresh_process_pending_upkeep_or_opponents_land_choice(cards,tmp_path,name):
    import subprocess
    import sys
    s=game(cards)
    lands=[put(s,n,'battlefield') for n in ['Forest','Island']]
    source=cast(s,name)
    to_phase(s,'upkeep',4)
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'B':3})
    settle(s)
    if name==NAMES[1]:
        choose(s,['decline'])
        choose(s,['p3'])
    saved=tmp_path/'upkeep.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
name,source,land,other=sys.argv[3:]
d=s.state.rules.decision
assert d and d.kind!='manual_resolution'
if name=='Cosmic Horror':
 assert d.player=='p1'
 answer='decline'
else:
 assert d.player=='p3' and {o.id for o in d.options}=={land,other}
 answer=land
act(s,d.player,type='choose',decision_id=d.id,option_ids=[answer])
settle(s)
if name=='Cosmic Horror':
 assert s.state.cards[source].zone=='p1:graveyard' and s.state.players['p1'].life==33
else:
 assert s.state.cards[source].tapped and s.state.cards[land].zone=='p1:graveyard' and s.state.cards[other].zone=='p1:battlefield'
assert GameState.model_validate_json(s.state.model_dump_json()).model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name,source.id,lands[0].id,lands[1].id],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
