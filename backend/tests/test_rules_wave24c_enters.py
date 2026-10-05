"""Wave 24C: "enters with" counters under a negated cast condition (CR 614.1c, 614.12, 601.2h) — "This creature enters with three +1/+1 counters on
it if you didn't cast it from your hand." (Epochrasite), "This creature enters with two -1/-1 counters on it unless you've cast another red
spell this turn." (Hotheaded Giant).

Every scenario uses real Oracle text (tests/fixtures/wave24c_enters_cards.json, from data/cards.sqlite) and checks that replaying the recorded
history reproduces the table and that a save/load round trip keeps it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, settle, to_hand
from tests.test_rules_effects import mana, replay_matches

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24c_enters_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t24e", number=f"E{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def counters(s, c):
    return {k: v for k, v in s.state.cards[c.id].counters.items() if v}


def check(s):
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", name


def test_epochrasite_enters_with_counters_only_when_not_cast_from_the_hand(cards):
    s = build(cards, "Epochrasite", "Reanimate")
    rasite = next(c for c in s.state.cards.values() if c.name == "Epochrasite")
    act(s, "p1", type="move", card_ids=[rasite.id], to={"player": "p1", "zone": "graveyard"})
    spell = to_hand(s, "Reanimate")
    mana(s, "p1", B=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[rasite.id])  # put onto the battlefield: not cast
    settle(s)
    assert s.state.cards[rasite.id].zone == "p1:battlefield" and counters(s, rasite) == {"+1/+1": 3}
    check(s)
    s = build(cards, "Epochrasite")
    rasite = to_hand(s, "Epochrasite")
    mana(s, "p1", C=2)
    act(s, "p1", type="cast_spell", card_id=rasite.id)
    settle(s)
    assert s.state.cards[rasite.id].zone == "p1:battlefield" and counters(s, rasite) == {}  # cast from its owner's hand
    check(s)


def test_hotheaded_giant_enters_with_counters_unless_another_red_spell_was_cast(cards):
    s = build(cards, "Hotheaded Giant")
    giant = to_hand(s, "Hotheaded Giant")
    mana(s, "p1", R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=giant.id)
    settle(s)
    assert counters(s, giant) == {"-1/-1": 2}  # (it is the only spell cast: "another" excludes itself)
    check(s)
    s = build(cards, "Hotheaded Giant", "Lightning Bolt")
    bolt, giant = to_hand(s, "Lightning Bolt"), to_hand(s, "Hotheaded Giant")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    mana(s, "p1", R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=giant.id)
    settle(s)
    assert counters(s, giant) == {}
    check(s)
