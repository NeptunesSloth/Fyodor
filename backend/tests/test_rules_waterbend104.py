"""Crashing Wave combines X tapping with an untargeted resolving stun distribution."""

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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_waterbend102 import helpers, pick, take
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/waterbend104_cards.json").read_text())
NAME = "Crashing Wave"


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="w03", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    ns = [c["name"] for c in DATA] * 7
    s = table(cards, ns, ns, ns)
    to_phase(s, "main1", 4)
    return s


def test_crashing_wave_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def prepare(cards, x=2):
    s = setup(cards)
    ids = helpers(s, x)
    bear = take(s, "Grizzly Bears", "battlefield", pid="p2")
    scout = take(s, "Gladecover Scout", "battlefield", pid="p2")
    act(s, "p2", type="tap", card_ids=[scout.id], tapped=True)
    own = take(s, "Ornithopter", "battlefield")
    act(s, "p1", type="tap", card_ids=[own.id], tapped=True)
    source = take(s, NAME)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2})
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=source.id,
        sources=[],
        x_value=x,
        targets=[bear.id] if x else [],
        target_counts=[1 if x else 0],
    )
    if x:
        pick(s, ids)
    settle(s)
    return s, bear, scout, own, source


def test_crashing_wave_targets_then_distributes_untargeted_stun_including_hexproof(cards):
    s, bear, scout, own, source = prepare(cards)
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {"done", bear.id, scout.id}
    pick(s, [bear.id])
    pick(s, [scout.id])
    if s.state.rules.decision and s.state.rules.decision.resume.get("stage") == "recipients":
        pick(s, ["done"])
    d = s.state.rules.decision
    assert d and d.resume["stage"] == "amount"
    act(s, d.player, type="choose", decision_id=d.id, name="2")
    settle(s)
    assert s.state.cards[bear.id].counters.get("stun") == 2
    assert s.state.cards[scout.id].counters.get("stun") == 1
    assert not s.state.cards[own.id].counters and source.zone == "p1:graveyard"
    roundtrip(s)


def test_zero_x_still_distributes_three_to_existing_tapped_opponent_creature(cards):
    s, bear, scout, own, source = prepare(cards, 0)
    pick(s, [scout.id])
    if s.state.rules.decision and s.state.rules.decision.resume.get("stage") == "recipients":
        pick(s, ["done"])
    settle(s)
    assert s.state.cards[scout.id].counters.get("stun") == 3
    assert not s.state.cards[bear.id].tapped and not s.state.cards[bear.id].counters
    roundtrip(s)


def test_true_cold_crashing_wave_distribution_keeps_unallocated_stun_choice(cards, tmp_path):
    from tests.test_rules_cost_statics101_extra import cold

    s, bear, scout, own, source = prepare(cards)
    cold(
        s,
        tmp_path,
        f"d=s.state.rules.decision\nact(s,d.player,type='choose',decision_id=d.id,option_ids=[{scout.id!r}])\n"
        "d=s.state.rules.decision\nact(s,d.player,type='choose',decision_id=d.id,option_ids=['done'])\nsettle(s)\n"
        f"assert s.state.cards[{scout.id!r}].counters.get('stun')==3\nroundtrip(s)",
    )
