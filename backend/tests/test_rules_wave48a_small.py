"""Wave 48A: single-wording gaps of cards ranked 13,000 and up (CR 2026-09-25), real Oracle text (tests/fixtures/wave48a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 608.2c, 608.2h: "Destroy target artifact. ~ deals damage to that artifact's controller equal to the artifact's mana value." (Viashino Heretic) - the artifact as it
  last existed; the damage goes to whoever controlled it, Alice for her own artifact.
* 115.3, 611.2c: "Until end of turn, target creature gets +0/+2 and another target creature gets -2/-0." (Rookie Mistake, Skulduggery) - two different targets, each its own pump;
  "+X/+0 and -0/-X, where X is the number of artifacts you control" (Monoist Circuit-Feeder) - one X for both halves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, ask, next_turn, settle
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand
from tests.wave43b_kit import cast

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave48a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w48a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_viashino_heretic_damages_the_controller_of_the_artifact_by_its_mana_value(cards):
    s = build(cards, ["Viashino Heretic"], ["Arcane Signet"])
    heretic = put(s, "Viashino Heretic")
    signet = put(s, "Arcane Signet", "p2")
    next_turn(s)  # (summoning sickness: it has to be there since the turn began)
    mana(s, R=1, C=1)
    activate(s, "p1", heretic, targets=[signet.id])
    settle(s)
    assert s.state.cards[signet.id].zone == "p2:graveyard"
    assert life(s, "p2") == 38 and life(s, "p1") == 40  # Arcane Signet is mana value 2
    check(s)


def test_viashino_heretic_hurts_its_own_controller_for_an_artifact_of_theirs(cards):
    s = build(cards, ["Viashino Heretic", "Sol Ring"], [])
    heretic = put(s, "Viashino Heretic")
    ring = put(s, "Sol Ring")
    next_turn(s)  # (summoning sickness: it has to be there since the turn began)
    mana(s, R=1, C=1)
    activate(s, "p1", heretic, targets=[ring.id])
    settle(s)
    assert life(s, "p1") == 39 and life(s, "p2") == 40
    check(s)


def test_rookie_mistake_pumps_one_creature_and_shrinks_another(cards):
    s = build(cards, ["Rookie Mistake", "Grizzly Bears"], ["Grizzly Bears"])
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    to_hand(s, "Rookie Mistake")
    mana(s, U=1)
    cast(s, "Rookie Mistake", targets=[mine.id, theirs.id], target_counts=[1, 1])
    assert pt(s, "Grizzly Bears") == (2, 4) and pt(s, "Grizzly Bears", "p2") == (0, 2)
    check(s)


def test_rookie_mistake_needs_two_different_creatures(cards):
    s = build(cards, ["Rookie Mistake", "Grizzly Bears"], [])
    only = put(s, "Grizzly Bears")
    to_hand(s, "Rookie Mistake")
    mana(s, U=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Rookie Mistake").id, targets=[only.id, only.id], target_counts=[1, 1])


def test_skulduggery_pumps_a_creature_you_control_and_shrinks_an_opponents(cards):
    s = build(cards, ["Skulduggery", "Grizzly Bears"], ["Grizzly Bears"])
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    to_hand(s, "Skulduggery")
    mana(s, B=1)
    cast(s, "Skulduggery", targets=[mine.id, theirs.id], target_counts=[1, 1])
    assert pt(s, "Grizzly Bears") == (3, 3) and pt(s, "Grizzly Bears", "p2") == (1, 1)
    check(s)


def test_monoist_circuit_feeder_counts_artifacts_once_for_both_halves(cards):
    s = build(cards, ["Monoist Circuit-Feeder", "Sol Ring", "Grizzly Bears"], ["Albino Troll"])
    put(s, "Sol Ring")
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Albino Troll", "p2")
    to_hand(s, "Monoist Circuit-Feeder")
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Monoist Circuit-Feeder").id)
    for pick in (mine, theirs):  # the enters ability's two targets, one after the other
        d = ask(s)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick.id])
    settle(s)
    # two artifacts (Sol Ring and the Feeder): +2/+0 on Alice's Bears, -0/-2 on Bob's Troll
    assert pt(s, "Grizzly Bears") == (4, 2) and pt(s, "Albino Troll", "p2") == (3, 1)
    check(s)
