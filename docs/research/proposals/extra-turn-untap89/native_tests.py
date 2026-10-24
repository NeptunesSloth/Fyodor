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
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads(
    (Path(__file__).parent / "fixtures/extra_turn_untap89_cards.json").read_text()
)


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"],
            set_code="e89",
            number=str(i),
            **{k: v for k, v in c.items() if k != "name"},
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup89(cards):
    names = [c["name"] for c in DATA] + ["Forest", "Swords to Plowshares"]
    s = table(cards, names, names, names)
    forest = put(s, "Forest", "battlefield")
    start(s)
    act(s, "p1", type="tap", card_ids=[forest.id])
    return s, forest


def cast89(s, name):
    c = put(s, name, "hand")
    mana(s, C=1 if name == "Savor the Moment" else 3, U=2)
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=c.id,
        **({"targets": ["p1"]} if name == "Time Warp" else {}),
    )
    settle(s)
    assert s.state.cards[c.id].zone == "p1:graveyard"


def test_whole_savor89(cards):
    assert coverage.of_card_data(cards.resolve("Savor the Moment")).level == "FULL"


def test_actual_savor_extra_turn_skips_untap_only_that_turn89(cards):
    s, forest = setup89(cards)
    cast89(s, "Savor the Moment")
    assert (
        len(s.state.rules.extra_turns) == 1
        and s.state.rules.extra_turns[0]["skip_untap89"]
    )
    to_phase(s, "main1", turn=5)
    assert s.state.turn.active_player == "p1" and forest.tapped
    to_phase(s, "main1", turn=8)
    assert s.state.turn.active_player == "p1" and not forest.tapped


@pytest.mark.parametrize("savor_last", [False, True])
def test_extra_turn_skip_belongs_to_exact_queue_record89(cards, savor_last):
    s, forest = setup89(cards)
    for name in (
        ["Time Warp", "Savor the Moment"]
        if savor_last
        else ["Savor the Moment", "Time Warp"]
    ):
        cast89(s, name)
    to_phase(s, "main1", turn=5)
    assert s.state.turn.active_player == "p1" and forest.tapped == savor_last
    if not forest.tapped:
        act(s, "p1", type="tap", card_ids=[forest.id])
    to_phase(s, "main1", turn=6)
    assert s.state.turn.active_player == "p1" and forest.tapped != savor_last


def test_static_skipped_extra_turn_discards_untap_metadata89(cards):
    s, forest = setup89(cards)
    source = put(s, "Stranglehold", "battlefield", pid="p2")
    cast89(s, "Savor the Moment")
    to_phase(s, "main1", turn=5)
    assert s.state.turn.active_player == "p2" and not s.state.rules.extra_turns
    assert not any(rec["what"] == "untap" for rec in s.state.rules.skips)
    act(
        s,
        "p2",
        type="move",
        card_ids=[source.id],
        to={"player": "p2", "zone": "graveyard"},
    )
    to_phase(s, "main1", turn=7)
    assert s.state.turn.active_player == "p1" and not forest.tapped


def test_static_untap_skip_does_not_leave_savor_skip_for_later89(cards):
    s, forest = setup89(cards)
    stasis = put(s, "Stasis", "battlefield")
    cast89(s, "Savor the Moment")
    to_phase(s, "upkeep", turn=5)
    assert forest.tapped
    mana(s, U=1)
    to_phase(s, "main1", turn=5)
    assert forest.tapped
    assert not any(rec["what"] == "untap" for rec in s.state.rules.skips)
    act(
        s,
        "p1",
        type="move",
        card_ids=[stasis.id],
        to={"player": "p1", "zone": "graveyard"},
    )
    to_phase(s, "main1", turn=8)
    assert s.state.turn.active_player == "p1" and not forest.tapped


@pytest.mark.parametrize("savor_last", [False, True])
def test_genuine_cold_per_extra_turn_untap_flag89(cards, tmp_path, savor_last):
    import subprocess
    import sys

    import app

    s, forest = setup89(cards)
    for name in (
        ["Time Warp", "Savor the Moment"]
        if savor_last
        else ["Savor the Moment", "Time Warp"]
    ):
        cast89(s, name)
    saved = tmp_path / "extra89.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
forest=s.state.cards[sys.argv[3]];last=sys.argv[4]=='True'
to_phase(s,'main1',turn=5)
assert s.state.turn.active_player=='p1' and forest.tapped==last
if not forest.tapped:act(s,'p1',type='tap',card_ids=[forest.id])
to_phase(s,'main1',turn=6)
assert s.state.turn.active_player=='p1' and forest.tapped!=last
assert not s.state.rules.extra_turns
assert not any(rec['what']=='untap' for rec in s.state.rules.skips)
repo.close()
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(saved),
            str(cards.db_path),
            forest.id,
            str(savor_last),
        ],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
