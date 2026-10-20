"""Actual paid mana is retained across counters, cast triggers and delayed mana."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Nix','Void Mirror','Unravel','Mana Sculpt','Smoldering Egg // Ashmouth Dragon']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/spent_spell_payment_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='ssp',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/spent_spell_payment_cards.json').read_text())]
    s=table(cards,names,names,names)
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True)
    return s


def cast(s,name,pool,targets=(),pid='p1',**kwargs):
    wait_priority(s,pid)
    c=put(s,name,'hand',pid=pid)
    if pool:
        act(s,pid,type='add_mana',player=pid,mana=pool)
    act(s,pid,type='cast_spell',card_id=c.id,targets=list(targets),sources=[],**kwargs)
    return c


def answers(s):
    for _ in range(30):
        settle(s)
        d=s.state.rules.decision
        if d is None:
            return
        assert 'keep' in {o.id for o in d.options},(d.kind,d.prompt)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=['keep'])
    raise AssertionError('Unfinished choices')


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize(('target','pool','countered'),[('Black Lotus',{},True),('Sol Ring',{'C':1},False)])
def test_nix_checks_actual_mana_not_mana_value(cards,target,pool,countered):
    s=game(cards)
    c=cast(s,target,pool)
    cast(s,'Nix',{'U':1},[c.id])
    settle(s)
    assert s.state.cards[c.id].zone==('p1:graveyard' if countered else 'p1:battlefield')
    roundtrip(s)


def test_nix_preserves_actual_generic_mana_when_phyrexian_symbols_use_life(cards):
    s=game(cards)
    # Dismember's generic {1} remains actual mana, despite four life for both B/P.
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    c=cast(s,'Dismember',{'C':1},[victim.id],life_symbols=['B','B'])
    cast(s,'Nix',{'U':1},[c.id])
    settle(s)
    assert s.state.cards[victim.id].zone=='p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize(('target','pool','countered'),[('Black Lotus',{},True),('Sol Ring',{'C':1},True),('Grizzly Bears',{'C':1,'G':1},False),('Sol Ring',{'G':1},False)])
def test_void_mirror_requires_actual_colored_mana(cards,target,pool,countered):
    s=game(cards)
    put(s,'Void Mirror','battlefield')
    c=cast(s,target,pool)
    settle(s)
    assert s.state.cards[c.id].zone==('p1:graveyard' if countered else 'p1:battlefield')
    roundtrip(s)


def test_void_mirror_does_not_trigger_for_an_actual_reverberate_copy(cards):
    s=game(cards)
    put(s,'Void Mirror','battlefield')
    c=cast(s,'Lightning Bolt',{'R':1},['p3'],pid='p2')
    cast(s,'Reverberate',{'R':2},[c.id])
    answers(s)
    assert s.state.players['p3'].life==34
    roundtrip(s)


@pytest.mark.parametrize(('target','pool','x','draw'),[('Black Lotus',{},None,False),('Sol Ring',{'C':1},None,False),('Blaze',{'C':3,'R':1},3,False)])
def test_unravel_compares_actual_mana_to_effective_stack_mana_value(cards,target,pool,x,draw):
    s=game(cards)
    c=cast(s,target,pool,['p2'] if target=='Blaze' else [],**({'x_value':x} if x is not None else {}))
    before=len(s.state.zones['p1:hand'])
    cast(s,'Unravel',{'C':1,'U':2},[c.id])
    settle(s)
    assert s.state.cards[c.id].zone=='p1:graveyard'
    assert len(s.state.zones['p1:hand'])==before+int(draw)
    roundtrip(s)


def test_unravel_uses_pre_counter_payment_and_life_is_not_mana(cards):
    s=game(cards)
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    c=cast(s,'Dismember',{'C':1},[victim.id],life_symbols=['B','B'])
    before=len(s.state.zones['p1:hand'])
    cast(s,'Unravel',{'C':1,'U':2},[c.id])
    settle(s)
    assert len(s.state.zones['p1:hand'])==before+1 and s.state.cards[victim.id].zone=='p2:battlefield'
    roundtrip(s)


def test_unravel_draws_even_when_the_underpaid_spell_cannot_be_countered(cards):
    s=game(cards)
    put(s,'Sapphire Medallion','battlefield')
    c=cast(s,'Supreme Verdict',{'W':2,'U':1})
    before=len(s.state.zones['p1:hand'])
    cast(s,'Unravel',{'C':1,'U':2},[c.id])
    settle(s)
    assert len(s.state.zones['p1:hand'])==before+1
    roundtrip(s)


@pytest.mark.parametrize('wizard',[False,True])
def test_mana_sculpt_freezes_payment_before_counter_and_waits_for_next_main(cards,wizard):
    s=game(cards)
    if wizard:
        put(s,'Willbender','battlefield')
    c=cast(s,'Sol Ring',{'C':1})
    cast(s,'Mana Sculpt',{'C':1,'U':2},[c.id])
    settle(s)
    assert s.state.cards[c.id].zone=='p1:graveyard'
    assert len(s.state.rules.delayed)==int(wizard)
    roundtrip(s)
    to_phase(s,'main2',1)
    settle(s)
    assert mana_pool(s,'p1')==({'C':1} if wizard else {})
    roundtrip(s)


def test_egg_counts_cast_payment_even_after_spell_is_countered(cards):
    s=game(cards)
    egg=put(s,'Smoldering Egg // Ashmouth Dragon','battlefield')
    c=cast(s,'Lightning Bolt',{'R':1},['p2'])
    cast(s,'Counterspell',{'U':2},[c.id])
    settle(s)
    assert s.state.cards[egg.id].counters.get('ember')==3
    assert s.state.cards[egg.id].face==0 and s.state.players['p2'].life==40
    roundtrip(s)


def test_egg_reaches_seven_removes_all_counters_and_transforms_same_object(cards):
    s=game(cards)
    egg=put(s,'Smoldering Egg // Ashmouth Dragon','battlefield')
    oid=s.state.rules.object_id(egg.id)
    cast(s,'Blaze',{'R':1,'C':6},['p2'],x_value=6)
    settle(s)
    assert s.state.cards[egg.id].face==1 and s.state.rules.object_id(egg.id)==oid
    assert not s.state.cards[egg.id].counters.get('ember',0)
    assert s.state.players['p2'].life==34
    roundtrip(s)


def test_nix_counters_an_actual_zero_mana_phyrexian_cast(cards):
    s=game(cards)
    c=cast(s,'Gitaxian Probe',{},['p2'],life_symbols=['U'])
    assert s.state.players['p1'].life==38
    cast(s,'Nix',{'U':1},[c.id])
    settle(s)
    assert s.state.cards[c.id].zone=='p1:graveyard'
    roundtrip(s)


def test_nix_counters_actual_spell_copy_that_was_not_cast(cards):
    s=game(cards)
    c=cast(s,'Lightning Bolt',{'R':1},['p3'],pid='p2')
    cast(s,'Reverberate',{'R':2},[c.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and 'keep' in {o.id for o in d.options}
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['keep'])
    copied=next(x for x in s.state.zones['stack'] if s.state.cards[x].is_token)
    assert s.state.rules.payments[s.state.rules.object_id(copied)].cast_from is None
    cast(s,'Nix',{'U':1},[copied])
    settle(s)
    assert copied not in s.state.cards and s.state.players['p3'].life==37
    roundtrip(s)


def test_egg_does_not_transform_back_for_an_older_stacked_trigger(cards):
    s=game(cards)
    egg=put(s,'Smoldering Egg // Ashmouth Dragon','battlefield')
    cast(s,'Blaze',{'R':1,'C':6},['p2'],x_value=6)
    cast(s,'Volcanic Geyser',{'R':2,'C':5},['p2'],x_value=5)
    settle(s)
    assert s.state.cards[egg.id].face==1
    assert not s.state.cards[egg.id].counters.get('ember',0)
    assert s.state.players['p2'].life==29
    roundtrip(s)


def test_egg_trigger_does_not_put_counters_on_returned_new_incarnation(cards):
    s=game(cards)
    egg=put(s,'Smoldering Egg // Ashmouth Dragon','battlefield')
    old=s.state.rules.object_id(egg.id)
    cast(s,'Lightning Bolt',{'R':1},['p2'])
    act(s,'p1',type='move',card_ids=[egg.id],to={'player':'p1','zone':'hand'})
    act(s,'p1',type='move',card_ids=[egg.id],to={'player':'p1','zone':'battlefield'})
    assert s.state.rules.object_id(egg.id)!=old
    settle(s)
    assert not s.state.cards[egg.id].counters.get('ember',0)
    roundtrip(s)


def test_mana_sculpt_saved_delayed_payment_survives_cold_load_and_wizard_loss(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    wizard=put(s,'Willbender','battlefield')
    c=cast(s,'Blaze',{'R':1,'C':3},['p2'],x_value=3)
    cast(s,'Mana Sculpt',{'C':1,'U':2},[c.id])
    settle(s)
    assert len(s.state.rules.delayed)==1
    act(s,'p1',type='move',card_ids=[wizard.id],to={'player':'p1','zone':'graveyard'})
    roundtrip(s)
    saved=tmp_path/'mana-sculpt.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved,database=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
for _ in range(100):
    if s.state.turn.phase=='main2' and not s.state.zones['stack']:
        break
    d=s.state.rules.decision
    if d is not None:
        assert d.kind in ('declare_attackers','declare_blockers')
        s.perform(d.player,{'type':d.kind,**({'attackers':[]} if d.kind=='declare_attackers' else {'blocks':[]})})
    else:
        s.perform(s.state.rules.priority,{'type':'pass_priority'})
else:
    raise AssertionError('Delayed main-phase trigger never completed')
assert s.state.players['p1'].mana.get('C',0)+sum(u.sym=='C' for u in s.state.players['p1'].mana_units)==4
assert not s.state.rules.delayed
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path)],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
