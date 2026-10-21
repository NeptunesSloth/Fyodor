"""Native self-block keyword loss and attack-triggered layer7d switching."""

from __future__ import annotations

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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack, block


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/trigger_leaf52_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="tlf", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Elder Land Wurm", "Valakut Fireboar"])
def test_full_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def setup(cards, name):
    names = [
        name,
        "Cloudshift",
        "Guard Duty",
        "Fists of the Anvil",
        "About Face",
        "Lightning Bolt",
        "Llanowar Elves",
    ]
    s = table(cards, names, ["Grizzly Bears", "Llanowar Elves", "Stifle", "Lightning Bolt"])
    source = put(s, name, "hand")
    to_phase(s, "main1", 1)
    wait_priority(s, "p1")
    cost = {"C": 4, "W": 3} if name == "Elder Land Wurm" else {"C": 4, "R": 1}
    act(s, "p1", type="add_mana", player="p1", mana=cost)
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    put(s, "Llanowar Elves", "battlefield")
    return s, source


def keywords(s, c):
    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c.id]).keywords


def pt(s, c):
    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c.id]).pt


def wurm_block(cards):
    s, source = setup(cards, "Elder Land Wurm")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    to_phase(s, "declare_attackers", 4)
    with pytest.raises(ActionError, match="can.t attack"):
        attack(s, (source, "p2"))
    attack(s)
    to_phase(s, "declare_attackers", 5)
    attack(s, (bear, "p1"), pid="p2")
    to_phase(s, "declare_blockers", 5)
    block(s, "p1", (source, bear))
    return s, source, bear


def test_wurm_block_removes_defender_permanently_then_attacks_with_trample(cards):
    s, source, bear = wurm_block(cards)
    assert "defender" in keywords(s, source)
    settle(s)
    assert "defender" not in keywords(s, source) and "trample" in keywords(s, source)
    to_phase(s, "main2", 5)
    assert s.state.cards[bear.id].zone == "p2:graveyard"
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    to_phase(s, "declare_attackers", 7)
    assert "defender" not in keywords(s, source)
    attack(s, (source, "p2"))
    to_phase(s, "declare_blockers", 7)
    block(s, "p2", (bear, source))
    for _ in range(20):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "divide" and d.resume["total"] == 5
    act(s, d.player, type="choose", decision_id=d.id, amounts=[3 if o.id == "p2" else 2 for o in d.options])
    to_phase(s, "main2", 7)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def fireboar_attack(cards):
    s, source = setup(cards, "Valakut Fireboar")
    assert pt(s, source) == (1, 7)
    to_phase(s, "declare_attackers", 4)
    attack(s, (source, "p2"))
    return s, source


def test_fireboar_attack_switches_then_cleanup_restores(cards):
    s, source = fireboar_attack(cards)
    assert pt(s, source) == (1, 7)
    settle(s)
    assert pt(s, source) == (7, 1)
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 33
    to_phase(s, "main1", 5)
    assert pt(s, source) == (1, 7)
    roundtrip(s)


def spell(s, name, target, player="p1"):
    source = put(s, name, "hand", player)
    wait_priority(s, player)
    mana = {
        "Fists of the Anvil": {"C": 1, "R": 1},
        "About Face": {"R": 1},
        "Cloudshift": {"W": 1},
        "Guard Duty": {"W": 1},
        "Stifle": {"U": 1},
        "Lightning Bolt": {"R": 1},
    }[name]
    act(s, player, type="add_mana", player=player, mana=mana)
    act(s, player, type="cast_spell", card_id=source.id, targets=[target])
    settle(s)
    return source


@pytest.mark.parametrize("before", [True, False])
def test_fireboar_asymmetric_pump_applies_before_switch_regardless_timestamp(cards, before):
    s, source = fireboar_attack(cards)
    if not before:
        settle(s)
    spell(s, "Fists of the Anvil", source.id)
    assert pt(s, source) == (7, 5)
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 33
    to_phase(s, "main1", 5)
    assert pt(s, source) == (1, 7)
    roundtrip(s)


def test_fireboar_second_native_switch_restores_original_pair(cards):
    s, source = fireboar_attack(cards)
    settle(s)
    spell(s, "About Face", source.id)
    assert pt(s, source) == (1, 7)
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 39
    roundtrip(s)


def test_fireboar_nonlethal_damage_becomes_lethal_on_trigger_resolution(cards):
    s, source = fireboar_attack(cards)
    bolt = put(s, "Lightning Bolt", "hand", "p2")
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[source.id])
    # The native Bolt resolves before the attack trigger; the original1/7 survives3.
    for _ in range(20):
        if s.state.cards[bolt.id].zone == "p2:graveyard":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[source.id].zone == "p1:battlefield" and pt(s, source) == (1, 7)
    settle(s)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Elder Land Wurm", "Valakut Fireboar"])
def test_countering_real_trigger_does_not_apply_layer_change(cards, name):
    if name == "Elder Land Wurm":
        s, source, _ = wurm_block(cards)
    else:
        s, source = fireboar_attack(cards)
    trigger = s.state.zones["stack"][-1]
    spell(s, "Stifle", trigger, "p2")
    if name == "Elder Land Wurm":
        assert "defender" in keywords(s, source)
    else:
        assert pt(s, source) == (1, 7)
    roundtrip(s)


def test_wurm_blink_resets_permanent_keyword_loss(cards):
    s, source, _ = wurm_block(cards)
    settle(s)
    assert "defender" not in keywords(s, source)
    old = s.state.rules.object_id(source.id)
    spell(s, "Cloudshift", source.id)
    assert s.state.rules.object_id(source.id) != old and "defender" in keywords(s, source)
    roundtrip(s)


def test_fireboar_blink_before_trigger_does_not_switch_new_incarnation(cards):
    s, source = fireboar_attack(cards)
    old = s.state.rules.object_id(source.id)
    spell(s, "Cloudshift", source.id)
    assert s.state.rules.object_id(source.id) != old and pt(s, source) == (1, 7)
    roundtrip(s)


def test_wurm_later_defender_grant_then_second_block_loses_that_instance(cards):
    s, source, bear = wurm_block(cards)
    settle(s)
    to_phase(s, "main1", 7)
    guard = spell(s, "Guard Duty", source.id)
    assert s.state.cards[guard.id].attached_to == source.id and "defender" in keywords(s, source)
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    to_phase(s, "declare_attackers", 7)
    with pytest.raises(ActionError):
        attack(s, (source, "p2"))
    attack(s)
    to_phase(s, "declare_attackers", 8)
    attack(s, (bear, "p1"), pid="p2")
    to_phase(s, "declare_blockers", 8)
    block(s, "p1", (source, bear))
    settle(s)
    assert s.state.cards[guard.id].attached_to == source.id and "defender" not in keywords(s, source)
    roundtrip(s)


def test_fireboar_control_change_same_object_keeps_pending_self_switch(cards):
    s, source = fireboar_attack(cards)
    old = s.state.rules.object_id(source.id)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    settle(s)
    assert s.state.rules.object_id(source.id) == old and pt(s, source) == (7, 1)
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
if os.environ.get('FYODOR_TRIGGERLEAF52_STAGE'):
 from fyodor_triggerleaf52_plugin import install
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


@pytest.mark.parametrize("name", ["Elder Land Wurm", "Valakut Fireboar"])
def test_cold_real_trigger_resolves_and_retains_correct_duration(cards, tmp_path, name):
    if name == "Elder Land Wurm":
        s, source, _ = wurm_block(cards)
    else:
        s, source = fireboar_attack(cards)
    s = fresh(
        s,
        cards,
        tmp_path / ("wurm.json" if name == "Elder Land Wurm" else "fireboar.json"),
        s.state.rules.priority,
        {"type": "pass_priority"},
    )
    if name == "Elder Land Wurm":
        assert "defender" not in keywords(s, source)
        to_phase(s, "main1", 7)
        assert "defender" not in keywords(s, source)
    else:
        assert pt(s, source) == (7, 1)
        to_phase(s, "main1", 5)
        assert pt(s, source) == (1, 7)
    roundtrip(s)


@pytest.mark.parametrize("name", ["Elder Land Wurm", "Valakut Fireboar"])
def test_other_block_event_does_not_trigger_self_block_or_attack_leaf(cards, name):
    s, source = setup(cards, name)
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    blocker = put(s, "Llanowar Elves", "battlefield") if name == "Elder Land Wurm" else source
    to_phase(s, "declare_attackers", 2)
    attack(s, (bear, "p1"), pid="p2")
    to_phase(s, "declare_blockers", 2)
    block(s, "p1", (blocker, bear))
    settle(s)
    assert s.state.rules.decision is None and not s.state.zones["stack"]
    if name == "Elder Land Wurm":
        assert "defender" in keywords(s, source)
    else:
        assert pt(s, source) == (1, 7)
    roundtrip(s)
