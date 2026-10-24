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
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads(
    (Path(__file__).parent / "fixtures/phase_skips88_cards.json").read_text()
)
NAMES = [c["name"] for c in DATA[:4]]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"],
            set_code="s88",
            number=str(i),
            **{k: v for k, v in c.items() if k != "name"},
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup88(cards):
    names = [
        *NAMES,
        "Full Throttle",
        "Fatigue",
        "Grizzly Bears",
        "Forest",
        "Swords to Plowshares",
    ]
    s = table(cards, names, names, names)
    start(s)
    return s


def cast88(s, name, target):
    c = put(s, name, "hand")
    mana(s, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target])
    settle(s)
    assert s.state.cards[c.id].zone == "p1:graveyard"


def walk88(s, turn):
    seen = []
    for _ in range(150):
        seen.append((s.state.turn.number, s.state.turn.phase))
        if s.state.turn.number > turn:
            return seen
        d = s.state.rules.decision
        if d:
            act(
                s,
                d.player,
                type="choose",
                decision_id=d.id,
                option_ids=[d.options[0].id],
            )
        elif s.state.rules.priority:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            raise AssertionError("no priority")
    raise AssertionError("walk exceeded")


@pytest.mark.parametrize("name", NAMES)
def test_whole88(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", ["Empty City Ruse", "False Peace"])
def test_all_combat_next_target_turn_and_expiry88(cards, name):
    s = setup88(cards)
    cast88(s, name, "p2")
    seen = walk88(s, 5)
    assert (4, "begin_combat") in seen
    assert (
        (5, "begin_combat") not in seen
        and (5, "main1") in seen
        and (5, "main2") in seen
    )
    to_phase(s, "begin_combat", turn=8)
    assert s.state.turn.active_player == "p2"


@pytest.mark.parametrize("target", ["p1", "p2"])
def test_moment_only_current_turn_next_combat88(cards, target):
    s = setup88(cards)
    cast88(s, "Moment of Silence", target)
    seen = walk88(s, 5)
    assert ((4, "begin_combat") in seen) == (target != "p1")
    assert (5, "begin_combat") in seen


@pytest.mark.parametrize("choice", ["draw", "main", "combat"])
def test_fatespinner_opponent_chooses_each_instance88(cards, choice):
    s = setup88(cards)
    c = put(s, "Fatespinner", "hand")
    mana(s, C=1, U=2)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    to_phase(s, "upkeep", turn=5)
    for _ in range(30):
        d = s.state.rules.decision
        if d:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert (
        d
        and d.player == "p2"
        and {o.id for o in d.options} == {"draw", "main", "combat"}
    )
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[choice])
    settle(s)
    seen = walk88(s, 5)
    for phase in ["draw", "main1", "begin_combat", "main2"]:
        skipped = (
            phase == "draw"
            if choice == "draw"
            else phase.startswith("main")
            if choice == "main"
            else phase == "begin_combat"
        )
        assert ((5, phase) in seen) != skipped, (choice, phase, seen)


@pytest.mark.parametrize("effect", ["False Peace", "Moment of Silence", "Fatespinner"])
def test_dynamically_added_combats_all_or_only_next88(cards, effect):
    s = setup88(cards)
    if effect == "False Peace":
        cast88(s, effect, "p2")
    if effect == "Fatespinner":
        put(s, "Fatespinner", "battlefield")
        to_phase(s, "upkeep", turn=5)
        for _ in range(30):
            d = s.state.rules.decision
            if d:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert d and d.player == "p2"
        act(s, "p2", type="choose", decision_id=d.id, option_ids=["combat"])
        settle(s)
    to_phase(s, "main1", turn=5)
    if effect == "Moment of Silence":
        cast88(s, effect, "p2")
    c = put(s, "Full Throttle", "hand", pid="p2")
    mana(s, pid="p2", C=4, R=2)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=c.id)
    settle(s)
    assert s.state.rules.extra_phases
    seen = walk88(s, 5)
    combats = [phase for turn, phase in seen if turn == 5 and phase == "begin_combat"]
    assert bool(combats) == (effect == "Moment of Silence"), seen
    assert not s.state.rules.extra_phases


@pytest.mark.parametrize("mode", ["False Peace", "Moment of Silence", "Fatespinner"])
def test_genuine_cold_turn_scoped_skips88(cards, tmp_path, mode):
    import subprocess
    import sys

    import app

    s = setup88(cards)
    if mode == "Fatespinner":
        put(s, mode, "battlefield")
        to_phase(s, "upkeep", turn=5)
        for _ in range(30):
            if s.state.rules.decision:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert s.state.rules.decision and s.state.rules.decision.player == "p2"
    else:
        cast88(s, mode, "p2" if mode == "False Peace" else "p1")
    saved = tmp_path / "cold88.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
mode=sys.argv[3]
if mode=='Fatespinner':
 d=s.state.rules.decision
 assert d.player=='p2'
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['main'])
seen=[]
for _ in range(150):
 seen.append((s.state.turn.number,s.state.turn.phase))
 if s.state.turn.number>5:break
 d=s.state.rules.decision
 if d:act(s,d.player,type='choose',decision_id=d.id,option_ids=[d.options[0].id])
 else:act(s,s.state.rules.priority,type='pass_priority')
else:raise AssertionError('cold walk exceeded')
if mode=='Fatespinner':assert (5,'main1') not in seen and (5,'main2') not in seen and (5,'begin_combat') in seen
elif mode=='False Peace':assert (4,'begin_combat') in seen and (5,'begin_combat') not in seen
else:assert (4,'begin_combat') not in seen and (5,'begin_combat') in seen
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), mode],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_moment_after_combat_started_cannot_remove_it88(cards):
    s = setup88(cards)
    to_phase(s, "begin_combat", turn=4)
    cast88(s, "Moment of Silence", "p1")
    assert s.state.turn.phase == "begin_combat"
    seen = walk88(s, 5)
    assert (4, "declare_attackers") in seen and (5, "begin_combat") in seen


def test_all_instance_skip_preserves_waiting_next_occurrence88(cards):
    s = setup88(cards)
    c = put(s, "Fatigue", "hand")
    mana(s, C=1, U=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    settle(s)
    put(s, "Fatespinner", "battlefield")
    to_phase(s, "upkeep", turn=5)
    for _ in range(30):
        d = s.state.rules.decision
        if d:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d and d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["draw"])
    settle(s)
    walk88(s, 5)
    pending = [
        rec
        for rec in s.state.rules.skips
        if rec["player"] == "p2" and rec["what"] == "draw" and not rec.get("repeat88")
    ]
    assert len(pending) == 1 and pending[0]["label"] == "Fatigue"
