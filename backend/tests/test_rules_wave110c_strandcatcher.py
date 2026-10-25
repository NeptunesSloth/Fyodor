"""Wave 110C: Dimir Strandcatcher (506.2: X is the number of opponents some creature of yours is attacking; 400.7 + 608.2i: three or more cards put
into your graveyard this turn from anywhere but the battlefield, tokens are no cards)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import answer, build, check, make_db, put, real

EXTRA = [real("Dimir Strandcatcher", "{1}{U}{B}", 3, "Creature — Merfolk Rogue",
              "Flying\nWhenever you attack, surveil X, where X is the number of opponents being attacked.\n"
              "At the beginning of each end step, if three or more cards were put into your graveyard from anywhere other than the battlefield this turn, "
              "draw a card.", ("2", "2"), "UB")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Dimir Strandcatcher")).level == "FULL"


@pytest.mark.parametrize("extra,draws", [(1, 0), (2, 1)])
def test_attack_surveils_one_and_end_step_draws_at_three_arrivals(cards, extra, draws):
    s = build(cards, ["Dimir Strandcatcher"], forests=40, islands=40)
    bird = put(s, "Dimir Strandcatcher")
    to_phase(s, "declare_attackers", 3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bird.id, "target": "p2"}])
    d = s.state.rules.decision
    assert d is not None and "surveil" in d.prompt.lower(), d
    answer(s, [d.options[-1].id])  # surveil 1 (one opponent attacked): the card goes to the graveyard, the first arrival
    act(s, "p1", type="move", card_ids=list(s.state.zones["p1:library"])[:extra], to={"player": "p1", "zone": "graveyard"})
    before = len(s.state.zones["p1:hand"])
    to_phase(s, "main1", 4)  # (the end step passes by itself; its trigger resolves on the way)
    assert len(s.state.zones["p1:hand"]) == before + draws
    check(s)
