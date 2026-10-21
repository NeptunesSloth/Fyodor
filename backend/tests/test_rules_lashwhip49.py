"""Lashwhip Predator counts opposing controllers collectively, without reducing GG."""

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditional_prevention import attack
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game
from tests.test_rules_wave30m_durations import to_phase


def setup(cards):
    s = game(cards, ["Lashwhip Predator", "Wind Drake"])
    source = put(s, "Lashwhip Predator", "hand")
    return s, source


def test_complete_canonical_predator(cards):
    assert coverage.of_card_data(cards.resolve("Lashwhip Predator")).level == "FULL"


def populate(s):
    put(s, "Grizzly Bears", "battlefield", "p2")
    put(s, "Grizzly Bears", "battlefield", "p3")
    put(s, "Llanowar Elves", "battlefield", "p3")


def test_aggregate_three_across_two_opponents_gets_discount_without_changing_mana_value(cards):
    s, source = setup(cards)
    populate(s)
    mana(s, C=2, G=2)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and not s.state.players["p1"].mana
    record = next(r for r in s.state.rules.payments.values() if r.card == source.id)
    assert record.total_cost == "{2}{G}{G}"
    from app.rules.plan import Plan

    assert Plan(s.state, "p1", cards, None).ch(source).mana_value == 6
    roundtrip(s)


def test_two_opposing_creatures_and_own_creatures_do_not_get_discount(cards):
    s, source = setup(cards)
    for pid in ["p1", "p2", "p3"]:
        put(s, "Grizzly Bears", "battlefield", pid)
    put(s, "Llanowar Elves", "battlefield")
    mana(s, C=2, G=2)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    assert s.state.model_dump_json() == before
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and not s.state.players["p1"].mana
    roundtrip(s)


def test_control_change_changes_current_opponent_count(cards):
    s, source = setup(cards)
    populate(s)
    elf = next(c for c in s.state.cards.values() if c.name == "Llanowar Elves" and c.zone == "p3:battlefield")
    act(s, "p1", type="set_controller", card_ids=[elf.id], player="p1")
    mana(s, C=2, G=2)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    assert s.state.model_dump_json() == before
    act(s, "p1", type="set_controller", card_ids=[elf.id], player="p2")
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield"
    roundtrip(s)


def test_reach_actually_blocks_a_flying_creature(cards):
    s, source = setup(cards)
    mana(s, C=4, G=2)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    flyer = put(s, "Wind Drake", "battlefield", "p2")
    attack(s, [flyer], pid="p2", target="p1", turn=5)
    to_phase(s, "declare_blockers")
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": source.id, "attacker_id": flyer.id}])
    assert source.blocking
    roundtrip(s)


def test_true_cold_saved_game_uses_current_aggregate_count(cards, tmp_path):
    import subprocess
    import sys

    s, source = setup(cards)
    populate(s)
    saved = tmp_path / "lashwhip49.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
mana(s,C=2,G=2)
act(s,'p1',type='cast_spell',card_id=sys.argv[3],sources=[])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:battlefield'
assert not s.state.players['p1'].mana
roundtrip(s)
"""
    p = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert p.returncode == 0, p.stdout + p.stderr
