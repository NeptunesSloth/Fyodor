"""Real flashback-selector collateral: Rootcoil Creeper and Seize the Storm."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/flashback_collateral32_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='fbc',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=['Rootcoil Creeper','Seize the Storm','Firebolt','Think Twice','Visions of Glory','Opt','Grizzly Bears','Sol Ring']
    return table(cards,ns,ns,ns)

@pytest.mark.parametrize('name',['Rootcoil Creeper','Seize the Storm'])
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_seize_actual_token_cda_counts_own_gy_and_owned_exile_and_changes_controller(cards):
    s=game(cards)
    own=put(s,'Firebolt','exile')
    enemy=put(s,'Firebolt','exile','p2')
    put(s,'Opt','graveyard')
    put(s,'Opt','graveyard','p2')
    nonflash=put(s,'Grizzly Bears','exile')
    source=put(s,'Seize the Storm','hand')
    mana(s,C=4,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    token=next(c for c in s.state.cards.values() if c.token and c.name=='Elemental' and c.zone=='p1:battlefield')
    assert chars(s,token).pt==(3,3) # Opt + resolving Seize in GY + owned exiled Firebolt.
    assert 'trample' in chars(s,token).keywords
    put(s,'Firebolt','hand')
    assert chars(s,token).pt==(2,2)
    act(s,'p1',type='set_controller',card_ids=[token.id],player='p2')
    assert chars(s,s.state.cards[token.id]).pt==(2,2) # p2's Opt and exiled Firebolt.
    assert s.state.cards[own.id].zone=='p1:hand'
    assert s.state.cards[enemy.id].zone=='p2:exile' and s.state.cards[nonflash.id].zone=='p1:exile'
    roundtrip(s)


def test_seize_zero_during_resolution_survives_then_flashback_counts_exile_once(cards):
    s=game(cards)
    source=put(s,'Seize the Storm','hand')
    # Remove all other cards from this player's graveyard for the empty-CDA baseline.
    assert not s.state.zones['p1:graveyard']
    mana(s,C=4,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    token=next(c for c in s.state.cards.values() if c.token and c.name=='Elemental' and c.zone=='p1:battlefield')
    assert chars(s,token).pt==(1,1)
    mana(s,C=6,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:exile'
    tokens=[c for c in s.state.cards.values() if c.token and c.name=='Elemental' and c.zone=='p1:battlefield']
    # Casting from the graveyard removes the original token's sole count;
    # it dies before the spell resolves. The replacement token sees exile.
    assert len(tokens)==1 and tokens[0].id!=token.id
    assert chars(s,tokens[0]).pt==(1,1)
    roundtrip(s)


def ready_creeper(cards):
    s=game(cards)
    source=put(s,'Rootcoil Creeper','battlefield')
    to_phase(s,'main1',turn=4)
    return s,source


def test_creeper_restricted_mana_pays_graveyard_spell_not_hand_spell(cards):
    s,source=ready_creeper(cards)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,mana_choice='U')
    spell=put(s,'Think Twice','hand')
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    assert s.state.model_dump(mode='json')==before
    spell=put(s,'Think Twice','graveyard')
    mana(s,C=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[])
    settle(s)
    assert s.state.cards[spell.id].zone=='p1:exile'
    assert not any(mana_pool(s).values())
    roundtrip(s)


def test_creeper_target_filter_cost_and_exact_own_flashback(cards):
    s,source=ready_creeper(cards)
    own=put(s,'Visions of Glory','exile')
    enemy=put(s,'Firebolt','exile','p2')
    wrong=put(s,'Grizzly Bears','exile')
    mana(s,G=1,U=1)
    for target in [enemy,wrong]:
        with pytest.raises(ActionError):
            act(s,'p1',type='activate_ability',card_id=source.id,ability=2,targets=[target.id],sources=[])
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2,targets=[own.id],sources=[])
    assert s.state.cards[source.id].zone=='p1:exile'
    settle(s)
    assert s.state.cards[own.id].zone=='p1:hand'
    assert not any(mana_pool(s).values())
    roundtrip(s)


def test_creeper_target_announcement_cold_resume_pays_once(cards,tmp_path):
    import subprocess
    import sys

    s,source=ready_creeper(cards)
    own=put(s,'Visions of Glory','exile')
    put(s,'Firebolt','exile')
    put(s,'Firebolt','exile','p2')
    mana(s,G=1,U=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2,sources=[])
    d=s.state.rules.decision
    assert d and {o.id for o in d.options if o.id!='cancel'}=={own.id,next(c.id for c in s.state.cards.values() if c.name=='Firebolt' and c.owner=='p1')}
    saved=tmp_path/'creeper.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle
save,db,source,target=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[target]})
settle(s)
assert s.state.cards[source].zone=='p1:exile'
assert s.state.cards[target].zone=='p1:hand'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,own.id],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_seize_cda_recomputed_from_current_zones_in_fresh_process(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    fire=put(s,'Firebolt','hand')
    put(s,'Opt','graveyard')
    source=put(s,'Seize the Storm','hand')
    mana(s,C=4,R=1)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    token=next(c for c in s.state.cards.values() if c.token and c.name=='Elemental' and c.zone=='p1:battlefield')
    assert chars(s,token).pt==(2,2)
    saved=tmp_path/'seize.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_wave6c_tokens_pumps import chars
save,db,token,fire=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
assert chars(s,s.state.cards[token]).pt==(2,2)
s.perform('p1',{'type':'move','card_ids':[fire],'to':{'player':'p1','zone':'exile'}})
assert chars(s,s.state.cards[token]).pt==(3,3)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),token.id,fire.id],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('color',['B','W'])
def test_creeper_unrestricted_mana_ability_is_separate_from_restricted_one(cards,color):
    s,source=ready_creeper(cards)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,mana_choice=color)
    assert mana_pool(s).get(color)==1
    assert s.state.cards[source.id].tapped
    roundtrip(s)
