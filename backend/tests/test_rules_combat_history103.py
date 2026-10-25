from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import pick, put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase as phase_until
from tests.test_rules_wave30p_combat import attack, block

DATA = json.loads((Path(__file__).parent / "fixtures/combat_damage95_cards.json").read_text())
NAMES = ["Hope of Ghirapur", "Admiral Beckett Brass", "Thirsting Axe"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="cmd95", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup95(cards):
    names = list(
        dict.fromkeys(
            [c["name"] for c in DATA]
            + [
                "Grizzly Bears",
                "Llanowar Elves",
                "Sol Ring",
                "Cloudshift",
                "Murder",
                "Counterspell",
                "Lightning Bolt",
                "Forest",
            ]
        )
    )
    s = table(cards, names, names, names)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", full_control=True, hold_priority=True)
    return s


def to_phase(s, phase, turn=None):
    phase_until(s, phase, turn=turn)
    if phase in ("declare_attackers", "declare_blockers"):
        for _ in range(12):
            d = s.state.rules.decision
            if d is not None or s.state.turn.phase != phase:
                break
            act(s,s.state.rules.priority,type="pass_priority")


def start(s,turn=4):
    to_phase(s, "main1", turn=turn)
    for pid in s.state.players:
        act(s,pid,type="set_prefs",full_control=True,hold_priority=True)


def combat95(s, attackers, blockers=()):
    to_phase(s, "declare_attackers", turn=4)
    attack(s, *[(c, "p2") for c in attackers])
    to_phase(s, "declare_blockers", turn=4)
    if s.state.rules.decision and s.state.rules.decision.kind == "declare_blockers":
        block(s, "p2", *blockers)
    else:
        assert not blockers
    to_phase(s, "main2", turn=4)


def cast95(s, name, targets=(), pid="p1", **extra):
    source = put(s, name, "hand", pid=pid)
    wait_priority(s, pid)
    mana(s, pid=pid, C=20, W=20, U=20, B=20, R=20, G=20)
    act(s, pid, type="cast_spell", card_id=source.id, targets=list(targets), **extra)
    settle(s)
    return source


@pytest.mark.parametrize("name", NAMES)
def test_whole_exact_combat_history95(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def hope_damage95(cards):
    s = setup95(cards)
    hope = put(s, NAMES[0], "battlefield")
    start(s)
    combat95(s, [hope])
    assert s.state.players["p2"].life == 39
    return s, hope


def test_hope_actual_combat_sacrifice_original_source_and_cast_restriction95(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s, hope = hope_damage95(cards)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=hope.id,
        ability=ability(s, hope, "Sacrifice"),
        targets=["p2"],
    )
    assert s.state.cards[hope.id].zone == "p1:graveyard"
    settle(s)
    assert any(x["player"] == "p2" for x in s.state.rules.cast_limits)
    to_phase(s, "main1", turn=5)
    cast95(s, "Grizzly Bears", pid="p2")
    artifact = put(s, "Sol Ring", "hand", pid="p2")
    wait_priority(s, "p2")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=artifact.id)
    assert s.state.model_dump_json() == before
    to_phase(s, "main1", turn=7)
    assert not s.state.rules.cast_limits


def test_hope_wrong_damaged_player_rejects_before_sacrifice95(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s, hope = hope_damage95(cards)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=hope.id,
            ability=ability(s, hope, "Sacrifice"),
            targets=["p3"],
        )
    assert s.state.model_dump_json() == before and s.state.cards[hope.id].zone == "p1:battlefield"


def test_axe_known_empty_combat_history_sacrifices_equipped_creature95(cards):
    s = setup95(cards)
    axe = put(s, NAMES[2], "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="attach", card_ids=[axe.id], to=bear.id)
    start(s)
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard" and s.state.cards[axe.id].zone == "p1:battlefield"


def test_beckett_actual_three_original_pirates_permanent_control95(cards):
    s = setup95(cards)
    pirates = [
        put(s, n, "battlefield") for n in ["Storm Fleet Sprinter", "Departed Deckhand", "Sailor of Means"]
    ]
    target = put(s, "Sol Ring", "battlefield", pid="p2")
    start(s)
    combat95(s, pirates)
    source = cast95(s, NAMES[1])
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.player == "p1"
    pick(s, [target.id])
    settle(s)
    assert s.state.cards[target.id].controller == "p1" and s.state.cards[source.id].zone == "p1:battlefield"


def axe_pair95(cards):
    s = setup95(cards)
    axe = put(s, NAMES[2], "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    start(s)
    act(s, "p1", type="attach", card_ids=[axe.id], to=bear.id)
    return s, axe, bear


@pytest.mark.parametrize("blocked", [True, False])
def test_axe_actual_creature_combat_receipt_only_spares_equipped_source95(cards, blocked):
    s, axe, bear = axe_pair95(cards)
    wall = put(s, "Wall of Roots", "battlefield", pid="p2") if blocked else None
    combat95(s, [bear], [(wall, bear)] if wall else [])
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[bear.id].zone == ("p1:battlefield" if blocked else "p1:graveyard")
    assert s.state.cards[axe.id].zone == "p1:battlefield"
    if wall:
        assert s.state.cards[wall.id].zone == "p2:graveyard"


def test_axe_combat_before_actual_equip_still_counts95(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s = setup95(cards)
    axe = put(s, NAMES[2], "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    wall = put(s, "Wall of Roots", "battlefield", pid="p2")
    start(s)
    combat95(s, [bear], [(wall, bear)])
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=axe.id, ability=ability(s, axe, "Equip {"), targets=[bear.id])
    settle(s)
    assert s.state.cards[axe.id].attached_to == bear.id
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"


def forget_combat_provenance95(s):
    from app.game.state import GameState

    data = s.state.model_dump(mode="json")
    data["rules"]["turn_log"].pop("combat_damage95_known")
    s.state = GameState.model_validate(data)
    assert s.state.rules.turn_log.combat_damage95_known is None


def test_axe_legacy_unknown_negative_manual_then_next_native_turn_known95(cards):
    s, axe, bear = axe_pair95(cards)
    forget_combat_provenance95(s)
    to_phase(s, "end", turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == "manual_resolution" and d.resume["step"] == "combat_damage95_legacy"
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    pick(s, ["done"])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    to_phase(s, "main1", turn=5)
    assert s.state.rules.turn_log.combat_damage95_known is True
    to_phase(s, "end", turn=7)
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard"


def test_axe_legacy_positive_actual_combat_receipt_remains_valid95(cards):
    s, axe, bear = axe_pair95(cards)
    wall = put(s, "Wall of Roots", "battlefield", pid="p2")
    combat95(s, [bear], [(wall, bear)])
    forget_combat_provenance95(s)
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.rules.decision is None and s.state.cards[bear.id].zone == "p1:battlefield"


def test_hope_actual_noncombat_longbow_damage_does_not_qualify95(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s = setup95(cards)
    hope = put(s, NAMES[0], "battlefield")
    bow = put(s, "Viridian Longbow", "battlefield")
    act(s, "p1", type="attach", card_ids=[bow.id], to=hope.id)
    start(s)
    act(s, "p1", type="activate_ability", card_id=hope.id, ability=ability(s, hope, "{T}:"), targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 39
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=hope.id,
            ability=ability(s, hope, "Sacrifice"),
            targets=["p2"],
        )
    assert s.state.model_dump_json() == before and s.state.cards[hope.id].zone == "p1:battlefield"


def test_hope_actual_prevented_combat_does_not_qualify95(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s = setup95(cards)
    hope = put(s, NAMES[0], "battlefield")
    start(s)
    cast95(s, "Fog")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (hope, "p2"))
    to_phase(s, "declare_blockers", turn=4)
    if s.state.rules.decision and s.state.rules.decision.kind == "declare_blockers":
        block(s, "p2")
    to_phase(s, "main2", turn=4)
    assert s.state.players["p2"].life == 40
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=hope.id,
            ability=ability(s, hope, "Sacrifice"),
            targets=["p2"],
        )
    assert s.state.model_dump_json() == before and s.state.cards[hope.id].zone == "p1:battlefield"


def test_hope_actual_spell_response_is_not_countered_by_later_restriction95(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s, hope = hope_damage95(cards)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=hope.id,
        ability=ability(s, hope, "Sacrifice"),
        targets=["p2"],
    )
    bolt = cast95(s, "Lightning Bolt", ["p3"], pid="p2")
    assert s.state.cards[bolt.id].zone == "p2:graveyard" and s.state.players["p3"].life == 37
    assert any(x["player"] == "p2" for x in s.state.rules.cast_limits)


def test_beckett_two_pirates_double_strike_is_only_two_originals95(cards):
    s = setup95(cards)
    pirates = [put(s, n, "battlefield") for n in ["Storm Fleet Sprinter", "Departed Deckhand"]]
    target = put(s, "Sol Ring", "battlefield", pid="p2")
    start(s)
    cast95(s, "Double Cleave", [pirates[0].id])
    to_phase(s, "declare_attackers", turn=4)
    attack(s, *[(c, "p2") for c in pirates])
    to_phase(s, "declare_blockers", turn=4)
    if s.state.rules.decision and s.state.rules.decision.kind == "declare_blockers":
        block(s, "p2")
    to_phase(s, "main2", turn=4)
    assert (
        sum(1 for f in s.state.rules.turn_log.facts if f.kind == "damage" and f.combat and f.player == "p2")
        == 3
    )
    cast95(s, NAMES[1])
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.rules.decision is None and s.state.cards[target.id].controller == "p2"


def test_beckett_frozen_pirates_count_after_actual_type_loss_and_departure95(cards):
    s = setup95(cards)
    pirates = [
        put(s, n, "battlefield") for n in ["Storm Fleet Sprinter", "Departed Deckhand", "Sailor of Means"]
    ]
    target = put(s, "Sol Ring", "battlefield", pid="p2")
    start(s)
    combat95(s, pirates)
    cast95(s, "Ego Erasure", ["p1"])
    cast95(s, "Murder", [pirates[0].id])
    cast95(s, NAMES[1])
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.rules.decision and target.id in {o.id for o in s.state.rules.decision.options}
    pick(s, [target.id])
    settle(s)
    assert s.state.cards[target.id].controller == "p1"


def cold95(s, tmp_path, body):
    import subprocess
    import sys

    import app

    saved = tmp_path / "combat95.json"
    saved.write_text(s.state.model_dump_json())
    code = (
        """import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import pick
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
"""
        + body
        + "\nrepo.close()\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(s.cards.db_path)],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_genuine_cold_hope_original_source_sacrificed_cost95(cards, tmp_path):
    from tests.test_rules_wave4h_activation_costs import ability

    s, hope = hope_damage95(cards)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=hope.id,
        ability=ability(s, hope, "Sacrifice"),
        targets=["p2"],
    )
    assert s.state.cards[hope.id].zone == "p1:graveyard"
    cold95(s, tmp_path, "settle(s)\nassert any(x['player']=='p2' for x in s.state.rules.cast_limits)")


def test_genuine_cold_beckett_native_player_history_target_choice95(cards, tmp_path):
    s = setup95(cards)
    pirates = [
        put(s, n, "battlefield") for n in ["Storm Fleet Sprinter", "Departed Deckhand", "Sailor of Means"]
    ]
    target = put(s, "Sol Ring", "battlefield", pid="p2")
    start(s)
    combat95(s, pirates)
    cast95(s, NAMES[1])
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.rules.decision.player == "p1"
    cold95(
        s,
        tmp_path,
        f"pick(s,[{target.id!r}]);settle(s)\nassert s.state.cards[{target.id!r}].controller=='p1'",
    )


def test_genuine_cold_axe_legacy_manual_history_continuation95(cards, tmp_path):
    s, axe, bear = axe_pair95(cards)
    forget_combat_provenance95(s)
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.rules.decision.resume["step"] == "combat_damage95_legacy"
    cold95(
        s,
        tmp_path,
        f"pick(s,['done']);settle(s)\nassert s.state.cards[{bear.id!r}].zone=='p1:battlefield'\nassert s.state.rules.decision is None",
    )


def test_axe_trigger_original_host_blink_excludes_new_incarnation95(cards):
    s, axe, bear = axe_pair95(cards)
    to_phase(s, "end", turn=4)
    assert s.state.zones.get("stack")
    original = s.state.rules.object_id(bear.id)
    cast95(s, "Cloudshift", [bear.id])
    assert s.state.rules.object_id(bear.id) != original
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[axe.id].attached_to is None


def test_axe_source_left_after_trigger_uses_original_attachment_lki95(cards):
    s, axe, bear = axe_pair95(cards)
    to_phase(s, "end", turn=4)
    assert s.state.zones.get("stack")
    cast95(s, "Disenchant", [axe.id])
    assert s.state.cards[axe.id].zone == "p1:graveyard" and s.state.cards[bear.id].zone == "p1:graveyard"


def test_hope_until_actual_next_turn_survives_native_meditate_skip95(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s, hope = hope_damage95(cards)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=hope.id,
        ability=ability(s, hope, "Sacrifice"),
        targets=["p2"],
    )
    settle(s)
    cast95(s, "Meditate")
    to_phase(s, "main1", turn=7)
    assert s.state.turn.active_player == "p2"
    assert any(x["player"] == "p2" for x in s.state.rules.cast_limits)
    to_phase(s, "main1", turn=9)
    assert s.state.turn.active_player == "p1" and not s.state.rules.cast_limits


def test_hope_changed_controller_uses_original_damage_and_new_controller_duration95(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s, hope = hope_damage95(cards)
    cast95(s, "Word of Seizing", [hope.id], pid="p3")
    assert s.state.cards[hope.id].controller == "p3"
    wait_priority(s, "p3")
    act(
        s,
        "p3",
        type="activate_ability",
        card_id=hope.id,
        ability=ability(s, hope, "Sacrifice"),
        targets=["p2"],
    )
    settle(s)
    assert s.state.cards[hope.id].zone == "p1:graveyard"
    assert any(x["controller"] == "p3" and x["player"] == "p2" for x in s.state.rules.cast_limits)
    to_phase(s, "main1", turn=5)
    assert s.state.rules.cast_limits
    to_phase(s, "main1", turn=6)
    assert not s.state.rules.cast_limits


def test_axe_native_reattach_in_response_sacrifices_current_host103(cards):
    s,axe,bear=axe_pair95(cards)
    other=put(s,"Llanowar Elves","battlefield")
    to_phase(s,"end",turn=4)
    assert s.state.zones.get("stack")
    cast95(s,"Magnetic Theft",[axe.id,other.id],target_counts=[1,1])
    assert s.state.cards[bear.id].zone=="p1:battlefield"
    assert s.state.cards[other.id].zone=="p1:graveyard"
