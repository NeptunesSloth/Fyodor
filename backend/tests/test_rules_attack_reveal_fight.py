"""Canonical exact-target delayed watches, event batching and source/controller identity."""

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
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/attack_reveal_fight_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="arf35", number=str(i), **{k: v for k, v in c.items() if k != "name"}
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
            (Path(__file__).parent / "fixtures/attack_reveal_fight_cards.json").read_text()
        )
    ]
    return table(cards, names, names, names)


def attack_setup(cards,top='Grizzly Bears',walkers=False):
    s=setup(cards)
    hans=put(s,'Hans Eriksson','battlefield')
    if walkers:
        start(s,turn=2)
        walker=cast(s,'Jace Beleren',pid='p2')
        assert walker.counters['loyalty']==3
        if walkers=='two':
            to_phase(s,'main1',turn=3)
            cast(s,'Jace Beleren',pid='p3')
    start(s,turn=4)
    shown=put(s,top,'hand')
    act(s,'p1',type='move',card_ids=[shown.id],to={'zone':'library','player':'p1'},position='top')
    return s,hans,shown


def begin_attack(s,hans):
    from tests.test_rules_wave30p_combat import attack
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(hans,'p2'))


def reach_fight(s):
    for _ in range(24):
        fights=[e for e in s.state.rules.stack.values() if e.effects and e.effects[0].get('do')=='fight']
        if fights:
            return fights
        assert s.state.rules.decision is None
        act(s,s.state.rules.priority,type='pass_priority')
    raise AssertionError('no reflexive fight')


def test_hans_full(cards):
    assert coverage.of_card_data(cards.resolve('Hans Eriksson')).level=='FULL'


def test_hans_actual_reveal_entry_and_response_window_before_fight(cards):
    s,hans,bear=attack_setup(cards)
    begin_attack(s,hans)
    fights=reach_fight(s)
    assert len(fights)==1 and fights[0].kind=='trigger'
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert s.state.cards[bear.id].attacking.id=='p2' and s.state.cards[bear.id].tapped
    assert s.state.cards[bear.id].damage==0 and s.state.cards[hans.id].damage==0
    settle(s)
    assert s.state.cards[bear.id].damage==1 and s.state.cards[hans.id].damage==2
    roundtrip(s)


def test_hans_noncreature_goes_to_hand_without_fight(cards):
    s,hans,land=attack_setup(cards,top='Forest')
    begin_attack(s,hans)
    settle(s)
    assert s.state.cards[land.id].zone=='p1:hand'
    assert not s.state.rules.stack
    assert s.state.cards[hans.id].damage==0
    roundtrip(s)


def test_hans_failed_library_entry_does_not_create_reflexive(cards):
    s,hans,bear=attack_setup(cards)
    cast(s,"Grafdigger's Cage")
    begin_attack(s,hans)
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:library'
    assert not s.state.rules.stack
    assert s.state.cards[hans.id].damage==0
    roundtrip(s)


def test_hans_defender_planeswalker_choice_is_opt_in_and_resumes(cards):
    s,hans,bear=attack_setup(cards,walkers=True)
    walker=next(c for c in s.state.cards.values() if c.name=='Jace Beleren' and c.controller=='p2' and c.zone.endswith(':battlefield'))
    begin_attack(s,hans)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player=='p1' and d.resume['step']=='token_attack'
    assert {o.id for o in d.options}=={'p2',walker.id}
    pick(s,[walker.id])
    settle(s)
    assert s.state.cards[bear.id].attacking.id==walker.id
    assert s.state.cards[hans.id].damage==2
    roundtrip(s)


@pytest.mark.parametrize('changed',['hans','entered'])
def test_hans_reflexive_fight_does_not_follow_blinked_participant(cards,changed):
    s,hans,bear=attack_setup(cards)
    begin_attack(s,hans)
    reach_fight(s)
    target=hans if changed=='hans' else bear
    old=s.state.rules.object_id(target.id)
    cast(s,'Cloudshift',[target.id])
    assert s.state.rules.object_id(target.id)!=old
    assert s.state.cards[hans.id].damage==0 and s.state.cards[bear.id].damage==0
    roundtrip(s)


@pytest.mark.parametrize('which',['attack','reflexive'])
def test_hans_original_and_reflexive_are_independently_counterable(cards,which):
    s,hans,bear=attack_setup(cards)
    begin_attack(s,hans)
    if which=='reflexive':
        reach_fight(s)
    sid=next(iter(s.state.rules.stack))
    cast(s,'Stifle',[sid])
    assert s.state.cards[bear.id].zone==('p1:library' if which=='attack' else 'p1:battlefield')
    assert s.state.cards[hans.id].damage==0
    assert s.state.cards[bear.id].damage==0
    roundtrip(s)


def test_hans_source_blink_before_reveal_still_puts_creature_attacking(cards):
    s,hans,bear=attack_setup(cards)
    begin_attack(s,hans)
    old=s.state.rules.object_id(hans.id)
    cast(s,'Cloudshift',[hans.id])
    assert s.state.rules.object_id(hans.id)!=old
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert s.state.cards[bear.id].attacking.id=='p2'
    assert s.state.cards[hans.id].damage==0 and s.state.cards[bear.id].damage==0
    roundtrip(s)


@pytest.mark.parametrize('orb',[False,True])
def test_hans_creature_card_can_enter_as_noncreature_without_fight(cards,orb):
    from app.rules.plan import Plan
    s,hans,god=attack_setup(cards,top='Thassa, God of the Sea')
    if orb:
        cast(s,'Torpor Orb')
    begin_attack(s,hans)
    fights=reach_fight(s)
    assert len(fights)==1
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[god.id])
    assert 'Creature' not in ch.types and 'Enchantment' in ch.types
    assert s.state.cards[god.id].attacking is None
    settle(s)
    assert s.state.cards[hans.id].damage==0
    roundtrip(s)


def test_torpor_orb_suppresses_hans_creature_entry_reflexive(cards):
    s,hans,bear=attack_setup(cards)
    cast(s,'Torpor Orb')
    begin_attack(s,hans)
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert s.state.cards[bear.id].attacking.id=='p2'
    assert s.state.cards[hans.id].damage==0 and s.state.cards[bear.id].damage==0
    assert not s.state.rules.stack
    roundtrip(s)


def test_saved_hans_planeswalker_entry_choice_finishes_cold(cards,tmp_path):
    import subprocess
    import sys
    s,hans,bear=attack_setup(cards,walkers=True)
    walker=next(c for c in s.state.cards.values() if c.name=='Jace Beleren' and c.controller=='p2' and c.zone.endswith(':battlefield'))
    begin_attack(s,hans)
    settle(s)
    assert s.state.rules.decision.resume['step']=='token_attack'
    saved=tmp_path/'hans-entry.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import pick,settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
pick(s,[sys.argv[3]])
settle(s)
assert s.state.cards[sys.argv[4]].attacking.id==sys.argv[3]
assert s.state.cards[sys.argv[5]].damage==2
roundtrip(s)
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),walker.id,bear.id,hans.id],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


def test_hans_attacking_planeswalker_uses_its_controller_and_excludes_other_players(cards):
    from tests.test_rules_wave30p_combat import attack
    s,hans,bear=attack_setup(cards,walkers='two')
    walkers={c.controller:c for c in s.state.cards.values() if c.name=='Jace Beleren' and c.zone.endswith(':battlefield')}
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(hans,walkers['p2'].id))
    settle(s)
    d=s.state.rules.decision
    assert {o.id for o in d.options}=={'p2',walkers['p2'].id}
    assert walkers['p3'].id not in {o.id for o in d.options}
    pick(s,['p2'])
    settle(s)
    assert s.state.cards[bear.id].attacking.id=='p2'
    assert s.state.cards[hans.id].damage==2
    roundtrip(s)
