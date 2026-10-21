"""Moss-Pit Skeleton watches native counters only from its exact graveyard incarnation."""
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

NAME = 'Moss-Pit Skeleton'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_grave_counter_top65_cards.json').read_text())


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


def cast(s, name, pool, targets=(), *, pid='p1', resolve=True, **kwargs):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    wait_priority(s, pid)
    c = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=c.id, targets=list(targets), **kwargs)
    if resolve:
        resolve_only(s, c)
    return c


def setup(cards, *, dead=True, replacement=None, kicker=0):
    deck = [c['name'] for c in DATA]
    s = table(cards, deck, deck, deck)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Hill Giant', 'battlefield')
    mill = put(s, 'Millstone', 'battlefield')
    crypt = put(s, "Tormod's Crypt", 'battlefield')
    if replacement:
        put(s, replacement, 'battlefield')
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, NAME, {'B': 1, 'G': 1, 'C': 3 * kicker}, kicker=kicker)
    assert source.zone == 'p1:battlefield' and source.counters.get('+1/+1', 0) == 3 * kicker
    if dead:
        cast(s, 'Lightning Bolt', {'R': 1}, [source.id])
        assert source.zone == 'p1:graveyard'
    return s, source, bear, second, mill, crypt


def triggers(s, source):
    return [sid for sid, entry in s.state.rules.stack.items() if entry.source_card == source.id]


def choose(s, yes):
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'confirm'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes' if yes else 'no'])
    settle(s)


def top(s, source):
    assert source.zone == 'p1:library' and s.state.zones['p1:library'][0] == source.id
    roundtrip(s)


def activate(s, obj, pool, targets):
    wait_priority(s, 'p1')
    mana(s, **pool)
    a = next(a for a in chars(s, obj).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=obj.id, ability=a.index, targets=targets)


def test_actual_whole_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('kicker', [0, 1])
def test_paid_normal_and_kicked_entry_do_not_watch_from_battlefield(cards, kicker):
    s, source, _, _, _, _ = setup(cards, dead=False, kicker=kicker)
    assert source.zone == 'p1:battlefield' and source.counters.get('+1/+1', 0) == 3 * kicker
    assert chars(s, source).pt == ((5, 5) if kicker else (2, 2))
    assert not triggers(s, source)
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_native_paid_counter_offer_accept_or_decline(cards, accept):
    s, source, bear, _, _, _ = setup(cards)
    cast(s, 'Burst of Strength', {'G': 1}, [bear.id])
    assert bear.counters['+1/+1'] == 1 and len(triggers(s, source)) == 1
    choose(s, accept)
    if accept:
        top(s, source)
    else:
        assert source.zone == 'p1:graveyard'
        roundtrip(s)


def test_counter_replacement_amount_is_one_event(cards):
    s, source, bear, _, _, _ = setup(cards, replacement='Hardened Scales')
    cast(s, 'Burst of Strength', {'G': 1}, [bear.id])
    assert bear.counters['+1/+1'] == 2 and len(triggers(s, source)) == 1
    choose(s, True)
    top(s, source)


def test_two_creatures_in_one_packet_generate_two_optional_triggers(cards):
    s, source, bear, second, _, _ = setup(cards)
    cast(s, 'Travel Preparations', {'C': 1, 'G': 1}, [bear.id, second.id], target_counts=[2])
    assert bear.counters['+1/+1'] == second.counters['+1/+1'] == 1
    d = s.state.rules.decision
    if d is not None and d.kind == 'order':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
    assert len(triggers(s, source)) == 2
    choose(s, False)
    # choose() settles to the second native optional decision.
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes'])
    settle(s)
    top(s, source)


@pytest.mark.parametrize('kind', ['opponent', 'minus', 'prevented', 'zero'])
def test_native_negative_counter_events(cards, kind):
    s, source, bear, _, _, _ = setup(cards, replacement='Solemnity' if kind == 'prevented' else None)
    if kind == 'opponent':
        other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
        cast(s, 'Burst of Strength', {'G': 1}, [other.id])
        assert other.counters['+1/+1'] == 1
    elif kind == 'minus':
        cast(s, "Black Sun's Zenith", {'B': 2, 'C': 1}, x_value=1)
        assert bear.counters['-1/-1'] == 1
    elif kind == 'zero':
        serpent = cast(s, 'Stonecoil Serpent', {}, x_value=0)
        assert serpent.zone == 'p1:graveyard' and not serpent.counters
    else:
        cast(s, 'Burst of Strength', {'G': 1}, [bear.id])
        assert not bear.counters
    settle(s)
    assert source.zone == 'p1:graveyard' and not triggers(s, source) and s.state.rules.decision is None
    roundtrip(s)


def test_native_entry_counters_are_watched_from_existing_graveyard(cards):
    s, source, _, _, _, _ = setup(cards)
    serpent = cast(s, 'Stonecoil Serpent', {'C': 3}, x_value=3)
    assert serpent.counters['+1/+1'] == 3 and len(triggers(s, source)) == 1
    choose(s, True)
    top(s, source)


@pytest.mark.parametrize('exile', [False, True])
def test_only_existing_graveyard_source_watches(cards, exile):
    s, source, bear, _, _, crypt = setup(cards, dead=exile)
    if exile:
        activate(s, crypt, {}, ['p1'])
        settle(s)
        assert source.zone == 'p1:exile'
    cast(s, 'Burst of Strength', {'G': 1}, [bear.id])
    settle(s)
    assert not triggers(s, source) and s.state.rules.decision is None
    assert source.zone == ('p1:exile' if exile else 'p1:battlefield')
    roundtrip(s)


def test_source_exiled_before_resolution_rechecks_intervening_if(cards):
    s, source, bear, _, _, crypt = setup(cards)
    cast(s, 'Burst of Strength', {'G': 1}, [bear.id])
    assert len(triggers(s, source)) == 1
    activate(s, crypt, {}, ['p1'])
    settle(s)
    assert source.zone == 'p1:exile' and s.state.rules.decision is None
    roundtrip(s)


def test_leave_and_return_graveyard_old_uid_cannot_move_successor(cards):
    s, source, bear, _, mill, _ = setup(cards)
    old = s.state.rules.object_id(source.id)
    cast(s, 'Burst of Strength', {'G': 1}, [bear.id])
    cast(s, 'Reclaim', {'G': 1}, [source.id])
    top(s, source)
    activate(s, mill, {'C': 2}, ['p1'])
    settle(s)
    assert source.zone == 'p1:graveyard' and s.state.rules.object_id(source.id) != old
    # Current-zone condition can hold, but the exact native self_gy selector refuses a successor UID.
    if s.state.rules.decision is not None:
        choose(s, True)
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('offered', [False, True])
def test_true_cold_pending_trigger_or_optional_decision(cards, tmp_path, offered):
    import subprocess
    import sys

    s, source, bear, _, _, _ = setup(cards)
    cast(s, 'Burst of Strength', {'G': 1}, [bear.id])
    if offered:
        settle(s)
        assert s.state.rules.decision is not None
    saved = tmp_path / 'moss65.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_trigger_grave_counter_top65 import choose,top
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=s.state.cards[sys.argv[3]]
choose(s,True)
top(s,source)
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('foreign_owner', [False, True])
def test_counter_recipient_current_controller_not_owner(cards, foreign_owner):
    s, source, own, _, _, _ = setup(cards)
    recipient = put(s, 'Grizzly Bears', 'battlefield', 'p2') if foreign_owner else own
    act(s, 'p1', type='set_controller', card_ids=[recipient.id], player='p1' if foreign_owner else 'p2')
    cast(s, 'Burst of Strength', {'G': 1}, [recipient.id])
    assert recipient.counters['+1/+1'] == 1
    if foreign_owner:
        assert recipient.owner == 'p2' and recipient.controller == 'p1' and len(triggers(s, source)) == 1
        choose(s, True)
        top(s, source)
    else:
        settle(s)
        assert recipient.owner == 'p1' and recipient.controller == 'p2'
        assert source.zone == 'p1:graveyard' and not triggers(s, source) and s.state.rules.decision is None
        roundtrip(s)


def test_real_double_major_copy_of_paid_kicked_spell_keeps_kicker(cards):
    deck = [c['name'] for c in DATA]
    s = table(cards, deck, deck, deck)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    original = cast(s, NAME, {'B': 1, 'G': 1, 'C': 3}, kicker=1, resolve=False)
    cast(s, 'Double Major', {'G': 1, 'U': 1}, [original.id])
    settle(s)
    copies = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield'
              and chars(s, c).name == NAME]
    assert len(copies) == 1 and original.zone == 'p1:battlefield'
    assert original.counters.get('+1/+1') == copies[0].counters.get('+1/+1') == 3
    assert chars(s, original).pt == chars(s, copies[0]).pt == (5, 5)
    assert not triggers(s, original) and not triggers(s, copies[0])
    roundtrip(s)


def test_real_clone_of_kicked_battlefield_permanent_is_not_kicked(cards):
    s, source, _, _, _, _ = setup(cards, dead=False, kicker=1)
    clone = cast(s, 'Clone', {'C': 3, 'U': 1}, resolve=False)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and any(o.id == source.id for o in d.options)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[source.id])
    settle(s)
    assert clone.zone == 'p1:battlefield' and chars(s, clone).name == NAME
    assert source.counters['+1/+1'] == 3 and not clone.counters
    assert chars(s, clone).pt == (2, 2)
    roundtrip(s)
