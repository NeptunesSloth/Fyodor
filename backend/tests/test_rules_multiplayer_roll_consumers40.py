"""Actual multiplayer roll actors, kept pairs, and untargeted roll reflexives."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import combat, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until_asked
from tests.test_rules_declaration_requirements33 import cast
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_random_consequences import faces
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import stops, three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / "fixtures/multiplayer_roll_consumers40_cards.json"


@pytest.fixture()
def cards(settings):
    from tests.test_rules_wave24b_dice import EXTRA

    existing = {c["name"]: c for c in [*fixture_cards(), *EXTRA]}
    for i, c in enumerate(json.loads(DATA.read_text())):
        existing[c["name"]] = card(
            c["name"],
            set_code="mr40",
            number=str(i),
            **{k: v for k, v in c.items() if k not in ("name", "set_code")},
        )
    settings.ensure_dirs()
    build_database(existing.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c["name"] for c in json.loads(DATA.read_text())] + [
        "Grizzly Bears",
        "Sol Ring",
        "Lightning Bolt",
    ]
    s = three(cards, names, names, names)
    hold(s)
    stops(s, "main1", "begin_combat", "declare_attackers", "declare_blockers", "end_combat", "main2")
    to_phase(s, "main1", turn=4)
    return s


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def begin(s):
    to_phase(s, "begin_combat", turn=4)
    assert s.state.zones.get("stack")
    settle(s)


@pytest.mark.parametrize("name", ["Chaos Dragon", "Celebr-8000", "Slight Malfunction"])
def test_canonical_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(
    "results,forbidden", [([20, 20, 1], {"p2"}), ([1, 20, 20], {"p2", "p3"}), ([20, 1, 1], set())]
)
def test_chaos_actual_all_players_highest_including_controller(cards, monkeypatch, results, forbidden):
    s = setup(cards)
    dragon = put(s, "Chaos Dragon", "battlefield")
    faces(monkeypatch, results)
    begin(s)
    assert {p: s.state.rules.turn_log.rolled.get(p, 0) for p in s.state.players} == {
        "p1": 1,
        "p2": 1,
        "p3": 1,
    }
    plan = Plan(s.state, "p1", s.cards, None)
    assert {p for p in ["p2", "p3"] if combat.attack_forbidden(plan, ch(s, dragon), p)} == forbidden
    assert "must_attack" in ch(s, dragon).imposed
    roundtrip(s)


def test_chaos_player_specific_extra_die_and_planeswalker_current_controller(cards, monkeypatch):
    s = setup(cards)
    dragon = put(s, "Chaos Dragon", "battlefield")
    put(s, "Pixie Guide", "battlefield", pid="p2")
    walker = cast(s, "Kaito, Bane of Nightmares")
    act(s, "p1", type="set_controller", card_ids=[walker.id], player="p2")
    faces(monkeypatch, [15, 1, 20, 2])
    begin(s)
    plan = Plan(s.state, "p1", s.cards, None)
    assert combat.attack_forbidden(plan, ch(s, dragon), "p2") and combat.attack_forbidden(
        plan, ch(s, dragon), walker.id
    )
    assert s.state.rules.turn_log.rolled == {"p1": 1, "p2": 1, "p3": 1}
    act(s, "p1", type="set_controller", card_ids=[walker.id], player="p3")
    assert not combat.attack_forbidden(Plan(s.state, "p1", s.cards, None), ch(s, dragon), walker.id)
    roundtrip(s)


@pytest.mark.parametrize(
    "results,pump,keywords",
    [
        ([1, 1], 2, {"double strike"}),
        ([2, 3], 0, {"menace", "vigilance"}),
        ([4, 5], 0, {"lifelink", "flying"}),
        ([6, 6], 0, {"indestructible", "double strike"}),
    ],
)
def test_celebr_actual_pair_all_rows_and_doubles(cards, monkeypatch, results, pump, keywords):
    s = setup(cards)
    source = put(s, "Celebr-8000", "battlefield")
    base = ch(s, source).pt
    faces(monkeypatch, results)
    begin(s)
    assert ch(s, source).pt == (base[0] + pump, base[1] + pump)
    assert ch(s, source).keywords == keywords
    roundtrip(s)


def slight_pending(s, monkeypatch, result=2):
    to_phase(s, "main1", turn=4)
    faces(monkeypatch, [result])
    source = spell(s, "Slight Malfunction", {"C": 1, "R": 1}, finish=False, modes=[1])
    original = s.state.rules.stack[source.id]
    assert not original.targets and not original.groups
    return source, until_asked(s)


def test_slight_mode_two_targets_only_reflexive_and_simultaneous_damage(cards, monkeypatch):
    s = setup(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Grizzly Bears", "battlefield", pid="p2")
    source, d = slight_pending(s, monkeypatch)
    assert d.kind == "choose_cards" and d.max_choices == 2 and source.id not in s.state.zones["stack"]
    roundtrip(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id, b.id])
    settle(s)
    assert s.state.cards[a.id].damage == 1 and s.state.cards[b.id].damage == 1
    roundtrip(s)


def test_slight_mode_one_still_destroys_artifact_without_roll(cards, monkeypatch):
    s = setup(cards)
    target = put(s, "Sol Ring", "battlefield", pid="p2")
    to_phase(s, "main1", turn=4)
    faces(monkeypatch, [])
    spell(s, "Slight Malfunction", {"C": 1, "R": 1}, target=[target.id], modes=[0])
    assert s.state.cards[target.id].zone == "p2:graveyard"
    roundtrip(s)


def test_chaos_native_declaration_rejects_highest_and_requires_other_opponent(cards, monkeypatch):
    s = setup(cards)
    dragon = put(s, "Chaos Dragon", "battlefield")
    faces(monkeypatch, [10, 20, 1])
    begin(s)
    to_phase(s, "declare_attackers", turn=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": dragon.id, "target": "p2"}])
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": dragon.id, "target": "p3"}])
    to_phase(s, "main2", turn=4)
    assert not any(rule.startswith("cant_attack_player") for rule in ch(s, dragon).imposed)
    roundtrip(s)


@pytest.mark.parametrize("name,results", [("Chaos Dragon", [10, 20, 1]), ("Celebr-8000", [6, 6])])
def test_pending_trigger_rolls_but_never_grants_to_new_incarnation(cards, monkeypatch, name, results):
    s = setup(cards)
    source = put(s, name, "battlefield")
    faces(monkeypatch, results)
    to_phase(s, "begin_combat", turn=4)
    assert s.state.zones.get("stack")
    old = s.state.rules.object_id(source.id)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "battlefield"})
    assert s.state.rules.object_id(source.id) != old
    settle(s)
    assert not any(rule.startswith("cant_attack_player") for rule in ch(s, source).imposed)
    assert not ({"indestructible", "double strike"} & ch(s, source).keywords)
    assert s.state.rules.turn_log.rolled["p1"] == (1 if name == "Chaos Dragon" else 2)
    roundtrip(s)


def test_celebr_ignored_lowest_not_counted_and_cleanup_expires(cards, monkeypatch):
    s = setup(cards)
    source = put(s, "Celebr-8000", "battlefield")
    put(s, "Pixie Guide", "battlefield")
    base = ch(s, source).pt
    faces(monkeypatch, [1, 2, 6])
    begin(s)
    assert ch(s, source).pt == base and ch(s, source).keywords == {"menace", "indestructible"}
    to_phase(s, "main1", turn=5)
    assert not ch(s, source).keywords
    roundtrip(s)


def test_celebr_modified_doubles_above_six_gain_only_double_strike(cards, monkeypatch):
    from app.rules import dice, effects

    original = dice.roll

    def modified(plan, ctx, e):
        return original(plan, ctx, {**e, "mod": {"op": "+", "v": 1}})

    monkeypatch.setitem(effects.PRIMITIVES, "roll", modified)
    s = setup(cards)
    source = put(s, "Celebr-8000", "battlefield")
    base = ch(s, source).pt
    faces(monkeypatch, [6, 6])
    begin(s)
    assert ch(s, source).pt == base and ch(s, source).keywords == {"double strike"}
    roundtrip(s)


def test_slight_reflexive_can_choose_zero_and_cannot_exceed_roll(cards, monkeypatch):
    s = setup(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Grizzly Bears", "battlefield", pid="p2")
    _, d = slight_pending(s, monkeypatch, result=1)
    with pytest.raises(ActionError):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id, b.id])
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[a.id].damage == s.state.cards[b.id].damage == 0
    roundtrip(s)


def test_slight_reflexive_is_counterable_after_target_selection(cards, monkeypatch):
    s = setup(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    _, d = slight_pending(s, monkeypatch, result=1)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id])
    stack_id = next(iter(s.state.rules.stack))
    spell(s, "Stifle", {"U": 1}, target=[stack_id])
    assert s.state.cards[a.id].damage == 0 and not s.state.rules.stack
    roundtrip(s)


def test_slight_modified_zero_still_creates_zero_target_reflexive(cards, monkeypatch):
    from app.rules import dice, effects

    original = dice.roll

    def modified(plan, ctx, e):
        return original(plan, ctx, {**e, "mod": {"op": "-", "v": 1}})

    monkeypatch.setitem(effects.PRIMITIVES, "roll", modified)
    s = setup(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    faces(monkeypatch, [1])
    spell(s, "Slight Malfunction", {"C": 1, "R": 1}, finish=False, modes=[1])
    for _ in range(20):
        entries = list(s.state.rules.stack.values())
        if entries and entries[0].event and entries[0].event.kind == "reflexive":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    else:
        raise AssertionError("zero-result reflexive did not trigger")
    assert entries[0].event.amount == 0 and not entries[0].targets
    settle(s)
    assert s.state.cards[a.id].damage == 0
    roundtrip(s)


def test_chaos_saved_second_player_roll_continues_in_fresh_process(cards, monkeypatch, tmp_path):
    import subprocess
    import sys

    from app.rules import dice, effects

    original = dice.roll

    def suspend_second(plan, ctx, e):
        if ctx.get("controller") == "p2":
            chunks = dice.ROLL_CHUNKS
            dice.ROLL_CHUNKS = 0
            try:
                return original(plan, ctx, e)
            finally:
                dice.ROLL_CHUNKS = chunks
        return original(plan, ctx, e)

    monkeypatch.setitem(effects.PRIMITIVES, "roll", suspend_second)
    s = setup(cards)
    source = put(s, "Chaos Dragon", "battlefield")
    faces(monkeypatch, [15])
    begin(s)
    d = s.state.rules.decision
    assert d.resume["step"] == "roll_group_continue" and d.player == "p2"
    assert d.resume["ctx"]["chaos_results"] == {"p1": 15}
    saved = tmp_path / "chaos40.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_designations import pick,settle,roundtrip
import app.game.resolve as resolve
resolve._rng_int=lambda rng,lo,hi:20
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
pick(s,['continue']);settle(s)
ch=Plan(s.state,'p1',repo,None).ch(s.state.cards[sys.argv[3]])
assert {'cant_attack_player_pw:p2','cant_attack_player_pw:p3'}<=ch.imposed
assert s.state.rules.turn_log.rolled=={'p1':1,'p2':1,'p3':1}
roundtrip(s);repo.close()
"""
    out = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert out.returncode == 0, out.stdout + out.stderr


def test_chaos_actual_other_controller_rolls_in_apnap_order(cards, monkeypatch):
    s = setup(cards)
    source = put(s, "Chaos Dragon", "battlefield", pid="p2")
    to_phase(s, "main1", turn=5)
    faces(monkeypatch, [20, 1, 20])
    to_phase(s, "begin_combat", turn=5)
    settle(s)
    assert "cant_attack_player_pw:p1" in ch(s, source).imposed
    assert not any(rule == "cant_attack_player_pw:p3" for rule in ch(s, source).imposed)
    assert s.state.rules.turn_log.rolled == {"p2": 1, "p3": 1, "p1": 1}
    roundtrip(s)


def test_slight_actual_spell_copy_rolls_and_reflexive_survives_copy_departure(cards, monkeypatch):
    s = setup(cards)
    act(s, "p1", type="set_prefs", hold_priority=True)
    target = put(s, "Grizzly Bears", "battlefield")
    faces(monkeypatch, [2])
    source = spell(s, "Slight Malfunction", {"C": 1, "R": 1}, finish=False, modes=[1])
    spell(s, "Narset's Reversal", {"U": 2}, target=[source.id])
    assert s.state.cards[source.id].zone == "p1:hand"
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and d.max_choices == 1
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[target.id])
    assert next(iter(s.state.rules.stack.values())).event.amount == 2
    settle(s)
    assert s.state.cards[target.id].damage == 1
    roundtrip(s)


@pytest.mark.parametrize("all_illegal", [False, True])
def test_slight_reflexive_rechecks_each_target_normally(cards, monkeypatch, all_illegal):
    s = setup(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Grizzly Bears", "battlefield", pid="p2")
    _, d = slight_pending(s, monkeypatch, result=2)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id, b.id])
    act(s, "p1", type="move", card_ids=[a.id], to={"player": "p1", "zone": "hand"})
    if all_illegal:
        act(s, "p1", type="move", card_ids=[b.id], to={"player": "p2", "zone": "hand"})
    settle(s)
    assert s.state.cards[a.id].damage == 0
    assert s.state.cards[b.id].damage == (0 if all_illegal else 1)
    roundtrip(s)


def test_chaos_uses_modified_result_for_highest_comparison(cards, monkeypatch):
    from app.rules import dice, effects

    original = dice.roll

    def modified(plan, ctx, e):
        return original(plan, ctx, {**e, "mod": {"op": "+", "v": 20}} if ctx["controller"] == "p1" else e)

    monkeypatch.setitem(effects.PRIMITIVES, "roll", modified)
    s = setup(cards)
    source = put(s, "Chaos Dragon", "battlefield")
    faces(monkeypatch, [1, 20, 20])
    begin(s)
    assert not any(rule.startswith("cant_attack_player") for rule in ch(s, source).imposed)
    roundtrip(s)
