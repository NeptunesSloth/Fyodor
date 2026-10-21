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
        json.loads((Path(__file__).parent / "fixtures/trigger_leaf57_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="tlf", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Absolving Lammasu", "Drake Familiar"])
def test_full_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def choose(s, ids, settle_after=True):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    if settle_after:
        settle(s)


def game(cards, name):
    names = [
        name,
        "Barbed Servitor",
        "Grizzly Bears",
        "Llanowar Elves",
        "One with the Stars",
        "Enchanted Evening",
        "Sterling Grove",
        "Stifle",
        "Cloudshift",
        "Beast Within",
        "Giant Growth",
        "Convenient Target",
    ]
    return table(cards, names, names, names)


def cast(s, name, mana, player="p1", targets=None, pending=False):
    source = put(s, name, "hand", player)
    wait_priority(s, player)
    act(s, player, type="add_mana", player=player, mana=mana)
    act(
        s,
        player,
        type="cast_spell",
        card_id=source.id,
        **({"targets": targets} if targets is not None else {}),
    )
    if pending:
        for _ in range(20):
            if s.state.cards[source.id].zone.endswith(":battlefield"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
    else:
        settle(s)
    return source


@pytest.mark.parametrize("mode", ["none", "decline", "opponent", "self_enchantment"])
def test_drake_optional_global_enchantment_return_cost(cards, mode):
    s = game(cards, "Drake Familiar")
    to_phase(s, "main1", 1)
    enchant = put(s, "Sterling Grove", "battlefield", "p2") if mode in ("opponent", "decline") else None
    if mode == "self_enchantment":
        put(s, "Enchanted Evening", "battlefield")
    source = cast(s, "Drake Familiar", {"C": 1, "U": 1})
    if mode != "none":
        choose(s, [] if mode == "decline" else [enchant.id if enchant else source.id])
    assert s.state.cards[source.id].zone == (
        "p1:graveyard"
        if mode in ("none", "decline")
        else "p1:hand"
        if mode == "self_enchantment"
        else "p1:battlefield"
    )
    if mode == "opponent":
        assert s.state.cards[enchant.id].zone == "p2:hand"
    roundtrip(s)


def test_lammasu_actual_native_suspect_removed_for_multiple_players(cards):
    s = game(cards, "Absolving Lammasu")
    to_phase(s, "main1", 1)
    first = cast(s, "Barbed Servitor", {"C": 3, "B": 1})
    to_phase(s, "main1", 2)
    second = cast(s, "Barbed Servitor", {"C": 3, "B": 1}, "p2")
    assert len(s.state.rules.suspected) == 2
    to_phase(s, "main1", 4)
    cast(s, "Absolving Lammasu", {"C": 4, "W": 1})
    assert not s.state.rules.suspected
    assert all(not any(m.name == "Suspected" for m in s.state.cards[c.id].effects) for c in (first, second))
    roundtrip(s)


def test_lammasu_preserves_suspected_noncreature_and_unrelated_markers(cards):
    s = game(cards, "Absolving Lammasu")
    to_phase(s, "main1", 1)
    victim = cast(s, "Barbed Servitor", {"C": 3, "B": 1})
    cast(s, "One with the Stars", {"C": 3, "U": 1}, targets=[victim.id])
    assert not Plan.view(s.state, "p1", s.cards).ch(s.state.cards[victim.id]).is_creature
    old = list(s.state.rules.suspected)
    act(s, "p1", type="add_effect", card_ids=[victim.id], name="Unrelated", value="Keep")
    cast(s, "Absolving Lammasu", {"C": 4, "W": 1})
    assert s.state.rules.suspected == old
    assert any(m.name == "Unrelated" for m in s.state.cards[victim.id].effects)
    roundtrip(s)


def test_lammasu_clears_only_suspected_markers_on_current_creature(cards):
    s = game(cards, "Absolving Lammasu")
    to_phase(s, "main1", 1)
    victim = cast(s, "Barbed Servitor", {"C": 3, "B": 1})
    act(s, "p1", type="add_effect", card_ids=[victim.id], name="Unrelated", value="Keep")
    cast(s, "Absolving Lammasu", {"C": 4, "W": 1})
    assert not s.state.rules.suspected
    assert any(m.name == "Unrelated" for m in s.state.cards[victim.id].effects)
    assert not any(m.name == "Suspected" for m in s.state.cards[victim.id].effects)
    ch = Plan.view(s.state, "p1", s.cards).ch(s.state.cards[victim.id])
    assert "menace" not in ch.keywords and "cant_block" not in ch.imposed
    roundtrip(s)


@pytest.mark.parametrize("target", ["none", "live", "illegal"])
def test_lammasu_whole_death_optional_target_and_official_illegal_target_ruling(cards, target):
    s = game(cards, "Absolving Lammasu")
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    to_phase(s, "main1", 1)
    source = cast(s, "Absolving Lammasu", {"C": 4, "W": 1})
    spell(s, "Beast Within", source.id)
    choose(s, [] if target == "none" else [victim.id], target != "illegal")
    if target == "illegal":
        spell(s, "Cloudshift", victim.id, "p2")
    assert s.state.players["p1"].life == (40 if target == "illegal" else 43)
    assert (s.state.rules.object_id(victim.id) in s.state.rules.suspected) == (target == "live")
    roundtrip(s)


def test_drake_untargeted_opponent_enchantment_with_shroud_and_owner_hand(cards):
    s = game(cards, "Drake Familiar")
    put(s, "Sterling Grove", "battlefield", "p2")
    other = put(s, "Enchanted Evening", "battlefield", "p2")
    # Grove grants shroud to the other enchantment; the non-targeted cost can choose it.
    assert "shroud" in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[other.id]).keywords
    to_phase(s, "main1", 1)
    source = cast(s, "Drake Familiar", {"C": 1, "U": 1})
    choose(s, [other.id])
    assert s.state.cards[other.id].zone == "p2:hand" and s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def test_drake_returns_foreign_owned_enchantment_to_owner_not_controller(cards):
    s = game(cards, "Drake Familiar")
    grove = put(s, "Sterling Grove", "battlefield", "p2")
    act(s, "p2", type="set_controller", card_ids=[grove.id], player="p3")
    to_phase(s, "main1", 1)
    source = cast(s, "Drake Familiar", {"C": 1, "U": 1})
    choose(s, [grove.id])
    assert s.state.cards[grove.id].zone == "p2:hand" and s.state.cards[source.id].zone == "p1:battlefield"
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
if os.environ.get('FYODOR_TRIGGERLEAF57_STAGE'):
 from fyodor_triggerleaf57_plugin import install
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


def test_lammasu_cold_pending_enter_trigger_clears_designations(cards, tmp_path):
    s = game(cards, "Absolving Lammasu")
    to_phase(s, "main1", 1)
    cast(s, "Barbed Servitor", {"C": 3, "B": 1})
    cast(s, "Absolving Lammasu", {"C": 4, "W": 1}, pending=True)
    assert s.state.rules.suspected and s.state.zones["stack"]
    s = fresh(s, cards, tmp_path / "lammasu.json", s.state.rules.priority, {"type": "pass_priority"})
    assert not s.state.rules.suspected
    roundtrip(s)


def test_drake_cold_optional_global_enchantment_cost(cards, tmp_path):
    s = game(cards, "Drake Familiar")
    enchant = put(s, "Sterling Grove", "battlefield", "p2")
    to_phase(s, "main1", 1)
    source = cast(s, "Drake Familiar", {"C": 1, "U": 1})
    d = s.state.rules.decision
    s = fresh(
        s,
        cards,
        tmp_path / "drake.json",
        d.player,
        {"type": "choose", "decision_id": d.id, "option_ids": [enchant.id]},
    )
    assert s.state.cards[source.id].zone == "p1:battlefield" and s.state.cards[enchant.id].zone == "p2:hand"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Absolving Lammasu", "Drake Familiar"])
def test_native_stifle_prevents_enter_effect_or_return_cost(cards, name):
    s = game(cards, name)
    to_phase(s, "main1", 1)
    cast(s, "Barbed Servitor", {"C": 3, "B": 1})
    source = cast(
        s, name, {"C": 4, "W": 1} if name == "Absolving Lammasu" else {"C": 1, "U": 1}, pending=True
    )
    spell(s, "Stifle", s.state.zones["stack"][-1])
    assert s.state.rules.suspected and s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def test_lammasu_never_carries_suspected_designation_to_blinked_new_incarnation(cards):
    s = game(cards, "Absolving Lammasu")
    victim = put(s, "Grizzly Bears", "battlefield")
    to_phase(s, "main1", 1)
    cast(s, "Convenient Target", {"R": 1}, targets=[victim.id])
    old = s.state.rules.object_id(victim.id)
    assert old in s.state.rules.suspected
    spell(s, "Cloudshift", victim.id)
    new = s.state.rules.object_id(victim.id)
    assert new != old and new not in s.state.rules.suspected
    act(s, "p1", type="add_effect", card_ids=[victim.id], name="Unrelated", value="Keep")
    cast(s, "Absolving Lammasu", {"C": 4, "W": 1})
    assert new not in s.state.rules.suspected and any(
        m.name == "Unrelated" for m in s.state.cards[victim.id].effects
    )
    roundtrip(s)


def test_drake_stale_enchantment_choice_cannot_pay_from_owner_hand(cards):
    s=game(cards,"Drake Familiar")
    enchant=put(s,"Sterling Grove","battlefield","p2")
    to_phase(s,"main1",1)
    source=cast(s,"Drake Familiar",{"C":1,"U":1})
    assert s.state.rules.decision is not None
    act(s,"p2",type="move",card_ids=[enchant.id],to={"player":"p2","zone":"hand"})
    choose(s,[enchant.id])
    assert s.state.cards[source.id].zone=="p1:graveyard"
    roundtrip(s)
