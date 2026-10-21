"""Native optional attack-mill target and entering-land controller binding."""

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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/trigger_leaf59_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="tlf", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards, active=True):
    names = [
        "Saproling Infestation",
        "Gnarlid Pack",
        "Kavu Titan",
        "Anavolver",
        "Counterspell",
        "Stifle",
        "Naturalize",
        "Grizzly Bears",
        "Sol Ring",
        "Long River's Pull",
        "Double Major",
        "Torch the Tower",
        "Clutch of Currents",
        "Leyline of Anticipation",
        "Roost of Drakes",
    ]
    s = table(cards, names, names, names)
    source = put(s, "Saproling Infestation", "hand")
    to_phase(s, "main1", 1)
    wait_priority(s, "p1")
    if not active:
        return s, source
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    return s, source


def sapros(s, pid="p1"):
    return [
        c
        for c in s.state.cards.values()
        if c.token and c.name == "Saproling" and c.zone.endswith(":battlefield") and c.controller == pid
    ]


def finish_order(s):
    d = s.state.rules.decision
    if d is not None and d.kind == "order":
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])


def cast_pack(s, count, player="p1", order=True):
    if player == "p2":
        to_phase(s, "main1", 2)
    spell = put(s, "Gnarlid Pack", "hand", player)
    wait_priority(s, player)
    act(s, player, type="add_mana", player=player, mana={"C": 1 + count, "G": 1 + count})
    act(s, player, type="set_prefs", hold_priority=True)
    act(s, player, type="cast_spell", card_id=spell.id, kicker=count)
    if order:
        finish_order(s)
    return spell


def test_whole_canonical(cards):
    assert coverage.of_card_data(cards.resolve("Saproling Infestation")).level == "FULL"


@pytest.mark.parametrize("count", [0, 1, 3])
def test_multikicker_independent_triggers_actual_payment_and_token_controller(cards, count):
    s, source = game(cards)
    spell = cast_pack(s, count)
    triggers = [e for e in s.state.rules.stack.values() if e.source_card == source.id]
    assert len(triggers) == count and not sapros(s)
    assert s.state.rules.payments[s.state.rules.object_id(spell.id)].kicked == count
    settle(s)
    assert len(sapros(s)) == count and not sapros(s, "p2")
    assert s.state.cards[spell.id].counters.get("+1/+1", 0) == count
    roundtrip(s)


def test_another_player_kicker_creates_tokens_for_frozen_ability_controller(cards):
    s, source = game(cards)
    cast_pack(s, 3, "p2")
    assert len([e for e in s.state.rules.stack.values() if e.source_card == source.id]) == 3
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p3")
    settle(s)
    assert len(sapros(s)) == 3 and not sapros(s, "p2") and not sapros(s, "p3")
    roundtrip(s)


@pytest.mark.parametrize("mask", [0, 1, 2, 3])
def test_dual_kicker_payments_are_independent_occurrences(cards, mask):
    s, source = game(cards)
    spell = put(s, "Anavolver", "hand")
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="add_mana",
        player="p1",
        mana={
            "C": 3 + int(bool(mask & 1)),
            "G": 1,
            **({"U": 1} if mask & 1 else {}),
            **({"B": 1} if mask & 2 else {}),
        },
    )
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=mask)
    finish_order(s)
    count = int(bool(mask & 1)) + int(bool(mask & 2))
    assert len([e for e in s.state.rules.stack.values() if e.source_card == source.id]) == count
    settle(s)
    assert len(sapros(s)) == count
    roundtrip(s)


def test_single_kicker_actual_cost_one_independent_trigger(cards):
    s, source = game(cards)
    spell = put(s, "Kavu Titan", "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "G": 2})
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1)
    assert len([e for e in s.state.rules.stack.values() if e.source_card == source.id]) == 1
    settle(s)
    assert len(sapros(s)) == 1 and s.state.cards[spell.id].counters.get("+1/+1", 0) == 3
    roundtrip(s)


@pytest.mark.parametrize("change", ["stifle_one", "spell_countered", "source_gone", "copy_spell"])
def test_independent_triggers_survive_spell_counter_source_death_or_copy(cards, change):
    s, source = game(cards)
    spell = cast_pack(s, 3)
    name = {
        "stifle_one": "Stifle",
        "spell_countered": "Counterspell",
        "source_gone": "Naturalize",
        "copy_spell": "Double Major",
    }[change]
    target = (
        source.id
        if change == "source_gone"
        else s.state.zones["stack"][-1]
        if change == "stifle_one"
        else spell.id
    )
    mana = {
        "Stifle": {"U": 1},
        "Counterspell": {"U": 2},
        "Naturalize": {"C": 1, "G": 1},
        "Double Major": {"G": 1, "U": 1},
    }[name]
    response = put(s, name, "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana=mana)
    act(s, "p1", type="cast_spell", card_id=response.id, targets=[target])
    settle(s)
    assert len(sapros(s)) == (2 if change == "stifle_one" else 3)
    if change == "spell_countered":
        assert s.state.cards[spell.id].zone == "p1:graveyard"
    if change == "source_gone":
        assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


def test_promised_gift_does_not_kick_a_spell(cards):
    s, source = game(cards)
    original = cast_pack(s, 0)
    response = put(s, "Long River's Pull", "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2})
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=response.id,
        optional_costs=[response.id + ":gift"],
        gift_to="p2",
        targets=[original.id],
        target_counts=[0, 1],
    )
    record = s.state.rules.payments[s.state.rules.object_id(response.id)]
    assert record.gift_to == "p2" and record.kicked == 1
    assert not [e for e in s.state.rules.stack.values() if e.source_card == source.id]
    settle(s)
    assert not sapros(s)
    roundtrip(s)


def test_bargain_does_not_kick_a_spell(cards):
    s, source = game(cards)
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    artifact = put(s, "Sol Ring", "battlefield")
    response = put(s, "Torch the Tower", "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=response.id,
        optional_costs=[response.id + ":bargain"],
        targets=[victim.id],
    )
    d = s.state.rules.decision
    assert d is not None and artifact.id in [o.id for o in d.options]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[artifact.id])
    record = s.state.rules.payments[s.state.rules.object_id(response.id)]
    assert record.kicked == 1 and any(x.endswith(":bargain") for x in record.additional)
    assert not [e for e in s.state.rules.stack.values() if e.source_card == source.id]
    settle(s)
    for _ in range(4):
        d = s.state.rules.decision
        if d is None:
            break
        act(
            s,
            d.player,
            type="choose",
            decision_id=d.id,
            option_ids=[o.id for o in d.options][: d.min_choices],
        )
        settle(s)
    assert not sapros(s)
    roundtrip(s)


def test_awaken_does_not_kick_a_spell(cards):
    s, source = game(cards)
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    land = put(s, "Forest", "battlefield")
    response = put(s, "Clutch of Currents", "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 4, "U": 1})
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=response.id,
        awaken=True,
        targets=[victim.id, land.id],
        target_counts=[1, 1],
    )
    record = s.state.rules.payments[s.state.rules.object_id(response.id)]
    assert record.kicked == 1 and record.alternative == "awaken"
    assert not [e for e in s.state.rules.stack.values() if e.source_card == source.id]
    settle(s)
    assert not sapros(s) and s.state.cards[land.id].counters.get("+1/+1", 0) == 3
    roundtrip(s)


def test_failed_unpaid_multikicker_cast_has_no_kicker_events(cards):
    from app.game.errors import ActionError

    s, source = game(cards)
    spell = put(s, "Gnarlid Pack", "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, kicker=3)
    assert s.state.cards[spell.id].zone == "p1:hand" and not s.state.zones["stack"] and not sapros(s)
    roundtrip(s)


def test_infestation_entering_after_kicker_cast_does_not_watch_retroactively(cards):
    s, source = game(cards, False)
    put(s, "Leyline of Anticipation", "battlefield")
    cast_pack(s, 3)
    assert not [e for e in s.state.rules.stack.values() if e.source_card == source.id]
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == "p1:battlefield" and not sapros(s)
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
if os.environ.get("FYODOR_TRIGGERLEAF59_STAGE"):
 sys.path.insert(0,"/tmp/fyodor-triggerleaf59-stage")
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
if os.environ.get('FYODOR_TRIGGERLEAF59_STAGE'):
 from fyodor_triggerleaf59_plugin import install
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


def test_cold_multiple_pending_trigger_order_and_separate_objects(cards, tmp_path):
    s, source = game(cards)
    put(s, "Roost of Drakes", "battlefield")
    spell = cast_pack(s, 3, order=False)
    d = s.state.rules.decision
    assert d is not None and d.kind == "order" and len(d.options) == 4
    s = fresh(
        s,
        cards,
        tmp_path / "kicks-order.json",
        d.player,
        {"type": "choose", "decision_id": d.id, "option_ids": [o.id for o in d.options]},
    )
    assert len(sapros(s)) == 3 and s.state.cards[spell.id].counters.get("+1/+1", 0) == 3
    assert (
        len(
            [
                c
                for c in s.state.cards.values()
                if c.token and c.name == "Drake" and c.zone.endswith(":battlefield")
            ]
        )
        == 1
    )
    roundtrip(s)


def test_cold_pending_kicks_keep_original_ability_controller(cards, tmp_path):
    s, source = game(cards)
    spell = cast_pack(s, 3, "p2")
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p3")
    s = fresh(s, cards, tmp_path / "kicks-controller.json", s.state.rules.priority, {"type": "pass_priority"})
    assert len(sapros(s)) == 3 and not sapros(s, "p2") and not sapros(s, "p3")
    assert s.state.cards[spell.id].counters.get("+1/+1", 0) == 3
    roundtrip(s)
