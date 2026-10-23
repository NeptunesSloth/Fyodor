"""Actual stack spells gain native abilities with exact object and duration lifetimes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/exile_counter_access85_cards.json').read_text())
LARA = 'Lara Croft, Tomb Raider'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json',
                     'fight_exile_receipts65_cards.json', 'top_library_authorities69_cards.json',
                     'pooled_casting_authorities71_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='lc76', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='lc76', number='a' + str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell', 'Sol Ring', 'Forest')


def test_lara_actual_attack_exiles_foreign_legend_and_can_play_it85(cards):
    from app.rules import permissions
    from tests.test_rules_controller_tutors import answer

    s = setup(cards)
    source = cast(s, LARA)
    target = put(s, 'Mox Amber', 'graveyard', pid='p2')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    assert s.state.rules.decision
    answer(s, [target.id])
    assert s.state.cards[target.id].counters.get('discovery') == 1
    assert s.state.cards[target.id].zone == 'p2:exile'
    to_phase(s, 'main2', turn=4)
    settle(s)
    card_now=s.state.cards[target.id]
    grants=permissions.grants(s.state,'p1',card_now,Plan(s.state,'p1',cards,None).ch(card_now),cards)
    assert grants
    act(s,'p1',type='cast_spell',card_id=target.id,via=grants[0].choice_key)
    settle(s)
    assert s.state.cards[target.id].zone=='p1:battlefield'


def attack85(s, source, turn, targets):
    from tests.test_rules_controller_tutors import answer

    to_phase(s, 'declare_attackers', turn=turn)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    if s.state.rules.decision:
        answer(s, targets)
    else:
        assert not targets
    to_phase(s, 'main2', turn=turn)
    settle(s)


def grants85(s, cards, cid, verb='cast'):
    from app.rules import permissions

    c = s.state.cards[cid]
    return permissions.grants(s.state, 'p1', c, Plan(s.state, 'p1', cards, None).ch(c), cards, verb=verb)


def test_lara_old_discovery_objects_and_actual_foreign_land_share_one_play85(cards):
    from app.game.errors import ActionError

    s=setup(cards)
    source=cast(s,LARA)
    old=put(s,'Mox Amber','graveyard',pid='p2')
    attack85(s,source,4,[old.id])
    land=put(s,'Boseiju, Who Endures','graveyard',pid='p3')
    attack85(s,source,7,[land.id])
    assert grants85(s,cards,old.id)
    assert grants85(s,cards,land.id,'play')
    act(s,'p1',type='play_land',card_id=land.id)
    assert s.state.cards[land.id].zone=='p1:battlefield'
    assert not grants85(s,cards,old.id)
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=old.id)
    assert s.state.model_dump(mode='json')==before


def test_lara_zero_target_creates_access_to_old_counter_objects_and_expiry85(cards):
    s=setup(cards)
    source=cast(s,LARA)
    old=put(s,'Mox Amber','graveyard',pid='p2')
    attack85(s,source,4,[old.id])
    to_phase(s,'upkeep',turn=5)
    settle(s)
    assert not grants85(s,cards,old.id)
    attack85(s,source,7,[])
    assert grants85(s,cards,old.id)
    cast(s,'Disperse',targets=[source.id])
    assert grants85(s,cards,old.id)
    act(s,'p1',type='cast_spell',card_id=old.id)
    settle(s)
    assert s.state.cards[old.id].zone=='p1:battlefield'


def test_lara_requires_discovery_counters_for_both_spell_and_land85(cards):
    s=setup(cards)
    source=cast(s,LARA)
    attack85(s,source,4,[])
    spell=put(s,'Mox Amber','exile',pid='p2')
    land=put(s,'Boseiju, Who Endures','exile',pid='p3')
    assert not grants85(s,cards,spell.id)
    assert not grants85(s,cards,land.id,'play')
    assert coverage.of_card_data(cards.resolve(LARA)).level=='FULL'


@pytest.mark.parametrize('kind', ['spell','land'])
def test_genuine_cold_lara_dynamic_counter_permission85(cards,tmp_path,kind):
    import os
    import subprocess
    import sys

    s=setup(cards)
    source=cast(s,LARA)
    target=put(s,'Mox Amber' if kind=='spell' else 'Boseiju, Who Endures','graveyard',pid='p2')
    attack85(s,source,4,[target.id])
    cast(s,'Disperse',targets=[source.id])
    saved=tmp_path/'exile85.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.rules import permissions
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
cid,kind=sys.argv[3:5]
c=s.state.cards[cid]
assert c.zone=='p2:exile' and c.counters.get('discovery')==1
verb='cast' if kind=='spell' else 'play'
g=permissions.grants(s.state,'p1',c,Plan(s.state,'p1',r,None).ch(c),r,verb=verb)
assert len(g)==1
act(s,'p1',type='cast_spell' if kind=='spell' else 'play_land',card_id=cid,via=g[0].choice_key)
settle(s)
assert s.state.cards[cid].zone=='p1:battlefield'
assert s.state.cards[cid].owner=='p2'
roundtrip(s)
r.close()
'''
    backend=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),target.id,kind],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=240)
    assert result.returncode==0,result.stdout+result.stderr
