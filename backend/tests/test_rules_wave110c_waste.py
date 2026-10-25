"""Wave 110C: Eumidian Wastewaker (101.4 APNAP choices, 701.9a discard, 701.21a sacrifice, draw per land card put into a graveyard this way)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import attack, to_phase
from tests.wave110c_kit import build, check, make_db, put, real, to_hand

TEXT = ("Whenever this creature attacks, you and defending player each discard a card or sacrifice a permanent. You draw a card for each land card put into a graveyard this way.\n"
        "Encore {6}{B}{B} ({6}{B}{B}, Exile this card from your graveyard: For each opponent, create a token copy that attacks that opponent this turn if able. They gain haste. "
        "Sacrifice them at the beginning of the next end step. Activate only as a sorcery.)")
EXTRA = [real("Eumidian Wastewaker", "{2}{B}", 3, "Creature — Phyrexian Rogue", TEXT, ("3", "3"), "B")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Eumidian Wastewaker")).level == "FULL"


def _go(cards, mine, theirs):
    """Attack with the Wastewaker; ``mine`` / ``theirs``: the card each player picks (by name, discard from hand else sacrifice)."""
    s = build(cards, ["Eumidian Wastewaker", "Forest", "Grizzly Bears"], ["Mountain", "Lightning Bolt", "Grizzly Bears"])
    w = put(s, "Eumidian Wastewaker")
    to_hand(s, "Grizzly Bears")
    forest = put(s, "Forest")
    to_hand(s, "Mountain", "p2")
    to_hand(s, "Lightning Bolt", "p2")
    to_phase(s, "declare_attackers", 3)
    attack(s, (w, "p2"))
    picks = {"p1": {"forest": forest.id, "bears": next(c for c in s.state.zones["p1:hand"] if s.state.cards[c].name == "Grizzly Bears")},
             "p2": {"mountain": next(c for c in s.state.zones["p2:hand"] if s.state.cards[c].name == "Mountain"),
                    "bolt": next(c for c in s.state.zones["p2:hand"] if s.state.cards[c].name == "Lightning Bolt")}}
    hand, hand2 = len(s.state.zones["p1:hand"]), len(s.state.zones["p2:hand"])
    for pid, name in (("p1", mine), ("p2", theirs)):
        d = s.state.rules.decision
        assert d is not None and d.player == pid
        act(s, pid, type="choose", decision_id=d.id, option_ids=[picks[pid][name]])
    return s, hand, hand2


@pytest.mark.parametrize(("mine", "theirs", "draws"), [("forest", "mountain", 2), ("bears", "mountain", 1), ("forest", "bolt", 1), ("bears", "bolt", 0)])
def test_draw_for_each_land_card(cards, mine, theirs, draws):
    s, hand, hand2 = _go(cards, mine, theirs)
    assert len(s.state.zones["p1:hand"]) == hand - (mine == "bears") + draws
    assert len(s.state.zones["p2:hand"]) == hand2 - 1
    check(s)
