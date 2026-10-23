"""Global morph increases preserve mana and nonmana payments and other face-up methods."""

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
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Exiled Doomsayer"]
DATA = json.loads((Path(__file__).parent / "fixtures/morph_costs78_cards.json").read_text())


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,name='Gravel Slinger',owner='p1',copies=1):
    ns=[c['name'] for c in DATA]*2
    s=table(cards,ns,ns,ns)
    for pid in ['p1','p2','p3']:
        act(s,pid,type='set_prefs',hold_priority=True,response='on')
    to_phase(s,'main1',4)
    for _i in range(copies):
        c=next(c for c in s.state.cards.values() if c.name=='Exiled Doomsayer' and c.owner==owner and not c.zone.endswith(':battlefield'))
        act(s,owner,type='move',card_ids=[c.id],to={'player':owner,'zone':'battlefield'})
    c=put(s,name,'battlefield')
    act(s,'p1',type='face_down',card_ids=[c.id],face_down=True,kind='morph')
    wait_priority(s,'p1')
    return s,c


def test_canonical(cards):
    assert coverage.of_card_data(cards.resolve('Exiled Doomsayer')).level=='FULL'


@pytest.mark.parametrize('name,mana,counters',[('Gravel Slinger',{'C':3,'W':1},0),('Aerie Bowmasters',{'C':7,'G':1},1)])
def test_real_morph_megamorph_increase(cards,name,mana,counters):
    s,c=setup(cards,name)
    act(s,'p1',type='add_mana',player='p1',mana=mana)
    act(s,'p1',type='turn_face_up',card_id=c.id)
    assert not s.state.cards[c.id].face_down
    assert s.state.cards[c.id].counters.get('+1/+1',0)==counters
    assert sum(s.state.players['p1'].mana.values())==0


def test_opposing_doomsayer_also_taxes(cards):
    s,c=setup(cards,owner='p2')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError,match='Not enough mana'):
        act(s,'p1',type='turn_face_up',card_id=c.id)
    assert s.state.model_dump(mode='json')==before
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='turn_face_up',card_id=c.id)
    assert not s.state.cards[c.id].face_down


def test_two_sources_stack(cards):
    s,c=setup(cards,copies=2)
    act(s,'p1',type='add_mana',player='p1',mana={'C':5,'W':1})
    act(s,'p1',type='turn_face_up',card_id=c.id)
    assert not s.state.cards[c.id].face_down
    assert sum(s.state.players['p1'].mana.values())==0


def test_nonmana_life_increase_preserves_original_payment(cards):
    s,c=setup(cards,'Zombie Cutthroat')
    life=s.state.players['p1'].life
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError,match='mana|pay'):
        act(s,'p1',type='turn_face_up',card_id=c.id)
    assert s.state.model_dump(mode='json')==before
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='turn_face_up',card_id=c.id)
    assert not s.state.cards[c.id].face_down
    assert s.state.players['p1'].life==life-5
    assert sum(s.state.players['p1'].mana.values())==0


def test_nonmana_discard_adds_mana_and_pays_exact_chosen_cost(cards):
    s,c=setup(cards,'Gathan Raiders')
    hand=put(s,'Forest','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='turn_face_up',card_id=c.id)
    d=s.state.rules.decision
    if d:
        target=next(o for o in d.options if o.card_id==hand.id)
        act(s,'p1',type='choose',decision_id=d.id,option_ids=[target.id])
    assert not s.state.cards[c.id].face_down
    assert s.state.cards[hand.id].zone=='p1:graveyard'
    assert sum(s.state.players['p1'].mana.values())==0

def test_cast_face_down_still_only_three(cards):
    s,c=setup(cards)
    act(s,'p1',type='move',card_ids=[c.id],to={'zone':'hand'})
    act(s,'p1',type='add_mana',player='p1',mana={'C':3})
    act(s,'p1',type='cast_spell',card_id=c.id,face_down=True,sources=[])
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)
    assert s.state.cards[c.id].face_down and s.state.cards[c.id].zone=='p1:battlefield'


def test_manifest_original_mana_cost_does_not_get_morph_increase(cards):
    s,c=setup(cards,'Zombie Cutthroat')
    act(s,'p1',type='face_down',card_ids=[c.id],face_down=False)
    act(s,'p1',type='face_down',card_ids=[c.id],face_down=True,kind='manifest')
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'B':2})
    act(s,'p1',type='turn_face_up',card_id=c.id,method='mana_cost')
    assert not s.state.cards[c.id].face_down
    assert s.state.players['p1'].life==40
    assert sum(s.state.players['p1'].mana.values())==0


def test_disguise_cost_is_not_morph(cards):
    s,c=setup(cards,'Fugitive Codebreaker')
    act(s,'p1',type='add_mana',player='p1',mana={'C':5,'R':1})
    act(s,'p1',type='turn_face_up',card_id=c.id,method='disguise')
    assert not s.state.cards[c.id].face_down
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)


def test_source_departure_removes_increase(cards):
    s,c=setup(cards)
    source=next(x for x in s.state.cards.values() if x.name=='Exiled Doomsayer' and x.zone=='p1:battlefield')
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'graveyard'})
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    act(s,'p1',type='turn_face_up',card_id=c.id)
    assert not s.state.cards[c.id].face_down
    assert sum(s.state.players['p1'].mana.values())==0


def test_reveal_nonmana_cost_increase_preserves_public_reveal(cards):
    s,c=setup(cards,'Ruthless Ripper')
    reveal=put(s,'Zombie Cutthroat','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='turn_face_up',card_id=c.id)
    d=s.state.rules.decision
    if d and any(o.card_id==reveal.id for o in d.options):
        target=next(o for o in d.options if o.card_id==reveal.id)
        act(s,'p1',type='choose',decision_id=d.id,option_ids=[target.id])
    assert not s.state.cards[c.id].face_down
    assert s.state.cards[reveal.id].zone=='p1:hand'
    assert sum(s.state.players['p1'].mana.values())==0
    answer(s)


def test_true_cold_pending_discard_keeps_increase_and_nonmana_selection(cards,tmp_path):
    import os
    import subprocess
    import sys
    s,c=setup(cards,'Gathan Raiders')
    hand=put(s,'Forest','hand')
    put(s,'Island','hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='turn_face_up',card_id=c.id)
    assert s.state.rules.decision is not None
    saved=tmp_path/'morph.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
saved,database,cid,discard=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
s.view('p1');s.view('p2')
d=s.state.rules.decision
pick=next(o for o in d.options if o.card_id==discard)
act(s,'p1',type='choose',decision_id=d.id,option_ids=[pick.id])
assert not s.state.cards[cid].face_down
assert s.state.cards[discard].zone=='p1:graveyard'
assert sum(s.state.players['p1'].mana.values())==0
GameState.model_validate_json(s.state.model_dump_json())
'''
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),c.id,hand.id],capture_output=True,text=True,env=os.environ.copy())
    assert run.returncode==0,run.stdout+run.stderr
