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


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/trigger_leaf56_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="tlf", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Skulking Killer", "Academy Researchers"])
def test_full_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def pt(s, c):
    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c.id]).pt


def choose(s, ids, settle_after=True):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    if settle_after:
        settle(s)


def game(cards, name):
    names = [
        name,
        "Rancor",
        "Fertile Ground",
        "Robe of Mirrors",
        "Stifle",
        "Cloudshift",
        "Giant Growth",
        "Beast Within",
        "Grizzly Bears",
        "Llanowar Elves",
        "Village Bell-Ringer",
        "Serra Angel",
        "Wurmweaver Coil",
        "Viridescent Wisps",
        "Panharmonicon",
    ]
    return table(cards, names, names, names)


def cast_source(s, name, target=None):
    source = put(s, name, "hand")
    to_phase(s, "main1", 1)
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="add_mana",
        player="p1",
        mana={"C": 3, "B": 1} if name == "Skulking Killer" else {"C": 1, "U": 2},
    )
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id)
    for _ in range(20):
        if s.state.cards[source.id].zone == "p1:battlefield":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return source


def test_killer_whole_single_opponent_creature(cards):
    s = game(cards, "Skulking Killer")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    cast_source(s, "Skulking Killer")
    choose(s, [bear.id])
    assert s.state.cards[bear.id].zone == "p2:graveyard"
    roundtrip(s)


def test_researchers_whole_optional_aura_self_attachment(cards):
    s = game(cards, "Academy Researchers")
    aura = put(s, "Rancor", "hand")
    source = cast_source(s, "Academy Researchers")
    settle(s)
    choose(s, ["yes"])
    choose(s, [aura.id])
    assert s.state.cards[aura.id].zone == "p1:battlefield" and s.state.cards[aura.id].attached_to == source.id
    assert pt(s, source) == (4, 2)
    roundtrip(s)


@pytest.mark.parametrize("extra", [False, True])
def test_killer_other_creatures_checked_only_on_resolution(cards, extra):
    s = game(cards, "Skulking Killer")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    elf = put(s, "Llanowar Elves", "battlefield", "p2") if extra else None
    cast_source(s, "Skulking Killer")
    # Extra creature never prevents choosing the otherwise legal target.
    assert any(o.id == bear.id for o in s.state.rules.decision.options)
    choose(s, [bear.id], False)
    if extra:
        spell(s, "Beast Within", elf.id)  # leaves Beast token, still another creature
    else:
        bell = put(s, "Village Bell-Ringer", "hand", "p2")
        wait_priority(s, "p2")
        act(s, "p2", type="add_mana", player="p2", mana={"C": 2, "W": 1})
        act(s, "p2", type="cast_spell", card_id=bell.id)
        settle(s)
    assert s.state.cards[bear.id].zone == "p2:battlefield" and pt(s, bear) == (2, 2)
    roundtrip(s)


def test_killer_extra_creature_leaves_before_resolution_then_effect_applies(cards):
    s = game(cards, "Skulking Killer")
    angel = put(s, "Serra Angel", "battlefield", "p2")
    elf = put(s, "Llanowar Elves", "battlefield", "p2")
    cast_source(s, "Skulking Killer")
    choose(s, [angel.id], False)
    act(s, "p2", type="move", card_ids=[elf.id], to={"player": "p2", "zone": "graveyard"})
    settle(s)
    assert pt(s, angel) == (2, 2)
    to_phase(s, "main1", 2)
    assert pt(s, angel) == (4, 4)
    roundtrip(s)


@pytest.mark.parametrize("other", [False, True])
def test_killer_current_target_controller_not_owner_or_original_controller(cards, other):
    s = game(cards, "Skulking Killer")
    angel = put(s, "Serra Angel", "battlefield", "p2")
    put(s, "Llanowar Elves", "battlefield", "p2")
    if other:
        put(s, "Grizzly Bears", "battlefield", "p3")
    cast_source(s, "Skulking Killer")
    choose(s, [angel.id], False)
    act(s, "p2", type="set_controller", card_ids=[angel.id], player="p3")
    settle(s)
    assert pt(s, angel) == ((4, 4) if other else (2, 2))
    roundtrip(s)


@pytest.mark.parametrize("aura", ["Fertile Ground", "Wurmweaver Coil"])
def test_researchers_illegal_enchant_land_or_green_stays_hand_no_redirect(cards, aura):
    s = game(cards, "Academy Researchers")
    card = put(s, aura, "hand")
    put(s, "Grizzly Bears", "battlefield")
    cast_source(s, "Academy Researchers")
    settle(s)
    choose(s, ["yes"])
    choose(s, [card.id])
    assert s.state.cards[card.id].zone == "p1:hand" and s.state.cards[card.id].attached_to is None
    roundtrip(s)


def test_researchers_decline_keeps_aura_in_hand(cards):
    s = game(cards, "Academy Researchers")
    aura = put(s, "Rancor", "hand")
    cast_source(s, "Academy Researchers")
    settle(s)
    choose(s, ["no"])
    assert s.state.cards[aura.id].zone == "p1:hand"
    roundtrip(s)


def test_researchers_source_blinked_old_trigger_cannot_attach_new_incarnation(cards):
    s = game(cards, "Academy Researchers")
    aura = put(s, "Rancor", "hand")
    source = cast_source(s, "Academy Researchers")
    spell(s, "Cloudshift", source.id)
    # Decline new incarnation's entry trigger; accept old pending trigger.
    choose(s, ["no"])
    choose(s, ["yes"])
    choose(s, [aura.id])
    assert s.state.cards[aura.id].zone == "p1:hand" and pt(s, source) == (2, 2)
    roundtrip(s)


def test_researchers_source_changed_controller_still_attaches_original_object(cards):
    s = game(cards, "Academy Researchers")
    aura = put(s, "Rancor", "hand")
    source = cast_source(s, "Academy Researchers")
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    settle(s)
    assert s.state.rules.decision.player == "p1"
    choose(s, ["yes"])
    choose(s, [aura.id])
    assert s.state.cards[aura.id].controller == "p1" and s.state.cards[aura.id].attached_to == source.id
    assert pt(s, source) == (4, 2)
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
if os.environ.get('FYODOR_TRIGGERLEAF56_STAGE'):
 from fyodor_triggerleaf56_plugin import install
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


@pytest.mark.parametrize("name", ["Skulking Killer", "Academy Researchers"])
def test_native_stifle_counters_exact_enter_trigger(cards, name):
    s = game(cards, name)
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    aura = put(s, "Rancor", "hand")
    cast_source(s, name)
    if name == "Skulking Killer":
        choose(s, [bear.id], False)
    spell(s, "Stifle", s.state.zones["stack"][-1])
    assert pt(s, bear) == (2, 2) and s.state.cards[aura.id].zone == "p1:hand"
    roundtrip(s)


def test_researchers_current_green_characteristics_per_official_ruling(cards):
    s = game(cards, "Academy Researchers")
    aura = put(s, "Wurmweaver Coil", "hand")
    source = cast_source(s, "Academy Researchers")
    green = put(s, "Viridescent Wisps", "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1})
    act(s, "p1", type="cast_spell", card_id=green.id, targets=[source.id])
    settle(s)
    choose(s, ["yes"])
    choose(s, [aura.id])
    assert s.state.cards[aura.id].attached_to == source.id and pt(s, source) == (9, 8)
    roundtrip(s)


def test_researchers_attaching_aura_does_not_target_shroud_source(cards):
    s = game(cards, "Academy Researchers")
    aura = put(s, "Rancor", "hand")
    robe = put(s, "Robe of Mirrors", "hand")
    put(s, "Panharmonicon", "battlefield")
    source = cast_source(s, "Academy Researchers")
    settle(s)
    choose(s, ["yes"])
    choose(s, [robe.id])
    assert "shroud" in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[source.id]).keywords
    choose(s, ["yes"])
    choose(s, [aura.id])
    assert s.state.cards[aura.id].attached_to == source.id and pt(s, source) == (4, 2)
    roundtrip(s)


def test_killer_cold_selected_target_dynamic_controller_count(cards, tmp_path):
    s = game(cards, "Skulking Killer")
    angel = put(s, "Serra Angel", "battlefield", "p2")
    cast_source(s, "Skulking Killer")
    d = s.state.rules.decision
    s = fresh(
        s,
        cards,
        tmp_path / "killer.json",
        d.player,
        {"type": "choose", "decision_id": d.id, "option_ids": [angel.id]},
    )
    assert pt(s, angel) == (2, 2)
    roundtrip(s)


def test_researchers_cold_selected_hand_aura_retains_exact_source(cards, tmp_path):
    s = game(cards, "Academy Researchers")
    aura = put(s, "Rancor", "hand")
    source = cast_source(s, "Academy Researchers")
    settle(s)
    choose(s, ["yes"])
    d = s.state.rules.decision
    s = fresh(
        s,
        cards,
        tmp_path / "researchers.json",
        d.player,
        {"type": "choose", "decision_id": d.id, "option_ids": [aura.id]},
    )
    assert s.state.cards[aura.id].attached_to == source.id and pt(s, source) == (4, 2)
    roundtrip(s)


@pytest.mark.parametrize("name", ["Skulking Killer", "Academy Researchers"])
def test_pending_trigger_source_destroyed_uses_exact_native_target_or_host(cards, name):
    s = game(cards, name)
    angel = put(s, "Serra Angel", "battlefield", "p2")
    aura = put(s, "Rancor", "hand")
    source = cast_source(s, name)
    if name == "Skulking Killer":
        choose(s, [angel.id], False)
    spell(s, "Beast Within", source.id)
    if name == "Academy Researchers":
        choose(s, ["yes"])
        choose(s, [aura.id])
        assert s.state.cards[aura.id].zone == "p1:hand"
    else:
        assert pt(s, angel) == (2, 2)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)
