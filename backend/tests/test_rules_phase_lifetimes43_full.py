"""Canonical production Out of Time and native lifetime proofs."""
import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests import test_rules_sacrifice_entry_outcomes43 as fixtures
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_linked_aggregates import cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Out of Time'


@pytest.fixture()
def cards(settings):
    yield from fixtures.cards.__wrapped__(settings)


def scene(cards):
    names = [c['name'] for c in fixtures.DATA] + ['Grizzly Bears', 'Bonesplitter']
    return table(cards, names, names, names)


def test_full_canonical_production(cards):
    q = coverage.of_card_data(cards.resolve(NAME))
    assert q.level == 'FULL', [(f.label, f.supported) for f in q.features]


def test_actual_untap_then_phase_stunned_creature_and_count_direct_attachment_packet(cards):
    s = scene(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    gear = put(s, 'Bonesplitter', 'battlefield')
    enemy = put(s, 'Serra Angel', 'battlefield', pid='p2')
    act(s, 'p1', type='attach', card_ids=[gear.id], to=bear.id)
    act(s, 'p1', type='tap', card_ids=[bear.id, enemy.id], tapped=True)
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='stun', delta=1)
    original = s.state.rules.object_id(bear.id)
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    assert s.state.cards[source.id].counters == {'time': 2}
    assert s.state.cards[bear.id].tapped and not s.state.cards[bear.id].counters
    assert not s.state.cards[enemy.id].tapped
    assert all(s.state.cards[c.id].zone.endswith(':phased') for c in (bear, gear, enemy))
    assert s.state.cards[gear.id].phased_indirect
    to_phase(s, 'main1', turn=4)
    assert s.state.cards[bear.id].zone == 'p1:phased'
    assert s.state.cards[source.id].counters == {'time': 1}
    spell = put(s, 'Naturalize', 'hand')
    cast(s, spell, targets=[source.id])
    settle(s)
    assert all(s.state.cards[c.id].zone.endswith(':battlefield') for c in (bear, gear, enemy))
    assert s.state.rules.object_id(bear.id) == original
    assert s.state.cards[gear.id].attached_to == bear.id
    assert not s.state.rules.phase_lifetimes
    roundtrip(s)


def test_actual_no_creatures_no_time_counter_no_vanishing_sacrifice(cards):
    s = scene(cards)
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    assert not s.state.cards[source.id].counters and not s.state.rules.phase_lifetimes
    to_phase(s, 'main1', turn=4)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert not s.state.cards[source.id].counters
    roundtrip(s)


def test_actual_last_time_counter_vanishing_releases_same_objects(cards):
    s = scene(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    oid = s.state.rules.object_id(bear.id)
    to_phase(s, 'main1', turn=4)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.rules.object_id(bear.id) == oid
    assert not Plan(s.state, 'p1', cards, None).rules.phase_lifetimes
    roundtrip(s)


def test_actual_stifle_last_counter_sacrifice_keeps_duration_until_source_leaves(cards):
    s = scene(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    to_phase(s, 'upkeep', turn=4)
    for _ in range(12):
        if not s.state.cards[source.id].counters:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert not s.state.cards[source.id].counters
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    trigger = s.state.zones['stack'][-1]
    spell = put(s, 'Stifle', 'hand')
    cast(s, spell, targets=[trigger])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    to_phase(s, 'main1', turn=7)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].zone == 'p1:phased'
    spell = put(s, 'Naturalize', 'hand')
    cast(s, spell, targets=[source.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert not s.state.rules.phase_lifetimes
    roundtrip(s)


def test_actual_source_destroyed_in_response_only_untaps_original_creatures(cards):
    s = scene(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[bear.id], tapped=True)
    source = put(s, NAME, 'hand')
    cast(s, source)
    for _ in range(12):
        if s.state.cards[source.id].zone == 'p1:battlefield':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.zones.get('stack')
    spell = put(s, 'Naturalize', 'hand')
    cast(s, spell, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[bear.id].zone == 'p1:battlefield' and not s.state.cards[bear.id].tapped
    assert not s.state.rules.phase_lifetimes
    roundtrip(s)


def test_actual_animated_source_phases_itself_and_does_not_expire_at_untap(cards):
    s = scene(cards)
    put(s, 'Opalescence', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    oid = s.state.rules.object_id(source.id)
    assert s.state.cards[source.id].zone == 'p1:phased'
    assert not s.state.cards[source.id].counters
    assert s.state.cards[bear.id].zone == 'p1:phased'
    to_phase(s, 'main1', turn=4)
    assert s.state.cards[source.id].zone == 'p1:phased'
    assert s.state.cards[bear.id].zone == 'p1:phased'
    assert s.state.rules.object_id(source.id) == oid
    assert len(s.state.rules.phase_lifetimes) == 1
    roundtrip(s)


def test_counter_replacement_creature_phases_before_time_counters_are_put(cards):
    s = scene(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    opponent = put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].counters == {'time': 4}
    assert s.state.cards[opponent.id].zone == 'p2:phased'
    assert s.state.cards[bear.id].zone == 'p1:phased'
    roundtrip(s)


def test_actual_self_phased_source_owner_departure_releases_enemy_true_cold(cards, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    s = scene(cards)
    put(s, 'Opalescence', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:phased'
    saved = tmp_path / 'outoftime43-self.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_wave30m_durations import to_phase
saved, db, source, bear = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent/'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
oid = s.state.rules.object_id(bear)
to_phase(s,'main1',turn=4)
assert s.state.cards[source].zone == 'p1:phased'
assert s.state.cards[bear].zone == 'p2:phased'
s.perform('p1',{'type':'concede'})
assert s.state.cards[bear].zone == 'p2:battlefield'
assert s.state.rules.object_id(bear) == oid and not s.state.rules.phase_lifetimes
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), source.id, bear.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('first,expected', [('Doubling Season', 1), ('Vorinclex', 0)])
def test_actual_phase_packet_and_time_counter_order_true_cold(cards, tmp_path, first, expected):
    import subprocess
    import sys
    from pathlib import Path

    s = scene(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    opponent = put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    aura = put(s, 'One with the Stars', 'hand')
    cast(s, aura, targets=[opponent.id])
    settle(s)
    assert not Plan(s.state,'p1',cards,None).ch(s.state.cards[opponent.id]).is_creature
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    assert s.state.rules.decision is not None
    assert s.state.cards[bear.id].zone == 'p1:phased'
    saved = tmp_path / 'outoftime43.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import put, settle
from tests.test_rules_linked_aggregates import cast
from tests.test_rules_wave30m_durations import to_phase
saved, db, source, bear, first, expected = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent/'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
oid = s.state.rules.object_id(bear)
for _ in range(10):
    d = s.state.rules.decision
    if d is None: break
    option = next(o for o in d.options if first in o.label)
    s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[option.id]})
    settle(s)
assert s.state.cards[source].counters == ({'time':int(expected)} if int(expected) else {})
assert s.state.cards[bear].zone == 'p1:phased'
to_phase(s,'main1',turn=4)
if int(expected):
    assert s.state.cards[source].zone == 'p1:graveyard'
else:
    assert s.state.cards[source].zone == 'p1:battlefield'
    assert s.state.cards[bear].zone == 'p1:phased'
    spell = put(s,'Naturalize','hand')
    cast(s,spell,targets=[source])
    settle(s)
assert s.state.cards[bear].zone == 'p1:battlefield'
assert s.state.rules.object_id(bear) == oid and not s.state.rules.phase_lifetimes
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), source.id, bear.id, first, str(expected)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
