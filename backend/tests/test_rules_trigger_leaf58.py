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
from tests.test_rules_wave30p_combat import attack, block


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/trigger_leaf58_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="tlf", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Righteous Indignation", "Ordruun Mentor"])
def test_full_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def game(cards, name):
    names = [
        name,
        "Wall of Glare",
        "Goblin Piker",
        "Drudge Skeletons",
        "Rakdos Cackler",
        "Grizzly Bears",
        "Llanowar Elves",
        "Jace Beleren",
        "Cerulean Wisps",
        "Crimson Wisps",
        "Cloudshift",
        "Beast Within",
        "Stifle",
        "Giant Growth",
        "Invasion of Mercadia // Kyren Flamewright",
    ]
    return table(cards, names, names, names)


def pt(s, c):
    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c.id]).pt


def cast_source(s, name):
    source = put(s, name, "hand")
    to_phase(s, "main1", 1)
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="add_mana",
        player="p1",
        mana={"C": 2, "W": 1} if name == "Righteous Indignation" else {"C": 1, "R": 1, "W": 1},
    )
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    return source


@pytest.mark.parametrize("names,expected", [("redblack", (2, 7)), ("multicolor", (1, 6)), ("green", (0, 5))])
def test_righteous_original_blocker_multipair_union_and_negative(cards, names, expected):
    s = game(cards, "Righteous Indignation")
    cast_source(s, "Righteous Indignation")
    wall = put(s, "Wall of Glare", "battlefield")
    attackers = [
        put(s, n, "battlefield", "p2")
        for n in (
            {
                "redblack": ["Goblin Piker", "Drudge Skeletons"],
                "multicolor": ["Rakdos Cackler"],
                "green": ["Grizzly Bears"],
            }[names]
        )
    ]
    to_phase(s, "declare_attackers", 2)
    attack(s, *[(a, "p1") for a in attackers], pid="p2")
    to_phase(s, "declare_blockers", 2)
    block(s, "p1", *[(wall, a) for a in attackers])
    settle(s)
    assert pt(s, wall) == expected
    assert all(
        pt(s, a)
        == (
            {
                "Goblin Piker": (2, 1),
                "Drudge Skeletons": (1, 1),
                "Rakdos Cackler": (1, 1),
                "Grizzly Bears": (2, 2),
            }[a.name]
        )
        for a in attackers
    )
    roundtrip(s)


def test_mentor_native_attacked_player_target_filter(cards):
    s = game(cards, "Ordruun Mentor")
    source = cast_source(s, "Ordruun Mentor")
    elf = put(s, "Llanowar Elves", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    to_phase(s, "declare_attackers", 4)
    attack(s, (elf, "p2"), (bear, "p3"))
    seen = set()
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        if d.kind == "order":
            ids = [o.id for o in d.options]
        else:
            ids = [o.id for o in d.options]
            assert len(ids) == 1 and ids[0] in (elf.id, bear.id)
            seen.add(ids[0])
        act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        settle(s)
    assert seen == {elf.id, bear.id}
    assert all(
        "first strike" in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c.id]).keywords
        for c in (elf, bear)
    )
    assert "first strike" not in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[source.id]).keywords
    roundtrip(s)


def righteous_block(cards, attacker="Goblin Piker"):
    s = game(cards, "Righteous Indignation")
    source = cast_source(s, "Righteous Indignation")
    wall = put(s, "Wall of Glare", "battlefield")
    enemy = put(s, attacker, "battlefield", "p2")
    to_phase(s, "declare_attackers", 2)
    attack(s, (enemy, "p1"), pid="p2")
    to_phase(s, "declare_blockers", 2)
    block(s, "p1", (wall, enemy))
    return s, source, wall, enemy


@pytest.mark.parametrize("change", ["red_to_blue", "green_to_red"])
def test_righteous_color_is_trigger_time_only_both_directions(cards, change):
    s, source, wall, enemy = righteous_block(
        cards, "Goblin Piker" if change == "red_to_blue" else "Grizzly Bears"
    )
    name = "Cerulean Wisps" if change == "red_to_blue" else "Crimson Wisps"
    spellcard = put(s, name, "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1} if change == "red_to_blue" else {"R": 1})
    act(s, "p1", type="cast_spell", card_id=spellcard.id, targets=[enemy.id])
    settle(s)
    assert pt(s, wall) == ((1, 6) if change == "red_to_blue" else (0, 5))
    roundtrip(s)


@pytest.mark.parametrize("leaves", ["attacker", "blocker", "source"])
def test_righteous_exact_original_blocker_reference_when_objects_leave(cards, leaves):
    s, source, wall, enemy = righteous_block(cards)
    if leaves == "attacker":
        spell(s, "Cloudshift", enemy.id, "p2")
    elif leaves == "blocker":
        spell(s, "Cloudshift", wall.id)
    else:
        spell(s, "Beast Within", source.id)
    assert pt(s, wall) == ((0, 5) if leaves == "blocker" else (1, 6))
    roundtrip(s)


def test_mentor_planeswalker_only_attack_does_not_trigger_player_ability(cards):
    s = game(cards, "Ordruun Mentor")
    cast_source(s, "Ordruun Mentor")
    elf = put(s, "Llanowar Elves", "battlefield")
    walker = put(s, "Jace Beleren", "hand", "p2")
    to_phase(s, "main1", 2)
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1, "U": 2})
    act(s, "p2", type="cast_spell", card_id=walker.id)
    settle(s)
    assert s.state.cards[walker.id].zone == "p2:battlefield"

    to_phase(s, "declare_attackers", 4)
    attack(s, (elf, walker.id))
    settle(s)
    assert not s.state.zones["stack"] and s.state.rules.decision is None
    assert "first strike" not in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[elf.id]).keywords
    roundtrip(s)


def test_mentor_mixed_direct_and_planeswalker_attack_only_direct_attacker_target(cards):
    s = game(cards, "Ordruun Mentor")
    cast_source(s, "Ordruun Mentor")
    elf = put(s, "Llanowar Elves", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    walker = put(s, "Jace Beleren", "hand", "p2")
    to_phase(s, "main1", 2)
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1, "U": 2})
    act(s, "p2", type="cast_spell", card_id=walker.id)
    settle(s)
    assert s.state.cards[walker.id].zone == "p2:battlefield"

    to_phase(s, "declare_attackers", 4)
    attack(s, (elf, "p2"), (bear, walker.id))
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {elf.id}
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[elf.id])
    settle(s)
    assert "first strike" in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[elf.id]).keywords
    assert "first strike" not in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[bear.id]).keywords
    roundtrip(s)


def mentor_both_triggers(cards):
    s = game(cards, "Ordruun Mentor")
    source = cast_source(s, "Ordruun Mentor")
    elf = put(s, "Llanowar Elves", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    to_phase(s, "declare_attackers", 4)
    attack(s, (source, "p2"), (elf, "p2"))
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        ids = [o.id for o in d.options] if d.kind == "order" else [elf.id]
        assert d.kind == "order" or elf.id in [o.id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    return s, source, elf, bear


def test_mentor_whole_counter_first_strike_and_real_combat(cards):
    s, source, elf, bear = mentor_both_triggers(cards)
    settle(s)
    assert (
        pt(s, elf) == (2, 2)
        and "first strike" in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[elf.id]).keywords
    )
    to_phase(s, "declare_blockers", 4)
    block(s, "p2", (bear, elf))
    to_phase(s, "main2", 4)
    assert s.state.cards[bear.id].zone == "p2:graveyard" and s.state.cards[elf.id].zone == "p1:battlefield"
    assert s.state.players["p2"].life == 37
    roundtrip(s)


@pytest.mark.parametrize("change", ["target_grown", "source_dead"])
def test_mentor_official_current_power_or_source_last_known_power(cards, change):
    s, source, elf, bear = mentor_both_triggers(cards)
    spell(s, "Giant Growth", elf.id) if change == "target_grown" else spell(s, "Beast Within", source.id)
    assert pt(s, elf) == ((4, 4) if change == "target_grown" else (2, 2))
    roundtrip(s)


@pytest.mark.parametrize("direct", [False, True])
def test_mentor_native_battle_protector_is_not_player_attack_target(cards, direct):
    s = game(cards, "Ordruun Mentor")
    cast_source(s, "Ordruun Mentor")
    elf = put(s, "Llanowar Elves", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    siege = put(s, "Invasion of Mercadia // Kyren Flamewright", "hand", "p2")
    to_phase(s, "main1", 2)
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1, "R": 1})
    act(s, "p2", type="cast_spell", card_id=siege.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {"p1", "p3"}
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["p3"])
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        print("BATTLE ETB", d)
        act(
            s,
            d.player,
            type="choose",
            decision_id=d.id,
            option_ids=["decline"],
        )
        settle(s)
    assert (
        s.state.cards[siege.id].zone == "p2:battlefield"
        and s.state.rules.protectors[s.state.rules.object_id(siege.id)] == "p3"
    )
    to_phase(s, "declare_attackers", 4)
    attack(s, *([(elf, "p3"), (bear, siege.id)] if direct else [(elf, siege.id)]))
    if direct:
        d = s.state.rules.decision
        assert d is not None and {o.id for o in d.options} == {elf.id}
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[elf.id])
    settle(s)
    assert not s.state.zones["stack"] and s.state.rules.decision is None
    assert ("first strike" in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[elf.id]).keywords) == direct
    assert "first strike" not in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[bear.id]).keywords
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
if os.environ.get('FYODOR_TRIGGERLEAF58_STAGE'):
 from fyodor_triggerleaf58_plugin import install
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


def mentor_single(cards):
    s = game(cards, "Ordruun Mentor")
    source = cast_source(s, "Ordruun Mentor")
    elf = put(s, "Llanowar Elves", "battlefield")
    to_phase(s, "declare_attackers", 4)
    attack(s, (elf, "p2"))
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {elf.id}
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[elf.id])
    return s, source, elf


@pytest.mark.parametrize("change", ["source_dead", "target_blinked", "redirected", "source_control"])
def test_mentor_pending_native_target_relation_and_source_identity(cards, change):
    s, source, elf = mentor_single(cards)
    if change == "source_dead":
        spell(s, "Beast Within", source.id)
    elif change == "target_blinked":
        spell(s, "Cloudshift", elf.id)
    elif change == "redirected":
        # Native table attack update exercises the resolution predicate for an
        # attacker reselected to another player without a new declaration.
        act(s, "p1", type="attack", card_ids=[elf.id], target={"kind": "player", "id": "p3"})
        settle(s)
    else:
        act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
        settle(s)
    expected = change in ("source_dead", "source_control")
    assert (
        "first strike" in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[elf.id]).keywords
    ) == expected
    roundtrip(s)


@pytest.mark.parametrize("name", ["Righteous Indignation", "Ordruun Mentor"])
def test_native_stifle_exact_missing_trigger(cards, name):
    if name == "Righteous Indignation":
        s, source, wall, enemy = righteous_block(cards)
        spell(s, "Stifle", s.state.zones["stack"][-1])
        assert pt(s, wall) == (0, 5)
    else:
        s, source, elf = mentor_single(cards)
        spell(s, "Stifle", s.state.zones["stack"][-1])
        assert "first strike" not in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[elf.id]).keywords
    roundtrip(s)


def test_righteous_cold_paired_event_preserves_original_blocker(cards, tmp_path):
    s, source, wall, enemy = righteous_block(cards)
    s = fresh(s, cards, tmp_path / "righteous.json", s.state.rules.priority, {"type": "pass_priority"})
    assert pt(s, wall) == (1, 6) and pt(s, enemy) == (2, 1)
    roundtrip(s)


def test_mentor_cold_attacked_player_bound_target_and_cleanup(cards, tmp_path):
    s, source, elf = mentor_single(cards)
    s = fresh(s, cards, tmp_path / "mentor.json", s.state.rules.priority, {"type": "pass_priority"})
    assert "first strike" in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[elf.id]).keywords
    to_phase(s, "main1", 5)
    assert "first strike" not in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[elf.id]).keywords
    roundtrip(s)
