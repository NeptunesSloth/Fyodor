"""Linked exile abilities grant native exact-object play permissions."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Raphael, Most Attitude", "Kayla's Music Box", "Muse Vessel", "Null Summoner", "Rogue Class"]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/linked_play_grant_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='lor', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def setup(cards, name):
    support = ['Grizzly Bears', 'Lightning Bolt', 'Counterspell', 'Unsummon', 'Naturalize', 'Word of Seizing', 'Song of the Dryads', 'Cloudshift', "Tormod's Crypt"]
    s = table(cards, [name, *support], support, support)
    for p in ['p1', 'p2', 'p3']:
        act(s, p, type='set_prefs', hold_priority=True)
    source = put(s, name, 'hand' if name == 'Null Summoner' else 'battlefield')
    return s, source


def top(s, name, pid='p1'):
    c = next(c for c in s.state.cards.values() if c.owner == pid and c.name == name)
    act(s, pid, type='move', card_ids=[c.id], to={'player': pid, 'zone': 'library'}, position='top')
    return c


def activate(s, source, ability, pid='p1', **kw):
    wait_priority(s, pid)
    act(s, pid, type='activate_ability', card_id=source.id, ability=ability, **kw)
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_are_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result


@pytest.mark.parametrize('first', ['land', 'spell'])
def test_raphael_native_alliance_attack_has_one_shared_land_spell_use(cards, first):
    s, source = setup(cards, 'Raphael, Most Attitude')
    to_phase(s, 'main1', turn=4)
    for name in ['Forest', 'Lightning Bolt']:
        top(s, name)
        bear = put(s, 'Grizzly Bears', 'hand')
        mana(s, C=1, G=1)
        act(s, 'p1', type='cast_spell', card_id=bear.id)
        settle(s)
    assert len(s.state.zones['p1:exile']) == 2
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    to_phase(s, 'main2', turn=4)
    exiled = s.state.zones['p1:exile']
    forest = next(c for c in exiled if s.state.cards[c].name == 'Forest')
    bolt = next(c for c in exiled if s.state.cards[c].name == 'Lightning Bolt')
    assert len({p.group for p in s.state.rules.permissions if p.left == 1}) == 1
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
    assert all(p.left == 1 for p in s.state.rules.permissions if p.group)
    mana(s, R=1)
    if first == 'land':
        act(s, 'p1', type='play_land', card_id=forest)
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
    else:
        act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
        settle(s)
        with pytest.raises(ActionError):
            act(s, 'p1', type='play_land', card_id=forest)
    roundtrip(s)


@pytest.mark.parametrize('departure', ['destroy', 'steal'])
def test_kayla_resolved_pool_is_frozen_and_survives_source_departure(cards, departure):
    s, source = setup(cards, "Kayla's Music Box")
    top(s, 'Lightning Bolt')
    mana(s, W=1)
    activate(s, source, 0)
    old = s.state.zones['p1:exile'][0]
    from tests.test_rules_linked_exile_look import assert_look
    assert_look(s, old, {'p1'})
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    activate(s, source, 1)
    top(s, 'Grizzly Bears')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    mana(s, W=1)
    activate(s, source, 0)
    new = next(c for c in s.state.zones['p1:exile'] if s.state.cards[c].name == 'Grizzly Bears')
    mana(s, C=1, G=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=new)
    removal = put(s, 'Naturalize' if departure == 'destroy' else 'Word of Seizing', 'hand', pid='p2')
    mana(s, 'p2', C=3, G=1, R=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    if departure == 'steal':
        assert_look(s, old, {'p1'})
        activate(s, source, 1, pid='p2')
        mana(s, 'p2', G=1)
        wait_priority(s, 'p2')
        with pytest.raises(ActionError):
            act(s, 'p2', type='cast_spell', card_id=new)
    wait_priority(s, 'p1')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=old, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_muse_vessel_native_opponent_exile_then_chosen_play(cards):
    s, source = setup(cards, 'Muse Vessel')
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    put(s, 'Grizzly Bears', 'hand', pid='p2')
    mana(s, C=3)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=['p2'])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == 'p2'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[bolt.id])
    settle(s)
    mana(s, C=1)
    activate(s, source, 1)
    cid = s.state.zones['p2:exile'][0]
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def null_entry(s, source):
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    put(s, 'Grizzly Bears', 'hand', pid='p2')
    mana(s, C=2, U=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bolt.id])
    settle(s)
    return s.state.zones['p2:exile'][0]


def graveyard_seven(s):
    cards = [c for c in s.state.zones['p1:library']][:7]
    act(s, 'p1', type='move', card_ids=cards, to={'player': 'p1', 'zone': 'graveyard'})


def test_null_summoner_threshold_rechecks_and_native_anytype_cast(cards):
    s, source = setup(cards, 'Null Summoner')
    cid = null_entry(s, source)
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
    graveyard_seven(s)
    crypt = put(s, "Tormod's Crypt", 'battlefield', pid='p2')
    activate(s, crypt, 0, pid='p2', targets=['p1'])
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
    graveyard_seven(s)
    mana(s, G=1)
    act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_rogue_class_native_levels_combat_private_pool_anycolor_cast(cards):
    from tests.test_rules_linked_exile_look import assert_look

    s, source = setup(cards, 'Rogue Class')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    top(s, 'Lightning Bolt', pid='p2')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    to_phase(s, 'main2', turn=4)
    settle(s)
    cid = s.state.zones['p2:exile'][0]
    assert s.state.cards[cid].name == 'Lightning Bolt'
    assert_look(s, cid, {'p1'})
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
    mana(s, C=3, U=2, B=2)
    activate(s, source, 1)
    activate(s, source, 3)
    mana(s, G=1)
    act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 35
    roundtrip(s)


def test_muse_pending_choice_cold_resume_after_source_removed(cards, tmp_path):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    s, source = setup(cards, 'Muse Vessel')
    for turn, pid, name in [(1, 'p2', 'Lightning Bolt'), (4, 'p3', 'Grizzly Bears')]:
        to_phase(s, 'main1', turn=turn)
        chosen = put(s, name, 'hand', pid=pid)
        put(s, 'Counterspell', 'hand', pid=pid)
        mana(s, C=3)
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[pid])
        until(s, lambda s: s.state.rules.decision is not None)
        d = s.state.rules.decision
        act(s, pid, type='choose', decision_id=d.id, option_ids=[chosen.id])
        settle(s)
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    removal = put(s, 'Naturalize', 'hand', pid='p2')
    mana(s, 'p2', C=1, G=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=removal.id, targets=[source.id])
    until(s, lambda s: s.state.rules.decision is not None)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    d = s.state.rules.decision
    assert d.player == 'p1' and len(d.options) == 2
    cid = s.state.zones['p2:exile'][0]
    original = tmp_path / 'original.json'
    restored = tmp_path / 'restored.json'
    original.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[1]),ImageStore(Path(sys.argv[2])))
s=GameSession(GameState.model_validate_json(Path(sys.argv[3]).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[sys.argv[5]]})
Path(sys.argv[4]).write_text(s.state.model_dump_json())
'''
    result = subprocess.run([sys.executable, '-c', code, str(cards.db_path), str(tmp_path / 'images'),
                             str(original), str(restored), cid], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    s = GameSession(GameState.model_validate_json(restored.read_text()), cards=cards)
    settle(s)
    assert {p.card for p in s.state.rules.permissions} == {cid}
    mana(s, R=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_rogue_transfer_static_play_is_distinct_from_resolved_look(cards):
    from tests.test_rules_linked_exile_look import assert_look

    s, source = setup(cards, 'Rogue Class')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    top(s, 'Lightning Bolt', pid='p2')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    to_phase(s, 'main2', turn=4)
    settle(s)
    cid = s.state.zones['p2:exile'][0]
    mana(s, C=3, U=2, B=2)
    activate(s, source, 1)
    activate(s, source, 3)
    stealing = put(s, 'Word of Seizing', 'hand', pid='p2')
    mana(s, 'p2', C=3, R=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=stealing.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].controller == 'p2'
    assert_look(s, cid, {'p1'})
    mana(s, G=1)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid, targets=['p3'])
    # 406.3a: the new controller may play the hidden card via the actual static
    # permission; doing so turns it face up as casting starts, without granting look.
    mana(s, 'p2', G=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=cid, targets=['p3'])
    settle(s)
    assert s.state.players['p3'].life == 37
    roundtrip(s)
