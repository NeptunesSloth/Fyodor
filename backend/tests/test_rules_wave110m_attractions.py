"""Wave 110M: Myra the Magnificent. The exiled instant or sorcery card is copied (707.12) every time its controller visits the marked Attraction (701.52a, 702.159a), for as long as that
Attraction is on the battlefield, and the copy may be cast free (118.9). Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.cards.importer import build_database
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.test_rules_wave12a_counters_keywords import rolls
from tests.test_rules_wave100l_attractions import EXTRA as EXTRA100L
from tests.test_rules_wave100l_attractions import game, play, to_main
from tests.wave36a_kit import ready
from tests.wave110m_kit import *
from tests.wave110m_kit import EXTRA as EXTRA110M

MYRA = "Myra the Magnificent"


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA100L, *EXTRA110M], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_myra_is_full(cards):
    assert coverage.of_card_data(cards.resolve(MYRA)).level == "FULL"


def to_main_aiming(s, turn, limit=400):
    """``to_main``, but every target choice is Bob."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.number == turn and s.state.turn.phase == "main1" and d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if "p2" in ids else ids[: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached that main phase")


def myra_table(cards, monkeypatch, die):
    rolls(monkeypatch, die)
    s = game(cards, [MYRA, "Lightning Bolt", "Disenchant"], ["Clown Extruder"])  # 204d: 5 and 6 lit
    myra = put(s, MYRA)
    put(s, "Clown Extruder")
    ready(s, MYRA)
    act(s, "p1", type="move", card_ids=[card_named(s, "Lightning Bolt").id], to={"player": "p1", "zone": "graveyard"})
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=myra.id, ability=1, x_value=1, targets=[card_named(s, "Lightning Bolt").id])
    play(s)
    return s, myra


def test_the_exile_marks_the_attraction_and_each_visit_copies_the_card(cards, monkeypatch):
    s, myra = myra_table(cards, monkeypatch, 5)
    extruder = card_named(s, "Clown Extruder")
    assert s.state.cards[extruder.id].counters.get("midway") == 1
    assert card_named(s, "Lightning Bolt").zone == "p1:exile"
    before = s.state.players["p2"].life
    to_main_aiming(s, 3)  # Alice's next precombat main phase: she rolls a 5, visiting the Extruder: the copy is cast free
    assert s.state.players["p2"].life == before - 3
    assert card_named(s, "Lightning Bolt").zone == "p1:exile"  # (the exiled card itself stays)
    check(s)


def test_a_roll_that_visits_nothing_copies_nothing(cards, monkeypatch):
    s, myra = myra_table(cards, monkeypatch, 3)
    before = s.state.players["p2"].life
    to_main(s, 3)
    assert s.state.players["p2"].life == before
    check(s)


def test_every_visit_copies_it_again(cards, monkeypatch):
    s, myra = myra_table(cards, monkeypatch, 5)
    rolls(monkeypatch, 5, 5)
    before = s.state.players["p2"].life
    to_main_aiming(s, 3)
    to_main_aiming(s, 5)
    assert s.state.players["p2"].life == before - 6
    check(s)


def test_when_the_attraction_leaves_the_battlefield_the_watch_is_over(cards, monkeypatch):
    s, myra = myra_table(cards, monkeypatch, 5)
    extruder = card_named(s, "Clown Extruder")
    to_hand(s, "Disenchant")
    fund(s, "{1}{W}")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Disenchant").id, targets=[extruder.id])
    play(s)
    assert s.state.cards[extruder.id].zone != "p1:battlefield" and not s.state.rules.delayed
    before = s.state.players["p2"].life
    to_main_aiming(s, 3)
    assert s.state.players["p2"].life == before
    check(s)
