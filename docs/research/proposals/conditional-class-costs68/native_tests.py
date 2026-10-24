"""Actual class levels and attack choices retain native costs and current combat counts."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave16a_class import bar, level
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/conditional_class_costs68_cards.json").read_text())


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, copies=1):
    names = [c["name"] for c in DATA] + ["Paladin Class"] * (copies - 1)
    s = table(cards, names, names, names)
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    source = put(s, "Paladin Class", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    answer(s)
    return s, source


def up(s, source, n):
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2 if n == 2 else 4, "W": 1})
    act(s, "p1", type="activate_ability", card_id=source.id, ability=bar(s, source, n), sources=[])
    answer(s)
    assert level(s, source) == n


def attack2(s, source):
    bear = put(s, "Grizzly Bears", "battlefield")
    other = put(s, "Runeclaw Bear", "battlefield")
    to_phase(s, "declare_attackers", 7)
    act(
        s,
        "p1",
        type="declare_attackers",
        attackers=[{"card_id": c.id, "target": "p2"} for c in [bear, other]],
    )
    return bear, other


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve("Paladin Class")).level == "FULL"


def test_native_tax_actual_opponent_cost_only_during_source_controller_turn(cards):
    s, source = setup(cards)
    bolt = put(s, "Lightning Bolt", "hand", pid="p2")
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    wait_priority(s, "p2")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p3"], sources=[])
    assert s.state.model_dump_json() == before
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p3"], sources=[])
    answer(s)
    assert s.state.players["p3"].life == 37
    to_phase(s, "main1", 5)
    bolt = put(s, "Lightning Bolt", "hand", pid="p3")
    act(s, "p3", type="add_mana", player="p3", mana={"R": 1})
    wait_priority(s, "p3")
    act(s, "p3", type="cast_spell", card_id=bolt.id, targets=["p1"], sources=[])
    answer(s)
    assert s.state.players["p1"].life == 37
    roundtrip(s)


def test_native_level_two_buff_and_no_attack_trigger_until_level_three(cards):
    s, source = setup(cards)
    up(s, source, 2)
    bear, other = attack2(s, source)
    assert s.state.rules.decision is None
    assert Plan(s.state, "p1", cards, None).ch(bear).pt == (3, 3)
    assert "double strike" not in Plan(s.state, "p1", cards, None).ch(bear).keywords
    roundtrip(s)


def test_native_level_three_selected_attacker_counts_other_not_itself(cards):
    s, source = setup(cards)
    up(s, source, 2)
    up(s, source, 3)
    bear, other = attack2(s, source)
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {bear.id, other.id}
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
    settle(s)
    a, b = (Plan(s.state, "p1", cards, None).ch(c) for c in [bear, other])
    assert a.pt == (4, 4) and "double strike" in a.keywords
    assert b.pt == (3, 3) and "double strike" not in b.keywords
    roundtrip(s)


def test_level_three_single_attacker_gets_double_strike_without_extra_power(cards):
    s, source = setup(cards)
    up(s, source, 2)
    up(s, source, 3)
    bear = put(s, "Grizzly Bears", "battlefield")
    to_phase(s, "declare_attackers", 7)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    d = s.state.rules.decision
    if d:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
    settle(s)
    ch = Plan(s.state, "p1", cards, None).ch(bear)
    assert ch.pt == (3, 3) and "double strike" in ch.keywords
    roundtrip(s)


def test_actual_source_control_change_moves_own_turn_tax_scope(cards):
    s, source = setup(cards)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    bolt = put(s, "Lightning Bolt", "hand", pid="p3")
    act(s, "p3", type="add_mana", player="p3", mana={"R": 1})
    wait_priority(s, "p3")
    act(s, "p3", type="cast_spell", card_id=bolt.id, targets=["p1"], sources=[])
    answer(s)
    to_phase(s, "main1", 5)
    bolt = put(s, "Lightning Bolt", "hand", pid="p1")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    wait_priority(s, "p1")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p3"], sources=[])
    assert s.state.model_dump_json() == before
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p3"], sources=[])
    answer(s)
    roundtrip(s)


def test_actual_class_recast_loses_levels_and_second_level_buff(cards):
    s, source = setup(cards)
    up(s, source, 2)
    up(s, source, 3)
    bear = put(s, "Grizzly Bears", "battlefield")
    assert Plan(s.state, "p1", cards, None).ch(bear).pt == (3, 3)
    old = s.state.rules.object_id(source.id)
    bounce = put(s, "Disperse", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 1, "W": 1})
    act(s, "p1", type="cast_spell", card_id=bounce.id, targets=[source.id], sources=[])
    answer(s)
    assert source.zone == "p1:hand" and Plan(s.state, "p1", cards, None).ch(bear).pt == (2, 2)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    answer(s)
    assert s.state.rules.object_id(source.id) != old and level(s, source) == 1
    assert Plan(s.state, "p1", cards, None).ch(bear).pt == (2, 2)
    roundtrip(s)


def test_native_attack_amount_reads_current_other_attackers_at_resolution(cards):
    s, source = setup(cards)
    up(s, source, 2)
    up(s, source, 3)
    bear, other = attack2(s, source)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
    bounce = put(s, "Disperse", "hand", pid="p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 2, "U": 1})
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=bounce.id, targets=[other.id], sources=[])
    answer(s)
    assert other.zone == "p1:hand"
    ch = Plan(s.state, "p1", cards, None).ch(bear)
    assert ch.pt == (3, 3) and "double strike" in ch.keywords
    to_phase(s, "main1", 8)
    ch = Plan(s.state, "p1", cards, None).ch(bear)
    assert ch.pt == (3, 3) and "double strike" not in ch.keywords
    roundtrip(s)


def test_true_cold_native_level_three_target_retains_level_and_current_count(cards, tmp_path):
    import subprocess
    import sys

    from app.rules import conditional_class_costs68

    s, source = setup(cards)
    up(s, source, 2)
    up(s, source, 3)
    bear, other = attack2(s, source)
    assert s.state.rules.decision
    saved = tmp_path / "saved.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
bear,other,source=sys.argv[3:]
d=s.state.rules.decision
assert d and {o.id for o in d.options}=={bear,other}
act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear])
settle(s)
ch=Plan(s.state,'p1',r,None).ch(s.state.cards[bear])
assert ch.pt==(4,4) and 'double strike' in ch.keywords
assert s.state.rules.levels[s.state.rules.object_id(source)]==3
roundtrip(s)
r.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), bear.id, other.id, source.id],
        cwd=Path(conditional_class_costs68.__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_two_actual_classes_stack_their_opponent_tax(cards):
    s, source = setup(cards, copies=2)
    twin = next(
        c
        for c in s.state.cards.values()
        if c.name == "Paladin Class" and c.owner == "p1" and c.id != source.id
    )
    act(s, "p1", type="move", card_ids=[twin.id], to={"zone": "hand", "player": "p1"})
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=twin.id, sources=[])
    answer(s)
    assert source.zone == twin.zone == "p1:battlefield"
    bolt = put(s, "Lightning Bolt", "hand", pid="p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1, "R": 1})
    wait_priority(s, "p2")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p3"], sources=[])
    assert s.state.model_dump_json() == before
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p3"], sources=[])
    answer(s)
    assert s.state.players["p3"].life == 37
    roundtrip(s)
