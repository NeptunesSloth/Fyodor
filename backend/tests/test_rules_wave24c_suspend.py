"""Wave 24C: suspend granted (CR 702.62b-e) — "Exile target creature and put two time counters on it. If it doesn't have suspend, it gains
suspend." (Suspend), "… exile target nonland card from your graveyard with two time counters on it. …" (Doom's Time Platform), "When this
creature dies, exile it with three time counters on it and it gains suspend." (Epochrasite), "Whenever this creature enters or attacks, exile
cards from the top of your library until you exile a nonland card. Put two time counters on that card. …" (Kang Prime).

Every scenario uses real Oracle text (tests/fixtures/wave24c_suspend_cards.json, from data/cards.sqlite) and checks that replaying the recorded
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
from tests.test_rules_suspend import until

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24c_suspend_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t24s", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def saved(s):
    return GameSession(s.history.rebuild(), cards=s.cards)


def counters(s, c):
    return {k: v for k, v in s.state.cards[c.id].counters.items() if v}


def zone(s, c):
    return s.state.cards[c.id].zone


def on_field(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", name


def test_suspend_exiles_a_creature_and_it_comes_back_with_haste(cards):
    s = build(cards, "Suspend", p2=("Grizzly Bears",))
    bears = on_field(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Suspend")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id])
    settle(s)
    assert zone(s, bears) == "p2:exile" and counters(s, bears) == {"time": 2}
    assert bears.id in s.state.rules.suspended  # 702.62b: it has suspend now, whether or not it printed it
    s = saved(s)
    replay_matches(s)
    until(s, lambda s: s.state.rules.decision is not None and (s.state.rules.decision.resume or {}).get("step") == "suspend_cast", limit=3000)
    assert counters(s, bears) == {}  # its owner's second upkeep took the last counter (702.62b)
    d = s.state.rules.decision
    assert d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes"])
    settle(s)
    assert zone(s, bears) == "p2:battlefield"
    assert bears.id not in s.state.rules.suspended
    replay_matches(saved(s))


def test_a_card_that_left_exile_is_no_longer_suspended(cards):
    s = build(cards, "Suspend", p2=("Grizzly Bears",))
    bears = on_field(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Suspend")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id])
    settle(s)
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "hand"})  # (some other effect took it out)
    until(s, lambda s: s.state.turn.number >= 4, limit=3000)
    assert zone(s, bears) == "p2:hand" and s.state.rules.decision is None
    assert bears.id not in s.state.rules.suspended  # (dropped at the next upkeep: no time counter, not in exile)
    replay_matches(s)


def test_epochrasite_exiles_itself_with_suspend_when_it_dies(cards):
    s = build(cards, "Epochrasite", "Lightning Bolt")
    rasite = to_hand(s, "Epochrasite")
    mana(s, "p1", C=2)
    act(s, "p1", type="cast_spell", card_id=rasite.id)
    settle(s)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[rasite.id])  # it dies (700.4)
    settle(s)
    assert zone(s, rasite) == "p1:exile" and counters(s, rasite) == {"time": 3}
    assert rasite.id in s.state.rules.suspended
    replay_matches(saved(s))


def test_kang_prime_suspends_the_first_nonland_card(cards):
    s = build(cards, "Kang Prime", "Epochrasite")
    prime = to_hand(s, "Kang Prime")
    rasite = to_hand(s, "Epochrasite")
    act(s, "p1", type="move", card_ids=[rasite.id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, "p1", U=1, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=prime.id)
    settle(s)
    assert zone(s, rasite) == "p1:exile" and counters(s, rasite) == {"time": 2}
    assert rasite.id in s.state.rules.suspended
    replay_matches(saved(s))
