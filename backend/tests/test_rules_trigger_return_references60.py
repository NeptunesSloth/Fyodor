"""Native return costs and owner-based hand events preserve original objects."""
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

DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_return_references60_cards.json').read_text())
NAMES = ['Slab Hammer', 'Azorius Aethermage']


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
    deck = [*NAMES, 'Grizzly Bears', 'Colossal Dreadmaw', 'Forest', 'Island', 'Leonin Shikari',
            'Raise the Alarm', 'Unsummon', 'Boomerang', 'Disenchant', "Nature's Spiral", 'Cloudshift', 'Evacuation']
    s = table(cards, deck, deck, deck)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s, bear


def cast(s, name, pool, targets=(), *, pid='p1', resolve=True):
    wait_priority(s, pid)
    c = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=c.id, targets=list(targets))
    if resolve:
        settle(s)
    return c


def answer(s, *, pay=True, land=None):
    for _ in range(5):
        settle(s)
        d = s.state.rules.decision
        if d is None or d.kind in ('declare_attackers', 'declare_blockers'):
            return
        ids = {o.id for o in d.options}
        chosen = ['pay' if pay else 'decline'] if 'decline' in ids else [land] if land in ids else [d.options[0].id]
        act(s, d.player, type='choose', decision_id=d.id, option_ids=chosen)
    raise AssertionError('payment failed to finish')


def hammer_pending(cards):
    s, bear = setup(cards)
    land = put(s, 'Forest', 'battlefield')
    source = cast(s, 'Slab Hammer', {'C': 2})
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[bear.id])
    settle(s)
    assert source.attached_to == bear.id
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (bear, 'p2'))
    return s, source, bear, land


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('pay', [False, True])
def test_paid_equip_actual_attack_return_land_cost(cards, pay):
    s, source, bear, land = hammer_pending(cards)
    answer(s, pay=pay, land=land.id)
    assert land.zone == ('p1:hand' if pay else 'p1:battlefield')
    assert chars(s, bear).pt == ((4, 4) if pay else (2, 2))
    assert source.attached_to == bear.id
    roundtrip(s)


def test_hammer_departed_equipment_still_buffs_original_attacker(cards):
    s, source, bear, land = hammer_pending(cards)
    cast(s, 'Disenchant', {'C': 1, 'W': 1}, [source.id])
    assert source.zone == 'p1:graveyard'
    answer(s, land=land.id)
    assert chars(s, bear).pt == (4, 4) and land.zone == 'p1:hand'
    roundtrip(s)


def test_hammer_native_instant_equip_does_not_move_bonus_to_new_host(cards):
    s, source, bear, land = hammer_pending(cards)
    put(s, 'Leonin Shikari', 'battlefield')
    other = put(s, 'Colossal Dreadmaw', 'battlefield')
    wait_priority(s, 'p1')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[other.id])
    settle(s)
    assert source.attached_to == other.id
    answer(s, land=land.id)
    assert chars(s, bear).pt == (4, 4) and chars(s, other).pt == (6, 6)
    roundtrip(s)


def test_hammer_original_attacker_blink_successor_is_not_pumped(cards):
    s, _, bear, land = hammer_pending(cards)
    old = s.state.rules.object_id(bear.id)
    cast(s, 'Cloudshift', {'W': 1}, [bear.id])
    assert bear.zone == 'p1:battlefield' and s.state.rules.object_id(bear.id) != old
    answer(s, land=land.id)
    assert land.zone == 'p1:hand' and chars(s, bear).pt == (2, 2)
    roundtrip(s)


def test_hammer_can_pay_with_a_controlled_land_owned_by_opponent(cards):
    s, _, bear, land = hammer_pending(cards)
    act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'hand'})
    foreign = put(s, 'Island', 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[foreign.id], player='p1')
    answer(s, land=foreign.id)
    assert foreign.zone == 'p2:hand' and chars(s, bear).pt == (4, 4)
    roundtrip(s)


def test_hammer_cannot_pay_after_its_only_land_is_gone(cards):
    s, _, bear, land = hammer_pending(cards)
    act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'hand'})
    settle(s)
    d = s.state.rules.decision
    if d is not None and d.kind not in ('declare_attackers', 'declare_blockers'):
        assert 'pay' not in {o.id for o in d.options}
        answer(s, pay=False)
    assert chars(s, bear).pt == (2, 2)
    roundtrip(s)


def mage_setup(cards):
    s, bear = setup(cards)
    source = cast(s, 'Azorius Aethermage', {'C': 1, 'W': 1, 'U': 1})
    return s, source, bear


@pytest.mark.parametrize('pay', [False, True])
@pytest.mark.parametrize('self_return', [False, True])
def test_mage_permanent_or_self_return_to_own_hand(cards, pay, self_return):
    s, source, bear = mage_setup(cards)
    target = source if self_return else bear
    mana(s, C=1)
    cast(s, 'Unsummon', {'U': 1}, [target.id], resolve=False)
    before = len(s.state.zones['p1:library'])
    settle(s)
    assert target.zone == 'p1:hand'
    answer(s, pay=pay)
    assert len(s.state.zones['p1:library']) == before - int(pay)
    roundtrip(s)


@pytest.mark.parametrize('owner', ['p1', 'p2'])
def test_mage_hand_owner_and_trigger_controller_are_independent_of_permanent_controller(cards, owner):
    s, source, bear = mage_setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    target = bear if owner == 'p1' else put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[target.id], player='p1')
    mana(s, pid='p2', C=1)
    cast(s, 'Unsummon', {'U': 1}, [target.id], resolve=False)
    before = len(s.state.zones['p2:library'])
    settle(s)
    assert target.zone == owner + ':hand'
    if owner == 'p2':
        assert s.state.rules.decision.player == 'p2'
        answer(s)
    else:
        assert s.state.rules.decision is None
    assert len(s.state.zones['p2:library']) == before - int(owner == 'p2')
    roundtrip(s)


def test_mage_graveyard_to_hand_does_not_trigger(cards):
    s, _, bear = mage_setup(cards)
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'graveyard'})
    cast(s, "Nature's Spiral", {'C': 1, 'G': 1}, [bear.id], resolve=False)
    before = len(s.state.zones['p1:library'])
    settle(s)
    assert bear.zone == 'p1:hand' and s.state.rules.decision is None
    assert len(s.state.zones['p1:library']) == before
    roundtrip(s)


def test_foreign_owned_mage_does_not_trigger_when_it_returns_to_owners_hand(cards):
    s, source, _ = mage_setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    cast(s, 'Unsummon', {'U': 1}, [source.id])
    assert source.zone == 'p1:hand' and s.state.rules.decision is None
    roundtrip(s)


def test_mage_token_return_triggers_before_token_ceases(cards):
    s, _, _ = mage_setup(cards)
    cast(s, 'Raise the Alarm', {'C': 1, 'W': 1})
    token = next(c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield')
    mana(s, C=1)
    cast(s, 'Unsummon', {'U': 1}, [token.id], resolve=False)
    before = len(s.state.zones['p1:library'])
    settle(s)
    answer(s)
    assert len(s.state.zones['p1:library']) == before - 1
    assert token.id not in s.state.cards or s.state.cards[token.id].zone != 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('permanent', ['Forest', 'Slab Hammer'])
def test_mage_also_observes_land_and_artifact_return(cards, permanent):
    s, _, _ = mage_setup(cards)
    target = put(s, permanent, 'battlefield')
    mana(s, C=1)
    cast(s, 'Boomerang', {'U': 2}, [target.id], resolve=False)
    before = len(s.state.zones['p1:library'])
    settle(s)
    answer(s)
    assert target.zone == 'p1:hand' and len(s.state.zones['p1:library']) == before - 1
    roundtrip(s)


def test_mage_simultaneous_source_and_other_return_each_offer_separate_payment(cards):
    s, source, bear = mage_setup(cards)
    mana(s, C=2)
    cast(s, 'Evacuation', {'C': 3, 'U': 2}, resolve=False)
    before = len(s.state.zones['p1:library'])
    settle(s)
    answer(s)
    assert source.zone == bear.zone == 'p1:hand'
    assert len(s.state.zones['p1:library']) == before - 2
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_return_payment_and_original_reference(cards, tmp_path, name):
    import subprocess
    import sys

    if name == 'Slab Hammer':
        s, _, target, land = hammer_pending(cards)
        settle(s)
        resource = land.id
    else:
        s, _, target = mage_setup(cards)
        mana(s, C=1)
        cast(s, 'Unsummon', {'U': 1}, [target.id])
        resource = ''
    assert s.state.rules.decision is not None
    saved = tmp_path / 'return60.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_trigger_return_references60 import answer
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
before=len(s.state.zones['p1:library'])
assert s.state.rules.decision
answer(s,land=sys.argv[5] or None)
if sys.argv[4]=='Slab Hammer':
 assert chars(s,s.state.cards[sys.argv[3]]).pt==(4,4)
 assert s.state.cards[sys.argv[5]].zone=='p1:hand'
else: assert len(s.state.zones['p1:library'])==before-1
roundtrip(s)
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id, name, resource],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
