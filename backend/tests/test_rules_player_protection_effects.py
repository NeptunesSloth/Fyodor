"""Resolved player qualities bind identities; continuous statics follow current opponents."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, player_shields, targets
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import answer, priority
from tests.test_rules_wave30m_durations import three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/player_protection_effects_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='ppe', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())]
    s = three(cards, names, names, names)
    hold(s)
    return s


def spell(s, name, mana, targets=()):
    c = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=list(targets))
    settle(s)
    return s.state.cards[c.id]


def legal(s, cid, player):
    return cid in targets.legal_targets(Plan(s.state, player, s.cards, None), 'permanent', player)


@pytest.mark.parametrize('name', ['Eon Frolicker', 'Absolute Virtue', 'Cliffside Rescuer', 'Figure of Fable'])
def test_canonical_cards_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_absolute_virtue_dynamic_controller_ability_loss_and_departure(cards):
    s = setup(cards)
    virtue = put(s, 'Absolute Virtue', 'battlefield')
    def can(actor, player):
        return player_shields.can_target(Plan(s.state, actor, cards, None), actor, player, None)
    assert not can('p2', 'p1') and not can('p3', 'p1') and can('p1', 'p1')
    act(s, 'p1', type='set_controller', card_ids=[virtue.id], player='p2')
    assert can('p2', 'p1') and not can('p1', 'p2') and not can('p3', 'p2')
    humility = put(s, 'Humility', 'battlefield')
    assert can('p1', 'p2')
    act(s, 'p1', type='move', card_ids=[humility.id], to={'zone': 'exile'})
    assert not can('p1', 'p2')
    act(s, 'p2', type='move', card_ids=[virtue.id], to={'zone': 'exile'})
    assert can('p1', 'p2')
    roundtrip(s)


def test_rescuer_sacrifices_and_binds_opponents_even_after_target_control_change(cards):
    s = setup(cards)
    rescuer = put(s, 'Cliffside Rescuer', 'battlefield')
    target = put(s, 'Bonesplitter', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=rescuer.id, ability=1, targets=[target.id])
    settle(s)
    assert s.state.cards[rescuer.id].zone == 'p1:graveyard'
    assert legal(s, target.id, 'p1') and not legal(s, target.id, 'p2') and not legal(s, target.id, 'p3')
    act(s, 'p1', type='set_controller', card_ids=[target.id], player='p2')
    assert legal(s, target.id, 'p1') and not legal(s, target.id, 'p2')
    to_phase(s, 'main1', turn=5)
    assert legal(s, target.id, 'p2')
    roundtrip(s)


def test_eon_cast_trigger_targets_opponent_extra_turn_and_snapshots_planeswalkers(cards):
    s = setup(cards)
    old = spell(s, 'Jace Beleren', {'U': 2, 'C': 1})
    source = spell(s, 'Eon Frolicker', {'U': 2, 'C': 2})
    d = s.state.rules.decision
    assert d is not None and 'p1' not in {o.id for o in d.options}
    answer(s, ['p2'])
    assert s.state.rules.extra_turns[-1]['player'] == 'p2'
    assert not legal(s, old.id, 'p2') and legal(s, old.id, 'p3')
    assert not player_shields.can_target(Plan(s.state, 'p2', cards, None), 'p2', 'p1', None)
    priority(s, 'p1')
    late = spell(s, 'Narset, Parter of Veils', {'U': 2, 'C': 1})
    assert legal(s, late.id, 'p2')
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
    act(s, 'p1', type='set_controller', card_ids=[old.id], player='p3')
    assert not legal(s, old.id, 'p2')
    to_phase(s, 'main1', turn=2)
    assert s.state.turn.active_player == 'p2'
    to_phase(s, 'main1', turn=5)
    assert s.state.turn.active_player == 'p1' and legal(s, old.id, 'p2')
    roundtrip(s)


def test_uncast_eon_entry_does_not_grant_extra_turn_or_protection(cards):
    s = setup(cards)
    put(s, 'Eon Frolicker', 'battlefield')
    act(s, 'p1', type='pass_priority')
    assert not s.state.rules.extra_turns and not s.state.rules.player_shields
    roundtrip(s)


def test_figure_full_upgrades_and_condition_bind_original_opponents(cards):
    s = setup(cards)
    figure = put(s, 'Figure of Fable', 'battlefield')
    for step, (index, mana) in enumerate([(2, {'G': 6}), (0, {'G': 1}), (1, {'G': 3}), (2, {'G': 6})]):
        priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana=mana)
        act(s, 'p1', type='activate_ability', card_id=figure.id, ability=index)
        settle(s)
        if step == 0:
            assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[figure.id]).pt == (1, 1)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[figure.id])
    assert ch.pt == (7, 8) and 'Avatar' in ch.subtypes
    assert not legal(s, figure.id, 'p2') and legal(s, figure.id, 'p1')
    act(s, 'p1', type='set_controller', card_ids=[figure.id], player='p2')
    assert not legal(s, figure.id, 'p2') and legal(s, figure.id, 'p1')
    roundtrip(s)


def test_real_reanimation_does_not_satisfy_eon_cast_condition(cards):
    s = setup(cards)
    source = put(s, 'Eon Frolicker', 'graveyard')
    spell(s, 'Reanimate', {'B': 1}, [source.id])
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].life == 36
    assert not s.state.rules.extra_turns and not s.state.rules.player_shields
    roundtrip(s)


def test_cast_clone_of_eon_satisfies_cast_condition_and_uses_new_trigger(cards):
    s = setup(cards)
    original = put(s, 'Eon Frolicker', 'battlefield', 'p2')
    source = spell(s, 'Clever Impersonator', {'U': 2, 'C': 2})
    d = s.state.rules.decision
    assert d is not None and original.id in {o.id for o in d.options}
    answer(s, [original.id])
    d = s.state.rules.decision
    assert d is not None and 'p3' in {o.id for o in d.options}
    answer(s, ['p3'])
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.extra_turns[-1]['player'] == 'p3'
    plan = Plan(s.state, 'p1', cards, None)
    assert not player_shields.can_target(plan, 'p3', 'p1', None)
    assert player_shields.can_target(plan, 'p2', 'p1', None)
    roundtrip(s)


def test_eon_pending_trigger_resumes_in_a_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    spell(s, 'Eon Frolicker', {'U': 2, 'C': 2})
    assert s.state.rules.decision is not None
    roundtrip(s)
    path = tmp_path / 'eon.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['p2']})
for _ in range(12):
    if not s.state.zones['stack']:
        break
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert s.state.rules.extra_turns[-1]['player'] == 'p2'
from app.rules import player_shields
from app.rules.plan import Plan
assert not player_shields.can_target(Plan(s.state, 'p1', repo, None), 'p2', 'p1', None)
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_departed_eon_pending_trigger_retains_cast_record_and_original_beneficiary(cards):
    s = setup(cards)
    source = spell(s, 'Eon Frolicker', {'U': 2, 'C': 2})
    assert s.state.rules.decision is not None
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
    answer(s, ['p3'])
    assert s.state.rules.extra_turns[-1]['player'] == 'p3'
    assert not player_shields.can_target(Plan(s.state, 'p1', cards, None), 'p3', 'p1', None)
    assert player_shields.can_target(Plan(s.state, 'p2', cards, None), 'p3', 'p2', None)
    roundtrip(s)
