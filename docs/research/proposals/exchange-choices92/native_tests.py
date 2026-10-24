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
from tests.test_rules_designations import pick, put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / "fixtures/exchange_choices92_cards.json").read_text())
NAMES = [d["name"] for d in DATA[:3]]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="e92", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup92(cards):
    names = list(
        dict.fromkeys(
            [c["name"] for c in DATA]
            + [
                "Grizzly Bears",
                "Llanowar Elves",
                "Wall of Roots",
                "Sol Ring",
                "Cloudshift",
                "Murder",
                "Counterspell",
            ]
        )
    )
    return table(cards, names, names, names)


@pytest.mark.parametrize("name", NAMES)
def test_whole92(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def cast92(s, name, targets=(), counts=()):
    spell = put(s, name, "hand")
    mana(s, C=20, U=20, R=20)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=list(targets), target_counts=list(counts))
    settle(s)
    return spell


def test_confusion_actual_cast_self_entry_mandatory_exchange92(cards):
    s = setup92(cards)
    other = put(s, "Glorious Anthem", "battlefield", pid="p2")
    start(s)
    source = cast92(s, NAMES[0])
    assert s.state.rules.decision.player == "p1"
    assert {o.id for o in s.state.rules.decision.options} == {other.id}
    pick(s, [other.id])
    settle(s)
    assert source.controller == "p2" and other.controller == "p1"


def test_confusion_entering_opponent_chooses_other_player_target92(cards):
    s = setup92(cards)
    source = put(s, NAMES[0], "battlefield")
    mine = put(s, "Llanowar Elves", "battlefield")
    third = put(s, "Grizzly Bears", "battlefield", pid="p3")
    bear = put(s, "Grizzly Bears", "hand", pid="p2")
    start(s, turn=5)
    mana(s, pid="p2", C=1, G=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=bear.id)
    settle(s)
    assert s.state.rules.decision.player == "p2"
    assert {o.id for o in s.state.rules.decision.options} == {mine.id, third.id}
    pick(s, [mine.id])
    settle(s)
    assert bear.controller == "p1" and mine.controller == "p2" and source.controller == "p1"


@pytest.mark.parametrize("zero", [False, True])
def test_cultural_actual_cast_chooses_equal_nontarget_cohorts92(cards, zero):
    s = setup92(cards)
    mine = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield")
    enemy = put(s, "Slippery Bogle", "battlefield", pid="p2")
    wall = put(s, "Wall of Roots", "battlefield", pid="p2")
    third = put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s)
    cast92(s, NAMES[1], ["p1", "p2"], [1, 1])
    d = s.state.rules.decision
    assert d.player == "p1" and d.min_choices == 0 and d.max_choices == 2
    assert {o.id for o in d.options} == {mine.id, elf.id}
    pick(s, [] if zero else [mine.id, elf.id])
    settle(s)
    if not zero:
        d = s.state.rules.decision
        assert d.player == "p1" and d.min_choices == d.max_choices == 2
        pick(s, [enemy.id, wall.id])
        settle(s)
    assert mine.controller == elf.controller == ("p1" if zero else "p2")
    assert enemy.controller == wall.controller == ("p2" if zero else "p1") and third.controller == "p2"


def test_juxtapose_actual_cast_sequential_artifact_creature_can_exchange_twice92(cards):
    s = setup92(cards)
    myr = put(s, "Myr Enforcer", "battlefield")
    ring = put(s, "Sol Ring", "battlefield")
    enemy = put(s, "Colossal Dreadmaw", "battlefield", pid="p2")
    orn = put(s, "Ornithopter", "battlefield", pid="p2")
    start(s)
    cast92(s, NAMES[2], ["p2"])
    assert (
        myr.controller == "p1"
        and enemy.controller == "p1"
        and ring.controller == "p2"
        and orn.controller == "p2"
    )


def test_juxtapose_each_controller_chooses_greatest_tie92(cards):
    s = setup92(cards)
    mine = put(s, "Grizzly Bears", "battlefield")
    wall = put(s, "Wall of Roots", "battlefield")
    enemy = put(s, "Grizzly Bears", "battlefield", pid="p2")
    their_wall = put(s, "Wall of Roots", "battlefield", pid="p2")
    start(s)
    cast92(s, NAMES[2], ["p2"])
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {mine.id, wall.id}
    pick(s, [mine.id])
    settle(s)
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} == {enemy.id, their_wall.id}
    pick(s, [their_wall.id])
    settle(s)
    assert (
        mine.controller == "p2"
        and their_wall.controller == "p1"
        and wall.controller == "p1"
        and enemy.controller == "p2"
    )


def test_confusion_artifact_land_entry_can_target_land92(cards):
    s = setup92(cards)
    put(s, NAMES[0], "battlefield")
    land = put(s, "Forest", "battlefield")
    seat = put(s, "Seat of the Synod", "hand", pid="p2")
    start(s, turn=5)
    wait_priority(s, "p2")
    act(s, "p2", type="play_land", card_id=seat.id)
    settle(s)
    assert s.state.rules.decision.player == "p2"
    assert land.id in {o.id for o in s.state.rules.decision.options}
    pick(s, [land.id])
    settle(s)
    assert seat.controller == "p1" and land.controller == "p2"


def test_juxtapose_missing_creatures_still_exchanges_artifacts92(cards):
    s = setup92(cards)
    ring = put(s, "Sol Ring", "battlefield")
    orn = put(s, "Ornithopter", "battlefield", pid="p2")
    start(s)
    cast92(s, NAMES[2], ["p2"])
    assert ring.controller == "p2" and orn.controller == "p1"


def confusion_pair92(cards, actor="Grizzly Bears"):
    s = setup92(cards)
    put(s, NAMES[0], "battlefield")
    mine = put(s, "Llanowar Elves", "battlefield")
    third = put(s, "Grizzly Bears", "battlefield", pid="p3")
    entering = put(s, actor, "hand", pid="p2")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    mana(s, pid="p2", C=7, G=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=entering.id)
    settle(s)
    return s, entering, mine, third


def test_confusion_blink_original_entry_cannot_exchange_new_incarnation92(cards):
    from app.rules.plan import Plan

    s, bear, mine, third = confusion_pair92(cards)
    original = Plan(s.state, "p2", s.cards, None).oid(bear)
    pick(s, [mine.id])
    blink = put(s, "Cloudshift", "hand", pid="p2")
    mana(s, pid="p2", W=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=blink.id, targets=[bear.id])
    settle(s)
    assert s.state.rules.decision.player == "p2"
    pick(s, [third.id])
    settle(s)
    assert Plan(s.state, "p2", s.cards, None).oid(bear) != original
    assert bear.controller == "p3" and third.controller == "p2" and mine.controller == "p1"


def test_confusion_live_actor_type_change_makes_artifact_target_illegal92(cards):
    from app.rules.plan import Plan

    s = setup92(cards)
    put(s, NAMES[0], "battlefield")
    ring = put(s, "Sol Ring", "battlefield")
    copy = put(s, "Grizzly Bears", "battlefield")
    myr = put(s, "Myr Enforcer", "hand", pid="p2")
    change = put(s, "Cytoshape", "hand", pid="p2")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    mana(s, pid="p2", C=7)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=myr.id)
    settle(s)
    pick(s, [ring.id])
    mana(s, pid="p2", C=1, G=1, U=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=change.id, targets=[myr.id])
    settle(s)
    pick(s, [copy.id])
    settle(s)
    assert Plan(s.state, "p2", s.cards, None).ch(myr).types == frozenset({"Creature"})
    assert ring.controller == "p1" and myr.controller == "p2"


def cold92(s, tmp_path, body):
    import subprocess
    import sys

    import app

    saved = tmp_path / "exchange92.json"
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


@pytest.mark.parametrize("mode", ["confusion", "cultural", "juxtapose"])
def test_genuine_cold_native_exchange_choice92(cards, tmp_path, mode):
    if mode == "confusion":
        s, bear, mine, third = confusion_pair92(cards)
        body = f"assert s.state.rules.decision.player=='p2'\npick(s,[{mine.id!r}]);settle(s)\nassert s.state.cards[{bear.id!r}].controller=='p1'\nassert s.state.cards[{mine.id!r}].controller=='p2'"
    else:
        s = setup92(cards)
        mine = put(s, "Grizzly Bears", "battlefield")
        wall = put(s, "Wall of Roots", "battlefield")
        enemy = put(s, "Grizzly Bears", "battlefield", pid="p2")
        other = put(s, "Wall of Roots", "battlefield", pid="p2")
        if mode == "cultural":
            put(s, "Llanowar Elves", "battlefield", pid="p2")
        start(s)
        cast92(
            s,
            NAMES[1] if mode == "cultural" else NAMES[2],
            ["p1", "p2"] if mode == "cultural" else ["p2"],
            [1, 1] if mode == "cultural" else [],
        )
        pick(s, [mine.id, wall.id] if mode == "cultural" else [mine.id])
        settle(s)
        body = f"assert s.state.rules.decision.player=={'p1' if mode == 'cultural' else 'p2'!r}\npick(s,{[enemy.id, other.id] if mode == 'cultural' else [other.id]!r});settle(s)\nassert s.state.cards[{mine.id!r}].controller=='p2'\nassert s.state.cards[{other.id!r}].controller=='p1'"
    cold92(s, tmp_path, body)


def test_cultural_caster_chooses_cohorts_between_two_opponents92(cards):
    s = setup92(cards)
    first = put(s, "Grizzly Bears", "battlefield", pid="p2")
    second = put(s, "Llanowar Elves", "battlefield", pid="p3")
    start(s)
    cast92(s, NAMES[1], ["p2", "p3"], [1, 1])
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {first.id}
    pick(s, [first.id])
    settle(s)
    assert first.controller == "p3" and second.controller == "p2"


def test_cultural_another_target_player_rejects_same_player_atomically92(cards):
    from app.game.errors import ActionError

    s = setup92(cards)
    spell = put(s, NAMES[1], "hand")
    start(s)
    mana(s, C=4, U=2)
    wait_priority(s, "p1")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p1", "p1"], target_counts=[1, 1])
    assert s.state.model_dump(mode="json") == before
