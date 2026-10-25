"""Actual original-control/LKI cohorts, delayed snapshots and native entry batches."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import put
from tests.test_rules_library_packets101 import advance, cast, cold
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/library_polymorph102_cards.json').read_text())


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        extra = {k: v for k, v in c.items() if k not in {'name', 'set_code', 'number', 'id'}}
        base[c['name']] = card(c['name'], set_code='lpoly102', number=str(i), **extra)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Divergent Transformations', 'Reality Scramble', 'Indomitable Creativity', 'Synthetic Destiny']


def setup(cards):
    names = [c['name'] for c in DATA]
    decks = [deck(cards, 'Krenko, Mob Boss', [(2, n) for n in names] + [(40, 'Forest')]),
             deck(cards, "Atraxa, Praetors' Voice", [(2, n) for n in names] + [(40, 'Island')])]
    s = GameSession(enable(new_game([PlayerSetup('Alice', cards=decks[0]), PlayerSetup('Bob', cards=decks[1])], shuffle=False)), cards=cards)
    to_phase(s, 'main1', 1)
    act(s, 'p1', type='set_stops', own=['main1', 'end'], others=['main1', 'end'], smart_pass=False)
    act(s, 'p1', type='add_mana', player='p1', mana={c: 50 for c in ['C', 'W', 'U', 'B', 'R', 'G']})
    return s


def top(s, names, owner='p1'):
    ids = [put(s, n, 'hand', owner).id for n in names]
    for cid in reversed(ids):
        act(s, owner, type='move', card_ids=[cid], to={'player': owner, 'zone': 'library'}, position='top')
    return ids


@pytest.mark.parametrize('name', NAMES)
def test_canonical_whole102(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_divergent_actual_two_libraries_and_original_controller102(cards):
    s = setup(cards)
    a, b = put(s, 'Walking Corpse', 'battlefield'), put(s, 'Grizzly Bears', 'battlefield', 'p2')
    mine = top(s, ['Forest', 'Hill Giant', 'Lightning Bolt'])
    theirs = top(s, ['Island', 'Champion of the Perished', 'Lightning Bolt'], 'p2')
    cast(s, 'Divergent Transformations', targets=[a.id, b.id], target_counts=[2])
    advance(s)
    assert s.state.cards[a.id].zone == 'p1:exile' and s.state.cards[b.id].zone == 'p2:exile'
    assert s.state.cards[mine[1]].zone == 'p1:battlefield'
    assert s.state.cards[theirs[1]].zone == 'p2:battlefield'
    assert s.state.cards[theirs[1]].controller == 'p2'


def test_divergent_same_controller_enters_sequentially_second_champion_sees_no_first102(cards):
    s = setup(cards)
    old = [c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Walking Corpse'][:2]
    act(s, 'p1', type='move', card_ids=old, to={'player': 'p1', 'zone': 'battlefield'})
    # Shuffle after each creature, so retain only this ordered library for the first hit.
    mine = top(s, ['Champion of the Perished', 'Diregraf Ghoul'])
    rest = [c for c in s.state.zones['p1:library'] if c not in mine]
    act(s, 'p1', type='move', card_ids=rest, to={'player': 'p1', 'zone': 'exile'})
    cast(s, 'Divergent Transformations', targets=old, target_counts=[2])
    advance(s)
    assert {c.name for c in s.state.cards.values() if c.owner == 'p1' and c.zone == 'p1:battlefield'} >= {'Champion of the Perished', 'Diregraf Ghoul'}
    assert s.state.cards[mine[0]].counters.get('+1/+1') == 1


def test_reality_scramble_uses_original_battlefield_types_not_card_in_library102(cards):
    s = setup(cards)
    target = put(s, 'Forest', 'battlefield')
    cast(s, 'Animate Land', targets=[target.id])
    advance(s)
    ids = top(s, ['Lightning Bolt', 'Grizzly Bears', 'Island'])
    cast(s, 'Reality Scramble', targets=[target.id])
    advance(s)
    assert s.state.cards[ids[1]].zone == 'p1:battlefield'
    assert s.state.cards[ids[2]].zone == 'p1:library'


def test_reality_kindred_instant_stops_but_cannot_enter_battlefield102(cards):
    s = setup(cards)
    target = put(s, 'Bitterblossom', 'battlefield')
    ids = top(s, ['Forest', 'Crib Swap', 'Demonic Vigor'])
    cast(s, 'Reality Scramble', targets=[target.id])
    advance(s)
    assert s.state.cards[ids[1]].zone == 'p1:library'
    assert s.state.zones['p1:library'][0] == ids[1]
    assert s.state.cards[ids[2]].zone == 'p1:library'


def test_creativity_counts_actual_destroyed_not_indestructible_and_rip_counts102(cards):
    s = setup(cards)
    a, b = put(s, 'Walking Corpse', 'battlefield'), put(s, 'Darksteel Ingot', 'battlefield')
    cast(s, 'Rest in Peace')
    advance(s)
    mine = top(s, ['Forest', 'Grizzly Bears', 'Hill Giant'])
    cast(s, 'Indomitable Creativity', x_value=2, targets=[a.id, b.id], target_counts=[2])
    advance(s)
    assert s.state.cards[a.id].zone == 'p1:exile' and s.state.cards[b.id].zone == 'p1:battlefield'
    assert s.state.cards[mine[1]].zone == 'p1:battlefield'
    assert any(c.name == 'Hill Giant' and c.zone == 'p1:library' for c in s.state.cards.values())


def test_creativity_all_gathered_creatures_enter_simultaneously102(cards):
    s = setup(cards)
    old = [c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Walking Corpse'][:2]
    act(s, 'p1', type='move', card_ids=old, to={'player': 'p1', 'zone': 'battlefield'})
    mine = top(s, ['Diregraf Ghoul', 'Champion of the Perished', 'Forest'])
    cast(s, 'Indomitable Creativity', x_value=2, targets=old, target_counts=[2])
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:battlefield' for c in mine[:2])
    assert s.state.cards[mine[1]].counters.get('+1/+1') == 1


def test_synthetic_delayed_original_count_and_simultaneous_entries102(cards):
    s = setup(cards)
    old = [c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Walking Corpse'][:2]
    act(s, 'p1', type='move', card_ids=old, to={'player': 'p1', 'zone': 'battlefield'})
    mine = top(s, ['Lightning Bolt', 'Diregraf Ghoul', 'Island', 'Champion of the Perished'])
    cast(s, 'Synthetic Destiny')
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in old)
    to_phase(s, 'end', 1)
    advance(s)
    assert all(s.state.cards[c].zone == 'p1:battlefield' for c in [mine[1], mine[3]])
    assert s.state.cards[mine[3]].counters.get('+1/+1') == 1


def test_genuine_cold_synthetic_delayed_snapshot_survives_before_trigger102(cards, tmp_path):
    s = setup(cards)
    old = put(s, 'Walking Corpse', 'battlefield')
    mine = top(s, ['Lightning Bolt', 'Grizzly Bears', 'Island'])
    cast(s, 'Synthetic Destiny')
    advance(s)
    cold(s, tmp_path, {'old': old.id, 'mine': mine}, '''from tests.test_rules_wave30m_durations import to_phase
to_phase(s,'end',1);advance(s)
assert s.state.cards[extra['old']].zone=='p1:exile'
assert s.state.cards[extra['mine'][1]].zone=='p1:battlefield'
''')


def test_divergent_uses_current_controller_not_owner_after_actual_theft102(cards):
    s = setup(cards)
    a, b = put(s, 'Walking Corpse', 'battlefield'), put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Act of Treason', targets=[b.id])
    advance(s)
    assert s.state.cards[b.id].controller == 'p1' and s.state.cards[b.id].owner == 'p2'
    mine = top(s, ['Champion of the Perished', 'Diregraf Ghoul'])
    rest = [c for c in s.state.zones['p1:library'] if c not in mine]
    act(s, 'p1', type='move', card_ids=rest, to={'player': 'p1', 'zone': 'exile'})
    theirs = list(s.state.zones['p2:library'])
    cast(s, 'Divergent Transformations', targets=[a.id, b.id], target_counts=[2])
    advance(s)
    assert s.state.zones['p2:library'] == theirs
    entered = [c for c in s.state.cards.values() if c.owner == 'p1' and c.zone == 'p1:battlefield']
    assert {c.name for c in entered} >= {'Champion of the Perished', 'Diregraf Ghoul'}
    assert s.state.cards[b.id].zone == 'p2:exile'


def test_synthetic_actual_tokens_cease_but_delayed_count_remains_two102(cards):
    s = setup(cards)
    cast(s, 'Raise the Alarm')
    advance(s)
    tokens = [c.id for c in s.state.cards.values() if c.is_token and c.controller == 'p1' and c.zone == 'p1:battlefield']
    assert len(tokens) == 2
    mine = top(s, ['Lightning Bolt', 'Diregraf Ghoul', 'Island', 'Champion of the Perished'])
    cast(s, 'Synthetic Destiny')
    advance(s)
    assert all(cid not in s.state.cards for cid in tokens)
    to_phase(s, 'end', 1)
    advance(s)
    assert all(s.state.cards[cid].zone == 'p1:battlefield' for cid in [mine[1], mine[3]])
    assert s.state.cards[mine[3]].counters.get('+1/+1') == 1


@pytest.mark.parametrize('answer', ['yes', 'no'])
def test_genuine_cold_reality_commander_library_choice_precedes_reveal102(cards, tmp_path, answer):
    s = setup(cards)
    target = put(s, 'Krenko, Mob Boss', 'battlefield')
    mine = top(s, ['Forest', 'Grizzly Bears', 'Island'])
    cast(s, 'Reality Scramble', targets=[target.id])
    advance(s, stop=lambda d: d.resume.get('step') == 'commander_first')
    assert s.state.rules.decision is not None
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    cold(s, tmp_path, {'target': target.id, 'mine': mine, 'answer': answer}, '''d=s.state.rules.decision
assert d.resume['step']=='commander_first'
act(s,d.player,type='choose',decision_id=d.id,option_ids=[extra['answer']]);advance(s)
assert s.state.cards[extra['target']].zone=='p1:'+('command' if extra['answer']=='yes' else 'library')
assert s.state.cards[extra['mine'][1]].zone=='p1:battlefield'
''')
