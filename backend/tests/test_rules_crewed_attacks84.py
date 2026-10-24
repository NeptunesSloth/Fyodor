from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_crew_saddle_readers81 import cards as cards
from tests.test_rules_crew_saddle_readers81 import crew81
from tests.test_rules_designations import pick, put
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack


def test_balthier_whole84(cards):
    assert coverage.of_card_data(cards.resolve("Balthier and Fran")).level == "FULL"


def setup84(cards):
    from tests.test_rules_crew_saddle_readers81 import DATA
    from tests.test_rules_declaration_requirements33 import start
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [c["name"] for c in DATA] + ["Grizzly Bears", "Forest"], ["Forest"], [])
    source = put(s, "Balthier and Fran", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    vehicle = put(s, "Ghost Ark", "battlefield")
    start(s)
    return s, source, bear, vehicle


def attack84(s, vehicle):
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (vehicle, "p2"))
    settle(s)


def test_native_original_crew_attack_pays_and_adds_combat_without_main(cards):
    s, source, bear, vehicle = setup84(cards)
    crew81(s, vehicle, source)
    to_phase(s, "declare_attackers", turn=4)
    mana(s, C=1, R=1, G=1)
    attack(s, (vehicle, "p2"))
    settle(s)
    d = s.state.rules.decision
    assert d and "pay" in {o.id for o in d.options}, d
    pick(s, ["pay"])
    settle(s)
    assert s.state.rules.extra_phases == ["begin_combat", "main2"]


def test_native_cost_decline_does_not_add_combat(cards):
    s, source, bear, vehicle = setup84(cards)
    crew81(s, vehicle, source)
    to_phase(s, "declare_attackers", turn=4)
    mana(s, C=1, R=1, G=1)
    attack(s, (vehicle, "p2"))
    settle(s)
    pick(s, ["decline"])
    settle(s)
    assert not s.state.rules.extra_phases


def test_other_creature_crew_does_not_trigger_source(cards):
    s, source, bear, vehicle = setup84(cards)
    crew81(s, vehicle, bear)
    attack84(s, vehicle)
    assert not s.state.rules.extra_phases
    assert not s.state.rules.decision or "pay" not in {o.id for o in s.state.rules.decision.options}


def test_new_source_incarnation_does_not_inherit_old_crew(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s, source, bear, vehicle = setup84(cards)
    crew81(s, vehicle, source)
    spell = put(s, "Cloudshift", "hand")
    mana(s, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[source.id])
    settle(s)
    attack84(s, vehicle)
    assert not s.state.rules.extra_phases
    assert not s.state.rules.decision or "pay" not in {o.id for o in s.state.rules.decision.options}


def test_changed_source_controller_can_pay_for_opponents_crewed_vehicle(cards):
    s, source, bear, vehicle = setup84(cards)
    crew81(s, vehicle, source)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    to_phase(s, "declare_attackers", turn=4)
    mana(s, pid="p2", C=1, R=1, G=1)
    attack(s, (vehicle, "p2"))
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.player == "p2"
    pick(s, ["pay"])
    settle(s)
    assert s.state.rules.extra_phases == ["begin_combat", "main2"]


def test_source_blinked_after_trigger_uses_original_crew_fact(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s, source, bear, vehicle = setup84(cards)
    crew81(s, vehicle, source)
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (vehicle, "p2"))
    assert s.state.zones.get("stack")
    spell = put(s, "Cloudshift", "hand")
    mana(s, W=1, R=1, G=1, C=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[source.id])
    settle(s)
    assert s.state.rules.decision and "pay" in {o.id for o in s.state.rules.decision.options}
    pick(s, ["pay"])
    settle(s)
    assert s.state.rules.extra_phases == ["begin_combat", "main2"]


def test_second_combat_attack_does_not_trigger_again(cards):
    s, source, bear, vehicle = setup84(cards)
    crew81(s, vehicle, source)
    to_phase(s, "declare_attackers", turn=4)
    mana(s, C=1, R=1, G=1)
    attack(s, (vehicle, "p2"))
    settle(s)
    pick(s, ["pay"])
    settle(s)
    for _ in range(80):
        if s.state.rules.combats == 2 and s.state.turn.phase == "begin_combat":
            break
        d = s.state.rules.decision
        if d:
            assert d.kind == "declare_blockers", d.model_dump()
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.combats == 2
    to_phase(s, "declare_attackers", turn=4)
    mana(s, C=1, R=1, G=1)
    attack(s, (vehicle, "p2"))
    settle(s)
    assert not s.state.rules.decision or "pay" not in {o.id for o in s.state.rules.decision.options}
    assert s.state.rules.extra_phases == ["main2"]


def test_actual_printed_cast_and_vehicle_static_branches(cards):
    from app.rules.plan import Plan
    from tests.test_rules_bandmate_references import wait_priority

    s, source, bear, vehicle = setup84(cards)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
    mana(s, C=1, R=1, G=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == "p1:battlefield"
    crew81(s, vehicle, source)
    plan = Plan(s.state, "p1", s.cards, None)
    ch = plan.ch(s.state.cards[vehicle.id])
    assert ch.pt == (4, 4)
    assert {"reach", "vigilance"} <= set(ch.keywords)
    assert "reach" in plan.ch(s.state.cards[source.id]).keywords
    assert plan.ch(s.state.cards[bear.id]).pt == (2, 2)


def test_genuine_cold_pending_native_optional_payment84(cards, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    import app

    s, source, bear, vehicle = setup84(cards)
    crew81(s, vehicle, source)
    to_phase(s, "declare_attackers", turn=4)
    mana(s, C=1, R=1, G=1)
    attack(s, (vehicle, "p2"))
    settle(s)
    assert s.state.rules.decision and "pay" in {o.id for o in s.state.rules.decision.options}
    saved = tmp_path / "balthier84.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d and d.kind!='manual_resolution' and 'pay' in {o.id for o in d.options}
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay']);settle(s)
assert s.state.rules.extra_phases==['begin_combat','main2']
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path)],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
