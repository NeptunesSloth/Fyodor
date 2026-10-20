"""Isolated typed prerequisite proofs; these are not card gameplay admissions."""
import pytest
from pydantic import ValidationError

from app.rules.last_combat_receipts44 import CombatMemory, begin, declared, previous_players


def test_fresh_first_combat_knows_no_previous_but_legacy_does_not_infer_one():
    fresh, legacy = CombatMemory(known_empty=['p1', 'p2']), CombatMemory()
    for memory in [fresh, legacy]:
        begin(memory, 'p1', 1, 1)
    assert previous_players(fresh, 'p1', 'hellkite.1') == set()
    assert previous_players(legacy, 'p1', 'hellkite.1') is None


def test_previous_own_combat_survives_other_players_turns_and_save():
    memory = CombatMemory(known_empty=['p1', 'p2', 'p3'])
    begin(memory, 'p1', 1, 1)
    assert declared(memory, 'p1', 1, 1, ['hellkite.1'], ['p2'], {'p1', 'p2', 'p3'})
    begin(memory, 'p2', 2, 1)
    begin(memory, 'p3', 3, 1)
    memory = CombatMemory.model_validate_json(memory.model_dump_json())
    begin(memory, 'p1', 4, 1)
    assert previous_players(memory, 'p1', 'hellkite.1') == {'p2'}
    assert previous_players(memory, 'p1', 'hellkite.2') == set()
    assert previous_players(memory, 'p2', 'hellkite.1') == set()


def test_same_turn_extra_combat_and_empty_previous_combat_replace_old_receipt():
    memory = CombatMemory(known_empty=['p1'])
    begin(memory, 'p1', 1, 1)
    declared(memory, 'p1', 1, 1, ['hellkite.1'], ['p2'], {'p1', 'p2'})
    begin(memory, 'p1', 1, 2)
    assert previous_players(memory, 'p1', 'hellkite.1') == {'p2'}
    begin(memory, 'p1', 1, 3)
    assert previous_players(memory, 'p1', 'hellkite.1') == set()


def test_only_actual_declaration_player_targets_enter_memory():
    memory = CombatMemory(known_empty=['p1'])
    begin(memory, 'p1', 1, 1)
    declared(memory, 'p1', 1, 1, ['hellkite.1', 'other.1'], ['walker.1', 'p2'], {'p1', 'p2'})
    begin(memory, 'p1', 1, 2)
    assert previous_players(memory, 'p1', 'hellkite.1') == set()
    assert previous_players(memory, 'p1', 'put-attacking.1') == set()
    assert previous_players(memory, 'p1', 'other.1') == {'p2'}


def test_stale_declaration_cannot_overwrite_current_combat_and_duplicate_begin_preserves_it():
    memory = CombatMemory()
    begin(memory, 'p1', 4, 2)
    assert not declared(memory, 'p1', 4, 1, ['hellkite.1'], ['p2'], {'p1', 'p2'})
    assert declared(memory, 'p1', 4, 2, ['hellkite.1'], ['p2'], {'p1', 'p2'})
    begin(memory, 'p1', 4, 2)
    begin(memory, 'p1', 4, 3)
    assert previous_players(memory, 'p1', 'hellkite.1') == {'p2'}


def test_unknown_receipt_version_is_rejected():
    with pytest.raises(ValidationError):
        CombatMemory.model_validate({'version': 2})
