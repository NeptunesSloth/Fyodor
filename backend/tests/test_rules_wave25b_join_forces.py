"""Wave 25B: join forces (CR 2026-09-25: 207.2c, 101.4, 118.12, 608.2c). Real Oracle text; every scenario checks the replay and a save and a load.

"Starting with you, each player may pay any amount of mana. Each player draws X cards, where X is the total amount of mana paid this way."
Each player in turn (the controller first) chooses how much to pay, privately but one after another; X is the total of what everyone paid.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, mana, to_hand

CARDS = [
    ("Minds Aglow", "{U}", "Sorcery", None, None,
     "Join forces — Starting with you, each player may pay any amount of mana. Each player draws X cards, where X is the total amount of mana paid this way."),
    ("Alliance of Arms", "{W}", "Sorcery", None, None,
     "Join forces — Starting with you, each player may pay any amount of mana. Each player creates X 1/1 white Soldier creature tokens, where X is "
     "the total amount of mana paid this way."),
    ("Shared Trauma", "{B}", "Sorcery", None, None,
     "Join forces — Starting with you, each player may pay any amount of mana. Each player mills X cards, where X is the total amount of mana paid this way."),
    ("Collective Voyage", "{G}", "Sorcery", None, None,
     "Join forces — Starting with you, each player may pay any amount of mana. Each player searches their library for up to X basic land cards, "
     "where X is the total amount of mana paid this way, puts them onto the battlefield tapped, then shuffles."),
    ("Mana-Charged Dragon", "{4}{R}{R}", "Creature — Dragon", "5", "5",
     "Flying, trample\nJoin forces — Whenever this creature attacks or blocks, each player starting with you may pay any amount of mana. "
     "This creature gets +X/+0 until end of turn, where X is the total amount of mana paid this way."),
]
EXTRA = [card(n, set_code="t25b", number=f"J{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
              colors=[], color_identity=[], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(CARDS)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def level(name):
    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", [c[0] for c in CARDS])
def test_join_forces_cards_are_full(name):
    assert level(name) == "FULL", name


def hand_size(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def pay(s, pid, n):
    """Answer the pending "pay {X}?" choice of ``pid`` with X = n (n 0 declines, as a player who pays nothing)."""
    d = s.state.rules.decision
    assert d is not None and d.player == pid, (d and d.player, pid)
    ids = [o.id for o in d.options]
    pick = f"x:{n}" if n else "decline"
    assert pick in ids, ids
    act(s, pid, type="choose", decision_id=d.id, option_ids=[pick])


def test_each_player_pays_in_turn_and_every_player_draws_the_total(cards):
    s = build(cards, ["Minds Aglow"])
    to_hand(s, "Minds Aglow")
    mana(s, U=3)  # {U} for the spell and two to pay as Alice
    mana(s, "p2", C=1)
    mine, theirs = hand_size(s) - 1, hand_size(s, "p2")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Minds Aglow").id)
    answer_first = s.state.rules.decision
    assert answer_first is not None and answer_first.player == "p1"  # (starting with you)
    pay(s, "p1", 2)
    assert s.state.rules.decision is not None and s.state.rules.decision.player == "p2"  # (then the other player)
    pay(s, "p2", 1)
    answer(s)
    assert hand_size(s) == mine + 3 and hand_size(s, "p2") == theirs + 3  # (2 + 1 = 3 each)
    assert sum(s.state.players["p1"].mana.values()) == 0 and sum(s.state.players["p2"].mana.values()) == 0
    check(s)


def test_a_player_may_pay_nothing_and_the_others_total_still_counts(cards):
    s = build(cards, ["Minds Aglow"])
    to_hand(s, "Minds Aglow")
    mana(s, U=1)
    mana(s, "p2", C=2)
    mine, theirs = hand_size(s) - 1, hand_size(s, "p2")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Minds Aglow").id)
    pay(s, "p1", 0)  # (Alice has no mana left to pay: only "don't pay" can be chosen)
    pay(s, "p2", 2)
    answer(s)
    assert hand_size(s) == mine + 2 and hand_size(s, "p2") == theirs + 2
    check(s)


def test_alliance_of_arms_creates_the_total_for_each_player(cards):
    s = build(cards, ["Alliance of Arms"])
    to_hand(s, "Alliance of Arms")
    mana(s, W=2)
    mana(s, "p2", C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Alliance of Arms").id)
    pay(s, "p1", 1)
    pay(s, "p2", 1)
    answer(s)
    soldiers = [c for c in s.state.cards.values() if c.is_token and c.name == "Soldier" and c.zone.endswith(":battlefield")]
    assert sorted(c.controller for c in soldiers) == ["p1", "p1", "p2", "p2"]  # (X = 2 each)
    check(s)


def test_shared_trauma_mills_the_total_from_each_library(cards):
    s = build(cards, ["Shared Trauma"])
    to_hand(s, "Shared Trauma")
    mana(s, B=3)
    mana(s, "p2", C=1)
    mine, theirs = len(s.state.zones["p1:library"]), len(s.state.zones["p2:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Shared Trauma").id)
    pay(s, "p1", 2)
    pay(s, "p2", 1)
    answer(s)
    assert len(s.state.zones["p1:library"]) == mine - 3 and len(s.state.zones["p2:library"]) == theirs - 3
    check(s)
