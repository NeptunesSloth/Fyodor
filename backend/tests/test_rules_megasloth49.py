"""Megasloth counts individual counters, with native cost settlement."""

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


def setup(cards):
    s = game(cards, ["Lumbering Megasloth"])
    return s, put(s, "Lumbering Megasloth", "hand")


def cast_paid(s, source, generic):
    mana(s, C=generic, G=2)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and source.tapped
    assert not s.state.players["p1"].mana
    from app.rules.plan import Plan

    assert Plan(s.state, "p1", s.cards, None).ch(source).mana_value == 12
    record = next(r for r in s.state.rules.payments.values() if r.card == source.id)
    expected = ("{" + str(generic) + "}" if generic else "") + "{G}{G}"
    assert record.total_cost == expected
    roundtrip(s)


def test_complete_canonical_megasloth(cards):
    assert coverage.of_card_data(cards.resolve("Lumbering Megasloth")).level == "FULL"


def test_counts_all_kinds_on_all_players_and_permanents(cards):
    s, source = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    ring = put(s, "Sol Ring", "battlefield", "p3")
    for obj, kind, n in [(bear, "+1/+1", 2), (bear, "stun", 1), (ring, "charge", 2)]:
        act(s, "p1", type="counter", card_ids=[obj.id], kind=kind, delta=n)
    for pid, kind, n in [("p1", "energy", 1), ("p2", "poison", 1), ("p3", "experience", 1)]:
        act(s, "p1", type="resource", player=pid, key=kind, delta=n)
    cast_paid(s, source, 2)


def test_speed_life_and_counters_on_nonpermanents_do_not_discount(cards):
    s, source = setup(cards)
    for pid in ["p1", "p2", "p3"]:
        act(s, "p1", type="resource", player=pid, key="speed", delta=4)
    for zone, pid in [("graveyard", "p2"), ("hand", "p3")]:
        obj = put(s, "Sol Ring", zone, pid)
        act(s, "p1", type="counter", card_ids=[obj.id], kind="charge", delta=10)
    mana(s, C=9, G=2)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    assert s.state.model_dump_json() == before
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and source.tapped
    assert not s.state.players["p1"].mana
    roundtrip(s)


def test_many_counters_do_not_reduce_green_requirements(cards):
    s, source = setup(cards)
    ring = put(s, "Sol Ring", "battlefield", "p2")
    act(s, "p1", type="counter", card_ids=[ring.id], kind="charge", delta=30)
    mana(s, C=2)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    assert s.state.model_dump_json() == before
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and source.tapped
    assert s.state.players["p1"].mana == {"C": 2}
    roundtrip(s)


def test_true_cold_saved_counters_drive_native_payment(cards, tmp_path):
    import subprocess
    import sys

    s, source = setup(cards)
    ring = put(s, "Sol Ring", "battlefield", "p2")
    act(s, "p1", type="counter", card_ids=[ring.id], kind="charge", delta=6)
    act(s, "p1", type="resource", player="p3", key="experience", delta=2)
    act(s, "p1", type="resource", player="p1", key="speed", delta=4)
    saved = tmp_path / "megasloth49.json"
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
source=s.state.cards[sys.argv[3]]
assert source.zone=='p1:battlefield' and source.tapped
assert not s.state.players['p1'].mana
record=next(r for r in s.state.rules.payments.values() if r.card==source.id)
assert record.total_cost=='{2}{G}{G}'
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_trample_damage_after_entering_tapped(cards):
    from tests.test_rules_conditional_prevention import attack, damage
    from tests.test_rules_wave30m_durations import to_phase

    s, source = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield", "p2")
    cast_paid(s, source, 10)
    attack(s, [source], target="p2", turn=7)
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": source.id}])
    before = s.state.players["p2"].life
    damage(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, amounts=[2, 6])
    settle(s)
    assert blocker.zone == "p2:graveyard"
    assert s.state.players["p2"].life == before - 6
    roundtrip(s)
