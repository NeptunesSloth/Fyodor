"""Native whole-card Demonic Covenant and prepared public mill continuations."""
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

CACHE, MIDNIGHT, DUMMY = 'Cache Grab', 'Midnight Tilling', 'Sparring Dummy'

@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/demonic_covenant62_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='oc59', number=str(i), **{k:v for k,v in c.items() if k not in ('name','set_code','number')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def setup(cards):
    names = ['Ornithopter', 'Demonic Covenant', CACHE, MIDNIGHT, DUMMY, 'Bruvac the Grandiloquent', 'Squirrel Sovereign', 'Chatterfang, Squirrel General', 'Environmental Sciences', 'Ashes of the Fallen', 'Wheel of Sun and Moon', 'Grizzly Bears', 'Hill Giant', 'Plains', 'Forest', 'Bonesplitter', 'Sol Ring', 'Rest in Peace', 'Lightning Bolt', 'Disperse', 'Darksteel Colossus']
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


@pytest.mark.parametrize('pair,match', [(['Grizzly Bears','Hill Giant'],True),(['Forest','Plains'],True),(['Grizzly Bears','Sol Ring'],False),(['Sol Ring','Bonesplitter'],True),(['Ornithopter','Sol Ring'],False)])
@pytest.mark.parametrize('rip',[False,True])
def test_native_exact_card_types(cards,pair,match,rip):
    s=setup(cards)
    if rip:
        cast(s,'Rest in Peace')
    source=cast(s,'Demonic Covenant')
    milled=top(s,pair)
    to_phase(s,'end',1)
    settle(s)
    assert source.zone==('p1:exile' if rip else 'p1:graveyard') if match else source.zone=='p1:battlefield'
    demons=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Demon']
    assert len(demons)==1
    assert all(c.zone==('p1:exile' if rip else 'p1:graveyard') for c in milled)
    roundtrip(s)

@pytest.mark.parametrize('cold',[False,True])
@pytest.mark.parametrize('outcome',['exile','library:shuffle'])
def test_native_pending_616_cannot_sacrifice_before_commit(cards,tmp_path,outcome,cold):
    s=setup(cards)
    cast(s,'Rest in Peace')
    source=cast(s,'Demonic Covenant')
    top(s,['Darksteel Colossus','Ornithopter'])
    to_phase(s,'end',1)
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='prepared_mill61'
    assert source.zone=='p1:battlefield'
    if cold:
        import os
        import subprocess
        import sys
        saved=tmp_path/'covenant62.json'
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
d=s.state.rules.decision;assert d and d.resume['step']=='prepared_mill61'
assert s.state.cards[sys.argv[3]].zone=='p1:battlefield'
chosen=next(o.id for o in d.options if o.label.endswith(': '+sys.argv[4]))
act(s,d.player,type='choose',decision_id=d.id,option_ids=[chosen]);settle(s)
assert s.state.cards[sys.argv[3]].zone==('p1:exile' if sys.argv[4]=='exile' else 'p1:battlefield')
assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Demon'])==1
roundtrip(s)
"""
        result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,outcome],capture_output=True,text=True,timeout=60,env=os.environ.copy())
        assert result.returncode==0,result.stdout+result.stderr
        return
    answer(s,[next(o.id for o in d.options if o.label.endswith(': '+outcome))])
    # Public exile preserves both matching Artifact Creature objects; hidden shuffle cannot be inferred.
    assert source.zone==('p1:exile' if outcome=='exile' else 'p1:battlefield')
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Demon'])==1
    roundtrip(s)

@pytest.mark.parametrize('expanded',[False,True])
def test_native_short_and_replacement_expanded_batch(cards,expanded):
    s=setup(cards)
    source=cast(s,'Demonic Covenant')
    if expanded:
        put(s,'Bruvac the Grandiloquent','battlefield','p2')
    for cid in list(s.state.zones['p1:library']):
        act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'hand'})
    milled=top(s,['Sol Ring','Grizzly Bears','Forest','Plains'] if expanded else ['Grizzly Bears'])
    to_phase(s,'end',1)
    settle(s)
    assert source.zone==('p1:graveyard' if expanded else 'p1:battlefield')
    assert all(c.zone=='p1:graveyard' for c in milled)
    roundtrip(s)


def test_whole_definition_and_exact_negative(cards):
    from app.rules import coverage, demonic_covenant62
    assert coverage.of_card_data(cards.resolve('Demonic Covenant')).level=='FULL'
    assert demonic_covenant62.parse('Create a 5/5 black Demon creature token with flying, then mill two cards. If two cards share a card type, sacrifice ~.') is None


def test_native_original_source_leaves_before_trigger_resolves(cards):
    s=setup(cards)
    source=cast(s,'Demonic Covenant')
    milled=top(s,['Grizzly Bears','Hill Giant'])
    to_phase(s,'end',1)
    assert s.state.rules.stack
    act(s,'p1',type='add_mana',player='p1',mana={'C':10,'U':10})
    cast(s,'Disperse',targets=[source.id])
    settle(s)
    assert source.zone=='p1:hand'
    assert all(c.zone=='p1:graveyard' for c in milled)
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Demon'])==1
    roundtrip(s)


def test_native_demon_attack_first_ability(cards):
    s=setup(cards)
    cast(s,'Demonic Covenant')
    top(s,['Grizzly Bears','Sol Ring'])
    to_phase(s,'end',1)
    settle(s)
    demon=next(c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Demon')
    to_phase(s,'declare_attackers',4)
    life=s.state.players['p1'].life
    hand=len(s.state.zones['p1:hand'])
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':demon.id,'target':'p2'}])
    settle(s)
    assert s.state.players['p1'].life==life-1
    assert len(s.state.zones['p1:hand'])==hand+1
    roundtrip(s)
