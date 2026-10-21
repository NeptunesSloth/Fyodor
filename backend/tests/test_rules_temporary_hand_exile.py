"""Temporary hand exile keeps distinct exact groups through draws and delayed returns."""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.visibility import SPECTATOR
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave18a_down import unseen_by
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Memory Jar', 'Magus of the Jar', 'Induced Amnesia', 'Suppress', 'Psychic Theft', "Planeswalker's Mischief"]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/temporary_hand_exile_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='the', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    support = ['Grizzly Bears', 'Counterspell', 'Unsummon', 'Naturalize', 'Lightning Bolt', 'Stinkweed Imp', 'Into the Roil']
    s = table(cards, [name, name, *support], support, support)
    for p in ['p1', 'p2', 'p3']:
        act(s, p, type='set_prefs', hold_priority=True)
    source = put(s, name, 'battlefield' if name in ['Memory Jar', 'Magus of the Jar', "Planeswalker's Mischief"] else 'hand')
    if name == 'Magus of the Jar':
        to_phase(s, 'main1', turn=4)
    for p in ['p1', 'p2', 'p3']:
        put(s, 'Grizzly Bears', 'hand', pid=p)
        put(s, 'Lightning Bolt', 'hand', pid=p)
    return s, source


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', ['Memory Jar', 'Magus of the Jar'])
def test_jar_native_sacrifice_exiles_all_original_hands_draws_and_returns(cards, name):
    s, source = setup(cards, name)
    original = {p: Counter(s.state.cards[c].card_id for c in s.state.zones.get(f'{p}:hand', [])) for p in s.state.players}
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    for p, printed in original.items():
        assert len(s.state.zones[f'{p}:hand']) == 7
        exiled = [s.state.cards[c] for c in s.state.zones.get(f'{p}:exile', [])]
        assert Counter(c.card_id for c in exiled) == printed
        for c in exiled:
            assert c.zone == f'{p}:exile' and c.face_down
            assert unseen_by(s, c, 'p1', 'p2', 'p3', SPECTATOR)
    roundtrip(s)
    turn = s.state.turn.number
    to_phase(s, 'end', turn=turn)
    settle(s)
    for p, printed in original.items():
        hand = [s.state.cards[c] for c in s.state.zones[f'{p}:hand']]
        assert Counter(c.card_id for c in hand) == printed
        assert all(not c.face_down for c in hand)
    roundtrip(s)


def test_suppress_waits_for_targets_next_turn_end_not_current_turn(cards):
    s, source = setup(cards, 'Suppress')
    original = Counter(s.state.cards[c].card_id for c in s.state.zones['p1:hand'] if c != source.id)
    mana(s, C=2, B=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p1'])
    settle(s)
    assert Counter(s.state.cards[c].card_id for c in s.state.zones['p1:exile']) == original
    to_phase(s, 'end', turn=1)
    settle(s)
    assert Counter(s.state.cards[c].card_id for c in s.state.zones['p1:exile']) == original
    to_phase(s, 'end', turn=4)
    settle(s)
    returned = Counter(s.state.cards[c].card_id for c in s.state.zones['p1:hand'])
    assert returned >= original
    roundtrip(s)


@pytest.mark.parametrize('departure', ['graveyard', 'hand'])
def test_induced_amnesia_returns_only_when_source_goes_to_graveyard(cards, departure):
    s, source = setup(cards, 'Induced Amnesia')
    original = list(s.state.zones['p2:hand'])
    mana(s, C=3, U=2, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    # The ETB's default target may be p1; target p2 explicitly in a separate trigger choice if asked.
    linked = s.state.rules.exiled_with.get(s.state.rules.object_id(source.id), [])
    assert linked
    linked_ids = [o.rsplit('.', 1)[0] for o in linked]
    removal = put(s, 'Naturalize' if departure == 'graveyard' else 'Into the Roil', 'hand')
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    assert all(s.state.cards[c].zone.endswith(':hand' if departure == 'graveyard' else ':exile') for c in linked_ids)
    assert original
    roundtrip(s)


def test_psychic_theft_declined_cast_returns_only_original_exile_object(cards):
    s, source = setup(cards, 'Psychic Theft')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'])
    settle(s)
    permissions = [p for p in s.state.rules.permissions if p.player == 'p1']
    assert len(permissions) == 1
    stolen = permissions[0].card
    assert s.state.cards[stolen].zone == 'p2:exile'
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[stolen].zone == 'p2:hand'
    roundtrip(s)


def test_mischief_random_reveal_and_free_permission(cards):
    s, source = setup(cards, "Planeswalker's Mischief")
    # One possible card makes the random outcome certain without replacing RNG.
    for cid in list(s.state.zones['p2:hand']):
        if s.state.cards[cid].name != 'Lightning Bolt':
            act(s, 'p2', type='move', card_ids=[cid], to={'player': 'p2', 'zone': 'library'})
    mana(s, C=3, U=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=['p2'])
    settle(s)
    permissions = [p for p in s.state.rules.permissions if p.player == 'p1']
    assert len(permissions) == 1 and permissions[0].free
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[permissions[0].card].zone == 'p2:hand'
    roundtrip(s)


def test_induced_amnesia_source_dies_before_etb_resolves_no_later_return(cards):
    s, source = setup(cards, 'Induced Amnesia')
    mana(s, C=3, U=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    until(s, lambda s: s.state.cards[source.id].zone == 'p1:battlefield')
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    assert s.state.zones.get('stack')
    removal = put(s, 'Naturalize', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.zones.get('p2:exile') and all(s.state.cards[c].face_down for c in s.state.zones['p2:exile'])
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.zones.get('p2:exile')
    roundtrip(s)


@pytest.mark.parametrize('countered', [False, True])
def test_psychic_theft_actual_paid_cast_never_returns_a_cast_object(cards, countered):
    s, source = setup(cards, 'Psychic Theft')
    mana(s, C=1, U=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'])
    settle(s)
    permission = next(p for p in s.state.rules.permissions if p.player == 'p1')
    stolen = permission.card
    assert s.state.cards[stolen].name == 'Lightning Bolt'
    act(s, 'p1', type='cast_spell', card_id=stolen, targets=['p3'])
    if countered:
        counter = put(s, 'Counterspell', 'hand', pid='p2')
        mana(s, pid='p2', U=2)
        wait_priority(s, 'p2')
        act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[stolen])
    settle(s)
    assert s.state.cards[stolen].zone == 'p2:graveyard'
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[stolen].zone == 'p2:graveyard'
    assert s.state.players['p3'].life == (40 if countered else 37)
    roundtrip(s)


def test_two_jar_groups_remain_distinct_at_shared_end_step(cards):
    s, first = setup(cards, 'Memory Jar')
    second = next(c for c in s.state.cards.values() if c.name == 'Memory Jar' and c.id != first.id)
    act(s, 'p1', type='move', card_ids=[second.id], to={'player': 'p1', 'zone': 'battlefield'})
    original = {p: Counter(s.state.cards[c].card_id for c in s.state.zones.get(f'{p}:hand', [])) for p in s.state.players}
    act(s, 'p1', type='activate_ability', card_id=first.id, ability=0)
    act(s, 'p1', type='activate_ability', card_id=second.id, ability=0)
    settle(s)
    assert len(s.state.rules.delayed) == 2
    groups = []
    for trigger in s.state.rules.delayed:
        binding = trigger.effects[0]['refs']['temporary_hand']['objects']
        group = {p: Counter() for p in s.state.players}
        for ref in binding:
            c = s.state.cards[ref['card']]
            group[c.owner][c.card_id] += 1
        groups.append(group)
    assert original in groups and groups[0] != groups[1]
    to_phase(s, 'end', turn=1)
    settle(s)
    final = {p: Counter(s.state.cards[c].card_id for c in s.state.zones.get(f'{p}:hand', [])) for p in s.state.players}
    assert final in groups
    assert not s.state.rules.delayed
    roundtrip(s)


def test_jar_cold_native_dredge_pause_keeps_all_exact_hands(cards, tmp_path):
    s, source = setup(cards, 'Memory Jar')
    put(s, 'Stinkweed Imp', 'graveyard', pid='p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == 'p2' and any(o.id == 'decline' for o in d.options)
    # Native draw replacement selection stages the whole APNAP draw sequence
    # before committing its actions; every original hand is already exiled.
    assert all(not s.state.zones.get(f'{p}:hand') for p in s.state.players)
    assert all(s.state.cards[c].face_down for p in s.state.players for c in s.state.zones.get(f'{p}:exile', []))
    original = {p: Counter(s.state.cards[c].card_id for c in s.state.zones.get(f'{p}:exile', [])) for p in s.state.players}
    saved = tmp_path / 'jar-draw.json'
    saved.write_text(s.state.model_dump_json())
    expected = tmp_path / 'expected.json'
    expected.write_text(json.dumps(original))
    code = r'''
import json,sys
from collections import Counter
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved,db,expected=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
for _ in range(100):
 d=s.state.rules.decision
 if d is not None:
  ids=['decline'] if any(o.id=='decline' for o in d.options) else [o.id for o in d.options][:max(1,d.min_choices)]
  if d.kind=='declare_attackers':s.perform(d.player,{'type':'declare_attackers','attackers':[]});continue
  if d.kind=='declare_blockers':s.perform(d.player,{'type':'declare_blockers','blocks':[]});continue
  s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':ids})
 elif s.state.turn.phase=='end' and not s.state.zones.get('stack'):break
 else:s.perform(s.state.rules.priority,{'type':'pass_priority'})
else:raise AssertionError('not completed')
original=json.loads(Path(expected).read_text())
for p,counts in original.items():assert Counter(s.state.cards[c].card_id for c in s.state.zones.get(p+':hand',[]))==Counter(counts)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), str(expected)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_mischief_native_free_cast_survives_original_source_departure(cards):
    s, source = setup(cards, "Planeswalker's Mischief")
    for cid in list(s.state.zones['p2:hand']):
        if s.state.cards[cid].name != 'Lightning Bolt':
            act(s, 'p2', type='move', card_ids=[cid], to={'player': 'p2', 'zone': 'library'})
    mana(s, C=4, U=1, G=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=['p2'])
    settle(s)
    permission = next(p for p in s.state.rules.permissions if p.player == 'p1')
    removal = put(s, 'Naturalize', 'hand')
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    stolen = permission.card
    act(s, 'p1', type='cast_spell', card_id=stolen, free=True, targets=['p3'])
    settle(s)
    assert s.state.players['p3'].life == 37 and s.state.cards[stolen].zone == 'p2:graveyard'
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[stolen].zone == 'p2:graveyard'
    roundtrip(s)
