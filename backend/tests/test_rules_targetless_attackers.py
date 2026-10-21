"""CR 506.4c: an attacker whose planeswalker/battle departs still attacks no object."""

from __future__ import annotations

import pytest

from app.rules import combat, selectors
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_defender_relative36 import cards as cards
from tests.test_rules_defender_relative36 import setup
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack


def pw_setup(cards, name="Harbor Guardian"):
    s = setup(cards)
    source = put(s, name, "battlefield")
    put(s, "Vedalken Orrery", "battlefield")
    blocker = put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s, turn=2)
    pw = cast(s, "Jace Beleren", pid="p2")
    start(s)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (source, pw.id))
    return s, source, blocker, pw


def test_pw_departure_retains_attacking_and_blockability_without_defender_effect(cards):
    s, source, blocker, pw = pw_setup(cards)
    cast(s, "Boomerang", [pw.id], target_counts=[1])
    assert s.state.rules.decision is None
    current = s.state.cards[source.id]
    assert current.is_attacking and current.attacking is None
    assert current.attacking_without_target == "p2"
    assert current.attack_defender_lost
    plan = Plan(s.state, "p1", cards, None)
    assert selectors.matches(plan, selectors.Selector(attacking=True), current, plan.ch(current), "p1")
    assert source.id in [c.id for c in combat.attackers_on(s.state)]
    to_phase(s, "declare_blockers", turn=4)
    d = s.state.rules.decision
    assert d and d.player == "p2"
    assert "a:" + source.id in [o.id for o in d.options]
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": source.id}])
    to_phase(s, "combat_damage", turn=4)
    settle(s)
    assert s.state.cards[blocker.id].zone == "p2:graveyard"
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_unblocked_targetless_attacker_deals_no_player_damage_and_clears_endcombat(cards):
    s, source, _, pw = pw_setup(cards)
    cast(s, "Boomerang", [pw.id], target_counts=[1])
    to_phase(s, "combat_damage", turn=4)
    settle(s)
    assert s.state.cards[source.id].is_attacking
    assert all(p.life == 40 for p in s.state.players.values())
    to_phase(s, "main2", turn=4)
    assert not s.state.cards[source.id].is_attacking
    assert not s.state.cards[source.id].attack_defender_lost
    roundtrip(s)


def test_actual_source_removal_before_defender_loss_keeps_original_defender(cards):
    s, source, _, _ = pw_setup(cards)
    cast(s, "Boomerang", [source.id], target_counts=[1])
    d = s.state.rules.decision
    assert d and d.player == "p2"
    before = len(s.state.zones["p2:hand"])
    pick(s, ["yes"])
    settle(s)
    assert len(s.state.zones["p2:hand"]) == before + 1
    roundtrip(s)


def test_targetless_graveyard_target_remains_original_frozen_target_constraint(cards):
    # Target selection occurs before the attacked planeswalker leaves; it isn't repeated.
    s = setup(cards)
    source = put(s, "Graven Abomination", "battlefield")
    victim = put(s, "Runeclaw Bear", "graveyard", pid="p2")
    start(s, turn=2)
    pw = cast(s, "Jace Beleren", pid="p2")
    start(s)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (source, pw.id))
    pick(s, [victim.id])
    cast(s, "Boomerang", [pw.id], target_counts=[1])
    assert s.state.cards[victim.id].zone == "p2:exile"
    assert s.state.cards[source.id].is_attacking
    roundtrip(s)


def test_attacked_pw_control_change_leaves_no_defender_and_still_original_blocker_player(cards):
    s, source, _, pw = pw_setup(cards)
    cast(s, "Confiscate", [pw.id], target_counts=[1])
    assert s.state.cards[pw.id].controller == "p1"
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].attacking_without_target == "p2"
    assert s.state.cards[source.id].is_attacking
    roundtrip(s)


def test_source_control_change_is_actual_removal_and_preserves_original_trigger_defender(cards):
    s, source, _, _ = pw_setup(cards)
    cast(s, "Act of Aggression", [source.id], pid="p3", target_counts=[1], life_symbols=[])
    assert s.state.cards[source.id].controller == "p3"
    assert not s.state.cards[source.id].is_attacking
    assert s.state.rules.decision.player == "p2"
    pick(s, ["no"])
    settle(s)
    roundtrip(s)


def test_targetless_attacker_saved_with_status_resumes_blockers_cold(cards, tmp_path):
    import subprocess
    import sys

    s, source, blocker, pw = pw_setup(cards)
    cast(s, "Boomerang", [pw.id], target_counts=[1])
    to_phase(s, "declare_blockers", turn=4)
    saved = tmp_path / "targetless.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import settle,roundtrip
from tests.test_rules_wave30m_durations import to_phase
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source,blocker=sys.argv[3:5]
assert s.state.cards[source].is_attacking and s.state.cards[source].attacking is None
act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':blocker,'attacker_id':source}])
to_phase(s,'combat_damage',turn=4)
settle(s)
assert s.state.cards[blocker].zone=='p2:graveyard'
assert s.state.players['p2'].life==40
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, blocker.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_save_without_new_designations_retains_ordinary_attack_target(cards):
    from app.game.state import GameState

    s, source, _, _ = pw_setup(cards)
    raw = s.state.model_dump(mode="json")
    for c in raw["cards"].values():
        c.pop("attacking_without_target", None)
        c.pop("attack_defender_lost", None)
    loaded = GameState.model_validate(raw)
    assert loaded.cards[source.id].is_attacking
    assert loaded.cards[source.id].attacking is not None
    assert loaded.cards[source.id].attacking_without_target is None


def announce(s, name, target, pid="p1", **kw):
    spell = put(s, name, "hand", pid=pid)
    mana(s, pid=pid, W=10, U=10, B=10, R=10, G=10, C=20)
    for _ in range(8):
        if s.state.rules.priority == pid:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, pid, type="cast_spell", card_id=spell.id, targets=[target.id], target_counts=[1], **kw)


def resolve_top(s):
    before = len(s.state.zones["stack"])
    for _ in range(12):
        if len(s.state.zones["stack"]) < before:
            return
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("top spell did not resolve")


def test_target_lost_then_creature_control_removed_still_has_no_last_defender(cards):
    s, source, _, pw = pw_setup(cards)
    announce(s, "Boomerang", pw)
    resolve_top(s)
    assert s.state.cards[source.id].attack_defender_lost
    announce(s, "Act of Aggression", source, pid="p3", life_symbols=[])
    resolve_top(s)
    assert not s.state.cards[source.id].is_attacking
    assert s.state.cards[source.id].attack_defender_lost
    before = {p: len(s.state.zones[p + ":hand"]) for p in ["p1", "p2", "p3"]}
    settle(s)
    assert s.state.rules.decision is None
    assert all(len(s.state.zones[p + ":hand"]) == before[p] for p in before)
    roundtrip(s)


def test_creature_removed_then_target_lost_preserves_real_last_defender(cards):
    s, source, _, pw = pw_setup(cards)
    announce(s, "Act of Aggression", source, pid="p3", life_symbols=[])
    resolve_top(s)
    assert not s.state.cards[source.id].attack_defender_lost
    announce(s, "Boomerang", pw)
    resolve_top(s)
    settle(s)
    assert s.state.rules.decision.player == "p2"
    before = len(s.state.zones["p2:hand"])
    pick(s, ["yes"])
    settle(s)
    assert len(s.state.zones["p2:hand"]) == before + 1
    roundtrip(s)


def battle_setup(cards):
    s = setup(cards)
    source = put(s, "Harbor Guardian", "battlefield")
    put(s, "Vedalken Orrery", "battlefield")
    put(s, "Vedalken Orrery", "battlefield", pid="p3")
    put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s)
    battle = cast(s, "Invasion of Zendikar // Awakened Skyclave")
    assert s.state.rules.decision.player == "p1"
    pick(s, ["p2"])
    settle(s)
    if s.state.rules.decision:
        pick(s, [])
        settle(s)
    assert s.state.cards[battle.id].zone == "p1:battlefield"
    to_phase(s, "declare_attackers", turn=7)
    attack(s, (source, battle.id))
    return s, source, battle


@pytest.mark.parametrize("effect", ["Boomerang", "Clever Concealment", "Confiscate"])
def test_attacked_battle_departure_phasing_or_control_change_preserves_targetless_status(cards, effect):
    s, source, battle = battle_setup(cards)
    if effect == "Confiscate":
        cast(s, effect, [battle.id], pid="p3", target_counts=[1])
    else:
        cast(s, effect, [battle.id], target_counts=[1])
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].is_attacking
    assert s.state.cards[source.id].attacking is None
    assert s.state.cards[source.id].attacking_without_target == "p2"
    assert s.state.cards[source.id].attack_defender_lost
    roundtrip(s)


@pytest.mark.parametrize("effect", ["Song of the Dryads", "Reality Ripple", "Cloudshift"])
def test_targetless_then_source_type_phase_or_blink_keeps_no_defender(cards, effect):
    s, source, _, pw = pw_setup(cards)
    announce(s, "Boomerang", pw)
    resolve_top(s)
    announce(s, effect, source)
    resolve_top(s)
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[source.id].is_attacking
    roundtrip(s)


def test_pw_type_loss_is_targetless_but_source_type_loss_is_removed(cards):
    s, source, _, pw = pw_setup(cards)
    cast(s, "Song of the Dryads", [pw.id], target_counts=[1])
    assert s.state.cards[source.id].is_attacking
    assert s.state.cards[source.id].attack_defender_lost
    roundtrip(s)
