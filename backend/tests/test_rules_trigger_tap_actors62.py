"""Instruction actors, individual untapped transitions, and printed tap follow-ons."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_tap_actors62_cards.json').read_text())
NAMES = ['Solitary Sanctuary', 'Icewrought Sentry']


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


def setup(cards, name, *, paid=False):
    deck = [*NAMES, 'Grizzly Bears', 'Frost Lynx', 'Frost Breath', 'Icy Manipulator', 'Llanowar Elves', 'Cloudshift', 'Rhystic Deluge']
    s = table(cards, deck, deck, deck)
    own = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, name, 'hand' if paid else 'battlefield')
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    return s, source, own, victim


def resolve(s, own, victim):
    for _ in range(15):
        settle(s)
        d = s.state.rules.decision
        if d is None or d.kind in ('declare_attackers', 'declare_blockers'):
            return
        ids = {o.id for o in d.options}
        picks = ['pay'] if 'pay' in ids else [victim.id] if victim.id in ids else [own.id] if own.id in ids else [d.options[0].id]
        act(s, d.player, type='choose', decision_id=d.id, option_ids=picks)
    raise AssertionError('native tap trigger did not finish')


def cast(s, name, pool, targets=(), *, pid='p1', **kwargs):
    wait_priority(s, pid)
    source = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), **kwargs)
    return source


def check(s, name, source, own, n):
    if name == 'Solitary Sanctuary':
        assert own.counters.get('+1/+1', 0) == n
    else:
        assert chars(s, source).pt == (2 + 2 * n, 3 + n)
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', NAMES)
def test_real_paid_tap_effect_and_already_tapped_repeat(cards, name):
    s, source, own, victim = setup(cards, name)
    cast(s, 'Frost Lynx', {'C': 2, 'U': 1})
    resolve(s, own, victim)
    assert victim.tapped
    check(s, name, source, own, 1)
    cast(s, 'Frost Lynx', {'C': 2, 'U': 1})
    resolve(s, own, victim)
    check(s, name, source, own, 1)


@pytest.mark.parametrize('name', NAMES)
def test_one_batch_two_opponents_means_two_singular_triggers(cards, name):
    s, source, own, victim = setup(cards, name)
    other = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    cast(s, 'Frost Breath', {'C': 2, 'U': 1}, [victim.id, other.id], target_counts=[2])
    resolve(s, own, victim)
    assert victim.tapped and other.tapped
    check(s, name, source, own, 2)


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('actor', ['p1', 'p3'])
def test_paid_tap_ability_uses_effect_controller_independently_of_owner(cards, name, actor):
    s, source, own, victim = setup(cards, name)
    icy = cast(s, 'Icy Manipulator', {'C': 4})
    settle(s)
    if actor != 'p1':
        act(s, 'p1', type='set_controller', card_ids=[icy.id], player=actor)
    wait_priority(s, actor)
    mana(s, pid=actor, C=1)
    ability = next(a for a in chars(s, icy).abilities if a.kind == 'activated')
    act(s, actor, type='activate_ability', card_id=icy.id, ability=ability.index, targets=[victim.id])
    resolve(s, own, victim)
    assert victim.tapped and icy.tapped
    check(s, name, source, own, int(actor == 'p1'))


@pytest.mark.parametrize('name', NAMES)
def test_victim_current_controller_matters_rather_than_owner(cards, name):
    s, source, own, _ = setup(cards, name)
    victim = put(s, 'Llanowar Elves', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[victim.id], player='p2')
    cast(s, 'Frost Lynx', {'C': 2, 'U': 1})
    resolve(s, own, victim)
    check(s, name, source, own, 1)


@pytest.mark.parametrize('name', NAMES)
def test_your_effect_tapping_your_own_creature_does_not_count(cards, name):
    s, source, own, _ = setup(cards, name)
    icy = cast(s, 'Icy Manipulator', {'C': 4})
    settle(s)
    wait_priority(s, 'p1')
    mana(s, C=1)
    ability = next(a for a in chars(s, icy).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=icy.id, ability=ability.index, targets=[own.id])
    resolve(s, own, own)
    assert own.tapped
    check(s, name, source, own, 0)


def test_pending_sentry_bonus_does_not_reach_a_blink_successor(cards):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    name = 'Icewrought Sentry'
    s, source, own, victim = setup(cards, name)
    lynx = cast(s, 'Frost Lynx', {'C': 2, 'U': 1})
    resolve_only(s, lynx)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[victim.id])
    trigger_id = next(sid for sid, entry in s.state.rules.stack.items() if entry.source_card == lynx.id)
    for _ in range(12):
        if trigger_id not in s.state.rules.stack:
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    assert trigger_id not in s.state.rules.stack
    assert any(entry.source_card == source.id for entry in s.state.rules.stack.values())
    assert victim.tapped and s.state.zones['stack']
    old = s.state.rules.object_id(source.id)
    cast(s, 'Cloudshift', {'W': 1}, [source.id])
    resolve(s, own, victim)
    assert source.zone == 'p1:battlefield' and s.state.rules.object_id(source.id) != old
    check(s, name, source, own, 0)


@pytest.mark.parametrize('name', NAMES)
def test_real_opponent_tap_mana_ability_does_not_count(cards, name):
    s, source, own, _ = setup(cards, name)
    elf = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=8)
    wait_priority(s, 'p2')
    from app.rules import casting
    index = next(i for i, _ in casting.mana_abilities(s.state, elf, cards))
    act(s, 'p2', type='activate_ability', card_id=elf.id, ability=index)
    resolve(s, own, elf)
    assert elf.tapped
    check(s, name, source, own, 0)


@pytest.mark.parametrize('name', NAMES)
def test_opponent_mana_tap_during_your_resolving_rhystic_payment_does_not_count(cards, name):
    from app.rules import casting

    s, source, own, victim = setup(cards, name)
    elf = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    deluge = put(s, 'Rhystic Deluge', 'battlefield')
    to_phase(s, 'main1', turn=7)
    wait_priority(s, 'p1')
    mana(s, U=1)
    ability = next(a for a in chars(s, deluge).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=deluge.id, ability=ability.index, targets=[victim.id])
    settle(s)
    assert s.state.rules.decision is not None and s.state.rules.decision.player == 'p2'
    index = next(i for i, _ in casting.mana_abilities(s.state, elf, cards))
    act(s, 'p2', type='activate_ability', card_id=elf.id, ability=index)
    assert elf.tapped
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
    resolve(s, own, victim)
    assert not victim.tapped
    check(s, name, source, own, 0)


@pytest.mark.parametrize('name', NAMES)
def test_declaring_opponent_attacker_is_not_your_tap_instruction(cards, name):
    s, source, own, victim = setup(cards, name)
    to_phase(s, 'declare_attackers', turn=5)
    attack(s, (victim, 'p1'), pid='p2')
    resolve(s, own, victim)
    assert victim.tapped
    check(s, name, source, own, 0)


def test_whole_sanctuary_paid_etb_tap_stun_and_counter_followon(cards):
    name = 'Solitary Sanctuary'
    s, source, own, victim = setup(cards, name, paid=True)
    source = cast(s, name, {'C': 2, 'W': 1})
    resolve(s, own, victim)
    assert source.zone == 'p1:battlefield' and victim.tapped and victim.counters.get('stun') == 1
    check(s, name, source, own, 1)


def test_whole_sanctuary_paid_etb_already_tapped_still_gets_stun_without_followon(cards):
    name = 'Solitary Sanctuary'
    s, _, own, victim = setup(cards, name, paid=True)
    act(s, 'p2', type='tap', card_ids=[victim.id], tapped=True)
    source = cast(s, name, {'C': 2, 'W': 1})
    resolve(s, own, victim)
    assert source.zone == 'p1:battlefield' and victim.tapped and victim.counters.get('stun') == 1
    check(s, name, source, own, 0)


def test_whole_sentry_paid_cast_vigilance_attack_paid_reflexive_tap(cards):
    name = 'Icewrought Sentry'
    s, source, own, victim = setup(cards, name, paid=True)
    source = cast(s, name, {'C': 2, 'U': 1})
    settle(s)
    to_phase(s, 'declare_attackers', turn=7)
    attack(s, (source, 'p2'))
    mana(s, C=1, U=1)
    resolve(s, own, victim)
    assert not source.tapped and victim.tapped
    check(s, name, source, own, 1)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_native_tap_followon(cards, tmp_path, name):
    import subprocess
    import sys

    s, source, own, victim = setup(cards, name)
    cast(s, 'Frost Lynx', {'C': 2, 'U': 1})
    saved = tmp_path / 'tap62.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_trigger_tap_actors62 import resolve,check
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source,own,victim=[s.state.cards[x] for x in sys.argv[3:6]]
assert s.state.zones['stack']
resolve(s,own,victim)
assert victim.tapped
check(s,sys.argv[6],source,own,1)
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, own.id, victim.id, name],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
