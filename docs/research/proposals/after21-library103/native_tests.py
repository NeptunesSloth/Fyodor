"""Native resolution, persistent public spell memory and upkeep copy replacements."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import put
from tests.test_rules_library_packets101 import advance, cast, cold, top
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/epic103_cards.json').read_text())
NAMES = [x['name'] for x in DATA[:5]]


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        extra = {k: v for k, v in c.items() if k not in {'name', 'set_code', 'number', 'id'}}
        base[c['name']] = card(c['name'], set_code='epic103', number=str(i), **extra)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, three=False):
    spells = [(2, c['name']) for c in DATA] + [(4, 'Lightning Bolt'), (40, 'Forest')]
    ds = [deck(cards, 'Krenko, Mob Boss', spells), deck(cards, "Atraxa, Praetors' Voice", spells)]
    players = [PlayerSetup('Alice', cards=ds[0]), PlayerSetup('Bob', cards=ds[1])]
    if three:
        players.append(PlayerSetup('Carol', cards=deck(cards, 'Krenko, Mob Boss', spells)))
    s = GameSession(enable(new_game(players, shuffle=False)), cards=cards)
    to_phase(s, 'main1', 1)
    for pid in ['p1', 'p2']:
        act(s, pid, type='set_stops', own=['upkeep', 'main1', 'end'], others=['upkeep', 'main1', 'end'], smart_pass=False)
        act(s, pid, type='add_mana', player=pid, mana={c: 50 for c in ['C', 'W', 'U', 'B', 'R', 'G']})
    put(s, 'Walking Corpse', 'hand')
    put(s, 'Grizzly Bears', 'hand')
    return s


def choose_search(s, name=None):
    advance(s, stop=lambda d: d.resume.get('step') == 'search')
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'search'
    choices = [o.id for o in d.options if name and s.state.cards[o.id].name == name]
    if not name:
        choices = [o.id for o in d.options[:d.min_choices]]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=choices[:d.max_choices])
    advance(s)


def upkeep(s, turn=3):
    to_phase(s, 'upkeep', turn)
    advance(s)


@pytest.mark.parametrize('name', NAMES)
def test_canonical103(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_swarm_native_persistent_not_cast_and_source_shuffled103(cards):
    s = setup(cards)
    c = cast(s, 'Endless Swarm')
    n = len(s.state.zones['p1:hand'])
    advance(s)
    assert sum(x.name == 'Snake' for x in s.state.cards.values()) == n
    assert len([x for x in s.state.rules.delayed if x.name == 'Endless Swarm']) == 1
    bolt = put(s, 'Lightning Bolt', 'hand')
    with pytest.raises(ActionError, match="can't cast"):
        act(s, 'p1', type='cast_spell', card_id=bolt.id, sources=[], targets=['p2'])
    original_id = c.id
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'})
    act(s, 'p1', type='shuffle', player='p1', zone='library')
    assert original_id not in s.state.cards
    upkeep(s)
    assert len([x for x in s.state.rules.delayed if x.name == 'Endless Swarm']) == 1
    assert sum(x.name == 'Snake' for x in s.state.cards.values()) == n + len(s.state.zones['p1:hand'])
    assert not s.state.rules.turn_log.casts
    from tests.test_rules_effects import replay_matches
    replay_matches(s)


def test_enduring_search_and_repeated_native_upkeep103(cards):
    s = setup(cards)
    cast(s, 'Enduring Ideal')
    choose_search(s, 'Doubling Season')
    assert any(c.name == 'Doubling Season' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    to_phase(s, 'upkeep', 3)
    choose_search(s, 'Doubling Season')
    assert len([c for c in s.state.cards.values() if c.name == 'Doubling Season' and c.zone == 'p1:battlefield']) == 2
    assert len(s.state.rules.cast_limits) == 1


def test_dominion_search_private_original_controller103(cards):
    s = setup(cards)
    cast(s, 'Eternal Dominion', targets=['p2'])
    advance(s, stop=lambda d: d.resume.get('step') == 'search')
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    target = next(o.id for o in d.options if s.state.cards[o.id].name == 'Hill Giant')
    assert s.state.cards[target].owner == 'p2'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target])
    advance(s)
    assert s.state.cards[target].zone == 'p1:battlefield' and s.state.cards[target].controller == 'p1'
    assert len(s.state.rules.cast_limits) == 1


def test_torment_counts_hand_on_each_resolution_and_quantity_search103(cards):
    s = setup(cards)
    cast(s, 'Neverending Torment', targets=['p2'])
    hand = len(s.state.zones['p1:hand'])
    advance(s, stop=lambda d: d.resume.get('step') == 'search')
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.min_choices == hand and d.max_choices == hand
    picked = [o.id for o in d.options[:hand]]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=picked)
    advance(s)
    assert all(s.state.cards[c].zone == 'p2:exile' for c in picked)
    hand_card = s.state.zones['p1:hand'][0]
    act(s, 'p1', type='move', card_ids=[hand_card], to={'player': 'p1', 'zone': 'exile'})
    to_phase(s, 'upkeep', 3)
    advance(s, stop=lambda d: d.resume.get('step') == 'search')
    d = s.state.rules.decision
    assert d is not None and d.min_choices == hand - 1 and d.max_choices == hand - 1
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options[:d.min_choices]])
    advance(s)


def test_flames_native_damage_original_card_mana_value103(cards):
    s = setup(cards)
    ids = top(s, ['Forest', 'Hill Giant', 'Lightning Bolt'])
    cast(s, 'Undying Flames', targets=['p2'])
    advance(s)
    assert s.state.players['p2'].life == 36
    assert all(s.state.cards[c].zone == 'p1:exile' for c in ids[:2])
    assert s.state.cards[ids[2]].zone == 'p1:library'
    assert len(s.state.rules.cast_limits) == 1


def test_countered_epic_never_sets_prohibition_or_trigger103(cards):
    s = setup(cards)
    c = cast(s, 'Endless Swarm')
    while s.state.rules.priority != 'p2':
        act(s, s.state.rules.priority, type='pass_priority')
    counter = put(s, 'Negate', 'hand', 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, sources=[], targets=[c.id])
    advance(s)
    assert not s.state.rules.cast_limits and not s.state.rules.delayed


def test_client_cannot_forge_preserved_copy103(cards):
    from app.game.rules_state import snapshot

    s = setup(cards)
    c = cast(s, 'Endless Swarm')
    with pytest.raises(ActionError, match='Only the rules engine'):
        act(s, 'p1', type='copy_card', card_id=c.id, saved_stack=snapshot(s.state, c.id).model_dump(mode='json'))


def test_cold_source_rekeyed_swarm103(cards, tmp_path):
    s = setup(cards)
    c = cast(s, 'Endless Swarm')
    advance(s)
    original_id = c.id
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'})
    act(s, 'p1', type='shuffle', player='p1', zone='library')
    assert original_id not in s.state.cards
    cold(s, tmp_path, {}, '''
from tests.test_rules_epic103 import upkeep
before = sum(c.name == 'Snake' for c in s.state.cards.values())
upkeep(s)
assert sum(c.name == 'Snake' for c in s.state.cards.values()) > before, (before, sum(c.name == 'Snake' for c in s.state.cards.values()), s.state.turn.model_dump(), [(t.name, t.when, t.once) for t in s.state.rules.delayed], s.state.rules.decision)
assert len([t for t in s.state.rules.delayed if t.name == 'Endless Swarm']) == 1
assert len(s.state.rules.cast_limits) == 1
''')


def test_epic_native_spell_copy_replacement_and_magecraft103(cards):
    s = setup(cards)
    put(s, 'Twinning Staff', 'battlefield')
    put(s, 'Witherbloom Apprentice', 'battlefield')
    cast(s, 'Endless Swarm')
    advance(s)
    assert s.state.players['p2'].life == 39
    before = sum(c.name == 'Snake' for c in s.state.cards.values())
    upkeep(s)
    after = sum(c.name == 'Snake' for c in s.state.cards.values())
    assert after - before == 2 * len(s.state.zones['p1:hand'])
    assert s.state.players['p2'].life == 37
    assert not s.state.rules.turn_log.casts
    assert len([t for t in s.state.rules.delayed if t.name == 'Endless Swarm']) == 1


@pytest.mark.parametrize('cold_resume', [False, True])
def test_epic_original_memory_retargets_after_cold_pause103(cards, tmp_path, cold_resume):
    s = setup(cards)
    top(s, ['Lightning Bolt', 'Hill Giant'])
    cast(s, 'Undying Flames', targets=['p2'])
    advance(s)
    assert s.state.players['p2'].life == 39
    to_phase(s, 'upkeep', 3)
    advance(s, stop=lambda d: d.resume.get('step') == 'copy_target')
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'copy_target'
    copied = d.resume['copy']
    assert all(x['do'] != 'epic_setup103' for x in s.state.rules.stack[copied].effects)
    from app.rules.plan import Plan
    assert not any(a.text == 'Epic' for a in Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[copied]).abilities)
    if cold_resume:
        cold(s, tmp_path, {}, '''
d=s.state.rules.decision
assert d.resume['step'] == 'copy_target'
act(s,d.player,type='choose',decision_id=d.id,option_ids=['p1'])
advance(s)
assert s.state.players['p1'].life == 36
assert s.state.players['p2'].life == 39
assert len([t for t in s.state.rules.delayed if t.name == 'Undying Flames']) == 1
''')
    else:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['p1'])
        advance(s)
        assert s.state.players['p1'].life == 36 and s.state.players['p2'].life == 39
        assert len([t for t in s.state.rules.delayed if t.name == 'Undying Flames']) == 1


def test_copy_of_original_epic_creates_its_own_perpetual_instance103(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    original = cast(s, 'Endless Swarm')
    wait_priority(s, 'p1')
    cast(s, 'Reverberate', targets=[original.id])
    advance(s)
    assert len([t for t in s.state.rules.delayed if t.name == 'Endless Swarm']) == 2
    assert len(s.state.rules.cast_limits) == 2
    before = sum(c.name == 'Snake' for c in s.state.cards.values())
    upkeep(s)
    assert sum(c.name == 'Snake' for c in s.state.cards.values()) - before == 2 * len(s.state.zones['p1:hand'])
    assert len([t for t in s.state.rules.delayed if t.name == 'Endless Swarm']) == 2


def test_fizzled_flames_does_not_make_epic103(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Undying Flames', targets=[target.id])
    act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'graveyard'})
    advance(s)
    assert not s.state.rules.cast_limits and not s.state.rules.delayed


def test_foreign_owned_original_leaves_game_epic_memory_remains103(cards, tmp_path):
    s = setup(cards, three=True)
    source = put(s, 'Endless Swarm', 'hand', 'p2')
    original_id = source.id
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    advance(s)
    assert len([t for t in s.state.rules.delayed if t.name == 'Endless Swarm']) == 1
    act(s, 'p2', type='concede')
    assert 'p2' in s.state.rules.conceded and s.state.cards[original_id].zone == 'p2:graveyard'
    cold(s, tmp_path, {}, '''
from tests.test_rules_epic103 import upkeep
before=sum(c.name == 'Snake' for c in s.state.cards.values())
upkeep(s, 4)
assert sum(c.name == 'Snake' for c in s.state.cards.values()) > before
assert len([t for t in s.state.rules.delayed if t.name == 'Endless Swarm']) == 1
assert len(s.state.rules.cast_limits) == 1
''')
