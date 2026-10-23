"""Native permanent offers defer every outcome until all APNAP choices finish."""
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

DATA = json.loads((Path(__file__).parent / 'fixtures/permanent83_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest']


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


def cast_wave(s, x):
    c = put(s, 'Killing Wave', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': x, 'B': 1})
    act(s, 'p1', type='cast_spell', card_id=c.id, x_value=x, targets=[], sources=[])
    settle(s)
    return c


def test_whole_killing_wave(cards):
    assert coverage.of_card_data(cards.resolve('Killing Wave')).level == 'FULL'


def test_apnap_choices_then_simultaneous_life_and_sacrifice(cards):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    c = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    d = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    cast_wave(s, 2)
    assert s.state.rules.decision.player == 'p1'
    choose(s, [a.id])
    assert s.state.rules.decision.player == 'p2'
    assert all(p.life == 40 for p in s.state.players.values())
    choose(s, [c.id])
    assert s.state.rules.decision.player == 'p3'
    assert all(p.life == 40 for p in s.state.players.values())
    assert all(s.state.cards[x.id].zone.endswith(':battlefield') for x in [a, b, c, d, other])
    choose(s, [])
    assert s.state.players['p1'].life == s.state.players['p2'].life == 38
    assert s.state.players['p3'].life == 40
    assert s.state.cards[a.id].zone == 'p1:battlefield' and s.state.cards[c.id].zone == 'p2:battlefield'
    gone = {b.id, d.id, other.id}
    assert all(s.state.cards[cid].zone.endswith(':graveyard') for cid in gone)
    changes = [e for e in s.state.rules.events if e.kind == 'zone_change' and e.card in gone]
    assert len(changes) == 3 and len({e.batch for e in changes}) == 1
    losses = [e for e in s.state.rules.events if e.kind == 'life_loss' and e.player in {'p1', 'p2'}]
    assert len(losses) == 2 and {e.batch for e in losses} == {changes[0].batch}
    roundtrip(s)


@pytest.mark.parametrize('locked', [False, True])
def test_zero_x_can_be_paid_even_with_life_locked(cards, locked):
    s = game(cards)
    creature = put(s, 'Platinum Emperion' if locked else 'Grizzly Bears', 'battlefield')
    cast_wave(s, 0)
    choose(s, [creature.id])
    assert s.state.cards[creature.id].zone == 'p1:battlefield' and s.state.players['p1'].life == 40
    roundtrip(s)


def test_life_lock_rejects_positive_payment_atomically_and_still_sacrifices(cards):
    from app.game.errors import ActionError

    s = game(cards)
    creature = put(s, 'Platinum Emperion', 'battlefield')
    cast_wave(s, 1)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        choose(s, [creature.id])
    assert s.state.model_dump(mode='json') == before
    choose(s, [])
    assert s.state.cards[creature.id].zone == 'p1:graveyard' and s.state.players['p1'].life == 40


def test_sigarda_allows_decline_without_forced_sacrifice(cards):
    s = game(cards)
    angel = put(s, 'Sigarda, Host of Herons', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast_wave(s, 3)
    choose(s, [])
    assert s.state.cards[angel.id].zone == s.state.cards[bear.id].zone == 'p2:battlefield'
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_cannot_pay_more_life_than_available_even_for_individual_creatures(cards):
    from app.game.errors import ActionError

    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    act(s, 'p1', type='set_life', player='p1', value=5)
    cast_wave(s, 3)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        choose(s, [a.id, b.id])
    assert s.state.model_dump(mode='json') == before
    choose(s, [a.id])
    assert s.state.players['p1'].life == 2
    assert s.state.cards[a.id].zone == 'p1:battlefield' and s.state.cards[b.id].zone == 'p1:graveyard'


def test_real_life_loss_replacement_does_not_change_the_chosen_payment(cards):
    s = game(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    blood = put(s, 'Bloodletter of Aclazotz', 'battlefield', 'p3')
    to_phase(s, 'main1', 3)
    # Carol's turn makes her real Bloodletter replace opponents' life loss.
    wave = put(s, 'Killing Wave', 'hand', 'p3')
    act(s, 'p3', type='add_mana', player='p3', mana={'C': 2, 'B': 1})
    wait_priority(s, 'p3')
    act(s, 'p3', type='cast_spell', card_id=wave.id, x_value=2, targets=[], sources=[])
    settle(s)
    assert s.state.rules.decision.player == 'p3'
    choose(s, [blood.id])
    assert s.state.players['p3'].life == s.state.players['p1'].life == 40
    choose(s, [a.id])
    assert s.state.players['p3'].life == 38 and s.state.players['p1'].life == 36
    assert s.state.cards[a.id].zone == 'p1:battlefield'
    roundtrip(s)


def pending_replacement(cards):
    s = game(cards)
    payer = put(s, 'Grizzly Bears', 'battlefield')
    colossus = put(s, 'Darksteel Colossus', 'battlefield', 'p2')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    put(s, 'Rest in Peace', 'battlefield', 'p3')
    cast_wave(s, 1)
    choose(s, [payer.id])
    choose(s, [])
    choose(s, [other.id])
    assert s.state.rules.decision.resume['step'] == 'permanent_route83'
    assert len(s.state.rules.decision.options) == 2
    assert all(p.life == 40 for p in s.state.players.values())
    assert s.state.cards[colossus.id].zone == 'p2:battlefield'
    return s, colossus


@pytest.mark.parametrize('route', ['exile', 'library:shuffle'])
def test_competing_replacements_finish_before_any_life_or_sacrifice_commit(cards, route):
    s, colossus = pending_replacement(cards)
    d = s.state.rules.decision
    chosen = next(o.id for o in d.options if route in o.label)
    choose(s, [chosen])
    assert s.state.players['p1'].life == s.state.players['p3'].life == 39
    assert s.state.players['p2'].life == 40
    if route == 'exile':
        assert s.state.cards[colossus.id].zone == 'p2:exile'
    else:
        assert any(c.name == 'Darksteel Colossus' and c.zone == 'p2:library' for c in s.state.cards.values())
    assert not s.state.rules.decision
    roundtrip(s)


@pytest.mark.parametrize('route', ['exile', 'library:shuffle'])
def test_true_cold_prepared_life_and_sacrifice_packet_preserves_original_choices(cards, tmp_path, route):
    import os
    import subprocess
    import sys

    import app

    s, colossus = pending_replacement(cards)
    backend = Path(app.__file__).resolve().parents[1]
    saved = tmp_path / 'packet.json'
    saved.write_text(s.state.model_dump_json())
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
route,old=sys.argv[3:]
assert all(p.life==40 for p in s.state.players.values())
assert s.state.cards[old].zone=='p2:battlefield'
d=s.state.rules.decision
assert d and d.resume['step']=='permanent_route83'
answer=next(o.id for o in d.options if route in o.label)
act(s,d.player,type='choose',decision_id=d.id,option_ids=[answer])
settle(s)
assert s.state.players['p1'].life==39 and s.state.players['p3'].life==39
assert s.state.players['p2'].life==40
if route=='exile':
 assert s.state.cards[old].zone=='p2:exile'
else:
 assert any(c.name=='Darksteel Colossus' and c.zone=='p2:library' for c in s.state.cards.values())
assert not s.state.rules.decision
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), route, colossus.id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('keep_vilis', [False, True])
def test_simultaneously_sacrificed_vilis_does_not_see_paid_life_but_surviving_vilis_does(cards, keep_vilis):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    vilis = put(s, 'Vilis, Broker of Blood', 'battlefield')
    cast_wave(s, 1)
    hand_before = len(s.state.zones['p1:hand'])
    choose(s, [bear.id, vilis.id] if keep_vilis else [bear.id])
    assert s.state.players['p1'].life == (38 if keep_vilis else 39)
    assert len(s.state.zones['p1:hand']) == hand_before + (2 if keep_vilis else 0)
    assert s.state.cards[vilis.id].zone == ('p1:battlefield' if keep_vilis else 'p1:graveyard')
    roundtrip(s)


def test_simultaneous_life_payment_and_sacrifice_use_true_before_event_power_for_kresh(cards):
    from app.rules.plan import Plan

    assert coverage.of_card_data(cards.resolve('Kresh the Bloodbraided')).level == 'FULL'
    assert coverage.of_card_data(cards.resolve("Death's Shadow")).level == 'FULL'
    s = game(cards)
    act(s, 'p1', type='set_life', player='p1', value=10)
    kresh = put(s, 'Kresh the Bloodbraided', 'battlefield')
    shadow = put(s, "Death's Shadow", 'battlefield')
    assert Plan(s.state, 'p1', s.cards, None).ch(shadow).pt == (3, 3)
    original = s.state.rules.object_id(shadow.id)
    cast_wave(s, 3)
    choose(s, [kresh.id])
    assert s.state.players['p1'].life == 7 and s.state.cards[shadow.id].zone == 'p1:graveyard'
    frozen = s.state.rules.lki[original]
    assert (frozen.power, frozen.toughness) == (3, 3)
    assert frozen.controller == 'p1' and frozen.zone == 'p1:battlefield'
    assert frozen.attached_objects_known
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {'yes', 'no'}
    choose(s, ['yes'])
    assert s.state.cards[kresh.id].counters.get('+1/+1', 0) == 3
