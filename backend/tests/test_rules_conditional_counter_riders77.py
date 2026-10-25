"""Canonical conditional counter riders through actual casting and saved payments."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Moment of Glory', 'Beast Mode', 'Recursive Recruitment', "Ent's Fury"]
DATA = json.loads((Path(__file__).parent / 'fixtures/conditional_counter_riders77_cards.json').read_text())


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


ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Forest', 'Island', 'Mountain', 'Counterspell', 'Lightning Bolt']


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def cast(s, name, targets=(), *, grave=False, teamwork=None):
    source = put(s, name, 'graveyard' if grave else 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 10, 'W': 2, 'U': 2, 'B': 2, 'G': 2})
    extra = {'flashback_choice': 0} if grave else {}
    if name == NAMES[3]:
        extra['target_counts'] = [1, 1]
    if teamwork is not None:
        extra.update(optional_costs=[source.id + ':teamwork'], cost_choices=[{'component': 0, 'cards': [teamwork.id]}])
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[], targets=list(targets), **extra)
    return source


def counters(s, c):
    return s.state.cards[c.id].counters.get('+1/+1', 0)


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('grave', [False, True])
def test_moment_actual_hand_or_flashback_excludes_target_from_second_counter(cards, grave):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    spell = cast(s, NAMES[0], [a.id], grave=grave)
    settle(s)
    assert (counters(s, a), counters(s, b), counters(s, enemy)) == (1, int(grave), 0)
    assert s.state.cards[spell.id].zone == ('p1:exile' if grave else 'p1:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('teamwork', [False, True])
def test_beast_actual_paid_teamwork_is_not_merely_available_helper(cards, teamwork):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    helper = put(s, 'Llanowar Elves', 'battlefield')
    cast(s, NAMES[1], [a.id], teamwork=helper if teamwork else None)
    settle(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[a.id])
    assert ch.pt == ((5, 5) if teamwork else (4, 4))
    assert counters(s, a) == int(teamwork) and 'trample' in ch.keywords
    assert s.state.cards[helper.id].tapped == teamwork
    roundtrip(s)


@pytest.mark.parametrize('grave,n', [(False, 6), (True, 0), (True, 2), (True, 3), (True, 5), (True, 6)])
def test_recursive_counts_current_graveyard_and_only_actual_created_tokens(cards, grave, n):
    s = game(cards)
    old = put(s, 'Grizzly Bears', 'battlefield')
    for name in [x for x in ALL if x not in (NAMES[2], 'Grizzly Bears')][:n]:
        put(s, name, 'graveyard')
    # Populate exact count with distinct already present cards, keeping the spell separate.
    actual = len(s.state.zones['p1:graveyard'])
    assert actual == n
    spell = cast(s, NAMES[2], grave=grave)
    settle(s)
    made = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield' and c.name == 'Cadet']
    assert len(made) == 2
    assert [c.counters.get('+1/+1', 0) for c in made] == [actual // 3 if grave else 0] * 2
    assert not counters(s, old)
    assert s.state.cards[spell.id].zone == ('p1:exile' if grave else 'p1:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('power', [2, 3, 4, 5])
def test_ent_checks_power_before_counter_and_pump_then_fights(cards, power):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    if power > 2:
        act(s, 'p1', type='counter', card_ids=[a.id], kind='+1/+1', delta=power-2)
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, NAMES[3], [a.id, enemy.id])
    settle(s)
    assert counters(s, a) == power - 2 + int(power >= 4)
    assert s.state.cards[a.id].zone == 'p1:battlefield'
    assert s.state.cards[enemy.id].zone == 'p2:graveyard'
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[a.id]).pt == (power + 1 + int(power >= 4),) * 2
    roundtrip(s)


@pytest.mark.parametrize('name', [NAMES[0], NAMES[1], NAMES[3]])
def test_original_target_leaves_before_resolution_no_counter_on_new_incarnation(cards, name):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    ally = put(s, 'Llanowar Elves', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, name, [a.id, enemy.id] if name == NAMES[3] else [a.id], grave=name == NAMES[0])
    old = Plan(s.state, 'p1', cards, None).oid(a.id)
    act(s, 'p1', type='move', card_ids=[a.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[a.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert Plan(s.state, 'p1', cards, None).oid(a.id) != old
    settle(s)
    assert not counters(s, a) and not counters(s, ally)
    assert not s.state.cards[enemy.id].damage
    roundtrip(s)


def test_ent_other_target_illegal_still_pumps_and_counters_legal_own_target(cards):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[a.id], kind='+1/+1', delta=2)
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, NAMES[3], [a.id, enemy.id])
    act(s, 'p2', type='move', card_ids=[enemy.id], to={'player': 'p2', 'zone': 'exile'})
    settle(s)
    assert counters(s, a) == 3 and not s.state.cards[a.id].damage
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[a.id]).pt == (6, 6)
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('prohibited', [False, True])
def test_counter_prohibition_and_doubling_use_native_replacements(cards, name, prohibited):
    s = game(cards)
    put(s, 'Solemnity' if prohibited else 'Doubling Season', 'battlefield')
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if name == NAMES[3]:
        # Explicit table setup is not an effect and does not use replacement doubling.
        act(s, 'p1', type='counter', card_ids=[a.id], kind='+1/+1', delta=2)
    if name == NAMES[2]:
        for n in ['Forest', 'Island', 'Mountain']:
            put(s, n, 'graveyard')
    cast(s, name, [] if name == NAMES[2] else [a.id, enemy.id] if name == NAMES[3] else [a.id],
         grave=name in (NAMES[0], NAMES[2]), teamwork=b if name == NAMES[1] else None)
    settle(s)
    if name == NAMES[2]:
        made = [c for c in s.state.cards.values() if c.is_token and c.name == 'Cadet' and c.zone == 'p1:battlefield']
        assert len(made) == (2 if prohibited else 4)
        assert all(c.counters == ({} if prohibited else {'+1/+1': 2}) for c in made)
    else:
        initial = 2 if name == NAMES[3] else 0
        assert counters(s, a) == initial + (0 if prohibited else 2)
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_genuine_cold_pending_cast_keeps_original_targets_payments_and_created_refs(cards, tmp_path, name):
    import os
    import subprocess
    import sys

    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if name == NAMES[3]:
        act(s, 'p1', type='counter', card_ids=[a.id], kind='+1/+1', delta=2)
    if name == NAMES[2]:
        for n in ['Forest', 'Island', 'Mountain', 'Giant Growth', 'Past in Flames', 'Snapcaster Mage']:
            put(s, n, 'graveyard')
    cast(s, name, [] if name == NAMES[2] else [a.id, enemy.id] if name == NAMES[3] else [a.id],
         grave=name in (NAMES[0], NAMES[2]), teamwork=b if name == NAMES[1] else None)
    saved = tmp_path / 'pending.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_library_look import settle
r = CardRepository(Path(sys.argv[2]), ImageStore(Path(sys.argv[2]).parent/'images'))
s = GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()), cards=r)
name, a, b, enemy = sys.argv[3:]
settle(s)
assert s.state.rules.decision is None
if name == 'Recursive Recruitment':
 made = [c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield' and c.name=='Cadet']
 assert len(made)==2 and all(c.counters=={'+1/+1':2} for c in made)
elif name == "Ent's Fury":
 assert s.state.cards[a].counters=={'+1/+1':3}
 assert s.state.cards[enemy].zone=='p2:graveyard'
else:
 assert s.state.cards[a].counters=={'+1/+1':1}
 if name=='Moment of Glory':assert s.state.cards[b].counters=={'+1/+1':1}
 else:assert s.state.cards[b].tapped and 'trample' in Plan(s.state,'p1',r,None).ch(s.state.cards[a]).keywords
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, a.id, b.id, enemy.id],
                            capture_output=True, text=True, timeout=90, env=os.environ.copy())
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', [NAMES[0], NAMES[2]])
def test_native_copy_of_graveyard_cast_was_not_cast_from_graveyard(cards, name):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    if name == NAMES[2]:
        for n in ['Forest', 'Island', 'Mountain']:
            put(s, n, 'graveyard')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, name, [a.id] if name == NAMES[0] else [], grave=True)
    copier = put(s, 'Twincast', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2})
    act(s, 'p1', type='cast_spell', card_id=copier.id, targets=[source.id], sources=[])
    for _ in range(40):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        assert 'keep' in {o.id for o in d.options}, d
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep'])
    assert s.state.rules.decision is None
    if name == NAMES[0]:
        assert counters(s, a) == 2 and counters(s, b) == 1
    else:
        made = [c for c in s.state.cards.values() if c.is_token and c.name == 'Cadet' and c.zone == 'p1:battlefield']
        # The copy makes two without counters. Twincast has resolved into the graveyard
        # by the original's counter instruction; four cards there still give one each.
        assert len(made) == 4 and sorted(c.counters.get('+1/+1', 0) for c in made) == [0, 0, 1, 1]
    roundtrip(s)
