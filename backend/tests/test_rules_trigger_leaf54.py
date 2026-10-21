"""Native optional attack-mill target and entering-land controller binding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_trigger_leaf53 import spell
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/trigger_leaf54_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="tlf", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Cultivator of Blades", "Arbiter of Knollridge"])
def test_full_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def setup_cultivator(cards, mode="servos"):
    names = [
        "Cultivator of Blades",
        "Llanowar Elves",
        "Grizzly Bears",
        "Giant Growth",
        "Disfigure",
        "Cloudshift",
        "Stifle",
        "Beast Within",
    ]
    s = table(cards, names, names, names)
    source = put(s, "Cultivator of Blades", "hand")
    to_phase(s, "main1", 1)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "G": 2})
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    if mode is None:
        return s, source
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[mode])
    settle(s)
    return s, source


def test_cultivator_cast_fabricate(cards):
    s, source = setup_cultivator(cards)


def pt(s, c):
    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c.id]).pt


def choose(s, option):
    if s.state.rules.decision is None:
        settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])
    settle(s)


def attack_cultivator(cards, mode="servos"):
    s, source = setup_cultivator(cards, mode)
    ally = put(s, "Llanowar Elves", "battlefield")
    idle = put(s, "Grizzly Bears", "battlefield")
    to_phase(s, "declare_attackers", 4)
    attack(s, (source, "p2"), (ally, "p3"))
    return s, source, ally, idle


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_cultivator_optional_other_attackers(cards, answer):
    s, source, ally, idle = attack_cultivator(cards)
    choose(s, answer)
    assert pt(s, source) == (1, 1) and pt(s, idle) == (2, 2)
    assert pt(s, ally) == ((2, 2) if answer == "yes" else (1, 1))
    to_phase(s, "main1", 5)
    assert pt(s, ally) == (1, 1)
    roundtrip(s)


@pytest.mark.parametrize("mode", ["counters", "servos"])
def test_cultivator_whole_fabricate_choices(cards, mode):
    s, source = setup_cultivator(cards, mode)
    assert pt(s, source) == ((3, 3) if mode == "counters" else (1, 1))
    servos = [
        c for c in s.state.cards.values() if c.token and c.name == "Servo" and c.zone.endswith(":battlefield")
    ]
    assert len(servos) == (0 if mode == "counters" else 2)
    roundtrip(s)


@pytest.mark.parametrize("change", ["pump", "negative", "blink"])
def test_cultivator_resolution_power_lki_and_negative_zero(cards, change):
    s, source, ally, idle = attack_cultivator(cards)
    if change == "blink":
        growth = put(s, "Giant Growth", "hand")
        wait_priority(s, "p1")
        act(s, "p1", type="set_prefs", hold_priority=True)
        act(s, "p1", type="add_mana", player="p1", mana={"G": 1})
        act(s, "p1", type="cast_spell", card_id=growth.id, targets=[source.id])
        for _ in range(20):
            if s.state.cards[growth.id].zone == "p1:graveyard":
                break
            act(s, s.state.rules.priority, type="pass_priority")
        spell(s, "Cloudshift", source.id)
        # The new incarnation has its separate native fabricate decision first.
        choose(s, "servos")
    else:
        spell(s, "Disfigure" if change == "negative" else "Giant Growth", source.id)
    choose(s, "yes")
    assert pt(s, ally) == ((1, 1) if change == "negative" else (5, 5))
    roundtrip(s)


def arbiter_cast(cards, extras=(), lives=(5, 12, 20)):
    names = [
        "Arbiter of Knollridge",
        "Stifle",
        "Beast Within",
        "Platinum Angel",
        "Alhammarret's Archive",
        "Platinum Emperion",
        "Sulfuric Vortex",
        "Cleric Class",
    ]
    s = table(cards, names, names, names)
    for name, pid in extras:
        put(s, name, "battlefield", pid)
    for pid, n in zip(("p1", "p2", "p3"), lives, strict=True):
        act(s, "p1", type="set_life", player=pid, value=n)
    source = put(s, "Arbiter of Knollridge", "hand")
    to_phase(s, "main1", 1)
    wait_priority(s, "p1")
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 6, "W": 1})
    act(s, "p1", type="cast_spell", card_id=source.id)
    for _ in range(20):
        if s.state.cards[source.id].zone == "p1:battlefield":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[source.id].zone == "p1:battlefield" and s.state.zones["stack"]
    return s, source


def life(s):
    return [s.state.players[p].life for p in ("p1", "p2", "p3")]


@pytest.mark.parametrize(
    "extras,expected",
    [
        ([], [20, 20, 20]),
        ([("Alhammarret's Archive", "p1"), ("Alhammarret's Archive", "p2")], [35, 28, 20]),
        ([("Platinum Emperion", "p1")], [5, 20, 20]),
        ([("Sulfuric Vortex", "p2")], [5, 12, 20]),
    ],
)
def test_arbiter_freezes_highest_before_atomic_replacements_prohibitions(cards, extras, expected):
    s, source = arbiter_cast(cards, extras)
    settle(s)
    assert life(s) == expected
    roundtrip(s)


@pytest.mark.parametrize("lives", [(30, 10, 20), (10, 30, 20), (10, 20, 30), (20, 20, 20)])
def test_arbiter_highest_any_seat_and_ties(cards, lives):
    s, source = arbiter_cast(cards, lives=lives)
    settle(s)
    assert life(s) == [max(lives)] * 3
    roundtrip(s)


@pytest.mark.parametrize("lives", [(-1, -2, -3), (-3, -1, -2)])
def test_arbiter_signed_negative_highest_with_native_cannot_lose(cards, lives):
    s, source = arbiter_cast(cards, [("Platinum Angel", p) for p in ("p1", "p2", "p3")], lives)
    settle(s)
    assert life(s) == [max(lives)] * 3
    roundtrip(s)


@pytest.mark.parametrize("change", ["source_gone", "countered"])
def test_arbiter_trigger_original_source_death_or_stifle(cards, change):
    s, source = arbiter_cast(cards)
    if change == "source_gone":
        spell(s, "Beast Within", source.id)
        assert s.state.cards[source.id].zone == "p1:graveyard" and life(s) == [20, 20, 20]
    else:
        spell(s, "Stifle", s.state.zones["stack"][-1])
        assert life(s) == [5, 12, 20]
    roundtrip(s)


def fresh(s, cards, path, actor, payload):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code = """
import json,os,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
if os.environ.get('FYODOR_TRIGGERLEAF54_STAGE'):
 from fyodor_triggerleaf54_plugin import install
 install()
path=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(path.parent/'cold-images'))
s=GameSession(GameState.model_validate_json(path.read_text()),cards=repo)
s.perform(sys.argv[3],json.loads(sys.argv[4]))
for _ in range(80):
 if s.state.rules.decision or not s.state.zones.get('stack'):break
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
path.write_text(s.state.model_dump_json());repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), str(cards.db_path), actor, json.dumps(payload)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()), cards=cards)


def test_cultivator_blinked_other_attacker_excluded_from_resolution_group(cards):
    s, source, ally, idle = attack_cultivator(cards)
    spell(s, "Cloudshift", ally.id)
    choose(s, "yes")
    assert pt(s, ally) == (1, 1) and not s.state.cards[ally.id].is_attacking
    roundtrip(s)


def test_cultivator_countered_attack_trigger_no_bonus(cards):
    s, source, ally, idle = attack_cultivator(cards)
    spell(s, "Stifle", s.state.zones["stack"][-1])
    assert pt(s, ally) == (1, 1)
    roundtrip(s)


def test_cultivator_cold_optional_choice_power_and_cleanup(cards, tmp_path):
    s, source, ally, idle = attack_cultivator(cards, "counters")
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    s = fresh(
        s,
        cards,
        tmp_path / "cultivator.json",
        d.player,
        {"type": "choose", "decision_id": d.id, "option_ids": ["yes"]},
    )
    assert pt(s, ally) == (4, 4) and pt(s, source) == (3, 3)
    to_phase(s, "main1", 5)
    assert pt(s, ally) == (1, 1)
    roundtrip(s)


def test_arbiter_cold_pending_highest_and_archive(cards, tmp_path):
    s, source = arbiter_cast(cards, [("Alhammarret's Archive", "p1"), ("Alhammarret's Archive", "p2")])
    s = fresh(s, cards, tmp_path / "arbiter.json", s.state.rules.priority, {"type": "pass_priority"})
    assert life(s) == [35, 28, 20]
    roundtrip(s)


def test_arbiter_native_replacement_choice_then_cold_frozen_request(cards, tmp_path):
    s, source = arbiter_cast(cards, [("Alhammarret's Archive", "p1"), ("Cleric Class", "p1")])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    option = d.options[0].id
    s = fresh(
        s,
        cards,
        tmp_path / "arbiter-choice.json",
        d.player,
        {"type": "choose", "decision_id": d.id, "option_ids": [option]},
    )
    settle(s)
    assert life(s)[1:] == [20, 20] and life(s)[0] in (36, 37)
    roundtrip(s)


def test_cultivator_controller_frozen_despite_source_control_change(cards):
    s, source, ally, idle = attack_cultivator(cards)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    choose(s, "yes")
    assert pt(s, ally) == (2, 2) and s.state.cards[source.id].controller == "p2"
    roundtrip(s)
