"""Canonical exact-target delayed watches, event batching and source/controller identity."""

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
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/watch35_collateral_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="bd35", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/watch35_collateral_cards.json").read_text()
        )
    ]
    return table(cards, names, names, names)


NAMES = ['Paladin of Prahv','Seasinger']

@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_paladin_actual_damage_trigger_and_source_leaving(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    paladin=put(s,'Paladin of Prahv','battlefield')
    start(s)
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(paladin,'p2'))
    to_phase(s,'combat_damage',turn=4)
    settle(s)
    assert s.state.players['p2'].life==37
    assert s.state.players['p1'].life==43
    roundtrip(s)


def forecast_setup(cards):
    s=setup(cards)
    tim=put(s,'Prodigal Sorcerer','battlefield')
    paladin=put(s,'Paladin of Prahv','hand')
    act(s,'p1',type='set_prefs',stops_my_turn=['upkeep'])
    start(s,turn=1)
    to_phase(s,'upkeep',turn=4)
    mana(s,W=1,C=1)
    return s,tim,paladin


def test_paladin_forecast_upkeep_once_per_turn_and_bound_damage(cards):
    s,tim,paladin=forecast_setup(cards)
    act(s,'p1',type='activate_ability',card_id=paladin.id,ability=1,targets=[tim.id],target_counts=[1])
    settle(s)
    assert s.state.cards[paladin.id].zone=='p1:hand'
    assert not s.state.cards[paladin.id].revealed_to
    mana(s,W=1,C=1)
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=paladin.id,ability=1,targets=[tim.id],target_counts=[1])
    act(s,'p1',type='activate_ability',card_id=tim.id,ability=0,targets=['p2'],target_counts=[1])
    settle(s)
    assert s.state.players['p1'].life==41
    assert s.state.players['p2'].life==39
    roundtrip(s)


def test_paladin_forecast_rejects_mainphase(cards):
    s=setup(cards)
    tim=put(s,'Prodigal Sorcerer','battlefield')
    paladin=put(s,'Paladin of Prahv','hand')
    start(s)
    mana(s,W=1,C=1)
    with pytest.raises(ActionError,match='upkeep'):
        act(s,'p1',type='activate_ability',card_id=paladin.id,ability=1,targets=[tim.id],target_counts=[1])
    roundtrip(s)


def singer_setup(cards):
    s=setup(cards)
    singer=put(s,'Seasinger','battlefield')
    own=put(s,'Island','battlefield')
    theirs=put(s,'Island','battlefield',pid='p2')
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s)
    return s,singer,own,theirs,bear


def test_seasinger_actual_control_tapped_duration_and_keep_choice(cards):
    from tests.test_rules_wave7f_untap_choice import play_to
    s,singer,_,_,bear=singer_setup(cards)
    act(s,'p1',type='activate_ability',card_id=singer.id,ability=2,targets=[bear.id],target_counts=[1])
    settle(s)
    assert s.state.cards[bear.id].controller=='p1'
    play_to(s,7,keep=[singer.id])
    assert s.state.cards[singer.id].tapped
    assert s.state.cards[bear.id].controller=='p1'
    play_to(s,10)
    assert not s.state.cards[singer.id].tapped
    assert s.state.cards[bear.id].controller=='p2'
    roundtrip(s)


def test_seasinger_target_current_controller_must_control_island(cards):
    s,singer,_,_,bear=singer_setup(cards)
    other=put(s,'Runeclaw Bear','battlefield',pid='p3')
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=singer.id,ability=2,targets=[other.id],target_counts=[1])
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='activate_ability',card_id=singer.id,ability=2,targets=[bear.id],target_counts=[1])
    act(s,'p2',type='set_controller',card_ids=[bear.id],player='p3')
    settle(s)
    assert s.state.cards[bear.id].controller=='p3'
    roundtrip(s)


def test_seasinger_loses_control_when_source_changes_controller(cards):
    s,singer,_,_,bear=singer_setup(cards)
    act(s,'p1',type='activate_ability',card_id=singer.id,ability=2,targets=[bear.id],target_counts=[1])
    settle(s)
    cast(s,'Act of Aggression',[singer.id],pid='p2',target_counts=[1],life_symbols=[])
    assert s.state.cards[singer.id].controller=='p2'
    assert s.state.cards[bear.id].controller=='p2'
    roundtrip(s)


def test_seasinger_no_island_state_trigger_sacrifices_and_ends_control(cards):
    s,singer,own,_,bear=singer_setup(cards)
    act(s,'p1',type='activate_ability',card_id=singer.id,ability=2,targets=[bear.id],target_counts=[1])
    settle(s)
    cast(s,'Boomerang',[own.id],target_counts=[1])
    assert s.state.cards[singer.id].zone=='p1:graveyard'
    assert s.state.cards[bear.id].controller=='p2'
    roundtrip(s)


def test_forecast_watch_saved_and_resumed_in_fresh_process(cards,tmp_path):
    import subprocess
    import sys
    s,tim,paladin=forecast_setup(cards)
    act(s,'p1',type='activate_ability',card_id=paladin.id,ability=1,targets=[tim.id],target_counts=[1])
    settle(s)
    saved=tmp_path/'forecast.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
act(s,'p1',type='activate_ability',card_id=sys.argv[3],ability=0,targets=['p2'],target_counts=[1])
settle(s)
assert s.state.players['p1'].life==41
assert s.state.players['p2'].life==39
roundtrip(s)
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),tim.id],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


def test_paladin_permanent_noncombat_fight_damage_gains_life(cards):
    s=setup(cards)
    paladin=put(s,'Paladin of Prahv','battlefield')
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s)
    cast(s,'Prey Upon',[paladin.id,bear.id],target_counts=[1,1])
    assert s.state.players['p1'].life==43
    assert s.state.cards[bear.id].zone=='p2:graveyard'
    roundtrip(s)


def test_forecast_watch_follows_exact_target_not_its_blinked_successor(cards):
    s,tim,paladin=forecast_setup(cards)
    act(s,'p1',type='activate_ability',card_id=paladin.id,ability=1,targets=[tim.id],target_counts=[1])
    settle(s)
    old=s.state.rules.object_id(tim.id)
    cast(s,'Cloudshift',[tim.id],target_counts=[1])
    assert s.state.rules.object_id(tim.id)!=old
    cast(s,'Crimson Wisps',[tim.id],target_counts=[1])
    act(s,'p1',type='activate_ability',card_id=tim.id,ability=0,targets=['p2'],target_counts=[1])
    settle(s)
    assert s.state.players['p1'].life==40
    roundtrip(s)
