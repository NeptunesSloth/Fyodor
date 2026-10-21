"""Actual nonhand cast history, demonstrate grants and permanent copy riders."""
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
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/nonhand_cast_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='evc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Surge of Brilliance', 'Impending Flux', 'The Twelfth Doctor', 'Spider-Verse', 'Mizzix, Replica Rider']


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def grant(s):
    will = put(s, "Yawgmoth's Will", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=will.id)
    settle(s)


def answer_copies(s):
    for _ in range(30):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return
        ids = {o.id for o in d.options}
        option = next((value for value in ['yes', 'pay', 'keep', 'same', 'p2'] if value in ids), None)
        assert option is not None, (d.resume, [(o.id, o.label) for o in d.options])
        pick(s, [option])
    raise AssertionError('copy continuation did not finish')


@pytest.mark.parametrize('zone,drawn', [('hand', 1), ('graveyard', 2)])
def test_surge_counts_only_actual_nonhand_casts_including_itself(cards, zone, drawn):
    s = table(cards, ['Surge of Brilliance', "Yawgmoth's Will", 'Lightning Bolt'])
    grant(s)
    bolt = put(s, 'Lightning Bolt', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    settle(s)
    source = put(s, 'Surge of Brilliance', zone)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert len(s.state.zones['p1:hand']) == before - int(zone == 'hand') + drawn
    roundtrip(s)


@pytest.mark.parametrize('zone,damage', [('hand', 2), ('graveyard', 3)])
def test_flux_uses_current_nonhand_cast_count_for_opponents_and_their_creatures(cards, zone, damage):
    s = table(cards, ['Impending Flux', "Yawgmoth's Will", 'Lightning Bolt', 'Grizzly Bears'], ['Air Elemental'])
    own = put(s, 'Grizzly Bears', 'battlefield')
    creature = put(s, 'Air Elemental', 'battlefield', 'p2')
    grant(s)
    bolt = put(s, 'Lightning Bolt', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    settle(s)
    before = {p: s.state.players[p].life for p in ['p2', 'p3']}
    source = put(s, 'Impending Flux', zone)
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert all(s.state.players[p].life == before[p] - damage for p in before)
    assert s.state.cards[creature.id].damage == damage
    assert s.state.cards[own.id].damage == 0
    roundtrip(s)


@pytest.mark.parametrize('early', [False, True])
def test_doctor_first_nonhand_spell_counts_casts_before_source_entered(cards, early):
    s = table(cards, ['The Twelfth Doctor', "Yawgmoth's Will", 'Lightning Bolt', 'Shock'])
    doctor = put(s, 'The Twelfth Doctor', 'battlefield') if early else None
    grant(s)
    bolt = put(s, 'Lightning Bolt', 'graveyard')
    shock = put(s, 'Shock', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 2})
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    answer_copies(s)
    if not early:
        doctor = put(s, 'The Twelfth Doctor', 'battlefield')
    act(s, 'p1', type='cast_spell', card_id=shock.id, targets=['p2'])
    answer_copies(s)
    assert s.state.cards[doctor.id].counters == ({'+1/+1': 1} if early else {})
    roundtrip(s)


@pytest.mark.parametrize('name', ['Spider-Verse', 'Mizzix, Replica Rider'])
def test_copied_permanent_gains_haste_and_mizzix_copy_sacrifices_at_end(cards, name):
    from app.rules.plan import Plan
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards, [name, "Yawgmoth's Will", 'Grizzly Bears'])
    put(s, name, 'battlefield')
    grant(s)
    original = put(s, 'Grizzly Bears', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'R': 1, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=original.id)
    answer_copies(s)
    bears = [c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.zone.endswith(':battlefield')]
    assert len(bears) == 2
    copy = next(c for c in bears if c.id != original.id)
    assert 'haste' in Plan(s.state, 'p1', cards, None).ch(copy).keywords
    assert 'haste' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[original.id]).keywords
    to_phase(s, 'end', turn=1)
    settle(s)
    assert (copy.id not in s.state.cards) if name == 'Mizzix, Replica Rider' else copy.id in s.state.cards
    assert s.state.cards[original.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_spider_failed_uncopyable_spell_does_not_consume_once(cards):
    s = table(cards, ['Spider-Verse', "Yawgmoth's Will", 'Display of Power', 'Grizzly Bears'])
    put(s, 'Spider-Verse', 'battlefield')
    grant(s)
    spell = put(s, 'Display of Power', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[], target_counts=[0])
    answer_copies(s)
    bear = put(s, 'Grizzly Bears', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    answer_copies(s)
    assert sum(c.name == 'Grizzly Bears' and c.zone.endswith(':battlefield') for c in s.state.cards.values()) == 2
    roundtrip(s)


@pytest.mark.parametrize('name,decline', [('Spider-Verse', 'no'), ('Mizzix, Replica Rider', 'decline')])
def test_declined_copy_leaves_original_without_haste(cards, name, decline):
    from app.rules.plan import Plan
    s = table(cards, [name, "Yawgmoth's Will", 'Grizzly Bears', 'Hill Giant'])
    put(s, name, 'battlefield')
    grant(s)
    bear = put(s, 'Grizzly Bears', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'R': 1, 'C': 5})
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    assert decline in {o.id for o in d.options}, [(o.id, o.label) for o in d.options]
    pick(s, [decline])
    settle(s)
    assert sum(c.name == 'Grizzly Bears' and c.zone.endswith(':battlefield') for c in s.state.cards.values()) == 1
    assert 'haste' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).keywords
    if name == 'Spider-Verse':
        giant = put(s, 'Hill Giant', 'graveyard')
        act(s, 'p1', type='cast_spell', card_id=giant.id)
        answer_copies(s)
        assert sum(c.name == 'Hill Giant' and c.zone.endswith(':battlefield') for c in s.state.cards.values()) == 2
    roundtrip(s)


def test_mizzix_pending_payment_cold_resume(cards, tmp_path):
    import subprocess
    import sys
    s = table(cards, ['Mizzix, Replica Rider', "Yawgmoth's Will", 'Grizzly Bears'], ['Unsummon'])
    source = put(s, 'Mizzix, Replica Rider', 'battlefield')
    grant(s)
    bear = put(s, 'Grizzly Bears', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'R': 1, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    while s.state.rules.priority != 'p2':
        act(s, s.state.rules.priority, type='pass_priority')
    bounce = put(s, 'Unsummon', 'hand', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    act(s, 'p2', type='cast_spell', card_id=bounce.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert s.state.rules.decision is not None
    path = tmp_path / 'mizzix-payment.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
path, database = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
for _ in range(80):
    d = s.state.rules.decision
    if d:
        ids = {o.id for o in d.options}
        option = next((v for v in ['pay', 'yes', 'keep', 'same', 'p2'] if v in ids), None)
        assert option is not None, (d.resume, ids)
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [option]})
    elif s.state.zones['stack']:
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
else:
    raise AssertionError('copy payment did not resolve')
bears = [c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.zone.endswith(':battlefield')]
assert len(bears) == 2
assert sum('haste' in Plan(s.state, 'p1', repo, None).ch(c).keywords for c in bears) == 1
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=90)
    assert result.returncode == 0, result.stderr


def test_two_doctors_grant_two_demonstrate_instances(cards):
    s = table(cards, ['The Twelfth Doctor', 'Spark Double', "Yawgmoth's Will", 'Lightning Bolt'])
    doctor = put(s, 'The Twelfth Doctor', 'battlefield')
    grant(s)
    double = put(s, 'Spark Double', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=double.id)
    settle(s)
    assert s.state.rules.decision is not None
    pick(s, [doctor.id])
    settle(s)
    bolt = put(s, 'Lightning Bolt', 'graveyard')
    before = s.state.players['p2'].life
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    answer_copies(s)
    assert s.state.players['p2'].life == before - 15
    assert s.state.cards[doctor.id].counters.get('+1/+1') == 2
    assert s.state.cards[double.id].counters.get('+1/+1') == 3
    roundtrip(s)


def test_silverquill_lecturer_grants_demonstrate_to_hand_creature(cards):
    assert coverage.of_card_data(cards.resolve('Silverquill Lecturer')).level == 'FULL'
    s = table(cards, ['Silverquill Lecturer', 'Grizzly Bears'])
    put(s, 'Silverquill Lecturer', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    answer_copies(s)
    bears = [c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.zone.endswith(':battlefield')]
    assert len(bears) == 3
    assert sum(c.controller == 'p1' for c in bears) == 2
    assert sum(c.controller == 'p2' for c in bears) == 1
    roundtrip(s)
