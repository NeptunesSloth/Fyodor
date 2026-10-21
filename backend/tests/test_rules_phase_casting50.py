"""CR506.8: exact combat-calendar restrictions; Wake the Dead whole-card play."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.state import PHASES
from app.rules import cast_timing, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards(settings):
    data = json.loads((Path(__file__).parent / "fixtures/phase_casting50_cards.json").read_text())
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(data):
        base[c["name"]] = card(
            c["name"], set_code="pct", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize(
    "clause,phases,whose,first",
    [
        ("during combat on your turn", set(PHASES[4:9]), "you", False),
        ("during combat on an opponent's turn", set(PHASES[4:9]), "opponent", False),
        ("during the declare blockers step on an opponent's turn", {"declare_blockers"}, "opponent", False),
        ("during your declare attackers step", {"declare_attackers"}, "you", False),
        (
            "during combat on your turn before blockers are declared",
            {"begin_combat", "declare_attackers"},
            "you",
            False,
        ),
        ("during an opponent's turn, before attackers are declared", set(PHASES[:5]), "opponent", True),
    ],
)
def test_exact_calendar_native_restriction_kernel(cards, clause, phases, whose, first):
    from app.rules import restrictions

    s = table(cards, ["Wake the Dead"])
    source = put(s, "Wake the Dead", "hand")
    definition = cast_timing.definition("Cast this spell only " + clause + ".")
    assert definition is not None
    predicate = definition["restrictions"]
    for active in ("p1", "p2", "p3"):
        for phase in PHASES:
            for combats in (0, 1, 2):
                s.state.turn.active_player = active
                s.state.turn.phase = phase
                s.state.rules.combats = combats
                expected = phase in phases and ((active == "p1") == (whose == "you"))
                if (
                    first
                    and phase
                    in {
                        "begin_combat",
                        "declare_attackers",
                        "declare_blockers",
                        "combat_damage",
                        "end_combat",
                    }
                    and combats > 1
                ):
                    expected = False
                assert (
                    restrictions.problem(s.state, "p1", source, 0, predicate, Plan.view(s.state, "p1", cards))
                    is None
                ) == expected, (clause, active, phase, combats)


def setup_wake(cards):
    s = table(cards, ["Wake the Dead", "Grizzly Bears", "Llanowar Elves"])
    source = put(s, "Wake the Dead", "hand")
    targets = [put(s, n, "graveyard") for n in ("Grizzly Bears", "Llanowar Elves")]
    return s, source, targets


def cast_wake(s, source, targets):
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2, "C": len(targets)})
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=source.id,
        x_value=len(targets),
        target_counts=[len(targets)],
        targets=[c.id for c in targets],
    )


def test_wake_whole_card_opponent_combat_and_delayed_sacrifice(cards):
    assert coverage.of_card_data(cards.resolve("Wake the Dead")).level == "FULL"
    s, source, targets = setup_wake(cards)
    to_phase(s, "begin_combat", 2)
    cast_wake(s, source, targets)
    settle(s)
    assert all(s.state.cards[c.id].zone == "p1:battlefield" for c in targets)
    roundtrip(s)
    to_phase(s, "end", 2)
    settle(s)
    assert all(s.state.cards[c.id].zone == "p1:graveyard" for c in targets)
    roundtrip(s)


@pytest.mark.parametrize("phase,turn", [("main1", 2), ("main2", 2), ("begin_combat", 4)])
def test_wake_refuses_outside_opponents_combat_atomically(cards, phase, turn):
    s, source, targets = setup_wake(cards)
    to_phase(s, phase, turn)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2, "C": 2})
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="cast_spell",
            card_id=source.id,
            x_value=2,
            target_counts=[2],
            targets=[c.id for c in targets],
        )
    assert s.state.model_dump(mode="json") == before


def test_real_extra_combats_allow_wake_but_first_combat_clause_refuses(cards):
    s = table(cards, ["Wake the Dead", "Grizzly Bears", "Siren's Call"], ["Full Throttle"])
    source = put(s, "Wake the Dead", "hand")
    siren = put(s, "Siren's Call", "hand")
    bear = put(s, "Grizzly Bears", "graveyard")
    throttle = put(s, "Full Throttle", "hand", "p2")
    to_phase(s, "main1", 2)
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 4, "R": 2})
    act(s, "p2", type="cast_spell", card_id=throttle.id)
    settle(s)
    to_phase(s, "begin_combat", 2)
    view = Plan.view(s.state, "p1", cards)
    assert cast_timing.problem(s.state, "p1", siren, view.ch(siren), cards) is None
    to_phase(s, "end_combat", 2)
    to_phase(s, "begin_combat", 2)
    assert s.state.rules.combats == 2
    view = Plan.view(s.state, "p1", cards)
    assert cast_timing.problem(s.state, "p1", siren, view.ch(siren), cards) is not None
    cast_wake(s, source, [bear])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    roundtrip(s)


def test_wake_lost_target_and_new_incarnation_not_sacrificed(cards):
    s, source, targets = setup_wake(cards)
    to_phase(s, "begin_combat", 2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    cast_wake(s, source, targets)
    act(s, "p1", type="move", card_ids=[targets[1].id], to={"player": "p1", "zone": "exile"})
    settle(s)
    assert s.state.cards[targets[0].id].zone == "p1:battlefield"
    assert s.state.cards[targets[1].id].zone == "p1:exile"
    act(s, "p1", type="move", card_ids=[targets[0].id], to={"player": "p1", "zone": "exile"})
    act(s, "p1", type="move", card_ids=[targets[0].id], to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "end", 2)
    settle(s)
    assert s.state.cards[targets[0].id].zone == "p1:battlefield"
    roundtrip(s)


def test_wake_zero_targets_is_legal(cards):
    s, source, _ = setup_wake(cards)
    to_phase(s, "begin_combat", 2)
    cast_wake(s, source, [])
    settle(s)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


def fresh_action(s, cards, path, actor, payload):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code = """
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(path.parent/'cold-images'))
s=GameSession(GameState.model_validate_json(path.read_text()),cards=repo)
s.perform(sys.argv[3],json.loads(sys.argv[4]))
for _ in range(60):
 d=s.state.rules.decision
 if d is not None:break
 if not s.state.zones.get('stack'):break
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


def test_wake_cold_cast_and_saved_delayed_sacrifice(cards, tmp_path):
    s, source, targets = setup_wake(cards)
    to_phase(s, "begin_combat", 2)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2, "C": 2})
    s = fresh_action(
        s,
        cards,
        tmp_path / "cast.json",
        "p1",
        {
            "type": "cast_spell",
            "card_id": source.id,
            "x_value": 2,
            "target_counts": [2],
            "targets": [c.id for c in targets],
        },
    )
    assert all(s.state.cards[c.id].zone == "p1:battlefield" for c in targets)
    to_phase(s, "end", 2)
    s = fresh_action(s, cards, tmp_path / "end.json", s.state.rules.priority, {"type": "pass_priority"})
    settle(s)
    assert all(s.state.cards[c.id].zone == "p1:graveyard" for c in targets)
    roundtrip(s)


@pytest.mark.parametrize("turn,legal", [(2, True), (4, False)])
def test_effect_cast_respects_calendar_even_when_resolution_grants_cast(cards, turn, legal):
    s = table(cards, ["Wake the Dead", "Torrential Gearhulk"])
    source = put(s, "Wake the Dead", "graveyard")
    gear = put(s, "Torrential Gearhulk", "hand")
    to_phase(s, "begin_combat", turn)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2, "C": 4})
    act(s, "p1", type="cast_spell", card_id=gear.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None, s.state.rules.model_dump()
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[source.id])
    settle(s)
    d = s.state.rules.decision
    if legal:
        assert d is not None and d.resume["step"] == "free_cast_pick"
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[source.id])
        settle(s)
    else:
        assert d is None
    assert s.state.cards[source.id].zone == ("p1:exile" if legal else "p1:graveyard")
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    roundtrip(s)


def setup_savage(cards):
    s = table(cards, ["Savage Beating", "Grizzly Bears", "Llanowar Elves"])
    source = put(s, "Savage Beating", "hand")
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield")
    to_phase(s, "declare_attackers", 4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    wait_priority(s, "p1")
    act(s, "p1", type="tap", card_ids=[elf.id], tapped=True)
    return s, source, bear, elf


@pytest.mark.parametrize("modes,kicker", [([0], 0), ([1], 0), ([0, 1], 1)])
def test_savage_whole_modes_entwine_and_extra_combat(cards, modes, kicker):
    assert coverage.of_card_data(cards.resolve("Savage Beating")).level == "FULL"
    s, source, bear, elf = setup_savage(cards)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 4 if kicker else 3, "R": 3 if kicker else 2})
    act(s, "p1", type="cast_spell", card_id=source.id, modes=modes, kicker=kicker)
    settle(s)
    assert ("double strike" in Plan.view(s.state, "p1", cards).ch(s.state.cards[bear.id]).keywords) == (
        0 in modes
    )
    assert s.state.cards[bear.id].tapped == (1 not in modes)
    assert s.state.cards[elf.id].tapped == (1 not in modes)
    to_phase(s, "end_combat", 4)
    assert s.state.players["p2"].life == (36 if 0 in modes else 38)
    if 1 in modes:
        to_phase(s, "begin_combat", 4)
        assert s.state.rules.combats == 2
    roundtrip(s)


@pytest.mark.parametrize("phase,turn", [("main1", 4), ("begin_combat", 2)])
def test_savage_calendar_refuses_wrong_turn_or_main_phase(cards, phase, turn):
    s = table(cards, ["Savage Beating"])
    source = put(s, "Savage Beating", "hand")
    to_phase(s, phase, turn)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "R": 2})
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, modes=[0])
    assert s.state.model_dump(mode="json") == before


def test_savage_entwine_cold_cast_adds_real_extra_combat(cards, tmp_path):
    s, source, bear, elf = setup_savage(cards)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 4, "R": 3})
    s = fresh_action(
        s,
        cards,
        tmp_path / "savage.json",
        "p1",
        {"type": "cast_spell", "card_id": source.id, "modes": [0, 1], "kicker": 1},
    )
    assert "double strike" in Plan.view(s.state, "p1", cards).ch(s.state.cards[bear.id]).keywords
    assert not s.state.cards[bear.id].tapped and not s.state.cards[elf.id].tapped
    to_phase(s, "end_combat", 4)
    to_phase(s, "begin_combat", 4)
    assert s.state.rules.combats == 2 and s.state.players["p2"].life == 36
    roundtrip(s)


def test_wake_delayed_sacrifice_does_not_retry_after_control_loss(cards):
    s, source, targets = setup_wake(cards)
    to_phase(s, "begin_combat", 2)
    cast_wake(s, source, [targets[0]])
    settle(s)
    act(s, "p1", type="set_controller", card_ids=[targets[0].id], player="p2")
    to_phase(s, "end", 2)
    settle(s)
    assert s.state.cards[targets[0].id].zone == "p2:battlefield"
    act(s, "p2", type="set_controller", card_ids=[targets[0].id], player="p1")
    to_phase(s, "end", 3)
    settle(s)
    assert s.state.cards[targets[0].id].zone == "p1:battlefield"
    roundtrip(s)


def test_resolving_cast_kernel_rechecks_card_restriction_before_costs(cards):
    """Isolated defensive entry-point proof, distinct from native Gearhulk gameplay."""
    from app.game.actions import CastSpell
    from app.rules import casting

    s, source, _ = setup_wake(cards)
    to_phase(s, "begin_combat", 4)
    s.state.rules.free_casts.append(source.id)
    plan = Plan(s.state, "p1", cards, None)
    with pytest.raises(ActionError, match="opponent's turn"):
        casting.cast_free(plan, source, plan.ch(source), CastSpell(card_id=source.id, free=True))
