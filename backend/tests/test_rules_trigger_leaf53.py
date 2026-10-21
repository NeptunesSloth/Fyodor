"""Native optional attack-mill target and entering-land controller binding."""

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
        json.loads((Path(__file__).parent / "fixtures/trigger_leaf53_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="tlf", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Veteran Ice Climber", "Tectonic Instability"])
def test_full_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def setup(cards, name):
    names = [
        name,
        "Llanowar Elves",
        "Forest",
        "Island",
        "Mountain",
        "Sol Ring",
        "Rampant Growth",
        "Giant Growth",
        "Cloudshift",
        "Disfigure",
        "Beast Within",
        "Naturalize",
        "Stifle",
    ]
    s = table(cards, names, names, names)
    source = put(s, name, "hand")
    to_phase(s, "main1", 1)
    wait_priority(s, "p1")
    mana = {"C": 1, "U": 1} if name == "Veteran Ice Climber" else {"C": 2, "R": 1}
    act(s, "p1", type="add_mana", player="p1", mana=mana)
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    return s, source


def choose(s, ids, settle_after=True):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    if settle_after:
        settle(s)


def climber_attack(cards, extra=False):
    s, source = setup(cards, "Veteran Ice Climber")
    elf = put(s, "Llanowar Elves", "battlefield") if extra else None
    # A real blocking creature makes the declare-blockers decision observable.
    bear = put(s, "Llanowar Elves", "battlefield", "p2")
    to_phase(s, "declare_attackers", 4)
    attack(s, *[(c, "p2") for c in (source, elf) if c is not None])
    return s, source, elf, bear


def test_climber_optional_player_target_differs_from_attacked_player_vigilance_unblockable(cards):
    s, source, elf, bear = climber_attack(cards, True)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0 and d.max_choices == 1
    before = len(s.state.zones["p3:library"])
    choose(s, ["p3"])
    assert len(s.state.zones["p3:library"]) == before - 1 and not s.state.cards[source.id].tapped
    to_phase(s, "declare_blockers", 4)
    with pytest.raises(ActionError):
        block(s, "p2", (bear, source))
    block(s, "p2", (bear, elf))
    to_phase(s, "main2", 4)
    assert s.state.players["p2"].life == 39 and not s.state.cards[source.id].tapped
    roundtrip(s)


@pytest.mark.parametrize("target", [None, "p1", "p2"])
def test_climber_may_choose_no_player_or_itself_or_attacked_player(cards, target):
    s, source, _, _ = climber_attack(cards)
    before = {p: len(s.state.zones[p + ":library"]) for p in ("p1", "p2", "p3")}
    choose(s, [] if target is None else [target])
    assert s.state.rules.decision is None
    for p in before:
        assert len(s.state.zones[p + ":library"]) == before[p] - (1 if p == target else 0)
    roundtrip(s)


def tectonic_play(cards):
    s, source = setup(cards, "Tectonic Instability")
    old = {
        p: put(s, n, "battlefield", p) for p, n in [("p1", "Forest"), ("p2", "Island"), ("p3", "Mountain")]
    }
    to_phase(s, "main1", 2)
    wait_priority(s, "p2")
    land = next(
        c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.id != old["p2"].id
    )
    act(s, "p2", type="move", card_ids=[land.id], to={"player": "p2", "zone": "hand"})
    act(s, "p2", type="set_prefs", hold_priority=True)
    act(s, "p2", type="play_land", card_id=land.id)
    assert s.state.zones["stack"]
    return s, source, land, old


def test_tectonic_real_land_play_taps_all_its_controllers_lands_only(cards):
    s, source, land, old = tectonic_play(cards)
    assert all(not s.state.cards[c.id].tapped for c in [land, *old.values()])
    settle(s)
    assert s.state.cards[land.id].tapped and s.state.cards[old["p2"].id].tapped
    assert not s.state.cards[old["p1"].id].tapped and not s.state.cards[old["p3"].id].tapped
    roundtrip(s)


def test_tectonic_event_land_current_controller_not_entry_actor_or_owner(cards):
    s, source, land, old = tectonic_play(cards)
    act(s, "p2", type="set_controller", card_ids=[land.id], player="p3")
    settle(s)
    assert s.state.cards[land.id].owner == "p2" and s.state.cards[land.id].controller == "p3"
    assert s.state.cards[land.id].tapped and s.state.cards[old["p3"].id].tapped
    assert not s.state.cards[old["p1"].id].tapped and not s.state.cards[old["p2"].id].tapped
    roundtrip(s)


def spell(s, name, target, player="p1"):
    source = put(s, name, "hand", player)
    wait_priority(s, player)
    mana = {
        "Giant Growth": {"G": 1},
        "Cloudshift": {"W": 1},
        "Disfigure": {"B": 1},
        "Naturalize": {"C": 1, "G": 1},
        "Beast Within": {"C": 2, "G": 1},
        "Stifle": {"U": 1},
    }[name]
    act(s, player, type="add_mana", player=player, mana=mana)
    act(s, player, type="cast_spell", card_id=source.id, targets=[target])
    settle(s)
    return source


@pytest.mark.parametrize("change", ["pump", "negative", "blink_lki"])
def test_climber_reads_resolution_power_or_exact_original_source_lki(cards, change):
    s, source, _, _ = climber_attack(cards)
    before = len(s.state.zones["p3:library"])
    choose(s, ["p3"], False)
    if change == "negative":
        spell(s, "Disfigure", source.id)
    else:
        if change == "blink_lki":
            # Keep the attack trigger pending while the pump resolves and the
            # source then leaves. Only that original object's LKI is relevant.
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
        else:
            spell(s, "Giant Growth", source.id)
    assert len(s.state.zones["p3:library"]) == before - (0 if change == "negative" else 4)
    roundtrip(s)


def test_tectonic_current_land_set_follows_control_not_land_ownership(cards):
    s, source, land, old = tectonic_play(cards)
    act(s, "p1", type="set_controller", card_ids=[old["p1"].id], player="p2")
    settle(s)
    assert all(s.state.cards[c.id].tapped for c in [land, old["p1"], old["p2"]])
    assert not s.state.cards[old["p3"].id].tapped
    roundtrip(s)


def test_tectonic_event_land_last_controller_after_native_destruction(cards):
    s, source, land, old = tectonic_play(cards)
    act(s, "p2", type="set_controller", card_ids=[land.id], player="p3")
    spell(s, "Beast Within", land.id)
    assert s.state.cards[land.id].zone == "p2:graveyard"
    assert s.state.cards[old["p3"].id].tapped
    assert not s.state.cards[old["p1"].id].tapped and not s.state.cards[old["p2"].id].tapped
    roundtrip(s)


def test_tectonic_source_departure_does_not_cancel_pending_trigger(cards):
    s, source, land, old = tectonic_play(cards)
    spell(s, "Naturalize", source.id)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert s.state.cards[land.id].tapped and s.state.cards[old["p2"].id].tapped
    assert not s.state.cards[old["p1"].id].tapped and not s.state.cards[old["p3"].id].tapped
    roundtrip(s)


def test_tectonic_actual_tutor_put_triggers_without_land_play(cards):
    s, source = setup(cards, "Tectonic Instability")
    old = put(s, "Island", "battlefield", "p2")
    growth = put(s, "Rampant Growth", "hand", "p2")
    to_phase(s, "main1", 2)
    wait_priority(s, "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1, "G": 1})
    act(s, "p2", type="cast_spell", card_id=growth.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    assert d.player == "p2" and d.resume["step"] == "search"
    land = next(
        o.id for o in d.options if o.card_id in s.state.cards and s.state.cards[o.card_id].name == "Island"
    )
    choose(s, [land])
    assert s.state.cards[land].zone == "p2:battlefield" and s.state.cards[land].tapped
    assert s.state.cards[old.id].tapped
    assert s.state.rules.lands_played.get("p2") is None
    roundtrip(s)


@pytest.mark.parametrize("name", ["Veteran Ice Climber", "Tectonic Instability"])
def test_native_stifle_counters_trigger_without_applying_effect(cards, name):
    if name == "Veteran Ice Climber":
        s, source, _, _ = climber_attack(cards)
        choose(s, ["p3"], False)
        before = len(s.state.zones["p3:library"])
        land = old = None
    else:
        s, source, land, old = tectonic_play(cards)
        before = None
    trigger = s.state.zones["stack"][-1]
    spell(s, "Stifle", trigger, "p2")
    if name == "Veteran Ice Climber":
        assert len(s.state.zones["p3:library"]) == before
    else:
        assert all(not s.state.cards[c.id].tapped for c in [land, *old.values()])
    roundtrip(s)


def test_climber_target_player_departure_does_not_redirect_mill(cards):
    s, source, _, _ = climber_attack(cards)
    choose(s, ["p3"], False)
    before = {p: len(s.state.zones[p + ":library"]) for p in ("p1", "p2")}
    act(s, "p3", type="concede")
    settle(s)
    assert all(len(s.state.zones[p + ":library"]) == before[p] for p in before)
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
if os.environ.get('FYODOR_TRIGGERLEAF53_STAGE'):
 from fyodor_triggerleaf53_plugin import install
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


def test_climber_cold_optional_target_group_and_native_power_value(cards, tmp_path):
    s, source, _, _ = climber_attack(cards)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0
    before = len(s.state.zones["p3:library"])
    s = fresh(
        s,
        cards,
        tmp_path / "climber.json",
        d.player,
        {"type": "choose", "decision_id": d.id, "option_ids": ["p3"]},
    )
    assert len(s.state.zones["p3:library"]) == before - 1 and not s.state.cards[source.id].tapped
    roundtrip(s)


def test_tectonic_cold_original_event_ref_reads_current_controller(cards, tmp_path):
    s, source, land, old = tectonic_play(cards)
    act(s, "p2", type="set_controller", card_ids=[land.id], player="p3")
    s = fresh(s, cards, tmp_path / "tectonic.json", s.state.rules.priority, {"type": "pass_priority"})
    assert s.state.cards[land.id].tapped and s.state.cards[old["p3"].id].tapped
    assert not s.state.cards[old["p1"].id].tapped and not s.state.cards[old["p2"].id].tapped
    roundtrip(s)


def test_tectonic_nonland_native_entry_does_not_trigger_land_tapping(cards):
    s, source = setup(cards, "Tectonic Instability")
    old = {
        p: put(s, n, "battlefield", p) for p, n in [("p1", "Forest"), ("p2", "Island"), ("p3", "Mountain")]
    }
    ring = put(s, "Sol Ring", "hand", "p2")
    to_phase(s, "main1", 2)
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    act(s, "p2", type="cast_spell", card_id=ring.id)
    settle(s)
    assert s.state.cards[ring.id].zone == "p2:battlefield" and not s.state.zones["stack"]
    assert all(not s.state.cards[c.id].tapped for c in old.values())
    roundtrip(s)
