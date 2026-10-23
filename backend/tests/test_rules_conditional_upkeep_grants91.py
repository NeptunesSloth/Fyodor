"""Conditional upkeep grants preserve native payments and original-source semantics."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/upkeep91_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest', 'Island']


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


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)



@pytest.mark.parametrize('name', ['Musician', 'Essence Leak'])
def test_whole(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def hold(s):
    for pid in s.state.players:
        act(s, pid, type='set_prefs', hold_priority=True)


def cast(s, name, targets=(), pid='p1', mana=None, **kwargs):
    source = put(s, name, 'hand', pid=pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana=mana or {'C': 5, 'U': 2, 'B': 2, 'R': 1, 'G': 2})
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[], **kwargs)
    settle(s)
    return source


def music_setup(cards, count=1, target_name='Grizzly Bears'):
    s = game(cards)
    source = put(s, 'Musician', 'battlefield')
    target = put(s, target_name, 'battlefield')
    cast(s, 'Expedite', [source.id], mana={'R': 1})
    for n in range(count):
        if n:
            cast(s, 'Dramatic Reversal', mana={'C': 1, 'U': 1})
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id], sources=[])
        settle(s)
    cast(s, 'Unsummon', [source.id], mana={'U': 1})
    return s, source, target


def upkeep(s, turn=4):
    hold(s)
    to_phase(s, 'upkeep', turn)
    assert s.state.zones.get('stack')


@pytest.mark.parametrize('pay', [False, True])
def test_music_two_counters_one_persistent_grant_and_actual_upkeep_cost(cards, pay):
    from app.rules.plan import Plan

    s, granter, target = music_setup(cards, count=2)
    assert s.state.cards[target.id].counters['music'] == 2
    assert s.state.cards[granter.id].zone == 'p1:hand'
    ch = Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[target.id])
    assert len([a for a in ch.abilities if 'music counter' in a.text]) == 1
    upkeep(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay' if pay else 'decline'])
    assert s.state.cards[target.id].zone == ('p1:battlefield' if pay else 'p1:graveyard')
    assert s.state.rules.decision is None
    assert s.state.players['p1'].mana == ({} if pay else {'C': 2})
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_essence_actual_conditional_host_grant_and_native_printed_cost(cards, pay):
    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', 2)
    aura = cast(s, 'Essence Leak', [target.id], pid='p2', mana={'U': 1})
    assert s.state.cards[aura.id].attached_to == target.id
    upkeep(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay' if pay else 'sacrifice'])
    assert s.state.cards[target.id].zone == ('p1:battlefield' if pay else 'p1:graveyard')
    assert s.state.players['p1'].mana == ({} if pay else {'C': 1, 'G': 1})
    roundtrip(s)


def essence_setup(cards):
    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', 2)
    aura = cast(s, 'Essence Leak', [target.id], pid='p2', mana={'U': 1})
    return s, aura, target


def resolve_one(s, cid):
    for _ in range(60):
        if s.state.cards[cid].zone != 'stack':
            return
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('Native spell did not resolve')


def respond(s, name, targets, pid, mana, **kwargs):
    source = put(s, name, 'hand', pid=pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana=mana)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[], **kwargs)
    resolve_one(s, source.id)
    return source


@pytest.mark.parametrize('kind', ['music', 'essence'])
@pytest.mark.parametrize('pay', [False, True])
def test_actual_dominate_after_trigger_keeps_original_payer_and_correct_outcome(cards, kind, pay):
    s, _, target = music_setup(cards, count=2) if kind == 'music' else essence_setup(cards)
    upkeep(s)
    respond(s, 'Dominate', [target.id], 'p2', {'C': 3, 'U': 2}, x_value=2)
    assert s.state.cards[target.id].controller == 'p2'
    owed = {'C': 2} if kind == 'music' else {'C': 1, 'G': 1}
    act(s, 'p1', type='add_mana', player='p1', mana=owed)
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay' if pay else ('decline' if kind == 'music' else 'sacrifice')])
    if kind == 'music' and not pay:
        assert s.state.cards[target.id].zone == 'p1:graveyard'
    else:
        assert s.state.cards[target.id].zone == 'p2:battlefield'
    assert s.state.players['p1'].mana == ({} if pay else owed)
    roundtrip(s)


def test_music_departure_uses_original_music_counter_lki_and_no_new_hand_object_destroy(cards):
    s, _, target = music_setup(cards, count=2)
    upkeep(s)
    respond(s, 'Unsummon', [target.id], 'p2', {'U': 1})
    assert s.state.cards[target.id].zone == 'p1:hand' and not s.state.cards[target.id].counters
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay'])
    assert s.state.players['p1'].mana == {}
    assert s.state.cards[target.id].zone == 'p1:hand'
    roundtrip(s)


def test_essence_copied_host_departure_pays_original_lki_cost_not_new_clone_hand_cost(cards):
    from app.rules.plan import Plan

    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    clone = cast(s, 'Clone', mana={'C': 3, 'U': 1})
    choose(s, [bear.id])
    assert Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[clone.id]).mana_cost == '{1}{G}'
    to_phase(s, 'main1', 2)
    cast(s, 'Essence Leak', [clone.id], pid='p2', mana={'U': 1})
    upkeep(s)
    respond(s, 'Unsummon', [clone.id], 'p2', {'U': 1})
    assert Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[clone.id]).mana_cost == '{3}{U}'
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay'])
    assert s.state.players['p1'].mana == {}
    assert s.state.cards[clone.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_musician_own_cumulative_upkeep_actual_control_change_original_payment(cards, pay):
    s = game(cards)
    source = put(s, 'Musician', 'battlefield')
    upkeep(s)
    respond(s, 'Dominate', [source.id], 'p2', {'C': 4, 'U': 2}, x_value=3)
    assert s.state.cards[source.id].controller == 'p2'
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    settle(s)
    assert s.state.cards[source.id].counters['age'] == 1
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    choose(s, ['pay' if pay else 'sacrifice'])
    assert s.state.cards[source.id].zone == 'p2:battlefield'
    assert s.state.players['p1'].mana == ({} if pay else {'C': 1})
    roundtrip(s)


def test_musician_cumulative_offer_pay_survives_native_mana_sacrifice_of_source(cards):
    s = game(cards)
    source = put(s, 'Musician', 'battlefield')
    altar = put(s, 'Phyrexian Altar', 'battlefield')
    upkeep(s)
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0, mana_choice='R', sources=[],
        cost_choices=[{'component': 0, 'cards': [source.id]}])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    choose(s, ['pay'])
    assert s.state.players['p1'].mana == {}
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def music_abilities(s, target):
    from app.rules.plan import Plan

    return [a for a in Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[target.id]).abilities if 'music counter' in a.text]


def essence_abilities(s, target):
    from app.rules.plan import Plan

    return [a for a in Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[target.id]).abilities if 'unless you pay its mana cost' in a.text]


def test_actual_fate_transfer_counters_alone_do_not_grant_and_original_zero_cost(cards):
    s, _, target = music_setup(cards, count=2)
    recipient = put(s, 'Llanowar Elves', 'battlefield')
    upkeep(s)
    respond(s, 'Fate Transfer', [target.id, recipient.id], 'p2', {'C': 1, 'U': 1}, target_counts=[1, 1])
    assert not s.state.cards[target.id].counters
    assert s.state.cards[recipient.id].counters['music'] == 2
    assert len(music_abilities(s, target)) == 1 and not music_abilities(s, recipient)
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay'])
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_essence_native_color_layers_and_actual_sleight_text_change(cards):
    s, aura, target = essence_setup(cards)
    assert len(essence_abilities(s, target)) == 1
    cast(s, 'Sleight of Mind', [aura.id], pid='p2', mana={'U': 1})
    choose(s, ['green'])
    choose(s, ['blue'])
    assert not essence_abilities(s, target)
    cast(s, 'Cerulean Wisps', [target.id], pid='p2', mana={'U': 1})
    assert len(essence_abilities(s, target)) == 1
    roundtrip(s)


def test_essence_color_change_removes_grant_aura_departure_removes_restored_grant(cards):
    s, aura, target = essence_setup(cards)
    cast(s, 'Deathlace', [target.id], pid='p2', mana={'B': 1})
    assert not essence_abilities(s, target)
    cast(s, 'Chaoslace', [target.id], pid='p2', mana={'R': 1})
    assert len(essence_abilities(s, target)) == 1
    cast(s, 'Naturalize', [aura.id], pid='p2', mana={'C': 1, 'G': 1})
    assert not essence_abilities(s, target)
    roundtrip(s)


def test_essence_lost_conditional_grant_does_not_remove_already_stacked_trigger(cards):
    s, _, target = essence_setup(cards)
    upkeep(s)
    respond(s, 'Deathlace', [target.id], 'p2', {'B': 1})
    assert not essence_abilities(s, target)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay'])
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].mana == {}
    roundtrip(s)


def test_music_destroys_indestructible_unsuccessfully_essence_sacrifices_it(cards):
    s, _, target = music_setup(cards, target_name='Darksteel Myr')
    upkeep(s)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.rules.decision is None
    roundtrip(s)
    t = game(cards)
    myr = put(t, 'Darksteel Myr', 'battlefield')
    cast(t, 'Chaoslace', [myr.id], mana={'R': 1})
    cast(t, 'Essence Leak', [myr.id], mana={'U': 1})
    upkeep(t)
    settle(t)
    assert t.state.cards[myr.id].zone == 'p1:graveyard'
    roundtrip(t)


def test_essence_natural_green_land_no_mana_cost_is_unpayable(cards):
    s = game(cards)
    target = put(s, 'Dryad Arbor', 'battlefield')
    cast(s, 'Essence Leak', [target.id], mana={'U': 1})
    assert essence_abilities(s, target)
    upkeep(s)
    settle(s)
    assert s.state.rules.decision is None and s.state.cards[target.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_essence_pure_printed_x_is_payable_zero_not_missing_mana_cost(cards):
    s = game(cards)
    target = cast(s, 'Endless One', mana={'C': 2}, x_value=2)
    cast(s, "Painter's Servant", mana={'C': 2})
    choose(s, ['Green'])
    cast(s, 'Essence Leak', [target.id], mana={'U': 1})
    upkeep(s)
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay'])
    assert s.state.cards[target.id].zone == 'p1:battlefield' and s.state.players['p1'].mana == {}
    roundtrip(s)


@pytest.mark.parametrize('has_x', [False, True])
def test_essence_preserves_real_original_cost_x_for_rosheen_restricted_mana(cards, has_x):
    s = game(cards)
    target = put(s, 'Riptide Replicator' if has_x else 'Hedron Archive', 'battlefield')
    rosheen = put(s, 'Rosheen Meanderer', 'battlefield')
    cast(s, "Painter's Servant", mana={'C': 2})
    choose(s, ['Green'])
    cast(s, 'Essence Leak', [target.id], mana={'U': 1})
    upkeep(s)
    settle(s)
    if has_x:
        assert s.state.rules.decision.player == 'p1'
        act(s, 'p1', type='activate_ability', card_id=rosheen.id, ability=0, sources=[])
        choose(s, ['pay'])
        assert s.state.cards[target.id].zone == 'p1:battlefield'
        assert s.state.players['p1'].mana == {}
    else:
        assert s.state.rules.decision is None
        assert s.state.cards[target.id].zone == 'p1:graveyard'
        assert not s.state.cards[rosheen.id].tapped
    roundtrip(s)


def test_cumulative_source_departed_before_resolution_does_not_offer_payment(cards):
    s = game(cards)
    source = put(s, 'Musician', 'battlefield')
    upkeep(s)
    respond(s, 'Unsummon', [source.id], 'p2', {'U': 1})
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert not s.state.cards[source.id].counters
    assert s.state.players['p1'].mana == {'C': 1}
    roundtrip(s)


@pytest.mark.parametrize('kind', ['music', 'copied_lki', 'rosheen'])
def test_true_cold_native_upkeep_payment(cards, tmp_path, kind):
    import os
    import subprocess
    import sys

    import app

    rosheen = None
    if kind == 'music':
        s, _, target = music_setup(cards, count=2)
        upkeep(s)
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    elif kind == 'copied_lki':
        s = game(cards)
        bear = put(s, 'Grizzly Bears', 'battlefield')
        target = cast(s, 'Clone', mana={'C': 3, 'U': 1})
        choose(s, [bear.id])
        to_phase(s, 'main1', 2)
        cast(s, 'Essence Leak', [target.id], pid='p2', mana={'U': 1})
        upkeep(s)
        respond(s, 'Unsummon', [target.id], 'p2', {'U': 1})
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    else:
        s = game(cards)
        target = put(s, 'Riptide Replicator', 'battlefield')
        rosheen = put(s, 'Rosheen Meanderer', 'battlefield')
        cast(s, "Painter's Servant", mana={'C': 2})
        choose(s, ['Green'])
        cast(s, 'Essence Leak', [target.id], mana={'U': 1})
        upkeep(s)
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    saved = tmp_path / 'upkeep91.json'
    saved.write_text(s.state.model_dump_json())
    backend = Path(app.__file__).resolve().parents[1]
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
kind,target,rosheen=sys.argv[3:]
if kind=='rosheen':
 act(s,'p1',type='activate_ability',card_id=rosheen,ability=0,sources=[])
d=s.state.rules.decision
assert d and d.player=='p1'
act(s,'p1',type='choose',decision_id=d.id,option_ids=['pay'])
settle(s)
assert s.state.players['p1'].mana=={}
assert s.state.cards[target].zone==('p1:hand' if kind=='copied_lki' else 'p1:battlefield')
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), kind, target.id, rosheen.id if rosheen else ''],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
