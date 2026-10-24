from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.mana_units import visible_pool
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

DATA = json.loads(
    (Path(__file__).parent / "fixtures/source_cohort87_cards.json").read_text()
)
NAMES = [c["name"] for c in DATA]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"],
            set_code="c87",
            number=str(i),
            **{k: v for k, v in c.items() if k != "name"},
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup87(cards, name):
    names = [
        *NAMES,
        "Grizzly Bears",
        "Llanowar Elves",
        "Forest",
        "Swords to Plowshares",
    ]
    s = table(cards, names, names, names)
    source = put(s, name, "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    other = put(s, "Llanowar Elves", "battlefield")
    start(s)
    return s, source, bear, other


@pytest.mark.parametrize("name", NAMES)
def test_whole87(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("target", [True, False])
def test_razorgrass_actual_eight_cost_optional_target_and_source(cards, target):
    s, source, bear, _ = setup87(cards, "Razorgrass Invoker")
    before = Plan(s.state, "p1", s.cards, None).ch(source).pt
    mana(s, C=8)
    wait_priority(s, "p1")
    index = next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(source).abilities
        if a.kind == "activated"
    )
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=index,
        targets=[bear.id] if target else [],
        target_counts=[1 if target else 0],
    )
    settle(s)
    assert Plan(s.state, "p1", s.cards, None).ch(source).pt == (
        before[0] + 3,
        before[1] + 3,
    )
    assert Plan(s.state, "p1", s.cards, None).ch(bear).pt == (
        (5, 5) if target else (2, 2)
    )
    assert not visible_pool(s.state, "p1")


@pytest.mark.parametrize("count", [1, 2, 3])
def test_suitor_only_actual_exactly_two_declared_attackers_transform(cards, count):
    s, source, bear, other = setup87(cards, NAMES[1])
    to_phase(s, "declare_attackers", turn=4)
    pairs = [
        (bear, "p2"),
        *([(other, "p2")] if count >= 2 else []),
        *([(source, "p2")] if count == 3 else []),
    ]
    act(s, "p1", type="clear_mana")
    attack(s, *pairs)
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(source)
    assert ch.name == ("Deadly Dancer" if count == 2 else "Alluring Suitor")
    if count == 2:
        assert visible_pool(s.state, "p1") == {"R": 2}
        to_phase(s, "main2", turn=4)
        assert visible_pool(s.state, "p1") == {"R": 2}
        index = next(
            a.index
            for a in Plan(s.state, "p1", s.cards, None).ch(source).abilities
            if a.kind == "activated"
        )
        wait_priority(s, "p1")
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=source.id,
            ability=index,
            targets=[bear.id],
        )
        settle(s)
        assert Plan(s.state, "p1", s.cards, None).ch(source).pt == (4, 3)
        assert Plan(s.state, "p1", s.cards, None).ch(bear).pt == (3, 2)
        assert not visible_pool(s.state, "p1")


@pytest.mark.parametrize("removed", ["source", "target"])
def test_razorgrass_resolution_original_source_and_target_legality(cards, removed):
    s, source, bear, _ = setup87(cards, NAMES[0])
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, C=8)
    wait_priority(s, "p1")
    index = next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(source).abilities
        if a.kind == "activated"
    )
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=index,
        targets=[bear.id],
        target_counts=[1],
    )
    spell = put(s, "Swords to Plowshares", "hand")
    mana(s, W=1)
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=spell.id,
        targets=[source.id if removed == "source" else bear.id],
    )
    settle(s)
    if removed == "source":
        assert Plan(s.state, "p1", s.cards, None).ch(bear).pt == (5, 5)
    else:
        assert Plan(s.state, "p1", s.cards, None).ch(source).pt == (4, 3)


@pytest.mark.parametrize(
    "name,cost", [(NAMES[0], {"C": 3, "G": 1}), (NAMES[1], {"C": 2, "R": 1})]
)
def test_actual_printed_cast87(cards, name, cost):
    s, source, _, _ = setup87(cards, name)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
    mana(s, **cost)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    assert source.zone == "p1:battlefield"
    assert Plan(s.state, "p1", s.cards, None).ch(source).pt == (
        (4, 3) if name == NAMES[0] else (2, 3)
    )


@pytest.mark.parametrize("mode", ["razor", "suitor"])
def test_genuine_cold_native_packet87(cards, tmp_path, mode):
    import subprocess
    import sys

    import app

    s, source, bear, other = setup87(cards, NAMES[0] if mode == "razor" else NAMES[1])
    act(s, "p1", type="set_prefs", hold_priority=True)
    if mode == "razor":
        mana(s, C=8)
        wait_priority(s, "p1")
        index = next(
            a.index
            for a in Plan(s.state, "p1", s.cards, None).ch(source).abilities
            if a.kind == "activated"
        )
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=source.id,
            ability=index,
            targets=[bear.id],
            target_counts=[1],
        )
    else:
        to_phase(s, "declare_attackers", turn=4)
        attack(s, (bear, "p2"), (other, "p2"))
    saved = tmp_path / "cold87.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[sys.argv[4]])
if sys.argv[3]=='razor':
 assert ch.pt==(7,6)
 assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[sys.argv[5]]).pt==(5,5)
else:assert ch.name=='Deadly Dancer'
repo.close()
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(saved),
            str(cards.db_path),
            mode,
            source.id,
            bear.id,
        ],
        cwd=Path(app.__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
