"""Native self-replacement branches freeze one verdict before either action."""
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

DATA = json.loads((Path(__file__).parent / 'fixtures/conditional_instead59_cards.json').read_text())
NAMES = ['Dark Temper', 'Will of the All-Hunter', 'Everflame Eidolon']


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


def setup(cards):
    deck = [*NAMES, 'Colossal Dreadmaw', 'Black Knight', 'Lightning Bolt', 'Grizzly Bears', 'Darksteel Myr', 'Disenchant']
    s = table(cards, deck, deck, deck)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s


def cast(s, name, pool, targets=(), *, pid='p1', resolve=True, **kwargs):
    wait_priority(s, pid)
    c = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=c.id, targets=list(targets), **kwargs)
    if resolve:
        settle(s)
    return c


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonicals(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('black', [False, True])
def test_dark_temper_self_replacement_is_destroy_or_damage(cards, black):
    s = setup(cards)
    target = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
    if black:
        put(s, 'Black Knight', 'battlefield')
    cast(s, 'Dark Temper', {'C': 2, 'R': 1}, [target.id])
    assert target.zone == ('p2:graveyard' if black else 'p2:battlefield')
    assert target.damage == (0 if black else 2)
    roundtrip(s)


def test_dark_temper_uses_resolution_color_after_response(cards):
    s = setup(cards)
    target = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
    black = put(s, 'Black Knight', 'battlefield')
    cast(s, 'Dark Temper', {'C': 2, 'R': 1}, [target.id], resolve=False)
    cast(s, 'Lightning Bolt', {'R': 1}, [black.id])
    assert black.zone == 'p1:graveyard'
    assert target.zone == 'p2:battlefield' and target.damage == 2
    roundtrip(s)


def test_dark_temper_destructible_branch_does_not_damage_indestructible(cards):
    s = setup(cards)
    put(s, 'Black Knight', 'battlefield')
    target = put(s, 'Darksteel Myr', 'battlefield', 'p2')
    cast(s, 'Dark Temper', {'C': 2, 'R': 1}, [target.id])
    assert target.zone == 'p2:battlefield' and target.damage == 0
    roundtrip(s)


@pytest.mark.parametrize('blocking', [False, True])
def test_will_uses_native_blocking_state_and_counters_instead_of_pump(cards, blocking):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield')
    if blocking:
        from tests.test_rules_wave30m_durations import to_phase
        from tests.test_rules_wave30p_combat import attack
        attacker = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
        to_phase(s, 'declare_attackers', turn=5)
        attack(s, (attacker, 'p1'), pid='p2')
        to_phase(s, 'declare_blockers', turn=5)
        act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': target.id, 'attacker_id': attacker.id}])
    cast(s, 'Will of the All-Hunter', {'C': 1, 'W': 1}, [target.id])
    assert target.counters.get('+1/+1', 0) == (2 if blocking else 0)
    assert chars(s, target).pt == (4, 4)
    roundtrip(s)


def eidolon(s, *, bestowed):
    host = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Everflame Eidolon', 'hand')
    mana(s, C=2 if bestowed else 1, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id,
        targets=[host.id] if bestowed else [], **({'alt_cost': f'{source.id}:0'} if bestowed else {}))
    settle(s)
    return source, host


def activate(s, source, *, resolve=True):
    wait_priority(s, 'p1')
    mana(s, R=1)
    ability = next(a for a in chars(s, source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index)
    if resolve:
        settle(s)


@pytest.mark.parametrize('bestowed', [False, True])
def test_eidolon_paid_normal_or_bestow_activations_buff_only_correct_object(cards, bestowed):
    s = setup(cards)
    source, host = eidolon(s, bestowed=bestowed)
    activate(s, source)
    assert chars(s, host).pt == ((4, 3) if bestowed else (2, 2))
    if not bestowed:
        assert chars(s, source).pt == (2, 1)
    assert ('Aura' in chars(s, source).subtypes) == bestowed
    roundtrip(s)


def test_eidolon_resolves_after_detach_as_creature(cards):
    s = setup(cards)
    source, host = eidolon(s, bestowed=True)
    activate(s, source, resolve=False)
    cast(s, 'Lightning Bolt', {'R': 1}, [host.id])
    assert host.zone == 'p1:graveyard'
    assert chars(s, source).is_creature and chars(s, source).pt == (2, 1)
    roundtrip(s)


def test_paid_will_cycling_discards_and_draws(cards):
    s = setup(cards)
    source = put(s, 'Will of the All-Hunter', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2)
    ability = next(a for a in chars(s, source).abilities if 'Cycling' in a.text)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index)
    assert source.zone == 'p1:graveyard'
    settle(s)
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


def test_illegal_bestow_target_resolves_as_creature_then_can_activate(cards):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Everflame Eidolon', 'hand')
    mana(s, C=2, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[host.id], alt_cost=f'{source.id}:0')
    cast(s, 'Lightning Bolt', {'R': 1}, [host.id])
    assert host.zone == 'p1:graveyard'
    assert chars(s, source).is_creature and source.attached_to is None
    activate(s, source)
    assert chars(s, source).pt == (2, 1)
    roundtrip(s)


def test_departed_aura_uses_lki_host_for_pending_native_activation(cards):
    s = setup(cards)
    source, host = eidolon(s, bestowed=True)
    activate(s, source, resolve=False)
    cast(s, 'Disenchant', {'C': 1, 'W': 1}, [source.id])
    assert source.zone == 'p1:graveyard'
    assert chars(s, host).pt == (3, 2)
    roundtrip(s)


def test_resolved_host_bonus_never_moves_to_detached_eidolon(cards):
    s = setup(cards)
    source, host = eidolon(s, bestowed=True)
    activate(s, source)
    assert chars(s, host).pt == (4, 3)
    cast(s, 'Lightning Bolt', {'R': 1}, [host.id])
    assert host.zone == 'p1:graveyard'
    assert chars(s, source).pt == (1, 1)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Dark Temper', 'Everflame Eidolon', 'Will of the All-Hunter'])
def test_true_cold_pending_branch(cards, tmp_path, name):
    import subprocess
    import sys

    s = setup(cards)
    if name == 'Dark Temper':
        target = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
        put(s, 'Black Knight', 'battlefield')
        cast(s, name, {'C': 2, 'R': 1}, [target.id], resolve=False)
    elif name == 'Everflame Eidolon':
        source, target = eidolon(s, bestowed=True)
        activate(s, source, resolve=False)
    else:
        from tests.test_rules_wave30m_durations import to_phase
        from tests.test_rules_wave30p_combat import attack
        target = put(s, 'Grizzly Bears', 'battlefield')
        attacker = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
        to_phase(s, 'declare_attackers', turn=5)
        attack(s, (attacker, 'p1'), pid='p2')
        to_phase(s, 'declare_blockers', turn=5)
        act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': target.id, 'attacker_id': attacker.id}])
        cast(s, name, {'C': 1, 'W': 1}, [target.id], resolve=False)
    saved = tmp_path / 'instead59.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack']
settle(s)
c=s.state.cards[sys.argv[3]]
if sys.argv[4]=='Dark Temper': assert c.zone=='p2:graveyard'
elif sys.argv[4]=='Everflame Eidolon': assert chars(s,c).pt==(4,3)
else: assert c.counters.get('+1/+1')==2 and chars(s,c).pt==(4,4)
roundtrip(s)
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id, name],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
