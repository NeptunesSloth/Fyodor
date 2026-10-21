"""Actual damage receipts identify Brine Hag's current surviving damagers."""

from app.rules.plan import Plan
from tests.test_rules_conditional_prevention import activate, cast
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game
from tests.test_rules_wave30m_durations import to_phase


def setup(cards):
    s = game(
        cards, ["Brine Hag", "Prodigal Pyromancer", "Prodigal Sorcerer", "Murder", "Boomerang", "Cloudshift"]
    )
    red = cast(s, "Prodigal Pyromancer")
    blue = cast(s, "Prodigal Sorcerer")
    hag = put(s, "Brine Hag", "battlefield", "p2")
    to_phase(s, "main1", turn=7)
    return s, hag, red, blue


def test_brine_native_damagers_become_base_zero_two_permanently(cards):
    s, hag, red, blue = setup(cards)
    activate(s, red, "deals 1 damage", [hag.id])
    activate(s, blue, "deals 1 damage", [hag.id])
    assert hag.zone == "p2:graveyard"
    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(red).pt == plan.ch(blue).pt == (0, 2)
    to_phase(s, "main1", turn=10)
    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(red).pt == plan.ch(blue).pt == (0, 2)
    assert any("deals 1 damage" in a.text for a in plan.ch(red).abilities)
    roundtrip(s)


def test_brine_no_actual_damager_leaves_creatures_unchanged(cards):
    s, hag, red, blue = setup(cards)
    hag = cast(s, "Brine Hag")
    cast(s, "Murder", [hag.id], pid="p2")
    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(red).pt == plan.ch(blue).pt == (1, 1)
    roundtrip(s)


def test_brine_damager_new_incarnation_is_not_affected(cards):
    s, hag, red, blue = setup(cards)
    activate(s, red, "deals 1 damage", [hag.id])
    cast(s, "Boomerang", [red.id])
    red = cast(s, "Prodigal Pyromancer")
    cast(s, "Murder", [hag.id], pid="p2")
    assert Plan(s.state, "p1", cards, None).ch(red).pt == (1, 1)
    roundtrip(s)


def test_brine_full_actual_canonical(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve("Brine Hag")).level == "FULL"


def test_brine_base_setting_preserves_counters_and_ignores_non_damager(cards):
    from tests.game_helpers import act

    s, hag, red, blue = setup(cards)
    act(s, "p1", type="counter", card_ids=[red.id], kind="+1/+1", delta=2)
    activate(s, red, "deals 1 damage", [hag.id])
    cast(s, "Murder", [hag.id], pid="p2")
    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(red).pt == (2, 4) and plan.ch(blue).pt == (1, 1)
    roundtrip(s)


def test_brine_prevented_damage_does_not_create_damager(cards):
    s, hag, red, blue = setup(cards)
    # The normal fixture includes the real printed modal Healing Salve.
    cast(s, "Healing Salve", [hag.id], pid="p2", modes=[1])
    activate(s, red, "deals 1 damage", [hag.id])
    assert hag.damage == 0
    cast(s, "Murder", [hag.id], pid="p2")
    assert Plan(s.state, "p1", cards, None).ch(red).pt == (1, 1)
    roundtrip(s)


def test_brine_new_recipient_incarnation_has_no_old_damagers(cards):
    s, hag, red, blue = setup(cards)
    activate(s, red, "deals 1 damage", [hag.id])
    cast(s, "Cloudshift", [hag.id], pid="p2")
    assert hag.damage == 0
    cast(s, "Murder", [hag.id], pid="p2")
    assert Plan(s.state, "p1", cards, None).ch(red).pt == (1, 1)
    roundtrip(s)


def test_brine_native_damage_history_survives_genuine_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    from tests.game_helpers import act

    s, hag, red, blue = setup(cards)
    activate(s, red, "deals 1 damage", [hag.id])
    act(s, "p2", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    cast(s, "Murder", [hag.id], pid="p2", resolve=False)
    for _ in range(12):
        if hag.zone == "p2:graveyard":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert hag.zone == "p2:graveyard" and Plan(s.state, "p1", cards, None).ch(red).pt == (1, 1)
    saved = tmp_path / "brine46.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
plan=Plan(s.state,'p1',repo,None)
assert plan.ch(s.state.cards[sys.argv[3]]).pt==(0,2)
assert plan.ch(s.state.cards[sys.argv[4]]).pt==(1,1)
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), red.id, blue.id],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
