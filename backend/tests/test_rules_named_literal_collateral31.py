"""Canonical gameplay checks for collateral named-selector promotions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from app.rules.sba import power, toughness
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7r_promotions import flips
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Rohgahh of Kher Keep", "Wirefly Hive"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/named_literal_collateral31_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="nlc31", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/named_literal_collateral31_cards.json").read_text()
        )
    ]
    return table(cards, names, names, names)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_rohgahh_named_pump_uses_current_controller_and_exact_name(cards):
    s = setup(cards)
    lord = put(s, NAMES[0], "battlefield")
    own = put(s, "Kobolds of Kher Keep", "battlefield")
    other = put(s, "Kobolds of Kher Keep", "battlefield", "p2")
    crimson = put(s, "Crimson Kobolds", "battlefield")
    def pt(c):
        ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
        return power(s.state.cards[c.id], ch), toughness(s.state.cards[c.id], ch)
    assert pt(own) == (2, 3)
    assert pt(other) == (0, 1)
    assert pt(crimson) == (0, 1)
    act(s, "p1", type="set_controller", card_ids=[lord.id], player="p2")
    assert pt(own) == (0, 1)
    assert pt(other) == (2, 3)
    roundtrip(s)


@pytest.mark.parametrize("pay", [True, False])
def test_rohgahh_upkeep_pay_or_opponent_takes_all_named_creatures(cards, pay):
    s = setup(cards)
    lord = put(s, NAMES[0], "battlefield")
    own = put(s, "Kobolds of Kher Keep", "battlefield")
    theirs = put(s, "Kobolds of Kher Keep", "battlefield", "p2")
    crimson = put(s, "Crimson Kobolds", "battlefield")
    from tests.test_rules_wave30m_durations import stops
    stops(s, "upkeep", "main1")
    to_phase(s, "upkeep", turn=4)
    mana(s, R=3)
    act(s, "p1", type="tap", card_ids=[own.id], tapped=True)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    pick(s, ["pay"] if pay else ["decline"])
    settle(s)
    if not pay:
        d = s.state.rules.decision
        if d is not None:
            pick(s, ["p3"])
            settle(s)
    assert s.state.cards[lord.id].controller == ("p1" if pay else "p3")
    assert s.state.cards[own.id].controller == ("p1" if pay else "p3")
    assert s.state.cards[theirs.id].controller == ("p2" if pay else "p3")
    assert s.state.cards[crimson.id].controller == "p1"
    if not pay:
        assert all(s.state.cards[c.id].tapped for c in [lord, own, theirs])
    roundtrip(s)


@pytest.mark.parametrize("won", [True, False])
def test_wirefly_win_creates_named_artifact_and_loss_destroys_across_controllers(cards, monkeypatch, won):
    flips(monkeypatch, True)
    s = setup(cards)
    hive = put(s, NAMES[1], "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=hive.id, ability=0)
    settle(s)
    bugs = [c for c in s.state.cards.values() if c.name == "Wirefly" and c.zone.endswith(":battlefield")]
    assert len(bugs) == 1
    bug = bugs[0]
    ch = Plan(s.state, "p1", s.cards, None).ch(bug)
    assert (power(bug, ch), toughness(bug, ch)) == (2, 2)
    assert "Artifact" in ch.types and "Creature" in ch.types and "flying" in ch.keywords
    assert "Insect" in ch.subtypes and not ch.colors
    act(s, "p1", type="set_controller", card_ids=[bug.id], player="p2")
    act(s, "p1", type="tap", card_ids=[hive.id], tapped=False)
    flips(monkeypatch, won)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=hive.id, ability=0)
    roundtrip(s)
    settle(s)
    bugs = [c for c in s.state.cards.values() if c.name == "Wirefly" and c.zone.endswith(":battlefield")]
    assert len(bugs) == (2 if won else 0)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    assert s.state.cards[hive.id].zone == "p1:battlefield"
    roundtrip(s)


def test_rohgahh_opponent_choice_resumes_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    from tests.test_rules_wave30m_durations import stops

    s = setup(cards)
    lord = put(s, NAMES[0], "battlefield")
    own = put(s, "Kobolds of Kher Keep", "battlefield")
    theirs = put(s, "Kobolds of Kher Keep", "battlefield", "p2")
    stops(s, "upkeep", "main1")
    to_phase(s, "upkeep", turn=4)
    mana(s, R=3)
    settle(s)
    pick(s, ["decline"])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {"p2", "p3"}
    # Exact original objects are serialized; recipient choice does not re-query the name.
    assert d.resume["e"]["who"] == "ref:tapped_named_group"
    saved = tmp_path / "rohgahh-choice.json"
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import pick, settle, roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
pick(s,['p3'])
settle(s)
for cid in sys.argv[3:]:
 assert s.state.cards[cid].controller=='p3'
 assert s.state.cards[cid].tapped
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, "-c", code, str(saved), str(cards.db_path), lord.id, own.id, theirs.id], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
