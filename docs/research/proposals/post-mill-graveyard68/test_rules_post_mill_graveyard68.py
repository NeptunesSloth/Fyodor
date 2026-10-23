"""Native public-mill selections and exact hand outcomes."""
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


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/post_mill_graveyard68_cards.json').read_text())):
        extra = {k:v for k,v in c.items() if k not in ('name','set_code','number')}
        if c.get('faces'):
            extra['card_faces'] = c['faces']
        if c.get('related_cards') or c.get('related_tokens'):
            extra['all_parts'] = [*c.get('related_cards', []), *[{**part, 'component': 'token'} for part in c.get('related_tokens', [])]]
        base[c['name']] = card(c['name'], set_code='oc59', number=str(i), **extra)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def setup(cards):
    names = list(dict.fromkeys([c['name'] for c in json.loads((Path(__file__).parent/'fixtures/post_mill_graveyard68_cards.json').read_text()) if c['name'] != 'Urza, Planeswalker'] + ['Grizzly Bears','Hill Giant','Forest','Lightning Bolt']))
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


def top_for(s,names,owner):
    cards=[put(s,name,'hand',owner) for name in names]
    for c in reversed(cards):
        act(s,owner,type='move',card_ids=[c.id],to={'player':owner,'zone':'library'},position='top')
    return cards



def test_whole_pair(cards):
    from app.rules.coverage import of_card_data
    for n in ['Roots of Wisdom','Stillness in Motion']:
        assert of_card_data(cards.resolve(n)).level=='FULL'


def test_roots_forces_return_existing_kindred_elf_not_just_milled(cards):
    s=setup(cards)
    elf=put(s,'Elvish Promenade','graveyard')
    milled=top(s,['Hill Giant','Lightning Bolt','Sol Ring'])
    source=cast(s,'Roots of Wisdom')
    assert not s.state.rules.decision
    assert elf.zone=='p1:hand' and all(c.zone=='p1:graveyard' for c in milled)
    assert source.zone=='p1:graveyard'
    roundtrip(s)


def test_roots_forced_non_target_choice_includes_old_and_new_land_elf(cards):
    s=setup(cards)
    old=put(s,'Elvish Promenade','graveyard')
    milled=top(s,['Forest','Elvish Visionary','Sol Ring'])
    source=cast(s,'Roots of Wisdom')
    d=s.state.rules.decision
    assert d and d.resume['step']=='return_choice' and d.min_choices==d.max_choices==1
    assert {o.id for o in d.options}=={old.id,milled[0].id,milled[1].id}
    answer(s,[milled[1].id])
    assert milled[1].zone=='p1:hand' and old.zone=='p1:graveyard' and source.zone=='p1:graveyard'
    roundtrip(s)


def test_roots_draws_only_when_no_qualifying_card_after_mill(cards):
    s=setup(cards)
    milled=top(s,['Hill Giant','Lightning Bolt','Sol Ring','Disenchant'])
    source=cast(s,'Roots of Wisdom')
    assert all(c.zone=='p1:graveyard' for c in milled[:3])
    assert milled[3].zone=='p1:hand' and source.zone=='p1:graveyard'
    roundtrip(s)


def trigger_still68(s):
    enchantment=cast(s,'Stillness in Motion')
    to_phase(s,'upkeep',4)
    settle(s)
    return enchantment


def test_stillness_nonempty_after_mill_does_not_exile_or_return(cards):
    s=setup(cards)
    milled=top(s,['Hill Giant','Lightning Bolt','Sol Ring','Disenchant'])
    source=trigger_still68(s)
    assert source.zone=='p1:battlefield'
    assert all(c.zone=='p1:graveyard' for c in milled[:3])
    assert milled[3].zone=='p1:library'
    roundtrip(s)


def trim68(s,keep):
    leave={c.id for c in keep}
    rest=[cid for cid in s.state.zones['p1:library'] if cid not in leave]
    if rest:
        act(s,'p1',type='move',card_ids=rest,to={'player':'p1','zone':'exile'})


def test_true_cold_stillness_empty_library_forces_five_chosen_then_native_private_order(cards,tmp_path):
    s=setup(cards)
    put(s,'Desecrated Tomb','battlefield')
    old=[put(s,n,'graveyard') for n in ['Elvish Promenade','Disenchant','Elvish Visionary']]
    source=cast(s,'Stillness in Motion')
    milled=top(s,['Hill Giant','Lightning Bolt','Sol Ring'])
    trim68(s,milled)
    to_phase(s,'upkeep',4)
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='return_choice' and d.min_choices==d.max_choices==5
    assert source.zone=='p1:exile' and not s.state.zones['p1:library']
    assert {o.id for o in d.options}=={c.id for c in [*old,*milled]}
    chosen=[*old,*milled[:2]]
    answer(s,[c.id for c in chosen])
    d=s.state.rules.decision
    assert d and d.resume['step']=='library_placements' and d.resume['stage']=='order'
    assert all(c.zone=='p1:graveyard' for c in chosen)
    ordered=list(reversed(chosen))
    s=cold68(s,cards,tmp_path,[c.id for c in ordered])
    assert s.state.zones['p1:library']==[c.id for c in ordered]
    assert milled[2].zone=='p1:graveyard'
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Bat'])==1
    roundtrip(s)


def cold68(s,cards,tmp_path,ids):
    import os
    import subprocess
    import sys

    import app
    from app.game.session import GameSession
    from app.game.state import GameState
    saved=tmp_path/'shuffle67.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision;assert d and d.resume['step'] in ('commander_first','prepared_mill61','library_placements')
act(s,d.player,type='choose',decision_id=d.id,option_ids=json.loads(sys.argv[3]));settle(s)
assert s.state.rules.decision is None
p.write_text(s.state.model_dump_json())
'''
    backend=Path(app.__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),json.dumps(ids)],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr
    return GameSession(GameState.model_validate_json(saved.read_text()),cards=cards)




def test_stillness_short_library_mills_as_many_as_possible_and_returns_available_cards(cards):
    s=setup(cards)
    source=cast(s,'Stillness in Motion')
    milled=top(s,['Hill Giant','Lightning Bolt'])
    trim68(s,milled)
    to_phase(s,'upkeep',4)
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='library_placements' and d.resume['stage']=='order'
    assert source.zone=='p1:exile' and all(c.zone=='p1:graveyard' for c in milled)
    answer(s,[c.id for c in reversed(milled)])
    assert s.state.zones['p1:library']==[c.id for c in reversed(milled)]
    roundtrip(s)


@pytest.mark.parametrize('outcome',['exile','library:shuffle'])
def test_true_cold_stillness_guard_uses_actual_library_after_native616(cards,tmp_path,outcome):
    s=setup(cards)
    cast(s,'Rest in Peace')
    source=cast(s,'Stillness in Motion')
    milled=top(s,['Darksteel Colossus','Forest','Sol Ring'])
    trim68(s,milled)
    to_phase(s,'upkeep',4)
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='prepared_mill61'
    assert source.zone=='p1:battlefield' and all(c.zone=='p1:library' for c in milled)
    choice=next(o.id for o in d.options if o.label.endswith(': '+outcome))
    s=cold68(s,cards,tmp_path,[choice])
    assert s.state.cards[source.id].zone==('p1:exile' if outcome=='exile' else 'p1:battlefield')
    assert len(s.state.zones.get('p1:library',[]))==(0 if outcome=='exile' else 1)
    assert not s.state.zones.get('p1:graveyard') and not s.state.rules.decision
    roundtrip(s)


@pytest.mark.parametrize('command',[False,True])
def test_true_cold_roots_original_elf_commander_diversion_does_not_draw_fallback(cards,tmp_path,command):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable
    names=['Roots of Wisdom','Lightning Bolt','Hill Giant','Sol Ring','Grizzly Bears','Disenchant']
    decks=[deck(cards,'Rhys the Redeemed',[(1,n) for n in names]+[(20,'Forest')]),
           deck(cards,'Krenko, Mob Boss',[(20,'Forest')]),deck(cards,'Krenko, Mob Boss',[(20,'Forest')])]
    s=GameSession(enable(new_game([PlayerSetup(str(i),cards=d) for i,d in enumerate(decks)],shuffle=False)),cards=cards)
    act(s,'p1',type='pass_priority')
    for pid in s.state.players:
        act(s,pid,type='set_prefs',response='on')
    to_phase(s,'main1',1)
    act(s,'p1',type='add_mana',player='p1',mana={c:30 for c in ['C','W','U','B','R','G']})
    commander=next(c for c in s.state.cards.values() if c.owner=='p1' and c.commander_key)
    act(s,'p1',type='move',card_ids=[commander.id],to={'player':'p1','zone':'battlefield'})
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,sources=[],targets=[commander.id])
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.resume['step']=='commander_zone'
    answer(s,['no'])
    top_cards=top(s,['Hill Giant','Sol Ring','Grizzly Bears','Disenchant'])
    source=cast(s,'Roots of Wisdom')
    d=s.state.rules.decision
    assert d and d.resume['step']=='commander_first' and commander.zone=='p1:graveyard'
    s=cold68(s,cards,tmp_path,['yes' if command else 'no'])
    assert s.state.cards[commander.id].zone==('p1:command' if command else 'p1:hand')
    assert s.state.cards[top_cards[3].id].zone=='p1:library'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_stillness_destroyed_in_response_still_returns_five_and_can_return_its_new_card(cards):
    s=setup(cards)
    source=cast(s,'Stillness in Motion')
    destroy=put(s,'Disenchant','hand')
    milled=top(s,['Hill Giant','Lightning Bolt','Sol Ring'])
    trim68(s,milled)
    to_phase(s,'upkeep',4)
    assert s.state.zones.get('stack')
    act(s,'p1',type='add_mana',player='p1',mana={'W':1,'C':1})
    act(s,'p1',type='cast_spell',card_id=destroy.id,sources=[],targets=[source.id])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='library_placements' and d.resume['stage']=='order'
    selected=[source,destroy,*milled]
    assert all(c.zone=='p1:graveyard' for c in selected)
    assert {o.id for o in d.options}=={c.id for c in selected}
    answer(s,[c.id for c in selected])
    assert s.state.zones['p1:library']==[c.id for c in selected]
    roundtrip(s)
