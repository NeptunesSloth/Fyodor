"""Wave 24C: hone counters (CR 122.1j, 613.4c) and a value naming its own target beside another one — "When Sting enters, put a hone counter on Sting
for each creature target opponent controls. Attach Sting to up to one target creature you control." (Sting, Bilbo's Sword), "Whenever Dwalin enters or
attacks, put a hone counter on each Equipment you control." (Dwalin, Weaponmaster).

* 122.1j: a hone counter on an Equipment gives +1/+0 to any creature that Equipment is attached to (power, layer 7c: counters).
* 601.2c / 115.1: the "target opponent" a value names is a target of the ability, chosen with the other one, in text order.

Every scenario uses real Oracle text (tests/fixtures/wave24c_hone_cards.json, from data/cards.sqlite) and checks that replaying the recorded history reproduces
the table and that a save/load round trip keeps it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, to_hand, token_of
from tests.test_rules_effects import mana, replay_matches

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24c_hone_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t24h", number=f"H{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def check(s):
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def answer(s, *picks, limit=40):
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = [pick] if isinstance(pick, str) else pick or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", name


def test_sting_gets_a_hone_counter_per_creature_the_chosen_opponent_controls(cards):
    s = build(cards, "Sting, Bilbo's Sword")
    mine = token_of(s, "p1", "Mine", "Creature — Bear", "2/2")
    token_of(s, "p2", "Theirs A", "Creature — Bear", "2/2")
    token_of(s, "p2", "Theirs B", "Creature — Bear", "2/2")
    token_of(s, "p2", "Theirs C", "Creature — Bear", "2/2")
    sting = to_hand(s, "Sting, Bilbo's Sword")
    mana(s, "p1", C=2)
    act(s, "p1", type="cast_spell", card_id=sting.id)
    answer(s, "p2", mine.id)  # the target opponent first, then the creature it's attached to (text order)
    assert s.state.cards[sting.id].counters.get("hone") == 3 and s.state.cards[sting.id].attached_to == mine.id
    assert ch(s, mine).pt == (5, 2)  # 122.1j: +1/+0 for each hone counter
    check(s)
    act(s, "p1", type="move", card_ids=[sting.id], to={"player": "p1", "zone": "graveyard"})  # it leaves: no memory of counters, no bonus
    assert ch(s, mine).pt == (2, 2)


def test_dwalin_puts_a_hone_counter_on_each_equipment_you_control(cards):
    s = build(cards, "Sting, Bilbo's Sword", "Dwalin, Weaponmaster")
    mine = token_of(s, "p1", "Mine", "Creature — Bear", "2/2")
    sting = to_hand(s, "Sting, Bilbo's Sword")
    mana(s, "p1", C=2)
    act(s, "p1", type="cast_spell", card_id=sting.id)
    answer(s, "p2", mine.id)  # (no creature on the other side: no counters yet)
    assert not s.state.cards[sting.id].counters.get("hone") and ch(s, mine).pt == (2, 2)
    dwalin = to_hand(s, "Dwalin, Weaponmaster")
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=dwalin.id)
    answer(s)
    assert s.state.cards[sting.id].counters.get("hone") == 1 and ch(s, mine).pt == (3, 2)
    check(s)
