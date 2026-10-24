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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / "fixtures/exchange_conditions91_cards.json").read_text())


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"],
            set_code="e91",
            number=str(i),
            **{k: v for k, v in c.items() if k != "name"},
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup91(cards):
    names = [c["name"] for c in DATA] + [
        "Grizzly Bears",
        "Llanowar Elves",
        "Sol Ring",
        "Forest",
        "Mountain",
        "Pacifism",
        "Cloudshift",
        "Counterspell",
        "Murder",
    ]
    return table(cards, names, names, names)


@pytest.mark.parametrize("name", ["Modify Memory", "Gauntlets of Chaos", "Gilded Drake"])
def test_whole91(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("mine", [False, True])
def test_modify_actual_printed_cast_control_after_exchange91(cards, mine):
    s = setup91(cards)
    first = put(s, "Grizzly Bears", "battlefield", pid="p1" if mine else "p2")
    second = put(s, "Llanowar Elves", "battlefield", pid="p3")
    spell = put(s, "Modify Memory", "hand")
    start(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, C=3, U=2)
    wait_priority(s, "p1")
    before = len(s.state.zones["p1:hand"])
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=spell.id,
        targets=[first.id, second.id],
        target_counts=[2],
    )
    settle(s)
    assert first.controller == "p3" and second.controller == ("p1" if mine else "p2")
    assert len(s.state.zones["p1:hand"]) == before - 1 + (0 if mine else 3)


def test_gauntlets_actual_artifact_exchange_cost91(cards):
    s = setup91(cards)
    gauntlets = put(s, "Gauntlets of Chaos", "battlefield")
    first = put(s, "Sol Ring", "battlefield")
    second = put(s, "Sol Ring", "battlefield", pid="p2")
    start(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, C=5)
    wait_priority(s, "p1")
    index = next(
        a.index for a in Plan(s.state, "p1", s.cards, None).ch(gauntlets).abilities if a.kind == "activated"
    )
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=gauntlets.id,
        ability=index,
        targets=[first.id, second.id],
        target_counts=[1, 1],
    )
    settle(s)
    assert gauntlets.zone == "p1:graveyard" and first.controller == "p2" and second.controller == "p1"


@pytest.mark.parametrize("mode", ["none", "legal", "removed"])
def test_drake_actual_printed_cast_exchange_or_sacrifice91(cards, mode):
    from tests.test_rules_designations import pick

    s = setup91(cards)
    enemy = put(s, "Grizzly Bears", "battlefield", pid="p2")
    drake = put(s, "Gilded Drake", "hand")
    kill = put(s, "Murder", "hand")
    start(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, C=1, U=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=drake.id)
    settle(s)
    assert s.state.rules.decision is not None
    pick(s, [] if mode == "none" else [enemy.id])
    if mode == "removed":
        mana(s, C=1, B=2)
        wait_priority(s, "p1")
        act(s, "p1", type="cast_spell", card_id=kill.id, targets=[enemy.id])
    settle(s)
    if mode == "legal":
        assert drake.zone == "p2:battlefield" and drake.controller == "p2" and enemy.controller == "p1"
    else:
        assert drake.zone == "p1:graveyard"
        assert enemy.controller == "p2"


@pytest.mark.parametrize("break_exchange", [False, True])
def test_gauntlets_actual_cast_auras_only_after_complete_exchange91(cards, break_exchange):
    s = setup91(cards)
    gauntlets = put(s, "Gauntlets of Chaos", "hand")
    mine = put(s, "Grizzly Bears", "battlefield")
    enemy = put(s, "Llanowar Elves", "battlefield", pid="p2")
    aura = put(s, "Pacifism", "hand")
    kill = put(s, "Murder", "hand")
    start(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, C=5)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=gauntlets.id)
    settle(s)
    mana(s, C=1, W=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[enemy.id])
    settle(s)
    assert aura.attached_to == enemy.id
    mana(s, C=5)
    wait_priority(s, "p1")
    index = next(
        a.index for a in Plan(s.state, "p1", s.cards, None).ch(gauntlets).abilities if a.kind == "activated"
    )
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=gauntlets.id,
        ability=index,
        targets=[mine.id, enemy.id],
        target_counts=[1, 1],
    )
    if break_exchange:
        mana(s, C=1, B=2)
        wait_priority(s, "p1")
        act(s, "p1", type="cast_spell", card_id=kill.id, targets=[mine.id])
    settle(s)
    assert gauntlets.zone == "p1:graveyard"
    if break_exchange:
        assert aura.zone == "p1:battlefield" and enemy.controller == "p2"
    else:
        assert aura.zone == "p1:graveyard" and enemy.controller == "p1" and mine.controller == "p2"


@pytest.mark.parametrize("mine", [False, True])
def test_modify_one_target_gone_rechecks_control_and_draw91(cards, mine):
    s = setup91(cards)
    first = put(s, "Grizzly Bears", "battlefield", pid="p1" if mine else "p2")
    second = put(s, "Llanowar Elves", "battlefield", pid="p3")
    spell = put(s, "Modify Memory", "hand")
    kill = put(s, "Murder", "hand")
    start(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, C=4, U=1)
    wait_priority(s, "p1")
    before = len(s.state.zones["p1:hand"])
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=spell.id,
        targets=[first.id, second.id],
        target_counts=[2],
    )
    mana(s, C=1, B=2)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=kill.id,
        targets=[second.id if mine else first.id],
    )
    settle(s)
    assert first.controller == ("p1" if mine else "p2") and second.controller == "p3"
    assert len(s.state.zones["p1:hand"]) == before - 2 + (0 if mine else 3)


def test_gauntlets_target_its_sacrificed_source_cannot_exchange91(cards):
    s = setup91(cards)
    gauntlets = put(s, "Gauntlets of Chaos", "battlefield")
    enemy = put(s, "Sol Ring", "battlefield", pid="p2")
    start(s)
    mana(s, C=5)
    wait_priority(s, "p1")
    index = next(
        a.index for a in Plan(s.state, "p1", s.cards, None).ch(gauntlets).abilities if a.kind == "activated"
    )
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=gauntlets.id,
        ability=index,
        targets=[gauntlets.id, enemy.id],
        target_counts=[1, 1],
    )
    settle(s)
    assert gauntlets.zone == "p1:graveyard" and enemy.controller == "p2"


def test_gauntlets_native_land_exchange91(cards):
    s = setup91(cards)
    gauntlets = put(s, "Gauntlets of Chaos", "battlefield")
    first = put(s, "Forest", "battlefield")
    second = put(s, "Mountain", "battlefield", pid="p2")
    start(s)
    mana(s, C=5)
    wait_priority(s, "p1")
    index = next(
        a.index for a in Plan(s.state, "p1", s.cards, None).ch(gauntlets).abilities if a.kind == "activated"
    )
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=gauntlets.id,
        ability=index,
        targets=[first.id, second.id],
        target_counts=[1, 1],
    )
    settle(s)
    assert first.controller == "p2" and second.controller == "p1"


def cold91(s, tmp_path, body):
    import subprocess
    import sys

    import app

    saved = tmp_path / "exchange91.json"
    saved.write_text(s.state.model_dump_json())
    code = (
        """import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
"""
        + body
        + "\nrepo.close()\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(s.cards.db_path)],
        cwd=Path(app.__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["modify", "drake"])
def test_genuine_cold_exchange91(cards, tmp_path, mode):
    from tests.test_rules_designations import pick

    s = setup91(cards)
    first = put(s, "Grizzly Bears", "battlefield", pid="p2")
    second = put(s, "Llanowar Elves", "battlefield", pid="p3")
    spell = put(s, "Modify Memory" if mode == "modify" else "Gilded Drake", "hand")
    kill = put(s, "Murder", "hand")
    start(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    wait_priority(s, "p1")
    if mode == "modify":
        mana(s, C=4, U=1)
        before = len(s.state.zones["p1:hand"])
        act(
            s,
            "p1",
            type="cast_spell",
            card_id=spell.id,
            targets=[first.id, second.id],
            target_counts=[2],
        )
        body = f"assert s.state.cards[{first.id!r}].controller=='p3'\nassert s.state.cards[{second.id!r}].controller=='p2'\nassert len(s.state.zones['p1:hand'])=={before + 2}"
    else:
        mana(s, C=1, U=1)
        act(s, "p1", type="cast_spell", card_id=spell.id)
        settle(s)
        pick(s, [first.id])
        mana(s, C=1, B=2)
        wait_priority(s, "p1")
        act(s, "p1", type="cast_spell", card_id=kill.id, targets=[first.id])
        body = f"assert s.state.cards[{spell.id!r}].zone=='p1:graveyard'\nassert s.state.cards[{first.id!r}].zone=='p2:graveyard'"
    cold91(s, tmp_path, body)


def test_drake_no_legal_targets_still_resolves_and_sacrifices91(cards):
    s = setup91(cards)
    drake = put(s, "Gilded Drake", "hand")
    start(s)
    mana(s, C=1, U=1)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=drake.id)
    settle(s)
    if s.state.rules.decision is not None:
        from tests.test_rules_designations import pick

        assert not s.state.rules.decision.options
        pick(s, [])
        settle(s)
    assert drake.zone == "p1:graveyard"
