"""Canonical damage amounts captured at the printed instruction, with native replacement continuations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/damage_snapshots38_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="bd35", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads((Path(__file__).parent / "fixtures/damage_snapshots38_cards.json").read_text())
    ]
    return table(cards, names, names, names)


def test_weight_counts_nonbasic_lands_of_current_controller_only(cards):
    from tests.game_helpers import act

    s = setup(cards)
    wall = put(s, "Wall of Omens", "battlefield", pid="p2")
    put(s, "Command Tower", "battlefield", pid="p2")
    put(s, "Darksteel Citadel", "battlefield", pid="p2")
    put(s, "Forest", "battlefield", pid="p2")
    put(s, "Command Tower", "battlefield", pid="p3")
    start(s)
    act(s, "p2", type="set_controller", card_ids=[wall.id], player="p3")
    cast(s, "Weight of Spires", [wall.id], target_counts=[1])
    assert s.state.cards[wall.id].damage == 1
    roundtrip(s)


@pytest.mark.parametrize("pid,first", [("p1", 3), ("p2", 2)])
def test_cerebral_vortex_actual_draw_count_this_turn_not_hand_size(cards, pid, first):
    s = setup(cards)
    start(s)
    before = len(s.state.zones[pid + ":hand"])
    cast(s, "Cerebral Vortex", [pid], target_counts=[1])
    assert len(s.state.zones[pid + ":hand"]) == before + 2 - (pid == "p1")
    assert s.state.players[pid].life == 40 - first
    cast(s, "Cerebral Vortex", [pid], target_counts=[1])
    assert s.state.players[pid].life == 40 - first - (first + 2)
    roundtrip(s)


def test_cerebral_vortex_counts_actual_replaced_draws_not_cards_put_in_hand(cards):
    s = setup(cards)
    put(s, "Notion Thief", "battlefield")
    start(s)
    before = len(s.state.zones["p2:hand"])
    cast(s, "Cerebral Vortex", ["p2"], target_counts=[1])
    assert len(s.state.zones["p2:hand"]) == before
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def test_incite_counts_each_players_creatures_before_atomic_damage(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    large = put(s, "Colossal Dreadmaw", "battlefield")
    enemy = put(s, "Runeclaw Bear", "battlefield", pid="p2")
    start(s)
    cast(s, "Incite Rebellion")
    assert (
        s.state.players["p1"].life == 38
        and s.state.players["p2"].life == 39
        and s.state.players["p3"].life == 40
    )
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    assert s.state.cards[large.id].damage == 2 and s.state.cards[enemy.id].damage == 1
    roundtrip(s)


@pytest.mark.parametrize("x", [0, 2])
def test_fear_fire_foes_unpreventable_x_and_other_same_controller_only(cards, x):
    s = setup(cards)
    target = put(s, "Wall of Omens", "battlefield", pid="p2")
    other = put(s, "Grizzly Bears", "battlefield", pid="p2")
    outside = put(s, "Runeclaw Bear", "battlefield", pid="p3")
    start(s)
    cast(s, "Safe Passage", pid="p2")
    cast(s, "Fear, Fire, Foes!", [target.id], x_value=x, target_counts=[1])
    assert s.state.cards[target.id].damage == x and s.state.cards[other.id].damage == 1
    assert s.state.cards[outside.id].damage == 0
    cast(s, "Shock", ["p2"], target_counts=[1])
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_grim_contest_uses_toughness_and_native_simultaneous_sources(cards):
    s = setup(cards)
    wall = put(s, "Wall of Omens", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s)
    cast(s, "Grim Contest", [wall.id, bear.id], target_counts=[1, 1])
    assert s.state.cards[bear.id].zone == "p2:graveyard"
    assert s.state.cards[wall.id].zone == "p1:battlefield" and s.state.cards[wall.id].damage == 2
    roundtrip(s)


@pytest.mark.parametrize("target", ["Mountain", "Darksteel Citadel"])
def test_roiling_terrain_includes_destroyed_land_and_damages_even_if_indestructible(cards, target):
    s = setup(cards)
    land = put(s, target, "battlefield", pid="p2")
    put(s, "Forest", "graveyard", pid="p2")
    start(s)
    cast(s, "Roiling Terrain", [land.id], target_counts=[1])
    assert s.state.players["p2"].life == (39 if target == "Darksteel Citadel" else 38)
    assert s.state.cards[land.id].zone == (
        "p2:battlefield" if target == "Darksteel Citadel" else "p2:graveyard"
    )
    roundtrip(s)


def test_roiling_frozen_controller_uses_that_players_graveyard_not_owner(cards):
    from tests.game_helpers import act

    s = setup(cards)
    land = put(s, "Mountain", "battlefield", pid="p2")
    put(s, "Forest", "graveyard", pid="p3")
    start(s)
    act(s, "p2", type="set_controller", card_ids=[land.id], player="p3")
    cast(s, "Roiling Terrain", [land.id], target_counts=[1])
    assert s.state.cards[land.id].zone == "p2:graveyard"
    assert s.state.players["p3"].life == 39 and s.state.players["p2"].life == 40
    roundtrip(s)


def test_word_blasting_uses_wall_mana_value_and_prevents_existing_regeneration(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    s = setup(cards)
    wall = put(s, "Wall of Bone", "battlefield", pid="p2")
    start(s)
    mana(s, pid="p2", B=1)
    ability = next(
        a
        for a in Plan(s.state, "p1", cards, None).ch(s.state.cards[wall.id]).abilities
        if "Regenerate" in a.text
    )
    # Instant regeneration ability, while p2 has priority in p1's main phase.
    while s.state.rules.priority != "p2":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="activate_ability", card_id=wall.id, ability=ability.index)
    settle(s)
    cast(s, "Word of Blasting", [wall.id], target_counts=[1])
    assert s.state.cards[wall.id].zone == "p2:graveyard"
    assert s.state.players["p2"].life == 37
    roundtrip(s)


@pytest.mark.parametrize("artifact,n,alive", [("Sol Ring", 1, True), ("Darksteel Ingot", 3, False)])
def test_goblin_tinkerer_artifact_is_damage_source_even_if_not_destroyed(cards, artifact, n, alive):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    s = setup(cards)
    tinkerer = put(s, "Goblin Tinkerer", "battlefield")
    target = put(s, artifact, "battlefield", pid="p2")
    start(s)
    mana(s, R=1)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=tinkerer.id,
        ability=0,
        targets=[target.id],
        target_counts=[1],
    )
    settle(s)
    assert s.state.cards[tinkerer.id].zone == ("p1:battlefield" if alive else "p1:graveyard")
    if alive:
        assert s.state.cards[tinkerer.id].damage == n
    assert s.state.cards[target.id].zone == (
        "p2:battlefield" if artifact == "Darksteel Ingot" else "p2:graveyard"
    )
    roundtrip(s)


@pytest.mark.parametrize("name,expected", [("Silvercoat Lion", 38), ("Grizzly Bears", 40)])
def test_cinder_cloud_only_white_death_deals_captured_power(cards, name, expected):
    s = setup(cards)
    target = put(s, name, "battlefield", pid="p2")
    start(s)
    cast(s, "Cinder Cloud", [target.id], target_counts=[1])
    assert s.state.cards[target.id].zone == "p2:graveyard"
    assert s.state.players["p2"].life == expected
    roundtrip(s)


@pytest.mark.parametrize("protection", ["Indestructibility", "Rest in Peace"])
def test_cinder_cloud_no_death_means_no_damage(cards, protection):
    s = setup(cards)
    target = put(s, "Silvercoat Lion", "battlefield", pid="p2")
    start(s)
    cast(
        s,
        protection,
        [target.id] if protection == "Indestructibility" else (),
        **({"target_counts": [1]} if protection == "Indestructibility" else {}),
    )
    cast(s, "Cinder Cloud", [target.id], target_counts=[1])
    assert s.state.players["p2"].life == 40
    assert s.state.cards[target.id].zone == (
        "p2:battlefield" if protection == "Indestructibility" else "p2:exile"
    )
    roundtrip(s)


def test_kaervek_purge_exact_announced_x_and_power_damage(cards):
    s = setup(cards)
    target = put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s)
    cast(s, "Kaervek's Purge", [target.id], x_value=2, target_counts=[1])
    assert s.state.cards[target.id].zone == "p2:graveyard" and s.state.players["p2"].life == 38
    roundtrip(s)


def test_parallectric_feedback_actual_x_spell_mana_value_without_countering(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    s = setup(cards)
    start(s)
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    spell = put(s, "Blaze", "hand")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"], target_counts=[1], x_value=3)
    assert s.state.cards[spell.id].zone == "stack"
    cast(s, "Parallectric Feedback", [spell.id], target_counts=[1])
    assert s.state.players["p1"].life == 36
    assert s.state.players["p2"].life == 37, (
        s.state.rules.decision,
        s.state.cards[spell.id].zone,
        s.state.rules.stack,
    )
    assert s.state.cards[spell.id].zone == "p1:graveyard"
    roundtrip(s)


def test_cerebral_vortex_saved_abundance_draw_continuation_counts_only_actual_draws_cold(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    start(s)
    put(s, "Abundance", "battlefield", pid="p2")
    put(s, "Forest", "library", pid="p2")
    put(s, "Island", "library", pid="p2")
    cast(s, "Cerebral Vortex", ["p2"], target_counts=[1])
    assert s.state.rules.decision and s.state.rules.decision.player == "p2"
    assert "decline" in {o.id for o in s.state.rules.decision.options}
    saved = tmp_path / "vortex-draw38.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import pick,settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
replaced=0
for _ in range(12):
 d=s.state.rules.decision
 if d is None:
  settle(s)
  if s.state.rules.decision is None:break
  continue
 ids={o.id for o in d.options}
 if 'decline' in ids:
  pick(s,[next(o.id for o in d.options if o.id!='decline')]);replaced+=1
 elif 'land' in ids:pick(s,['land'])
 elif d.kind=='order':pick(s,[o.id for o in d.options])
 else:raise AssertionError(d)
 settle(s)
assert replaced==2 and s.state.rules.decision is None
assert s.state.players['p2'].life==40
assert s.state.rules.turn_log.drew.get('p2',0)==0
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_incite_pending_damage_replacement_resumes_cold_single_frozen_batch(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    torbran = put(s, "Torbran, Thane of Red Fell", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    enemy = put(s, "Memnite", "battlefield", pid="p2")
    put(s, "Furnace of Rath", "battlefield")
    start(s)
    cast(s, "Incite Rebellion")
    assert s.state.rules.decision and s.state.rules.decision.player == "p2"
    assert any("Furnace of Rath" in o.label for o in s.state.rules.decision.options)
    # The whole event is still prepared: its first recipients have not died.
    assert s.state.cards[torbran.id].zone == "p1:battlefield"
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    roundtrip(s)
    saved = tmp_path / "incite-damage38.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import pick,settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
ordered=0
for _ in range(10):
 d=s.state.rules.decision
 if d is None:break
 assert d.player=='p2'
 option=next(o for o in d.options if 'Furnace of Rath' in o.label)
 pick(s,[option.id]);ordered+=1
 settle(s)
assert ordered>=1 and s.state.rules.decision is None
assert s.state.players['p1'].life==36 and s.state.players['p2'].life==36
assert s.state.players['p3'].life==40
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
assert s.state.cards[sys.argv[4]].zone=='p1:graveyard'
assert s.state.cards[sys.argv[5]].zone=='p2:graveyard'
facts=[f for f in s.state.rules.turn_log.facts if f.kind in ('damage','damaged')]
assert len(facts)==5 and len({f.batch for f in facts})==1, facts
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), torbran.id, bear.id, enemy.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
