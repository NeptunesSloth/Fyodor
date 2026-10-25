"""Wave 110A: Bounce Chamber (Unfinity 201c, lit 4 and 6), real Oracle text. Each scenario checks replay and a save and a load.

* 702.159a, 701.52a: the visit ability triggers when a die roll lights the Attraction; the visitor (not each opponent) chooses among
  the creatures they don't control with the lowest toughness (a tie: any one of them, the card's reminder), then 400.3 returns it to its owner's hand.
"""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature
from tests.test_rules_wave12a_counters_keywords import rolls
from tests.test_rules_wave100l_attractions import game
from tests.wave9c_kit import check, put

CHAMBER = card("Bounce Chamber", set_code="unf", number="201c", mana_cost="{3}", cmc=3, type_line="Artifact — Attraction",
               oracle_text="Visit — Return a creature you don't control with the lowest toughness among creatures you don't control to "
                           "its owner's hand. (If multiple creatures are tied, choose any one of them.)", colors=[], color_identity=[], keywords=[])


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), CHAMBER], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Bounce Chamber")).level == "FULL"


def start(cards, monkeypatch, die, others):
    """Alice has the Attraction; Bob's creatures (name, pt) and hers; her turn 3 rolls to visit. Stops at the first decision or at main 1."""
    rolls(monkeypatch, die)
    s = game(cards, [], ["Bounce Chamber"])
    put(s, "Bounce Chamber")
    made = {n: creature(s, p, n, pt) for n, p, pt in others}
    for _ in range(400):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and d.player == "p1":
            return s, made, d
        if s.state.turn.number == 3 and s.state.turn.phase == "main1" and d is None and not s.state.zones.get("stack"):
            return s, made, None
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")


def alive(s, c):
    return c.id in s.state.cards and s.state.cards[c.id].zone == f"{c.owner}:battlefield"


@pytest.mark.parametrize(("die", "back"), [(6, True), (5, False)])
def test_visit_returns_the_weakest_creature_you_dont_control(cards, monkeypatch, die, back):
    s, made, d = start(cards, monkeypatch, die, [("Mine", "p1", "3/3"), ("Small", "p2", "1/1"), ("Big", "p2", "3/3")])
    assert d is None  # (one creature has the lowest toughness: nothing to choose)
    assert alive(s, made["Small"]) is not back and alive(s, made["Big"]) and alive(s, made["Mine"])  # (a token that leaves ceases to exist, 111.7)
    check(s)


def test_a_tie_lets_the_visitor_choose(cards, monkeypatch):
    s, made, d = start(cards, monkeypatch, 4, [("Tie A", "p2", "2/2"), ("Tie B", "p2", "2/2"), ("Big", "p2", "3/3")])
    assert d is not None and {o.id for o in d.options} == {made["Tie A"].id, made["Tie B"].id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[made["Tie B"].id])
    assert alive(s, made["Tie A"]) and not alive(s, made["Tie B"]) and alive(s, made["Big"])
    check(s)
