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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / "fixtures/zone_exchanges94_cards.json").read_text())


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="zex94", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup94(cards, extra=()):
    names = list(
        dict.fromkeys(
            ["Harness Infinity", "Morality Shift", *extra]
            + ["Grizzly Bears", "Llanowar Elves", "Sol Ring", "Forest", "Murder"]
        )
    )
    return table(cards, names, names, names)


def cast94(s, name):
    source = put(s, name, "hand")
    wait_priority(s, "p1")
    mana(s, C=20, B=20, G=20)
    act(s, "p1", type="cast_spell", card_id=source.id)
    before = {z: list(s.state.zones.get(f"p1:{z}", [])) for z in ("hand", "graveyard", "library")}
    settle(s)
    return source, before


@pytest.mark.parametrize("name", ["Harness Infinity", "Morality Shift"])
def test_whole_exact_zone_exchange94(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_harness_actual_original_cohorts_and_self_exile94(cards):
    s = setup94(cards)
    start(s)
    put(s, "Grizzly Bears", "hand")
    put(s, "Llanowar Elves", "graveyard")
    source, before = cast94(s, "Harness Infinity")
    assert s.state.rules.decision is None
    assert set(s.state.zones["p1:hand"]) == set(before["graveyard"])
    assert set(s.state.zones["p1:graveyard"]) == set(before["hand"])
    assert source.zone == "p1:exile"


def test_harness_no_madness_or_waste_not_discard94(cards):
    s = setup94(cards, ["Waste Not", "Fiery Temper"])
    put(s, "Waste Not", "battlefield", pid="p2")
    start(s)
    temper = put(s, "Fiery Temper", "hand")
    source, before = cast94(s, "Harness Infinity")
    assert s.state.rules.decision is None and temper.zone == "p1:graveyard"
    assert source.zone == "p1:exile"
    assert not any(c.is_token and c.controller == "p2" for c in s.state.cards.values())
    assert not any(n.player == "p1" and n.kind == "discard" for n in s.state.rules.turn_log.facts)
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_morality_actual_original_library_graveyard_then_shuffle94(cards):
    s = setup94(cards)
    start(s)
    put(s, "Grizzly Bears", "graveyard")
    put(s, "Llanowar Elves", "graveyard")
    source, before = cast94(s, "Morality Shift")
    assert s.state.rules.decision is None
    assert set(s.state.zones["p1:graveyard"]) == set(before["library"]) | {source.id}
    assert len(s.state.zones["p1:library"]) == len(before["graveyard"])
    assert {s.state.cards[cid].name for cid in s.state.zones["p1:library"]} == {
        "Grizzly Bears",
        "Llanowar Elves",
    }
    assert not set(before["graveyard"]) & set(s.state.zones["p1:library"])


@pytest.mark.parametrize(
    "name,zone",
    [
        ("Harness Infinity", "hand"),
        ("Harness Infinity", "graveyard"),
        ("Morality Shift", "library"),
        ("Morality Shift", "graveyard"),
    ],
)
def test_zone_exchange_empty_side_still_moves_other_original_cohort94(cards, name, zone):
    s = setup94(cards)
    start(s)
    source = put(s, name, "hand")
    for cid in list(s.state.zones.get(f"p1:{zone}", [])):
        if cid != source.id:
            act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "exile"})
    put(
        s,
        "Grizzly Bears",
        "graveyard" if zone in ("hand", "library") else ("hand" if name == "Harness Infinity" else "library"),
    )
    source, before = cast94(s, name)
    assert s.state.rules.decision is None
    if name == "Harness Infinity":
        assert set(s.state.zones["p1:hand"]) == set(before["graveyard"])
        assert set(s.state.zones["p1:graveyard"]) == set(before["hand"])
        assert source.zone == "p1:exile"
    else:
        assert set(s.state.zones["p1:graveyard"]) == set(before["library"]) | {source.id}
        assert len(s.state.zones["p1:library"]) == len(before["graveyard"])


def test_harness_rest_in_peace_actual_routes_no_discard94(cards):
    s = setup94(cards, ["Rest in Peace", "Fiery Temper"])
    put(s, "Rest in Peace", "battlefield")
    start(s)
    temper = put(s, "Fiery Temper", "hand")
    source, before = cast94(s, "Harness Infinity")
    assert s.state.rules.decision is None
    assert temper.zone == "p1:exile" and source.zone == "p1:exile"
    assert not s.state.zones.get("p1:graveyard", [])
    assert set(before["hand"]) <= set(s.state.zones["p1:exile"])


def test_harness_original_graveyard_leaves_one_native_tormod_trigger94(cards):
    s = setup94(cards, ["Tormod, the Desecrator"])
    put(s, "Tormod, the Desecrator", "battlefield")
    start(s)
    put(s, "Grizzly Bears", "graveyard")
    put(s, "Llanowar Elves", "graveyard")
    source, before = cast94(s, "Harness Infinity")
    assert set(s.state.zones["p1:hand"]) == set(before["graveyard"])
    zombies = [c for c in s.state.cards.values() if c.is_token and c.controller == "p1"]
    assert len(zombies) == 1 and zombies[0].tapped


def progenitus_choice94(cards):
    s = setup94(cards, ["Progenitus", "Rest in Peace"])
    put(s, "Rest in Peace", "battlefield")
    start(s)
    progenitus = put(s, "Progenitus", "hand")
    source, before = cast94(s, "Harness Infinity")
    d = s.state.rules.decision
    assert d and d.player == "p1" and d.resume["step"] == "exchange_zones94"
    assert progenitus.zone == "p1:hand" and source.zone == "stack"
    assert s.view("p2")["rules"]["decision"]["kind"] == "waiting"
    assert "Progenitus" not in json.dumps(s.view("p2")["rules"]["decision"])
    return s, progenitus, source, before


@pytest.mark.parametrize("replacement", ["Rest in Peace", "Progenitus"])
def test_harness_actual_native_replacement_choice_before_original_move94(cards, replacement):
    from tests.test_rules_designations import pick

    s, progenitus, source, before = progenitus_choice94(cards)
    option = next(o.id for o in s.state.rules.decision.options if o.label == replacement)
    pick(s, [option])
    settle(s)
    assert s.state.rules.decision is None and source.zone == "p1:exile"
    if replacement == "Rest in Peace":
        assert progenitus.zone == "p1:exile"
    else:
        assert any(c.name == "Progenitus" and c.zone == "p1:library" for c in s.state.cards.values())


def graveyard_commander94(cards):
    from tests.test_rules_designations import pick

    s = setup94(cards, ["Tormod, the Desecrator"])
    commander = put(s, "Tormod, the Desecrator", "battlefield")
    act(s, "p1", type="set_commander", card_id=commander.id)
    kill = put(s, "Murder", "hand")
    start(s)
    mana(s, C=1, B=2)
    act(s, "p1", type="cast_spell", card_id=kill.id, targets=[commander.id])
    settle(s)
    assert commander.zone == "p1:graveyard" and s.state.rules.decision.player == "p1"
    pick(s, ["no"])
    settle(s)
    assert commander.zone == "p1:graveyard" and s.state.rules.decision is None
    return s, commander


@pytest.mark.parametrize("name", ["Harness Infinity", "Morality Shift"])
@pytest.mark.parametrize("answer", ["yes", "no"])
def test_actual_previous_commander_graveyard_decline_then_hidden_replacement94(cards, name, answer):
    from tests.test_rules_designations import pick

    s, commander = graveyard_commander94(cards)
    source, before = cast94(s, name)
    d = s.state.rules.decision
    assert d.player == "p1" and d.resume["step"] == "exchange_zones94"
    assert commander.zone == "p1:graveyard" and source.zone == "stack"
    assert set(s.state.zones["p1:graveyard"]) == set(before["graveyard"])
    assert set(s.state.zones["p1:library"]) == set(before["library"])
    pick(s, [answer])
    settle(s)
    assert s.state.rules.decision is None
    if answer == "yes":
        assert commander.zone == "p1:command"
    else:
        where = "hand" if name == "Harness Infinity" else "library"
        assert any(
            c.name == "Tormod, the Desecrator" and c.zone == f"p1:{where}" for c in s.state.cards.values()
        )


def cold94(s, tmp_path, body):
    import subprocess
    import sys

    import app

    saved = tmp_path / "zone94.json"
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


def test_genuine_cold_prepared_zone_replacement94(cards, tmp_path):
    s, progenitus, source, before = progenitus_choice94(cards)
    option = next(o.id for o in s.state.rules.decision.options if o.label == "Rest in Peace")
    cold94(
        s,
        tmp_path,
        f"pick(s,[{option!r}]);settle(s)\nassert s.state.cards[{progenitus.id!r}].zone=='p1:exile'\nassert s.state.cards[{source.id!r}].zone=='p1:exile'\nassert s.state.rules.decision is None",
    )


def test_genuine_cold_original_commander_zone_exchange94(cards, tmp_path):
    s, commander = graveyard_commander94(cards)
    source, before = cast94(s, "Morality Shift")
    assert s.state.rules.decision.resume["step"] == "exchange_zones94"
    cold94(
        s,
        tmp_path,
        f"pick(s,['yes']);settle(s)\nassert s.state.cards[{commander.id!r}].zone=='p1:command'\nassert s.state.cards[{source.id!r}].zone=='p1:graveyard'\nassert s.state.rules.decision is None",
    )


def test_ordinary_actual_discard_retains_native_madness_and_waste_not94(cards):
    from tests.test_rules_designations import pick

    s = setup94(cards, ["Mind Rot", "Waste Not", "Fiery Temper"])
    put(s, "Waste Not", "battlefield")
    start(s)
    temper = put(s, "Fiery Temper", "hand", pid="p2")
    forest = put(s, "Forest", "hand", pid="p2")
    rot = put(s, "Mind Rot", "hand")
    mana(s, C=2, B=1)
    act(s, "p1", type="cast_spell", card_id=rot.id, targets=["p2"])
    settle(s)
    assert s.state.rules.decision.player == "p2"
    pick(s, [temper.id, forest.id])
    settle(s)
    assert s.state.rules.decision.player == "p2" and "madness" in s.state.rules.decision.prompt.lower()
    assert temper.zone == "p2:exile"
    pick(s, ["no"])
    settle(s)
    assert temper.zone == "p2:graveyard"
    assert sum(1 for f in s.state.rules.turn_log.facts if f.kind == "discard" and f.player == "p2") == 2
    from tests.game_helpers import mana_pool

    assert mana_pool(s, "p1").get("B", 0) == 2
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_morality_large_original_cohort_is_one_native_event94(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    mine = deck(
        cards,
        "Krenko, Mob Boss",
        [(1, "Morality Shift"), (1, "Sidisi, Brood Tyrant"), (300, "Grizzly Bears")],
    )
    other = deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")])
    s = GameSession(
        enable(
            new_game(
                [
                    PlayerSetup("Alice", cards=mine),
                    PlayerSetup("Bob", cards=other),
                    PlayerSetup("Carol", cards=other),
                ],
                shuffle=False,
            )
        ),
        cards=cards,
    )
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", response="on")
    from tests.test_rules_wave30m_durations import to_phase

    put(s, "Sidisi, Brood Tyrant", "battlefield")
    to_phase(s, "main1", turn=1)
    source, before = cast94(s, "Morality Shift")
    assert len(before["library"]) > 250
    assert set(s.state.zones["p1:graveyard"]) == set(before["library"]) | {source.id}
    assert not s.state.zones.get("p1:library", [])
    assert len([c for c in s.state.cards.values() if c.is_token and c.controller == "p1"]) == 1
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_morality_native_graveyard_order_covers_original_library94(cards):
    from tests.test_rules_designations import pick

    s = setup94(cards)
    start(s)
    act(s, "p1", type="set_prefs", ask_graveyard_order=True)
    source = put(s, "Morality Shift", "hand")
    original = list(s.state.zones["p1:library"])
    mana(s, C=5, B=2)
    act(s, "p1", type="cast_spell", card_id=source.id)
    for _ in range(20):
        if s.state.rules.decision:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d and d.player == "p1" and d.resume["step"] == "graveyard_order"
    assert {o.id for o in d.options} == set(original)
    ordered = sorted(original)
    pick(s, ordered)
    settle(s)
    assert [cid for cid in s.state.zones["p1:graveyard"] if cid in original] == list(reversed(ordered))


def test_morality_rest_in_peace_replaces_original_library_but_not_original_graveyard94(cards):
    s = setup94(cards, ["Rest in Peace"])
    start(s)
    put(s, "Grizzly Bears", "graveyard")
    put(s, "Llanowar Elves", "graveyard")
    put(s, "Rest in Peace", "battlefield")  # A valid snapshot after its entry trigger was countered.
    source, before = cast94(s, "Morality Shift")
    assert s.state.rules.decision is None and source.zone == "p1:exile"
    assert not s.state.zones.get("p1:graveyard", [])
    assert set(before["library"]) <= set(s.state.zones["p1:exile"])
    assert {s.state.cards[cid].name for cid in s.state.zones["p1:library"]} == {
        "Grizzly Bears",
        "Llanowar Elves",
    }
