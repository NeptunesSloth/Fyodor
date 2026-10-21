"""Frozen combat attacking-player receipts and Souls of the Faultless."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import attack
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import block

DATA = json.loads((Path(__file__).parent / 'fixtures/combat_damage_life43_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(DATA):
        base[row['name']] = card(row['name'], number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.fixture(autouse=True)
def native_scripts():
    scripts._cached.cache_clear()
    yield
    scripts._cached.cache_clear()


def game(cards):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    for player in ('p1', 'p2', 'p3'):
        act(s, player, type='set_prefs', auto_resolve_own_triggers='off', hold_priority=True)
    return s


def blocked_damage(s, soul, *, attacking=False, multiple=False, attacker='p1'):
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2' if attacking else attacker)
    if attacking:
        put(s, 'High Alert', 'battlefield')
    second = put(s, 'Runeclaw Bear', 'battlefield', 'p2') if multiple else None
    turn = 6 if attacker == 'p3' else 4
    start(s, turn=turn)
    attack(s, [soul if attacking else bear], pid=attacker, turn=turn)
    to_phase(s, 'declare_blockers')
    pairs = [(bear, soul)] if attacking else [(soul, bear)]
    if second is not None:
        pairs.append((second, soul))
    block(s, 'p2', *pairs)
    from app.rules import combat, replace
    from app.rules.plan import Plan

    plan = Plan(s.state, 'p1', s.cards, None)
    before = s.state.model_dump_json()
    events = combat.combat_damage_events(plan, combat.compute_combat_damage(plan, 'only'))
    assert events and all(event['attacking_player'] == attacker for event in events)
    preview = replace.damage_outcome(plan, events, answers={}, order=None, ask=False)
    assert isinstance(preview, replace.DamageOutcome)
    assert all(event['attacking_player'] == attacker for event in preview.events)
    assert s.state.model_dump_json() == before
    to_phase(s, 'combat_damage')
    decision = s.state.rules.decision
    if multiple:
        assert decision.kind == 'divide'
        act(s, decision.player, type='choose', decision_id=decision.id, amounts=[2, 2])
        while s.state.rules.decision is not None and s.state.rules.decision.kind == 'order':
            decision = s.state.rules.decision
            act(s, decision.player, type='choose', decision_id=decision.id,
                option_ids=[option.id for option in decision.options])
    return bear


def test_defender_stops_native_attack_and_noncombat_damage_never_triggers(cards):
    s = game(cards)
    soul = cast(s, 'Souls of the Faultless')
    put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    to_phase(s, 'declare_attackers', turn=4)
    with pytest.raises(ActionError, match='defender|attack'):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': soul.id, 'target': 'p2'}])
    act(s, 'p1', type='declare_attackers', attackers=[])
    to_phase(s, 'main2')
    cast(s, 'Lightning Bolt', targets=[soul.id])
    assert soul.damage == 3 and not s.state.zones['stack']
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [40, 40, 40]
    roundtrip(s)


@pytest.mark.parametrize('attacking', [False, True])
def test_actual_combat_attacker_is_not_necessarily_damage_source_controller(cards, attacking):
    s = game(cards)
    soul = put(s, 'Souls of the Faultless', 'battlefield', 'p1' if attacking else 'p2')
    blocked_damage(s, soul, attacking=attacking)
    settle(s)
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == ([40, 40, 40] if attacking else [38, 42, 40])
    roundtrip(s)


def test_simultaneous_two_blockers_one_receipt_source_dies_gain_replaced_loss_nominal(cards):
    s = game(cards)
    soul = put(s, 'Souls of the Faultless', 'battlefield')
    put(s, "Alhammarret's Archive", 'battlefield')
    blocked_damage(s, soul, attacking=True, multiple=True)
    assert s.state.cards[soul.id].zone == 'p1:graveyard', (s.state.cards[soul.id].damage, s.state.rules.decision)
    queued = [entry for entry in s.state.rules.stack.values() if entry.event]
    assert len(queued) == 1, (s.state.rules.decision, s.state.rules.pending_triggers, s.state.turn.phase, [s.state.players[p].life for p in ('p1', 'p2', 'p3')])
    event = queued[0].event
    assert event.amount == 4 and event.attacking_player == 'p1' and event.count == 2
    settle(s)
    assert s.state.players['p1'].life == 44
    roundtrip(s)


def test_trigger_controller_stays_frozen_after_actual_control_change(cards):
    s = game(cards)
    soul = put(s, 'Souls of the Faultless', 'battlefield', 'p2')
    blocked_damage(s, soul)
    pending = next(entry for entry in s.state.rules.stack.values() if entry.event)
    assert pending.controller == 'p2' and pending.event.attacking_player == 'p1'
    cast(s, 'Act of Aggression', targets=[soul.id], life_symbols=[])
    assert s.state.rules.decision is None
    assert s.state.cards[soul.id].controller == 'p1', (s.state.turn.phase, s.state.turn.number, [e for e in s.state.rules.effects if e.layer == '2'], s.state.rules.decision)
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [38, 42, 40]
    to_phase(s, 'main1', turn=5)
    assert s.state.cards[soul.id].controller == 'p2'
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [38, 42, 40]
    roundtrip(s)


def test_legacy_missing_combat_player_requires_manual_resolution(cards):
    from app.game.actions import DamageDealt
    from app.game.rules_state import Event, TriggerEvent
    from app.game.session import GameSession
    from app.game.state import GameState

    assert Event(batch=1, kind='damage').attacking_player is None
    assert TriggerEvent(kind='dealt_damage').attacking_player is None
    assert DamageDealt(source='o1', target='c1', amount=2).attacking_player is None
    s = game(cards)
    soul = put(s, 'Souls of the Faultless', 'battlefield', 'p2')
    blocked_damage(s, soul)
    raw = s.state.model_dump(mode='json')
    for entry in raw['rules']['stack'].values():
        if entry.get('event'):
            entry['event'].pop('attacking_player')
    s = GameSession(GameState.model_validate(raw), cards=cards)
    settle(s)
    decision = s.state.rules.decision
    assert decision.kind == 'manual_resolution' and 'attacking player' in decision.prompt
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [40, 40, 40]
    act(s, decision.player, type='choose', decision_id=decision.id, option_ids=['done'])
    assert s.state.rules.decision is None
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [40, 40, 40]
    roundtrip(s)


def test_saved_sourcegone_combat_receipt_resolves_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = game(cards)
    soul = put(s, 'Souls of the Faultless', 'battlefield')
    put(s, "Alhammarret's Archive", 'battlefield')
    blocked_damage(s, soul, attacking=True, multiple=True)
    assert s.state.cards[soul.id].zone == 'p1:graveyard', (s.state.cards[soul.id].damage, s.state.rules.decision)
    saved = tmp_path / 'souls.json'
    saved.write_text(s.state.model_dump_json())
    worker = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3');settle(s)
assert [s.state.players[p].life for p in ('p1','p2','p3')]==[44,40,40]
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
roundtrip(s);repo.close()
"""
    result = subprocess.run([sys.executable, '-c', worker, str(saved), str(cards.db_path), soul.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_prevented_combat_damage_creates_no_life_trigger(cards):
    s = game(cards)
    soul = put(s, 'Souls of the Faultless', 'battlefield', 'p2')
    cast(s, 'Gaseous Form', targets=[soul.id])
    blocked_damage(s, soul)
    settle(s)
    assert s.state.cards[soul.id].damage == 0 and not s.state.zones['stack']
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [40, 40, 40]
    roundtrip(s)


def test_third_player_combat_has_its_own_frozen_attacking_player(cards):
    s = game(cards)
    soul = put(s, 'Souls of the Faultless', 'battlefield', 'p2')
    blocked_damage(s, soul, attacker='p3')
    settle(s)
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [40, 42, 38]
    roundtrip(s)


def test_whole_canonical_souls_is_supported(cards):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve('Souls of the Faultless'))
    assert result.level == 'FULL', result.manual_parts
