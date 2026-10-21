"""Fixed owner-library placements share private ordering and one native move batch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.view import decision_view
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
        json.loads((Path(__file__).parent / "fixtures/library_placements51_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="lpf", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    names = [
        name,
        "Grizzly Bears",
        "Llanowar Elves",
        "Holy Strength",
        "Pacifism",
        "Forest",
        "Island",
        "Sol Ring",
        "Arcane Signet",
    ]
    s = table(cards, names, names, names)
    source = put(s, name, "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    return s, source


def cast(s, source, targets=()):
    amounts = {
        "Terminus": {"C": 4, "W": 2},
        "Hallowed Burial": {"C": 3, "W": 2},
        "Harmonic Convergence": {"C": 2, "G": 1},
        "Plow Under": {"C": 3, "G": 2},
        "Rebuking Ceremony": {"C": 3, "G": 2},
    }
    act(s, "p1", type="add_mana", player="p1", mana=amounts[source.name])
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=source.id,
        targets=[c.id for c in targets],
        target_counts=[2] if targets else [],
    )
    settle(s)


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    settle(s)


def assert_single_batch(s, cards):
    ids = {c.id for c in cards}
    events = [
        e
        for e in s.state.rules.events
        if e.kind == "zone_change" and e.card in ids and e.to_zone.endswith(":library")
    ]
    assert len(events) == len(ids) and len({e.batch for e in events}) == 1


@pytest.mark.parametrize(
    "name", ["Terminus", "Hallowed Burial", "Harmonic Convergence", "Plow Under", "Rebuking Ceremony"]
)
def test_whole_coverage(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", ["Terminus", "Hallowed Burial"])
def test_creature_sweep_owners_private_order_and_one_batch(cards, name):
    s, source = setup(cards, name)
    ours = [put(s, n, "battlefield") for n in ("Grizzly Bears", "Llanowar Elves")]
    other = put(s, "Grizzly Bears", "battlefield", "p2")
    land = put(s, "Forest", "battlefield")
    act(s, "p2", type="set_controller", card_ids=[other.id], player="p1")
    cast(s, source)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.kind == "order"
    assert {o.id for o in d.options} == {c.id for c in ours}
    assert "options" not in decision_view(s.state, d, "p2")
    assert all(s.state.cards[c.id].zone.endswith(":battlefield") for c in [*ours, other])
    choose(s, [c.id for c in ours])
    assert s.state.zones["p1:library"][-2:] == [ours[1].id, ours[0].id]
    assert s.state.zones["p2:library"][-1] == other.id
    assert s.state.cards[land.id].zone == "p1:battlefield"
    assert_single_batch(s, [*ours, other])
    roundtrip(s)


@pytest.mark.parametrize(
    "name,types", [("Plow Under", ["Forest", "Island"]), ("Rebuking Ceremony", ["Sol Ring", "Arcane Signet"])]
)
def test_two_targets_shared_owner_orders_top_privately(cards, name, types):
    s, source = setup(cards, name)
    targets = [put(s, n, "battlefield", "p2") for n in types]
    cast(s, source, targets)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.kind == "order"
    assert "options" not in decision_view(s.state, d, "p1")
    assert all(s.state.cards[c.id].zone == "p2:battlefield" for c in targets)
    choose(s, [c.id for c in reversed(targets)])
    assert s.state.zones["p2:library"][:2] == [c.id for c in reversed(targets)]
    assert_single_batch(s, targets)
    roundtrip(s)


def test_all_enchantments_go_to_owners_top_without_targeting(cards):
    s, source = setup(cards, "Harmonic Convergence")
    bear = put(s, "Grizzly Bears", "battlefield")
    auras = [put(s, n, "battlefield") for n in ("Holy Strength", "Pacifism")]
    for aura in auras:
        act(s, "p1", type="attach", card_ids=[aura.id], to=bear.id)
    opponent = put(s, "Holy Strength", "battlefield", "p2")
    act(s, "p2", type="attach", card_ids=[opponent.id], to=bear.id)
    cast(s, source)
    assert all(s.state.cards[c.id].zone.endswith(":battlefield") for c in [*auras, opponent])
    choose(s, [c.id for c in auras])
    assert s.state.zones["p1:library"][:2] == [c.id for c in auras]
    assert s.state.zones["p2:library"][0] == opponent.id
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    assert_single_batch(s, [*auras, opponent])
    roundtrip(s)


@pytest.mark.parametrize("remaining", [0, 1])
def test_target_library_mover_fizzles_or_moves_only_still_legal_target(cards, remaining):
    s, source = setup(cards, "Plow Under")
    targets = [put(s, n, "battlefield", "p2") for n in ("Forest", "Island")]
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "G": 2})
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[c.id for c in targets], target_counts=[2])
    for c in targets[remaining:]:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "graveyard"})
    settle(s)
    assert s.state.rules.decision is None
    for i, c in enumerate(targets):
        assert s.state.cards[c.id].zone == ("p2:library" if i < remaining else "p2:graveyard")
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("command", [True, False])
def test_fixed_sweep_commander_choice_precedes_private_order_and_all_moves(cards, command):
    s, source = setup(cards, "Hallowed Burial")
    commander = put(s, "Krenko, Mob Boss", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    other = put(s, "Grizzly Bears", "battlefield", "p2")
    cast(s, source)
    d = s.state.rules.decision
    assert d is not None and d.resume["stage"] == "commander"
    assert all(s.state.cards[c.id].zone.endswith(":battlefield") for c in (commander, bear, other))
    choose(s, ["yes" if command else "no"])
    if not command:
        assert all(s.state.cards[c.id].zone.endswith(":battlefield") for c in (commander, bear, other))
        choose(s, [commander.id, bear.id])
    assert s.state.cards[commander.id].zone == ("p1:command" if command else "p1:library")
    assert s.state.cards[bear.id].zone == "p1:library" and s.state.cards[other.id].zone == "p2:library"
    events = [
        e
        for e in s.state.rules.events
        if e.kind == "zone_change"
        and e.card in {commander.id, bear.id, other.id}
        and (e.from_zone or "").endswith(":battlefield")
    ]
    assert len(events) == 3 and len({e.batch for e in events}) == 1
    roundtrip(s)


def test_terminus_actual_miracle_cast_for_white(cards):
    from tests.test_rules_wave18e_casting import _first_draw_with_opt, find

    s = _first_draw_with_opt(cards, "Terminus")
    source = find(s, "Terminus")
    assert s.state.rules.miracle == [source.id]
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="miracle_reveal", card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    choose(s, ["yes"])
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert all(
        not (c.zone.endswith(":battlefield") and c.name == "Elvish Visionary") for c in s.state.cards.values()
    )
    roundtrip(s)


def test_fixed_owner_order_survives_true_cold_save_before_single_batch(cards, tmp_path):
    import os
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    s, source = setup(cards, "Hallowed Burial")
    targets = [put(s, n, "battlefield") for n in ("Grizzly Bears", "Llanowar Elves")]
    other = put(s, "Grizzly Bears", "battlefield", "p2")
    cast(s, source)
    d = s.state.rules.decision
    assert d is not None and d.kind == "order"
    path = tmp_path / "fixed-order.json"
    path.write_text(s.state.model_dump_json())
    code = """
import json,os,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(path.parent/'cold-images'))
s=GameSession(GameState.model_validate_json(path.read_text()),cards=repo)
s.perform(sys.argv[3],json.loads(sys.argv[4]))
for _ in range(40):
 if s.state.rules.decision or not s.state.zones.get('stack'):break
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
path.write_text(s.state.model_dump_json());repo.close()
"""
    payload = {"type": "choose", "decision_id": d.id, "option_ids": [c.id for c in targets]}
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), str(cards.db_path), d.player, json.dumps(payload)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    s = GameSession(GameState.model_validate_json(path.read_text()), cards=cards)
    assert s.state.zones["p1:library"][-2:] == [targets[1].id, targets[0].id]
    assert s.state.zones["p2:library"][-1] == other.id
    assert_single_batch(s, [*targets, other])
    roundtrip(s)


def test_fixed_sweep_collects_each_owners_order_before_any_move(cards):
    s, source = setup(cards, "Hallowed Burial")
    piles = {
        p: [put(s, n, "battlefield", p) for n in ("Grizzly Bears", "Llanowar Elves")]
        for p in ("p1", "p2", "p3")
    }
    cast(s, source)
    all_cards = [c for pile in piles.values() for c in pile]
    for p in ("p1", "p2", "p3"):
        d = s.state.rules.decision
        assert d is not None and d.player == p and d.kind == "order"
        assert all(s.state.cards[c.id].zone.endswith(":battlefield") for c in all_cards)
        assert all(
            "options" not in decision_view(s.state, d, other) for other in ("p1", "p2", "p3") if other != p
        )
        choose(s, [c.id for c in piles[p]])
    for p in piles:
        assert s.state.zones[p + ":library"][-2:] == [piles[p][1].id, piles[p][0].id]
    assert_single_batch(s, all_cards)
    roundtrip(s)
